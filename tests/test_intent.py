from __future__ import annotations

import ast
import json
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from noema import (
    AssistanceEnvelope,
    AuthorityLevel,
    CapabilityManifest,
    Commitment,
    CommitmentClosureReason,
    CommitmentStatus,
    CoverageDisposition,
    DurableWorkCoordinator,
    Event,
    ExecutionLocus,
    ExternalWorkstream,
    FakePlanner,
    GoalKind,
    GoalRevision,
    GoalStatus,
    IntentAuthority,
    IntentAuthorityScope,
    IntentStewardCoordinator,
    InterventionLevel,
    NoemaKernel,
    OriginKind,
    OriginProvenance,
    OutcomeActor,
    OutcomeNode,
    OutcomeRoleAssignment,
    PortfolioSignals,
    StaticStrategicTrust,
    StrategicProjection,
    StrategicValidator,
    WorkNode,
    WorkNodeKind,
    WorkOrder,
)

NOW = datetime(2026, 8, 31, 15, 0, tzinfo=UTC)


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


def signals(*, wip: int = 0) -> PortfolioSignals:
    return PortfolioSignals(
        expected_goal_value=0.9,
        commitment_strength=1.0,
        urgency=0.7,
        critical_path_pressure=0.6,
        success_estimate=0.8,
        cost=2.0,
        coordination_cost=0.2,
        context_affinity=0.9,
        verification_capacity=0.5,
        wip=wip,
        scarce_competence_pressure=0.3,
        future_information_access_requirements=("domain:career-private",),
    )


class LegacyStrategicMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_exact_head_evidence_accepts_durable_sequence_gaps(self) -> None:
        origin, authority, _trust = user_security()
        projection = StrategicProjection()
        projection.apply(Event("unrelated.event", "test", {}, timestamp=NOW).with_sequence(1))
        revision = GoalRevision.create(
            goal_id="goal:after-gap",
            version=1,
            description="Remain valid after a rolled-back database insert",
            priority=0.8,
            utility=0.8,
            success_criteria=("exact prior head is preserved",),
            owner="user:carlos",
            status=GoalStatus.ACTIVE,
            kind=GoalKind.USER_AUTHORED,
            origin=origin,
            intent_authority=authority,
            based_on_event_cursor=1,
            author="user:carlos",
            revision_reason="sequence-gap regression",
            recorded_at=NOW + timedelta(minutes=1),
        )
        event = replace(
            revision.to_event(source="intent:coordinator"),
            metadata={"validated_at_event_cursor": 1},
        ).with_sequence(3)

        self.assertTrue(projection.apply(event))
        self.assertEqual(projection.event_cursor, 3)
        self.assertEqual(projection.current_goal_revision("goal:after-gap"), revision)

    async def test_legacy_goal_and_commitment_history_upcasts_deterministically(self) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        await kernel.emit(
            Event(
                "goal.created",
                "legacy",
                {
                    "id": "goal:legacy",
                    "description": "Ship safely",
                    "priority": 0.6,
                },
                timestamp=NOW,
            )
        )
        await kernel.emit(
            Event(
                "goal.updated",
                "legacy",
                {"id": "goal:legacy", "priority": 0.9},
                timestamp=NOW + timedelta(minutes=1),
            )
        )
        await kernel.emit(
            Event(
                "commitment.created",
                "legacy",
                {
                    "id": "commitment:legacy",
                    "description": "Prepare release",
                    "owner": "user:carlos",
                    "status": "in_progress",
                },
                timestamp=NOW + timedelta(minutes=2),
            )
        )
        await kernel.emit(
            Event(
                "commitment.failed",
                "legacy",
                {"id": "commitment:legacy"},
                timestamp=NOW + timedelta(minutes=3),
            )
        )

        raw = await kernel.history()
        self.assertTrue(all(event.schema_version == 1 for event in raw))
        normalized = tuple(kernel.schemas.normalize(event) for event in raw)
        first = StrategicProjection()
        second = StrategicProjection()
        first.rebuild(normalized)
        second.rebuild(normalized)

        self.assertEqual(first.goal_revisions, second.goal_revisions)
        self.assertEqual(len(first.goal_history("goal:legacy")), 2)
        current_goal = first.current_goal_revision("goal:legacy")
        self.assertIsNotNone(current_goal)
        assert current_goal is not None
        self.assertEqual(current_goal.priority, 0.9)
        self.assertIs(current_goal.kind, GoalKind.LEGACY_UNCLASSIFIED)
        self.assertIs(current_goal.origin.kind, OriginKind.LEGACY_UNVERIFIED)

        commitment = first.commitment("commitment:legacy")
        self.assertIsNotNone(commitment)
        assert commitment is not None
        self.assertIs(commitment.status, CommitmentStatus.CLOSED)
        self.assertIs(commitment.closure_reason, CommitmentClosureReason.FAILED)
        self.assertIsNot(commitment.closure_reason, CommitmentClosureReason.BREACHED)
        self.assertEqual(
            first.commitment_history("commitment:legacy"),
            second.commitment_history("commitment:legacy"),
        )

        snapshot = await kernel.snapshot()
        self.assertIs(snapshot.commitments["commitment:legacy"].status, CommitmentStatus.CLOSED)
        self.assertIs(
            snapshot.commitments["commitment:legacy"].closure_reason,
            CommitmentClosureReason.FAILED,
        )
        await kernel.stop()


class IntentOutcomeAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_forged_user_origin_and_closed_commitment_mutation_fail(self) -> None:
        origin, authority, _trust = user_security()
        other_origin = OriginProvenance(
            provenance_id="origin:user:other",
            kind=OriginKind.USER,
            principal_id="user:other",
            authentication_ref="authn:local-user-session:other",
        )
        other_authority = IntentAuthority(
            authority_id="intent-authority:user:other",
            principal_id="user:other",
            scope=IntentAuthorityScope.USER,
            allowed_goal_kinds=(GoalKind.USER_AUTHORED,),
            goal_refs=(),
            provenance_ref=other_origin.provenance_id,
        )
        proposal_only = IntentAuthority(
            authority_id="intent-authority:user:carlos:proposal-only",
            principal_id="user:carlos",
            scope=IntentAuthorityScope.PROPOSE,
            allowed_goal_kinds=(GoalKind.USER_AUTHORED,),
            goal_refs=(),
            provenance_ref=origin.provenance_id,
        )
        trust = StaticStrategicTrust(
            (origin, other_origin),
            (authority, other_authority, proposal_only),
        )
        kernel = NoemaKernel()
        steward = IntentStewardCoordinator(
            kernel,
            validator=StrategicValidator(trust),
            clock=MutableClock(NOW),
        )
        forged = OriginProvenance(
            provenance_id="origin:forged-by-agent",
            kind=OriginKind.USER,
            principal_id="user:carlos",
            authentication_ref="agent-asserted-user-session",
        )
        with self.assertRaisesRegex(ValueError, "not authenticated"):
            await steward.record_goal_revision(
                goal_id="goal:forged",
                description="agent pretends this is user intent",
                priority=1.0,
                utility=1.0,
                success_criteria=("must never become canonical",),
                owner="user:carlos",
                status=GoalStatus.ACTIVE,
                kind=GoalKind.USER_AUTHORED,
                origin=forged,
                intent_authority=authority,
                author="user:carlos",
                revision_reason="forged provenance attempt",
            )
        with self.assertRaisesRegex(ValueError, "different principals"):
            await steward.record_goal_revision(
                goal_id="goal:cross-principal",
                description="compose two valid credentials into invalid authority",
                priority=1.0,
                utility=1.0,
                success_criteria=("must never become canonical",),
                owner="user:carlos",
                status=GoalStatus.ACTIVE,
                kind=GoalKind.USER_AUTHORED,
                origin=origin,
                intent_authority=other_authority,
                author="user:other",
                revision_reason="cross-principal credential composition",
            )
        with self.assertRaisesRegex(ValueError, "proposal-only"):
            await steward.record_goal_revision(
                goal_id="goal:proposal-only",
                description="proposal authority cannot make canonical intent",
                priority=1.0,
                utility=1.0,
                success_criteria=("must never become canonical",),
                owner="user:carlos",
                status=GoalStatus.ACTIVE,
                kind=GoalKind.USER_AUTHORED,
                origin=origin,
                intent_authority=proposal_only,
                author="user:carlos",
                revision_reason="proposal-only admission attempt",
            )
        self.assertEqual(await kernel.history(), [])

        await kernel.emit(
            Event(
                "commitment.created",
                "legacy",
                {
                    "id": "commitment:closed",
                    "description": "legacy obligation",
                    "owner": "user:carlos",
                },
                timestamp=NOW,
            )
        )
        await kernel.emit(
            Event(
                "commitment.completed",
                "legacy",
                {"id": "commitment:closed"},
                timestamp=NOW + timedelta(minutes=1),
            )
        )
        with self.assertRaisesRegex(ValueError, "closed commitment"):
            await steward.transition_commitment(
                "commitment:closed",
                to_state=CommitmentStatus.ACTIVE,
                closure_reason=None,
                intent_authority=authority,
                author="user:carlos",
                reason="illegal resurrection",
            )
        await steward._reload()
        closed = steward.projection.commitment("commitment:closed")
        self.assertIsNotNone(closed)
        assert closed is not None
        self.assertIs(closed.status, CommitmentStatus.CLOSED)
        self.assertIs(closed.closure_reason, CommitmentClosureReason.FULFILLED)
        await kernel.stop()

    async def test_deterministic_stewardship_vertical_slice(self) -> None:
        clock = MutableClock(NOW)
        origin, authority, trust = user_security()
        kernel = NoemaKernel()
        steward = IntentStewardCoordinator(
            kernel,
            validator=StrategicValidator(trust, wip_limit=4),
            clock=clock,
        )

        goal_v1 = await steward.record_goal_revision(
            goal_id="goal:career",
            description="Earn a promotion without surrendering the human decisions",
            priority=0.8,
            utility=1.0,
            success_criteria=("promotion outcome is decided",),
            owner="user:carlos",
            status=GoalStatus.ACTIVE,
            kind=GoalKind.USER_AUTHORED,
            origin=origin,
            intent_authority=authority,
            author="user:carlos",
            revision_reason="initial authenticated user intent",
        )
        clock.advance()
        nodes = (
            OutcomeNode(
                "hypothetical-networking",
                "Develop a wider network if later evidence supports it",
                ("networking option is assessed",),
                confidence=0.4,
            ),
            OutcomeNode(
                "human-interview",
                "User completes the identity-bound interview",
                ("interview is completed by the user",),
                approximate_dependencies=("agent-preparation",),
                confidence=0.9,
            ),
            OutcomeNode(
                "agent-preparation",
                "Prepare evidence and interview options",
                ("preparation brief is ready",),
                confidence=0.8,
            ),
        )
        roadmap_v1 = await steward.record_roadmap_revision(
            roadmap_id="roadmap:career",
            governing_goal_revision_ids=(goal_v1.revision_id,),
            outcome_nodes=nodes,
            assumptions=("promotion cycle remains open",),
            confidence=0.7,
            success_criteria=("promotion path remains aligned",),
            resource_envelope={"attention_hours": 8.0},
            intent_authority=authority,
            author="user:carlos",
            revision_reason="initial outcome hypothesis",
        )
        with self.assertRaises(FrozenInstanceError):
            goal_v1.priority = 0.1  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            roadmap_v1.version = 99  # type: ignore[misc]
        with self.assertRaises(TypeError):
            roadmap_v1.resource_envelope["attention_hours"] = 99.0  # type: ignore[index]

        clock.advance()
        support_roles = OutcomeRoleAssignment.create(
            outcome_ref=f"{roadmap_v1.revision_id}#agent-preparation",
            outcome_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            decision_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            executor=OutcomeActor("agent:noema", ExecutionLocus.AGENT),
            verifier=OutcomeActor("user:carlos", ExecutionLocus.USER),
            recorded_at=clock(),
        )
        await steward.record_outcome_roles(support_roles)
        clock.advance()
        human_roles = OutcomeRoleAssignment.create(
            outcome_ref=f"{roadmap_v1.revision_id}#human-interview",
            outcome_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            decision_owner=OutcomeActor("employer:panel", ExecutionLocus.EXTERNAL_HUMAN),
            executor=OutcomeActor("user:carlos", ExecutionLocus.USER),
            verifier=OutcomeActor("employer:panel", ExecutionLocus.EXTERNAL_HUMAN),
            recorded_at=clock(),
        )
        await steward.record_outcome_roles(human_roles)
        clock.advance()
        envelope = AssistanceEnvelope.create(
            role_assignment_id=human_roles.assignment_id,
            maximum_intervention=InterventionLevel.PREPARE,
            identity_bound=True,
            physical_presence_required=True,
            relationship_bound=True,
            institutional_restrictions=("employer decides",),
            user_development_value=1.0,
            permitted_agent_support=("research", "practice", "draft notes"),
            required_human_work=("attend interview", "make personal claims"),
            checkpoints=("user approves preparation brief",),
            reversible=True,
            risk_limit=0.4,
            privacy_limit=0.3,
            attention_budget=3.0,
            recorded_at=clock(),
        )
        await steward.record_assistance_envelope(envelope)

        clock.advance()
        future = Commitment(
            id="commitment:interview",
            description="Complete the interview when scheduled",
            owner="user:carlos",
            priority=0.9,
            status=CommitmentStatus.ACCEPTED,
            deadline=NOW + timedelta(days=30),
            created_at=clock(),
            updated_at=clock(),
            governing_goal_refs=("goal:career",),
            roadmap_revision_id=roadmap_v1.revision_id,
            outcome_node_id="human-interview",
            role_assignment_id=human_roles.assignment_id,
            assistance_envelope_id=envelope.envelope_id,
        )
        await steward.record_commitment(future, intent_authority=authority)
        future_coverage = await steward.coverage(future.id)
        self.assertIs(future_coverage.disposition, CoverageDisposition.INACTIVE)
        with self.assertRaisesRegex(ValueError, "not yet eligible"):
            await steward.propose_work_for_commitment(
                future.id,
                purpose="premature interview execution",
                desired_outcome="interview done",
                success_criteria=("interview done",),
                portfolio_signals=signals(),
            )

        clock.advance()
        activation_due = Commitment(
            id="commitment:activation-due",
            description="Prepare prerequisites at the activation boundary",
            owner="user:carlos",
            priority=0.7,
            status=CommitmentStatus.ACCEPTED,
            deadline=NOW + timedelta(days=14),
            created_at=clock(),
            updated_at=clock(),
            governing_goal_refs=("goal:career",),
            roadmap_revision_id=roadmap_v1.revision_id,
            outcome_node_id="human-interview",
            role_assignment_id=human_roles.assignment_id,
            assistance_envelope_id=envelope.envelope_id,
            activation_due_at=clock(),
        )
        await steward.record_commitment(activation_due, intent_authority=authority)
        due_proposal = await steward.propose_work_for_commitment(
            activation_due.id,
            purpose="prepare activation prerequisites",
            desired_outcome="activation prerequisites are ready",
            success_criteria=("activation prerequisites are ready",),
            portfolio_signals=signals(),
        )
        with self.assertRaisesRegex(ValueError, "requires ACTIVE"):
            await steward.admit_work_order(due_proposal.proposal_id)

        clock.advance()
        active = Commitment(
            id="commitment:preparation",
            description="Prepare the promotion evidence brief",
            owner="user:carlos",
            priority=0.8,
            status=CommitmentStatus.ACTIVE,
            deadline=NOW + timedelta(days=7),
            created_at=clock(),
            updated_at=clock(),
            governing_goal_refs=("goal:career",),
            roadmap_revision_id=roadmap_v1.revision_id,
            outcome_node_id="agent-preparation",
            role_assignment_id=support_roles.assignment_id,
        )
        await steward.record_commitment(active, intent_authority=authority)
        self.assertEqual(len(steward.projection.commitments), 3)
        self.assertEqual(
            {value.outcome_node_id for value in steward.projection.commitments},
            {"human-interview", "agent-preparation"},
        )
        self.assertNotIn(
            "hypothetical-networking",
            {value.outcome_node_id for value in steward.projection.commitments},
        )

        clock.advance()
        proposal = await steward.propose_work_for_commitment(
            active.id,
            purpose="prepare promotion evidence",
            desired_outcome="a bounded preparation brief exists",
            success_criteria=("preparation brief is ready",),
            portfolio_signals=signals(wip=1),
        )
        self.assertIs(
            (await steward.coverage(active.id)).disposition,
            CoverageDisposition.PROPOSED,
        )
        order = await steward.admit_work_order(proposal.proposal_id)
        self.assertIn(f"commitment:{active.id}", order.created_from)
        self.assertIs(
            (await steward.coverage(active.id)).disposition,
            CoverageDisposition.COVERED,
        )

        work_clock = MutableClock(clock())
        planner = FakePlanner(
            nodes=(
                WorkNode(
                    "prepare",
                    WorkNodeKind.PREPARE,
                    "prepare bounded evidence brief",
                    ("writing",),
                    ("preparation brief is ready",),
                ),
            ),
            dependencies=(),
            assumptions=("commitment remains active",),
            done_conditions=("preparation brief is ready",),
            replan_event_types=("intent.commitment_transitioned",),
            clock=work_clock,
        )
        work = DurableWorkCoordinator(kernel, planner=planner, clock=work_clock)
        await work.record_manifest(
            CapabilityManifest.create(
                agent_id="agent:noema",
                capabilities=("writing",),
                recorded_at=work_clock(),
            )
        )
        graph = await work.plan(order.work_order_id)
        self.assertEqual(graph.work_order_id, order.work_order_id)

        for index, direct_origin in enumerate(
            (
                "user-instruction:investigate-now",
                "incident:api-down",
                "external-obligation:tax-deadline",
                "endogenous-inquiry:stale-risk",
            )
        ):
            direct = WorkOrder.create(
                purpose=f"respond to direct origin {index}",
                governing_goal_refs=("goal:direct-work",),
                created_from=(direct_origin,),
                priority=1.0,
                desired_outcome=f"direct work {index} is bounded",
                success_criteria=(f"direct assessment {index} exists",),
                created_at=work_clock(),
            )
            recorded_direct = await work.record_work_order(direct)
            self.assertEqual(recorded_direct.work_order_id, direct.work_order_id)
            self.assertNotIn("commitment:", " ".join(direct.created_from))

        clock.advance()
        external = ExternalWorkstream.create(
            workstream_id="external:promotion-cycle",
            source_of_truth_id="employer:hr-system",
            observed_roadmap_ref="employer-roadmap:promotion-2026",
            provenance_refs=("observation:hr-window",),
            valid_at=clock(),
            recorded_at=clock(),
            confidence=0.9,
            freshness_expires_at=clock() + timedelta(days=2),
            user_role="candidate",
            noema_role="preparation support",
            support_commitment_refs=(active.id,),
            support_required=True,
        )
        await steward.observe_external_workstream(external)
        self.assertTrue((await steward.coverage(active.id)).external_support_required)
        self.assertTrue((await steward.roadmap_health("roadmap:career")).review_required)
        bad_external = ExternalWorkstream.create(
            workstream_id="external:bad-copy",
            source_of_truth_id="external:system",
            observed_roadmap_ref=graph.graph_id,
            provenance_refs=("observation:bad",),
            valid_at=clock(),
            recorded_at=clock(),
            confidence=1.0,
            freshness_expires_at=clock() + timedelta(hours=1),
            user_role="observer",
            noema_role="support",
            support_commitment_refs=(),
            support_required=False,
        )
        with self.assertRaisesRegex(ValueError, "work graph"):
            await steward.observe_external_workstream(bad_external)

        clock.advance()
        goal_v2 = await steward.record_goal_revision(
            goal_id="goal:career",
            description="Prioritize sustainable promotion readiness",
            priority=1.0,
            utility=1.0,
            success_criteria=("promotion outcome and sustainable workload are decided",),
            owner="user:carlos",
            status=GoalStatus.ACTIVE,
            kind=GoalKind.USER_AUTHORED,
            origin=origin,
            intent_authority=authority,
            author="user:carlos",
            revision_reason="user reprioritized sustainable workload",
        )
        self.assertEqual(len(steward.projection.goal_history("goal:career")), 2)
        stale_health = await steward.roadmap_health("roadmap:career")
        self.assertEqual(stale_health.goal_alignment.value, "needs_review")

        clock.advance()
        roadmap_v2 = await steward.record_roadmap_revision(
            roadmap_id="roadmap:career",
            governing_goal_revision_ids=(goal_v2.revision_id,),
            outcome_nodes=nodes,
            assumptions=("promotion cycle remains open", "workload remains sustainable"),
            confidence=0.75,
            success_criteria=("promotion path and workload remain aligned",),
            resource_envelope={"attention_hours": 6.0},
            intent_authority=authority,
            author="user:carlos",
            revision_reason="respond to the goal reprioritization",
        )
        self.assertEqual(len(steward.projection.roadmap_history("roadmap:career")), 2)
        self.assertNotEqual(roadmap_v1.revision_id, roadmap_v2.revision_id)

        clock.advance()
        suspension = await steward.transition_commitment(
            active.id,
            to_state=CommitmentStatus.SUSPENDED,
            closure_reason=None,
            intent_authority=authority,
            author="user:carlos",
            reason="reassess against changed goal",
        )
        suspension_event = next(
            event
            for event in await kernel.history()
            if event.id == f"commitment-transitioned:{suspension.transition_id}"
        )
        invalidated = await work.invalidate_for(
            suspension_event,
            reason="active strategic obligation was suspended",
            invalidated_at=clock(),
        )
        self.assertEqual(tuple(value.graph_id for value in invalidated), (graph.graph_id,))
        self.assertFalse(work.projection.graph_is_active(graph.graph_id))
        with self.assertRaisesRegex(ValueError, "reactivation requires"):
            await steward.transition_commitment(
                active.id,
                to_state=CommitmentStatus.ACTIVE,
                closure_reason=None,
                intent_authority=authority,
                author="user:carlos",
                reason="blind resume",
            )
        clock.advance()
        await steward.transition_commitment(
            active.id,
            to_state=CommitmentStatus.ACTIVE,
            closure_reason=None,
            intent_authority=authority,
            author="user:carlos",
            reason="reactivate after current assessment",
            reactivation_roadmap_revision_id=roadmap_v2.revision_id,
            reorientation_evidence_refs=("orientation:career-current",),
        )

        history = await kernel.history()
        replayed = StrategicProjection()
        replayed.rebuild(kernel.schemas.normalize(event) for event in history)
        self.assertEqual(replayed.goal_revisions, steward.projection.goal_revisions)
        self.assertEqual(replayed.roadmap_revisions, steward.projection.roadmap_revisions)
        self.assertEqual(replayed.commitments, steward.projection.commitments)
        semantic = {
            "goals": [value.to_dict() for value in replayed.goal_revisions],
            "roadmaps": [value.to_dict() for value in replayed.roadmap_revisions],
            "commitments": [value.id + ":" + value.status.value for value in replayed.commitments],
        }
        current_semantic = {
            "goals": [value.to_dict() for value in steward.projection.goal_revisions],
            "roadmaps": [value.to_dict() for value in steward.projection.roadmap_revisions],
            "commitments": [
                value.id + ":" + value.status.value for value in steward.projection.commitments
            ],
        }
        self.assertEqual(
            json.dumps(semantic, sort_keys=True, separators=(",", ":")),
            json.dumps(current_semantic, sort_keys=True, separators=(",", ":")),
        )
        await kernel.stop()

    async def test_strategic_cas_reloads_and_rejects_concurrent_goal_mutation(self) -> None:
        clock = MutableClock(NOW)
        origin, authority, trust = user_security()
        kernel = NoemaKernel()
        validator = StrategicValidator(trust)
        first = IntentStewardCoordinator(kernel, validator=validator, clock=clock)
        second = IntentStewardCoordinator(kernel, validator=validator, clock=clock)
        await first.record_goal_revision(
            goal_id="goal:race",
            description="original",
            priority=0.5,
            utility=1.0,
            success_criteria=("done",),
            owner="user:carlos",
            status=GoalStatus.ACTIVE,
            kind=GoalKind.USER_AUTHORED,
            origin=origin,
            intent_authority=authority,
            author="user:carlos",
            revision_reason="initial",
        )
        original_emit_if_head = kernel.emit_if_head
        injected = False

        async def racing_emit(event: Event, *, expected_head_sequence: int) -> Event:
            nonlocal injected
            if not injected and event.type == "intent.goal_revision_recorded":
                injected = True
                await second.record_goal_revision(
                    goal_id="goal:race",
                    description="concurrent canonical revision",
                    priority=0.8,
                    utility=1.0,
                    success_criteria=("done",),
                    owner="user:carlos",
                    status=GoalStatus.ACTIVE,
                    kind=GoalKind.USER_AUTHORED,
                    origin=origin,
                    intent_authority=authority,
                    author="user:carlos",
                    revision_reason="concurrent update",
                )
            return await original_emit_if_head(
                event,
                expected_head_sequence=expected_head_sequence,
            )

        kernel.emit_if_head = racing_emit  # type: ignore[method-assign]
        with self.assertRaisesRegex(ValueError, "changed after"):
            await first.record_goal_revision(
                goal_id="goal:race",
                description="stale competing revision",
                priority=0.7,
                utility=1.0,
                success_criteria=("done",),
                owner="user:carlos",
                status=GoalStatus.ACTIVE,
                kind=GoalKind.USER_AUTHORED,
                origin=origin,
                intent_authority=authority,
                author="user:carlos",
                revision_reason="losing update",
            )
        await first._reload()
        current = first.projection.current_goal_revision("goal:race")
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.description, "concurrent canonical revision")
        self.assertEqual(len(first.projection.goal_history("goal:race")), 2)
        await kernel.stop()


