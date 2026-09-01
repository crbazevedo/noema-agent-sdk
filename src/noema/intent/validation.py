"""Deterministic legality and authority checks for strategic admission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..situation import Commitment
from .models import (
    AssistanceEnvelope,
    CommitmentTransition,
    ExternalWorkstream,
    GoalRevision,
    IntentAuthority,
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
        if not self.trust.verifies_origin(revision.origin):
            raise ValueError("goal origin provenance is not authenticated")
        if not self.trust.verifies_authority(revision.intent_authority):
            raise ValueError("intent authority is not authenticated")
        projection.validate_goal_revision_structure(revision)

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
        if not self.trust.verifies_authority(revision.intent_authority):
            raise ValueError("roadmap revision lacks authenticated intent authority")
        projection.validate_roadmap_revision_structure(revision)

    def validate_roles(
        self, assignment: OutcomeRoleAssignment, projection: StrategicProjection
    ) -> None:
        projection.validate_roles_structure(assignment)

    def validate_assistance(
        self, envelope: AssistanceEnvelope, projection: StrategicProjection
    ) -> None:
        projection.validate_assistance_structure(envelope)

    def validate_commitment(
        self,
        value: Commitment,
        projection: StrategicProjection,
        *,
        authority: IntentAuthority,
    ) -> None:
        if not self.trust.verifies_authority(authority):
            raise ValueError("commitment lacks authenticated intent authority")
        projection.validate_commitment_structure(value, authority=authority)

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
        projection.validate_transition_structure(transition, authority=authority)

    def validate_external(self, value: ExternalWorkstream, projection: StrategicProjection) -> None:
        projection.validate_external_structure(value)

    def validate_work_proposal(
        self, proposal: WorkOrderProposal, projection: StrategicProjection, *, at: datetime
    ) -> None:
        self._require_cursor(proposal.based_on_event_cursor, projection)
        if proposal.validator_id != self.validator_id:
            raise ValueError("work proposal validator identity is inconsistent")
        if proposal.wip_limit != self.wip_limit:
            raise ValueError("work proposal WIP policy differs from its validator")
        projection.validate_work_proposal_structure(proposal, at=at)

    def validate_work_admission(
        self, proposal: WorkOrderProposal, projection: StrategicProjection
    ) -> None:
        if projection.admitted_work_order(proposal.work_order.work_order_id) is not None:
            return
        projection.validate_work_admission_structure(proposal)

    @staticmethod
    def work_eligibility(commitment: Commitment, *, at: datetime) -> WorkProposalEligibility | None:
        return StrategicProjection.work_eligibility(commitment, at=at)

    @staticmethod
    def _require_cursor(cursor: int, projection: StrategicProjection) -> None:
        if cursor != projection.event_cursor:
            raise ValueError("strategic mutation was not validated through current head")
