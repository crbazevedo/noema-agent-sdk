from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from noema import (
    ALLOCATION_TRACE_RECORDED_EVENT,
    INQUIRY_RECORDED_EVENT,
    LINEAGE_RECORDED_EVENT,
    POLICY_BOUND_EVENT,
    RECONSIDERATION_ALLOCATION_RECORDED_EVENT,
    RECONSIDERATION_CANDIDATE_RECORDED_EVENT,
    RECONSIDERATION_EVENT_TYPES,
    SHADOW_PROPOSAL_RECORDED_EVENT,
    AllocationLabel,
    BackgroundCognitiveBudget,
    Classification,
    CognitionScanRequest,
    CognitiveResourceVector,
    ConsumerCheckpoint,
    CurrentCognitiveBasis,
    DisclosureForm,
    DreamEpoch,
    EndogenousDrive,
    EndogenousPolicySnapshot,
    EstimateEvidenceKind,
    Event,
    EvidenceBackedEstimate,
    GoalKind,
    GoalStatus,
    GovernedInformationRef,
    GoverningIntentRef,
    HmacOpaqueInformationIdDeriver,
    InformationGovernanceEngine,
    InformationLineage,
    InformationPolicy,
    Inquiry,
    IntentAuthority,
    IntentAuthorityScope,
    IntentStewardCoordinator,
    LineageTransformation,
    MandateIssuerKind,
    NoemaKernel,
    OriginKind,
    OriginProvenance,
    PolicyBinding,
    PrincipalSnapshot,
    ReconsiderationAllocation,
    ReconsiderationFeatureSnapshot,
    ReconsiderationMandate,
    ReconsiderationMandateRevocation,
    ReconsiderationPolicySnapshot,
    ReconsiderationProjection,
    ReconsiderationSeed,
    ReconsiderationShadowWorker,
    RetentionPolicy,
    ScarceCognitionBudget,
    ScarceCognitionCostSnapshot,
    StaleGovernanceDecisionError,
    StaticReconsiderationAuthority,
    StaticStrategicTrust,
    StrategicValidator,
    SurfacingPolicy,
)
from noema.store import InMemoryEventStore

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
ID_DERIVER = HmacOpaqueInformationIdDeriver(b"reconsideration-fixture-key-32b!")


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta = timedelta(minutes=1)) -> None:
        self.value += delta


def user_security() -> tuple[OriginProvenance, IntentAuthority, StaticStrategicTrust]:
    origin = OriginProvenance(
        provenance_id="origin:user:carlos",
        kind=OriginKind.USER,
        principal_id="user:carlos",
        authentication_ref="authn:fixture-session",
    )
    authority = IntentAuthority(
        authority_id="intent-authority:user:carlos",
        principal_id="user:carlos",
        scope=IntentAuthorityScope.USER,
        allowed_goal_kinds=(GoalKind.USER_AUTHORED,),
        goal_refs=(),
        provenance_ref=origin.provenance_id,
    )
    return origin, authority, StaticStrategicTrust((origin,), (authority,))


def scarce_budget(*, max_candidates: int = 1) -> ScarceCognitionBudget:
    return ScarceCognitionBudget.create(
        max_candidates=max_candidates,
        ceiling=ScarceCognitionCostSnapshot(
            compute_units=4.0,
            wall_time_seconds=120.0,
            monetary_cost=1.0,
            attention_units=1.0,
            interruption_units=0.5,
            privacy_exposure_units=0.5,
            opportunity_cost_units=1.0,
            revalidation_units=1.0,
        ),
    )


async def record_goal(
    steward: IntentStewardCoordinator,
    *,
    goal_id: str,
    status: GoalStatus,
    origin: OriginProvenance,
    authority: IntentAuthority,
    reason: str,
):
    return await steward.record_goal_revision(
        goal_id=goal_id,
        description=f"Synthetic outcome for {goal_id}",
        priority=0.9,
        utility=1.0,
        success_criteria=(f"{goal_id} outcome is resolved",),
        owner="user:carlos",
        status=status,
        deadline=NOW + timedelta(days=30),
        kind=GoalKind.USER_AUTHORED,
        governing_goal_refs=(),
        origin=origin,
        intent_authority=authority,
        author="user:carlos",
        revision_reason=reason,
    )


async def append_exact(kernel: NoemaKernel, event: Event) -> Event:
    head = await kernel.store.latest_sequence()
    return await kernel.emit_if_head(
        replace(event, metadata={"validated_at_event_cursor": head}),
        expected_head_sequence=head,
    )


async def seed_historical_inquiries(
    kernel: NoemaKernel,
    clock: MutableClock,
    *,
    count: int = 2,
    terminal: bool = True,
    inquiry_lifetime: timedelta = timedelta(minutes=15),
    revise_goal: bool = True,
):
    origin, authority, trust = user_security()
    steward = IntentStewardCoordinator(
        kernel,
        validator=StrategicValidator(trust),
        clock=clock,
    )
    g1 = await record_goal(
        steward,
        goal_id="goal:historical",
        status=GoalStatus.ACTIVE,
        origin=origin,
        authority=authority,
        reason="seed historical intent",
    )
    evidence: list[Event] = []
    for index in range(count):
        clock.advance()
        evidence.append(
            await kernel.emit(
                Event(
                    "external.historical_evidence",
                    "fixture",
                    {"candidate": index},
                    subject="goal:historical",
                    timestamp=clock(),
                )
            )
        )
    policy = EndogenousPolicySnapshot.create(version="historical-fixture")
    clock.advance()
    await kernel.emit(policy.to_event(source="fixture", recorded_at=clock()))
    request = CognitionScanRequest.create(
        policy_id=policy.policy_id,
        budget=BackgroundCognitiveBudget.create(
            ceiling=CognitiveResourceVector(
                activities=count,
                compute_units=float(count),
                wall_time_seconds=60.0,
                attention_units=1.0,
                privacy_risk_units=0.2,
            )
        ),
        requested_at=clock(),
        expires_at=clock() + inquiry_lifetime,
    )
    request_event = await kernel.emit(request.to_event(source="fixture"))
    assert request_event.sequence is not None
    epoch = DreamEpoch.start(
        consumer_id="historical-fixture",
        trigger_event_id=request_event.id,
        event_log_cursor=request_event.sequence,
        policy=policy,
        budget=request.budget,
        started_at=request.requested_at,
        expires_at=request.expires_at,
    )
    await append_exact(kernel, epoch.to_event(source="fixture"))
    inquiries: list[Inquiry] = []
    for index, evidence_event in enumerate(evidence):
        inquiry = Inquiry.create(
            question=f"Could historical possibility {index + 1} still matter?",
            origin=EndogenousDrive.CURIOSITY,
            governing_intent_refs=(GoverningIntentRef("goal:historical", g1.revision_id),),
            evidence_refs=(f"event:{evidence_event.id}",),
            target_refs=(f"possibility:{index + 1}",),
            decision_relevance=0.8,
            expected_information_value=0.8,
            uncertainty=0.6,
            possible_methods=("review current evidence",),
            estimated_cognitive_cost=0.2,
            privacy_risk_cost=0.1,
            expires_at=request.expires_at,
            causal_cursor=request_event.sequence,
            created_at=request.requested_at,
            producer_id="historical-fixture",
        )
        await append_exact(
            kernel,
            inquiry.to_event(source="fixture", epoch_id=epoch.epoch_id),
        )
        inquiries.append(inquiry)

    if not revise_goal:
        return steward, g1, g1, tuple(inquiries)

    clock.advance(timedelta(minutes=20))
    next_status = GoalStatus.COMPLETED if terminal else GoalStatus.ACTIVE
    current_g1 = await record_goal(
        steward,
        goal_id="goal:historical",
        status=next_status,
        origin=origin,
        authority=authority,
        reason="close or revise the historical intent",
    )
    if terminal:
        clock.advance()
        await record_goal(
            steward,
            goal_id="goal:urgent",
            status=GoalStatus.ACTIVE,
            origin=origin,
            authority=authority,
            reason="urgent foreground intent",
        )
        clock.advance()
        await record_goal(
            steward,
            goal_id="goal:urgent",
            status=GoalStatus.COMPLETED,
            origin=origin,
            authority=authority,
            reason="urgent intent fulfilled",
        )
    return steward, g1, current_g1, tuple(inquiries)


