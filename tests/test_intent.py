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
    RoadmapRevision,
    StaticStrategicTrust,
    StrategicProjection,
    StrategicValidator,
    WorkNode,
    WorkNodeKind,
    WorkOrder,
    WorkOrderProposal,
    WorkProposalEligibility,
)
from noema.intent.models import commitment_recorded_event

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
            deadline=None,
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
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

        registry = NoemaKernel().schemas
        legacy = StrategicProjection()
        legacy.apply(Event("unrelated.one", "test", {}, timestamp=NOW).with_sequence(2))
        legacy_goal = registry.normalize(
            Event(
                "goal.created",
                "legacy",
                {"id": "goal:legacy-gap", "description": "Preserve actual head"},
                timestamp=NOW + timedelta(minutes=2),
            ).with_sequence(5)
        )
        legacy.apply(legacy_goal)
        migrated_goal = legacy.current_goal_revision("goal:legacy-gap")
        self.assertIsNotNone(migrated_goal)
        assert migrated_goal is not None
        self.assertEqual(migrated_goal.based_on_event_cursor, 2)

        legacy_commitment = registry.normalize(
            Event(
                "commitment.created",
                "legacy",
                {
                    "id": "commitment:legacy-gap",
                    "description": "Gap-safe transition",
                    "owner": "legacy",
                },
                timestamp=NOW + timedelta(minutes=3),
            ).with_sequence(8)
        )
        legacy.apply(legacy_commitment)
        legacy.apply(Event("unrelated.two", "test", {}, timestamp=NOW).with_sequence(10))
        legacy_failed = registry.normalize(
            Event(
                "commitment.failed",
                "legacy",
                {"id": "commitment:legacy-gap"},
                timestamp=NOW + timedelta(minutes=4),
            ).with_sequence(13)
        )
        legacy.apply(legacy_failed)
        transitions = legacy.commitment_transitions("commitment:legacy-gap")
        self.assertEqual(transitions[-1].based_on_event_cursor, 10)

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
                deadline=None,
                kind=GoalKind.USER_AUTHORED,
                governing_goal_refs=(),
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
                deadline=None,
                kind=GoalKind.USER_AUTHORED,
                governing_goal_refs=(),
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
                deadline=None,
                kind=GoalKind.USER_AUTHORED,
                governing_goal_refs=(),
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
            deadline=NOW + timedelta(days=60),
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
            origin=origin,
            intent_authority=authority,
            author="user:carlos",
            revision_reason="initial authenticated user intent",
        )
        self.assertEqual(goal_v1.deadline, NOW + timedelta(days=60))
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
                (
                    "preparation brief is ready",
                    "evidence references are checked",
                ),
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
                intervention=InterventionLevel.PREPARE,
                declared_agent_support=("research",),
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
            intervention=InterventionLevel.PREPARE,
            declared_agent_support=("research",),
            portfolio_signals=signals(),
        )
        with self.assertRaisesRegex(ValueError, "intervention limit"):
            await steward.propose_work_for_commitment(
                activation_due.id,
                purpose="conduct the identity-bound interview",
                desired_outcome="agent substitutes for the user",
                success_criteria=("interview is completed by the user",),
                intervention=InterventionLevel.ACT,
                declared_agent_support=("research",),
                portfolio_signals=signals(wip=1),
            )
        with self.assertRaisesRegex(ValueError, "outside the assistance envelope"):
            await steward.propose_work_for_commitment(
                activation_due.id,
                purpose="perform undeclared assistance",
                desired_outcome="unsupported work slips through",
                success_criteria=("must never become canonical",),
                intervention=InterventionLevel.PREPARE,
                declared_agent_support=("impersonation",),
                portfolio_signals=signals(wip=1),
            )
        clock.advance()
        identity_envelope = AssistanceEnvelope.create(
            role_assignment_id=human_roles.assignment_id,
            maximum_intervention=InterventionLevel.ACT,
            identity_bound=True,
            physical_presence_required=True,
            relationship_bound=True,
            institutional_restrictions=("employer authenticates the candidate",),
            user_development_value=1.0,
            permitted_agent_support=("conduct interview",),
            required_human_work=("personally attend interview",),
            checkpoints=("user remains the authenticated participant",),
            reversible=False,
            risk_limit=0.2,
            privacy_limit=0.2,
            attention_budget=2.0,
            recorded_at=clock(),
        )
        await steward.record_assistance_envelope(identity_envelope)
        clock.advance()
        identity_bound_active = Commitment(
            id="commitment:identity-bound-interview",
            description="User personally conducts the identity-bound interview",
            owner="user:carlos",
            priority=1.0,
            status=CommitmentStatus.ACTIVE,
            deadline=NOW + timedelta(days=14),
            created_at=clock(),
            updated_at=clock(),
            governing_goal_refs=("goal:career",),
            roadmap_revision_id=roadmap_v1.revision_id,
            outcome_node_id="human-interview",
            role_assignment_id=human_roles.assignment_id,
            assistance_envelope_id=identity_envelope.envelope_id,
        )
        await steward.record_commitment(
            identity_bound_active,
            intent_authority=authority,
        )
        with self.assertRaisesRegex(ValueError, "identity-bound"):
            await steward.propose_work_for_commitment(
                identity_bound_active.id,
                purpose="impersonate the user in the interview",
                desired_outcome="agent acts in the user's identity",
                success_criteria=("interview is completed by the user",),
                intervention=InterventionLevel.ACT,
                declared_agent_support=("conduct interview",),
                portfolio_signals=signals(wip=1),
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
        self.assertEqual(len(steward.projection.commitments), 4)
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
            intervention=InterventionLevel.PREPARE,
            declared_agent_support=("writing",),
            portfolio_signals=signals(wip=1),
        )
        self.assertIs(
            (await steward.coverage(active.id)).disposition,
            CoverageDisposition.PROPOSED,
        )
        order = await steward.admit_work_order(proposal.proposal_id)
        self.assertIn(f"commitment:{active.id}", order.created_from)
        partial_coverage = await steward.coverage(active.id)
        self.assertIs(partial_coverage.disposition, CoverageDisposition.UNCOVERED)
        self.assertEqual(
            partial_coverage.uncovered_criteria,
            ("evidence references are checked",),
        )
        clock.advance()
        evidence_proposal = await steward.propose_work_for_commitment(
            active.id,
            purpose="verify promotion evidence references",
            desired_outcome="all evidence references are checked",
            success_criteria=("evidence references are checked",),
            intervention=InterventionLevel.PREPARE,
            declared_agent_support=("verification",),
            portfolio_signals=signals(wip=1),
        )
        await steward.admit_work_order(evidence_proposal.proposal_id)
        complete_coverage = await steward.coverage(active.id)
        self.assertIs(complete_coverage.disposition, CoverageDisposition.COVERED)
        self.assertEqual(
            complete_coverage.covered_criteria,
            (
                "preparation brief is ready",
                "evidence references are checked",
            ),
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
            deadline=NOW + timedelta(days=45),
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
            origin=origin,
            intent_authority=authority,
            author="user:carlos",
            revision_reason="user reprioritized sustainable workload",
        )
        self.assertEqual(len(steward.projection.goal_history("goal:career")), 2)
        self.assertEqual(goal_v2.deadline, NOW + timedelta(days=45))
        self.assertEqual(
            (await kernel.snapshot()).goals["goal:career"].deadline,
            NOW + timedelta(days=45),
        )
        stale_health = await steward.roadmap_health("roadmap:career")
        self.assertEqual(stale_health.goal_alignment.value, "needs_review")
        with self.assertRaisesRegex(ValueError, "current governing goal"):
            await steward.record_roadmap_revision(
                roadmap_id="roadmap:known-stale",
                governing_goal_revision_ids=(goal_v1.revision_id,),
                outcome_nodes=nodes,
                assumptions=("stale intent is acceptable",),
                confidence=0.1,
                success_criteria=("must never become canonical",),
                resource_envelope={"attention_hours": 1.0},
                intent_authority=authority,
                author="user:carlos",
                revision_reason="known-stale roadmap attempt",
            )
        with self.assertRaisesRegex(ValueError, "stale governing intent"):
            await steward.propose_work_for_commitment(
                active.id,
                purpose="create new work from stale intent",
                desired_outcome="must never become canonical",
                success_criteria=("must never become canonical",),
                intervention=InterventionLevel.PREPARE,
                declared_agent_support=("writing",),
                portfolio_signals=signals(wip=1),
            )

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
        stale_commitment = Commitment(
            id="commitment:stale-roadmap",
            description="must not bind a superseded roadmap",
            owner="user:carlos",
            status=CommitmentStatus.ACCEPTED,
            created_at=clock(),
            updated_at=clock(),
            governing_goal_refs=("goal:career",),
            roadmap_revision_id=roadmap_v1.revision_id,
            outcome_node_id="agent-preparation",
            role_assignment_id=support_roles.assignment_id,
        )
        with self.assertRaisesRegex(ValueError, "stale roadmap"):
            await steward.record_commitment(
                stale_commitment,
                intent_authority=authority,
            )

        clock.advance()
        support_roles_v2 = OutcomeRoleAssignment.create(
            outcome_ref=f"{roadmap_v2.revision_id}#agent-preparation",
            outcome_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            decision_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            executor=OutcomeActor("agent:noema", ExecutionLocus.AGENT),
            verifier=OutcomeActor("user:carlos", ExecutionLocus.USER),
            recorded_at=clock(),
        )
        await steward.record_outcome_roles(support_roles_v2)

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
        with self.assertRaisesRegex(ValueError, "roles do not target"):
            await steward.transition_commitment(
                active.id,
                to_state=CommitmentStatus.ACTIVE,
                closure_reason=None,
                intent_authority=authority,
                author="user:carlos",
                reason="reuse stale revision-scoped roles",
                reactivation_roadmap_revision_id=roadmap_v2.revision_id,
                reactivation_role_assignment_id=support_roles.assignment_id,
                reorientation_evidence_refs=("orientation:career-current",),
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
            reactivation_role_assignment_id=support_roles_v2.assignment_id,
            reorientation_evidence_refs=("orientation:career-current",),
        )
        reactivated = steward.projection.commitment(active.id)
        self.assertIsNotNone(reactivated)
        assert reactivated is not None
        self.assertEqual(reactivated.roadmap_revision_id, roadmap_v2.revision_id)
        self.assertEqual(reactivated.role_assignment_id, support_roles_v2.assignment_id)
        reactivated_coverage = await steward.coverage(active.id)
        self.assertIs(reactivated_coverage.disposition, CoverageDisposition.UNCOVERED)
        self.assertEqual(reactivated_coverage.work_proposal_ids, ())
        self.assertEqual(reactivated_coverage.admitted_work_order_ids, ())
        self.assertEqual(
            reactivated_coverage.uncovered_criteria,
            (
                "preparation brief is ready",
                "evidence references are checked",
            ),
        )

        clock.advance()
        reactivated_proposal = await steward.propose_work_for_commitment(
            active.id,
            purpose="establish coverage for the reoriented outcome",
            desired_outcome="the current roadmap outcome has explicit work coverage",
            success_criteria=(
                "preparation brief is ready",
                "evidence references are checked",
            ),
            intervention=InterventionLevel.PREPARE,
            declared_agent_support=("writing", "verification"),
            portfolio_signals=signals(wip=1),
        )
        await steward.admit_work_order(reactivated_proposal.proposal_id)
        current_coverage = await steward.coverage(active.id)
        self.assertIs(current_coverage.disposition, CoverageDisposition.COVERED)
        self.assertEqual(
            current_coverage.work_proposal_ids,
            (reactivated_proposal.proposal_id,),
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

    async def test_delegated_intent_creates_subordinate_goals_without_rewriting_user_intent(
        self,
    ) -> None:
        user_origin, user_authority, _trust = user_security()
        agent_origin = OriginProvenance(
            provenance_id="origin:agent:noema",
            kind=OriginKind.AGENT,
            principal_id="agent:noema",
            authentication_ref="runtime-identity:noema",
        )
        delegated = IntentAuthority(
            authority_id="intent-authority:agent:noema:career",
            principal_id="agent:noema",
            scope=IntentAuthorityScope.DELEGATED,
            allowed_goal_kinds=(GoalKind.INSTRUMENTAL,),
            goal_refs=("goal:career",),
            provenance_ref=agent_origin.provenance_id,
        )
        trust = StaticStrategicTrust(
            (user_origin, agent_origin),
            (user_authority, delegated),
        )
        kernel = NoemaKernel()
        steward = IntentStewardCoordinator(
            kernel,
            validator=StrategicValidator(trust),
            clock=MutableClock(NOW),
        )
        await steward.record_goal_revision(
            goal_id="goal:career",
            description="User controls the governing career outcome",
            priority=1.0,
            utility=1.0,
            success_criteria=("user intent remains authoritative",),
            owner="user:carlos",
            status=GoalStatus.ACTIVE,
            deadline=None,
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
            origin=user_origin,
            intent_authority=user_authority,
            author="user:carlos",
            revision_reason="governing user intent",
        )
        with self.assertRaisesRegex(ValueError, "semantic lineage"):
            await steward.record_goal_revision(
                goal_id="goal:career",
                description="Agent attempts to capture the governing identity",
                priority=1.0,
                utility=1.0,
                success_criteria=("agent owns the rewritten goal",),
                owner="agent:noema",
                status=GoalStatus.ACTIVE,
                deadline=None,
                kind=GoalKind.INSTRUMENTAL,
                governing_goal_refs=("goal:career",),
                origin=agent_origin,
                intent_authority=delegated,
                author="agent:noema",
                revision_reason="illegal in-place semantic rewrite",
            )
        with self.assertRaisesRegex(ValueError, "explicit governing goal lineage"):
            await steward.record_goal_revision(
                goal_id="goal:prepare",
                description="Prepare evidence",
                priority=0.8,
                utility=0.8,
                success_criteria=("evidence is prepared",),
                owner="agent:noema",
                status=GoalStatus.ACTIVE,
                deadline=None,
                kind=GoalKind.INSTRUMENTAL,
                governing_goal_refs=(),
                origin=agent_origin,
                intent_authority=delegated,
                author="agent:noema",
                revision_reason="missing lineage attempt",
            )
        derived = await steward.record_goal_revision(
            goal_id="goal:prepare",
            description="Prepare evidence",
            priority=0.8,
            utility=0.8,
            success_criteria=("evidence is prepared",),
            owner="agent:noema",
            status=GoalStatus.ACTIVE,
            deadline=NOW + timedelta(days=7),
            kind=GoalKind.INSTRUMENTAL,
            governing_goal_refs=("goal:career",),
            origin=agent_origin,
            intent_authority=delegated,
            author="agent:noema",
            revision_reason="bounded subordinate goal",
        )
        self.assertEqual(derived.governing_goal_refs, ("goal:career",))
        governing = steward.projection.current_goal_revision("goal:career")
        self.assertIsNotNone(governing)
        assert governing is not None
        self.assertIs(governing.kind, GoalKind.USER_AUTHORED)
        self.assertEqual(governing.owner, "user:carlos")
        await kernel.stop()

    async def test_terminal_goals_block_strategy_while_blocked_goals_allow_recovery(self) -> None:
        clock = MutableClock(NOW)
        origin, authority, trust = user_security()
        kernel = NoemaKernel()
        steward = IntentStewardCoordinator(
            kernel,
            validator=StrategicValidator(trust),
            clock=clock,
        )
        cancelled_v1 = await steward.record_goal_revision(
            goal_id="goal:cancelled",
            description="Remain live until the user cancels the direction",
            priority=1.0,
            utility=1.0,
            success_criteria=("the direction remains intentional",),
            owner="user:carlos",
            status=GoalStatus.ACTIVE,
            deadline=None,
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
            origin=origin,
            intent_authority=authority,
            author="user:carlos",
            revision_reason="active fixture",
        )
        clock.advance()
        cancelled_roadmap = await steward.record_roadmap_revision(
            roadmap_id="roadmap:cancelled",
            governing_goal_revision_ids=(cancelled_v1.revision_id,),
            outcome_nodes=(OutcomeNode("recover", "Recover direction", ("recovery is complete",)),),
            assumptions=(),
            confidence=1.0,
            success_criteria=("recovery remains intentional",),
            resource_envelope={},
            intent_authority=authority,
            author="user:carlos",
            revision_reason="active strategy fixture",
        )
        clock.advance()
        cancelled_roles = OutcomeRoleAssignment.create(
            outcome_ref=f"{cancelled_roadmap.revision_id}#recover",
            outcome_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            decision_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            executor=OutcomeActor("agent:noema", ExecutionLocus.AGENT),
            verifier=OutcomeActor("user:carlos", ExecutionLocus.USER),
            recorded_at=clock(),
        )
        await steward.record_outcome_roles(cancelled_roles)
        clock.advance()
        cancelled_commitment = Commitment(
            id="commitment:cancelled-goal",
            description="Work only while the governing goal remains live",
            owner="user:carlos",
            status=CommitmentStatus.ACTIVE,
            created_at=clock(),
            updated_at=clock(),
            governing_goal_refs=("goal:cancelled",),
            roadmap_revision_id=cancelled_roadmap.revision_id,
            outcome_node_id="recover",
            role_assignment_id=cancelled_roles.assignment_id,
        )
        await steward.record_commitment(cancelled_commitment, intent_authority=authority)
        clock.advance()
        cancelled_v2 = await steward.record_goal_revision(
            goal_id="goal:cancelled",
            description="The user cancelled this direction",
            priority=0.0,
            utility=0.0,
            success_criteria=("no new strategic execution begins",),
            owner="user:carlos",
            status=GoalStatus.CANCELLED,
            deadline=None,
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
            origin=origin,
            intent_authority=authority,
            author="user:carlos",
            revision_reason="explicit cancellation",
        )
        with self.assertRaisesRegex(ValueError, "non-terminal governing goals"):
            await steward.record_roadmap_revision(
                roadmap_id="roadmap:cancelled-current",
                governing_goal_revision_ids=(cancelled_v2.revision_id,),
                outcome_nodes=(
                    OutcomeNode("illegal", "Illegal new strategy", ("must not be admitted",)),
                ),
                assumptions=(),
                confidence=1.0,
                success_criteria=("must not become canonical",),
                resource_envelope={},
                intent_authority=authority,
                author="user:carlos",
                revision_reason="terminal-goal bypass attempt",
            )
        with self.assertRaisesRegex(ValueError, "stale governing intent"):
            await steward.propose_work_for_commitment(
                cancelled_commitment.id,
                purpose="continue after cancellation",
                desired_outcome="must not become canonical",
                success_criteria=("must not become canonical",),
                intervention=InterventionLevel.PREPARE,
                declared_agent_support=("research",),
                portfolio_signals=signals(),
            )

        for index, terminal_status in enumerate(
            (GoalStatus.COMPLETED, GoalStatus.FAILED),
            start=1,
        ):
            with self.subTest(status=terminal_status):
                goal_id = f"goal:{terminal_status.value}"
                clock.advance()
                await steward.record_goal_revision(
                    goal_id=goal_id,
                    description="Begin as live intent",
                    priority=0.8,
                    utility=0.8,
                    success_criteria=("the terminal boundary is tested",),
                    owner="user:carlos",
                    status=GoalStatus.ACTIVE,
                    deadline=None,
                    kind=GoalKind.USER_AUTHORED,
                    governing_goal_refs=(),
                    origin=origin,
                    intent_authority=authority,
                    author="user:carlos",
                    revision_reason="active terminal fixture",
                )
                clock.advance()
                terminal = await steward.record_goal_revision(
                    goal_id=goal_id,
                    description=f"The goal is now {terminal_status.value}",
                    priority=0.0,
                    utility=0.0,
                    success_criteria=("no new strategy is admitted",),
                    owner="user:carlos",
                    status=terminal_status,
                    deadline=None,
                    kind=GoalKind.USER_AUTHORED,
                    governing_goal_refs=(),
                    origin=origin,
                    intent_authority=authority,
                    author="user:carlos",
                    revision_reason="terminal status fixture",
                )
                with self.assertRaisesRegex(ValueError, "non-terminal governing goals"):
                    await steward.record_roadmap_revision(
                        roadmap_id=f"roadmap:{terminal_status.value}",
                        governing_goal_revision_ids=(terminal.revision_id,),
                        outcome_nodes=(
                            OutcomeNode(
                                f"illegal-{index}",
                                "Illegal terminal strategy",
                                ("must not be admitted",),
                            ),
                        ),
                        assumptions=(),
                        confidence=1.0,
                        success_criteria=("must not become canonical",),
                        resource_envelope={},
                        intent_authority=authority,
                        author="user:carlos",
                        revision_reason="terminal-goal bypass attempt",
                    )

        clock.advance()
        blocked = await steward.record_goal_revision(
            goal_id="goal:blocked",
            description="Recover a goal whose progress is blocked",
            priority=0.9,
            utility=1.0,
            success_criteria=("the blocker is removed",),
            owner="user:carlos",
            status=GoalStatus.BLOCKED,
            deadline=None,
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
            origin=origin,
            intent_authority=authority,
            author="user:carlos",
            revision_reason="blocked recovery fixture",
        )
        clock.advance()
        blocked_roadmap = await steward.record_roadmap_revision(
            roadmap_id="roadmap:blocked",
            governing_goal_revision_ids=(blocked.revision_id,),
            outcome_nodes=(OutcomeNode("unblock", "Remove blocker", ("the blocker is removed",)),),
            assumptions=(),
            confidence=0.8,
            success_criteria=("blocked recovery remains possible",),
            resource_envelope={},
            intent_authority=authority,
            author="user:carlos",
            revision_reason="recovery strategy",
        )
        clock.advance()
        blocked_roles = OutcomeRoleAssignment.create(
            outcome_ref=f"{blocked_roadmap.revision_id}#unblock",
            outcome_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            decision_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            executor=OutcomeActor("agent:noema", ExecutionLocus.AGENT),
            verifier=OutcomeActor("user:carlos", ExecutionLocus.USER),
            recorded_at=clock(),
        )
        await steward.record_outcome_roles(blocked_roles)
        clock.advance()
        blocked_commitment = Commitment(
            id="commitment:blocked-recovery",
            description="Remove the blocker",
            owner="user:carlos",
            status=CommitmentStatus.ACTIVE,
            created_at=clock(),
            updated_at=clock(),
            governing_goal_refs=("goal:blocked",),
            roadmap_revision_id=blocked_roadmap.revision_id,
            outcome_node_id="unblock",
            role_assignment_id=blocked_roles.assignment_id,
        )
        await steward.record_commitment(blocked_commitment, intent_authority=authority)
        recovery = await steward.propose_work_for_commitment(
            blocked_commitment.id,
            purpose="remove the governing goal blocker",
            desired_outcome="the blocked goal can progress",
            success_criteria=("the blocker is removed",),
            intervention=InterventionLevel.PREPARE,
            declared_agent_support=("research",),
            portfolio_signals=signals(),
        )
        await steward.admit_work_order(recovery.proposal_id)
        self.assertIs(
            (await steward.coverage(blocked_commitment.id)).disposition,
            CoverageDisposition.COVERED,
        )
        await kernel.stop()

    async def test_identity_bound_act_follows_user_or_shared_executor_locus(self) -> None:
        clock = MutableClock(NOW)
        origin, authority, trust = user_security()
        kernel = NoemaKernel()
        steward = IntentStewardCoordinator(
            kernel,
            validator=StrategicValidator(trust),
            clock=clock,
        )
        goal = await steward.record_goal_revision(
            goal_id="goal:identity-execution",
            description="Preserve the user's identity-bound execution role",
            priority=1.0,
            utility=1.0,
            success_criteria=("identity-bound execution is not substituted",),
            owner="user:carlos",
            status=GoalStatus.ACTIVE,
            deadline=None,
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
            origin=origin,
            intent_authority=authority,
            author="user:carlos",
            revision_reason="identity execution fixture",
        )
        clock.advance()
        roadmap = await steward.record_roadmap_revision(
            roadmap_id="roadmap:identity-execution",
            governing_goal_revision_ids=(goal.revision_id,),
            outcome_nodes=(
                OutcomeNode(
                    "identity-act",
                    "Complete the identity-bound act",
                    ("the required actor completes the act",),
                ),
            ),
            assumptions=(),
            confidence=1.0,
            success_criteria=("identity-bound roles remain intact",),
            resource_envelope={},
            intent_authority=authority,
            author="user:carlos",
            revision_reason="identity execution strategy",
        )

        for index, executor_locus in enumerate(
            (ExecutionLocus.USER, ExecutionLocus.SHARED),
            start=1,
        ):
            with self.subTest(executor=executor_locus):
                clock.advance()
                roles = OutcomeRoleAssignment.create(
                    outcome_ref=f"{roadmap.revision_id}#identity-act",
                    outcome_owner=OutcomeActor(
                        "employer:process",
                        ExecutionLocus.EXTERNAL_HUMAN,
                    ),
                    decision_owner=OutcomeActor(
                        "employer:panel",
                        ExecutionLocus.EXTERNAL_HUMAN,
                    ),
                    executor=OutcomeActor(f"executor:{index}", executor_locus),
                    verifier=OutcomeActor(
                        "employer:panel",
                        ExecutionLocus.EXTERNAL_HUMAN,
                    ),
                    recorded_at=clock(),
                )
                await steward.record_outcome_roles(roles)
                clock.advance()
                envelope = AssistanceEnvelope.create(
                    role_assignment_id=roles.assignment_id,
                    maximum_intervention=InterventionLevel.ACT,
                    identity_bound=True,
                    physical_presence_required=False,
                    relationship_bound=False,
                    institutional_restrictions=("the executor identity is authenticated",),
                    user_development_value=1.0,
                    permitted_agent_support=("participation support",),
                    required_human_work=("remain the required participant",),
                    checkpoints=("executor identity is preserved",),
                    reversible=False,
                    risk_limit=0.2,
                    privacy_limit=0.2,
                    attention_budget=1.0,
                    recorded_at=clock(),
                )
                await steward.record_assistance_envelope(envelope)
                clock.advance()
                commitment = Commitment(
                    id=f"commitment:identity-executor:{index}",
                    description="Preserve the required executor",
                    owner="user:carlos",
                    status=CommitmentStatus.ACTIVE,
                    created_at=clock(),
                    updated_at=clock(),
                    governing_goal_refs=("goal:identity-execution",),
                    roadmap_revision_id=roadmap.revision_id,
                    outcome_node_id="identity-act",
                    role_assignment_id=roles.assignment_id,
                    assistance_envelope_id=envelope.envelope_id,
                )
                await steward.record_commitment(commitment, intent_authority=authority)
                with self.assertRaisesRegex(ValueError, "identity-bound execution"):
                    await steward.propose_work_for_commitment(
                        commitment.id,
                        purpose="unilaterally substitute for the required executor",
                        desired_outcome="must not become canonical",
                        success_criteria=("must not become canonical",),
                        intervention=InterventionLevel.ACT,
                        declared_agent_support=("participation support",),
                        portfolio_signals=signals(),
                    )
        await kernel.stop()

    async def test_replay_rejects_structurally_illegal_native_events(self) -> None:
        origin, authority, trust = user_security()
        kernel = NoemaKernel()
        steward = IntentStewardCoordinator(
            kernel,
            validator=StrategicValidator(trust),
            clock=MutableClock(NOW),
        )
        goal = await steward.record_goal_revision(
            goal_id="goal:replay",
            description="Replay remains a structural admission boundary",
            priority=1.0,
            utility=1.0,
            success_criteria=("illegal histories fail closed",),
            owner="user:carlos",
            status=GoalStatus.ACTIVE,
            deadline=None,
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
            origin=origin,
            intent_authority=authority,
            author="user:carlos",
            revision_reason="replay boundary fixture",
        )
        projection = StrategicProjection()
        projection.rebuild(kernel.schemas.normalize(event) for event in await kernel.history())
        native_legacy = GoalRevision.create(
            goal_id="goal:illegal-native-legacy",
            version=1,
            description="Native events cannot claim migration-only provenance",
            priority=1.0,
            utility=1.0,
            success_criteria=(),
            owner="user:carlos",
            status=GoalStatus.ACTIVE,
            deadline=None,
            kind=GoalKind.LEGACY_UNCLASSIFIED,
            governing_goal_refs=(),
            origin=origin,
            intent_authority=authority,
            based_on_event_cursor=projection.event_cursor,
            author="user:carlos",
            revision_reason="direct legacy provenance attempt",
            recorded_at=NOW + timedelta(seconds=30),
        )
        native_legacy_event = replace(
            native_legacy.to_event(source="direct-emitter"),
            metadata={"validated_at_event_cursor": projection.event_cursor},
        ).with_sequence(projection.event_cursor + 1)
        with self.assertRaisesRegex(ValueError, "native admission"):
            projection.apply(native_legacy_event)

        cyclic = RoadmapRevision.create(
            roadmap_id="roadmap:illegal-cycle",
            version=1,
            governing_goal_revision_ids=(goal.revision_id,),
            outcome_nodes=(
                OutcomeNode("a", "A", ("A complete",), ("b",)),
                OutcomeNode("b", "B", ("B complete",), ("a",)),
            ),
            assumptions=(),
            confidence=0.5,
            success_criteria=("cycle must be rejected",),
            resource_envelope={},
            intent_authority=authority,
            based_on_event_cursor=projection.event_cursor,
            author="user:carlos",
            revision_reason="direct illegal event",
            recorded_at=NOW + timedelta(minutes=1),
        )
        cyclic_event = replace(
            cyclic.to_event(source="direct-emitter"),
            metadata={"validated_at_event_cursor": projection.event_cursor},
        ).with_sequence(projection.event_cursor + 1)
        with self.assertRaisesRegex(ValueError, "DAG"):
            projection.apply(cyclic_event)

        orphan_roles = OutcomeRoleAssignment.create(
            outcome_ref="roadmap-revision:missing#missing-node",
            outcome_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            decision_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            executor=OutcomeActor("agent:noema", ExecutionLocus.AGENT),
            verifier=OutcomeActor("user:carlos", ExecutionLocus.USER),
            recorded_at=NOW + timedelta(minutes=2),
        )
        orphan_event = replace(
            orphan_roles.to_event(source="direct-emitter"),
            metadata={"validated_at_event_cursor": projection.event_cursor},
        ).with_sequence(projection.event_cursor + 1)
        with self.assertRaisesRegex(ValueError, "canonical roadmap outcome"):
            projection.apply(orphan_event)

        valid_roadmap = await steward.record_roadmap_revision(
            roadmap_id="roadmap:replay",
            governing_goal_revision_ids=(goal.revision_id,),
            outcome_nodes=(OutcomeNode("valid", "Valid outcome", ("valid outcome is covered",)),),
            assumptions=(),
            confidence=1.0,
            success_criteria=("valid outcome remains structural",),
            resource_envelope={},
            intent_authority=authority,
            author="user:carlos",
            revision_reason="valid replay fixture",
        )
        projection.rebuild(kernel.schemas.normalize(event) for event in await kernel.history())
        invalid_commitment = Commitment(
            id="commitment:missing-roles",
            description="Direct event bypasses canonical roles",
            owner="user:carlos",
            status=CommitmentStatus.ACTIVE,
            created_at=NOW + timedelta(minutes=3),
            updated_at=NOW + timedelta(minutes=3),
            governing_goal_refs=("goal:replay",),
            roadmap_revision_id=valid_roadmap.revision_id,
            outcome_node_id="valid",
            role_assignment_id="outcome-roles:missing",
        )
        commitment_event = replace(
            commitment_recorded_event(
                invalid_commitment,
                source="direct-emitter",
            ),
            metadata={
                "validated_at_event_cursor": projection.event_cursor,
                "intent_authority": authority.to_dict(),
            },
        ).with_sequence(projection.event_cursor + 1)
        with self.assertRaisesRegex(ValueError, "role assignment"):
            projection.apply(commitment_event)

        human_roles = OutcomeRoleAssignment.create(
            outcome_ref=f"{valid_roadmap.revision_id}#valid",
            outcome_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            decision_owner=OutcomeActor("user:carlos", ExecutionLocus.USER),
            executor=OutcomeActor("user:carlos", ExecutionLocus.USER),
            verifier=OutcomeActor("user:carlos", ExecutionLocus.USER),
            recorded_at=NOW + timedelta(minutes=4),
        )
        await steward.record_outcome_roles(human_roles)
        bounded_envelope = AssistanceEnvelope.create(
            role_assignment_id=human_roles.assignment_id,
            maximum_intervention=InterventionLevel.PREPARE,
            identity_bound=True,
            physical_presence_required=False,
            relationship_bound=False,
            institutional_restrictions=(),
            user_development_value=1.0,
            permitted_agent_support=("research",),
            required_human_work=("complete the outcome",),
            checkpoints=("user reviews preparation",),
            reversible=True,
            risk_limit=0.2,
            privacy_limit=0.2,
            attention_budget=1.0,
            recorded_at=NOW + timedelta(minutes=5),
        )
        await steward.record_assistance_envelope(bounded_envelope)
        human_commitment = Commitment(
            id="commitment:replay-assistance",
            description="Human executes while the agent remains bounded",
            owner="user:carlos",
            status=CommitmentStatus.ACTIVE,
            created_at=NOW + timedelta(minutes=6),
            updated_at=NOW + timedelta(minutes=6),
            governing_goal_refs=("goal:replay",),
            roadmap_revision_id=valid_roadmap.revision_id,
            outcome_node_id="valid",
            role_assignment_id=human_roles.assignment_id,
            assistance_envelope_id=bounded_envelope.envelope_id,
        )
        await steward.record_commitment(human_commitment, intent_authority=authority)
        projection.rebuild(kernel.schemas.normalize(event) for event in await kernel.history())
        direct_order = WorkOrder.create(
            purpose="bypass bounded assistance",
            governing_goal_refs=("goal:replay",),
            created_from=(
                f"commitment:{human_commitment.id}",
                f"roadmap-revision:{valid_roadmap.revision_id}",
                "outcome-node:valid",
            ),
            priority=0.5,
            desired_outcome="agent substitutes for human execution",
            success_criteria=("valid outcome is covered",),
            created_at=NOW + timedelta(minutes=7),
        )
        direct_proposal = WorkOrderProposal.create(
            commitment_id=human_commitment.id,
            roadmap_revision_id=valid_roadmap.revision_id,
            outcome_node_id="valid",
            work_order=direct_order,
            intervention=InterventionLevel.ACT,
            declared_agent_support=("research",),
            eligibility=WorkProposalEligibility.ACTIVE,
            portfolio_signals=signals(),
            wip_limit=4,
            based_on_event_cursor=projection.event_cursor,
            proposed_at=NOW + timedelta(minutes=7),
            validator_id="strategic-validator:v1",
        )
        direct_proposal_event = replace(
            direct_proposal.to_event(source="direct-emitter"),
            metadata={"validated_at_event_cursor": projection.event_cursor},
        ).with_sequence(projection.event_cursor + 1)
        with self.assertRaisesRegex(ValueError, "intervention limit"):
            projection.apply(direct_proposal_event)
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
            deadline=None,
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
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
                    deadline=None,
                    kind=GoalKind.USER_AUTHORED,
                    governing_goal_refs=(),
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
                deadline=None,
                kind=GoalKind.USER_AUTHORED,
                governing_goal_refs=(),
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
