from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from noema import (
    AGENDA_SELECTED_EVENT,
    STABLE_GREEDY_SELECTOR_ID,
    ActivityDisposition,
    BackgroundCognitiveBudget,
    CalibrationExchange,
    CognitionScanRequest,
    CognitiveResourceVector,
    Commitment,
    CommitmentStatus,
    ConsumerCheckpointProjection,
    DreamAbandonmentReason,
    DreamEpoch,
    DreamEpochStatus,
    EndogenousPolicySnapshot,
    EndogenousProjection,
    EndogenousShadowWorker,
    Event,
    ExecutionLocus,
    GoalKind,
    GoalStatus,
    GoverningIntentRef,
    IntentAuthority,
    IntentAuthorityScope,
    IntentStewardCoordinator,
    IntrinsicActivity,
    IntrinsicActivityKind,
    MemoryProjector,
    NoemaKernel,
    OriginKind,
    OriginProvenance,
    OutcomeActor,
    OutcomeNode,
    OutcomeRoleAssignment,
    RuleEvaluationTrace,
    SemanticAssertion,
    Signal,
    SignalRole,
    StaticStrategicTrust,
    StrategicValidator,
    WorkOrder,
    select_intrinsic_agenda,
)
from noema.memory import EpistemicType

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


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
        authentication_ref="authn:local-user-session:1",
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


def budget(*, activities: int = 2) -> BackgroundCognitiveBudget:
    return BackgroundCognitiveBudget.create(
        ceiling=CognitiveResourceVector(
            activities=activities,
            compute_units=float(activities),
            wall_time_seconds=120.0,
            attention_units=0.25,
            privacy_risk_units=0.05,
        )
    )


async def build_strategy(
    kernel: NoemaKernel,
    clock: MutableClock,
) -> tuple[IntentStewardCoordinator, object, object, Commitment]:
    origin, authority, trust = user_security()
    steward = IntentStewardCoordinator(
        kernel,
        validator=StrategicValidator(trust),
        clock=clock,
    )
    goal = await steward.record_goal_revision(
        goal_id="goal:endogenous",
        description="Maintain a reliable release direction",
        priority=0.9,
        utility=1.0,
        success_criteria=("release direction remains defensible",),
        owner="user:carlos",
        status=GoalStatus.ACTIVE,
        deadline=NOW + timedelta(days=30),
        kind=GoalKind.USER_AUTHORED,
        governing_goal_refs=(),
        origin=origin,
        intent_authority=authority,
        author="user:carlos",
        revision_reason="seed durable intent",
    )
    clock.advance()
    roadmap = await steward.record_roadmap_revision(
        roadmap_id="roadmap:endogenous",
        governing_goal_revision_ids=(goal.revision_id,),  # type: ignore[attr-defined]
        outcome_nodes=(
            OutcomeNode(
                "release-confidence",
                "Maintain evidence-backed release confidence",
                ("release evidence is current", "coverage gap is closed"),
            ),
        ),
        assumptions=("release constraints remain stable",),
        confidence=0.7,
        success_criteria=("release remains safe",),
        resource_envelope={"attention_hours": 2.0},
        intent_authority=authority,
        author="user:carlos",
        revision_reason="seed strategic hypothesis",
    )
    clock.advance()
    roles = OutcomeRoleAssignment.create(
        outcome_ref=f"{roadmap.revision_id}#release-confidence",  # type: ignore[attr-defined]
        outcome_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
        decision_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
        executor=OutcomeActor("agent:noema", ExecutionLocus.AGENT),
        verifier=OutcomeActor("user:carlos", ExecutionLocus.USER),
        recorded_at=clock(),
    )
    await steward.record_outcome_roles(roles)
    clock.advance()
    commitment = Commitment(
        id="commitment:endogenous",
        description="Close the release evidence gap",
        owner="user:carlos",
        priority=0.9,
        status=CommitmentStatus.ACTIVE,
        deadline=NOW + timedelta(days=7),
        created_at=clock(),
        updated_at=clock(),
        governing_goal_refs=("goal:endogenous",),
        roadmap_revision_id=roadmap.revision_id,  # type: ignore[attr-defined]
        outcome_node_id="release-confidence",
        role_assignment_id=roles.assignment_id,
    )
    await steward.record_commitment(commitment, intent_authority=authority)
    return steward, goal, roadmap, commitment


class EndogenousCognitionAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_flagship_shadow_agenda_is_bounded_replayable_and_preemptible(self) -> None:
        clock = MutableClock(NOW)
        kernel = NoemaKernel()
        _steward, goal, _roadmap, commitment = await build_strategy(kernel, clock)

        memory = MemoryProjector(kernel, clock=clock)
        await memory.start()
        clock.advance()
        first_evidence = await kernel.emit(
            Event(
                "external.release_assessment",
                "fixture",
                {"assessment": "ready"},
                subject="goal:endogenous",
                timestamp=clock(),
            )
        )
        second_evidence = await kernel.emit(
            Event(
                "external.release_assessment",
                "fixture",
                {"assessment": "not-ready"},
                subject="goal:endogenous",
                timestamp=clock() + timedelta(minutes=1),
            )
        )
        first = SemanticAssertion.create(
            subject="goal:endogenous",
            predicate="release-readiness",
            value="ready",
            epistemic_type=EpistemicType.OBSERVED,
            confidence=0.9,
            valid_from=clock(),
            recorded_at=clock(),
            fresh_until=clock() + timedelta(minutes=5),
            source_refs=(f"event:{first_evidence.id}",),
            mutable_world=True,
        )
        second = SemanticAssertion.create(
            subject="goal:endogenous",
            predicate="release-readiness",
            value="not-ready",
            epistemic_type=EpistemicType.REPORTED,
            confidence=0.8,
            valid_from=clock(),
            recorded_at=clock() + timedelta(minutes=1),
            fresh_until=clock() + timedelta(minutes=5),
            source_refs=(f"event:{second_evidence.id}",),
            mutable_world=True,
        )
        await kernel.emit(first.to_event(source="fixture"))
        await kernel.emit(second.to_event(source="fixture"))
        await kernel.bus.drain()
        await memory.stop()

        scan_at = NOW + timedelta(hours=1)
        novelty_evidence = await kernel.emit(
            Event(
                "fact.observed",
                "fixture",
                {"key": "irrelevant-novel-fact", "value": "new but immaterial"},
                subject="goal:endogenous",
                timestamp=scan_at - timedelta(minutes=2),
            )
        )
        novelty_signal = Signal(
            signal_id="signal:irrelevant-novelty",
            kind="novelty",
            subject="goal:endogenous",
            confidence=0.9,
            salience=0.1,
            urgency=0.1,
            expected_value=0.05,
            valid_from=scan_at - timedelta(minutes=1),
            valid_until=scan_at + timedelta(hours=1),
            evidence_event_ids=(novelty_evidence.id,),
            rule_ref="novelty-fixture@1",
            evaluation_epoch_id="evaluation-epoch:fixture",
            role=SignalRole.EXCITATORY,
        )
        novelty_trace = RuleEvaluationTrace(
            trace_id="trace:irrelevant-novelty",
            rule_id="novelty-fixture",
            version=1,
            epoch_id="evaluation-epoch:fixture",
            evaluated_at=scan_at - timedelta(minutes=1),
            candidate=True,
            activated=True,
            activation_score=1.0,
            threshold=0.5,
            matched_conditions=("fact is new",),
            failed_conditions=(),
            evidence_refs=(novelty_evidence.id,),
            signal_would_emit=novelty_signal,
        )
        await kernel.emit(novelty_trace.to_event(source="fixture"))

        request_evidence = await kernel.emit(
            Event(
                "peer.calibration_requested",
                "fixture",
                {"proposition": "release is ready"},
                timestamp=scan_at - timedelta(minutes=4),
            )
        )
        response_evidence = await kernel.emit(
            Event(
                "peer.calibration_responded",
                "peer:reviewer",
                {"proposition": "release is ready", "confidence": 0.2},
                timestamp=scan_at - timedelta(minutes=3),
            )
        )
        worker = EndogenousShadowWorker(kernel, clock=clock)
        intent_ref = GoverningIntentRef(
            "goal:endogenous",
            goal.revision_id,  # type: ignore[attr-defined]
        )
        exchange = CalibrationExchange.create(
            proposition="release is ready",
            local_confidence=0.9,
            peer_confidence=0.2,
            local_evidence_refs=(f"event:{first_evidence.id}",),
            peer_evidence_refs=(f"event:{response_evidence.id}",),
            local_assumptions=("tests represent production",),
            peer_assumptions=("deployment conditions changed",),
            governing_intent_refs=(intent_ref,),
            peer_id="peer:reviewer",
            protocol_version="calibration-v1",
            request_provenance_ref=f"event:{request_evidence.id}",
            response_provenance_ref=f"event:{response_evidence.id}",
            recorded_at=scan_at - timedelta(minutes=2),
        )
        recorded_exchange = await worker.record_calibration(exchange)
        await worker.start()

        strategic_before = tuple(
            event.id for event in await kernel.history() if event.type.startswith("intent.")
        )
        selection = await worker.run_scan(
            budget=budget(activities=2),
            started_at=scan_at,
            expires_at=scan_at + timedelta(minutes=10),
        )
        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertEqual(len(selection.selected_activity_ids), 2)

        projection = await worker.current_projection()
        activities = {
            value.activity_id: value
            for value in projection.activities_for_epoch(selection.epoch_id)
        }
        selected_kinds = {
            activities[activity_id].kind for activity_id in selection.selected_activity_ids
        }
        self.assertEqual(
            selected_kinds,
            {
                IntrinsicActivityKind.BELIEF_MAINTENANCE,
                IntrinsicActivityKind.GOAL_OR_ROADMAP_MAINTENANCE,
            },
        )
        novelty = next(
            value
            for value in activities.values()
            if "signal:irrelevant-novelty" in value.target_refs
        )
        novelty_decision = next(
            value for value in selection.decisions if value.activity_id == novelty.activity_id
        )
        self.assertIs(novelty_decision.disposition, ActivityDisposition.SUPPRESSED)
        self.assertEqual(projection.calibrations, (recorded_exchange,))
        self.assertEqual(recorded_exchange.local_confidence, 0.9)
        self.assertEqual(recorded_exchange.peer_confidence, 0.2)
        self.assertEqual(recorded_exchange.local_assumptions, ("tests represent production",))
        self.assertEqual(recorded_exchange.peer_assumptions, ("deployment conditions changed",))
        self.assertNotEqual(
            recorded_exchange.local_evidence_refs,
            recorded_exchange.peer_evidence_refs,
        )

        replay = EndogenousProjection()
        replay.rebuild(kernel.schemas.normalize(event) for event in await kernel.history())
        self.assertEqual(replay.semantic_snapshot(), projection.semantic_snapshot())

        epoch = projection.epoch(selection.epoch_id)
        policy = projection.policy(selection.policy_id)
        assert epoch is not None
        assert policy is not None
        self.assertEqual(epoch.selector_id, STABLE_GREEDY_SELECTOR_ID)
        roadmap_activity = next(
            activity
            for activity in activities.values()
            if any(ref.startswith("roadmap-revision:") for ref in activity.target_refs)
        )
        self.assertIn(
            "event:commitment-recorded:commitment:endogenous",
            roadmap_activity.evidence_refs,
        )
        duplicate_selection = select_intrinsic_agenda(
            epoch=epoch,
            policy=policy,
            activities=projection.activities_for_epoch(epoch.epoch_id),
            estimates=projection.estimates_for_epoch(epoch.epoch_id),
            selected_at=selection.selected_at + timedelta(microseconds=1),
        )
        duplicate_event = replace(
            duplicate_selection.to_event(source="fixture"),
            sequence=projection.event_cursor + 1,
            metadata={"validated_at_event_cursor": projection.event_cursor},
        )
        with self.assertRaisesRegex(ValueError, "spend its budget twice"):
            projection.apply(duplicate_event)

        foreground = WorkOrder.create(
            purpose="respond to foreground release request",
            governing_goal_refs=("goal:endogenous",),
            created_from=(f"commitment:{commitment.id}",),
            priority=1.0,
            desired_outcome="foreground request is represented",
            success_criteria=("foreground request is bounded",),
            created_at=scan_at + timedelta(minutes=1),
        )
        await kernel.emit(foreground.to_event(source="fixture"))
        await kernel.bus.drain()
        projection = await worker.current_projection()
        self.assertIs(
            projection.epoch_status(selection.epoch_id),
            DreamEpochStatus.PREEMPTED,
        )
        existing_activity = activities[selection.selected_activity_ids[0]]
        post_preemption_activity = IntrinsicActivity.create(
            kind=existing_activity.kind,
            inquiry_id=existing_activity.inquiry_id,
            governing_intent_refs=existing_activity.governing_intent_refs,
            evidence_refs=existing_activity.evidence_refs,
            target_refs=(*existing_activity.target_refs, "test:post-preemption"),
            voc_inputs=existing_activity.voc_inputs,
            urgency=existing_activity.urgency,
            confidence=existing_activity.confidence,
            interruptible=True,
            expires_at=existing_activity.expires_at,
            resources=existing_activity.resources,
            causal_cursor=existing_activity.causal_cursor,
            producer_id="fixture",
        )
        post_preemption_event = replace(
            post_preemption_activity.to_event(
                source="fixture",
                epoch_id=selection.epoch_id,
                recorded_at=scan_at + timedelta(minutes=2),
            ),
            sequence=projection.event_cursor + 1,
            metadata={"validated_at_event_cursor": projection.event_cursor},
        )
        with self.assertRaisesRegex(ValueError, "cannot consume cognition"):
            projection.apply(post_preemption_event)
        terminal_replay = EndogenousProjection()
        terminal_replay.rebuild(kernel.schemas.normalize(event) for event in await kernel.history())
        self.assertEqual(terminal_replay.semantic_snapshot(), projection.semantic_snapshot())
        strategic_after = tuple(
            event.id for event in await kernel.history() if event.type.startswith("intent.")
        )
        self.assertEqual(strategic_after, strategic_before)
        self.assertFalse(
            any(
                event.type.startswith(("action.", "decision.authorized"))
                for event in await kernel.history()
            )
        )
        await worker.stop()
        await kernel.stop()

    async def test_no_positive_value_spends_no_cognitive_budget(self) -> None:
        clock = MutableClock(NOW)
        kernel = NoemaKernel()
        await build_strategy(kernel, clock)
        worker = EndogenousShadowWorker(
            kernel,
            policy=EndogenousPolicySnapshot.create(
                version="deterministic-silence-fixture",
                minimum_net_voc=10.0,
            ),
        )
        selection = await worker.run_scan(
            budget=budget(activities=2),
            started_at=NOW + timedelta(hours=1),
        )
        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertEqual(selection.selected_activity_ids, ())
        self.assertEqual(selection.consumed, CognitiveResourceVector())
        self.assertTrue(
            all(
                decision.disposition is ActivityDisposition.SUPPRESSED
                for decision in selection.decisions
            )
        )
        self.assertFalse(
            any(
                event.type.startswith(("work.", "action.", "decision.authorized"))
                for event in await kernel.history()
            )
        )
        await kernel.stop()

    async def test_no_goal_and_terminal_goal_produce_no_intrinsic_activity(self) -> None:
        empty_kernel = NoemaKernel()
        empty_worker = EndogenousShadowWorker(empty_kernel)
        self.assertIsNone(
            await empty_worker.run_scan(
                budget=budget(activities=1),
                started_at=NOW,
            )
        )
        self.assertEqual((await empty_worker.current_projection()).activities, ())
        await empty_kernel.stop()

        clock = MutableClock(NOW)
        kernel = NoemaKernel()
        steward, goal, _roadmap, _commitment = await build_strategy(kernel, clock)
        origin, authority, _trust = user_security()
        clock.advance()
        await steward.record_goal_revision(
            goal_id="goal:endogenous",
            description="Maintain a reliable release direction",
            priority=0.9,
            utility=1.0,
            success_criteria=("release direction remains defensible",),
            owner="user:carlos",
            status=GoalStatus.CANCELLED,
            deadline=NOW + timedelta(days=30),
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
            origin=origin,
            intent_authority=authority,
            author="user:carlos",
            revision_reason="cancel governing intent",
        )
        worker = EndogenousShadowWorker(kernel)
        self.assertIsNone(
            await worker.run_scan(
                budget=budget(activities=1),
                started_at=NOW + timedelta(hours=1),
            )
        )
        projection = await worker.current_projection()
        self.assertEqual(projection.activities, ())
        self.assertFalse(
            any(
                inquiry.governing_intent_refs[0].goal_revision_id == goal.revision_id  # type: ignore[attr-defined]
                for inquiry in projection.inquiries
            )
        )
        await kernel.stop()

    async def test_crash_before_checkpoint_reuses_outputs_and_budget_once(self) -> None:
        class CrashBeforeCheckpointWorker(EndogenousShadowWorker):
            async def _advance_checkpoint(self, **kwargs: object):  # type: ignore[no-untyped-def]
                raise RuntimeError("simulated crash before checkpoint")

        clock = MutableClock(NOW)
        kernel = NoemaKernel()
        await build_strategy(kernel, clock)
        clock.value = NOW + timedelta(hours=1)
        crashed = CrashBeforeCheckpointWorker(kernel, clock=clock)
        with self.assertRaisesRegex(RuntimeError, "simulated crash"):
            await crashed.run_scan(
                budget=budget(activities=1),
                started_at=NOW + timedelta(hours=1),
            )
        before = await crashed.current_projection()
        self.assertEqual(len(before.selections), 1)
        inquiry_ids = tuple(value.inquiry_id for value in before.inquiries)
        consumed = before.selections[0].consumed

        clock.advance(timedelta(seconds=30))
        recovered_worker = EndogenousShadowWorker(kernel, clock=clock)
        recovered = await recovered_worker.recover()
        self.assertEqual(len(recovered), 1)
        after = await recovered_worker.current_projection()
        self.assertEqual(tuple(value.inquiry_id for value in after.inquiries), inquiry_ids)
        self.assertEqual(len(after.selections), 1)
        self.assertEqual(after.selections[0].consumed, consumed)
        await kernel.stop()

    async def test_event_driven_foreground_preempts_before_selection_and_recovers(self) -> None:
        class PreemptBeforeAgendaWorker(EndogenousShadowWorker):
            injected = False

            async def _append_epoch_output(
                self,
                event: Event,
                *,
                epoch_id: str,
                intent_refs: tuple[GoverningIntentRef, ...],
                at: datetime,
            ) -> Event | None:
                if event.type == AGENDA_SELECTED_EVENT and not self.injected:
                    self.injected = True
                    await self.kernel.emit(
                        Event(
                            "decision.proposed",
                            "fixture",
                            {"reason": "foreground arrived during DREAM"},
                            timestamp=at + timedelta(seconds=1),
                        )
                    )
                    await self.kernel.bus.drain()
                return await super()._append_epoch_output(
                    event,
                    epoch_id=epoch_id,
                    intent_refs=intent_refs,
                    at=at,
                )

        clock = MutableClock(NOW + timedelta(hours=1))
        kernel = NoemaKernel()
        await build_strategy(kernel, MutableClock(NOW))
        worker = PreemptBeforeAgendaWorker(kernel, clock=clock)
        await worker.start()
        selection = await worker.run_scan(
            budget=budget(activities=1),
            started_at=clock(),
            expires_at=clock() + timedelta(minutes=5),
        )
        self.assertIsNone(selection)
        projection = await worker.current_projection()
        self.assertEqual(len(projection.epochs), 1)
        epoch = projection.epochs[0]
        self.assertIs(projection.epoch_status(epoch.epoch_id), DreamEpochStatus.PREEMPTED)
        self.assertEqual(projection.selections, ())

        before_recovery = tuple(event.id for event in await kernel.history())
        recovered = await worker.recover()
        self.assertEqual(recovered, ())
        self.assertEqual(tuple(event.id for event in await kernel.history()), before_recovery)
        await worker.stop()
        await kernel.stop()

    async def test_expiry_before_selection_recovers_terminal_scan_checkpoint(self) -> None:
        class ExpireBeforeAgendaWorker(EndogenousShadowWorker):
            injected = False
            crash_checkpoint = True

            async def _append_epoch_output(
                self,
                event: Event,
                *,
                epoch_id: str,
                intent_refs: tuple[GoverningIntentRef, ...],
                at: datetime,
            ) -> Event | None:
                if event.type == AGENDA_SELECTED_EVENT and not self.injected:
                    self.injected = True
                    projection = await self.current_projection()
                    epoch = projection.epoch(epoch_id)
                    assert epoch is not None
                    await self.expire_epochs(at=epoch.expires_at + timedelta(seconds=1))
                return await super()._append_epoch_output(
                    event,
                    epoch_id=epoch_id,
                    intent_refs=intent_refs,
                    at=at,
                )

            async def _complete_scan_checkpoint(
                self,
                trigger: Event,
                request: CognitionScanRequest,
                epoch: DreamEpoch,
            ) -> None:
                if self.crash_checkpoint:
                    self.crash_checkpoint = False
                    raise RuntimeError("simulated crash after DREAM expiry")
                await super()._complete_scan_checkpoint(trigger, request, epoch)

        clock = MutableClock(NOW + timedelta(hours=1))
        kernel = NoemaKernel()
        await build_strategy(kernel, MutableClock(NOW))
        crashed = ExpireBeforeAgendaWorker(kernel, clock=clock)
        with self.assertRaisesRegex(RuntimeError, "after DREAM expiry"):
            await crashed.run_scan(
                budget=budget(activities=1),
                started_at=clock(),
                expires_at=clock() + timedelta(seconds=5),
            )
        projection = await crashed.current_projection()
        epoch = projection.epochs[0]
        self.assertIs(projection.epoch_status(epoch.epoch_id), DreamEpochStatus.EXPIRED)
        self.assertEqual(projection.selections, ())

        clock.advance(timedelta(seconds=10))
        recovered_worker = EndogenousShadowWorker(kernel, clock=clock)
        self.assertEqual(await recovered_worker.recover(), ())
        checkpoints = ConsumerCheckpointProjection()
        checkpoints.rebuild(await kernel.history())
        checkpoint = checkpoints.get(recovered_worker.consumer_id)
        assert checkpoint is not None
        request_event = projection.event(epoch.trigger_event_id)
        assert request_event is not None and request_event.sequence is not None
        self.assertGreaterEqual(checkpoint.last_completed_sequence, request_event.sequence)
        await kernel.stop()

    async def test_intent_change_before_selection_abandons_and_recovers_scan(self) -> None:
        clock = MutableClock(NOW)
        kernel = NoemaKernel()
        steward, _goal, _roadmap, _commitment = await build_strategy(kernel, clock)
        origin, authority, _trust = user_security()
        scan_at = NOW + timedelta(hours=1)
        clock.value = scan_at

        class ChangeIntentBeforeAgendaWorker(EndogenousShadowWorker):
            injected = False
            crash_checkpoint = True

            async def _append_epoch_output(
                self,
                event: Event,
                *,
                epoch_id: str,
                intent_refs: tuple[GoverningIntentRef, ...],
                at: datetime,
            ) -> Event | None:
                if event.type == AGENDA_SELECTED_EVENT and not self.injected:
                    self.injected = True
                    clock.advance(timedelta(seconds=1))
                    await steward.record_goal_revision(
                        goal_id="goal:endogenous",
                        description="Maintain a reliable release direction",
                        priority=0.9,
                        utility=1.0,
                        success_criteria=("release direction remains defensible",),
                        owner="user:carlos",
                        status=GoalStatus.CANCELLED,
                        deadline=NOW + timedelta(days=30),
                        kind=GoalKind.USER_AUTHORED,
                        governing_goal_refs=(),
                        origin=origin,
                        intent_authority=authority,
                        author="user:carlos",
                        revision_reason="cancel intent during DREAM",
                    )
                return await super()._append_epoch_output(
                    event,
                    epoch_id=epoch_id,
                    intent_refs=intent_refs,
                    at=at,
                )

            async def _complete_scan_checkpoint(
                self,
                trigger: Event,
                request: CognitionScanRequest,
                epoch: DreamEpoch,
            ) -> None:
                if self.crash_checkpoint:
                    self.crash_checkpoint = False
                    raise RuntimeError("simulated crash after DREAM abandonment")
                await super()._complete_scan_checkpoint(trigger, request, epoch)

        crashed = ChangeIntentBeforeAgendaWorker(kernel, clock=clock)
        with self.assertRaisesRegex(RuntimeError, "after DREAM abandonment"):
            await crashed.run_scan(
                budget=budget(activities=1),
                started_at=scan_at,
                expires_at=scan_at + timedelta(minutes=5),
            )
        projection = await crashed.current_projection()
        epoch = projection.epochs[0]
        self.assertIs(projection.epoch_status(epoch.epoch_id), DreamEpochStatus.ABANDONED)
        epoch_snapshot = projection.semantic_snapshot()["epochs"][0]
        assert isinstance(epoch_snapshot, dict)
        self.assertEqual(
            epoch_snapshot["abandonment_reason"],
            DreamAbandonmentReason.GOVERNING_INTENT_CHANGED.value,
        )
        self.assertEqual(projection.selections, ())

        recovered_worker = EndogenousShadowWorker(kernel, clock=clock)
        self.assertEqual(await recovered_worker.recover(), ())
        checkpoints = ConsumerCheckpointProjection()
        checkpoints.rebuild(await kernel.history())
        checkpoint = checkpoints.get(recovered_worker.consumer_id)
        assert checkpoint is not None
        request_event = projection.event(epoch.trigger_event_id)
        assert request_event is not None and request_event.sequence is not None
        self.assertGreaterEqual(checkpoint.last_completed_sequence, request_event.sequence)
        await kernel.stop()

    async def test_repeated_scan_reuses_active_epoch_and_does_not_renew_inquiry(self) -> None:
        clock = MutableClock(NOW + timedelta(hours=1))
        kernel = NoemaKernel()
        await build_strategy(kernel, MutableClock(NOW))
        worker = EndogenousShadowWorker(kernel, clock=clock)
        first = await worker.run_scan(
            budget=budget(activities=1),
            started_at=clock(),
            expires_at=clock() + timedelta(minutes=5),
        )
        self.assertIsNotNone(first)
        assert first is not None
        first_projection = await worker.current_projection()
        inquiry_ids = tuple(value.inquiry_id for value in first_projection.inquiries)
        activity_ids = tuple(value.activity_id for value in first_projection.activities)

        clock.advance(timedelta(minutes=1))
        reused = await worker.run_scan(
            budget=budget(activities=2),
            started_at=clock(),
            expires_at=clock() + timedelta(minutes=5),
        )
        self.assertEqual(reused, first)
        active_projection = await worker.current_projection()
        self.assertEqual(len(active_projection.epochs), 1)
        self.assertEqual(
            tuple(value.activity_id for value in active_projection.activities),
            activity_ids,
        )

        clock.advance(timedelta(minutes=5))
        await worker.expire_epochs(at=clock())
        clock.advance(timedelta(seconds=1))
        self.assertIsNone(
            await worker.run_scan(
                budget=budget(activities=2),
                started_at=clock(),
                expires_at=clock() + timedelta(minutes=5),
            )
        )
        final_projection = await worker.current_projection()
        self.assertEqual(len(final_projection.epochs), 1)
        self.assertEqual(
            tuple(value.inquiry_id for value in final_projection.inquiries),
            inquiry_ids,
        )
        self.assertEqual(
            tuple(value.activity_id for value in final_projection.activities),
            activity_ids,
        )
        await kernel.stop()

    async def test_historical_foreground_and_unknown_selector_fail_closed(self) -> None:
        clock = MutableClock(NOW + timedelta(hours=1))
        kernel = NoemaKernel()
        await build_strategy(kernel, MutableClock(NOW))
        historical = await kernel.emit(
            Event(
                "decision.proposed",
                "fixture",
                {"reason": "older foreground"},
                timestamp=clock() - timedelta(minutes=1),
            )
        )
        worker = EndogenousShadowWorker(kernel, clock=clock)
        await worker.start()
        selection = await worker.run_scan(
            budget=budget(activities=1),
            started_at=clock(),
            expires_at=clock() + timedelta(minutes=5),
        )
        self.assertIsNotNone(selection)
        assert selection is not None
        projection = await worker.current_projection()
        epoch = projection.epoch(selection.epoch_id)
        assert epoch is not None and historical.sequence is not None
        self.assertLess(historical.sequence, epoch.event_log_cursor)
        self.assertIs(projection.epoch_status(epoch.epoch_id), DreamEpochStatus.ACTIVE)
        await worker.stop()
        await kernel.stop()

        unknown_policy = EndogenousPolicySnapshot.create(
            version="future-selector-fixture",
            selector_id="future-selector",
            selector_version=99,
        )
        request = CognitionScanRequest.create(
            policy_id=unknown_policy.policy_id,
            budget=budget(activities=1),
            requested_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
        )
        policy_event = replace(
            unknown_policy.to_event(source="fixture", recorded_at=NOW),
            sequence=1,
        )
        request_event = replace(request.to_event(source="fixture"), sequence=2)
        unknown_epoch = DreamEpoch.start(
            consumer_id="fixture-consumer",
            trigger_event_id=request_event.id,
            event_log_cursor=2,
            policy=unknown_policy,
            budget=request.budget,
            started_at=request.requested_at,
            expires_at=request.expires_at,
        )
        epoch_event = replace(
            unknown_epoch.to_event(source="fixture"),
            sequence=3,
            metadata={"validated_at_event_cursor": 2},
        )
        replay = EndogenousProjection()
        replay.apply(policy_event)
        replay.apply(request_event)
        with self.assertRaisesRegex(ValueError, "unsupported endogenous agenda selector"):
            replay.apply(epoch_event)

    async def test_blocked_goal_remains_eligible_for_recovery_cognition(self) -> None:
        clock = MutableClock(NOW)
        kernel = NoemaKernel()
        steward, _goal, _roadmap, _commitment = await build_strategy(kernel, clock)
        origin, authority, _trust = user_security()
        clock.advance()
        blocked = await steward.record_goal_revision(
            goal_id="goal:endogenous",
            description="Maintain a reliable release direction",
            priority=0.9,
            utility=1.0,
            success_criteria=("release direction remains defensible",),
            owner="user:carlos",
            status=GoalStatus.BLOCKED,
            deadline=NOW + timedelta(days=30),
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
            origin=origin,
            intent_authority=authority,
            author="user:carlos",
            revision_reason="represent a recoverable blockage",
        )
        worker = EndogenousShadowWorker(kernel)
        selection = await worker.run_scan(
            budget=budget(activities=1),
            started_at=NOW + timedelta(hours=1),
        )
        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertTrue(selection.selected_activity_ids)
        projection = await worker.current_projection()
        self.assertTrue(
            all(
                activity.governing_intent_refs
                == (GoverningIntentRef("goal:endogenous", blocked.revision_id),)
                for activity in projection.activities_for_epoch(selection.epoch_id)
            )
        )
        await kernel.stop()

    async def test_expired_epoch_is_durably_terminal(self) -> None:
        clock = MutableClock(NOW)
        kernel = NoemaKernel()
        await build_strategy(kernel, clock)
        worker = EndogenousShadowWorker(kernel)
        selection = await worker.run_scan(
            budget=budget(activities=1),
            started_at=NOW + timedelta(hours=1),
            expires_at=NOW + timedelta(hours=1, seconds=1),
        )
        self.assertIsNotNone(selection)
        assert selection is not None
        expired = await worker.expire_epochs(at=NOW + timedelta(hours=1, seconds=2))
        self.assertEqual(tuple(value.epoch_id for value in expired), (selection.epoch_id,))
        projection = await worker.current_projection()
        self.assertIs(projection.epoch_status(selection.epoch_id), DreamEpochStatus.EXPIRED)
        await kernel.stop()
