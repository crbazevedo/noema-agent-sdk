from __future__ import annotations

import asyncio
import os
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from noema import (
    DISPOSITION_RECORDED_EVENT,
    AttentionAuthorityCeiling,
    AttentionDisposition,
    AttentionDispositionDecision,
    AttentionExposureProjection,
    AttentionFeatureDefinition,
    AttentionFeatureSchemaSnapshot,
    AttentionFeatureType,
    AttentionOpportunity,
    AttentionSemanticConflictError,
    AttentionSourcePolicySnapshot,
    AttentionTelemetryContext,
    Classification,
    ConcurrentAppendError,
    DeliberativeAttentionRecorder,
    DisclosureForm,
    Event,
    FeatureMissingness,
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

    async def test_attention_admission_races_and_replay_survive_bigserial_gap(self) -> None:
        unique = str(uuid4())
        recorded_at = datetime.now(UTC)
        derivation_key = b"postgres-attention-test-key-00001"
        deriver = HmacOpaqueInformationIdDeriver(derivation_key)
        first_kernel = NoemaKernel(store=self.first)
        await first_kernel.start()
        information_ref = GovernedInformationRef.create(
            namespace="postgres-attention",
            stable_key=unique,
            deriver=deriver,
        )
        information_policy = InformationPolicy.create(
            version=2,
            origin_domains=(f"postgres-attention-{unique}",),
            classification=Classification.CONFIDENTIAL,
            allowed_purposes=("attention-telemetry",),
            allowed_recipients=("companion",),
            allowed_trust_domains=("local",),
            allowed_localities=("local",),
            allowed_providers=(),
            cross_agent_sharing=False,
            retention=RetentionPolicy(),
            disclosure_forms=(DisclosureForm.REDACTED,),
            declassification_authorities=(),
            recorded_at=recorded_at,
            allowed_secondary_uses=(InformationOperation.LEARN,),
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
            policy_ids=(information_policy.policy_id,),
            bound_at=recorded_at,
        )
        await first_kernel.emit_many(
            (
                information_policy.to_event(source="test:postgres-attention"),
                lineage.to_event(source="test:postgres-attention"),
                binding.to_event(source="test:postgres-attention"),
            )
        )
        schema = AttentionFeatureSchemaSnapshot.create(
            version=f"postgres-v1-{unique}",
            features=(
                AttentionFeatureDefinition(
                    name="deep_work",
                    value_type=AttentionFeatureType.BOOLEAN,
                    required=True,
                    policy_safe=True,
                    missingness=FeatureMissingness.REQUIRED_EXPOSURE_INCOMPLETE,
                ),
            ),
            recorded_at=recorded_at + timedelta(seconds=1),
        )
        source_type = f"test.postgres.attention.{unique}"
        source_policy = AttentionSourcePolicySnapshot.create(
            version=f"postgres-v1-{unique}",
            feature_schema_id=schema.schema_id,
            source_event_types=(source_type,),
            information_id_payload_fields=("governed_information_id",),
            scope=f"postgres-{unique}",
            recorded_at=recorded_at + timedelta(seconds=2),
        )
        base_recorder = DeliberativeAttentionRecorder(
            first_kernel,
            derived_information_id_deriver=deriver,
            source="test:postgres-attention",
        )
        await base_recorder.register_contracts(
            feature_schema=schema,
            source_policy=source_policy,
        )
        await first_kernel.emit(
            Event(
                id=f"postgres-attention-intent-{unique}",
                type="test.postgres.current_intent",
                source="test:postgres-attention",
                timestamp=recorded_at + timedelta(seconds=3),
            )
        )
        context = AttentionTelemetryContext(
            principal=PrincipalSnapshot.create(
                principal_id="companion",
                roles=(),
                groups=(),
                trust_domains=("local",),
                captured_at=recorded_at,
            ),
            actor_id="agent:companion",
            purpose="attention-telemetry",
            source_trust_domain="local",
            locality="local",
        )

        async def source_event(index: int) -> Event:
            return await first_kernel.emit(
                Event(
                    id=f"postgres-attention-source-{unique}-{index}",
                    type=source_type,
                    source="test:postgres-attention",
                    timestamp=recorded_at + timedelta(minutes=index + 1),
                    payload={
                        "deep_work": True,
                        "governed_information_id": information_ref.information_id,
                    },
                )
            )

        def decision(
            opportunity: AttentionOpportunity, disposition: AttentionDisposition
        ) -> AttentionDispositionDecision:
            return AttentionDispositionDecision(
                disposition=disposition,
                features=opportunity.features,
                situation_causal_cursor=opportunity.situation_causal_cursor,
                decision_mechanism_id="postgres-fixture-provider",
                decision_mechanism_version="1",
                decision_configuration_ref=f"fixture:{unique}",
                decision_refs=(f"postgres-attention-intent-{unique}",),
                governing_intent_refs=(f"postgres-attention-intent-{unique}",),
                authority_ceiling=AttentionAuthorityCeiling.INTERNAL_ATTENTION_ONLY,
                governed_information_ids=opportunity.governed_information_ids,
                valid_at=opportunity.source_event_timestamp,
                known_at=opportunity.source_event_timestamp,
                decided_at=opportunity.source_event_timestamp,
            )

        gap_source = await source_event(0)

        class _GapRecorder(DeliberativeAttentionRecorder):
            injected = False

            async def _append_exact(
                self,
                event: Event,
                projection: AttentionExposureProjection,
            ) -> Event:
                if event.type == DISPOSITION_RECORDED_EVENT and not self.injected:
                    self.injected = True
                    gap_seed = Event(
                        f"test.postgres.attention-gap.{unique}",
                        "test:postgres-attention-gap",
                        timestamp=recorded_at,
                    )
                    await self.kernel.emit(gap_seed)
                    await self.second_store.append(gap_seed)
                return await super()._append_exact(event, projection)

            def __init__(self, second_store: PostgresEventStore) -> None:
                super().__init__(
                    first_kernel,
                    derived_information_id_deriver=deriver,
                    source="test:postgres-attention-gap",
                )
                self.second_store = second_store

        gap_recorder = _GapRecorder(self.second)
        gap_opportunity = await base_recorder.prepare_opportunity(
            source_event_id=gap_source.id,
            source_policy_id=source_policy.policy_id,
            telemetry_context=context,
        )
        gap_record = await gap_recorder.record_disposition(
            opportunity=gap_opportunity,
            decision=decision(gap_opportunity, AttentionDisposition.REMEMBER),
            telemetry_context=context,
        )
        disposition_event = next(
            event
            for event in await first_kernel.history()
            if event.id == f"attention-disposition-recorded:{gap_record.disposition_id}"
        )
        assert disposition_event.sequence is not None
        self.assertGreater(
            disposition_event.sequence,
            gap_record.admitted_predecessor_head + 1,
        )
        replayed = AttentionExposureProjection()
        replayed.rebuild(
            first_kernel.schemas.normalize(event) for event in await first_kernel.history()
        )
        self.assertEqual(replayed.disposition(gap_record.disposition_id), gap_record)

        second_kernel = NoemaKernel(store=self.second)
        await second_kernel.start()
        first_recorder = DeliberativeAttentionRecorder(
            first_kernel,
            derived_information_id_deriver=deriver,
            source="test:postgres-attention-distributed",
        )
        second_recorder = DeliberativeAttentionRecorder(
            second_kernel,
            derived_information_id_deriver=deriver,
            source="test:postgres-attention-distributed",
        )
        equal_source = await source_event(1)
        equal_opportunity = await first_recorder.prepare_opportunity(
            source_event_id=equal_source.id,
            source_policy_id=source_policy.policy_id,
            telemetry_context=context,
        )
        equal_decision = decision(equal_opportunity, AttentionDisposition.WAKE)
        equal = await asyncio.gather(
            first_recorder.record_disposition(
                opportunity=equal_opportunity,
                decision=equal_decision,
                telemetry_context=context,
            ),
            second_recorder.record_disposition(
                opportunity=equal_opportunity,
                decision=equal_decision,
                telemetry_context=context,
            ),
        )
        self.assertEqual(equal[0], equal[1])

        conflict_source = await source_event(2)
        conflict_opportunity = await first_recorder.prepare_opportunity(
            source_event_id=conflict_source.id,
            source_policy_id=source_policy.policy_id,
            telemetry_context=context,
        )
        conflict = await asyncio.gather(
            first_recorder.record_disposition(
                opportunity=conflict_opportunity,
                decision=decision(conflict_opportunity, AttentionDisposition.DEFER),
                telemetry_context=context,
            ),
            second_recorder.record_disposition(
                opportunity=conflict_opportunity,
                decision=decision(conflict_opportunity, AttentionDisposition.SUPPRESS),
                telemetry_context=context,
            ),
            return_exceptions=True,
        )
        self.assertEqual(sum(not isinstance(value, BaseException) for value in conflict), 1)
        self.assertEqual(
            sum(isinstance(value, AttentionSemanticConflictError) for value in conflict),
            1,
        )
        final = AttentionExposureProjection()
        final.rebuild(
            first_kernel.schemas.normalize(event) for event in await first_kernel.history()
        )
        matching = tuple(
            value
            for value in final.dispositions
            if value.source_event_id == conflict_source.id
        )
        self.assertEqual(len(matching), 1)
        await first_kernel.stop()
        await second_kernel.stop()
