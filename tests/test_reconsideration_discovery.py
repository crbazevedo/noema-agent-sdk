from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from noema import (
    ALLOCATION_TRACE_RECORDED_EVENT,
    EVIDENCE_QUALIFICATION_BOUND_EVENT,
    OPPORTUNITY_RECORDED_EVENT,
    SHADOW_PROPOSAL_RECORDED_EVENT,
    AllocationLabel,
    CognitiveAllocationOutcomeLink,
    ConsumerCheckpoint,
    CurrentCognitiveBasis,
    DeterministicDormantInquiryDetector,
    DiscoveryReason,
    DormancyReason,
    DormantInquiryDescriptor,
    DormantInquiryIndex,
    EpistemicType,
    Event,
    EvidenceQualificationRole,
    MemoryProjection,
    NoemaKernel,
    ReconsiderationDiscoveryPolicySnapshot,
    ReconsiderationDiscoveryProjection,
    ReconsiderationDiscoveryWorker,
    ReconsiderationOpportunityKind,
    ReconsiderationPolicySnapshot,
    ReconsiderationProjection,
    ReconsiderationShadowWorker,
    ScarceCognitionCostSnapshot,
    SemanticAssertion,
    StaticReconsiderationDiscoveryAuthority,
)
from tests.test_reconsideration import (
    ID_DERIVER,
    NOW,
    MutableClock,
    current_evidence,
    prepare_mandate_fixture,
    scarce_budget,
    seed,
)


def discovery_policy(
    *,
    max_opportunities: int = 8,
    max_dormant: int = 64,
    max_qualifications: int = 32,
) -> ReconsiderationDiscoveryPolicySnapshot:
    return ReconsiderationDiscoveryPolicySnapshot.create(
        version="discovery-fixture-v1",
        max_opportunities_emitted=max_opportunities,
        max_dormant_inquiries_examined=max_dormant,
        max_qualification_bindings_consumed=max_qualifications,
        seed_costs=ScarceCognitionCostSnapshot(
            compute_units=0.05,
            wall_time_seconds=1.0,
            attention_units=0.01,
            context_switching_units=0.0,
            interruption_units=0.01,
            privacy_exposure_units=0.01,
            opportunity_cost_units=0.01,
            revalidation_units=0.01,
        ),
    )


