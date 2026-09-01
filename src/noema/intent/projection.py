"""Rebuildable strategic history, coverage, and health projections."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime
from typing import TypeVar, cast

from ..events import Event
from ..situation import Commitment, CommitmentClosureReason, CommitmentStatus, GoalStatus
from ..work.models import WORK_GRAPH_ACCEPTED_EVENT, WORK_ORDER_RECORDED_EVENT, WorkGraph, WorkOrder
from .models import (
    ASSISTANCE_ENVELOPE_RECORDED_EVENT,
    COMMITMENT_RECORDED_EVENT,
    COMMITMENT_TRANSITIONED_EVENT,
    EXTERNAL_WORKSTREAM_OBSERVED_EVENT,
    GOAL_REVISION_RECORDED_EVENT,
    OUTCOME_ROLES_RECORDED_EVENT,
    ROADMAP_REVISION_RECORDED_EVENT,
    WORK_ORDER_PROPOSED_EVENT,
    AssistanceEnvelope,
    CommitmentCoverage,
    CommitmentTransition,
    CoverageDisposition,
    ExecutionLocus,
    ExternalWorkstream,
    GoalKind,
    GoalRevision,
    HealthSignal,
    IntentAuthority,
    IntentAuthorityScope,
    InterventionLevel,
    OriginKind,
    OriginProvenance,
    OutcomeRoleAssignment,
    Roadmap,
    RoadmapHealth,
    RoadmapRevision,
    WorkOrderProposal,
    WorkProposalEligibility,
    commitment_from_dict,
)
from .schemas import is_legacy_intent_event, legacy_context

T = TypeVar("T")


class StrategicProjection:
    """Project immutable strategic history from one canonical event cut."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._events: dict[str, Event] = {}
        self._last_sequence = 0
        self._goal_revisions: dict[str, GoalRevision] = {}
        self._goal_history: dict[str, list[str]] = {}
        self._current_goal_revision: dict[str, str] = {}
        self._roadmap_revisions: dict[str, RoadmapRevision] = {}
        self._roadmap_history: dict[str, list[str]] = {}
        self._current_roadmap_revision: dict[str, str] = {}
        self._commitments: dict[str, Commitment] = {}
        self._commitment_versions: dict[str, list[Commitment]] = {}
        self._commitment_transitions: dict[str, list[CommitmentTransition]] = {}
        self._roles: dict[str, OutcomeRoleAssignment] = {}
        self._assistance: dict[str, AssistanceEnvelope] = {}
        self._external_history: dict[str, list[ExternalWorkstream]] = {}
        self._external_current: dict[str, ExternalWorkstream] = {}
        self._work_proposals: dict[str, WorkOrderProposal] = {}
        self._admitted_work_orders: dict[str, WorkOrder] = {}
        self._work_graph_ids: set[str] = set()

    @property
    def event_cursor(self) -> int:
        return self._last_sequence

    @property
    def goal_revisions(self) -> tuple[GoalRevision, ...]:
        return tuple(
            self._goal_revisions[key]
            for key in sorted(
                self._goal_revisions,
                key=lambda value: (
                    self._goal_revisions[value].goal_id,
                    self._goal_revisions[value].version,
                    value,
                ),
            )
        )

    @property
    def roadmap_revisions(self) -> tuple[RoadmapRevision, ...]:
        return tuple(
            self._roadmap_revisions[key]
            for key in sorted(
                self._roadmap_revisions,
                key=lambda value: (
                    self._roadmap_revisions[value].roadmap_id,
                    self._roadmap_revisions[value].version,
                    value,
                ),
            )
        )

    @property
    def commitments(self) -> tuple[Commitment, ...]:
        return tuple(self._commitments[key] for key in sorted(self._commitments))

    @property
    def work_proposals(self) -> tuple[WorkOrderProposal, ...]:
        return tuple(self._work_proposals[key] for key in sorted(self._work_proposals))

    @property
    def external_workstreams(self) -> tuple[ExternalWorkstream, ...]:
        return tuple(self._external_current[key] for key in sorted(self._external_current))

    @property
    def work_graph_ids(self) -> frozenset[str]:
        return frozenset(self._work_graph_ids)

    def current_goal_revision(self, goal_id: str) -> GoalRevision | None:
        revision_id = self._current_goal_revision.get(goal_id)
        return self._goal_revisions.get(revision_id) if revision_id else None

    def goal_revision(self, revision_id: str) -> GoalRevision | None:
        return self._goal_revisions.get(revision_id)

    def goal_history(self, goal_id: str) -> tuple[GoalRevision, ...]:
        return tuple(self._goal_revisions[value] for value in self._goal_history.get(goal_id, ()))

    def roadmap_revision(self, revision_id: str) -> RoadmapRevision | None:
        return self._roadmap_revisions.get(revision_id)

    def current_roadmap_revision(self, roadmap_id: str) -> RoadmapRevision | None:
        revision_id = self._current_roadmap_revision.get(roadmap_id)
        return self._roadmap_revisions.get(revision_id) if revision_id else None

    def roadmap(self, roadmap_id: str) -> Roadmap | None:
        revision = self.current_roadmap_revision(roadmap_id)
        if revision is None:
            return None
        return Roadmap(roadmap_id, revision.revision_id, revision.version)

    def roadmap_history(self, roadmap_id: str) -> tuple[RoadmapRevision, ...]:
        return tuple(
            self._roadmap_revisions[value] for value in self._roadmap_history.get(roadmap_id, ())
        )

    def commitment(self, commitment_id: str) -> Commitment | None:
        return self._commitments.get(commitment_id)

    def commitment_history(self, commitment_id: str) -> tuple[Commitment, ...]:
        return tuple(self._commitment_versions.get(commitment_id, ()))

    def commitment_transitions(self, commitment_id: str) -> tuple[CommitmentTransition, ...]:
        return tuple(self._commitment_transitions.get(commitment_id, ()))

    def role_assignment(self, assignment_id: str) -> OutcomeRoleAssignment | None:
        return self._roles.get(assignment_id)

    def assistance_envelope(self, envelope_id: str) -> AssistanceEnvelope | None:
        return self._assistance.get(envelope_id)

    def work_proposal(self, proposal_id: str) -> WorkOrderProposal | None:
        return self._work_proposals.get(proposal_id)

    def admitted_work_order(self, work_order_id: str) -> WorkOrder | None:
        return self._admitted_work_orders.get(work_order_id)

    def external_history(self, workstream_id: str) -> tuple[ExternalWorkstream, ...]:
        return tuple(self._external_history.get(workstream_id, ()))

    def validate_goal_revision_structure(self, revision: GoalRevision) -> None:
        """Validate replayable goal identity, lineage, and authority binding."""

        current = self.current_goal_revision(revision.goal_id)
        if revision.version != (current.version + 1 if current else 1):
            raise ValueError("goal revision version is not the next version")
        if revision.supersedes_revision_id != (current.revision_id if current else None):
            raise ValueError("goal revision must supersede the current revision")
        if revision.kind is GoalKind.LEGACY_UNCLASSIFIED:
            raise ValueError("native admission cannot manufacture legacy goal provenance")
        authority = revision.intent_authority
        if authority.scope is IntentAuthorityScope.PROPOSE:
            raise ValueError("proposal-only intent authority cannot admit a goal revision")
        if (
            authority.principal_id != revision.origin.principal_id
            or authority.provenance_ref != revision.origin.provenance_id
        ):
            raise ValueError("goal origin and intent authority belong to different principals")
        if revision.owner != revision.origin.principal_id:
            raise ValueError("goal owner must match authenticated origin principal")
        if revision.author != authority.principal_id:
            raise ValueError("goal revision author does not hold the supplied intent authority")
        if revision.kind not in authority.allowed_goal_kinds:
            raise ValueError("intent authority does not cover the goal kind")
        if current is not None:
            if (
                revision.kind is not current.kind
                or revision.origin != current.origin
                or revision.owner != current.owner
                or revision.governing_goal_refs != current.governing_goal_refs
            ):
                raise ValueError("goal revision cannot change semantic lineage in place")
            if current.kind in {GoalKind.USER_AUTHORED, GoalKind.CONSTITUTIONAL} and (
                authority.principal_id != current.origin.principal_id
            ):
                raise ValueError("delegated authority cannot rewrite a governing goal")
        if revision.kind is GoalKind.USER_AUTHORED:
            if revision.origin.kind is not OriginKind.USER:
                raise ValueError("user-authored goals require authenticated user provenance")
            if authority.scope not in {
                IntentAuthorityScope.USER,
                IntentAuthorityScope.CONSTITUTIONAL,
            }:
                raise ValueError("user-authored goals require user intent authority")
        elif revision.kind is GoalKind.CONSTITUTIONAL:
            if revision.origin.kind is not OriginKind.CONSTITUTIONAL:
                raise ValueError(
                    "constitutional goals require authenticated constitutional provenance"
                )
            if authority.scope is not IntentAuthorityScope.CONSTITUTIONAL:
                raise ValueError("constitutional goals require constitutional intent authority")

        derived_kinds = {
            GoalKind.DELEGATED,
            GoalKind.INSTRUMENTAL,
            GoalKind.EPISTEMIC,
            GoalKind.MAINTENANCE,
            GoalKind.EXPLORATORY,
        }
        if revision.kind in derived_kinds:
            if not revision.governing_goal_refs:
                raise ValueError("derived goal requires explicit governing goal lineage")
            if revision.goal_id in revision.governing_goal_refs:
                raise ValueError("derived goal cannot govern itself")
            missing = tuple(
                ref
                for ref in revision.governing_goal_refs
                if self.current_goal_revision(ref) is None
            )
            if missing:
                raise ValueError(f"derived goal references unknown governing goals: {missing}")
            if authority.scope is IntentAuthorityScope.DELEGATED and not authority.goal_refs:
                raise ValueError("delegated intent authority requires an explicit goal scope")
            if authority.goal_refs and not set(revision.governing_goal_refs).issubset(
                authority.goal_refs
            ):
                raise ValueError("derived goal lineage exceeds delegated intent scope")
        else:
            if revision.governing_goal_refs:
                raise ValueError("governing goals cannot themselves have derived-goal lineage")
            if authority.goal_refs and revision.goal_id not in authority.goal_refs:
                raise ValueError("intent authority does not cover this governing goal")

    def validate_roadmap_revision_structure(self, revision: RoadmapRevision) -> None:
        """Validate replayable roadmap lineage, freshness, and graph legality."""

        current = self.current_roadmap_revision(revision.roadmap_id)
        if revision.version != (current.version + 1 if current else 1):
            raise ValueError("roadmap revision version is not the next version")
        if revision.supersedes_revision_id != (current.revision_id if current else None):
            raise ValueError("roadmap revision must supersede the current revision")
        authority = revision.intent_authority
        if authority.scope is IntentAuthorityScope.PROPOSE:
            raise ValueError("proposal-only intent authority cannot admit a roadmap revision")
        if revision.author != authority.principal_id:
            raise ValueError("roadmap author lacks the supplied intent authority")
        goals = tuple(self.goal_revision(value) for value in revision.governing_goal_revision_ids)
        missing = tuple(
            value
            for value, goal in zip(
                revision.governing_goal_revision_ids,
                goals,
                strict=True,
            )
            if goal is None
        )
        if missing:
            raise ValueError(f"roadmap references unknown goal revisions: {missing}")
        admitted_goals = tuple(goal for goal in goals if goal is not None)
        if any(self.current_goal_revision(goal.goal_id) != goal for goal in admitted_goals):
            raise ValueError("roadmap requires current governing goal revisions")
        scoped_goal_ids = set(authority.goal_refs)
        if scoped_goal_ids:
            if any(goal.goal_id not in scoped_goal_ids for goal in admitted_goals):
                raise ValueError("roadmap intent authority does not cover its governing goals")
        elif any(goal.owner != authority.principal_id for goal in admitted_goals):
            raise ValueError("roadmap author does not own its governing goals")

        node_ids = {value.node_id for value in revision.outcome_nodes}
        unknown_dependencies = {
            dependency
            for node in revision.outcome_nodes
            for dependency in node.approximate_dependencies
            if dependency not in node_ids
        }
        if unknown_dependencies:
            raise ValueError(
                f"roadmap dependencies reference unknown outcomes: {sorted(unknown_dependencies)}"
            )
        unknown_assumptions = {
            assumption
            for node in revision.outcome_nodes
            for assumption in node.assumption_refs
            if assumption not in revision.assumptions
        }
        if unknown_assumptions:
            raise ValueError(
                f"roadmap outcomes reference unknown assumptions: {sorted(unknown_assumptions)}"
            )
        self._require_dag(revision)

    def validate_roles_structure(self, assignment: OutcomeRoleAssignment) -> None:
        self._resolve_outcome(assignment.outcome_ref)

    def validate_assistance_structure(self, envelope: AssistanceEnvelope) -> None:
        if self.role_assignment(envelope.role_assignment_id) is None:
            raise ValueError("assistance envelope must reference canonical outcome roles")

    def validate_commitment_structure(
        self,
        value: Commitment,
        *,
        authority: IntentAuthority,
    ) -> None:
        for text, label in (
            (value.id, "commitment id"),
            (value.description, "commitment description"),
            (value.owner, "commitment owner"),
        ):
            if not text.strip():
                raise ValueError(f"{label} must be non-empty")
        if not math.isfinite(value.priority) or not 0.0 <= value.priority <= 1.0:
            raise ValueError("commitment priority must be between zero and one")
        for amount, label in (
            (value.attention_cost, "commitment attention cost"),
            (value.social_cost_of_failure, "commitment social cost of failure"),
        ):
            if not math.isfinite(amount) or amount < 0:
                raise ValueError(f"{label} must be finite and non-negative")
        for moment, label in (
            (value.created_at, "commitment created_at"),
            (value.updated_at, "commitment updated_at"),
            (value.deadline, "commitment deadline"),
            (value.activation_due_at, "commitment activation_due_at"),
        ):
            if moment is not None and moment.tzinfo is None:
                raise ValueError(f"{label} must be timezone-aware")
        if value.updated_at < value.created_at:
            raise ValueError("commitment updated_at cannot precede created_at")
        if authority.scope is IntentAuthorityScope.PROPOSE:
            raise ValueError("proposal-only intent authority cannot admit a commitment")
        if value.owner != authority.principal_id:
            raise ValueError("commitment owner lacks supplied intent authority")
        if authority.goal_refs and not set(value.governing_goal_refs).issubset(authority.goal_refs):
            raise ValueError("commitment intent authority does not cover governing goals")
        if self.commitment(value.id) is not None:
            raise ValueError("commitment identity already exists")
        if value.status not in {
            CommitmentStatus.PROPOSED,
            CommitmentStatus.ACCEPTED,
            CommitmentStatus.ACTIVE,
        }:
            raise ValueError("new commitment has an invalid lifecycle state")
        if value.closure_reason is not None:
            raise ValueError("open commitment cannot have a closure reason")
        if not value.governing_goal_refs:
            raise ValueError("strategic commitment requires governing goal refs")
        if value.roadmap_revision_id is None or value.outcome_node_id is None:
            raise ValueError("roadmap-derived commitment requires roadmap outcome provenance")
        roadmap = self._require_current_roadmap(value.roadmap_revision_id)
        self._require_current_goals(roadmap)
        if value.outcome_node_id not in {node.node_id for node in roadmap.outcome_nodes}:
            raise ValueError("commitment references an unknown roadmap outcome")
        expected_goals = {
            goal.goal_id
            for revision_id in roadmap.governing_goal_revision_ids
            if (goal := self.goal_revision(revision_id)) is not None
        }
        if set(value.governing_goal_refs) != expected_goals:
            raise ValueError("commitment governing goals differ from its roadmap")
        if value.role_assignment_id is None:
            raise ValueError("commitment requires independent outcome role assignment")
        roles = self.role_assignment(value.role_assignment_id)
        expected_outcome_ref = f"{roadmap.revision_id}#{value.outcome_node_id}"
        if roles is None or roles.outcome_ref != expected_outcome_ref:
            raise ValueError("commitment role assignment does not target its outcome")
        envelope = (
            self.assistance_envelope(value.assistance_envelope_id)
            if value.assistance_envelope_id
            else None
        )
        if value.assistance_envelope_id is not None and (
            envelope is None or envelope.role_assignment_id != roles.assignment_id
        ):
            raise ValueError("commitment assistance does not reference its outcome roles")
        if roles.executor.locus is not ExecutionLocus.AGENT and envelope is None:
            raise ValueError("human or external execution requires an assistance envelope")

    def validate_transition_structure(
        self,
        transition: CommitmentTransition,
        *,
        authority: IntentAuthority,
    ) -> None:
        if authority.scope is IntentAuthorityScope.PROPOSE:
            raise ValueError("proposal-only intent authority cannot transition a commitment")
        if transition.author != authority.principal_id:
            raise ValueError("commitment transition author lacks the supplied authority")
        current = self.commitment(transition.commitment_id)
        if current is None:
            raise ValueError("unknown commitment")
        if current.owner != authority.principal_id:
            raise ValueError("commitment transition authority does not own the obligation")
        if authority.goal_refs and not set(current.governing_goal_refs).issubset(
            authority.goal_refs
        ):
            raise ValueError("commitment transition authority does not cover governing goals")
        if current.status is CommitmentStatus.CLOSED:
            raise ValueError("closed commitment history cannot mutate")
        if transition.from_state is not current.status:
            raise ValueError("commitment transition starts from stale state")
        allowed = {
            CommitmentStatus.PROPOSED: {CommitmentStatus.ACCEPTED},
            CommitmentStatus.ACCEPTED: {
                CommitmentStatus.ACTIVE,
                CommitmentStatus.SUSPENDED,
                CommitmentStatus.CLOSED,
            },
            CommitmentStatus.ACTIVE: {
                CommitmentStatus.SUSPENDED,
                CommitmentStatus.CLOSED,
            },
            CommitmentStatus.SUSPENDED: {
                CommitmentStatus.ACTIVE,
                CommitmentStatus.CLOSED,
            },
        }
        if transition.to_state not in allowed.get(current.status, set()):
            raise ValueError("illegal commitment lifecycle transition")
        if transition.to_state is CommitmentStatus.CLOSED:
            if transition.closure_reason is None:
                raise ValueError("closed commitment requires a closure reason")
        elif transition.closure_reason is not None:
            raise ValueError("non-closed commitment cannot have a closure reason")

        is_reactivation = (
            current.status is CommitmentStatus.SUSPENDED
            and transition.to_state is CommitmentStatus.ACTIVE
        )
        if is_reactivation:
            revision_id = transition.reactivation_roadmap_revision_id
            role_id = transition.reactivation_role_assignment_id
            if revision_id is None or role_id is None or not transition.reorientation_evidence_refs:
                raise ValueError(
                    "reactivation requires current roadmap, remapped roles, and current evidence"
                )
            prior = (
                self.roadmap_revision(current.roadmap_revision_id)
                if current.roadmap_revision_id
                else None
            )
            revision = self._require_current_roadmap(revision_id)
            self._require_current_goals(revision)
            if (
                prior is None
                or revision.roadmap_id != prior.roadmap_id
                or revision.version <= prior.version
            ):
                raise ValueError("reactivation roadmap revision is not newer than suspension")
            if current.outcome_node_id not in {node.node_id for node in revision.outcome_nodes}:
                raise ValueError("reactivation outcome no longer exists in current roadmap")
            roles = self.role_assignment(role_id)
            expected = f"{revision.revision_id}#{current.outcome_node_id}"
            if roles is None or roles.outcome_ref != expected:
                raise ValueError("reactivation roles do not target the current roadmap outcome")
            envelope_id = transition.reactivation_assistance_envelope_id
            envelope = self.assistance_envelope(envelope_id) if envelope_id else None
            if envelope_id is not None and (
                envelope is None or envelope.role_assignment_id != role_id
            ):
                raise ValueError("reactivation assistance does not target remapped roles")
            if roles.executor.locus is not ExecutionLocus.AGENT and envelope is None:
                raise ValueError("reactivation requires assistance for human or external work")
        elif (
            transition.reactivation_roadmap_revision_id is not None
            or transition.reactivation_role_assignment_id is not None
            or transition.reactivation_assistance_envelope_id is not None
            or transition.reorientation_evidence_refs
        ):
            raise ValueError("reactivation remapping belongs only on suspended-to-active")

        if (
            transition.to_state
            in {
                CommitmentStatus.ACCEPTED,
                CommitmentStatus.ACTIVE,
            }
            and not is_reactivation
        ):
            if current.roadmap_revision_id is None:
                raise ValueError("commitment activation lacks roadmap provenance")
            roadmap = self._require_current_roadmap(current.roadmap_revision_id)
            self._require_current_goals(roadmap)

    def validate_external_structure(self, value: ExternalWorkstream) -> None:
        if (
            value.observed_roadmap_ref.startswith("work-graph:")
            or value.observed_roadmap_ref in self.work_graph_ids
        ):
            raise ValueError("external roadmap cannot reuse a Noema work graph id")
        missing = tuple(
            ref for ref in value.support_commitment_refs if self.commitment(ref) is None
        )
        if missing:
            raise ValueError(f"external support references unknown commitments: {missing}")

    def validate_work_proposal_structure(
        self,
        proposal: WorkOrderProposal,
        *,
        at: datetime,
    ) -> None:
        commitment = self.commitment(proposal.commitment_id)
        if commitment is None:
            raise ValueError("work proposal requires a canonical commitment")
        if commitment.roadmap_revision_id != proposal.roadmap_revision_id:
            raise ValueError("work proposal roadmap provenance differs from commitment")
        if commitment.outcome_node_id != proposal.outcome_node_id:
            raise ValueError("work proposal outcome provenance differs from commitment")
        roadmap = self._require_current_roadmap(proposal.roadmap_revision_id)
        self._require_current_goals(roadmap)
        if proposal.outcome_node_id not in {node.node_id for node in roadmap.outcome_nodes}:
            raise ValueError("work proposal references an unknown current roadmap outcome")
        eligibility = self.work_eligibility(commitment, at=at)
        if eligibility is None or proposal.eligibility is not eligibility:
            raise ValueError("commitment is not eligible for automatic work proposal")
        required_provenance = {
            f"commitment:{commitment.id}",
            f"roadmap-revision:{proposal.roadmap_revision_id}",
            f"outcome-node:{proposal.outcome_node_id}",
        }
        if not required_provenance.issubset(proposal.work_order.created_from):
            raise ValueError("roadmap-derived work lacks commitment provenance")
        if set(proposal.work_order.governing_goal_refs) != set(commitment.governing_goal_refs):
            raise ValueError("work proposal governing goals differ from commitment")
        self._validate_work_assistance(proposal, commitment)
        pending = sum(
            self.admitted_work_order(value.work_order.work_order_id) is None
            for value in self.work_proposals
        )
        if proposal.portfolio_signals.wip != pending:
            raise ValueError("work proposal WIP input differs from canonical pending work")
        if pending >= proposal.wip_limit:
            raise ValueError("deterministic strategic WIP limit reached")

    def validate_work_admission_structure(self, proposal: WorkOrderProposal) -> None:
        commitment = self.commitment(proposal.commitment_id)
        if commitment is None or commitment.status is not CommitmentStatus.ACTIVE:
            raise ValueError("commitment-derived execution requires ACTIVE commitment")
        roadmap = self._require_current_roadmap(proposal.roadmap_revision_id)
        self._require_current_goals(roadmap)
        self._validate_work_assistance(proposal, commitment)

    @staticmethod
    def work_eligibility(
        commitment: Commitment,
        *,
        at: datetime,
    ) -> WorkProposalEligibility | None:
        if commitment.status is CommitmentStatus.ACTIVE:
            return WorkProposalEligibility.ACTIVE
        if commitment.status is not CommitmentStatus.ACCEPTED:
            return None
        if commitment.activation_due_at is not None and commitment.activation_due_at <= at:
            return WorkProposalEligibility.ACTIVATION_DUE
        if commitment.lead_time_evidence_refs:
            return WorkProposalEligibility.PREREQUISITE_LEAD_TIME
        return None

    def _validate_work_assistance(
        self,
        proposal: WorkOrderProposal,
        commitment: Commitment,
    ) -> None:
        if commitment.role_assignment_id is None:
            raise ValueError("commitment-derived work requires outcome roles")
        roles = self.role_assignment(commitment.role_assignment_id)
        if roles is None:
            raise ValueError("commitment-derived work references unknown outcome roles")
        envelope = (
            self.assistance_envelope(commitment.assistance_envelope_id)
            if commitment.assistance_envelope_id
            else None
        )
        if roles.executor.locus is not ExecutionLocus.AGENT and envelope is None:
            raise ValueError("human or external execution requires bounded assistance")
        if envelope is None:
            return
        intervention_rank = {
            InterventionLevel.PREPARE: 0,
            InterventionLevel.PROPOSE: 1,
            InterventionLevel.CO_EXECUTE: 2,
            InterventionLevel.ACT: 3,
        }
        if (
            intervention_rank[proposal.intervention]
            > intervention_rank[envelope.maximum_intervention]
        ):
            raise ValueError("work proposal exceeds the assistance intervention limit")
        if not set(proposal.declared_agent_support).issubset(envelope.permitted_agent_support):
            raise ValueError("work proposal declares support outside the assistance envelope")
        if (
            proposal.intervention is InterventionLevel.ACT
            and envelope.identity_bound
            and roles.outcome_owner.locus is ExecutionLocus.USER
        ):
            raise ValueError("agent cannot act on a user-owned identity-bound outcome")

    def _require_current_roadmap(self, revision_id: str) -> RoadmapRevision:
        revision = self.roadmap_revision(revision_id)
        if revision is None:
            raise ValueError("strategic reference uses an unknown roadmap revision")
        if self.current_roadmap_revision(revision.roadmap_id) != revision:
            raise ValueError("strategic reference uses a stale roadmap revision")
        return revision

    def _require_current_goals(self, revision: RoadmapRevision) -> None:
        for revision_id in revision.governing_goal_revision_ids:
            goal = self.goal_revision(revision_id)
            if goal is None or self.current_goal_revision(goal.goal_id) != goal:
                raise ValueError("strategic reference uses stale governing intent")

    def _resolve_outcome(self, outcome_ref: str) -> None:
        revision_id, separator, node_id = outcome_ref.partition("#")
        revision = self.roadmap_revision(revision_id)
        if not separator or revision is None:
            raise ValueError("outcome role assignment requires canonical roadmap outcome")
        if node_id not in {value.node_id for value in revision.outcome_nodes}:
            raise ValueError("outcome role assignment references unknown outcome node")

    @staticmethod
    def _require_dag(revision: RoadmapRevision) -> None:
        dependencies = {
            value.node_id: set(value.approximate_dependencies) for value in revision.outcome_nodes
        }
        ready = sorted(key for key, values in dependencies.items() if not values)
        visited: list[str] = []
        while ready:
            node_id = ready.pop(0)
            visited.append(node_id)
            for successor, predecessors in dependencies.items():
                if node_id in predecessors:
                    predecessors.remove(node_id)
                    if not predecessors and successor not in visited and successor not in ready:
                        ready.append(successor)
                        ready.sort()
        if len(visited) != len(dependencies):
            raise ValueError("roadmap approximate dependencies must form a DAG")

    def apply(self, event: Event) -> bool:
        existing = self._events.get(event.id)
        if existing is not None:
            if existing != event:
                raise ValueError(f"conflicting canonical strategic event identity: {event.id}")
            return False
        if event.sequence is None:
            raise ValueError("strategic projection requires canonical sequenced events")
        if event.sequence <= self._last_sequence:
            raise ValueError("strategic events must be applied in canonical sequence order")

        handled = self._apply_event(event)
        self._events[event.id] = event
        self._last_sequence = event.sequence
        return handled

    def rebuild(self, events: Iterable[Event]) -> None:
        self._reset()
        for event in events:
            self.apply(event)

    def _apply_event(self, event: Event) -> bool:
        if is_legacy_intent_event(event):
            return self._apply_legacy(event)
        if event.type == GOAL_REVISION_RECORDED_EVENT:
            goal_revision = GoalRevision.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=f"goal-revision-recorded:{goal_revision.revision_id}",
                subject=goal_revision.goal_id,
                timestamp=goal_revision.recorded_at,
                based_on_event_cursor=goal_revision.based_on_event_cursor,
            )
            self.validate_goal_revision_structure(goal_revision)
            self._record_goal_revision(goal_revision, event)
            return True
        if event.type == ROADMAP_REVISION_RECORDED_EVENT:
            roadmap_revision = RoadmapRevision.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=(f"roadmap-revision-recorded:{roadmap_revision.revision_id}"),
                subject=roadmap_revision.roadmap_id,
                timestamp=roadmap_revision.recorded_at,
                based_on_event_cursor=roadmap_revision.based_on_event_cursor,
            )
            self.validate_roadmap_revision_structure(roadmap_revision)
            self._record_roadmap_revision(roadmap_revision, event)
            return True
        if event.type == COMMITMENT_RECORDED_EVENT:
            commitment = commitment_from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=f"commitment-recorded:{commitment.id}",
                subject=commitment.id,
                timestamp=commitment.created_at,
            )
            self.validate_commitment_structure(
                commitment,
                authority=self._event_intent_authority(event),
            )
            self._record_commitment(commitment, event)
            return True
        if event.type == COMMITMENT_TRANSITIONED_EVENT:
            transition = CommitmentTransition.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=f"commitment-transitioned:{transition.transition_id}",
                subject=transition.commitment_id,
                timestamp=transition.transitioned_at,
                based_on_event_cursor=transition.based_on_event_cursor,
            )
            self.validate_transition_structure(
                transition,
                authority=self._event_intent_authority(event),
            )
            self._record_transition(transition, event)
            return True
        if event.type == OUTCOME_ROLES_RECORDED_EVENT:
            roles = OutcomeRoleAssignment.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=f"outcome-roles-recorded:{roles.assignment_id}",
                subject=roles.outcome_ref,
                timestamp=roles.recorded_at,
            )
            self.validate_roles_structure(roles)
            self._record_immutable(self._roles, roles.assignment_id, roles, "outcome roles")
            return True
        if event.type == ASSISTANCE_ENVELOPE_RECORDED_EVENT:
            envelope = AssistanceEnvelope.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=f"assistance-envelope-recorded:{envelope.envelope_id}",
                subject=envelope.role_assignment_id,
                timestamp=envelope.recorded_at,
            )
            self.validate_assistance_structure(envelope)
            self._record_immutable(self._assistance, envelope.envelope_id, envelope, "assistance")
            return True
        if event.type == EXTERNAL_WORKSTREAM_OBSERVED_EVENT:
            observation = ExternalWorkstream.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=(f"external-workstream-observed:{observation.observation_id}"),
                subject=observation.workstream_id,
                timestamp=observation.recorded_at,
            )
            self.validate_external_structure(observation)
            history = self._external_history.setdefault(observation.workstream_id, [])
            if history and observation.recorded_at < history[-1].recorded_at:
                raise ValueError("external workstream knowledge time cannot regress")
            if any(item.observation_id == observation.observation_id for item in history):
                raise ValueError("external observation id changed")
            history.append(observation)
            self._external_current[observation.workstream_id] = observation
            return True
        if event.type == WORK_ORDER_PROPOSED_EVENT:
            proposal = WorkOrderProposal.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=f"work-order-proposed:{proposal.proposal_id}",
                subject=proposal.commitment_id,
                timestamp=proposal.proposed_at,
                based_on_event_cursor=proposal.based_on_event_cursor,
            )
            self.validate_work_proposal_structure(proposal, at=proposal.proposed_at)
            self._record_immutable(
                self._work_proposals,
                proposal.proposal_id,
                proposal,
                "work order proposal",
            )
            return True
        if event.type == WORK_ORDER_RECORDED_EVENT:
            order = WorkOrder.from_event(event)
            matching = tuple(
                proposal
                for proposal in self._work_proposals.values()
                if proposal.work_order.work_order_id == order.work_order_id
            )
            for proposal in matching:
                self.validate_work_admission_structure(proposal)
            self._record_immutable(
                self._admitted_work_orders, order.work_order_id, order, "work order"
            )
            return True
        if event.type == WORK_GRAPH_ACCEPTED_EVENT:
            self._work_graph_ids.add(WorkGraph.from_event(event).graph_id)
            return True
        return False

    @staticmethod
    def _record_immutable(values: dict[str, T], key: str, value: T, label: str) -> None:
        existing = values.get(key)
        if existing is not None and existing != value:
            raise ValueError(f"{label} changed in place: {key}")
        values[key] = value

    @staticmethod
    def _event_intent_authority(event: Event) -> IntentAuthority:
        value = event.metadata.get("intent_authority")
        if not isinstance(value, dict):
            raise ValueError("strategic event lacks an intent-authority admission receipt")
        return IntentAuthority.from_dict(cast(Mapping[str, object], value))

    def _validate_native_envelope(
        self,
        event: Event,
        *,
        expected_id: str,
        subject: str,
        timestamp: datetime,
        based_on_event_cursor: int | None = None,
    ) -> None:
        if event.id != expected_id or event.subject != subject or event.timestamp != timestamp:
            raise ValueError("strategic event envelope is inconsistent")
        validated_cursor = event.metadata.get("validated_at_event_cursor")
        # Durable store sequences may contain gaps after rolled-back inserts.
        # The exact causal cut is the preceding canonical head we projected,
        # not an arithmetic assumption about the next sequence value.
        expected_cursor = self._last_sequence
        if validated_cursor != expected_cursor:
            raise ValueError("strategic event lacks exact-head admission evidence")
        if based_on_event_cursor is not None and validated_cursor != based_on_event_cursor:
            raise ValueError("strategic event cursor differs from admitted content")

    def _record_goal_revision(self, revision: GoalRevision, event: Event) -> None:
        subject_matches = event.subject == revision.goal_id or (
            is_legacy_intent_event(event) and event.subject is None
        )
        if not subject_matches or event.timestamp != revision.recorded_at:
            raise ValueError("goal revision event envelope is inconsistent")
        current = self.current_goal_revision(revision.goal_id)
        expected_version = current.version + 1 if current else 1
        expected_supersedes = current.revision_id if current else None
        if (
            revision.version != expected_version
            or revision.supersedes_revision_id != expected_supersedes
        ):
            raise ValueError("goal revision does not extend immutable history")
        if revision.based_on_event_cursor >= cast(int, event.sequence):
            raise ValueError("goal revision cursor must precede its canonical event")
        self._record_immutable(
            self._goal_revisions, revision.revision_id, revision, "goal revision"
        )
        self._goal_history.setdefault(revision.goal_id, []).append(revision.revision_id)
        self._current_goal_revision[revision.goal_id] = revision.revision_id

    def _record_roadmap_revision(self, revision: RoadmapRevision, event: Event) -> None:
        if event.subject != revision.roadmap_id or event.timestamp != revision.recorded_at:
            raise ValueError("roadmap revision event envelope is inconsistent")
        current = self.current_roadmap_revision(revision.roadmap_id)
        expected_version = current.version + 1 if current else 1
        expected_supersedes = current.revision_id if current else None
        if (
            revision.version != expected_version
            or revision.supersedes_revision_id != expected_supersedes
        ):
            raise ValueError("roadmap revision does not extend immutable history")
        if revision.based_on_event_cursor >= cast(int, event.sequence):
            raise ValueError("roadmap revision cursor must precede its canonical event")
        self._record_immutable(
            self._roadmap_revisions, revision.revision_id, revision, "roadmap revision"
        )
        self._roadmap_history.setdefault(revision.roadmap_id, []).append(revision.revision_id)
        self._current_roadmap_revision[revision.roadmap_id] = revision.revision_id

    def _record_commitment(self, value: Commitment, event: Event) -> None:
        if event.subject != value.id or event.timestamp != value.created_at:
            raise ValueError("commitment event envelope is inconsistent")
        existing = self._commitments.get(value.id)
        if existing is not None and existing != value:
            raise ValueError(f"commitment identity changed: {value.id}")
        self._commitments[value.id] = value
        self._commitment_versions.setdefault(value.id, []).append(value)

    def _record_transition(self, transition: CommitmentTransition, event: Event) -> None:
        current = self._commitments.get(transition.commitment_id)
        if current is None:
            raise ValueError("commitment transition references unknown commitment")
        if event.subject != current.id or event.timestamp != transition.transitioned_at:
            raise ValueError("commitment transition event envelope is inconsistent")
        if current.status != transition.from_state:
            raise ValueError("commitment transition does not start at current state")
        updated = replace(
            current,
            status=transition.to_state,
            closure_reason=transition.closure_reason,
            roadmap_revision_id=(
                transition.reactivation_roadmap_revision_id or current.roadmap_revision_id
            ),
            role_assignment_id=(
                transition.reactivation_role_assignment_id or current.role_assignment_id
            ),
            assistance_envelope_id=(
                transition.reactivation_assistance_envelope_id
                if transition.reactivation_roadmap_revision_id is not None
                else current.assistance_envelope_id
            ),
            updated_at=transition.transitioned_at,
        )
        self._commitments[current.id] = updated
        self._commitment_versions.setdefault(current.id, []).append(updated)
        self._commitment_transitions.setdefault(current.id, []).append(transition)

    def _apply_legacy(self, event: Event) -> bool:
        context = legacy_context(event)
        operation = str(context["operation"])
        if event.type.startswith("goal."):
            return self._apply_legacy_goal(event, operation, context)
        if event.type.startswith("commitment."):
            return self._apply_legacy_commitment(event, operation)
        return False

    def _apply_legacy_goal(
        self, event: Event, operation: str, context: Mapping[str, object]
    ) -> bool:
        goal_id = str(event.payload.get("id") or event.subject or event.id)
        current = self.current_goal_revision(goal_id)
        if operation == "patch" and current is None:
            return False
        origin = (
            current.origin
            if current
            else OriginProvenance.from_dict(cast(Mapping[str, object], context["origin"]))
        )
        authority = (
            current.intent_authority
            if current
            else IntentAuthority.from_dict(cast(Mapping[str, object], context["intent_authority"]))
        )
        payload = event.payload
        revision = GoalRevision.create(
            goal_id=goal_id,
            version=current.version + 1 if current else 1,
            description=str(payload.get("description", current.description if current else "")),
            priority=_float_value(payload.get("priority", current.priority if current else 0.5)),
            utility=_float_value(payload.get("utility", current.utility if current else 1.0)),
            success_criteria=_string_values(
                payload.get("success_criteria", current.success_criteria if current else ())
            ),
            owner=str(payload.get("owner", current.owner if current else event.source)),
            status=GoalStatus(str(payload.get("status", current.status if current else "active"))),
            deadline=(
                current.deadline
                if "deadline" not in payload and current is not None
                else _parse_optional_datetime(payload.get("deadline"))
            ),
            kind=current.kind if current else GoalKind.LEGACY_UNCLASSIFIED,
            governing_goal_refs=current.governing_goal_refs if current else (),
            origin=origin,
            intent_authority=authority,
            based_on_event_cursor=self._last_sequence,
            author=event.source,
            revision_reason=f"deterministic migration of {event.type}",
            recorded_at=event.timestamp,
            supersedes_revision_id=current.revision_id if current else None,
        )
        self._record_goal_revision(revision, event)
        return True

    def _apply_legacy_commitment(self, event: Event, operation: str) -> bool:
        commitment_id = str(event.payload.get("id") or event.subject or event.id)
        current = self._commitments.get(commitment_id)
        if operation != "create" and current is None:
            return False
        if current is None:
            data: dict[str, object] = dict(event.payload)
            data.update(
                {
                    "id": commitment_id,
                    "created_at": event.timestamp,
                    "updated_at": event.timestamp,
                }
            )
            value = commitment_from_dict(data)
            self._commitments[value.id] = value
            self._commitment_versions.setdefault(value.id, []).append(value)
            return True
        status = CommitmentStatus(str(event.payload.get("status", current.status)))
        closure_value = event.payload.get("closure_reason", current.closure_reason)
        closure = (
            closure_value
            if isinstance(closure_value, CommitmentClosureReason)
            else CommitmentClosureReason(str(closure_value))
            if closure_value is not None
            else None
        )
        updated = replace(
            current,
            description=str(event.payload.get("description", current.description)),
            owner=str(event.payload.get("owner", current.owner)),
            priority=_float_value(event.payload.get("priority", current.priority)),
            status=status,
            deadline=(
                current.deadline
                if "deadline" not in event.payload
                else _parse_optional_datetime(event.payload["deadline"])
            ),
            terminal=bool(event.payload.get("terminal", current.terminal)),
            attention_cost=_float_value(
                event.payload.get("attention_cost", current.attention_cost)
            ),
            social_cost_of_failure=_float_value(
                event.payload.get("social_cost_of_failure", current.social_cost_of_failure)
            ),
            closure_reason=closure,
            updated_at=event.timestamp,
        )
        self._commitments[commitment_id] = updated
        self._commitment_versions.setdefault(commitment_id, []).append(updated)
        if status != current.status:
            transition = CommitmentTransition.create(
                commitment_id=commitment_id,
                from_state=current.status,
                to_state=status,
                closure_reason=closure,
                based_on_event_cursor=self._last_sequence,
                author=event.source,
                reason=f"deterministic migration of {event.type}",
                transitioned_at=event.timestamp,
            )
            self._commitment_transitions.setdefault(commitment_id, []).append(transition)
        return True

    def coverage(self, commitment_id: str, *, at: datetime) -> CommitmentCoverage:
        commitment = self._commitments.get(commitment_id)
        if commitment is None:
            raise KeyError(f"unknown commitment: {commitment_id}")
        proposals = tuple(
            sorted(
                value.proposal_id
                for value in self._work_proposals.values()
                if value.commitment_id == commitment_id
            )
        )
        admitted = tuple(
            sorted(
                value.work_order.work_order_id
                for value in self._work_proposals.values()
                if value.commitment_id == commitment_id
                and value.work_order.work_order_id in self._admitted_work_orders
            )
        )
        roadmap = (
            self.roadmap_revision(commitment.roadmap_revision_id)
            if commitment.roadmap_revision_id
            else None
        )
        if roadmap is None or commitment.outcome_node_id is None:
            required_criteria: tuple[str, ...] = ()
        else:
            outcome = next(
                (
                    node
                    for node in roadmap.outcome_nodes
                    if node.node_id == commitment.outcome_node_id
                ),
                None,
            )
            required_criteria = outcome.success_criteria if outcome else ()
        admitted_criteria = {
            criterion
            for work_order_id in admitted
            for criterion in self._admitted_work_orders[work_order_id].success_criteria
        }
        covered_criteria = tuple(
            criterion for criterion in required_criteria if criterion in admitted_criteria
        )
        uncovered_criteria = tuple(
            criterion for criterion in required_criteria if criterion not in admitted_criteria
        )
        pending_proposals = tuple(
            value
            for value in self._work_proposals.values()
            if value.commitment_id == commitment_id
            and value.work_order.work_order_id not in self._admitted_work_orders
        )
        external_support = any(
            value.support_required
            and commitment_id in value.support_commitment_refs
            and value.freshness_expires_at > at
            for value in self._external_current.values()
        )
        eligible = commitment.status is CommitmentStatus.ACTIVE or (
            commitment.status is CommitmentStatus.ACCEPTED
            and (
                commitment.activation_due_at is not None
                and commitment.activation_due_at <= at
                or bool(commitment.lead_time_evidence_refs)
            )
        )
        if required_criteria and not uncovered_criteria:
            disposition = CoverageDisposition.COVERED
        elif pending_proposals:
            disposition = CoverageDisposition.PROPOSED
        elif eligible:
            disposition = CoverageDisposition.UNCOVERED
        else:
            disposition = CoverageDisposition.INACTIVE
        return CommitmentCoverage(
            commitment_id=commitment_id,
            disposition=disposition,
            required_criteria=required_criteria,
            covered_criteria=covered_criteria,
            uncovered_criteria=uncovered_criteria,
            work_proposal_ids=proposals,
            admitted_work_order_ids=admitted,
            external_support_required=external_support,
        )

    def roadmap_health(self, roadmap_id: str, *, at: datetime, wip_limit: int = 4) -> RoadmapHealth:
        revision = self.current_roadmap_revision(roadmap_id)
        if revision is None:
            raise KeyError(f"unknown roadmap: {roadmap_id}")
        aligned = all(
            (goal := self._goal_revisions.get(revision_id)) is not None
            and self._current_goal_revision.get(goal.goal_id) == revision_id
            for revision_id in revision.governing_goal_revision_ids
        )
        linked = tuple(
            value
            for value in self._commitments.values()
            if value.roadmap_revision_id == revision.revision_id
        )
        failed = any(
            value.status is CommitmentStatus.CLOSED
            and value.closure_reason
            in {CommitmentClosureReason.FAILED, CommitmentClosureReason.BREACHED}
            for value in linked
        )
        late = any(
            value.status in {CommitmentStatus.ACCEPTED, CommitmentStatus.ACTIVE}
            and value.deadline is not None
            and value.deadline < at
            for value in linked
        )
        linked_commitment_ids = {item.id for item in linked}
        wip = sum(
            value.commitment_id in linked_commitment_ids
            and value.work_order.work_order_id not in self._admitted_work_orders
            for value in self._work_proposals.values()
        )
        external_change = any(
            value.support_required
            and value.freshness_expires_at > at
            and any(ref in {item.id for item in linked} for ref in value.support_commitment_refs)
            for value in self._external_current.values()
        )
        signals = {
            "goal alignment": HealthSignal.SATISFIED if aligned else HealthSignal.NEEDS_REVIEW,
            "assumption validity": (
                HealthSignal.UNKNOWN if revision.assumptions else HealthSignal.SATISFIED
            ),
            "dependency validity": HealthSignal.SATISFIED,
            "progress consistency": (
                HealthSignal.NEEDS_REVIEW if failed else HealthSignal.SATISFIED
            ),
            "schedule feasibility": (HealthSignal.NEEDS_REVIEW if late else HealthSignal.SATISFIED),
            "capacity fit": (
                HealthSignal.NEEDS_REVIEW if wip > wip_limit else HealthSignal.SATISFIED
            ),
            "opportunity validity": (
                HealthSignal.NEEDS_REVIEW if external_change else HealthSignal.SATISFIED
            ),
        }
        reasons = tuple(
            key for key, value in signals.items() if value is not HealthSignal.SATISFIED
        )
        return RoadmapHealth(
            roadmap_id=roadmap_id,
            revision_id=revision.revision_id,
            goal_alignment=signals["goal alignment"],
            assumption_validity=signals["assumption validity"],
            dependency_validity=signals["dependency validity"],
            progress_consistency=signals["progress consistency"],
            schedule_feasibility=signals["schedule feasibility"],
            capacity_fit=signals["capacity fit"],
            opportunity_validity=signals["opportunity validity"],
            review_reasons=reasons,
        )


def _parse_optional_datetime(value: object) -> datetime | None:
    from ..types import parse_datetime

    return parse_datetime(cast(str | datetime | None, value))


def _float_value(value: object) -> float:
    return float(cast(str | int | float, value))


def _string_values(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in cast(tuple[object, ...] | list[object], value))
