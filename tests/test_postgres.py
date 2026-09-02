from __future__ import annotations

import asyncio
import os
import unittest
from datetime import UTC, datetime
from uuid import uuid4

from noema import (
    Classification,
    ConcurrentAppendError,
    DisclosureForm,
    Event,
    GovernedInformationRef,
    HmacOpaqueInformationIdDeriver,
    InboxDisposition,
    InformationAccessRequest,
    InformationGovernanceAdmission,
    InformationGovernanceEngine,
    InformationGovernanceProjection,
    InformationLineage,
    InformationOperation,
    InformationPolicy,
    LineageTransformation,
    NoemaKernel,
    PolicyBinding,
    PrincipalSnapshot,
    RetentionPolicy,
)
from noema.adapters.stores import PostgresEventStore

POSTGRES_DSN = os.getenv("NOEMA_TEST_POSTGRES_DSN")


@unittest.skipUnless(POSTGRES_DSN, "NOEMA_TEST_POSTGRES_DSN is not configured")
class PostgresConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        assert POSTGRES_DSN is not None
        self.first = await PostgresEventStore.connect(POSTGRES_DSN)
        self.second = await PostgresEventStore.connect(POSTGRES_DSN)

    async def asyncTearDown(self) -> None:
        await self.first.close()
        await self.second.close()

    async def test_concurrent_duplicate_append_has_one_canonical_sequence(self) -> None:
        event = Event(f"test.concurrent.{uuid4()}", "postgres-test")
        first, second = await asyncio.gather(
            self.first.append(event),
            self.second.append(event),
        )
        self.assertEqual(first.id, event.id)
        self.assertEqual(second.id, event.id)
        self.assertEqual(first.sequence, second.sequence)

    async def test_conditional_append_has_one_cross_connection_head_winner(self) -> None:
        expected_head = await self.first.latest_sequence()
        results = await asyncio.gather(
            self.first.append_if_head(
                Event(f"test.head.first.{uuid4()}", "postgres-test"),
                expected_head_sequence=expected_head,
            ),
            self.second.append_if_head(
                Event(f"test.head.second.{uuid4()}", "postgres-test"),
                expected_head_sequence=expected_head,
            ),
            return_exceptions=True,
        )

        self.assertEqual(sum(isinstance(value, Event) for value in results), 1)
        self.assertEqual(
            sum(isinstance(value, ConcurrentAppendError) for value in results),
            1,
        )

    async def test_conditional_append_keeps_postgres_outbox_transactional(self) -> None:
        expected_head = await self.first.latest_sequence()
        event = Event(f"test.outbox.conditional.{uuid4()}", "postgres-test")
        stored = await self.first.append_with_outbox_if_head(
            event,
            topic="noema.test.conditional",
            expected_head_sequence=expected_head,
        )
        claimed = await self.first.claim_outbox(
            f"conditional-worker-{uuid4()}",
            limit=1000,
            lease_seconds=10,
        )

        self.assertEqual(stored.id, event.id)
        self.assertIn(event.id, {record.event.id for record in claimed})

    async def test_concurrent_inbox_claim_has_one_lease_winner(self) -> None:
        message_id = f"message-{uuid4()}"
        first, second = await asyncio.gather(
            self.first.claim_inbox(message_id, "shared-consumer", lease_seconds=10),
            self.second.claim_inbox(message_id, "shared-consumer", lease_seconds=10),
        )
        self.assertCountEqual(
            (first.disposition, second.disposition),
            (InboxDisposition.ACQUIRED, InboxDisposition.BUSY),
        )

    async def test_governance_admission_and_replay_survive_bigserial_gap(self) -> None:
        unique = str(uuid4())
        recorded_at = datetime.now(UTC)
        kernel = NoemaKernel(store=self.first)
        await kernel.start()
        information_ref = GovernedInformationRef.create(
            namespace="postgres-governance",
            stable_key=unique,
            deriver=HmacOpaqueInformationIdDeriver(
                b"0123456789abcdef0123456789abcdef"
            ),
        )
        policy = InformationPolicy.create(
            version=1,
            origin_domains=(f"postgres-test-{unique}",),
            classification=Classification.CONFIDENTIAL,
            allowed_purposes=("work",),
            allowed_recipients=("reader",),
            allowed_trust_domains=("local",),
            allowed_localities=("local",),
            allowed_providers=(),
            cross_agent_sharing=False,
            retention=RetentionPolicy(),
            disclosure_forms=(DisclosureForm.REDACTED,),
            declassification_authorities=(),
            recorded_at=recorded_at,
        )
        lineage = InformationLineage.create(
            information_id=information_ref.information_id,
            source_information_ids=(),
            transformation=LineageTransformation.SOURCE,
            recorded_at=recorded_at,
        )
        binding = PolicyBinding.create(
            information_id=information_ref.information_id,
            lineage_id=lineage.lineage_id,
            policy_ids=(policy.policy_id,),
            bound_at=recorded_at,
        )
        for event in (
            policy.to_event(source="test:postgres-governance"),
            lineage.to_event(source="test:postgres-governance"),
            binding.to_event(source="test:postgres-governance"),
        ):
            await kernel.emit(event)

        gap_seed = Event(
            f"test.postgres.gap.{unique}",
            "test:postgres-gap",
            timestamp=recorded_at,
        )
        await kernel.emit(gap_seed)
        predecessor_head = await self.first.latest_sequence()
        duplicate = await self.second.append(gap_seed)
        self.assertEqual(duplicate.sequence, predecessor_head)
        self.assertEqual(await self.first.latest_sequence(), predecessor_head)

        projection = InformationGovernanceProjection()
        projection.rebuild(await kernel.history())
        engine = InformationGovernanceEngine(projection)
        request = InformationAccessRequest.create(
            information_ref=information_ref,
            context=engine.context_for(
                information_ref=information_ref,
                actor_id="agent:reader",
                principal=PrincipalSnapshot.create(
                    principal_id="reader",
                    roles=(),
                    groups=(),
                    trust_domains=("local",),
                    captured_at=recorded_at,
                ),
                purpose="work",
                operation=InformationOperation.READ,
                source_trust_domain="local",
                destination_trust_domain=None,
                recipient=None,
                decision_time=recorded_at,
                locality="local",
            ),
        )
        receipt = await InformationGovernanceAdmission(
            kernel,
            projection,
        ).admit_access(request)

        self.assertTrue(receipt.record.allowed)
        self.assertEqual(receipt.record.causal_event_cursor, predecessor_head)
        self.assertEqual(receipt.validated_predecessor_head, predecessor_head)
        self.assertGreater(receipt.canonical_sequence, predecessor_head + 1)
        replayed = InformationGovernanceProjection()
        replayed.rebuild(await kernel.history())
        self.assertEqual(
            replayed.access_decision(receipt.record.decision_id),
            receipt.record,
        )
        await kernel.stop()