async def prepare_discovery(
    *,
    count: int = 1,
    max_candidates: int = 1,
    kernel: NoemaKernel | None = None,
):
    (
        kernel,
        reconsideration_worker,
        mandate,
        principal,
        g1,
        current_g1,
        inquiries,
        information_refs,
        clock,
    ) = await prepare_mandate_fixture(
        count=count,
        max_candidates=max_candidates,
        minimum_interval_seconds=0.0,
        kernel=kernel,
    )
    authorization = await kernel.emit(
        Event(
            "user.reconsideration_evidence_authorized",
            "fixture:user",
            subject="user:carlos",
            timestamp=clock(),
        )
    )
    authority = StaticReconsiderationDiscoveryAuthority(
        authority_id="discovery-authority:fixture",
        scope_resolvers=(("fixture-scope", "1"),),
        qualification_resolvers=(("fixture-qualifier", "1"),),
        qualification_roles=tuple(EvidenceQualificationRole),
    )
    worker = ReconsiderationDiscoveryWorker(
        kernel,
        reconsideration_worker=reconsideration_worker,
        authority=authority,
        derived_information_id_deriver=ID_DERIVER,
        policy=discovery_policy(),
        clock=clock,
    )
    for inquiry, information_ref in zip(inquiries, information_refs, strict=True):
        await worker.bind_inquiry_scope(
            inquiry_id=inquiry.inquiry_id,
            domain_ids=("personal-research",),
            governed_information_ids=(information_ref.information_id,),
            evidence_refs=(f"event:{authorization.id}",),
            resolver_id="fixture-scope",
            resolver_version="1",
            authorization_ref=f"event:{authorization.id}",
            information_use_purpose=mandate.information_use_purpose,
            information_policy_ids=mandate.information_policy_ids,
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
    return (
        kernel,
        reconsideration_worker,
        worker,
        mandate,
        principal,
        g1,
        current_g1,
        inquiries,
        information_refs,
        clock,
        authorization,
    )


async def qualify(
    worker: ReconsiderationDiscoveryWorker,
    *,
    inquiry_id: str,
    information_id: str,
    mandate,
    principal,
    clock: MutableClock,
    authorization: Event,
    role: EvidenceQualificationRole,
    value: float,
    derivation_refs: tuple[str, ...] = (),
    target_refs: tuple[str, ...] | None = None,
    confidence: float = 0.95,
    source_refs: tuple[str, ...] | None = None,
):
    clock.advance(timedelta(seconds=1))
    assertion = SemanticAssertion.create(
        subject=inquiry_id,
        predicate=f"reconsideration.{role.value.lower()}",
        value=value,
        epistemic_type=(EpistemicType.INFERRED if derivation_refs else EpistemicType.REPORTED),
        confidence=confidence,
        valid_from=clock(),
        recorded_at=clock(),
        fresh_until=clock() + timedelta(days=1),
        source_refs=source_refs or (f"event:{authorization.id}",),
        derivation_refs=derivation_refs,
        mutable_world=True,
    )
    await worker.kernel.emit(assertion.to_event(source="fixture:memory"))
    clock.advance(timedelta(seconds=1))
    binding = await worker.bind_evidence_qualification(
        assertion_ref=assertion.assertion_id,
        role=role,
        target_refs=target_refs or (inquiry_id,),
        qualifier_id="fixture-qualifier",
        qualifier_version="1",
        authorization_ref=f"event:{authorization.id}",
        governed_information_ids=(information_id,),
        information_use_purpose=mandate.information_use_purpose,
        information_policy_ids=mandate.information_policy_ids,
        principal=principal,
        actor_id="user:carlos",
        source_trust_domain="local",
        locality="local",
        bound_at=clock(),
    )
    return assertion, binding


async def critical_qualifications(
    worker: ReconsiderationDiscoveryWorker,
    *,
    inquiry_id: str,
    information_id: str,
    mandate,
    principal,
    clock: MutableClock,
    authorization: Event,
):
    old_source = await worker.kernel.emit(
        Event(
            "user.value_reported",
            "fixture:user",
            subject="user:carlos",
            timestamp=NOW - timedelta(days=2),
        )
    )
    old_value = SemanticAssertion.create(
        subject="user:carlos",
        predicate="user_value.careful_exploration",
        value=0.95,
        epistemic_type=EpistemicType.REPORTED,
        confidence=0.95,
        valid_from=NOW - timedelta(days=2),
        recorded_at=NOW - timedelta(days=2),
        source_refs=(f"event:{old_source.id}",),
    )
    await worker.kernel.emit(old_value.to_event(source="fixture:memory"))
    value_assertion, value_binding = await qualify(
        worker,
        inquiry_id=inquiry_id,
        information_id=information_id,
        mandate=mandate,
        principal=principal,
        clock=clock,
        authorization=authorization,
        role=EvidenceQualificationRole.DURABLE_VALUE,
        value=0.95,
        derivation_refs=(old_value.assertion_id,),
    )
    current_source = await worker.kernel.emit(
        Event(
            "external.current_revalidation",
            "fixture:evidence",
            {"still_relevant": True},
            subject=inquiry_id,
            timestamp=clock(),
        )
    )
    current_revalidation = await qualify(
        worker,
        inquiry_id=inquiry_id,
        information_id=information_id,
        mandate=mandate,
        principal=principal,
        clock=clock,
        authorization=authorization,
        role=EvidenceQualificationRole.CURRENT_REVALIDATION,
        value=1.0,
        source_refs=(f"event:{current_source.id}",),
    )
    alignment = await qualify(
        worker,
        inquiry_id=inquiry_id,
        information_id=information_id,
        mandate=mandate,
        principal=principal,
        clock=clock,
        authorization=authorization,
        role=EvidenceQualificationRole.VALUE_ALIGNMENT,
        value=0.85,
        confidence=0.25,
    )
    motivation = await qualify(
        worker,
        inquiry_id=inquiry_id,
        information_id=information_id,
        mandate=mandate,
        principal=principal,
        clock=clock,
        authorization=authorization,
        role=EvidenceQualificationRole.MOTIVATION,
        value=0.90,
    )
    expected = await qualify(
        worker,
        inquiry_id=inquiry_id,
        information_id=information_id,
        mandate=mandate,
        principal=principal,
        clock=clock,
        authorization=authorization,
        role=EvidenceQualificationRole.EXPECTED_OUTCOME_VALUE,
        value=0.90,
    )
    return (
        old_value,
        value_assertion,
        value_binding,
        current_revalidation,
        alignment,
        motivation,
        expected,
    )


class DormantCognitionDiscoveryAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_flagship_discovers_qualified_history_and_only_proposes(self) -> None:
        (
            kernel,
            _reconsideration_worker,
            worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery(count=2)
        (
            old_value,
            current_value,
            _value_binding,
            _current_revalidation,
            alignment,
            _motivation,
            expected,
        ) = await critical_qualifications(
            worker,
            inquiry_id=inquiries[0].inquiry_id,
            information_id=information_refs[0].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
        )
        slack_only = await kernel.emit(
            Event(
                "reconsideration.opportunity_window_opened",
                "fixture",
                subject=inquiries[1].inquiry_id,
                timestamp=clock(),
            )
        )
        no_opportunity = await worker.run_trigger(
            trigger_event_id=slack_only.id,
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(no_opportunity.opportunities, ())

        trigger = f"reconsideration-evidence-qualified:{expected[1].qualification_id}"
        before = await kernel.store.latest_sequence()
        result = await worker.run_trigger(
            trigger_event_id=trigger,
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(len(result.opportunities), 1)
        self.assertEqual(len(result.seeds), 1)
        self.assertIsNotNone(result.allocation)
        assert result.allocation is not None
        self.assertEqual(
            len(result.allocation.selected_candidate_ids),
            1,
            result.allocation.decisions,
        )
        self.assertIn(
            DiscoveryReason.QUALIFIED_PERSISTENT_VALUE,
            result.opportunities[0].discovery_reasons,
        )
        self.assertEqual(
            result.opportunities[0].kind,
            ReconsiderationOpportunityKind.NEW_REVALIDATION,
        )
        self.assertLess(old_value.recorded_at, current_value.recorded_at)
        self.assertIn(old_value.assertion_id, current_value.derivation_refs)
        self.assertNotEqual(old_value.assertion_id, current_value.assertion_id)
        self.assertEqual(result.seeds[0].features.evidence_freshness, 1.0)
        assert result.seeds[0].features.value_alignment_estimate is not None
        self.assertEqual(result.seeds[0].features.value_alignment_estimate.confidence, 0.25)
        self.assertEqual(result.seeds[0].features.meaningful_new_evidence, 1.0)
        self.assertEqual(
            result.seeds[0].features.value_alignment_estimate.evidence_refs,
            (f"event:memory-assertion:{alignment[0].assertion_id}",),
        )

        projection = await worker.current_projection()
        self.assertEqual(
            len(projection.reconsideration.proposals),
            1,
            projection.reconsideration.allocations,
        )
        replay = ReconsiderationDiscoveryProjection()
        history = tuple(kernel.schemas.normalize(value) for value in await kernel.history())
        replay.rebuild(history)
        self.assertEqual(replay.semantic_snapshot(), projection.semantic_snapshot())
        opportunity_event = next(
            value for value in history if value.type == OPPORTUNITY_RECORDED_EVENT
        )
        assert opportunity_event.sequence is not None
        predecessor = result.opportunities[0].admitted_at_head
        before_opportunity = tuple(
            value for value in history if (value.sequence or 0) <= predecessor
        )
        gap_replay = ReconsiderationDiscoveryProjection()
        gap_replay.rebuild(
            (*before_opportunity, replace(opportunity_event, sequence=predecessor + 7))
        )
        self.assertEqual(gap_replay.opportunities, result.opportunities)
        later = tuple(value for value in await kernel.history() if (value.sequence or 0) > before)
        self.assertFalse(
            any(value.type.startswith(("intent.goal", "work.", "action.")) for value in later)
        )
        discovery_payloads = json.dumps(
            [
                value.payload
                for value in later
                if value.type in {EVIDENCE_QUALIFICATION_BOUND_EVENT, OPPORTUNITY_RECORDED_EVENT}
            ]
        )
        self.assertNotIn(inquiries[0].question, discovery_payloads)
        await kernel.stop()

    async def test_generic_values_checkpoint_no_op_without_unrelated_churn(self) -> None:
        (
            kernel,
            _rw,
            worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery()
        await qualify(
            worker,
            inquiry_id="user:carlos",
            information_id=information_refs[0].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
            role=EvidenceQualificationRole.DURABLE_VALUE,
            value=0.95,
        )
        await qualify(
            worker,
            inquiry_id=inquiries[0].inquiry_id,
            information_id=information_refs[0].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
            role=EvidenceQualificationRole.MOTIVATION,
            value=0.9,
        )
        _assertion, expected = await qualify(
            worker,
            inquiry_id=inquiries[0].inquiry_id,
            information_id=information_refs[0].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
            role=EvidenceQualificationRole.EXPECTED_OUTCOME_VALUE,
            value=0.9,
        )
        before = await kernel.store.latest_sequence()
        result = await worker.run_trigger(
            trigger_event_id=f"reconsideration-evidence-qualified:{expected.qualification_id}",
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(result.opportunities, ())
        self.assertEqual(await kernel.store.latest_sequence(), before + 1)
        checkpoint = ConsumerCheckpoint.from_event((await kernel.history())[-1])
        trigger_event = next(
            value
            for value in await kernel.history()
            if value.id == f"reconsideration-evidence-qualified:{expected.qualification_id}"
        )
        self.assertEqual(checkpoint.last_completed_sequence, trigger_event.sequence)

        unrelated = await kernel.emit(
            Event("fixture.unrelated", "fixture", subject="unrelated", timestamp=clock())
        )
        unrelated_head = await kernel.store.latest_sequence()
        result = await worker.run_trigger(
            trigger_event_id=unrelated.id,
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(result.opportunities, ())
        self.assertEqual(await kernel.store.latest_sequence(), unrelated_head)
        await kernel.stop()

    async def test_dormancy_is_projection_only_and_explains_terminal_intent(self) -> None:
        (
            kernel,
            _rw,
            worker,
            _mandate,
            _principal,
            _g1,
            _current,
            inquiries,
            _information,
            clock,
            _authorization,
        ) = await prepare_discovery()
        projection = await worker.current_projection()
        index = DormantInquiryIndex.derive(
            endogenous=projection.endogenous,
            reconsideration=projection.reconsideration,
            at=clock(),
        )
        descriptor = index.get(inquiries[0].inquiry_id)
        self.assertIsNotNone(descriptor)
        assert descriptor is not None
        self.assertIn(DormancyReason.INTENT_REVISION_STALE, descriptor.reasons)
        self.assertIn(DormancyReason.INTENT_TERMINAL, descriptor.reasons)
        self.assertFalse(any("dorman" in value.type for value in await kernel.history()))
        await kernel.stop()

    async def test_qualification_authority_and_distinct_assertions_fail_closed(
        self,
    ) -> None:
        (
            kernel,
            _rw,
            worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery()
        q, binding = await qualify(
            worker,
            inquiry_id=inquiries[0].inquiry_id,
            information_id=information_refs[0].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
            role=EvidenceQualificationRole.DURABLE_VALUE,
            value=0.9,
        )
        before = sum(
            value.type == EVIDENCE_QUALIFICATION_BOUND_EVENT for value in await kernel.history()
        )
        with self.assertRaisesRegex(PermissionError, "not authenticated"):
            await worker.bind_evidence_qualification(
                assertion_ref=q.assertion_id,
                role=EvidenceQualificationRole.PREFERENCE,
                target_refs=(inquiries[0].inquiry_id,),
                qualifier_id="forged-qualifier",
                qualifier_version="1",
                authorization_ref=f"event:{authorization.id}",
                governed_information_ids=(information_refs[0].information_id,),
                information_use_purpose=mandate.information_use_purpose,
                information_policy_ids=mandate.information_policy_ids,
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
                bound_at=clock(),
            )
        self.assertEqual(
            sum(
                value.type == EVIDENCE_QUALIFICATION_BOUND_EVENT for value in await kernel.history()
            ),
            before,
        )

        bindings = [binding]
        for role in (
            EvidenceQualificationRole.VALUE_ALIGNMENT,
            EvidenceQualificationRole.MOTIVATION,
            EvidenceQualificationRole.EXPECTED_OUTCOME_VALUE,
        ):
            bindings.append(
                await worker.bind_evidence_qualification(
                    assertion_ref=q.assertion_id,
                    role=role,
                    target_refs=(inquiries[0].inquiry_id,),
                    qualifier_id="fixture-qualifier",
                    qualifier_version="1",
                    authorization_ref=f"event:{authorization.id}",
                    governed_information_ids=(information_refs[0].information_id,),
                    information_use_purpose=mandate.information_use_purpose,
                    information_policy_ids=mandate.information_policy_ids,
                    principal=principal,
                    actor_id="user:carlos",
                    source_trust_domain="local",
                    locality="local",
                    bound_at=clock(),
                )
            )
        result = await worker.run_trigger(
            trigger_event_id=f"reconsideration-evidence-qualified:{bindings[-1].qualification_id}",
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(result.opportunities, ())
        await kernel.stop()

    async def test_durable_value_alone_cannot_supply_candidate_estimates(self) -> None:
        (
            kernel,
            _rw,
            worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery()
        _assertion, durable = await qualify(
            worker,
            inquiry_id=inquiries[0].inquiry_id,
            information_id=information_refs[0].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
            role=EvidenceQualificationRole.DURABLE_VALUE,
            value=0.95,
        )
        result = await worker.run_trigger(
            trigger_event_id=f"reconsideration-evidence-qualified:{durable.qualification_id}",
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(result.opportunities, ())
        await kernel.stop()

    async def test_critical_estimates_require_one_common_stable_target(self) -> None:
        (
            kernel,
            _rw,
            worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery()
        inquiry = inquiries[0]
        for role, targets in (
            (EvidenceQualificationRole.DURABLE_VALUE, (inquiry.inquiry_id,)),
            (EvidenceQualificationRole.VALUE_ALIGNMENT, (inquiry.inquiry_id,)),
            (EvidenceQualificationRole.MOTIVATION, inquiry.target_refs),
        ):
            await qualify(
                worker,
                inquiry_id=inquiry.inquiry_id,
                information_id=information_refs[0].information_id,
                mandate=mandate,
                principal=principal,
                clock=clock,
                authorization=authorization,
                role=role,
                value=0.9,
                target_refs=targets,
            )
        _assertion, expected = await qualify(
            worker,
            inquiry_id=inquiry.inquiry_id,
            information_id=information_refs[0].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
            role=EvidenceQualificationRole.EXPECTED_OUTCOME_VALUE,
            value=0.9,
            target_refs=(inquiry.inquiry_id,),
        )
        result = await worker.run_trigger(
            trigger_event_id=f"reconsideration-evidence-qualified:{expected.qualification_id}",
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(result.opportunities, ())
        await kernel.stop()

    async def test_seed_features_use_versioned_semantics_without_new_evidence_inflation(
        self,
    ) -> None:
        (
            kernel,
            _rw,
            worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery()
        inquiry = inquiries[0]
        bindings = []
        for role, value, confidence in (
            (EvidenceQualificationRole.DURABLE_VALUE, 0.95, 0.95),
            (EvidenceQualificationRole.VALUE_ALIGNMENT, 0.8, 0.2),
            (EvidenceQualificationRole.MOTIVATION, 0.9, 0.9),
            (EvidenceQualificationRole.EXPECTED_OUTCOME_VALUE, 0.9, 0.9),
        ):
            bindings.append(
                await qualify(
                    worker,
                    inquiry_id=inquiry.inquiry_id,
                    information_id=information_refs[0].information_id,
                    mandate=mandate,
                    principal=principal,
                    clock=clock,
                    authorization=authorization,
                    role=role,
                    value=value,
                    confidence=confidence,
                )
            )
        result = await worker.run_trigger(
            trigger_event_id=(
                f"reconsideration-evidence-qualified:{bindings[-1][1].qualification_id}"
            ),
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(len(result.seeds), 1)
        features = result.seeds[0].features
        self.assertEqual(features.unresolvedness, inquiry.uncertainty)
        self.assertEqual(features.evidence_freshness, 1.0)
        self.assertEqual(features.meaningful_new_evidence, 0.0)
        assert features.value_alignment_estimate is not None
        self.assertEqual(features.value_alignment_estimate.confidence, 0.2)
        await kernel.stop()

    async def test_old_evidence_requires_a_post_inquiry_applicability_assertion(self) -> None:
        async def attempt(*, reattest: bool):
            kernel = NoemaKernel()
            old_source = await kernel.emit(
                Event(
                    "user.value_reported",
                    "fixture:user",
                    subject="user:carlos",
                    timestamp=NOW - timedelta(days=2),
                )
            )
            old_value = SemanticAssertion.create(
                subject="user:carlos",
                predicate="user_value.durable_exploration",
                value=0.95,
                epistemic_type=EpistemicType.REPORTED,
                confidence=0.95,
                valid_from=NOW - timedelta(days=2),
                recorded_at=NOW - timedelta(days=2),
                source_refs=(f"event:{old_source.id}",),
            )
            old_event = await kernel.emit(old_value.to_event(source="fixture:memory"))
            (
                kernel,
                _rw,
                worker,
                mandate,
                principal,
                _g1,
                _current,
                inquiries,
                information_refs,
                clock,
                authorization,
            ) = await prepare_discovery(kernel=kernel)
            inquiry = inquiries[0]
            for role in (
                EvidenceQualificationRole.VALUE_ALIGNMENT,
                EvidenceQualificationRole.MOTIVATION,
                EvidenceQualificationRole.EXPECTED_OUTCOME_VALUE,
            ):
                await qualify(
                    worker,
                    inquiry_id=inquiry.inquiry_id,
                    information_id=information_refs[0].information_id,
                    mandate=mandate,
                    principal=principal,
                    clock=clock,
                    authorization=authorization,
                    role=role,
                    value=0.9,
                )
            if reattest:
                current_value, durable = await qualify(
                    worker,
                    inquiry_id=inquiry.inquiry_id,
                    information_id=information_refs[0].information_id,
                    mandate=mandate,
                    principal=principal,
                    clock=clock,
                    authorization=authorization,
                    role=EvidenceQualificationRole.DURABLE_VALUE,
                    value=0.95,
                    derivation_refs=(old_value.assertion_id,),
                    source_refs=(f"event:{old_source.id}",),
                )
            else:
                current_value = old_value
                durable = await worker.bind_evidence_qualification(
                    assertion_ref=old_value.assertion_id,
                    role=EvidenceQualificationRole.DURABLE_VALUE,
                    target_refs=(inquiry.inquiry_id,),
                    qualifier_id="fixture-qualifier",
                    qualifier_version="1",
                    authorization_ref=f"event:{authorization.id}",
                    governed_information_ids=(information_refs[0].information_id,),
                    information_use_purpose=mandate.information_use_purpose,
                    information_policy_ids=mandate.information_policy_ids,
                    principal=principal,
                    actor_id="user:carlos",
                    source_trust_domain="local",
                    locality="local",
                    bound_at=clock(),
                )
            result = await worker.run_trigger(
                trigger_event_id=f"reconsideration-evidence-qualified:{durable.qualification_id}",
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
            assert old_event.sequence is not None
            self.assertLessEqual(old_event.sequence, inquiry.causal_cursor)
            await kernel.stop()
            return result, old_value, current_value

        rejected, _old, _same = await attempt(reattest=False)
        self.assertEqual(rejected.seeds, ())

        accepted, old_value, current_value = await attempt(reattest=True)
        self.assertEqual(len(accepted.seeds), 1)
        self.assertIn(old_value.assertion_id, current_value.derivation_refs)
        current_ref = f"event:memory-assertion:{current_value.assertion_id}"
        old_ref = f"event:memory-assertion:{old_value.assertion_id}"
        self.assertIn(current_ref, accepted.seeds[0].current_evidence_refs)
        self.assertNotIn(old_ref, accepted.seeds[0].current_evidence_refs)

    async def test_explicit_target_is_narrowed_before_dormant_examination_budget(self) -> None:
        (
            kernel,
            reconsideration_worker,
            fixture_worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery(count=3)
        worker = ReconsiderationDiscoveryWorker(
            kernel,
            reconsideration_worker=reconsideration_worker,
            authority=fixture_worker.authority,
            derived_information_id_deriver=ID_DERIVER,
            policy=discovery_policy(max_dormant=2),
            clock=clock,
        )
        await worker.record_policy()
        target = max(inquiries, key=lambda value: value.inquiry_id)
        target_index = inquiries.index(target)
        *_, expected = await critical_qualifications(
            worker,
            inquiry_id=target.inquiry_id,
            information_id=information_refs[target_index].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
        )
        result = await worker.run_trigger(
            trigger_event_id=f"reconsideration-evidence-qualified:{expected[1].qualification_id}",
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(
            tuple(value.historical_inquiry_id for value in result.opportunities),
            (target.inquiry_id,),
        )
        await kernel.stop()

    def test_discovery_budgets_bound_semantic_evaluation_before_it_is_spent(self) -> None:
        class FakeEndogenous:
            def __init__(self, inquiries):  # type: ignore[no-untyped-def]
                self._inquiries = inquiries
                self.strategy = SimpleNamespace(goal_revisions=())

            def inquiry(self, inquiry_id):  # type: ignore[no-untyped-def]
                return self._inquiries.get(inquiry_id)

        class FakeReconsideration:
            latest_policy = None
            allocations = ()

            def __init__(self, candidates):  # type: ignore[no-untyped-def]
                self.candidates = candidates

            @staticmethod
            def candidate_was_selected(_candidate_id):  # type: ignore[no-untyped-def]
                return False

        class CheapBinding:
            def __init__(self, ordinal: int, target: str) -> None:
                self.qualification_id = f"qualification:{ordinal:05d}"
                self.target_refs = (target,)

        class CountingDetector(DeterministicDormantInquiryDetector):
            def __init__(self) -> None:
                self.evaluated_inquiries: list[str] = []
                self.qualification_checks = 0

            def _reasons(self, **kwargs):  # type: ignore[no-untyped-def]
                self.evaluated_inquiries.append(kwargs["inquiry"].inquiry_id)
                return super()._reasons(**kwargs)

            def _qualification_is_current(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                self.qualification_checks += 1
                return False

        count = 10_000
        inquiry_ids = tuple(f"inquiry:{index:05d}" for index in range(count))
        explicit_target = inquiry_ids[-1]
        inquiries = {
            inquiry_id: SimpleNamespace(
                inquiry_id=inquiry_id,
                target_refs=(f"target:{inquiry_id}",),
                governing_intent_refs=(),
            )
            for inquiry_id in inquiry_ids
        }
        descriptors = tuple(
            DormantInquiryDescriptor(
                inquiry_id=inquiry_id,
                epoch_id=f"epoch:{inquiry_id}",
                historical_causal_cursor=1,
                reasons=(DormancyReason.INQUIRY_EXPIRED,),
                target_refs=(f"target:{inquiry_id}",),
                dream_status=None,
                last_considered_cut=0,
            )
            for inquiry_id in inquiry_ids
        )
        basis = CurrentCognitiveBasis.from_mandate("mandate:budget-fixture")
        deferred = tuple(
            SimpleNamespace(
                candidate_id=f"candidate:{inquiry_id}",
                historical=SimpleNamespace(inquiry_id=inquiry_id),
                current_basis=basis,
                features=SimpleNamespace(estimates=lambda: ()),
            )
            for inquiry_id in inquiry_ids[:-1]
        )
        trigger = Event(
            "user.reconsideration_requested",
            "fixture:user",
            subject=explicit_target,
            timestamp=NOW,
        ).with_sequence(10_001)
        detector = CountingDetector()
        with patch(
            "noema.reconsideration.discovery.DormantInquiryIndex.derive",
            return_value=DormantInquiryIndex(descriptors),
        ):
            nominations = detector.discover(
                endogenous=FakeEndogenous(inquiries),  # type: ignore[arg-type]
                reconsideration=FakeReconsideration(deferred),  # type: ignore[arg-type]
                memory=MemoryProjection(),
                trigger=trigger,
                basis=basis,
                policy=discovery_policy(max_dormant=8, max_qualifications=12),
                scope_bindings=tuple(
                    SimpleNamespace(inquiry_id=inquiry_id) for inquiry_id in inquiry_ids
                ),  # type: ignore[arg-type]
                qualification_bindings=tuple(
                    CheapBinding(index, explicit_target) for index in range(1_000)
                ),  # type: ignore[arg-type]
                current_budget=scarce_budget(max_candidates=8),
                current_maximum_interruption_units=0.25,
                current_foreground_refs=(),
                canonical_events=(trigger,),
                at=NOW,
            )
        self.assertEqual(nominations, ())
        self.assertLessEqual(len(detector.evaluated_inquiries), 8)
        self.assertEqual(detector.evaluated_inquiries[0], explicit_target)
        self.assertLessEqual(detector.qualification_checks, 12)

    async def test_qualification_limit_is_one_discovery_batch_budget(self) -> None:
        (
            kernel,
            reconsideration_worker,
            fixture_worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery(count=2, max_candidates=2)
        worker = ReconsiderationDiscoveryWorker(
            kernel,
            reconsideration_worker=reconsideration_worker,
            authority=fixture_worker.authority,
            derived_information_id_deriver=ID_DERIVER,
            policy=discovery_policy(max_qualifications=5),
            clock=clock,
        )
        await worker.record_policy()
        for inquiry, information in zip(inquiries, information_refs, strict=True):
            await critical_qualifications(
                worker,
                inquiry_id=inquiry.inquiry_id,
                information_id=information.information_id,
                mandate=mandate,
                principal=principal,
                clock=clock,
                authorization=authorization,
            )
        trigger = await kernel.emit(
            Event(
                "user.reconsideration_requested",
                "fixture:user",
                {"target_refs": [value.inquiry_id for value in inquiries]},
                timestamp=clock(),
            )
        )
        result = await worker.run_trigger(
            trigger_event_id=trigger.id,
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(len(result.opportunities), 1)
        self.assertLessEqual(
            sum(len(value.qualification_ids) for value in result.opportunities),
            5,
        )
        await kernel.stop()

    async def test_partial_discovery_recovers_exactly_once(self) -> None:
        class CrashBeforeHandoff(ReconsiderationDiscoveryWorker):
            crashed = False

            async def _handoff(self, **kwargs):  # type: ignore[no-untyped-def]
                if not self.crashed:
                    self.crashed = True
                    raise RuntimeError("simulated crash after opportunity")
                return await super()._handoff(**kwargs)

        (
            kernel,
            reconsideration_worker,
            fixture_worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery()
        *_, expected = await critical_qualifications(
            fixture_worker,
            inquiry_id=inquiries[0].inquiry_id,
            information_id=information_refs[0].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
        )
        crashed = CrashBeforeHandoff(
            kernel,
            reconsideration_worker=reconsideration_worker,
            authority=fixture_worker.authority,
            derived_information_id_deriver=ID_DERIVER,
            policy=fixture_worker.policy,
            clock=clock,
        )
        with self.assertRaisesRegex(RuntimeError, "after opportunity"):
            await crashed.run_trigger(
                trigger_event_id=f"reconsideration-evidence-qualified:{expected[1].qualification_id}",
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
        later_no_op = await kernel.emit(
            Event(
                "user.reconsideration_requested",
                "fixture:user",
                subject="inquiry:unrelated",
                timestamp=clock(),
            )
        )
        no_op = await fixture_worker.run_trigger(
            trigger_event_id=later_no_op.id,
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(no_op.opportunities, ())
        checkpoint_before_recovery = ConsumerCheckpoint.from_event(
            (await kernel.history())[-1]
        )
        assert later_no_op.sequence is not None
        self.assertEqual(
            checkpoint_before_recovery.last_completed_sequence,
            later_no_op.sequence,
        )
        recovered = await fixture_worker.recover(
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(len(recovered), 1)
        projection = await fixture_worker.current_projection()
        self.assertEqual(len(projection.opportunities), 1)
        self.assertEqual(len(projection.reconsideration.candidates), 1)
        self.assertEqual(len(projection.reconsideration.allocations), 1)
        checkpoints = [
            ConsumerCheckpoint.from_event(value)
            for value in await kernel.history()
            if value.type == "runtime.consumer_checkpoint_advanced"
            and value.subject == fixture_worker.consumer_id
        ]
        self.assertTrue(checkpoints)
        await kernel.stop()

    async def test_recovery_repairs_allocation_trace_and_proposal_handoff_gaps(self) -> None:
        async def attempt(crash_event_type: str) -> None:
            class CrashAtOutput(ReconsiderationShadowWorker):
                crashed = False

                async def _append_exact(self, event, **kwargs):  # type: ignore[no-untyped-def]
                    if event.type == crash_event_type and not self.crashed:
                        self.crashed = True
                        raise RuntimeError(f"simulated crash before {crash_event_type}")
                    return await super()._append_exact(event, **kwargs)

            (
                kernel,
                reconsideration_worker,
                fixture_worker,
                mandate,
                principal,
                _g1,
                _current,
                inquiries,
                information_refs,
                clock,
                authorization,
            ) = await prepare_discovery()
            *_, expected = await critical_qualifications(
                fixture_worker,
                inquiry_id=inquiries[0].inquiry_id,
                information_id=information_refs[0].information_id,
                mandate=mandate,
                principal=principal,
                clock=clock,
                authorization=authorization,
            )
            crashing_reconsideration = CrashAtOutput(
                kernel,
                authority=reconsideration_worker.authority,
                policy=reconsideration_worker.policy,
                clock=clock,
                derived_information_id_deriver=ID_DERIVER,
            )
            crashing_discovery = ReconsiderationDiscoveryWorker(
                kernel,
                reconsideration_worker=crashing_reconsideration,
                authority=fixture_worker.authority,
                derived_information_id_deriver=ID_DERIVER,
                policy=fixture_worker.policy,
                clock=clock,
            )
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                await crashing_discovery.run_trigger(
                    trigger_event_id=(
                        f"reconsideration-evidence-qualified:{expected[1].qualification_id}"
                    ),
                    basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                    principal=principal,
                    actor_id="user:carlos",
                    source_trust_domain="local",
                    locality="local",
                )
            partial = await fixture_worker.current_projection()
            self.assertEqual(len(partial.reconsideration.allocations), 1)
            if crash_event_type == ALLOCATION_TRACE_RECORDED_EVENT:
                self.assertEqual(partial.reconsideration.traces, ())
            else:
                self.assertEqual(len(partial.reconsideration.traces), 1)
                self.assertEqual(partial.reconsideration.proposals, ())

            later_no_op = await kernel.emit(
                Event(
                    "user.reconsideration_requested",
                    "fixture:user",
                    subject="inquiry:unrelated",
                    timestamp=clock(),
                )
            )
            await fixture_worker.run_trigger(
                trigger_event_id=later_no_op.id,
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
            await fixture_worker.recover(
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
            repaired = await fixture_worker.current_projection()
            self.assertEqual(len(repaired.reconsideration.traces), 1)
            self.assertEqual(len(repaired.reconsideration.proposals), 1)
            before_retry = tuple(
                value.type
                for value in await kernel.history()
                if value.type in {ALLOCATION_TRACE_RECORDED_EVENT, SHADOW_PROPOSAL_RECORDED_EVENT}
            )
            await fixture_worker.recover(
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
            after_retry = tuple(
                value.type
                for value in await kernel.history()
                if value.type in {ALLOCATION_TRACE_RECORDED_EVENT, SHADOW_PROPOSAL_RECORDED_EVENT}
            )
            self.assertEqual(after_retry, before_retry)
            self.assertEqual(before_retry.count(ALLOCATION_TRACE_RECORDED_EVENT), 1)
            self.assertEqual(before_retry.count(SHADOW_PROPOSAL_RECORDED_EVENT), 1)
            await kernel.stop()

        for crash_event_type in (
            ALLOCATION_TRACE_RECORDED_EVENT,
            SHADOW_PROPOSAL_RECORDED_EVENT,
        ):
            with self.subTest(crash_event_type=crash_event_type):
                await attempt(crash_event_type)

    async def test_expired_unallocated_opportunity_is_terminal_for_recovery(self) -> None:
        class CrashBeforeHandoff(ReconsiderationDiscoveryWorker):
            async def _handoff(self, **_kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("simulated crash after opportunity")

        class CountingWorker(ReconsiderationDiscoveryWorker):
            trigger_calls = 0

            async def run_trigger(self, **kwargs):  # type: ignore[no-untyped-def]
                self.trigger_calls += 1
                return await super().run_trigger(**kwargs)

        (
            kernel,
            reconsideration_worker,
            fixture_worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery()
        *_, expected = await critical_qualifications(
            fixture_worker,
            inquiry_id=inquiries[0].inquiry_id,
            information_id=information_refs[0].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
        )
        crashed = CrashBeforeHandoff(
            kernel,
            reconsideration_worker=reconsideration_worker,
            authority=fixture_worker.authority,
            derived_information_id_deriver=ID_DERIVER,
            policy=fixture_worker.policy,
            clock=clock,
        )
        with self.assertRaisesRegex(RuntimeError, "after opportunity"):
            await crashed.run_trigger(
                trigger_event_id=f"reconsideration-evidence-qualified:{expected[1].qualification_id}",
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
        later_no_op = await kernel.emit(
            Event(
                "user.reconsideration_requested",
                "fixture:user",
                subject="inquiry:unrelated",
                timestamp=clock(),
            )
        )
        await fixture_worker.run_trigger(
            trigger_event_id=later_no_op.id,
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        clock.advance(timedelta(days=2))
        recovered_worker = CountingWorker(
            kernel,
            reconsideration_worker=reconsideration_worker,
            authority=fixture_worker.authority,
            derived_information_id_deriver=ID_DERIVER,
            policy=fixture_worker.policy,
            clock=clock,
        )
        for _attempt in range(2):
            recovered = await recovered_worker.recover(
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
            self.assertEqual(recovered, ())
        self.assertEqual(recovered_worker.trigger_calls, 0)
        projection = await recovered_worker.current_projection()
        self.assertEqual(projection.reconsideration.allocations, ())
        self.assertEqual(projection.reconsideration.proposals, ())
        await kernel.stop()

    async def test_foreground_arrival_between_evaluation_and_admission_fails_closed(
        self,
    ) -> None:
        class ForegroundRace(ReconsiderationDiscoveryWorker):
            injected = False

            async def _admit_opportunity(self, *args, **kwargs):
                if not self.injected:
                    self.injected = True
                    await self.kernel.emit(
                        Event(
                            "decision.proposed",
                            "fixture:foreground",
                            timestamp=self.clock(),
                        )
                    )
                return await super()._admit_opportunity(*args, **kwargs)

        (
            kernel,
            _rw,
            worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery()
        *_, expected = await critical_qualifications(
            worker,
            inquiry_id=inquiries[0].inquiry_id,
            information_id=information_refs[0].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
        )
        raced = ForegroundRace(
            kernel,
            reconsideration_worker=worker.reconsideration_worker,
            authority=worker.authority,
            derived_information_id_deriver=ID_DERIVER,
            policy=worker.policy,
            clock=clock,
        )
        with self.assertRaisesRegex(ValueError, "foreground demand blocks"):
            await raced.run_trigger(
                trigger_event_id=(
                    f"reconsideration-evidence-qualified:{expected[1].qualification_id}"
                ),
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
        projection = await worker.current_projection()
        self.assertEqual(projection.opportunities, ())
        await kernel.stop()

    async def test_post_trigger_foreground_does_not_rewrite_evaluation_cut(self) -> None:
        class RecordingDetector(DeterministicDormantInquiryDetector):
            nominations = ()

            def discover(self, **kwargs):  # type: ignore[no-untyped-def]
                self.nominations = super().discover(**kwargs)
                return self.nominations

        (
            kernel,
            reconsideration_worker,
            fixture_worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery()
        *_, expected = await critical_qualifications(
            fixture_worker,
            inquiry_id=inquiries[0].inquiry_id,
            information_id=information_refs[0].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
        )
        trigger_id = f"reconsideration-evidence-qualified:{expected[1].qualification_id}"
        await kernel.emit(
            Event(
                "decision.proposed",
                "fixture:foreground",
                timestamp=clock(),
            )
        )
        detector = RecordingDetector()
        worker = ReconsiderationDiscoveryWorker(
            kernel,
            reconsideration_worker=reconsideration_worker,
            authority=fixture_worker.authority,
            derived_information_id_deriver=ID_DERIVER,
            policy=fixture_worker.policy,
            clock=clock,
            detector=detector,
        )
        with self.assertRaisesRegex(ValueError, "foreground demand blocks"):
            await worker.run_trigger(
                trigger_event_id=trigger_id,
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
        self.assertEqual(len(detector.nominations), 1)
        self.assertEqual((await worker.current_projection()).opportunities, ())
        await kernel.stop()

    async def test_concurrent_discovery_admits_one_semantic_opportunity(self) -> None:
        (
            kernel,
            _rw,
            first,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery()
        *_, expected = await critical_qualifications(
            first,
            inquiry_id=inquiries[0].inquiry_id,
            information_id=information_refs[0].information_id,
            mandate=mandate,
            principal=principal,
            clock=clock,
            authorization=authorization,
        )
        second = ReconsiderationDiscoveryWorker(
            kernel,
            reconsideration_worker=first.reconsideration_worker,
            authority=first.authority,
            derived_information_id_deriver=ID_DERIVER,
            policy=first.policy,
            clock=clock,
        )
        trigger = f"reconsideration-evidence-qualified:{expected[1].qualification_id}"
        results = await asyncio.gather(
            *(
                worker.run_trigger(
                    trigger_event_id=trigger,
                    basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                    principal=principal,
                    actor_id="user:carlos",
                    source_trust_domain="local",
                    locality="local",
                )
                for worker in (first, second)
            )
        )
        self.assertTrue(all(value.opportunities for value in results))
        projection = await first.current_projection()
        self.assertEqual(len(projection.opportunities), 1)
        self.assertEqual(len(projection.reconsideration.proposals), 1)
        await kernel.stop()

    async def test_recovery_uses_checkpoint_as_normal_lower_bound(self) -> None:
        class CountingWorker(ReconsiderationDiscoveryWorker):
            trigger_calls = 0

            async def run_trigger(self, **kwargs):  # type: ignore[no-untyped-def]
                self.trigger_calls += 1
                return await super().run_trigger(**kwargs)

        (
            kernel,
            reconsideration_worker,
            fixture_worker,
            _mandate,
            principal,
            _g1,
            _current,
            _inquiries,
            _information_refs,
            clock,
            _authorization,
        ) = await prepare_discovery()
        last = None
        for index in range(1_200):
            last = await kernel.emit(
                Event(
                    "rule.evaluation_traced",
                    "fixture:noop-history",
                    {"candidate": False, "ordinal": index},
                    subject=f"rule:noop:{index}@1",
                    timestamp=clock(),
                )
            )
        assert last is not None and last.sequence is not None
        await kernel.emit(
            ConsumerCheckpoint(
                consumer_id=fixture_worker.consumer_id,
                last_completed_sequence=last.sequence,
                observed_head_sequence=last.sequence,
                epoch_id=f"trigger:{last.id}",
            ).to_event(
                source=fixture_worker.source,
                timestamp=clock(),
                causation_id=last.id,
            )
        )
        worker = CountingWorker(
            kernel,
            reconsideration_worker=reconsideration_worker,
            authority=fixture_worker.authority,
            derived_information_id_deriver=ID_DERIVER,
            policy=fixture_worker.policy,
            clock=clock,
        )
        recovered = await worker.recover(
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(recovered, ())
        self.assertEqual(worker.trigger_calls, 0)
        await kernel.stop()

    async def test_deferred_candidate_reuses_identity_after_context_change(self) -> None:
        (
            kernel,
            _rw,
            worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            clock,
            authorization,
        ) = await prepare_discovery(count=2, max_candidates=2)
        for inquiry, information in zip(inquiries, information_refs, strict=True):
            await critical_qualifications(
                worker,
                inquiry_id=inquiry.inquiry_id,
                information_id=information.information_id,
                mandate=mandate,
                principal=principal,
                clock=clock,
                authorization=authorization,
            )
        multi_target = await kernel.emit(
            Event(
                "reconsideration.relevance_asserted",
                "fixture:user",
                {"target_refs": [value.inquiry_id for value in inquiries]},
                timestamp=clock(),
            )
        )
        first = await worker.run_trigger(
            trigger_event_id=multi_target.id,
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
            budget=scarce_budget(max_candidates=1),
        )
        assert first.allocation is not None
        deferred_id = next(
            value.candidate_id
            for value in first.allocation.decisions
            if value.label is AllocationLabel.DEFERRED_BY_CONSTRAINT
        )
        clock.advance(timedelta(minutes=1))
        retry = await kernel.emit(
            Event(
                "user.reconsideration_requested",
                "fixture:user",
                subject=next(
                    value.historical.inquiry_id
                    for value in (await worker.current_projection()).reconsideration.candidates
                    if value.candidate_id == deferred_id
                ),
                timestamp=clock(),
            )
        )
        second = await worker.run_trigger(
            trigger_event_id=retry.id,
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
            budget=scarce_budget(max_candidates=2),
        )
        self.assertEqual(
            second.opportunities[0].kind,
            ReconsiderationOpportunityKind.REALLOCATE_EXISTING,
        )
        self.assertEqual(second.opportunities[0].existing_candidate_id, deferred_id)
        assert second.allocation is not None
        self.assertIn(deferred_id, second.allocation.selected_candidate_ids)
        projection = await worker.current_projection()
        self.assertEqual(
            sum(
                value.candidate_id == deferred_id for value in projection.reconsideration.candidates
            ),
            1,
        )
        await kernel.stop()


class ReconsiderationPolicyOrderingTests(unittest.TestCase):
    def test_latest_policy_follows_canonical_sequence_not_lexical_id(self) -> None:
        first = ReconsiderationPolicySnapshot.create(version="policy-order-a")
        second = ReconsiderationPolicySnapshot.create(version="policy-order-b")
        lexical_first, lexical_last = sorted((first, second), key=lambda value: value.policy_id)
        projection = ReconsiderationProjection()
        projection.rebuild(
            (
                lexical_last.to_event(source="fixture", recorded_at=NOW).with_sequence(1),
                lexical_first.to_event(source="fixture", recorded_at=NOW).with_sequence(2),
            )
        )
        self.assertEqual(projection.policies[-1], lexical_last)
        self.assertEqual(projection.latest_policy, lexical_first)


class ReconsiderationOutcomeOrderingTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_event_cannot_be_linked_as_a_subsequent_outcome(self) -> None:
        (
            kernel,
            worker,
            mandate,
            principal,
            _g1,
            _current,
            inquiries,
            information_refs,
            _clock,
        ) = await prepare_mandate_fixture(count=1)
        old_outcome = await kernel.emit(
            Event(
                "user.reconsideration_response",
                "fixture:user",
                timestamp=NOW + timedelta(hours=2, minutes=30),
            )
        )
        evidence = await current_evidence(kernel, suffix="outcome-order")
        allocation = await worker.run_scan(
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            seeds=(seed(inquiries[0], information_refs[0], evidence, strength=0.9),),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        assert allocation is not None
        trace = (await worker.current_projection()).traces[0]
        invalid = CognitiveAllocationOutcomeLink.create(
            trace_id=trace.trace_id,
            outcome_ref=f"event:{old_outcome.id}",
            outcome_kind="user_response",
            linked_at=NOW + timedelta(hours=4),
        )
        with self.assertRaisesRegex(ValueError, "causally follow"):
            await worker.link_outcome(
                trace_id=invalid.trace_id,
                outcome_ref=invalid.outcome_ref,
                outcome_kind=invalid.outcome_kind,
                linked_at=invalid.linked_at,
            )
        await kernel.stop()
