"""Immutable contracts for durable work coordination."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import cast

from ..authority import AuthorityLevel
from ..continuity import ActionPrerequisite
from ..events import Event
from ..information.models import validate_opaque_governance_id
from ..types import JSONObject, JSONValue, parse_datetime

WORK_ORDER_RECORDED_EVENT = "work.order_recorded"
PLAN_PROPOSED_EVENT = "work.plan_proposed"
WORK_GRAPH_ACCEPTED_EVENT = "work.graph_accepted"
AGENT_PRESENCE_RECORDED_EVENT = "work.agent_presence_recorded"
CAPABILITY_MANIFEST_RECORDED_EVENT = "work.capability_manifest_recorded"
COMPETENCE_ESTIMATE_RECORDED_EVENT = "work.competence_estimate_recorded"
WORK_LEASE_GRANTED_EVENT = "work.lease_granted"
WORK_LEASE_EXPIRED_EVENT = "work.lease_expired"
WORK_NODE_COMPLETED_EVENT = "work.node_completed"
WORK_PLAN_INVALIDATED_EVENT = "work.plan_invalidated"


class WorkNodeKind(StrEnum):
    ANALYZE = "analyze"
    PREPARE = "prepare"
    EXECUTE = "execute"
    VERIFY = "verify"
    RELEASE = "release"


class PresenceStatus(StrEnum):
    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"


class CompetenceBasis(StrEnum):
    SEEDED = "seeded"
    EVIDENCE = "evidence"


def _require_text(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _bounded(value: float, name: str) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between zero and one")


def _unique_text(values: tuple[str, ...], name: str, *, required: bool = False) -> None:
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
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:32]}"


def _datetime(data: Mapping[str, object], key: str) -> datetime:
    value = parse_datetime(cast(str | datetime | None, data.get(key)))
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _optional_datetime(data: Mapping[str, object], key: str) -> datetime | None:
    return parse_datetime(cast(str | datetime | None, data.get(key)))


def _strings(data: Mapping[str, object], key: str) -> tuple[str, ...]:
    values = cast(list[object] | tuple[object, ...], data.get(key, ()))
    return tuple(str(value) for value in values)


def _prerequisite_dict(value: ActionPrerequisite) -> JSONObject:
    return {
        "source_id": value.source_id,
        "minimum_freshness": value.minimum_freshness,
        "minimum_confidence": value.minimum_confidence,
    }


def _prerequisite(data: Mapping[str, object]) -> ActionPrerequisite:
    return ActionPrerequisite(
        source_id=str(data["source_id"]),
        minimum_freshness=float(cast(float, data["minimum_freshness"])),
        minimum_confidence=float(cast(float, data["minimum_confidence"])),
    )


def _prerequisites(data: Mapping[str, object], key: str) -> tuple[ActionPrerequisite, ...]:
    values = cast(list[object] | tuple[object, ...], data.get(key, ()))
    return tuple(_prerequisite(cast(Mapping[str, object], value)) for value in values)


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
        causation_id=causation_id,
        payload=payload,
    )


@dataclass(frozen=True, slots=True)
class WorkOrder:
    work_order_id: str
    purpose: str
    governing_goal_refs: tuple[str, ...]
    created_from: tuple[str, ...]
    priority: float
    desired_outcome: str
    success_criteria: tuple[str, ...]
    deadline: datetime | None
    opportunity_window_end: datetime | None
    authority_ceiling: AuthorityLevel
    epistemic_prerequisites: tuple[ActionPrerequisite, ...]
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        purpose: str,
        governing_goal_refs: tuple[str, ...],
        created_from: tuple[str, ...],
        priority: float,
        desired_outcome: str,
        success_criteria: tuple[str, ...],
        created_at: datetime,
        deadline: datetime | None = None,
        opportunity_window_end: datetime | None = None,
        authority_ceiling: AuthorityLevel = AuthorityLevel.PROPOSE,
        epistemic_prerequisites: tuple[ActionPrerequisite, ...] = (),
    ) -> WorkOrder:
        identity: JSONObject = {
            "purpose": purpose,
            "governing_goal_refs": list(governing_goal_refs),
            "created_from": list(created_from),
            "priority": priority,
            "desired_outcome": desired_outcome,
            "success_criteria": list(success_criteria),
            "deadline": deadline.isoformat() if deadline else None,
            "opportunity_window_end": (
                opportunity_window_end.isoformat() if opportunity_window_end else None
            ),
            "authority_ceiling": int(authority_ceiling),
            "epistemic_prerequisites": [
                _prerequisite_dict(value) for value in epistemic_prerequisites
            ],
            "created_at": created_at.isoformat(),
        }
        return cls(
            work_order_id=_canonical_id("work-order", identity),
            purpose=purpose,
            governing_goal_refs=governing_goal_refs,
            created_from=created_from,
            priority=priority,
            desired_outcome=desired_outcome,
            success_criteria=success_criteria,
            deadline=deadline,
            opportunity_window_end=opportunity_window_end,
            authority_ceiling=authority_ceiling,
            epistemic_prerequisites=epistemic_prerequisites,
            created_at=created_at,
        )

    def __post_init__(self) -> None:
        _require_text(self.work_order_id, "work order id")
        _require_text(self.purpose, "work order purpose")
        _require_text(self.desired_outcome, "work order desired outcome")
        _unique_text(self.governing_goal_refs, "work order goal refs", required=True)
        _unique_text(self.created_from, "work order provenance", required=True)
        _unique_text(self.success_criteria, "work order success criteria", required=True)
        _bounded(self.priority, "work order priority")
        _require_aware(self.created_at, "work order created_at")
        for value, name in (
            (self.deadline, "work order deadline"),
            (self.opportunity_window_end, "work order opportunity window"),
        ):
            if value is not None:
                _require_aware(value, name)
                if value < self.created_at:
                    raise ValueError(f"{name} cannot precede creation")
        prerequisite_ids = [value.source_id for value in self.epistemic_prerequisites]
        if len(set(prerequisite_ids)) != len(prerequisite_ids):
            raise ValueError("work order epistemic prerequisite sources must be unique")

    def to_dict(self) -> JSONObject:
        return {
            "work_order_id": self.work_order_id,
            "purpose": self.purpose,
            "governing_goal_refs": list(self.governing_goal_refs),
            "created_from": list(self.created_from),
            "priority": self.priority,
            "desired_outcome": self.desired_outcome,
            "success_criteria": list(self.success_criteria),
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "opportunity_window_end": (
                self.opportunity_window_end.isoformat() if self.opportunity_window_end else None
            ),
            "authority_ceiling": int(self.authority_ceiling),
            "epistemic_prerequisites": [
                _prerequisite_dict(value) for value in self.epistemic_prerequisites
            ],
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> WorkOrder:
        order = cls(
            work_order_id=str(data["work_order_id"]),
            purpose=str(data["purpose"]),
            governing_goal_refs=_strings(data, "governing_goal_refs"),
            created_from=_strings(data, "created_from"),
            priority=float(cast(float, data["priority"])),
            desired_outcome=str(data["desired_outcome"]),
            success_criteria=_strings(data, "success_criteria"),
            deadline=_optional_datetime(data, "deadline"),
            opportunity_window_end=_optional_datetime(data, "opportunity_window_end"),
            authority_ceiling=AuthorityLevel(int(cast(int, data["authority_ceiling"]))),
            epistemic_prerequisites=_prerequisites(data, "epistemic_prerequisites"),
            created_at=_datetime(data, "created_at"),
        )
        expected = cls.create(
            purpose=order.purpose,
            governing_goal_refs=order.governing_goal_refs,
            created_from=order.created_from,
            priority=order.priority,
            desired_outcome=order.desired_outcome,
            success_criteria=order.success_criteria,
            deadline=order.deadline,
            opportunity_window_end=order.opportunity_window_end,
            authority_ceiling=order.authority_ceiling,
            epistemic_prerequisites=order.epistemic_prerequisites,
            created_at=order.created_at,
        )
        if order.work_order_id != expected.work_order_id:
            raise ValueError("work order id does not match immutable content")
        return order

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"work-order-recorded:{self.work_order_id}",
            event_type=WORK_ORDER_RECORDED_EVENT,
            source=source,
            subject=self.work_order_id,
            timestamp=self.created_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> WorkOrder:
        if event.type != WORK_ORDER_RECORDED_EVENT:
            raise ValueError(f"not a work order event: {event.type}")
        value = cls.from_dict(event.payload)
        if event.id != f"work-order-recorded:{value.work_order_id}":
            raise ValueError("work order event id is inconsistent")
        if event.subject != value.work_order_id or event.timestamp != value.created_at:
            raise ValueError("work order event envelope is inconsistent")
        return value


@dataclass(frozen=True, slots=True)
class WorkNode:
    node_id: str
    kind: WorkNodeKind
    description: str
    required_capabilities: tuple[str, ...]
    completion_criteria: tuple[str, ...]
    epistemic_prerequisites: tuple[ActionPrerequisite, ...] = ()
    verification_of: tuple[str, ...] = ()
    governed_information_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.node_id, "work node id")
        _require_text(self.description, "work node description")
        _unique_text(self.required_capabilities, "work node capabilities", required=True)
        _unique_text(self.completion_criteria, "work node completion criteria", required=True)
        _unique_text(self.verification_of, "verified node ids")
        _unique_text(
            self.governed_information_refs,
            "work node governed information refs",
        )
        for value in self.governed_information_refs:
            validate_opaque_governance_id(value, "work node governed information ref")
        prerequisite_ids = [value.source_id for value in self.epistemic_prerequisites]
        if len(set(prerequisite_ids)) != len(prerequisite_ids):
            raise ValueError("work node epistemic prerequisite sources must be unique")
        if self.kind is WorkNodeKind.VERIFY and not self.verification_of:
            raise ValueError("verification work must name the nodes it independently verifies")
        if self.kind is not WorkNodeKind.VERIFY and self.verification_of:
            raise ValueError("only verification work may carry verification targets")
        if self.node_id in self.verification_of:
            raise ValueError("a work node cannot verify itself")

    def to_dict(self) -> JSONObject:
        data: JSONObject = {
            "node_id": self.node_id,
            "kind": self.kind.value,
            "description": self.description,
            "required_capabilities": list(self.required_capabilities),
            "completion_criteria": list(self.completion_criteria),
            "epistemic_prerequisites": [
                _prerequisite_dict(value) for value in self.epistemic_prerequisites
            ],
            "verification_of": list(self.verification_of),
        }
        if self.governed_information_refs:
            data["governed_information_refs"] = list(self.governed_information_refs)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> WorkNode:
        return cls(
            node_id=str(data["node_id"]),
            kind=WorkNodeKind(str(data["kind"])),
            description=str(data["description"]),
            required_capabilities=_strings(data, "required_capabilities"),
            completion_criteria=_strings(data, "completion_criteria"),
            epistemic_prerequisites=_prerequisites(data, "epistemic_prerequisites"),
            verification_of=_strings(data, "verification_of"),
            governed_information_refs=_strings(data, "governed_information_refs"),
        )


@dataclass(frozen=True, slots=True)
class WorkDependency:
    predecessor_id: str
    successor_id: str

    def __post_init__(self) -> None:
        _require_text(self.predecessor_id, "dependency predecessor")
        _require_text(self.successor_id, "dependency successor")
        if self.predecessor_id == self.successor_id:
            raise ValueError("a work dependency cannot be self-referential")

    def to_dict(self) -> JSONObject:
        return {
            "predecessor_id": self.predecessor_id,
            "successor_id": self.successor_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> WorkDependency:
        return cls(
            predecessor_id=str(data["predecessor_id"]),
            successor_id=str(data["successor_id"]),
        )


def _nodes(data: Mapping[str, object]) -> tuple[WorkNode, ...]:
    values = cast(list[object] | tuple[object, ...], data.get("nodes", ()))
    return tuple(WorkNode.from_dict(cast(Mapping[str, object], value)) for value in values)


def _dependencies(data: Mapping[str, object]) -> tuple[WorkDependency, ...]:
    values = cast(list[object] | tuple[object, ...], data.get("dependencies", ()))
    return tuple(
        WorkDependency.from_dict(cast(Mapping[str, object], value)) for value in values
    )


@dataclass(frozen=True, slots=True)
class PlanProposal:
    proposal_id: str
    planner_id: str
    work_order_id: str
    based_on_event_cursor: int
    based_on_graph_version: int
    nodes: tuple[WorkNode, ...]
    dependencies: tuple[WorkDependency, ...]
    assumptions: tuple[str, ...]
    done_conditions: tuple[str, ...]
    replan_event_types: tuple[str, ...]
    proposed_at: datetime

    @classmethod
    def create(
        cls,
        *,
        planner_id: str,
        work_order_id: str,
        based_on_event_cursor: int,
        based_on_graph_version: int,
        nodes: tuple[WorkNode, ...],
        dependencies: tuple[WorkDependency, ...],
        assumptions: tuple[str, ...],
        done_conditions: tuple[str, ...],
        replan_event_types: tuple[str, ...],
        proposed_at: datetime,
    ) -> PlanProposal:
        ordered_nodes = tuple(sorted(nodes, key=lambda value: value.node_id))
        ordered_dependencies = tuple(
            sorted(dependencies, key=lambda value: (value.predecessor_id, value.successor_id))
        )
        payload: JSONObject = {
            "planner_id": planner_id,
            "work_order_id": work_order_id,
            "based_on_event_cursor": based_on_event_cursor,
            "based_on_graph_version": based_on_graph_version,
            "nodes": [value.to_dict() for value in ordered_nodes],
            "dependencies": [value.to_dict() for value in ordered_dependencies],
            "assumptions": list(assumptions),
            "done_conditions": list(done_conditions),
            "replan_event_types": list(replan_event_types),
            "proposed_at": proposed_at.isoformat(),
        }
        return cls(
            proposal_id=_canonical_id("plan-proposal", payload),
            planner_id=planner_id,
            work_order_id=work_order_id,
            based_on_event_cursor=based_on_event_cursor,
            based_on_graph_version=based_on_graph_version,
            nodes=ordered_nodes,
            dependencies=ordered_dependencies,
            assumptions=assumptions,
            done_conditions=done_conditions,
            replan_event_types=replan_event_types,
            proposed_at=proposed_at,
        )

    def __post_init__(self) -> None:
        _require_text(self.proposal_id, "plan proposal id")
        _require_text(self.planner_id, "planner id")
        _require_text(self.work_order_id, "plan proposal work order id")
        if self.based_on_event_cursor < 0 or self.based_on_graph_version < 0:
            raise ValueError("plan proposal cursors and versions cannot be negative")
        if not self.nodes:
            raise ValueError("plan proposal must contain work nodes")
        _unique_text(self.assumptions, "plan assumptions")
        _unique_text(self.done_conditions, "plan done conditions", required=True)
        _unique_text(self.replan_event_types, "plan replan event types", required=True)
        _require_aware(self.proposed_at, "plan proposed_at")

    def to_dict(self) -> JSONObject:
        return {
            "proposal_id": self.proposal_id,
            "planner_id": self.planner_id,
            "work_order_id": self.work_order_id,
            "based_on_event_cursor": self.based_on_event_cursor,
            "based_on_graph_version": self.based_on_graph_version,
            "nodes": [value.to_dict() for value in self.nodes],
            "dependencies": [value.to_dict() for value in self.dependencies],
            "assumptions": list(self.assumptions),
            "done_conditions": list(self.done_conditions),
            "replan_event_types": list(self.replan_event_types),
            "proposed_at": self.proposed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PlanProposal:
        proposal = cls(
            proposal_id=str(data["proposal_id"]),
            planner_id=str(data["planner_id"]),
            work_order_id=str(data["work_order_id"]),
            based_on_event_cursor=int(cast(int, data["based_on_event_cursor"])),
            based_on_graph_version=int(cast(int, data["based_on_graph_version"])),
            nodes=_nodes(data),
            dependencies=_dependencies(data),
            assumptions=_strings(data, "assumptions"),
            done_conditions=_strings(data, "done_conditions"),
            replan_event_types=_strings(data, "replan_event_types"),
            proposed_at=_datetime(data, "proposed_at"),
        )
        expected = cls.create(
            planner_id=proposal.planner_id,
            work_order_id=proposal.work_order_id,
            based_on_event_cursor=proposal.based_on_event_cursor,
            based_on_graph_version=proposal.based_on_graph_version,
            nodes=proposal.nodes,
            dependencies=proposal.dependencies,
            assumptions=proposal.assumptions,
            done_conditions=proposal.done_conditions,
            replan_event_types=proposal.replan_event_types,
            proposed_at=proposal.proposed_at,
        )
        if proposal != expected:
            raise ValueError("plan proposal id does not match immutable content")
        return proposal

    def to_event(self, *, source: str, causation_id: str) -> Event:
        return _event(
            event_id=f"plan-proposed:{self.proposal_id}",
            event_type=PLAN_PROPOSED_EVENT,
            source=source,
            subject=self.work_order_id,
            timestamp=self.proposed_at,
            payload=self.to_dict(),
            causation_id=causation_id,
        )

    @classmethod
    def from_event(cls, event: Event) -> PlanProposal:
        if event.type != PLAN_PROPOSED_EVENT:
            raise ValueError(f"not a plan proposal event: {event.type}")
        value = cls.from_dict(event.payload)
        if event.id != f"plan-proposed:{value.proposal_id}":
            raise ValueError("plan proposal event id is inconsistent")
        if event.subject != value.work_order_id or event.timestamp != value.proposed_at:
            raise ValueError("plan proposal event envelope is inconsistent")
        if event.causation_id is None:
            raise ValueError("plan proposal requires work-order causation")
        return value


@dataclass(frozen=True, slots=True)
class WorkGraph:
    graph_id: str
    work_order_id: str
    proposal_id: str
    version: int
    based_on_event_cursor: int
    nodes: tuple[WorkNode, ...]
    dependencies: tuple[WorkDependency, ...]
    done_conditions: tuple[str, ...]
    replan_event_types: tuple[str, ...]
    validator_id: str
    accepted_at: datetime

    @classmethod
    def create(
        cls,
        *,
        proposal: PlanProposal,
        version: int,
        validator_id: str,
        accepted_at: datetime,
    ) -> WorkGraph:
        payload: JSONObject = {
            "work_order_id": proposal.work_order_id,
            "proposal_id": proposal.proposal_id,
            "version": version,
            "based_on_event_cursor": proposal.based_on_event_cursor,
            "nodes": [value.to_dict() for value in proposal.nodes],
            "dependencies": [value.to_dict() for value in proposal.dependencies],
            "done_conditions": list(proposal.done_conditions),
            "replan_event_types": list(proposal.replan_event_types),
            "validator_id": validator_id,
            "accepted_at": accepted_at.isoformat(),
        }
        return cls(
            graph_id=_canonical_id("work-graph", payload),
            work_order_id=proposal.work_order_id,
            proposal_id=proposal.proposal_id,
            version=version,
            based_on_event_cursor=proposal.based_on_event_cursor,
            nodes=proposal.nodes,
            dependencies=proposal.dependencies,
            done_conditions=proposal.done_conditions,
            replan_event_types=proposal.replan_event_types,
            validator_id=validator_id,
            accepted_at=accepted_at,
        )

    def __post_init__(self) -> None:
        _require_text(self.graph_id, "work graph id")
        _require_text(self.work_order_id, "work graph order id")
        _require_text(self.proposal_id, "work graph proposal id")
        _require_text(self.validator_id, "work graph validator id")
        if self.version <= 0 or self.based_on_event_cursor < 0:
            raise ValueError("work graph version must be positive and cursor non-negative")
        if not self.nodes:
            raise ValueError("work graph must contain nodes")
        _unique_text(self.done_conditions, "work graph done conditions", required=True)
        _unique_text(self.replan_event_types, "work graph replan event types", required=True)
        _require_aware(self.accepted_at, "work graph accepted_at")

    def to_dict(self) -> JSONObject:
        return {
            "graph_id": self.graph_id,
            "work_order_id": self.work_order_id,
            "proposal_id": self.proposal_id,
            "version": self.version,
            "based_on_event_cursor": self.based_on_event_cursor,
            "nodes": [value.to_dict() for value in self.nodes],
            "dependencies": [value.to_dict() for value in self.dependencies],
            "done_conditions": list(self.done_conditions),
            "replan_event_types": list(self.replan_event_types),
            "validator_id": self.validator_id,
            "accepted_at": self.accepted_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> WorkGraph:
        value = cls(
            graph_id=str(data["graph_id"]),
            work_order_id=str(data["work_order_id"]),
            proposal_id=str(data["proposal_id"]),
            version=int(cast(int, data["version"])),
            based_on_event_cursor=int(cast(int, data["based_on_event_cursor"])),
            nodes=_nodes(data),
            dependencies=_dependencies(data),
            done_conditions=_strings(data, "done_conditions"),
            replan_event_types=_strings(data, "replan_event_types"),
            validator_id=str(data["validator_id"]),
            accepted_at=_datetime(data, "accepted_at"),
        )
        identity: JSONObject = {
            "work_order_id": value.work_order_id,
            "proposal_id": value.proposal_id,
            "version": value.version,
            "based_on_event_cursor": value.based_on_event_cursor,
            "nodes": [item.to_dict() for item in value.nodes],
            "dependencies": [item.to_dict() for item in value.dependencies],
            "done_conditions": list(value.done_conditions),
            "replan_event_types": list(value.replan_event_types),
            "validator_id": value.validator_id,
            "accepted_at": value.accepted_at.isoformat(),
        }
        if value.graph_id != _canonical_id("work-graph", identity):
            raise ValueError("work graph id does not match immutable content")
        return value

    def to_event(self, *, source: str, causation_id: str) -> Event:
        return _event(
            event_id=f"work-graph-accepted:{self.graph_id}",
            event_type=WORK_GRAPH_ACCEPTED_EVENT,
            source=source,
            subject=self.work_order_id,
            timestamp=self.accepted_at,
            payload=self.to_dict(),
            causation_id=causation_id,
        )

    @classmethod
    def from_event(cls, event: Event) -> WorkGraph:
        if event.type != WORK_GRAPH_ACCEPTED_EVENT:
            raise ValueError(f"not a work graph event: {event.type}")
        value = cls.from_dict(event.payload)
        if event.id != f"work-graph-accepted:{value.graph_id}":
            raise ValueError("work graph event id is inconsistent")
        if event.subject != value.work_order_id or event.timestamp != value.accepted_at:
            raise ValueError("work graph event envelope is inconsistent")
        if event.causation_id is None:
            raise ValueError("work graph requires plan-proposal causation")
        return value

    def node(self, node_id: str) -> WorkNode:
        for value in self.nodes:
            if value.node_id == node_id:
                return value
        raise KeyError(f"unknown work node: {node_id}")

    def predecessors(self, node_id: str) -> tuple[str, ...]:
        return tuple(
            value.predecessor_id
            for value in self.dependencies
            if value.successor_id == node_id
        )


@dataclass(frozen=True, slots=True)
class AgentPresence:
    agent_id: str
    status: PresenceStatus
    max_concurrency: int
    observed_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        _require_text(self.agent_id, "agent presence id")
        if self.max_concurrency <= 0:
            raise ValueError("agent max concurrency must be positive")
        _require_aware(self.observed_at, "agent presence observed_at")
        _require_aware(self.valid_until, "agent presence valid_until")
        if self.valid_until <= self.observed_at:
            raise ValueError("agent presence validity must end after observation")

    def is_valid_at(self, at: datetime) -> bool:
        _require_aware(at, "agent presence evaluation time")
        return self.observed_at <= at < self.valid_until

    def to_dict(self) -> JSONObject:
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "max_concurrency": self.max_concurrency,
            "observed_at": self.observed_at.isoformat(),
            "valid_until": self.valid_until.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AgentPresence:
        return cls(
            agent_id=str(data["agent_id"]),
            status=PresenceStatus(str(data["status"])),
            max_concurrency=int(cast(int, data["max_concurrency"])),
            observed_at=_datetime(data, "observed_at"),
            valid_until=_datetime(data, "valid_until"),
        )

    def to_event(self, *, source: str) -> Event:
        payload = self.to_dict()
        return _event(
            event_id=_canonical_id("agent-presence", payload),
            event_type=AGENT_PRESENCE_RECORDED_EVENT,
            source=source,
            subject=self.agent_id,
            timestamp=self.observed_at,
            payload=payload,
        )

    @classmethod
    def from_event(cls, event: Event) -> AgentPresence:
        if event.type != AGENT_PRESENCE_RECORDED_EVENT:
            raise ValueError(f"not an agent presence event: {event.type}")
        value = cls.from_dict(event.payload)
        expected_id = _canonical_id("agent-presence", value.to_dict())
        if event.id != expected_id:
            raise ValueError("agent presence event id is inconsistent")
        if event.subject != value.agent_id or event.timestamp != value.observed_at:
            raise ValueError("agent presence event envelope is inconsistent")
        return value


@dataclass(frozen=True, slots=True)
class CapabilityManifest:
    manifest_id: str
    agent_id: str
    capabilities: tuple[str, ...]
    recorded_at: datetime

    @classmethod
    def create(
        cls,
        *,
        agent_id: str,
        capabilities: tuple[str, ...],
        recorded_at: datetime,
    ) -> CapabilityManifest:
        ordered = tuple(sorted(capabilities))
        payload: JSONObject = {
            "agent_id": agent_id,
            "capabilities": list(ordered),
            "recorded_at": recorded_at.isoformat(),
        }
        return cls(
            manifest_id=_canonical_id("capability-manifest", payload),
            agent_id=agent_id,
            capabilities=ordered,
            recorded_at=recorded_at,
        )

    def __post_init__(self) -> None:
        _require_text(self.manifest_id, "capability manifest id")
        _require_text(self.agent_id, "capability manifest agent id")
        _unique_text(self.capabilities, "declared capabilities", required=True)
        _require_aware(self.recorded_at, "capability manifest recorded_at")

    def to_dict(self) -> JSONObject:
        return {
            "manifest_id": self.manifest_id,
            "agent_id": self.agent_id,
            "capabilities": list(self.capabilities),
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CapabilityManifest:
        value = cls(
            manifest_id=str(data["manifest_id"]),
            agent_id=str(data["agent_id"]),
            capabilities=_strings(data, "capabilities"),
            recorded_at=_datetime(data, "recorded_at"),
        )
        expected = cls.create(
            agent_id=value.agent_id,
            capabilities=value.capabilities,
            recorded_at=value.recorded_at,
        )
        if value != expected:
            raise ValueError("capability manifest id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"capability-manifest-recorded:{self.manifest_id}",
            event_type=CAPABILITY_MANIFEST_RECORDED_EVENT,
            source=source,
            subject=self.agent_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> CapabilityManifest:
        if event.type != CAPABILITY_MANIFEST_RECORDED_EVENT:
            raise ValueError(f"not a capability manifest event: {event.type}")
        value = cls.from_dict(event.payload)
        if event.id != f"capability-manifest-recorded:{value.manifest_id}":
            raise ValueError("capability manifest event id is inconsistent")
        if event.subject != value.agent_id or event.timestamp != value.recorded_at:
            raise ValueError("capability manifest event envelope is inconsistent")
        return value


@dataclass(frozen=True, slots=True)
class CompetenceEstimate:
    estimate_id: str
    agent_id: str
    capability: str
    score: float
    evidence_confidence: float
    basis: CompetenceBasis
    evidence_refs: tuple[str, ...]
    estimated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        agent_id: str,
        capability: str,
        score: float,
        evidence_confidence: float,
        basis: CompetenceBasis,
        evidence_refs: tuple[str, ...],
        estimated_at: datetime,
    ) -> CompetenceEstimate:
        payload: JSONObject = {
            "agent_id": agent_id,
            "capability": capability,
            "score": score,
            "evidence_confidence": evidence_confidence,
            "basis": basis.value,
            "evidence_refs": list(evidence_refs),
            "estimated_at": estimated_at.isoformat(),
        }
        return cls(
            estimate_id=_canonical_id("competence-estimate", payload),
            agent_id=agent_id,
            capability=capability,
            score=score,
            evidence_confidence=evidence_confidence,
            basis=basis,
            evidence_refs=evidence_refs,
            estimated_at=estimated_at,
        )

    def __post_init__(self) -> None:
        _require_text(self.estimate_id, "competence estimate id")
        _require_text(self.agent_id, "competence agent id")
        _require_text(self.capability, "competence capability")
        _bounded(self.score, "competence score")
        _bounded(self.evidence_confidence, "competence evidence confidence")
        _unique_text(self.evidence_refs, "competence evidence refs")
        if self.basis is CompetenceBasis.EVIDENCE and not self.evidence_refs:
            raise ValueError("evidence-based competence requires evidence refs")
        if self.basis is CompetenceBasis.SEEDED and self.evidence_refs:
            raise ValueError("seeded competence cannot claim empirical evidence")
        _require_aware(self.estimated_at, "competence estimated_at")

    def to_dict(self) -> JSONObject:
        return {
            "estimate_id": self.estimate_id,
            "agent_id": self.agent_id,
            "capability": self.capability,
            "score": self.score,
            "evidence_confidence": self.evidence_confidence,
            "basis": self.basis.value,
            "evidence_refs": list(self.evidence_refs),
            "estimated_at": self.estimated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CompetenceEstimate:
        value = cls(
            estimate_id=str(data["estimate_id"]),
            agent_id=str(data["agent_id"]),
            capability=str(data["capability"]),
            score=float(cast(float, data["score"])),
            evidence_confidence=float(cast(float, data["evidence_confidence"])),
            basis=CompetenceBasis(str(data["basis"])),
            evidence_refs=_strings(data, "evidence_refs"),
            estimated_at=_datetime(data, "estimated_at"),
        )
        expected = cls.create(
            agent_id=value.agent_id,
            capability=value.capability,
            score=value.score,
            evidence_confidence=value.evidence_confidence,
            basis=value.basis,
            evidence_refs=value.evidence_refs,
            estimated_at=value.estimated_at,
        )
        if value.estimate_id != expected.estimate_id:
            raise ValueError("competence estimate id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"competence-estimate-recorded:{self.estimate_id}",
            event_type=COMPETENCE_ESTIMATE_RECORDED_EVENT,
            source=source,
            subject=self.agent_id,
            timestamp=self.estimated_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> CompetenceEstimate:
        if event.type != COMPETENCE_ESTIMATE_RECORDED_EVENT:
            raise ValueError(f"not a competence estimate event: {event.type}")
        value = cls.from_dict(event.payload)
        if event.id != f"competence-estimate-recorded:{value.estimate_id}":
            raise ValueError("competence estimate event id is inconsistent")
        if event.subject != value.agent_id or event.timestamp != value.estimated_at:
            raise ValueError("competence estimate event envelope is inconsistent")
        return value


@dataclass(frozen=True, slots=True)
class WorkLease:
    lease_id: str
    graph_id: str
    node_id: str
    agent_id: str
    fencing_token: int
    granted_at: datetime
    expires_at: datetime
    match_score: float
    competence_estimate_refs: tuple[str, ...]
    information_access_decision_refs: tuple[str, ...] = ()
    information_disclosure_decision_refs: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        graph_id: str,
        node_id: str,
        agent_id: str,
        fencing_token: int,
        granted_at: datetime,
        lease_duration: timedelta,
        match_score: float,
        competence_estimate_refs: tuple[str, ...],
        information_access_decision_refs: tuple[str, ...] = (),
        information_disclosure_decision_refs: tuple[str, ...] = (),
    ) -> WorkLease:
        return cls(
            lease_id=f"work-lease:{graph_id}:{node_id}:{fencing_token}",
            graph_id=graph_id,
            node_id=node_id,
            agent_id=agent_id,
            fencing_token=fencing_token,
            granted_at=granted_at,
            expires_at=granted_at + lease_duration,
            match_score=match_score,
            competence_estimate_refs=competence_estimate_refs,
            information_access_decision_refs=information_access_decision_refs,
            information_disclosure_decision_refs=information_disclosure_decision_refs,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.lease_id, "work lease id"),
            (self.graph_id, "work lease graph id"),
            (self.node_id, "work lease node id"),
            (self.agent_id, "work lease agent id"),
        ):
            _require_text(value, name)
        if self.fencing_token <= 0:
            raise ValueError("work lease fencing token must be positive")
        expected_id = f"work-lease:{self.graph_id}:{self.node_id}:{self.fencing_token}"
        if self.lease_id != expected_id:
            raise ValueError("work lease id is inconsistent with its fencing identity")
        _require_aware(self.granted_at, "work lease granted_at")
        _require_aware(self.expires_at, "work lease expires_at")
        if self.expires_at <= self.granted_at:
            raise ValueError("work lease must expire after it is granted")
        _bounded(self.match_score, "work lease match score")
        _unique_text(
            self.competence_estimate_refs,
            "work lease competence estimate refs",
            required=True,
        )
        _unique_text(
            self.information_access_decision_refs,
            "work lease information access decision refs",
        )
        for value in self.information_access_decision_refs:
            validate_opaque_governance_id(
                value,
                "work lease information access decision ref",
            )
        _unique_text(
            self.information_disclosure_decision_refs,
            "work lease information disclosure decision refs",
        )
        for value in self.information_disclosure_decision_refs:
            validate_opaque_governance_id(
                value,
                "work lease information disclosure decision ref",
            )

    def to_dict(self) -> JSONObject:
        data: JSONObject = {
            "lease_id": self.lease_id,
            "graph_id": self.graph_id,
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "fencing_token": self.fencing_token,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "match_score": self.match_score,
            "competence_estimate_refs": list(self.competence_estimate_refs),
        }
        if self.information_access_decision_refs:
            data["information_access_decision_refs"] = list(
                self.information_access_decision_refs
            )
        if self.information_disclosure_decision_refs:
            data["information_disclosure_decision_refs"] = list(
                self.information_disclosure_decision_refs
            )
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> WorkLease:
        return cls(
            lease_id=str(data["lease_id"]),
            graph_id=str(data["graph_id"]),
            node_id=str(data["node_id"]),
            agent_id=str(data["agent_id"]),
            fencing_token=int(cast(int, data["fencing_token"])),
            granted_at=_datetime(data, "granted_at"),
            expires_at=_datetime(data, "expires_at"),
            match_score=float(cast(float, data["match_score"])),
            competence_estimate_refs=_strings(data, "competence_estimate_refs"),
            information_access_decision_refs=_strings(
                data, "information_access_decision_refs"
            ),
            information_disclosure_decision_refs=_strings(
                data, "information_disclosure_decision_refs"
            ),
        )

    def to_event(self, *, source: str, causation_id: str) -> Event:
        return _event(
            event_id=f"work-lease-granted:{self.graph_id}:{self.node_id}:{self.fencing_token}",
            event_type=WORK_LEASE_GRANTED_EVENT,
            source=source,
            subject=self.node_id,
            timestamp=self.granted_at,
            payload=self.to_dict(),
            causation_id=causation_id,
        )

    @classmethod
    def from_event(cls, event: Event) -> WorkLease:
        if event.type != WORK_LEASE_GRANTED_EVENT:
            raise ValueError(f"not a work lease event: {event.type}")
        value = cls.from_dict(event.payload)
        expected_id = (
            f"work-lease-granted:{value.graph_id}:{value.node_id}:{value.fencing_token}"
        )
        if event.id != expected_id:
            raise ValueError("work lease event id is inconsistent")
        if event.subject != value.node_id or event.timestamp != value.granted_at:
            raise ValueError("work lease event envelope is inconsistent")
        if event.causation_id is None:
            raise ValueError("work lease requires graph causation")
        return value

    def expiration_event(
        self,
        *,
        source: str,
        expired_at: datetime,
        reason: str,
    ) -> Event:
        _require_aware(expired_at, "work lease expired_at")
        _require_text(reason, "work lease expiration reason")
        if expired_at < self.expires_at:
            raise ValueError("a work lease cannot expire before its deadline")
        payload: JSONObject = {
            **self.to_dict(),
            "expired_at": expired_at.isoformat(),
            "reason": reason,
        }
        return _event(
            event_id=f"work-lease-terminal:{self.lease_id}",
            event_type=WORK_LEASE_EXPIRED_EVENT,
            source=source,
            subject=self.node_id,
            timestamp=expired_at,
            payload=payload,
            causation_id=f"work-lease-granted:{self.graph_id}:{self.node_id}:{self.fencing_token}",
        )

    def completion_event(
        self,
        *,
        source: str,
        accepted_at: datetime,
        artifact_refs: tuple[str, ...],
        reported_finished_at: datetime | None = None,
        verification_passed: bool | None = None,
    ) -> Event:
        _require_aware(accepted_at, "work completion acceptance time")
        if accepted_at < self.granted_at or accepted_at >= self.expires_at:
            raise ValueError("work completion must be accepted during its active lease")
        if reported_finished_at is not None:
            _require_aware(reported_finished_at, "reported work finish time")
        _unique_text(artifact_refs, "work completion artifact refs", required=True)
        payload: JSONObject = {
            "lease_id": self.lease_id,
            "graph_id": self.graph_id,
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "fencing_token": self.fencing_token,
            "accepted_at": accepted_at.isoformat(),
            "reported_finished_at": (
                reported_finished_at.isoformat()
                if reported_finished_at is not None
                else None
            ),
            "artifact_refs": list(artifact_refs),
            "verification_passed": verification_passed,
        }
        return _event(
            event_id=f"work-lease-terminal:{self.lease_id}",
            event_type=WORK_NODE_COMPLETED_EVENT,
            source=source,
            subject=self.node_id,
            timestamp=accepted_at,
            payload=payload,
            causation_id=f"work-lease-granted:{self.graph_id}:{self.node_id}:{self.fencing_token}",
        )


def plan_invalidation_event(
    graph: WorkGraph,
    trigger: Event,
    *,
    source: str,
    invalidated_at: datetime,
    reason: str,
) -> Event:
    if trigger.sequence is None:
        raise ValueError("plan invalidation requires a canonical trigger")
    if trigger.sequence <= graph.based_on_event_cursor:
        raise ValueError("plan invalidation trigger must follow the plan causal cut")
    if trigger.type not in graph.replan_event_types:
        raise ValueError("event type is not a declared replan condition")
    _require_aware(invalidated_at, "plan invalidated_at")
    if invalidated_at < trigger.timestamp:
        raise ValueError("plan invalidation cannot precede its causal trigger")
    _require_text(reason, "plan invalidation reason")
    payload: JSONObject = {
        "graph_id": graph.graph_id,
        "work_order_id": graph.work_order_id,
        "trigger_event_id": trigger.id,
        "trigger_event_type": trigger.type,
        "trigger_event_sequence": trigger.sequence,
        "invalidated_at": invalidated_at.isoformat(),
        "reason": reason,
    }
    return _event(
        event_id=f"work-plan-invalidated:{graph.graph_id}:{trigger.id}",
        event_type=WORK_PLAN_INVALIDATED_EVENT,
        source=source,
        subject=graph.work_order_id,
        timestamp=invalidated_at,
        payload=payload,
        causation_id=trigger.id,
    )
