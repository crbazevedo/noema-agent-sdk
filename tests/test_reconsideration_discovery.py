from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import replace
from datetime import timedelta

from noema import (
    EVIDENCE_QUALIFICATION_BOUND_EVENT,
    OPPORTUNITY_RECORDED_EVENT,
    AllocationLabel,
    CognitiveAllocationOutcomeLink,
    ConsumerCheckpoint,
    CurrentCognitiveBasis,
    DiscoveryReason,
    DormancyReason,
    DormantInquiryIndex,
    EpistemicType,
    Event,
    EvidenceQualificationRole,
    ReconsiderationDiscoveryPolicySnapshot,
    ReconsiderationDiscoveryProjection,
    ReconsiderationDiscoveryWorker,
    ReconsiderationOpportunityKind,
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


def discovery_policy(*, max_opportunities: int = 8) -> ReconsiderationDiscoveryPolicySnapshot:
    return ReconsiderationDiscoveryPolicySnapshot.create(
        version="discovery-fixture-v1",
        max_opportunities_emitted=max_opportunities,
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


async def prepare_discovery(*, count: int = 1, max_candidates: int = 1):
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
):
    clock.advance(timedelta(seconds=1))
    assertion = SemanticAssertion.create(
        subject=inquiry_id,
        predicate=f"reconsideration.{role.value.lower()}",
        value=value,
        epistemic_type=(EpistemicType.INFERRED if derivation_refs else EpistemicType.REPORTED),
        confidence=0.95,
        valid_from=clock(),
        recorded_at=clock(),
        fresh_until=clock() + timedelta(days=1),
        source_refs=(f"event:{authorization.id}",),
        derivation_refs=derivation_refs,
        mutable_world=True,
    )
    await worker.kernel.emit(assertion.to_event(source="fixture:memory"))
    clock.advance(timedelta(seconds=1))
    binding = await worker.bind_evidence_qualification(
        assertion_ref=assertion.assertion_id,
        role=role,
        target_refs=(inquiry_id,),
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
    return old_value, value_assertion, value_binding, motivation, expected


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

    async def test_unrelated_events_and_generic_values_create_no_durable_churn(self) -> None:
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
        self.assertEqual(await kernel.store.latest_sequence(), before)

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
        _old, _qv, _bv, _qm, expected = await critical_qualifications(
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
        _old, _qv, _bv, _qm, expected = await critical_qualifications(
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
        _old, _qv, _bv, _qm, expected = await critical_qualifications(
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