async def record_information(
    kernel: NoemaKernel,
    *,
    count: int,
    purpose: str = "historical-reconsideration",
    classification: Classification = Classification.INTERNAL,
) -> tuple[InformationPolicy, tuple[GovernedInformationRef, ...]]:
    policy = InformationPolicy.create(
        version=1,
        origin_domains=("synthetic",),
        classification=classification,
        allowed_purposes=(purpose,),
        allowed_recipients=("user:carlos",),
        allowed_trust_domains=("local",),
        allowed_localities=("local",),
        allowed_providers=(),
        cross_agent_sharing=False,
        retention=RetentionPolicy(),
        disclosure_forms=(DisclosureForm.FULL,),
        declassification_authorities=("user:carlos",),
        recorded_at=NOW + timedelta(hours=1),
    )
    await kernel.emit(policy.to_event(source="fixture"))
    refs: list[GovernedInformationRef] = []
    for index in range(count):
        ref = GovernedInformationRef.create(
            namespace="reconsideration-fixture",
            stable_key=f"historical-inquiry-{index}",
            deriver=ID_DERIVER,
        )
        lineage = InformationLineage.create(
            information_id=ref.information_id,
            source_information_ids=(),
            transformation=LineageTransformation.SOURCE,
            recorded_at=NOW + timedelta(hours=1, minutes=index + 1),
        )
        await kernel.emit(lineage.to_event(source="fixture"))
        await kernel.emit(
            PolicyBinding.create(
                information_id=ref.information_id,
                lineage_id=lineage.lineage_id,
                policy_ids=(policy.policy_id,),
                bound_at=NOW + timedelta(hours=1, minutes=index + 1),
            ).to_event(source="fixture")
        )
        refs.append(ref)
    return policy, tuple(refs)


async def prepare_mandate_fixture(
    *,
    count: int = 2,
    policy_purpose: str = "historical-reconsideration",
    mandate_purpose: str = "historical-reconsideration",
    domains: tuple[str, ...] = ("personal-research",),
    trigger_event_types: tuple[str, ...] = (),
    minimum_interval_seconds: float = 60.0,
    expires_in: timedelta = timedelta(days=1),
    max_candidates: int = 1,
    maximum_interruption_units: float = 0.25,
    classification: Classification = Classification.INTERNAL,
    historical_terminal: bool = True,
    inquiry_lifetime: timedelta = timedelta(minutes=15),
    revise_historical_goal: bool = True,
):
    kernel = NoemaKernel()
    clock = MutableClock(NOW)
    _steward, g1, current_g1, inquiries = await seed_historical_inquiries(
        kernel,
        clock,
        count=count,
        terminal=historical_terminal,
        inquiry_lifetime=inquiry_lifetime,
        revise_goal=revise_historical_goal,
    )
    information_policy, information_refs = await record_information(
        kernel,
        count=count,
        purpose=policy_purpose,
        classification=classification,
    )
    authorization = await kernel.emit(
        Event(
            "user.reconsideration_authorized",
            "fixture:user",
            {"scope": "historical inquiry only"},
            subject="user:carlos",
            timestamp=NOW + timedelta(hours=2),
        )
    )
    authority = StaticReconsiderationAuthority(
        authority_id="reconsideration-authority:fixture",
        authorized_issuers=(("user:carlos", MandateIssuerKind.USER),),
    )
    scan_clock = MutableClock(NOW + timedelta(hours=3, minutes=1))
    worker = ReconsiderationShadowWorker(
        kernel,
        authority=authority,
        clock=scan_clock,
        derived_information_id_deriver=ID_DERIVER,
    )
    if trigger_event_types:
        await kernel.emit(
            Event(
                trigger_event_types[0],
                "fixture:pre-activation-trigger",
                timestamp=NOW + timedelta(hours=1, minutes=59),
            )
        )
    mandate = ReconsiderationMandate.create(
        mandate_id="mandate:historical-review",
        revision=1,
        issuer_id="user:carlos",
        issuer_kind=MandateIssuerKind.USER,
        authority_id=authority.authority_id,
        authorization_ref=f"event:{authorization.id}",
        scope="review unresolved historical inquiries without reviving intent",
        candidate_classes=("inquiry",),
        candidate_domains=domains,
        budget=scarce_budget(max_candidates=max_candidates),
        minimum_interval_seconds=minimum_interval_seconds,
        trigger_event_types=trigger_event_types,
        issued_at=NOW + timedelta(hours=2),
        expires_at=NOW + timedelta(hours=2) + expires_in,
        maximum_interruption_units=maximum_interruption_units,
        surfacing_policy=SurfacingPolicy.SHADOW_QUESTION_ONLY,
        information_use_purpose=mandate_purpose,
        information_policy_ids=(information_policy.policy_id,),
    )
    await worker.record_mandate(mandate)
    principal = PrincipalSnapshot.create(
        principal_id="user:carlos",
        roles=(),
        groups=(),
        trust_domains=("local",),
        captured_at=NOW + timedelta(hours=2),
    )
    return (
        kernel,
        worker,
        mandate,
        principal,
        g1,
        current_g1,
        inquiries,
        information_refs,
        scan_clock,
    )


async def current_evidence(kernel: NoemaKernel, *, suffix: str = "base") -> Event:
    return await kernel.emit(
        Event(
            "external.current_revalidation",
            "fixture",
            {"still_relevant": True, "suffix": suffix},
            subject="historical-possibility",
            timestamp=NOW + timedelta(hours=3),
        )
    )


def feature_snapshot(
    evidence: Event,
    *,
    strength: float = 0.9,
    unknown: bool = False,
) -> ReconsiderationFeatureSnapshot:
    ref = f"event:{evidence.id}"
    estimate = EvidenceBackedEstimate(
        value=strength,
        kind=EstimateEvidenceKind.EXPLICIT,
        confidence=0.95,
        evidence_refs=(ref,),
        observed_at=evidence.timestamp,
        valid_until=evidence.timestamp + timedelta(days=1),
    )
    return ReconsiderationFeatureSnapshot(
        unresolvedness=strength,
        evidence_freshness=strength,
        meaningful_new_evidence=strength,
        opportunity_window=strength,
        current_basis_validity=1.0,
        value_alignment_estimate=None if unknown else estimate,
        expected_outcome_value=None if unknown else estimate,
        motivation_estimate=None if unknown else estimate,
        provenance_refs=(ref,),
    )


def seed(
    inquiry: Inquiry,
    information_ref: GovernedInformationRef,
    evidence: Event,
    *,
    strength: float,
    unknown: bool = False,
    domain: str = "personal-research",
    costs: ScarceCognitionCostSnapshot | None = None,
) -> ReconsiderationSeed:
    return ReconsiderationSeed(
        inquiry_id=inquiry.inquiry_id,
        domain=domain,
        current_evidence_refs=(f"event:{evidence.id}",),
        governed_information_ids=(information_ref.information_id,),
        features=feature_snapshot(evidence, strength=strength, unknown=unknown),
        costs=costs
        or ScarceCognitionCostSnapshot(
            compute_units=0.5,
            wall_time_seconds=10.0,
            monetary_cost=0.05,
            attention_units=0.1,
            interruption_units=0.1,
            privacy_exposure_units=0.05,
            opportunity_cost_units=0.1,
            revalidation_units=0.1,
        ),
    )


class CognitiveReconsiderationAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_flagship_reconsiders_history_without_resuming_or_acting(self) -> None:
        (
            kernel,
            worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            scan_clock,
        ) = await prepare_mandate_fixture()
        evidence = await current_evidence(kernel)
        before = await kernel.store.latest_sequence()
        basis = CurrentCognitiveBasis.from_mandate(mandate.revision_id)
        seeds = (
            seed(inquiries[0], information_refs[0], evidence, strength=0.95),
            seed(inquiries[1], information_refs[1], evidence, strength=0.75),
        )
        allocation = await worker.run_scan(
            basis=basis,
            seeds=seeds,
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertIsNotNone(allocation)
        assert allocation is not None
        labels = {value.candidate_id: value.label for value in allocation.decisions}
        self.assertEqual(tuple(labels.values()).count(AllocationLabel.SELECTED), 1)
        self.assertEqual(
            tuple(labels.values()).count(AllocationLabel.DEFERRED_BY_CONSTRAINT),
            1,
        )

        projection = await worker.current_projection()
        self.assertEqual(len(projection.candidates), 2)
        self.assertEqual(len(projection.traces), 2)
        self.assertEqual(len(projection.proposals), 1)
        selected = next(
            value
            for value in projection.candidates
            if value.candidate_id in allocation.selected_candidate_ids
        )
        self.assertEqual(selected.historical.inquiry_id, inquiries[0].inquiry_id)
        self.assertEqual(selected.current_basis, basis)
        self.assertGreater(
            selected.current_causal_cursor,
            selected.historical.historical_causal_cursor,
        )
        self.assertEqual(
            projection.endogenous.inquiry(inquiries[0].inquiry_id),
            inquiries[0],
        )
        history = await kernel.history()
        self.assertEqual(
            sum(event.type == INQUIRY_RECORDED_EVENT for event in history),
            2,
        )
        later = tuple(event for event in history if (event.sequence or 0) > before)
        self.assertFalse(
            any(event.type.startswith(("intent.goal", "work.", "action.")) for event in later)
        )
        self.assertEqual(
            sum(event.type == ALLOCATION_TRACE_RECORDED_EVENT for event in later),
            2,
        )

        original_trace = projection.traces[0]
        response = await kernel.emit(
            Event(
                "user.reconsideration_response",
                "fixture:user",
                {"response": "still matters"},
                timestamp=NOW + timedelta(hours=3, minutes=2),
            )
        )
        linked = await worker.link_outcome(
            trace_id=original_trace.trace_id,
            outcome_ref=f"event:{response.id}",
            outcome_kind="user_response",
            linked_at=response.timestamp,
        )
        projection = await worker.current_projection()
        self.assertEqual(projection.traces[0], original_trace)
        self.assertEqual(projection.outcome_links, (linked,))

        replay = ReconsiderationProjection()
        history = await kernel.history()
        replay.rebuild(kernel.schemas.normalize(event) for event in history)
        self.assertEqual(replay.semantic_snapshot(), projection.semantic_snapshot())

        scan_clock.advance(timedelta(hours=1))
        second = await worker.run_scan(
            basis=basis,
            seeds=seeds,
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        assert second is not None
        self.assertNotEqual(second.allocation_id, allocation.allocation_id)
        self.assertEqual(
            second.selected_candidate_ids,
            tuple(
                value.candidate_id
                for value in allocation.decisions
                if value.label is AllocationLabel.DEFERRED_BY_CONSTRAINT
            ),
        )
        projection = await worker.current_projection()
        self.assertEqual(len(projection.candidates), 2)
        self.assertEqual(len(projection.allocations), 2)
        self.assertEqual(len(projection.traces), 3)
        self.assertEqual(len(projection.proposals), 2)

        unchanged_count = len(await kernel.history())
        same = await worker.run_scan(
            basis=basis,
            seeds=seeds,
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        self.assertEqual(same, second)
        self.assertEqual(len(await kernel.history()), unchanged_count)
        await kernel.stop()

    async def test_partial_scan_recovers_without_duplicate_outputs(self) -> None:
        class CrashBeforeCheckpointWorker(ReconsiderationShadowWorker):
            def __init__(
                self,
                kernel: NoemaKernel,
                *,
                authority: StaticReconsiderationAuthority,
                policy: ReconsiderationPolicySnapshot,
                clock: MutableClock,
            ) -> None:
                super().__init__(
                    kernel,
                    authority=authority,
                    policy=policy,
                    clock=clock,
                    derived_information_id_deriver=ID_DERIVER,
                )
                self.crash_once = True

            async def _advance_checkpoint(
                self,
                trigger: Event,
                allocation_id: str,
            ) -> ConsumerCheckpoint:
                if self.crash_once:
                    self.crash_once = False
                    raise RuntimeError("simulated crash before reconsideration checkpoint")
                return await super()._advance_checkpoint(trigger, allocation_id)

        (
            kernel,
            fixture_worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            scan_clock,
        ) = await prepare_mandate_fixture(count=1)
        worker = CrashBeforeCheckpointWorker(
            kernel,
            authority=fixture_worker.authority,
            policy=fixture_worker.policy,
            clock=scan_clock,
        )
        evidence = await current_evidence(kernel, suffix="crash")
        scan_seed = seed(inquiries[0], information_refs[0], evidence, strength=0.9)
        with self.assertRaisesRegex(RuntimeError, "simulated crash"):
            await worker.run_scan(
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                seeds=(scan_seed,),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )

        before_recovery = await kernel.history()
        recovered = await ReconsiderationShadowWorker(
            kernel,
            authority=fixture_worker.authority,
            policy=fixture_worker.policy,
            clock=scan_clock,
            derived_information_id_deriver=ID_DERIVER,
        ).recover()
        after_recovery = await kernel.history()
        self.assertEqual(len(recovered), 1)
        self.assertEqual(
            sum(event.type == ALLOCATION_TRACE_RECORDED_EVENT for event in after_recovery),
            1,
        )
        self.assertEqual(
            tuple(event for event in after_recovery if event.type.startswith("reconsideration.")),
            tuple(event for event in before_recovery if event.type.startswith("reconsideration.")),
        )
        checkpoint = ConsumerCheckpoint.from_event(after_recovery[-1])
        self.assertEqual(checkpoint.epoch_id, recovered[0].allocation_id)
        await kernel.stop()

    async def test_recovery_reconciles_every_partial_output_stage(self) -> None:
        class CrashAfterStageWorker(ReconsiderationShadowWorker):
            def __init__(
                self,
                kernel: NoemaKernel,
                *,
                authority: StaticReconsiderationAuthority,
                policy: ReconsiderationPolicySnapshot,
                clock: MutableClock,
                stage: str,
            ) -> None:
                super().__init__(
                    kernel,
                    authority=authority,
                    policy=policy,
                    clock=clock,
                    derived_information_id_deriver=ID_DERIVER,
                )
                self.stage = stage
                self.crashed = False
                self.trace_count = 0

            async def _append_exact(
                self,
                event: Event,
                *,
                authority_id: str | None = None,
            ) -> Event:
                stored = await super()._append_exact(event, authority_id=authority_id)
                should_crash = False
                if (
                    self.stage == "first_candidate"
                    and stored.type == RECONSIDERATION_CANDIDATE_RECORDED_EVENT
                ):
                    should_crash = True
                elif stored.type == ALLOCATION_TRACE_RECORDED_EVENT:
                    self.trace_count += 1
                    if self.stage == "first_trace" and self.trace_count == 1:
                        should_crash = True
                    if (
                        self.stage == "selected_trace"
                        and stored.payload["decision"] == AllocationLabel.SELECTED.value
                    ):
                        should_crash = True
                if should_crash and not self.crashed:
                    self.crashed = True
                    raise RuntimeError(f"simulated crash after {self.stage}")
                return stored

            async def _ensure_allocation(
                self,
                scan_event: Event,
            ) -> ReconsiderationAllocation:
                allocation = await super()._ensure_allocation(scan_event)
                if self.stage == "allocation" and not self.crashed:
                    self.crashed = True
                    raise RuntimeError("simulated crash after allocation")
                return allocation

        for stage in (
            "first_candidate",
            "allocation",
            "first_trace",
            "selected_trace",
        ):
            with self.subTest(stage=stage):
                (
                    kernel,
                    fixture_worker,
                    mandate,
                    principal,
                    _g1,
                    _current_g1,
                    inquiries,
                    information_refs,
                    scan_clock,
                ) = await prepare_mandate_fixture(count=2)
                worker = CrashAfterStageWorker(
                    kernel,
                    authority=fixture_worker.authority,
                    policy=fixture_worker.policy,
                    clock=scan_clock,
                    stage=stage,
                )
                evidence = await current_evidence(kernel, suffix=stage)
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    await worker.run_scan(
                        basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                        seeds=(
                            seed(
                                inquiries[0],
                                information_refs[0],
                                evidence,
                                strength=0.95,
                            ),
                            seed(
                                inquiries[1],
                                information_refs[1],
                                evidence,
                                strength=0.75,
                            ),
                        ),
                        principal=principal,
                        actor_id="user:carlos",
                        source_trust_domain="local",
                        locality="local",
                    )

                recovered = await ReconsiderationShadowWorker(
                    kernel,
                    authority=fixture_worker.authority,
                    policy=fixture_worker.policy,
                    clock=scan_clock,
                    derived_information_id_deriver=ID_DERIVER,
                ).recover()
                self.assertEqual(len(recovered), 1)
                projection = await fixture_worker.current_projection()
                self.assertEqual(len(projection.scans), 1)
                self.assertEqual(len(projection.candidates), 2)
                self.assertEqual(len(projection.allocations), 1)
                self.assertEqual(len(projection.traces), 2)
                self.assertEqual(len(projection.proposals), 1)
                history = await kernel.history()
                self.assertEqual(
                    sum(
                        event.type == RECONSIDERATION_CANDIDATE_RECORDED_EVENT for event in history
                    ),
                    2,
                )
                self.assertEqual(
                    sum(
                        event.type == RECONSIDERATION_ALLOCATION_RECORDED_EVENT for event in history
                    ),
                    1,
                )
                self.assertEqual(
                    sum(event.type == ALLOCATION_TRACE_RECORDED_EVENT for event in history),
                    2,
                )
                self.assertEqual(
                    sum(event.type == SHADOW_PROPOSAL_RECORDED_EVENT for event in history),
                    1,
                )
                await kernel.stop()

    async def test_recovery_does_not_surface_after_basis_expiry(self) -> None:
        class CrashAfterSelectedTraceWorker(ReconsiderationShadowWorker):
            async def _append_exact(
                self,
                event: Event,
                *,
                authority_id: str | None = None,
            ) -> Event:
                stored = await super()._append_exact(event, authority_id=authority_id)
                if (
                    stored.type == ALLOCATION_TRACE_RECORDED_EVENT
                    and stored.payload["decision"] == AllocationLabel.SELECTED.value
                ):
                    raise RuntimeError("simulated crash before proposal")
                return stored

        (
            kernel,
            fixture_worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            scan_clock,
        ) = await prepare_mandate_fixture(count=1, expires_in=timedelta(hours=2))
        worker = CrashAfterSelectedTraceWorker(
            kernel,
            authority=fixture_worker.authority,
            policy=fixture_worker.policy,
            clock=scan_clock,
            derived_information_id_deriver=ID_DERIVER,
        )
        evidence = await current_evidence(kernel, suffix="expiry-before-recovery")
        with self.assertRaisesRegex(RuntimeError, "before proposal"):
            await worker.run_scan(
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                seeds=(seed(inquiries[0], information_refs[0], evidence, strength=0.9),),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )

        scan_clock.advance(timedelta(hours=2))
        recovered = await ReconsiderationShadowWorker(
            kernel,
            authority=fixture_worker.authority,
            policy=fixture_worker.policy,
            clock=scan_clock,
            derived_information_id_deriver=ID_DERIVER,
        ).recover()
        self.assertEqual(len(recovered), 1)
        projection = await fixture_worker.current_projection()
        self.assertEqual(len(projection.traces), 1)
        self.assertEqual(projection.proposals, ())
        checkpoint = ConsumerCheckpoint.from_event((await kernel.history())[-1])
        self.assertEqual(checkpoint.epoch_id, recovered[0].allocation_id)
        await kernel.stop()

    async def test_later_checkpoint_cannot_hide_an_earlier_partial_scan(self) -> None:
        class CrashAfterAllocationWorker(ReconsiderationShadowWorker):
            def __init__(self, *args: object, **kwargs: object) -> None:
                super().__init__(*args, **kwargs)  # type: ignore[arg-type]
                self.crashed = False

            async def _ensure_allocation(
                self,
                scan_event: Event,
            ) -> ReconsiderationAllocation:
                allocation = await super()._ensure_allocation(scan_event)
                if not self.crashed:
                    self.crashed = True
                    raise RuntimeError("simulated earlier partial allocation")
                return allocation

        (
            kernel,
            fixture_worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            scan_clock,
        ) = await prepare_mandate_fixture(count=2)
        evidence = await current_evidence(kernel, suffix="checkpoint-overtake")
        crashed = CrashAfterAllocationWorker(
            kernel,
            authority=fixture_worker.authority,
            policy=fixture_worker.policy,
            clock=scan_clock,
            derived_information_id_deriver=ID_DERIVER,
        )
        with self.assertRaisesRegex(RuntimeError, "earlier partial"):
            await crashed.run_scan(
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                seeds=(seed(inquiries[0], information_refs[0], evidence, strength=0.95),),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )

        scan_clock.advance(timedelta(minutes=2))
        later = await fixture_worker.run_scan(
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            seeds=(seed(inquiries[1], information_refs[1], evidence, strength=0.9),),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        assert later is not None
        checkpoint = ConsumerCheckpoint.from_event((await kernel.history())[-1])
        partial_projection = await fixture_worker.current_projection()
        earlier_allocation = next(
            allocation
            for allocation in partial_projection.allocations
            if all(
                partial_projection.trace_for_decision(
                    decision.candidate_id,
                    allocation.allocation_id,
                )
                is None
                for decision in allocation.decisions
            )
        )
        earlier_scan = partial_projection.scan(earlier_allocation.scan_request_id)
        assert earlier_scan is not None
        earlier_scan_event = next(
            event
            for event in await kernel.history()
            if event.id == f"reconsideration-scan-requested:{earlier_scan.request_id}"
        )
        assert earlier_scan_event.sequence is not None
        self.assertGreater(checkpoint.last_completed_sequence, earlier_scan_event.sequence)

        recovered = await ReconsiderationShadowWorker(
            kernel,
            authority=fixture_worker.authority,
            policy=fixture_worker.policy,
            clock=scan_clock,
            derived_information_id_deriver=ID_DERIVER,
        ).recover()
        self.assertEqual(len(recovered), 1)
        projection = await fixture_worker.current_projection()
        self.assertEqual(len(projection.allocations), 2)
        self.assertEqual(len(projection.traces), 2)
        self.assertEqual(len(projection.proposals), 2)
        await kernel.stop()

    async def test_concurrent_scans_can_select_one_semantic_candidate_only_once(self) -> None:
        release = asyncio.Event()
        arrival_lock = asyncio.Lock()
        arrivals = 0

        class PausedAfterScanWorker(ReconsiderationShadowWorker):
            async def _process_scan(
                self,
                scan_event: Event,
            ) -> ReconsiderationAllocation | None:
                nonlocal arrivals
                async with arrival_lock:
                    arrivals += 1
                    if arrivals == 2:
                        release.set()
                await release.wait()
                return await super()._process_scan(scan_event)

        (
            kernel,
            fixture_worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            scan_clock,
        ) = await prepare_mandate_fixture(count=1, minimum_interval_seconds=0.0)
        evidence = await current_evidence(kernel, suffix="concurrent-selection")
        candidate_seed = seed(inquiries[0], information_refs[0], evidence, strength=0.9)
        second_kernel = NoemaKernel(store=kernel.store)
        await second_kernel.start()
        first = PausedAfterScanWorker(
            kernel,
            authority=fixture_worker.authority,
            policy=fixture_worker.policy,
            clock=scan_clock,
            derived_information_id_deriver=ID_DERIVER,
        )
        second = PausedAfterScanWorker(
            second_kernel,
            authority=fixture_worker.authority,
            policy=fixture_worker.policy,
            clock=MutableClock(scan_clock() + timedelta(seconds=1)),
            derived_information_id_deriver=ID_DERIVER,
        )
        allocations = await asyncio.gather(
            first.run_scan(
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                seeds=(candidate_seed,),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            ),
            second.run_scan(
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                seeds=(candidate_seed,),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            ),
        )
        self.assertTrue(all(value is not None for value in allocations))
        projection = await fixture_worker.current_projection()
        self.assertEqual(len(projection.scans), 2)
        self.assertEqual(len(projection.candidates), 1)
        self.assertEqual(len(projection.allocations), 2)
        self.assertEqual(len(projection.traces), 2)
        self.assertEqual(len(projection.proposals), 1)
        decisions = tuple(
            decision for allocation in projection.allocations for decision in allocation.decisions
        )
        self.assertEqual(
            sum(value.label is AllocationLabel.SELECTED for value in decisions),
            1,
        )
        loser = next(value for value in decisions if value.label is AllocationLabel.SUPPRESSED)
        self.assertEqual(loser.binding_constraint, "candidate_already_selected")

        replay = ReconsiderationProjection()
        replay.rebuild(kernel.schemas.normalize(event) for event in await kernel.history())
        self.assertEqual(replay.semantic_snapshot(), projection.semantic_snapshot())
        await kernel.stop()
        await second_kernel.stop()

    async def test_revocation_between_scan_and_allocation_terminates_without_surface(self) -> None:
        scan_admitted = asyncio.Event()
        release = asyncio.Event()

        class PausedAfterScanWorker(ReconsiderationShadowWorker):
            async def _process_scan(
                self,
                scan_event: Event,
            ) -> ReconsiderationAllocation | None:
                scan_admitted.set()
                await release.wait()
                return await super()._process_scan(scan_event)

        (
            kernel,
            fixture_worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            scan_clock,
        ) = await prepare_mandate_fixture(count=1)
        worker = PausedAfterScanWorker(
            kernel,
            authority=fixture_worker.authority,
            policy=fixture_worker.policy,
            clock=scan_clock,
            derived_information_id_deriver=ID_DERIVER,
        )
        evidence = await current_evidence(kernel, suffix="revoked-after-scan")
        task = asyncio.create_task(
            worker.run_scan(
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                seeds=(seed(inquiries[0], information_refs[0], evidence, strength=0.9),),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
        )
        await scan_admitted.wait()
        revocation_authorization = await kernel.emit(
            Event(
                "user.reconsideration_revoked",
                "fixture:user",
                timestamp=scan_clock(),
            )
        )
        await fixture_worker.revoke_mandate(
            ReconsiderationMandateRevocation.create(
                mandate_id=mandate.mandate_id,
                mandate_revision_id=mandate.revision_id,
                issuer_id="user:carlos",
                authority_id=mandate.authority_id,
                authorization_ref=f"event:{revocation_authorization.id}",
                reason="close allocation-time revocation race",
                revoked_at=scan_clock(),
            )
        )
        release.set()
        allocation = await task
        assert allocation is not None
        self.assertEqual(allocation.selected_candidate_ids, ())
        self.assertEqual(
            allocation.decisions[0].binding_constraint,
            "basis_no_longer_current",
        )
        projection = await fixture_worker.current_projection()
        self.assertEqual(len(projection.traces), 1)
        self.assertEqual(projection.proposals, ())
        checkpoint = ConsumerCheckpoint.from_event((await kernel.history())[-1])
        self.assertEqual(checkpoint.epoch_id, allocation.allocation_id)

        replay = ReconsiderationProjection()
        replay.rebuild(kernel.schemas.normalize(event) for event in await kernel.history())
        self.assertEqual(replay.semantic_snapshot(), projection.semantic_snapshot())
        await kernel.stop()

    async def test_changed_current_evidence_creates_a_new_candidate(self) -> None:
        (
            kernel,
            worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            scan_clock,
        ) = await prepare_mandate_fixture(count=1)
        basis = CurrentCognitiveBasis.from_mandate(mandate.revision_id)
        first_evidence = await current_evidence(kernel, suffix="first-cut")
        first = await worker.run_scan(
            basis=basis,
            seeds=(seed(inquiries[0], information_refs[0], first_evidence, strength=0.9),),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        scan_clock.advance(timedelta(minutes=2))
        second_evidence = await current_evidence(kernel, suffix="second-cut")
        second = await worker.run_scan(
            basis=basis,
            seeds=(seed(inquiries[0], information_refs[0], second_evidence, strength=0.9),),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        assert first is not None and second is not None
        self.assertNotEqual(first.allocation_id, second.allocation_id)
        projection = await worker.current_projection()
        self.assertEqual(len(projection.candidates), 2)
        self.assertEqual(len(projection.allocations), 2)
        await kernel.stop()

    async def test_unknown_and_negative_value_candidates_are_suppressed(self) -> None:
        (
            kernel,
            worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            _scan_clock,
        ) = await prepare_mandate_fixture()
        evidence = await current_evidence(kernel)
        expensive = ScarceCognitionCostSnapshot(
            compute_units=3.0,
            wall_time_seconds=100.0,
            monetary_cost=0.9,
            attention_units=0.8,
            interruption_units=0.2,
            privacy_exposure_units=0.4,
            opportunity_cost_units=0.9,
            revalidation_units=0.9,
        )
        allocation = await worker.run_scan(
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            seeds=(
                seed(
                    inquiries[0],
                    information_refs[0],
                    evidence,
                    strength=0.8,
                    unknown=True,
                ),
                seed(
                    inquiries[1],
                    information_refs[1],
                    evidence,
                    strength=0.1,
                    costs=expensive,
                ),
            ),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        assert allocation is not None
        self.assertTrue(
            all(value.label is AllocationLabel.SUPPRESSED for value in allocation.decisions)
        )
        projection = await worker.current_projection()
        self.assertEqual(projection.proposals, ())
        self.assertTrue(
            any(value.binding_constraint == "critical_features" for value in allocation.decisions)
        )
        self.assertTrue(
            any(value.binding_constraint == "minimum_net_voc" for value in allocation.decisions)
        )
        await kernel.stop()

    async def test_aggregate_interruption_ceiling_limits_selected_portfolio(self) -> None:
        (
            kernel,
            worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            _scan_clock,
        ) = await prepare_mandate_fixture(
            count=2,
            max_candidates=2,
            maximum_interruption_units=0.15,
        )
        evidence = await current_evidence(kernel, suffix="aggregate-interruption")
        allocation = await worker.run_scan(
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            seeds=(
                seed(inquiries[0], information_refs[0], evidence, strength=0.95),
                seed(inquiries[1], information_refs[1], evidence, strength=0.9),
            ),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        assert allocation is not None
        self.assertEqual(len(allocation.selected_candidate_ids), 1)
        self.assertLessEqual(
            allocation.consumed.interruption_units,
            mandate.maximum_interruption_units,
        )
        self.assertEqual(
            sum(
                value.binding_constraint == "maximum_interruption_units"
                for value in allocation.decisions
            ),
            1,
        )
        await kernel.stop()

    async def test_restricted_sources_remain_governed_without_text_leakage(self) -> None:
        (
            kernel,
            worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            _scan_clock,
        ) = await prepare_mandate_fixture(
            count=1,
            classification=Classification.RESTRICTED,
        )
        evidence = await current_evidence(kernel, suffix="restricted")
        allocation = await worker.run_scan(
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            seeds=(seed(inquiries[0], information_refs[0], evidence, strength=0.9),),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        assert allocation is not None
        projection = await worker.current_projection()
        candidate = projection.candidates[0]
        trace = projection.traces[0]
        reconsideration_events = tuple(
            event for event in await kernel.history() if event.type in RECONSIDERATION_EVENT_TYPES
        )
        serialized = json.dumps(
            [
                {
                    "type": event.type,
                    "subject": event.subject,
                    "payload": event.payload,
                    "metadata": event.metadata,
                }
                for event in reconsideration_events
            ],
            sort_keys=True,
        )
        self.assertNotIn(inquiries[0].question, serialized)
        self.assertNotIn("historical_question", serialized)

        candidate_lineage = projection.information.lineage(candidate.derived_information_id)
        allocation_lineage = projection.information.lineage(allocation.derived_information_id)
        trace_lineage = projection.information.lineage(trace.derived_information_id)
        self.assertIsNotNone(candidate_lineage)
        self.assertIsNotNone(allocation_lineage)
        self.assertIsNotNone(trace_lineage)
        assert candidate_lineage is not None
        assert allocation_lineage is not None
        assert trace_lineage is not None
        self.assertEqual(
            candidate_lineage.source_information_ids,
            (information_refs[0].information_id,),
        )
        self.assertEqual(
            allocation_lineage.source_information_ids,
            (candidate.derived_information_id,),
        )
        self.assertEqual(
            trace_lineage.source_information_ids,
            (allocation.derived_information_id,),
        )
        composition = InformationGovernanceEngine(projection.information).composition_for(
            GovernedInformationRef(trace.derived_information_id)
        )
        self.assertEqual(composition.classification, Classification.RESTRICTED)
        await kernel.stop()

    async def test_foreground_demand_defers_positive_reconsideration(self) -> None:
        (
            kernel,
            worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            _scan_clock,
        ) = await prepare_mandate_fixture(count=1)
        evidence = await current_evidence(kernel)
        await kernel.emit(
            Event(
                "decision.proposed",
                "fixture",
                {"foreground": True},
                timestamp=NOW + timedelta(hours=3, seconds=30),
            )
        )
        allocation = await worker.run_scan(
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            seeds=(seed(inquiries[0], information_refs[0], evidence, strength=0.9),),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        assert allocation is not None
        self.assertIs(
            allocation.decisions[0].label,
            AllocationLabel.DEFERRED_BY_CONSTRAINT,
        )
        self.assertEqual(
            allocation.decisions[0].binding_constraint,
            "foreground_preemption",
        )
        self.assertEqual((await worker.current_projection()).proposals, ())
        await kernel.stop()

    async def test_foreground_arriving_after_scan_is_pinned_and_preempts(self) -> None:
        class InterleavingForegroundWorker(ReconsiderationShadowWorker):
            def __init__(self, *args: object, **kwargs: object) -> None:
                super().__init__(*args, **kwargs)  # type: ignore[arg-type]
                self.inserted = False

            async def _process_scan(
                self,
                scan_event: Event,
            ) -> ReconsiderationAllocation | None:
                if not self.inserted:
                    self.inserted = True
                    await self.kernel.emit(
                        Event(
                            "decision.proposed",
                            "fixture:foreground-race",
                            {"foreground": True},
                            timestamp=self.clock(),
                        )
                    )
                return await super()._process_scan(scan_event)

        (
            kernel,
            fixture_worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            scan_clock,
        ) = await prepare_mandate_fixture(count=1)
        worker = InterleavingForegroundWorker(
            kernel,
            authority=fixture_worker.authority,
            policy=fixture_worker.policy,
            clock=scan_clock,
            derived_information_id_deriver=ID_DERIVER,
        )
        evidence = await current_evidence(kernel, suffix="foreground-race")
        scan_seed = seed(inquiries[0], information_refs[0], evidence, strength=0.9)
        first = await worker.run_scan(
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            seeds=(scan_seed,),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        assert first is not None
        self.assertIs(
            first.decisions[0].label,
            AllocationLabel.DEFERRED_BY_CONSTRAINT,
        )
        self.assertEqual(first.decisions[0].binding_constraint, "foreground_preemption")
        self.assertEqual(len(first.foreground_demand_refs), 1)
        foreground_event = next(
            event
            for event in await kernel.history()
            if event.type == "decision.proposed" and event.source == "fixture:foreground-race"
        )
        self.assertEqual(first.foreground_demand_refs, (f"event:{foreground_event.id}",))

        scan_clock.advance(timedelta(minutes=2))
        second = await worker.run_scan(
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            seeds=(scan_seed,),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        assert second is not None
        self.assertNotEqual(second.allocation_id, first.allocation_id)
        self.assertEqual(second.selected_candidate_ids, (first.decisions[0].candidate_id,))
        self.assertEqual(len((await worker.current_projection()).candidates), 1)
        await kernel.stop()

    async def test_mandate_triggers_must_be_fresh_and_single_use(self) -> None:
        (
            kernel,
            worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            scan_clock,
        ) = await prepare_mandate_fixture(
            count=2,
            trigger_event_types=("scheduled.reconsideration",),
        )
        evidence = await current_evidence(kernel, suffix="trigger")
        first_seed = seed(inquiries[0], information_refs[0], evidence, strength=0.9)
        second_seed = seed(inquiries[1], information_refs[1], evidence, strength=0.8)
        pre_activation = next(
            event
            for event in await kernel.history()
            if event.source == "fixture:pre-activation-trigger"
        )
        with self.assertRaisesRegex(ValueError, "predates mandate activation"):
            await worker.run_scan(
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                seeds=(first_seed,),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
                trigger_event_id=pre_activation.id,
            )
        self.assertEqual((await worker.current_projection()).scans, ())

        older_unused = await kernel.emit(
            Event("scheduled.reconsideration", "fixture:trigger:older", timestamp=scan_clock())
        )
        fresh = await kernel.emit(
            Event("scheduled.reconsideration", "fixture:trigger:fresh", timestamp=scan_clock())
        )
        first = await worker.run_scan(
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            seeds=(first_seed,),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
            trigger_event_id=fresh.id,
        )
        self.assertIsNotNone(first)

        with self.assertRaisesRegex(ValueError, "already consumed"):
            await worker.run_scan(
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                seeds=(second_seed,),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
                trigger_event_id=fresh.id,
            )

        scan_clock.advance(timedelta(minutes=2))
        with self.assertRaisesRegex(ValueError, "stale"):
            await worker.run_scan(
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                seeds=(second_seed,),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
                trigger_event_id=older_unused.id,
            )
        self.assertEqual(len((await worker.current_projection()).scans), 1)

        fresh_second = await kernel.emit(
            Event(
                "scheduled.reconsideration",
                "fixture:trigger:second",
                timestamp=scan_clock(),
            )
        )
        second = await worker.run_scan(
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            seeds=(second_seed,),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
            trigger_event_id=fresh_second.id,
        )
        self.assertIsNotNone(second)
        self.assertEqual(len((await worker.current_projection()).scans), 2)
        await kernel.stop()

    async def test_expired_revoked_scope_trigger_cadence_and_interruption_fail_closed(self) -> None:
        async def attempt(case: str) -> None:
            trigger_types = ("scheduled.reconsideration",) if case == "trigger" else ()
            expires_in = timedelta(minutes=30) if case == "expired" else timedelta(days=1)
            (
                kernel,
                worker,
                mandate,
                principal,
                _g1,
                _current_g1,
                inquiries,
                information_refs,
                _scan_clock,
            ) = await prepare_mandate_fixture(
                count=1,
                trigger_event_types=trigger_types,
                expires_in=expires_in,
            )
            evidence = await current_evidence(kernel, suffix=case)
            candidate = seed(
                inquiries[0],
                information_refs[0],
                evidence,
                strength=0.9,
                domain="outside-scope" if case == "scope" else "personal-research",
                costs=(
                    ScarceCognitionCostSnapshot(interruption_units=0.3)
                    if case == "interruption"
                    else None
                ),
            )
            if case == "revoked":
                revocation_auth = await kernel.emit(
                    Event(
                        "user.reconsideration_revoked",
                        "fixture:user",
                        timestamp=NOW + timedelta(hours=2, minutes=30),
                    )
                )
                await worker.revoke_mandate(
                    ReconsiderationMandateRevocation.create(
                        mandate_id=mandate.mandate_id,
                        mandate_revision_id=mandate.revision_id,
                        issuer_id="user:carlos",
                        authority_id=mandate.authority_id,
                        authorization_ref=f"event:{revocation_auth.id}",
                        reason="fixture revocation",
                        revoked_at=revocation_auth.timestamp,
                    )
                )
            with self.assertRaises(ValueError, msg=case):
                await worker.run_scan(
                    basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                    seeds=(candidate,),
                    principal=principal,
                    actor_id="user:carlos",
                    source_trust_domain="local",
                    locality="local",
                )
            projection = await worker.current_projection()
            self.assertEqual(projection.scans, ())
            self.assertEqual(await worker.recover(), ())
            await kernel.stop()

        for case in ("expired", "revoked", "scope", "trigger", "interruption"):
            with self.subTest(case=case):
                await attempt(case)

        (
            kernel,
            worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            scan_clock,
        ) = await prepare_mandate_fixture(count=2, minimum_interval_seconds=600.0)
        first_evidence = await current_evidence(kernel, suffix="cadence-one")
        await worker.run_scan(
            basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
            seeds=(seed(inquiries[0], information_refs[0], first_evidence, strength=0.9),),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
        )
        scan_clock.advance(timedelta(minutes=1))
        second_evidence = await current_evidence(kernel, suffix="cadence-two")
        with self.assertRaisesRegex(ValueError, "cadence"):
            await worker.run_scan(
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                seeds=(seed(inquiries[1], information_refs[1], second_evidence, strength=0.8),),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
        await kernel.stop()

    async def test_information_governance_denial_and_missing_provenance_fail_closed(self) -> None:
        (
            kernel,
            worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            _scan_clock,
        ) = await prepare_mandate_fixture(
            count=1,
            policy_purpose="unrelated-purpose",
            mandate_purpose="historical-reconsideration",
        )
        evidence = await current_evidence(kernel)
        with self.assertRaises(StaleGovernanceDecisionError):
            await worker.run_scan(
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                seeds=(seed(inquiries[0], information_refs[0], evidence, strength=0.9),),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
        projection = await worker.current_projection()
        self.assertEqual(projection.scans, ())
        self.assertEqual(await worker.recover(), ())
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            replace(
                seed(inquiries[0], information_refs[0], evidence, strength=0.9),
                current_evidence_refs=(),
            )
        await kernel.stop()

    async def test_invalid_candidate_inputs_never_admit_a_poison_scan(self) -> None:
        (
            kernel,
            worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            _scan_clock,
        ) = await prepare_mandate_fixture(count=1)
        evidence = await current_evidence(kernel, suffix="valid-cut")
        valid = seed(inquiries[0], information_refs[0], evidence, strength=0.9)
        invalid_seeds = (
            replace(valid, inquiry_id="inquiry:unknown"),
            replace(valid, current_evidence_refs=("event:missing-current-evidence",)),
            replace(
                valid,
                features=replace(
                    valid.features,
                    provenance_refs=("event:missing-feature-provenance",),
                ),
            ),
            replace(valid, current_evidence_refs=inquiries[0].evidence_refs),
        )
        for invalid in invalid_seeds:
            with self.subTest(inquiry_id=invalid.inquiry_id):
                with self.assertRaises(ValueError):
                    await worker.run_scan(
                        basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                        seeds=(invalid,),
                        principal=principal,
                        actor_id="user:carlos",
                        source_trust_domain="local",
                        locality="local",
                    )
                self.assertEqual((await worker.current_projection()).scans, ())
                self.assertEqual(await worker.recover(), ())
        await kernel.stop()

        (
            kernel,
            worker,
            mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            _scan_clock,
        ) = await prepare_mandate_fixture(
            count=1,
            historical_terminal=False,
            inquiry_lifetime=timedelta(hours=6),
            revise_historical_goal=False,
        )
        evidence = await current_evidence(kernel, suffix="current-inquiry")
        with self.assertRaisesRegex(ValueError, "current inquiry"):
            await worker.run_scan(
                basis=CurrentCognitiveBasis.from_mandate(mandate.revision_id),
                seeds=(seed(inquiries[0], information_refs[0], evidence, strength=0.9),),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
            )
        self.assertEqual((await worker.current_projection()).scans, ())
        self.assertEqual(await worker.recover(), ())
        await kernel.stop()

        (
            kernel,
            worker,
            _mandate,
            principal,
            _g1,
            _current_g1,
            inquiries,
            information_refs,
            _scan_clock,
        ) = await prepare_mandate_fixture(count=1)
        origin, authority, trust = user_security()
        other_goal = await record_goal(
            IntentStewardCoordinator(
                kernel,
                validator=StrategicValidator(trust),
                clock=MutableClock(NOW + timedelta(hours=3)),
            ),
            goal_id="goal:unrelated-live",
            status=GoalStatus.ACTIVE,
            origin=origin,
            authority=authority,
            reason="prove same-goal reconsideration boundary",
        )
        evidence = await current_evidence(kernel, suffix="wrong-goal")
        policies = tuple(
            value.policy_id for value in (await worker.current_projection()).information.policies
        )
        with self.assertRaisesRegex(ValueError, "same stable goal lineage"):
            await worker.run_scan(
                basis=CurrentCognitiveBasis.from_live_intent(
                    GoverningIntentRef(other_goal.goal_id, other_goal.revision_id)
                ),
                seeds=(seed(inquiries[0], information_refs[0], evidence, strength=0.9),),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
                budget=scarce_budget(),
                information_use_purpose="historical-reconsideration",
                information_policy_ids=policies,
            )
        self.assertEqual((await worker.current_projection()).scans, ())
        self.assertEqual(await worker.recover(), ())
        await kernel.stop()

    async def test_terminal_and_stale_intent_cannot_self_authorize_reconsideration(self) -> None:
        (
            kernel,
            worker,
            _mandate,
            principal,
            g1,
            _current_g1,
            inquiries,
            information_refs,
            _scan_clock,
        ) = await prepare_mandate_fixture(count=1)
        evidence = await current_evidence(kernel)
        with self.assertRaisesRegex(ValueError, "ACTIVE or BLOCKED"):
            await worker.run_scan(
                basis=CurrentCognitiveBasis.from_live_intent(
                    GoverningIntentRef(g1.goal_id, g1.revision_id)
                ),
                seeds=(seed(inquiries[0], information_refs[0], evidence, strength=0.9),),
                principal=principal,
                actor_id="user:carlos",
                source_trust_domain="local",
                locality="local",
                budget=scarce_budget(),
                information_use_purpose="historical-reconsideration",
                information_policy_ids=tuple(
                    value.policy_id
                    for value in (await worker.current_projection()).information.policies
                ),
            )
        self.assertEqual((await worker.current_projection()).candidates, ())
        await kernel.stop()

    async def test_live_current_revision_can_reconsider_same_goal_lineage_only(self) -> None:
        kernel = NoemaKernel()
        clock = MutableClock(NOW)
        _steward, _old_g1, current_g1, inquiries = await seed_historical_inquiries(
            kernel,
            clock,
            count=1,
            terminal=False,
        )
        policy, information_refs = await record_information(kernel, count=1)
        authority = StaticReconsiderationAuthority(
            "reconsideration-authority:fixture",
            (("user:carlos", MandateIssuerKind.USER),),
        )
        worker = ReconsiderationShadowWorker(
            kernel,
            authority=authority,
            clock=MutableClock(NOW + timedelta(hours=3, minutes=1)),
            derived_information_id_deriver=ID_DERIVER,
        )
        principal = PrincipalSnapshot.create(
            principal_id="user:carlos",
            roles=(),
            groups=(),
            trust_domains=("local",),
            captured_at=NOW + timedelta(hours=2),
        )
        evidence = await current_evidence(kernel)
        allocation = await worker.run_scan(
            basis=CurrentCognitiveBasis.from_live_intent(
                GoverningIntentRef(current_g1.goal_id, current_g1.revision_id)
            ),
            seeds=(seed(inquiries[0], information_refs[0], evidence, strength=0.9),),
            principal=principal,
            actor_id="user:carlos",
            source_trust_domain="local",
            locality="local",
            budget=scarce_budget(),
            information_use_purpose="historical-reconsideration",
            information_policy_ids=(policy.policy_id,),
        )
        assert allocation is not None
        self.assertEqual(allocation.selected_candidate_ids, (allocation.decisions[0].candidate_id,))
        await kernel.stop()


class DerivedGovernanceRaceStore(InMemoryEventStore):
    """Hold matching CAS writers until both observed the same missing state."""

    def __init__(self) -> None:
        super().__init__()
        self.target_information_id: str | None = None
        self.arrivals = {
            LINEAGE_RECORDED_EVENT: 0,
            POLICY_BOUND_EVENT: 0,
        }
        self._barriers = {
            LINEAGE_RECORDED_EVENT: asyncio.Event(),
            POLICY_BOUND_EVENT: asyncio.Event(),
        }

    async def append_if_head(
        self,
        event: Event,
        *,
        expected_head_sequence: int,
    ) -> Event:
        if event.subject == self.target_information_id and event.type in self._barriers:
            self.arrivals[event.type] += 1
            barrier = self._barriers[event.type]
            if self.arrivals[event.type] >= 2:
                barrier.set()
            await asyncio.wait_for(barrier.wait(), timeout=5.0)
        return await super().append_if_head(
            event,
            expected_head_sequence=expected_head_sequence,
        )


class GappedSequenceStore(InMemoryEventStore):
    """Test store whose canonical sequences are monotonic but deliberately non-contiguous."""

    def _append_locked(self, event: Event) -> Event:
        existing = self._by_id.get(event.id)
        if existing is not None:
            return existing
        next_sequence = (self._events[-1].sequence or 0) + 2 if self._events else 2
        stored = event.with_sequence(next_sequence)
        self._events.append(stored)
        self._by_id[event.id] = stored
        return stored

    async def append_if_head(self, event: Event, *, expected_head_sequence: int) -> Event:
        async with self._lock:
            existing = self._by_id.get(event.id)
            if existing is not None:
                return existing
            actual = self._events[-1].sequence or 0 if self._events else 0
            if actual != expected_head_sequence:
                from noema import ConcurrentAppendError

                raise ConcurrentAppendError(
                    expected_head_sequence=expected_head_sequence,
                    actual_head_sequence=actual,
                )
            return self._append_locked(event)

    async def latest_sequence(self) -> int:
        async with self._lock:
            return self._events[-1].sequence or 0 if self._events else 0


class ReconsiderationDurabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_derived_governance_writers_reuse_one_lineage_and_binding(
        self,
    ) -> None:
        store = DerivedGovernanceRaceStore()
        first_kernel = NoemaKernel(store=store)
        await first_kernel.start()
        policy, information_refs = await record_information(first_kernel, count=1)
        second_kernel = NoemaKernel(store=store)
        await second_kernel.start()
        derived_information_id = ID_DERIVER.derive(
            namespace="reconsideration-concurrent-derived",
            stable_key="same-semantic-information",
        )
        store.target_information_id = derived_information_id
        authority = StaticReconsiderationAuthority(
            "authority:derived-governance-race",
            (("user:carlos", MandateIssuerKind.USER),),
        )
        first = ReconsiderationShadowWorker(
            first_kernel,
            authority=authority,
            clock=MutableClock(NOW + timedelta(hours=3)),
            derived_information_id_deriver=ID_DERIVER,
        )
        second = ReconsiderationShadowWorker(
            second_kernel,
            authority=authority,
            clock=MutableClock(NOW + timedelta(hours=3, seconds=1)),
            derived_information_id_deriver=ID_DERIVER,
        )
        await asyncio.wait_for(
            asyncio.gather(
                first._ensure_derived_governance(
                    information_id=derived_information_id,
                    source_information_ids=(information_refs[0].information_id,),
                    policy_ids=(policy.policy_id,),
                    recorded_at=NOW + timedelta(hours=3),
                ),
                second._ensure_derived_governance(
                    information_id=derived_information_id,
                    source_information_ids=(information_refs[0].information_id,),
                    policy_ids=(policy.policy_id,),
                    recorded_at=NOW + timedelta(hours=3, seconds=1),
                ),
            ),
            timeout=10.0,
        )

        history = await first_kernel.history()
        self.assertEqual(store.arrivals[LINEAGE_RECORDED_EVENT], 2)
        self.assertEqual(store.arrivals[POLICY_BOUND_EVENT], 2)
        self.assertEqual(
            sum(
                event.type == LINEAGE_RECORDED_EVENT and event.subject == derived_information_id
                for event in history
            ),
            1,
        )
        self.assertEqual(
            sum(
                event.type == POLICY_BOUND_EVENT and event.subject == derived_information_id
                for event in history
            ),
            1,
        )
        replay = ReconsiderationProjection()
        replay.rebuild(first_kernel.schemas.normalize(event) for event in history)
        lineage = replay.information.lineage(derived_information_id)
        binding = replay.information.binding(derived_information_id)
        self.assertIsNotNone(lineage)
        self.assertIsNotNone(binding)
        assert lineage is not None and binding is not None
        self.assertEqual(
            lineage.source_information_ids,
            (information_refs[0].information_id,),
        )
        self.assertEqual(binding.lineage_id, lineage.lineage_id)
        self.assertEqual(binding.policy_ids, (policy.policy_id,))
        await first_kernel.stop()
        await second_kernel.stop()

    async def test_exact_head_admission_is_safe_with_noncontiguous_sequences(self) -> None:
        kernel = NoemaKernel(store=GappedSequenceStore())
        authorization = await kernel.emit(
            Event("user.reconsideration_authorized", "fixture:user", timestamp=NOW)
        )
        authority = StaticReconsiderationAuthority(
            "authority:gapped",
            (("user:carlos", MandateIssuerKind.USER),),
        )
        worker = ReconsiderationShadowWorker(
            kernel,
            authority=authority,
            clock=MutableClock(NOW + timedelta(minutes=2)),
            derived_information_id_deriver=ID_DERIVER,
        )
        mandate = ReconsiderationMandate.create(
            mandate_id="mandate:gapped",
            revision=1,
            issuer_id="user:carlos",
            issuer_kind=MandateIssuerKind.USER,
            authority_id=authority.authority_id,
            authorization_ref=f"event:{authorization.id}",
            scope="prove gap-safe admission",
            candidate_classes=("inquiry",),
            candidate_domains=("personal-research",),
            budget=scarce_budget(),
            minimum_interval_seconds=1.0,
            trigger_event_types=(),
            issued_at=NOW + timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
            maximum_interruption_units=0.1,
            surfacing_policy=SurfacingPolicy.SHADOW_QUESTION_ONLY,
            information_use_purpose="historical-reconsideration",
            information_policy_ids=("ipol:0123456789abcdef0123456789abcdef",),
        )
        await worker.record_mandate(mandate)
        history = await kernel.history()
        self.assertEqual(tuple(event.sequence for event in history), (2, 4))
        self.assertEqual(
            history[1].metadata["validated_at_event_cursor"],
            history[0].sequence,
        )
        projection = await worker.current_projection()
        self.assertTrue(
            projection.mandates.is_active_revision(
                mandate.revision_id,
                at=NOW + timedelta(minutes=2),
            )
        )
        await kernel.stop()


class ReconsiderationModelTests(unittest.TestCase):
    def test_allocation_labels_are_exact_and_counterfactual_probability_is_absent(self) -> None:
        self.assertEqual(
            tuple(value.value for value in AllocationLabel),
            (
                "SELECTED",
                "DEFERRED_BY_CONSTRAINT",
                "SUPPRESSED",
                "EXPLICITLY_REJECTED",
            ),
        )

    def test_policy_weight_mappings_are_immutable(self) -> None:
        policy = ReconsiderationPolicySnapshot.create(version="immutable-fixture")
        with self.assertRaises(TypeError):
            policy.feature_weights["unresolvedness"] = 99.0
        with self.assertRaises(TypeError):
            policy.cost_weights["compute_units"] = 99.0

    def test_unauthorized_mandate_cannot_be_admitted(self) -> None:
        authority = StaticReconsiderationAuthority(
            "authority:fixture",
            (("user:carlos", MandateIssuerKind.USER),),
        )
        mandate = ReconsiderationMandate.create(
            mandate_id="mandate:bad",
            revision=1,
            issuer_id="agent:noema",
            issuer_kind=MandateIssuerKind.USER,
            authority_id=authority.authority_id,
            authorization_ref="event:claimed-user-event",
            scope="invalid",
            candidate_classes=("inquiry",),
            candidate_domains=("personal-research",),
            budget=scarce_budget(),
            minimum_interval_seconds=1.0,
            trigger_event_types=(),
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
            maximum_interruption_units=0.1,
            surfacing_policy=SurfacingPolicy.SHADOW_QUESTION_ONLY,
            information_use_purpose="historical-reconsideration",
            information_policy_ids=("ipol:0123456789abcdef0123456789abcdef",),
        )
        self.assertFalse(authority.authenticates_mandate(mandate))
