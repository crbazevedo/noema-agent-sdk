"""Immutable contracts for intent and user-outcome stewardship."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import cast

from ..events import Event
from ..situation import (
    Commitment,
    CommitmentClosureReason,
    CommitmentStatus,
    GoalStatus,
)
from ..types import JSONObject, JSONValue, parse_datetime
from ..work.models import WorkOrder

GOAL_REVISION_RECORDED_EVENT = "intent.goal_revision_recorded"
ROADMAP_REVISION_RECORDED_EVENT = "intent.roadmap_revision_recorded"
COMMITMENT_RECORDED_EVENT = "intent.commitment_recorded"
COMMITMENT_TRANSITIONED_EVENT = "intent.commitment_transitioned"
OUTCOME_ROLES_RECORDED_EVENT = "intent.outcome_roles_recorded"
ASSISTANCE_ENVELOPE_RECORDED_EVENT = "intent.assistance_envelope_recorded"
EXTERNAL_WORKSTREAM_OBSERVED_EVENT = "intent.external_workstream_observed"
WORK_ORDER_PROPOSED_EVENT = "intent.work_order_proposed"


class GoalKind(StrEnum):
    CONSTITUTIONAL = "constitutional"
    USER_AUTHORED = "user_authored"
    DELEGATED = "delegated"
    INSTRUMENTAL = "instrumental"
    EPISTEMIC = "epistemic"
    MAINTENANCE = "maintenance"
    EXPLORATORY = "exploratory"
    LEGACY_UNCLASSIFIED = "legacy_unclassified"


class OriginKind(StrEnum):
    CONSTITUTIONAL = "constitutional"
    USER = "user"
    DELEGATED = "delegated"
    AGENT = "agent"
    SYSTEM = "system"
    LEGACY_UNVERIFIED = "legacy_unverified"


class IntentAuthorityScope(StrEnum):
    PROPOSE = "propose"
    DELEGATED = "delegated"
    USER = "user"
    CONSTITUTIONAL = "constitutional"


class ExecutionLocus(StrEnum):
    USER = "user"
    AGENT = "agent"
    SHARED = "shared"
    EXTERNAL_HUMAN = "external_human"
    EXTERNAL_SYSTEM = "external_system"


class InterventionLevel(StrEnum):
    PREPARE = "prepare"
    PROPOSE = "propose"
    CO_EXECUTE = "co_execute"
    ACT = "act"


class WorkProposalEligibility(StrEnum):
    ACTIVE = "active"
    ACTIVATION_DUE = "activation_due"
    PREREQUISITE_LEAD_TIME = "prerequisite_lead_time"


class CoverageDisposition(StrEnum):
    INACTIVE = "inactive"
    UNCOVERED = "uncovered"
    PROPOSED = "proposed"
    COVERED = "covered"


class HealthSignal(StrEnum):
    SATISFIED = "satisfied"
    NEEDS_REVIEW = "needs_review"
    UNKNOWN = "unknown"


def _require_text(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _bounded(value: float, name: str) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between zero and one")


def _unique(values: tuple[str, ...], name: str, *, required: bool = False) -> None:
    if required and not values:
        raise ValueError(f"{name} must not be empty")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} values must be non-empty")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} values must be unique")


def _canonical_id(prefix: str, payload: Mapping[str, JSONValue]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:32]}"


def _datetime(data: Mapping[str, object], key: str) -> datetime:
    value = parse_datetime(cast(str | datetime | None, data.get(key)))
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _optional_datetime(data: Mapping[str, object], key: str) -> datetime | None:
    return parse_datetime(cast(str | datetime | None, data.get(key)))


def _optional_text(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    return str(value) if value is not None and str(value) else None


def _strings(data: Mapping[str, object], key: str) -> tuple[str, ...]:
    values = cast(tuple[object, ...] | list[object], data.get(key, ()))
    return tuple(str(value) for value in values)


def _event(
    *,
    event_id: str,
    event_type: str,
    source: str,
    subject: str,
    timestamp: datetime,
    payload: Mapping[str, JSONValue],
    causation_id: str | None = None,
) -> Event:
    return Event(
        id=event_id,
        type=event_type,
        source=source,
        subject=subject,
        timestamp=timestamp,
        payload=payload,
        causation_id=causation_id,
    )


@dataclass(frozen=True, slots=True)
class OriginProvenance:
    provenance_id: str
    kind: OriginKind
    principal_id: str
    authentication_ref: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.provenance_id, "origin provenance id"),
            (self.principal_id, "origin principal id"),
            (self.authentication_ref, "origin authentication ref"),
        ):
            _require_text(value, name)

    def to_dict(self) -> JSONObject:
        return {
            "provenance_id": self.provenance_id,
            "kind": self.kind.value,
            "principal_id": self.principal_id,
            "authentication_ref": self.authentication_ref,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> OriginProvenance:
        return cls(
            provenance_id=str(data["provenance_id"]),
            kind=OriginKind(str(data["kind"])),
            principal_id=str(data["principal_id"]),
            authentication_ref=str(data["authentication_ref"]),
        )


@dataclass(frozen=True, slots=True)
class IntentAuthority:
    authority_id: str
    principal_id: str
    scope: IntentAuthorityScope
    allowed_goal_kinds: tuple[GoalKind, ...]
    goal_refs: tuple[str, ...]
    provenance_ref: str

    def __post_init__(self) -> None:
        _require_text(self.authority_id, "intent authority id")
        _require_text(self.principal_id, "intent authority principal")
        _require_text(self.provenance_ref, "intent authority provenance")
        if not self.allowed_goal_kinds:
            raise ValueError("intent authority must allow at least one goal kind")
        if len(set(self.allowed_goal_kinds)) != len(self.allowed_goal_kinds):
            raise ValueError("intent authority goal kinds must be unique")
        _unique(self.goal_refs, "intent authority goal refs")

    def to_dict(self) -> JSONObject:
        return {
            "authority_id": self.authority_id,
            "principal_id": self.principal_id,
            "scope": self.scope.value,
            "allowed_goal_kinds": [value.value for value in self.allowed_goal_kinds],
            "goal_refs": list(self.goal_refs),
            "provenance_ref": self.provenance_ref,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> IntentAuthority:
        kinds = cast(tuple[object, ...] | list[object], data["allowed_goal_kinds"])
        return cls(
            authority_id=str(data["authority_id"]),
            principal_id=str(data["principal_id"]),
            scope=IntentAuthorityScope(str(data["scope"])),
            allowed_goal_kinds=tuple(GoalKind(str(value)) for value in kinds),
            goal_refs=_strings(data, "goal_refs"),
            provenance_ref=str(data["provenance_ref"]),
        )


@dataclass(frozen=True, slots=True)
class GoalRevision:
    revision_id: str
    goal_id: str
    version: int
    description: str
    priority: float
    utility: float
    success_criteria: tuple[str, ...]
    owner: str
    status: GoalStatus
    deadline: datetime | None
    kind: GoalKind
    governing_goal_refs: tuple[str, ...]
    origin: OriginProvenance
    intent_authority: IntentAuthority
    based_on_event_cursor: int
    author: str
    revision_reason: str
    recorded_at: datetime
    supersedes_revision_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        goal_id: str,
        version: int,
        description: str,
        priority: float,
        utility: float,
        success_criteria: tuple[str, ...],
        owner: str,
        status: GoalStatus,
        deadline: datetime | None,
        kind: GoalKind,
        governing_goal_refs: tuple[str, ...],
        origin: OriginProvenance,
        intent_authority: IntentAuthority,
        based_on_event_cursor: int,
        author: str,
        revision_reason: str,
        recorded_at: datetime,
        supersedes_revision_id: str | None = None,
    ) -> GoalRevision:
        identity: JSONObject = {
            "goal_id": goal_id,
            "version": version,
            "description": description,
            "priority": priority,
            "utility": utility,
            "success_criteria": list(success_criteria),
            "owner": owner,
            "status": status.value,
            "deadline": deadline.isoformat() if deadline else None,
            "kind": kind.value,
            "governing_goal_refs": list(governing_goal_refs),
            "origin": origin.to_dict(),
            "intent_authority": intent_authority.to_dict(),
            "based_on_event_cursor": based_on_event_cursor,
            "author": author,
            "revision_reason": revision_reason,
            "recorded_at": recorded_at.isoformat(),
            "supersedes_revision_id": supersedes_revision_id,
        }
        return cls(
            revision_id=_canonical_id("goal-revision", identity),
            goal_id=goal_id,
            version=version,
            description=description,
            priority=priority,
            utility=utility,
            success_criteria=success_criteria,
            owner=owner,
            status=status,
            deadline=deadline,
            kind=kind,
            governing_goal_refs=governing_goal_refs,
            origin=origin,
            intent_authority=intent_authority,
            based_on_event_cursor=based_on_event_cursor,
            author=author,
            revision_reason=revision_reason,
            recorded_at=recorded_at,
            supersedes_revision_id=supersedes_revision_id,
        )

    def __post_init__(self) -> None:
        _require_text(self.revision_id, "goal revision id")
        _require_text(self.goal_id, "goal id")
        _require_text(self.description, "goal description")
        _require_text(self.owner, "goal owner")
        _require_text(self.author, "goal revision author")
        _require_text(self.revision_reason, "goal revision reason")
        if self.version <= 0:
            raise ValueError("goal revision version must be positive")
        if self.based_on_event_cursor < 0:
            raise ValueError("goal revision cursor cannot be negative")
        _bounded(self.priority, "goal priority")
        if not math.isfinite(self.utility):
            raise ValueError("goal utility must be finite")
        _unique(
            self.success_criteria,
            "goal success criteria",
            required=self.kind is not GoalKind.LEGACY_UNCLASSIFIED,
        )
        _unique(self.governing_goal_refs, "governing goal refs")
        if self.deadline is not None:
            _aware(self.deadline, "goal deadline")
        _aware(self.recorded_at, "goal revision recorded_at")

    def to_dict(self) -> JSONObject:
        return {
            "revision_id": self.revision_id,
            "goal_id": self.goal_id,
            "version": self.version,
            "description": self.description,
            "priority": self.priority,
            "utility": self.utility,
            "success_criteria": list(self.success_criteria),
            "owner": self.owner,
            "status": self.status.value,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "kind": self.kind.value,
            "governing_goal_refs": list(self.governing_goal_refs),
            "origin": self.origin.to_dict(),
            "intent_authority": self.intent_authority.to_dict(),
            "based_on_event_cursor": self.based_on_event_cursor,
            "author": self.author,
            "revision_reason": self.revision_reason,
            "recorded_at": self.recorded_at.isoformat(),
            "supersedes_revision_id": self.supersedes_revision_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> GoalRevision:
        revision = cls(
            revision_id=str(data["revision_id"]),
            goal_id=str(data["goal_id"]),
            version=int(cast(int, data["version"])),
            description=str(data["description"]),
            priority=float(cast(float, data["priority"])),
            utility=float(cast(float, data["utility"])),
            success_criteria=_strings(data, "success_criteria"),
            owner=str(data["owner"]),
            status=GoalStatus(str(data["status"])),
            deadline=_optional_datetime(data, "deadline"),
            kind=GoalKind(str(data["kind"])),
            governing_goal_refs=_strings(data, "governing_goal_refs"),
            origin=OriginProvenance.from_dict(cast(Mapping[str, object], data["origin"])),
            intent_authority=IntentAuthority.from_dict(
                cast(Mapping[str, object], data["intent_authority"])
            ),
            based_on_event_cursor=int(cast(int, data["based_on_event_cursor"])),
            author=str(data["author"]),
            revision_reason=str(data["revision_reason"]),
            recorded_at=_datetime(data, "recorded_at"),
            supersedes_revision_id=_optional_text(data, "supersedes_revision_id"),
        )
        expected = cls.create(
            goal_id=revision.goal_id,
            version=revision.version,
            description=revision.description,
            priority=revision.priority,
            utility=revision.utility,
            success_criteria=revision.success_criteria,
            owner=revision.owner,
            status=revision.status,
            deadline=revision.deadline,
            kind=revision.kind,
            governing_goal_refs=revision.governing_goal_refs,
            origin=revision.origin,
            intent_authority=revision.intent_authority,
            based_on_event_cursor=revision.based_on_event_cursor,
            author=revision.author,
            revision_reason=revision.revision_reason,
            recorded_at=revision.recorded_at,
            supersedes_revision_id=revision.supersedes_revision_id,
        )
        if revision.revision_id != expected.revision_id:
            raise ValueError("goal revision id does not match immutable content")
        return revision

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"goal-revision-recorded:{self.revision_id}",
            event_type=GOAL_REVISION_RECORDED_EVENT,
            source=source,
            subject=self.goal_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )


@dataclass(frozen=True, slots=True)
class OutcomeNode:
    node_id: str
    description: str
    success_criteria: tuple[str, ...]
    approximate_dependencies: tuple[str, ...] = ()
    assumption_refs: tuple[str, ...] = ()
    confidence: float = 1.0

    def __post_init__(self) -> None:
        _require_text(self.node_id, "outcome node id")
        _require_text(self.description, "outcome node description")
        _unique(self.success_criteria, "outcome success criteria", required=True)
        _unique(self.approximate_dependencies, "outcome dependencies")
        _unique(self.assumption_refs, "outcome assumption refs")
        _bounded(self.confidence, "outcome confidence")
        if self.node_id in self.approximate_dependencies:
            raise ValueError("outcome node cannot depend on itself")

    def to_dict(self) -> JSONObject:
        return {
            "node_id": self.node_id,
            "description": self.description,
            "success_criteria": list(self.success_criteria),
            "approximate_dependencies": list(self.approximate_dependencies),
            "assumption_refs": list(self.assumption_refs),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> OutcomeNode:
        return cls(
            node_id=str(data["node_id"]),
            description=str(data["description"]),
            success_criteria=_strings(data, "success_criteria"),
            approximate_dependencies=_strings(data, "approximate_dependencies"),
            assumption_refs=_strings(data, "assumption_refs"),
            confidence=float(cast(float, data["confidence"])),
        )


@dataclass(frozen=True, slots=True)
class RoadmapRevision:
    revision_id: str
    roadmap_id: str
    version: int
    governing_goal_revision_ids: tuple[str, ...]
    outcome_nodes: tuple[OutcomeNode, ...]
    assumptions: tuple[str, ...]
    confidence: float
    success_criteria: tuple[str, ...]
    resource_envelope: Mapping[str, float]
    intent_authority: IntentAuthority
    based_on_event_cursor: int
    author: str
    revision_reason: str
    recorded_at: datetime
    supersedes_revision_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        roadmap_id: str,
        version: int,
        governing_goal_revision_ids: tuple[str, ...],
        outcome_nodes: tuple[OutcomeNode, ...],
        assumptions: tuple[str, ...],
        confidence: float,
        success_criteria: tuple[str, ...],
        resource_envelope: Mapping[str, float],
        intent_authority: IntentAuthority,
        based_on_event_cursor: int,
        author: str,
        revision_reason: str,
        recorded_at: datetime,
        supersedes_revision_id: str | None = None,
    ) -> RoadmapRevision:
        ordered_nodes = tuple(sorted(outcome_nodes, key=lambda value: value.node_id))
        identity: JSONObject = {
            "roadmap_id": roadmap_id,
            "version": version,
            "governing_goal_revision_ids": list(governing_goal_revision_ids),
            "outcome_nodes": [value.to_dict() for value in ordered_nodes],
            "assumptions": list(assumptions),
            "confidence": confidence,
            "success_criteria": list(success_criteria),
            "resource_envelope": dict(sorted(resource_envelope.items())),
            "intent_authority": intent_authority.to_dict(),
            "based_on_event_cursor": based_on_event_cursor,
            "author": author,
            "revision_reason": revision_reason,
            "recorded_at": recorded_at.isoformat(),
            "supersedes_revision_id": supersedes_revision_id,
        }
        return cls(
            revision_id=_canonical_id("roadmap-revision", identity),
            roadmap_id=roadmap_id,
            version=version,
            governing_goal_revision_ids=governing_goal_revision_ids,
            outcome_nodes=ordered_nodes,
            assumptions=assumptions,
            confidence=confidence,
            success_criteria=success_criteria,
            resource_envelope=dict(sorted(resource_envelope.items())),
            intent_authority=intent_authority,
            based_on_event_cursor=based_on_event_cursor,
            author=author,
            revision_reason=revision_reason,
            recorded_at=recorded_at,
            supersedes_revision_id=supersedes_revision_id,
        )

    def __post_init__(self) -> None:
        _require_text(self.revision_id, "roadmap revision id")
        _require_text(self.roadmap_id, "roadmap id")
        _require_text(self.author, "roadmap author")
        _require_text(self.revision_reason, "roadmap revision reason")
        if self.version <= 0 or self.based_on_event_cursor < 0:
            raise ValueError("roadmap version must be positive and cursor non-negative")
        _unique(self.governing_goal_revision_ids, "governing goal revisions", required=True)
        _unique(self.assumptions, "roadmap assumptions")
        _unique(self.success_criteria, "roadmap success criteria", required=True)
        _bounded(self.confidence, "roadmap confidence")
        _aware(self.recorded_at, "roadmap recorded_at")
        node_ids = tuple(value.node_id for value in self.outcome_nodes)
        _unique(node_ids, "roadmap outcome ids", required=True)
        resources = dict(sorted(self.resource_envelope.items()))
        if any(not key.strip() for key in resources):
            raise ValueError("roadmap resource envelope keys must be non-empty")
        if any(not math.isfinite(value) or value < 0 for value in resources.values()):
            raise ValueError("roadmap resource envelope values must be finite and non-negative")
        object.__setattr__(self, "resource_envelope", MappingProxyType(resources))

    def to_dict(self) -> JSONObject:
        return {
            "revision_id": self.revision_id,
            "roadmap_id": self.roadmap_id,
            "version": self.version,
            "governing_goal_revision_ids": list(self.governing_goal_revision_ids),
            "outcome_nodes": [value.to_dict() for value in self.outcome_nodes],
            "assumptions": list(self.assumptions),
            "confidence": self.confidence,
            "success_criteria": list(self.success_criteria),
            "resource_envelope": dict(self.resource_envelope),
            "intent_authority": self.intent_authority.to_dict(),
            "based_on_event_cursor": self.based_on_event_cursor,
            "author": self.author,
            "revision_reason": self.revision_reason,
            "recorded_at": self.recorded_at.isoformat(),
            "supersedes_revision_id": self.supersedes_revision_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RoadmapRevision:
        nodes = cast(tuple[object, ...] | list[object], data["outcome_nodes"])
        resources = cast(Mapping[str, object], data["resource_envelope"])
        revision = cls(
            revision_id=str(data["revision_id"]),
            roadmap_id=str(data["roadmap_id"]),
            version=int(cast(int, data["version"])),
            governing_goal_revision_ids=_strings(data, "governing_goal_revision_ids"),
            outcome_nodes=tuple(
                OutcomeNode.from_dict(cast(Mapping[str, object], value)) for value in nodes
            ),
            assumptions=_strings(data, "assumptions"),
            confidence=float(cast(float, data["confidence"])),
            success_criteria=_strings(data, "success_criteria"),
            resource_envelope={key: float(cast(float, value)) for key, value in resources.items()},
            intent_authority=IntentAuthority.from_dict(
                cast(Mapping[str, object], data["intent_authority"])
            ),
            based_on_event_cursor=int(cast(int, data["based_on_event_cursor"])),
            author=str(data["author"]),
            revision_reason=str(data["revision_reason"]),
            recorded_at=_datetime(data, "recorded_at"),
            supersedes_revision_id=_optional_text(data, "supersedes_revision_id"),
        )
        expected = cls.create(
            roadmap_id=revision.roadmap_id,
            version=revision.version,
            governing_goal_revision_ids=revision.governing_goal_revision_ids,
            outcome_nodes=revision.outcome_nodes,
            assumptions=revision.assumptions,
            confidence=revision.confidence,
            success_criteria=revision.success_criteria,
            resource_envelope=revision.resource_envelope,
            intent_authority=revision.intent_authority,
            based_on_event_cursor=revision.based_on_event_cursor,
            author=revision.author,
            revision_reason=revision.revision_reason,
            recorded_at=revision.recorded_at,
            supersedes_revision_id=revision.supersedes_revision_id,
        )
        if revision.revision_id != expected.revision_id:
            raise ValueError("roadmap revision id does not match immutable content")
        return revision

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"roadmap-revision-recorded:{self.revision_id}",
            event_type=ROADMAP_REVISION_RECORDED_EVENT,
            source=source,
            subject=self.roadmap_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )

    def node(self, node_id: str) -> OutcomeNode:
        return next(value for value in self.outcome_nodes if value.node_id == node_id)


@dataclass(frozen=True, slots=True)
class Roadmap:
    roadmap_id: str
    current_revision_id: str
    version: int


@dataclass(frozen=True, slots=True)
class CommitmentTransition:
    transition_id: str
    commitment_id: str
    from_state: CommitmentStatus
    to_state: CommitmentStatus
    closure_reason: CommitmentClosureReason | None
    based_on_event_cursor: int
    author: str
    reason: str
    transitioned_at: datetime
    reactivation_roadmap_revision_id: str | None = None
    reactivation_role_assignment_id: str | None = None
    reactivation_assistance_envelope_id: str | None = None
    reorientation_evidence_refs: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        commitment_id: str,
        from_state: CommitmentStatus,
        to_state: CommitmentStatus,
        closure_reason: CommitmentClosureReason | None,
        based_on_event_cursor: int,
        author: str,
        reason: str,
        transitioned_at: datetime,
        reactivation_roadmap_revision_id: str | None = None,
        reactivation_role_assignment_id: str | None = None,
        reactivation_assistance_envelope_id: str | None = None,
        reorientation_evidence_refs: tuple[str, ...] = (),
    ) -> CommitmentTransition:
        identity: JSONObject = {
            "commitment_id": commitment_id,
            "from_state": from_state.value,
            "to_state": to_state.value,
            "closure_reason": closure_reason.value if closure_reason else None,
            "based_on_event_cursor": based_on_event_cursor,
            "author": author,
            "reason": reason,
            "transitioned_at": transitioned_at.isoformat(),
            "reactivation_roadmap_revision_id": reactivation_roadmap_revision_id,
            "reactivation_role_assignment_id": reactivation_role_assignment_id,
            "reactivation_assistance_envelope_id": reactivation_assistance_envelope_id,
            "reorientation_evidence_refs": list(reorientation_evidence_refs),
        }
        return cls(
            transition_id=_canonical_id("commitment-transition", identity),
            commitment_id=commitment_id,
            from_state=from_state,
            to_state=to_state,
            closure_reason=closure_reason,
            based_on_event_cursor=based_on_event_cursor,
            author=author,
            reason=reason,
            transitioned_at=transitioned_at,
            reactivation_roadmap_revision_id=reactivation_roadmap_revision_id,
            reactivation_role_assignment_id=reactivation_role_assignment_id,
            reactivation_assistance_envelope_id=reactivation_assistance_envelope_id,
            reorientation_evidence_refs=reorientation_evidence_refs,
        )

    def __post_init__(self) -> None:
        _require_text(self.transition_id, "commitment transition id")
        _require_text(self.commitment_id, "commitment id")
        _require_text(self.author, "commitment transition author")
        _require_text(self.reason, "commitment transition reason")
        if self.based_on_event_cursor < 0:
            raise ValueError("commitment transition cursor cannot be negative")
        _unique(self.reorientation_evidence_refs, "reorientation evidence refs")
        _aware(self.transitioned_at, "commitment transitioned_at")

    def to_dict(self) -> JSONObject:
        return {
            "transition_id": self.transition_id,
            "commitment_id": self.commitment_id,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "closure_reason": self.closure_reason.value if self.closure_reason else None,
            "based_on_event_cursor": self.based_on_event_cursor,
            "author": self.author,
            "reason": self.reason,
            "transitioned_at": self.transitioned_at.isoformat(),
            "reactivation_roadmap_revision_id": self.reactivation_roadmap_revision_id,
            "reactivation_role_assignment_id": self.reactivation_role_assignment_id,
            "reactivation_assistance_envelope_id": (self.reactivation_assistance_envelope_id),
            "reorientation_evidence_refs": list(self.reorientation_evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CommitmentTransition:
        closure = _optional_text(data, "closure_reason")
        transition = cls(
            transition_id=str(data["transition_id"]),
            commitment_id=str(data["commitment_id"]),
            from_state=CommitmentStatus(str(data["from_state"])),
            to_state=CommitmentStatus(str(data["to_state"])),
            closure_reason=CommitmentClosureReason(closure) if closure else None,
            based_on_event_cursor=int(cast(int, data["based_on_event_cursor"])),
            author=str(data["author"]),
            reason=str(data["reason"]),
            transitioned_at=_datetime(data, "transitioned_at"),
            reactivation_roadmap_revision_id=_optional_text(
                data, "reactivation_roadmap_revision_id"
            ),
            reactivation_role_assignment_id=_optional_text(data, "reactivation_role_assignment_id"),
            reactivation_assistance_envelope_id=_optional_text(
                data, "reactivation_assistance_envelope_id"
            ),
            reorientation_evidence_refs=_strings(data, "reorientation_evidence_refs"),
        )
        expected = cls.create(
            commitment_id=transition.commitment_id,
            from_state=transition.from_state,
            to_state=transition.to_state,
            closure_reason=transition.closure_reason,
            based_on_event_cursor=transition.based_on_event_cursor,
            author=transition.author,
            reason=transition.reason,
            transitioned_at=transition.transitioned_at,
            reactivation_roadmap_revision_id=(transition.reactivation_roadmap_revision_id),
            reactivation_role_assignment_id=transition.reactivation_role_assignment_id,
            reactivation_assistance_envelope_id=(transition.reactivation_assistance_envelope_id),
            reorientation_evidence_refs=transition.reorientation_evidence_refs,
        )
        if transition.transition_id != expected.transition_id:
            raise ValueError("commitment transition id does not match immutable content")
        return transition

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"commitment-transitioned:{self.transition_id}",
            event_type=COMMITMENT_TRANSITIONED_EVENT,
            source=source,
            subject=self.commitment_id,
            timestamp=self.transitioned_at,
            payload=self.to_dict(),
        )


def commitment_to_dict(value: Commitment) -> JSONObject:
    return {
        "id": value.id,
        "description": value.description,
        "owner": value.owner,
        "priority": value.priority,
        "status": value.status.value,
        "deadline": value.deadline.isoformat() if value.deadline else None,
        "terminal": value.terminal,
        "attention_cost": value.attention_cost,
        "social_cost_of_failure": value.social_cost_of_failure,
        "created_at": value.created_at.isoformat(),
        "updated_at": value.updated_at.isoformat(),
        "closure_reason": value.closure_reason.value if value.closure_reason else None,
        "governing_goal_refs": list(value.governing_goal_refs),
        "roadmap_revision_id": value.roadmap_revision_id,
        "outcome_node_id": value.outcome_node_id,
        "role_assignment_id": value.role_assignment_id,
        "assistance_envelope_id": value.assistance_envelope_id,
        "activation_due_at": (
            value.activation_due_at.isoformat() if value.activation_due_at else None
        ),
        "lead_time_evidence_refs": list(value.lead_time_evidence_refs),
    }


def commitment_from_dict(data: Mapping[str, object]) -> Commitment:
    closure = _optional_text(data, "closure_reason")
    return Commitment(
        id=str(data["id"]),
        description=str(data["description"]),
        owner=str(data["owner"]),
        priority=float(cast(float, data.get("priority", 0.5))),
        status=CommitmentStatus(str(data.get("status", CommitmentStatus.ACCEPTED))),
        deadline=_optional_datetime(data, "deadline"),
        terminal=bool(data.get("terminal", True)),
        attention_cost=float(cast(float, data.get("attention_cost", 1.0))),
        social_cost_of_failure=float(cast(float, data.get("social_cost_of_failure", 0.0))),
        created_at=_datetime(data, "created_at"),
        updated_at=_datetime(data, "updated_at"),
        closure_reason=CommitmentClosureReason(closure) if closure else None,
        governing_goal_refs=_strings(data, "governing_goal_refs"),
        roadmap_revision_id=_optional_text(data, "roadmap_revision_id"),
        outcome_node_id=_optional_text(data, "outcome_node_id"),
        role_assignment_id=_optional_text(data, "role_assignment_id"),
        assistance_envelope_id=_optional_text(data, "assistance_envelope_id"),
        activation_due_at=_optional_datetime(data, "activation_due_at"),
        lead_time_evidence_refs=_strings(data, "lead_time_evidence_refs"),
    )


def commitment_recorded_event(value: Commitment, *, source: str) -> Event:
    return _event(
        event_id=f"commitment-recorded:{value.id}",
        event_type=COMMITMENT_RECORDED_EVENT,
        source=source,
        subject=value.id,
        timestamp=value.created_at,
        payload=commitment_to_dict(value),
    )


@dataclass(frozen=True, slots=True)
class OutcomeActor:
    actor_id: str
    locus: ExecutionLocus

    def __post_init__(self) -> None:
        _require_text(self.actor_id, "outcome actor id")

    def to_dict(self) -> JSONObject:
        return {"actor_id": self.actor_id, "locus": self.locus.value}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> OutcomeActor:
        return cls(actor_id=str(data["actor_id"]), locus=ExecutionLocus(str(data["locus"])))


@dataclass(frozen=True, slots=True)
class OutcomeRoleAssignment:
    assignment_id: str
    outcome_ref: str
    outcome_owner: OutcomeActor
    decision_owner: OutcomeActor
    executor: OutcomeActor
    verifier: OutcomeActor
    recorded_at: datetime

    @classmethod
    def create(
        cls,
        *,
        outcome_ref: str,
        outcome_owner: OutcomeActor,
        decision_owner: OutcomeActor,
        executor: OutcomeActor,
        verifier: OutcomeActor,
        recorded_at: datetime,
    ) -> OutcomeRoleAssignment:
        identity: JSONObject = {
            "outcome_ref": outcome_ref,
            "outcome_owner": outcome_owner.to_dict(),
            "decision_owner": decision_owner.to_dict(),
            "executor": executor.to_dict(),
            "verifier": verifier.to_dict(),
            "recorded_at": recorded_at.isoformat(),
        }
        return cls(
            assignment_id=_canonical_id("outcome-roles", identity),
            outcome_ref=outcome_ref,
            outcome_owner=outcome_owner,
            decision_owner=decision_owner,
            executor=executor,
            verifier=verifier,
            recorded_at=recorded_at,
        )

    def __post_init__(self) -> None:
        _require_text(self.assignment_id, "outcome role assignment id")
        _require_text(self.outcome_ref, "outcome ref")
        _aware(self.recorded_at, "outcome roles recorded_at")

    def to_dict(self) -> JSONObject:
        return {
            "assignment_id": self.assignment_id,
            "outcome_ref": self.outcome_ref,
            "outcome_owner": self.outcome_owner.to_dict(),
            "decision_owner": self.decision_owner.to_dict(),
            "executor": self.executor.to_dict(),
            "verifier": self.verifier.to_dict(),
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> OutcomeRoleAssignment:
        assignment = cls(
            assignment_id=str(data["assignment_id"]),
            outcome_ref=str(data["outcome_ref"]),
            outcome_owner=OutcomeActor.from_dict(cast(Mapping[str, object], data["outcome_owner"])),
            decision_owner=OutcomeActor.from_dict(
                cast(Mapping[str, object], data["decision_owner"])
            ),
            executor=OutcomeActor.from_dict(cast(Mapping[str, object], data["executor"])),
            verifier=OutcomeActor.from_dict(cast(Mapping[str, object], data["verifier"])),
            recorded_at=_datetime(data, "recorded_at"),
        )
        expected = cls.create(
            outcome_ref=assignment.outcome_ref,
            outcome_owner=assignment.outcome_owner,
            decision_owner=assignment.decision_owner,
            executor=assignment.executor,
            verifier=assignment.verifier,
            recorded_at=assignment.recorded_at,
        )
        if assignment.assignment_id != expected.assignment_id:
            raise ValueError("outcome role id does not match immutable content")
        return assignment

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"outcome-roles-recorded:{self.assignment_id}",
            event_type=OUTCOME_ROLES_RECORDED_EVENT,
            source=source,
            subject=self.outcome_ref,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )


@dataclass(frozen=True, slots=True)
class AssistanceEnvelope:
    envelope_id: str
    role_assignment_id: str
    maximum_intervention: InterventionLevel
    identity_bound: bool
    physical_presence_required: bool
    relationship_bound: bool
    institutional_restrictions: tuple[str, ...]
    user_development_value: float
    permitted_agent_support: tuple[str, ...]
    required_human_work: tuple[str, ...]
    checkpoints: tuple[str, ...]
    reversible: bool
    risk_limit: float
    privacy_limit: float
    attention_budget: float
    recorded_at: datetime

    @classmethod
    def create(
        cls,
        *,
        role_assignment_id: str,
        maximum_intervention: InterventionLevel,
        identity_bound: bool,
        physical_presence_required: bool,
        relationship_bound: bool,
        institutional_restrictions: tuple[str, ...],
        user_development_value: float,
        permitted_agent_support: tuple[str, ...],
        required_human_work: tuple[str, ...],
        checkpoints: tuple[str, ...],
        reversible: bool,
        risk_limit: float,
        privacy_limit: float,
        attention_budget: float,
        recorded_at: datetime,
    ) -> AssistanceEnvelope:
        payload: JSONObject = {
            "role_assignment_id": role_assignment_id,
            "maximum_intervention": maximum_intervention.value,
            "identity_bound": identity_bound,
            "physical_presence_required": physical_presence_required,
            "relationship_bound": relationship_bound,
            "institutional_restrictions": list(institutional_restrictions),
            "user_development_value": user_development_value,
            "permitted_agent_support": list(permitted_agent_support),
            "required_human_work": list(required_human_work),
            "checkpoints": list(checkpoints),
            "reversible": reversible,
            "risk_limit": risk_limit,
            "privacy_limit": privacy_limit,
            "attention_budget": attention_budget,
            "recorded_at": recorded_at.isoformat(),
        }
        return cls(
            envelope_id=_canonical_id("assistance-envelope", payload),
            role_assignment_id=role_assignment_id,
            maximum_intervention=maximum_intervention,
            identity_bound=identity_bound,
            physical_presence_required=physical_presence_required,
            relationship_bound=relationship_bound,
            institutional_restrictions=institutional_restrictions,
            user_development_value=user_development_value,
            permitted_agent_support=permitted_agent_support,
            required_human_work=required_human_work,
            checkpoints=checkpoints,
            reversible=reversible,
            risk_limit=risk_limit,
            privacy_limit=privacy_limit,
            attention_budget=attention_budget,
            recorded_at=recorded_at,
        )

    def __post_init__(self) -> None:
        _require_text(self.envelope_id, "assistance envelope id")
        _require_text(self.role_assignment_id, "assistance role assignment ref")
        _unique(self.institutional_restrictions, "institutional restrictions")
        _unique(self.permitted_agent_support, "permitted agent support")
        _unique(self.required_human_work, "required human work")
        _unique(self.checkpoints, "assistance checkpoints")
        for value, name in (
            (self.user_development_value, "user development value"),
            (self.risk_limit, "risk limit"),
            (self.privacy_limit, "privacy limit"),
        ):
            _bounded(value, name)
        if not math.isfinite(self.attention_budget) or self.attention_budget < 0:
            raise ValueError("attention budget must be finite and non-negative")
        _aware(self.recorded_at, "assistance envelope recorded_at")

    def to_dict(self) -> JSONObject:
        return {
            "envelope_id": self.envelope_id,
            "role_assignment_id": self.role_assignment_id,
            "maximum_intervention": self.maximum_intervention.value,
            "identity_bound": self.identity_bound,
            "physical_presence_required": self.physical_presence_required,
            "relationship_bound": self.relationship_bound,
            "institutional_restrictions": list(self.institutional_restrictions),
            "user_development_value": self.user_development_value,
            "permitted_agent_support": list(self.permitted_agent_support),
            "required_human_work": list(self.required_human_work),
            "checkpoints": list(self.checkpoints),
            "reversible": self.reversible,
            "risk_limit": self.risk_limit,
            "privacy_limit": self.privacy_limit,
            "attention_budget": self.attention_budget,
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AssistanceEnvelope:
        envelope = cls(
            envelope_id=str(data["envelope_id"]),
            role_assignment_id=str(data["role_assignment_id"]),
            maximum_intervention=InterventionLevel(str(data["maximum_intervention"])),
            identity_bound=bool(data["identity_bound"]),
            physical_presence_required=bool(data["physical_presence_required"]),
            relationship_bound=bool(data["relationship_bound"]),
            institutional_restrictions=_strings(data, "institutional_restrictions"),
            user_development_value=float(cast(float, data["user_development_value"])),
            permitted_agent_support=_strings(data, "permitted_agent_support"),
            required_human_work=_strings(data, "required_human_work"),
            checkpoints=_strings(data, "checkpoints"),
            reversible=bool(data["reversible"]),
            risk_limit=float(cast(float, data["risk_limit"])),
            privacy_limit=float(cast(float, data["privacy_limit"])),
            attention_budget=float(cast(float, data["attention_budget"])),
            recorded_at=_datetime(data, "recorded_at"),
        )
        expected = cls.create(
            role_assignment_id=envelope.role_assignment_id,
            maximum_intervention=envelope.maximum_intervention,
            identity_bound=envelope.identity_bound,
            physical_presence_required=envelope.physical_presence_required,
            relationship_bound=envelope.relationship_bound,
            institutional_restrictions=envelope.institutional_restrictions,
            user_development_value=envelope.user_development_value,
            permitted_agent_support=envelope.permitted_agent_support,
            required_human_work=envelope.required_human_work,
            checkpoints=envelope.checkpoints,
            reversible=envelope.reversible,
            risk_limit=envelope.risk_limit,
            privacy_limit=envelope.privacy_limit,
            attention_budget=envelope.attention_budget,
            recorded_at=envelope.recorded_at,
        )
        if envelope.envelope_id != expected.envelope_id:
            raise ValueError("assistance envelope id does not match immutable content")
        return envelope

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"assistance-envelope-recorded:{self.envelope_id}",
            event_type=ASSISTANCE_ENVELOPE_RECORDED_EVENT,
            source=source,
            subject=self.role_assignment_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )


@dataclass(frozen=True, slots=True)
class ExternalWorkstream:
    observation_id: str
    workstream_id: str
    source_of_truth_id: str
    observed_roadmap_ref: str
    provenance_refs: tuple[str, ...]
    valid_at: datetime
    recorded_at: datetime
    confidence: float
    freshness_expires_at: datetime
    user_role: str
    noema_role: str
    support_commitment_refs: tuple[str, ...]
    support_required: bool

    @classmethod
    def create(
        cls,
        *,
        workstream_id: str,
        source_of_truth_id: str,
        observed_roadmap_ref: str,
        provenance_refs: tuple[str, ...],
        valid_at: datetime,
        recorded_at: datetime,
        confidence: float,
        freshness_expires_at: datetime,
        user_role: str,
        noema_role: str,
        support_commitment_refs: tuple[str, ...],
        support_required: bool,
    ) -> ExternalWorkstream:
        payload: JSONObject = {
            "workstream_id": workstream_id,
            "source_of_truth_id": source_of_truth_id,
            "observed_roadmap_ref": observed_roadmap_ref,
            "provenance_refs": list(provenance_refs),
            "valid_at": valid_at.isoformat(),
            "recorded_at": recorded_at.isoformat(),
            "confidence": confidence,
            "freshness_expires_at": freshness_expires_at.isoformat(),
            "user_role": user_role,
            "noema_role": noema_role,
            "support_commitment_refs": list(support_commitment_refs),
            "support_required": support_required,
        }
        return cls(
            observation_id=_canonical_id("external-workstream", payload),
            workstream_id=workstream_id,
            source_of_truth_id=source_of_truth_id,
            observed_roadmap_ref=observed_roadmap_ref,
            provenance_refs=provenance_refs,
            valid_at=valid_at,
            recorded_at=recorded_at,
            confidence=confidence,
            freshness_expires_at=freshness_expires_at,
            user_role=user_role,
            noema_role=noema_role,
            support_commitment_refs=support_commitment_refs,
            support_required=support_required,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.observation_id, "external observation id"),
            (self.workstream_id, "external workstream id"),
            (self.source_of_truth_id, "external source-of-truth id"),
            (self.observed_roadmap_ref, "external roadmap ref"),
            (self.user_role, "external workstream user role"),
            (self.noema_role, "external workstream Noema role"),
        ):
            _require_text(value, name)
        _unique(self.provenance_refs, "external provenance refs", required=True)
        _unique(self.support_commitment_refs, "external support commitment refs")
        _aware(self.valid_at, "external valid_at")
        _aware(self.recorded_at, "external recorded_at")
        _aware(self.freshness_expires_at, "external freshness expiry")
        _bounded(self.confidence, "external confidence")
        if self.freshness_expires_at <= self.recorded_at:
            raise ValueError("external freshness expiry must follow recording")

    def to_dict(self) -> JSONObject:
        return {
            "observation_id": self.observation_id,
            "workstream_id": self.workstream_id,
            "source_of_truth_id": self.source_of_truth_id,
            "observed_roadmap_ref": self.observed_roadmap_ref,
            "provenance_refs": list(self.provenance_refs),
            "valid_at": self.valid_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
            "confidence": self.confidence,
            "freshness_expires_at": self.freshness_expires_at.isoformat(),
            "user_role": self.user_role,
            "noema_role": self.noema_role,
            "support_commitment_refs": list(self.support_commitment_refs),
            "support_required": self.support_required,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ExternalWorkstream:
        observation = cls(
            observation_id=str(data["observation_id"]),
            workstream_id=str(data["workstream_id"]),
            source_of_truth_id=str(data["source_of_truth_id"]),
            observed_roadmap_ref=str(data["observed_roadmap_ref"]),
            provenance_refs=_strings(data, "provenance_refs"),
            valid_at=_datetime(data, "valid_at"),
            recorded_at=_datetime(data, "recorded_at"),
            confidence=float(cast(float, data["confidence"])),
            freshness_expires_at=_datetime(data, "freshness_expires_at"),
            user_role=str(data["user_role"]),
            noema_role=str(data["noema_role"]),
            support_commitment_refs=_strings(data, "support_commitment_refs"),
            support_required=bool(data["support_required"]),
        )
        expected = cls.create(
            workstream_id=observation.workstream_id,
            source_of_truth_id=observation.source_of_truth_id,
            observed_roadmap_ref=observation.observed_roadmap_ref,
            provenance_refs=observation.provenance_refs,
            valid_at=observation.valid_at,
            recorded_at=observation.recorded_at,
            confidence=observation.confidence,
            freshness_expires_at=observation.freshness_expires_at,
            user_role=observation.user_role,
            noema_role=observation.noema_role,
            support_commitment_refs=observation.support_commitment_refs,
            support_required=observation.support_required,
        )
        if observation.observation_id != expected.observation_id:
            raise ValueError("external observation id does not match immutable content")
        return observation

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"external-workstream-observed:{self.observation_id}",
            event_type=EXTERNAL_WORKSTREAM_OBSERVED_EVENT,
            source=source,
            subject=self.workstream_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )


@dataclass(frozen=True, slots=True)
class PortfolioSignals:
    expected_goal_value: float
    commitment_strength: float
    urgency: float
    critical_path_pressure: float
    success_estimate: float
    cost: float
    coordination_cost: float
    context_affinity: float
    verification_capacity: float
    wip: int
    scarce_competence_pressure: float
    future_information_access_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.expected_goal_value, "expected goal value"),
            (self.commitment_strength, "commitment strength"),
            (self.urgency, "urgency"),
            (self.critical_path_pressure, "critical path pressure"),
            (self.success_estimate, "success estimate"),
            (self.context_affinity, "context affinity"),
            (self.verification_capacity, "verification capacity"),
            (self.scarce_competence_pressure, "scarce competence pressure"),
        ):
            _bounded(value, name)
        for value, name in ((self.cost, "cost"), (self.coordination_cost, "coordination cost")):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.wip < 0:
            raise ValueError("WIP cannot be negative")
        _unique(
            self.future_information_access_requirements,
            "future information access requirements",
        )

    def to_dict(self) -> JSONObject:
        return {
            "expected_goal_value": self.expected_goal_value,
            "commitment_strength": self.commitment_strength,
            "urgency": self.urgency,
            "critical_path_pressure": self.critical_path_pressure,
            "success_estimate": self.success_estimate,
            "cost": self.cost,
            "coordination_cost": self.coordination_cost,
            "context_affinity": self.context_affinity,
            "verification_capacity": self.verification_capacity,
            "wip": self.wip,
            "scarce_competence_pressure": self.scarce_competence_pressure,
            "future_information_access_requirements": list(
                self.future_information_access_requirements
            ),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PortfolioSignals:
        return cls(
            expected_goal_value=float(cast(float, data["expected_goal_value"])),
            commitment_strength=float(cast(float, data["commitment_strength"])),
            urgency=float(cast(float, data["urgency"])),
            critical_path_pressure=float(cast(float, data["critical_path_pressure"])),
            success_estimate=float(cast(float, data["success_estimate"])),
            cost=float(cast(float, data["cost"])),
            coordination_cost=float(cast(float, data["coordination_cost"])),
            context_affinity=float(cast(float, data["context_affinity"])),
            verification_capacity=float(cast(float, data["verification_capacity"])),
            wip=int(cast(int, data["wip"])),
            scarce_competence_pressure=float(cast(float, data["scarce_competence_pressure"])),
            future_information_access_requirements=_strings(
                data, "future_information_access_requirements"
            ),
        )


@dataclass(frozen=True, slots=True)
class WorkOrderProposal:
    proposal_id: str
    commitment_id: str
    roadmap_revision_id: str
    outcome_node_id: str
    work_order: WorkOrder
    intervention: InterventionLevel
    declared_agent_support: tuple[str, ...]
    eligibility: WorkProposalEligibility
    portfolio_signals: PortfolioSignals
    wip_limit: int
    based_on_event_cursor: int
    proposed_at: datetime
    validator_id: str

    @classmethod
    def create(
        cls,
        *,
        commitment_id: str,
        roadmap_revision_id: str,
        outcome_node_id: str,
        work_order: WorkOrder,
        intervention: InterventionLevel,
        declared_agent_support: tuple[str, ...],
        eligibility: WorkProposalEligibility,
        portfolio_signals: PortfolioSignals,
        wip_limit: int,
        based_on_event_cursor: int,
        proposed_at: datetime,
        validator_id: str,
    ) -> WorkOrderProposal:
        payload: JSONObject = {
            "commitment_id": commitment_id,
            "roadmap_revision_id": roadmap_revision_id,
            "outcome_node_id": outcome_node_id,
            "work_order": work_order.to_dict(),
            "intervention": intervention.value,
            "declared_agent_support": list(declared_agent_support),
            "eligibility": eligibility.value,
            "portfolio_signals": portfolio_signals.to_dict(),
            "wip_limit": wip_limit,
            "based_on_event_cursor": based_on_event_cursor,
            "proposed_at": proposed_at.isoformat(),
            "validator_id": validator_id,
        }
        return cls(
            proposal_id=_canonical_id("work-order-proposal", payload),
            commitment_id=commitment_id,
            roadmap_revision_id=roadmap_revision_id,
            outcome_node_id=outcome_node_id,
            work_order=work_order,
            intervention=intervention,
            declared_agent_support=declared_agent_support,
            eligibility=eligibility,
            portfolio_signals=portfolio_signals,
            wip_limit=wip_limit,
            based_on_event_cursor=based_on_event_cursor,
            proposed_at=proposed_at,
            validator_id=validator_id,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.proposal_id, "work order proposal id"),
            (self.commitment_id, "proposal commitment id"),
            (self.roadmap_revision_id, "proposal roadmap revision id"),
            (self.outcome_node_id, "proposal outcome node id"),
            (self.validator_id, "proposal validator id"),
        ):
            _require_text(value, name)
        if self.based_on_event_cursor < 0:
            raise ValueError("work proposal cursor cannot be negative")
        if self.wip_limit <= 0:
            raise ValueError("work proposal WIP limit must be positive")
        _unique(
            self.declared_agent_support,
            "declared agent support",
            required=True,
        )
        _aware(self.proposed_at, "work proposal proposed_at")

    def to_dict(self) -> JSONObject:
        return {
            "proposal_id": self.proposal_id,
            "commitment_id": self.commitment_id,
            "roadmap_revision_id": self.roadmap_revision_id,
            "outcome_node_id": self.outcome_node_id,
            "work_order": self.work_order.to_dict(),
            "intervention": self.intervention.value,
            "declared_agent_support": list(self.declared_agent_support),
            "eligibility": self.eligibility.value,
            "portfolio_signals": self.portfolio_signals.to_dict(),
            "wip_limit": self.wip_limit,
            "based_on_event_cursor": self.based_on_event_cursor,
            "proposed_at": self.proposed_at.isoformat(),
            "validator_id": self.validator_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> WorkOrderProposal:
        proposal = cls(
            proposal_id=str(data["proposal_id"]),
            commitment_id=str(data["commitment_id"]),
            roadmap_revision_id=str(data["roadmap_revision_id"]),
            outcome_node_id=str(data["outcome_node_id"]),
            work_order=WorkOrder.from_dict(cast(Mapping[str, object], data["work_order"])),
            intervention=InterventionLevel(str(data["intervention"])),
            declared_agent_support=_strings(data, "declared_agent_support"),
            eligibility=WorkProposalEligibility(str(data["eligibility"])),
            portfolio_signals=PortfolioSignals.from_dict(
                cast(Mapping[str, object], data["portfolio_signals"])
            ),
            wip_limit=int(cast(int, data["wip_limit"])),
            based_on_event_cursor=int(cast(int, data["based_on_event_cursor"])),
            proposed_at=_datetime(data, "proposed_at"),
            validator_id=str(data["validator_id"]),
        )
        expected = cls.create(
            commitment_id=proposal.commitment_id,
            roadmap_revision_id=proposal.roadmap_revision_id,
            outcome_node_id=proposal.outcome_node_id,
            work_order=proposal.work_order,
            intervention=proposal.intervention,
            declared_agent_support=proposal.declared_agent_support,
            eligibility=proposal.eligibility,
            portfolio_signals=proposal.portfolio_signals,
            wip_limit=proposal.wip_limit,
            based_on_event_cursor=proposal.based_on_event_cursor,
            proposed_at=proposal.proposed_at,
            validator_id=proposal.validator_id,
        )
        if proposal.proposal_id != expected.proposal_id:
            raise ValueError("work order proposal id does not match immutable content")
        return proposal

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"work-order-proposed:{self.proposal_id}",
            event_type=WORK_ORDER_PROPOSED_EVENT,
            source=source,
            subject=self.commitment_id,
            timestamp=self.proposed_at,
            payload=self.to_dict(),
        )


@dataclass(frozen=True, slots=True)
class CommitmentCoverage:
    commitment_id: str
    disposition: CoverageDisposition
    required_criteria: tuple[str, ...]
    covered_criteria: tuple[str, ...]
    uncovered_criteria: tuple[str, ...]
    work_proposal_ids: tuple[str, ...]
    admitted_work_order_ids: tuple[str, ...]
    external_support_required: bool


@dataclass(frozen=True, slots=True)
class RoadmapHealth:
    roadmap_id: str
    revision_id: str
    goal_alignment: HealthSignal
    assumption_validity: HealthSignal
    dependency_validity: HealthSignal
    progress_consistency: HealthSignal
    schedule_feasibility: HealthSignal
    capacity_fit: HealthSignal
    opportunity_validity: HealthSignal
    review_reasons: tuple[str, ...]

    @property
    def review_required(self) -> bool:
        return bool(self.review_reasons)
