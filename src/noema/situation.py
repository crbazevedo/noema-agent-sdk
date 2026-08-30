"""Event-sourced situation model.

A situation is not a prompt. It is a typed, queryable projection of the world,
its actors, goals, commitments, opportunities, risks, and available resources.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType

from .events import Event
from .types import JSONValue, parse_datetime, utc_now


class GoalStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CommitmentStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Fact:
    key: str
    value: JSONValue
    confidence: float = 1.0
    source: str | None = None
    observed_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
    evidence_event_id: str | None = None

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= utc_now()


@dataclass(frozen=True, slots=True)
class Entity:
    id: str
    kind: str
    attributes: Mapping[str, JSONValue] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class Relation:
    id: str
    source_id: str
    target_id: str
    kind: str
    attributes: Mapping[str, JSONValue] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class Goal:
    id: str
    description: str
    priority: float = 0.5
    utility: float = 1.0
    status: GoalStatus = GoalStatus.ACTIVE
    deadline: datetime | None = None
    success_criteria: tuple[str, ...] = ()
    owner: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class Commitment:
    id: str
    description: str
    owner: str
    priority: float = 0.5
    status: CommitmentStatus = CommitmentStatus.OPEN
    deadline: datetime | None = None
    terminal: bool = True
    attention_cost: float = 1.0
    social_cost_of_failure: float = 0.0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class Risk:
    id: str
    description: str
    severity: float
    probability: float = 1.0
    impact: float = 1.0
    mitigation: str | None = None
    source: str | None = None
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def expected_loss(self) -> float:
        return self.severity * self.probability * self.impact


@dataclass(frozen=True, slots=True)
class Opportunity:
    id: str
    description: str
    expected_value: float
    uncertainty: float = 0.5
    attention_cost: float = 1.0
    expires_at: datetime | None = None
    active: bool = True
    source: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class SituationSnapshot:
    version: int
    observed_at: datetime
    facts: Mapping[str, Fact]
    entities: Mapping[str, Entity]
    relations: Mapping[str, Relation]
    goals: Mapping[str, Goal]
    commitments: Mapping[str, Commitment]
    risks: Mapping[str, Risk]
    opportunities: Mapping[str, Opportunity]
    resources: Mapping[str, float]

    def fact(self, key: str, default: JSONValue = None) -> JSONValue:
        fact = self.facts.get(key)
        if fact is None or fact.expired:
            return default
        return fact.value

    def active_goals(self) -> tuple[Goal, ...]:
        return tuple(goal for goal in self.goals.values() if goal.status == GoalStatus.ACTIVE)

    def open_commitments(self) -> tuple[Commitment, ...]:
        return tuple(
            commitment
            for commitment in self.commitments.values()
            if commitment.status in {CommitmentStatus.OPEN, CommitmentStatus.IN_PROGRESS}
        )

    def active_risks(self) -> tuple[Risk, ...]:
        return tuple(risk for risk in self.risks.values() if risk.active)

    def active_opportunities(self) -> tuple[Opportunity, ...]:
        now = utc_now()
        return tuple(
            opportunity
            for opportunity in self.opportunities.values()
            if opportunity.active
            and (opportunity.expires_at is None or opportunity.expires_at > now)
        )

    def relations_from(self, entity_id: str, *, kind: str | None = None) -> tuple[Relation, ...]:
        return tuple(
            relation
            for relation in self.relations.values()
            if relation.source_id == entity_id
            and (kind is None or relation.kind == kind)
        )

    def relations_to(self, entity_id: str, *, kind: str | None = None) -> tuple[Relation, ...]:
        return tuple(
            relation
            for relation in self.relations.values()
            if relation.target_id == entity_id
            and (kind is None or relation.kind == kind)
        )


Projector = Callable[["SituationModel", Event], bool]


class SituationModel:
    """Mutable projection rebuilt exclusively from events."""

    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}
        self._entities: dict[str, Entity] = {}
        self._relations: dict[str, Relation] = {}
        self._goals: dict[str, Goal] = {}
        self._commitments: dict[str, Commitment] = {}
        self._risks: dict[str, Risk] = {}
        self._opportunities: dict[str, Opportunity] = {}
        self._resources: dict[str, float] = {}
        self._version = 0
        self._observed_at = utc_now()
        self._projectors: list[Projector] = []
        self._lock = asyncio.Lock()

    @property
    def version(self) -> int:
        return self._version

    def register_projector(self, projector: Projector) -> None:
        self._projectors.append(projector)

    async def apply(self, event: Event) -> None:
        async with self._lock:
            handled = self._apply_builtin(event)
            for projector in self._projectors:
                handled = projector(self, event) or handled
            self._version = event.sequence or self._version + 1
            self._observed_at = event.timestamp
            del handled  # kept for future strict-schema diagnostics

    async def rebuild(self, events: Iterable[Event]) -> None:
        async with self._lock:
            self._clear_unlocked()
            for event in events:
                self._apply_builtin(event)
                for projector in self._projectors:
                    projector(self, event)
                self._version = event.sequence or self._version + 1
                self._observed_at = event.timestamp

    async def snapshot(self) -> SituationSnapshot:
        async with self._lock:
            now = utc_now()
            valid_facts = {
                key: fact
                for key, fact in self._facts.items()
                if fact.expires_at is None or fact.expires_at > now
            }
            return SituationSnapshot(
                version=self._version,
                observed_at=self._observed_at,
                facts=MappingProxyType(valid_facts),
                entities=MappingProxyType(dict(self._entities)),
                relations=MappingProxyType(dict(self._relations)),
                goals=MappingProxyType(dict(self._goals)),
                commitments=MappingProxyType(dict(self._commitments)),
                risks=MappingProxyType(dict(self._risks)),
                opportunities=MappingProxyType(dict(self._opportunities)),
                resources=MappingProxyType(dict(self._resources)),
            )

    def _clear_unlocked(self) -> None:
        self._facts.clear()
        self._entities.clear()
        self._relations.clear()
        self._goals.clear()
        self._commitments.clear()
        self._risks.clear()
        self._opportunities.clear()
        self._resources.clear()
        self._version = 0
        self._observed_at = utc_now()

    def _apply_builtin(self, event: Event) -> bool:
        payload = event.payload
        now = event.timestamp

        if event.type == "fact.observed":
            key = str(payload["key"])
            ttl_seconds = payload.get("ttl_seconds")
            expires_at = (
                now + timedelta(seconds=float(ttl_seconds))
                if ttl_seconds is not None
                else parse_datetime(payload.get("expires_at"))
            )
            self._facts[key] = Fact(
                key=key,
                value=payload.get("value"),
                confidence=float(payload.get("confidence", 1.0)),
                source=str(payload.get("source") or event.source),
                observed_at=now,
                expires_at=expires_at,
                evidence_event_id=event.id,
            )
            return True

        if event.type == "fact.retracted":
            self._facts.pop(str(payload["key"]), None)
            return True

        if event.type == "entity.upserted":
            entity_id = str(payload.get("id") or event.subject)
            if not entity_id:
                raise ValueError("entity.upserted requires id or subject")
            current = self._entities.get(entity_id)
            attributes = dict(current.attributes) if current else {}
            attributes.update(dict(payload.get("attributes", {})))
            self._entities[entity_id] = Entity(
                id=entity_id,
                kind=str(payload.get("kind") or (current.kind if current else "entity")),
                attributes=attributes,
                updated_at=now,
            )
            return True

        if event.type == "entity.removed":
            entity_id = str(payload.get("id") or event.subject)
            self._entities.pop(entity_id, None)
            for relation_id, relation in tuple(self._relations.items()):
                if relation.source_id == entity_id or relation.target_id == entity_id:
                    self._relations.pop(relation_id, None)
            return True

        if event.type == "relation.upserted":
            relation_id = str(payload.get("id") or event.subject)
            if not relation_id:
                raise ValueError("relation.upserted requires id or subject")
            current = self._relations.get(relation_id)
            attributes = dict(current.attributes) if current else {}
            attributes.update(dict(payload.get("attributes", {})))
            self._relations[relation_id] = Relation(
                id=relation_id,
                source_id=str(payload["source_id"]),
                target_id=str(payload["target_id"]),
                kind=str(payload["kind"]),
                attributes=attributes,
                updated_at=now,
            )
            return True

        if event.type == "relation.removed":
            relation_id = str(payload.get("id") or event.subject)
            self._relations.pop(relation_id, None)
            return True

        if event.type == "goal.created":
            goal_id = str(payload.get("id") or event.subject or event.id)
            self._goals[goal_id] = Goal(
                id=goal_id,
                description=str(payload["description"]),
                priority=float(payload.get("priority", 0.5)),
                utility=float(payload.get("utility", 1.0)),
                status=GoalStatus(str(payload.get("status", GoalStatus.ACTIVE))),
                deadline=parse_datetime(payload.get("deadline")),
                success_criteria=tuple(str(item) for item in payload.get("success_criteria", [])),
                owner=str(payload["owner"]) if payload.get("owner") else None,
                created_at=now,
                updated_at=now,
            )
            return True

        if event.type == "goal.updated":
            goal_id = str(payload.get("id") or event.subject)
            current = self._goals.get(goal_id)
            if current is None:
                return False
            self._goals[goal_id] = replace(
                current,
                description=str(payload.get("description", current.description)),
                priority=float(payload.get("priority", current.priority)),
                utility=float(payload.get("utility", current.utility)),
                status=GoalStatus(str(payload.get("status", current.status))),
                deadline=parse_datetime(payload.get("deadline", current.deadline)),
                owner=str(payload.get("owner", current.owner)) if payload.get("owner", current.owner) else None,
                updated_at=now,
            )
            return True

        if event.type == "commitment.created":
            commitment_id = str(payload.get("id") or event.subject or event.id)
            self._commitments[commitment_id] = Commitment(
                id=commitment_id,
                description=str(payload["description"]),
                owner=str(payload.get("owner") or event.source),
                priority=float(payload.get("priority", 0.5)),
                status=CommitmentStatus(str(payload.get("status", CommitmentStatus.OPEN))),
                deadline=parse_datetime(payload.get("deadline")),
                terminal=bool(payload.get("terminal", True)),
                attention_cost=float(payload.get("attention_cost", 1.0)),
                social_cost_of_failure=float(payload.get("social_cost_of_failure", 0.0)),
                created_at=now,
                updated_at=now,
            )
            return True

        if event.type == "commitment.updated":
            commitment_id = str(payload.get("id") or event.subject)
            current = self._commitments.get(commitment_id)
            if current is None:
                return False
            self._commitments[commitment_id] = replace(
                current,
                description=str(payload.get("description", current.description)),
                owner=str(payload.get("owner", current.owner)),
                priority=float(payload.get("priority", current.priority)),
                status=CommitmentStatus(str(payload.get("status", current.status))),
                deadline=parse_datetime(payload.get("deadline", current.deadline)),
                terminal=bool(payload.get("terminal", current.terminal)),
                attention_cost=float(payload.get("attention_cost", current.attention_cost)),
                social_cost_of_failure=float(
                    payload.get("social_cost_of_failure", current.social_cost_of_failure)
                ),
                updated_at=now,
            )
            return True

        if event.type.startswith("commitment.") and event.type.split(".", 1)[1] in {
            "completed",
            "failed",
            "cancelled",
        }:
            commitment_id = str(payload.get("id") or event.subject)
            current = self._commitments.get(commitment_id)
            if current is None:
                return False
            status = CommitmentStatus(event.type.split(".", 1)[1])
            self._commitments[commitment_id] = replace(current, status=status, updated_at=now)
            return True

        if event.type == "risk.detected":
            risk_id = str(payload.get("id") or event.subject or event.id)
            self._risks[risk_id] = Risk(
                id=risk_id,
                description=str(payload["description"]),
                severity=float(payload.get("severity", 0.5)),
                probability=float(payload.get("probability", 1.0)),
                impact=float(payload.get("impact", 1.0)),
                mitigation=str(payload["mitigation"]) if payload.get("mitigation") else None,
                source=str(payload.get("source") or event.source),
                active=True,
                created_at=now,
                updated_at=now,
            )
            return True

        if event.type == "risk.resolved":
            risk_id = str(payload.get("id") or event.subject)
            current = self._risks.get(risk_id)
            if current is None:
                return False
            self._risks[risk_id] = replace(current, active=False, updated_at=now)
            return True

        if event.type == "opportunity.detected":
            opportunity_id = str(payload.get("id") or event.subject or event.id)
            self._opportunities[opportunity_id] = Opportunity(
                id=opportunity_id,
                description=str(payload["description"]),
                expected_value=float(payload.get("expected_value", 0.0)),
                uncertainty=float(payload.get("uncertainty", 0.5)),
                attention_cost=float(payload.get("attention_cost", 1.0)),
                expires_at=parse_datetime(payload.get("expires_at")),
                active=True,
                source=str(payload.get("source") or event.source),
                created_at=now,
                updated_at=now,
            )
            return True

        if event.type == "opportunity.closed":
            opportunity_id = str(payload.get("id") or event.subject)
            current = self._opportunities.get(opportunity_id)
            if current is None:
                return False
            self._opportunities[opportunity_id] = replace(current, active=False, updated_at=now)
            return True

        if event.type == "resource.updated":
            name = str(payload["name"])
            self._resources[name] = float(payload["amount"])
            return True

        return False