class IntentArchitectureFitnessTests(unittest.TestCase):
    def test_intent_core_has_no_deferred_or_effect_plane_dependencies(self) -> None:
        root = Path(__file__).parents[1] / "src" / "noema" / "intent"
        forbidden_modules = {
            "adapters",
            "agent",
            "capabilities",
            "models",
            "reasoning",
            "scheduler",
        }
        forbidden_names = {
            "LLMPlanSynthesizer",
            "RDDLPlanner",
            "MDPPlanner",
            "OversightAllocator",
            "HabitForge",
            "SkillForge",
            "WorkflowDSL",
            "InformationPolicy",
            "ArtifactStore",
            "DisclosureDecision",
        }
        violations: list[str] = []
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for name in forbidden_names:
                if name in source:
                    violations.append(f"{path.name} references deferred {name}")
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    module_root = node.module.split(".")[0]
                    if node.level >= 2 and module_root in forbidden_modules:
                        violations.append(f"{path.name} imports {node.module}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in {"authorize", "dispatch", "execute", "invoke"}:
                        violations.append(f"{path.name} calls {node.func.attr}")
        self.assertEqual(violations, [])

    def test_authority_roles_and_assistance_remain_independent_types(self) -> None:
        self.assertFalse(isinstance(AuthorityLevel.PROPOSE, IntentAuthority))
        role_fields = {value.name for value in fields(OutcomeRoleAssignment)}
        self.assertEqual(
            {"outcome_owner", "decision_owner", "executor", "verifier"} - role_fields,
            set(),
        )
        envelope_fields = {value.name for value in fields(AssistanceEnvelope)}
        self.assertTrue(
            {"outcome_owner", "decision_owner", "executor", "verifier"}.isdisjoint(envelope_fields)
        )
        self.assertIn("role_assignment_id", envelope_fields)
