"""Deterministic legality and authority checks for strategic admission."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..situation import Commitment, CommitmentStatus
from .models import (
    AssistanceEnvelope,
    CommitmentTransition,
    ExternalWorkstream,
    GoalKind,
    GoalRevision,
    IntentAuthority,
    IntentAuthorityScope,
    OriginKind,
    OriginProvenance,
    OutcomeRoleAssignment,
    RoadmapRevision,
    WorkOrderProposal,
    WorkProposalEligibility,
)
from .projection import StrategicProjection


class StrategicTrust(Protocol):
    """Admission boundary backed by an authenticator outside model control."""

    def verifies_origin(self, value: OriginProvenance) -> bool: ...

    def verifies_authority(self, value: IntentAuthority) -> bool: ...


@dataclass(frozen=True, slots=True)
class StaticStrategicTrust:
    """Deterministic admission trust fixture; deployments can replace this port."""

    origins: tuple[OriginProvenance, ...]
    authorities: tuple[IntentAuthority, ...]

    def verifies_origin(self, value: OriginProvenance) -> bool:
        return value in self.origins

    def verifies_authority(self, value: IntentAuthority) -> bool:
        return value in self.authorities


class StrategicValidator:
    def __init__(
        self,
        trust: StrategicTrust,
        *,
        validator_id: str = "strategic-validator:v1",
        wip_limit: int = 4,
    ) -> None:
        if not validator_id.strip():
            raise ValueError("strategic validator id must be non-empty")
        if wip_limit <= 0:
            raise ValueError("strategic WIP limit must be positive")
        self.trust = trust
        self.validator_id = validator_id
        self.wip_limit = wip_limit

    def validate_goal_revision(
        self,
        revision: GoalRevision,
        projection: StrategicProjection,
        *,
        expected_current_revision_id: str | None,
    ) -> None:
        self._require_cursor(revision.based_on_event_cursor, projection)
        current = projection.current_goal_revision(revision.goal_id)
        current_id = current.revision_id if current else None
        if current_id != expected_current_revision_id:
            raise ValueError("goal changed after the revision command was captured")
        expected_version = current.version + 1 if current else 1
        if revision.version != expected_version:
            raise ValueError("goal revision version is not the next version")
        if revision.supersedes_revision_id != current_id:
            raise ValueError("goal revision must supersede the current revision")
        if revision.kind is GoalKind.LEGACY_UNCLASSIFIED:
            raise ValueError("native admission cannot manufacture legacy goal provenance")
        if not self.trust.verifies_origin(revision.origin):
            raise ValueError("goal origin provenance is not authenticated")
        if not self.trust.verifies_authority(revision.intent_authority):
            raise ValueError("intent authority is not authenticated")
        authority = revision.intent_authority
        if authority.scope is IntentAuthorityScope.PROPOSE:
            raise ValueError("proposal-only intent authority cannot admit a goal revision")
        if (
            authority.principal_id != revision.origin.principal_id
            or authority.provenance_ref != revision.origin.provenance_id
        ):
            raise ValueError("goal origin and intent authority belong to different principals")
        if revision.author != authority.principal_id:
            raise ValueError("goal revision author does not hold the supplied intent authority")
        if revision.kind not in authority.allowed_goal_kinds:
            raise ValueError("intent authority does not cover the goal kind")
        if authority.goal_refs and revision.goal_id not in authority.goal_refs:
            raise ValueError("intent authority does not cover this goal")
        if revision.origin.principal_id != revision.owner:
            raise ValueError("goal owner must match authenticated origin principal")
        if revision.kind is GoalKind.USER_AUTHORED:
            if revision.origin.kind is not OriginKind.USER:
                raise ValueError("user-authored goals require authenticated user provenance")
            if authority.scope not in {
                IntentAuthorityScope.USER,
                IntentAuthorityScope.CONSTITUTIONAL,
            }:
                raise ValueError("user-authored goals require user intent authority")
        if revision.kind is GoalKind.CONSTITUTIONAL:
            if revision.origin.kind is not OriginKind.CONSTITUTIONAL:
                raise ValueError(
                    "constitutional goals require authenticated constitutional provenance"
                )
            if authority.scope is not IntentAuthorityScope.CONSTITUTIONAL:
                raise ValueError("constitutional goals require constitutional intent authority")
        if (
            revision.kind
            in {
                GoalKind.INSTRUMENTAL,
                GoalKind.EPISTEMIC,
                GoalKind.MAINTENANCE,
                GoalKind.EXPLORATORY,
            }
            and current is None
            and not authority.goal_refs
        ):
            raise ValueError("agent-origin goals require a governing goal scope")

    def validate_roadmap_revision(
        self,
        revision: RoadmapRevision,
        projection: StrategicProjection,
        *,
        expected_current_revision_id: str | None,
    ) -> None:
        self._require_cursor(revision.based_on_event_cursor, projection)
        current = projection.current_roadmap_revision(revision.roadmap_id)
        current_id = current.revision_id if current else None
        if current_id != expected_current_revision_id:
            raise ValueError("roadmap changed after the revision command was captured")
        if revision.version != (current.version + 1 if current else 1):
            raise ValueError("roadmap revision version is not the next version")
        if revision.supersedes_revision_id != current_id:
            raise ValueError("roadmap revision must supersede the current revision")
        if not self.trust.verifies_authority(revision.intent_authority):
            raise ValueError("roadmap revision lacks authenticated intent authority")
        if revision.intent_authority.scope is IntentAuthorityScope.PROPOSE:
            raise ValueError("proposal-only intent authority cannot admit a roadmap revision")
        if revision.author != revision.intent_authority.principal_id:
            raise ValueError("roadmap author lacks the supplied intent authority")
        governing_goals = tuple(
            projection.goal_revision(value) for value in revision.governing_goal_revision_ids
        )
        missing_goals = tuple(
            value
            for value, goal in zip(
                revision.governing_goal_revision_ids,
                governing_goals,
                strict=True,
            )
            if goal is None
        )
        if missing_goals:
            raise ValueError(f"roadmap references unknown goal revisions: {missing_goals}")
        admitted_goals = tuple(goal for goal in governing_goals if goal is not None)
        scoped_goal_ids = set(revision.intent_authority.goal_refs)
        if scoped_goal_ids:
            if any(goal.goal_id not in scoped_goal_ids for goal in admitted_goals):
                raise ValueError("roadmap intent authority does not cover its governing goals")
        elif any(goal.owner != revision.intent_authority.principal_id for goal in admitted_goals):
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
        self._require_dag(revision)

    def validate_roles(
        self, assignment: OutcomeRoleAssignment, projection: StrategicProjection
    ) -> None:
        self._resolve_outcome(assignment.outcome_ref, projection)

    def validate_assistance(
        self, envelope: AssistanceEnvelope, projection: StrategicProjection
    ) -> None:
        if projection.role_assignment(envelope.role_assignment_id) is None:
            raise ValueError("assistance envelope must reference canonical outcome roles")

    def validate_commitment(
        self,
        value: Commitment,
        projection: StrategicProjection,
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
        if not self.trust.verifies_authority(authority):
            raise ValueError("commitment lacks authenticated intent authority")
        if authority.scope is IntentAuthorityScope.PROPOSE:
            raise ValueError("proposal-only intent authority cannot admit a commitment")
        if value.owner != authority.principal_id:
            raise ValueError("commitment owner lacks supplied intent authority")
        if authority.goal_refs and not set(value.governing_goal_refs).issubset(authority.goal_refs):
            raise ValueError("commitment intent authority does not cover governing goals")
        if projection.commitment(value.id) is not None:
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
        roadmap = projection.roadmap_revision(value.roadmap_revision_id)
        if roadmap is None:
            raise ValueError("commitment references an unknown roadmap revision")
        if value.outcome_node_id not in {node.node_id for node in roadmap.outcome_nodes}:
            raise ValueError("commitment references an unknown roadmap outcome")
        expected_goals = {
            goal.goal_id
            for revision_id in roadmap.governing_goal_revision_ids
            if (goal := projection.goal_revision(revision_id)) is not None
        }
        if set(value.governing_goal_refs) != expected_goals:
            raise ValueError("commitment governing goals differ from its roadmap")
        if value.role_assignment_id is None:
            raise ValueError("commitment requires independent outcome role assignment")
        roles = projection.role_assignment(value.role_assignment_id)
        expected_outcome_ref = f"{roadmap.revision_id}#{value.outcome_node_id}"
        if roles is None or roles.outcome_ref != expected_outcome_ref:
            raise ValueError("commitment role assignment does not target its outcome")
        if value.assistance_envelope_id is not None:
            envelope = projection.assistance_envelope(value.assistance_envelope_id)
            if envelope is None or envelope.role_assignment_id != roles.assignment_id:
                raise ValueError("commitment assistance does not reference its outcome roles")

    def validate_transition(
        self,
        transition: CommitmentTransition,
        projection: StrategicProjection,
        *,
        authority: IntentAuthority,
    ) -> None:
        self._require_cursor(transition.based_on_event_cursor, projection)
        if not self.trust.verifies_authority(authority):
            raise ValueError("commitment transition lacks authenticated intent authority")
        if authority.scope is IntentAuthorityScope.PROPOSE:
            raise ValueError("proposal-only intent authority cannot transition a commitment")
        if transition.author != authority.principal_id:
            raise ValueError("commitment transition author lacks the supplied authority")
        current = projection.commitment(transition.commitment_id)
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
        if (
            current.status is CommitmentStatus.SUSPENDED
            and transition.to_state is CommitmentStatus.ACTIVE
        ):
            revision_id = transition.reactivation_roadmap_revision_id
            if revision_id is None or not transition.reorientation_evidence_refs:
                raise ValueError(
                    "reactivation requires a new roadmap revision and current evidence"
                )
            prior = (
                projection.roadmap_revision(current.roadmap_revision_id)
                if current.roadmap_revision_id
                else None
            )
            revision = projection.roadmap_revision(revision_id)
            if (
                prior is None
                or revision is None
                or revision.roadmap_id != prior.roadmap_id
                or revision.version <= prior.version
            ):
                raise ValueError("reactivation roadmap revision is not newer than suspension")
        elif (
            transition.reactivation_roadmap_revision_id is not None
            or transition.reorientation_evidence_refs
        ):
            raise ValueError("reactivation evidence belongs only on suspended-to-active")

    def validate_external(self, value: ExternalWorkstream, projection: StrategicProjection) -> None:
        if (
            value.observed_roadmap_ref.startswith("work-graph:")
            or value.observed_roadmap_ref in projection.work_graph_ids
        ):
            raise ValueError("external roadmap cannot reuse a Noema work graph id")
        missing = tuple(
            ref for ref in value.support_commitment_refs if projection.commitment(ref) is None
        )
        if missing:
            raise ValueError(f"external support references unknown commitments: {missing}")

    def validate_work_proposal(
        self, proposal: WorkOrderProposal, projection: StrategicProjection, *, at: datetime
    ) -> None:
        self._require_cursor(proposal.based_on_event_cursor, projection)
        if proposal.validator_id != self.validator_id:
            raise ValueError("work proposal validator identity is inconsistent")
        commitment = projection.commitment(proposal.commitment_id)
        if commitment is None:
            raise ValueError("work proposal requires a canonical commitment")
        if commitment.roadmap_revision_id != proposal.roadmap_revision_id:
            raise ValueError("work proposal roadmap provenance differs from commitment")
        if commitment.outcome_node_id != proposal.outcome_node_id:
            raise ValueError("work proposal outcome provenance differs from commitment")
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
        pending = sum(
            projection.admitted_work_order(value.work_order.work_order_id) is None
            for value in projection.work_proposals
        )
        if proposal.portfolio_signals.wip != pending:
            raise ValueError("work proposal WIP input differs from canonical pending work")
        if pending >= self.wip_limit:
            raise ValueError("deterministic strategic WIP limit reached")

    def validate_work_admission(
        self, proposal: WorkOrderProposal, projection: StrategicProjection
    ) -> None:
        commitment = projection.commitment(proposal.commitment_id)
        if commitment is None or commitment.status is not CommitmentStatus.ACTIVE:
            raise ValueError("commitment-derived execution requires ACTIVE commitment")
        if projection.admitted_work_order(proposal.work_order.work_order_id) is not None:
            return

    @staticmethod
    def work_eligibility(commitment: Commitment, *, at: datetime) -> WorkProposalEligibility | None:
        if commitment.status is CommitmentStatus.ACTIVE:
            return WorkProposalEligibility.ACTIVE
        if commitment.status is not CommitmentStatus.ACCEPTED:
            return None
        if commitment.activation_due_at is not None and commitment.activation_due_at <= at:
            return WorkProposalEligibility.ACTIVATION_DUE
        if commitment.lead_time_evidence_refs:
            return WorkProposalEligibility.PREREQUISITE_LEAD_TIME
        return None

    @staticmethod
    def _require_cursor(cursor: int, projection: StrategicProjection) -> None:
        if cursor != projection.event_cursor:
            raise ValueError("strategic mutation was not validated through current head")

    @staticmethod
    def _resolve_outcome(outcome_ref: str, projection: StrategicProjection) -> None:
        revision_id, separator, node_id = outcome_ref.partition("#")
        revision = projection.roadmap_revision(revision_id)
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
