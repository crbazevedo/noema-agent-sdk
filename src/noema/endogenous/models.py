"""Immutable contracts for deterministic, shadow-first endogenous cognition."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from ..events import Event
from ..types import JSONObject, JSONValue, parse_datetime

POLICY_SNAPSHOT_RECORDED_EVENT = "endogenous.policy_snapshot_recorded"
COGNITION_SCAN_REQUESTED_EVENT = "endogenous.scan_requested"
DREAM_EPOCH_STARTED_EVENT = "endogenous.dream_epoch_started"
INQUIRY_RECORDED_EVENT = "endogenous.inquiry_recorded"
INTRINSIC_ACTIVITY_RECORDED_EVENT = "endogenous.activity_recorded"
VOC_EVALUATED_EVENT = "endogenous.voc_evaluated"
AGENDA_SELECTED_EVENT = "endogenous.agenda_selected"
CALIBRATION_EXCHANGE_RECORDED_EVENT = "endogenous.calibration_exchange_recorded"
DREAM_EPOCH_PREEMPTED_EVENT = "endogenous.dream_epoch_preempted"
DREAM_EPOCH_EXPIRED_EVENT = "endogenous.dream_epoch_expired"
DREAM_EPOCH_ABANDONED_EVENT = "endogenous.dream_epoch_abandoned"

STABLE_GREEDY_SELECTOR_ID = "stable-greedy-multidimensional"
STABLE_GREEDY_SELECTOR_VERSION = 1

ENDOGENOUS_EVENT_TYPES = (
    POLICY_SNAPSHOT_RECORDED_EVENT,
    COGNITION_SCAN_REQUESTED_EVENT,
    DREAM_EPOCH_STARTED_EVENT,
    INQUIRY_RECORDED_EVENT,
    INTRINSIC_ACTIVITY_RECORDED_EVENT,
    VOC_EVALUATED_EVENT,
    AGENDA_SELECTED_EVENT,
    CALIBRATION_EXCHANGE_RECORDED_EVENT,
    DREAM_EPOCH_PREEMPTED_EVENT,
    DREAM_EPOCH_EXPIRED_EVENT,
    DREAM_EPOCH_ABANDONED_EVENT,
)


class EndogenousDrive(StrEnum):
    COHERENCE = "coherence"
    CURIOSITY = "curiosity"
    GOAL_MAINTENANCE = "goal_maintenance"
    SOCIAL_CALIBRATION = "social_calibration"


class InquiryStatus(StrEnum):
    OPEN = "open"


class IntrinsicActivityKind(StrEnum):
    INQUIRY = "inquiry"
    BELIEF_MAINTENANCE = "belief_maintenance"
    GOAL_OR_ROADMAP_MAINTENANCE = "goal_or_roadmap_maintenance"
    PEER_CALIBRATION = "peer_calibration"
    BOUNDED_SIMULATION_CANDIDATE = "bounded_simulation_candidate"


class ActivityDisposition(StrEnum):
    SELECTED = "selected"
    DEFERRED = "deferred"
    SUPPRESSED = "suppressed"


class DreamEpochStatus(StrEnum):
    ACTIVE = "active"
    PREEMPTED = "preempted"
    EXPIRED = "expired"
    ABANDONED = "abandoned"


class DreamAbandonmentReason(StrEnum):
    GOVERNING_INTENT_CHANGED = "governing_intent_changed"


class CognitiveAuthorityCeiling(StrEnum):
    """A cognitive ceiling, deliberately not effect authority."""

    DREAM_PROPOSAL_ONLY = "dream_proposal_only"


def _canonical_id(prefix: str, payload: Mapping[str, JSONValue]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:32]}"


def _require_text(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _bounded(value: float, name: str) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between zero and one")


def _non_negative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")


def _unique(values: tuple[str, ...], name: str, *, required: bool = False) -> None:
    if required and not values:
        raise ValueError(f"{name} must not be empty")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} values must be non-empty")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} values must be unique")


def _datetime(data: Mapping[str, object], key: str) -> datetime:
    value = parse_datetime(cast(str | datetime | None, data.get(key)))
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _optional_datetime(data: Mapping[str, object], key: str) -> datetime | None:
    return parse_datetime(cast(str | datetime | None, data.get(key)))


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


@dataclass(frozen=True, slots=True, order=True)
class GoverningIntentRef:
    goal_id: str
    goal_revision_id: str

    def __post_init__(self) -> None:
        _require_text(self.goal_id, "governing goal id")
        _require_text(self.goal_revision_id, "governing goal revision id")

    def to_dict(self) -> JSONObject:
        return {
            "goal_id": self.goal_id,
            "goal_revision_id": self.goal_revision_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> GoverningIntentRef:
        return cls(
            goal_id=str(data["goal_id"]),
            goal_revision_id=str(data["goal_revision_id"]),
        )


@dataclass(frozen=True, slots=True)
class CognitiveResourceVector:
    activities: int = 0
    compute_units: float = 0.0
    wall_time_seconds: float = 0.0
    attention_units: float = 0.0
    privacy_risk_units: float = 0.0

    def __post_init__(self) -> None:
        if self.activities < 0:
            raise ValueError("cognitive activity count cannot be negative")
        for value, name in (
            (self.compute_units, "compute units"),
            (self.wall_time_seconds, "wall-time seconds"),
            (self.attention_units, "attention units"),
            (self.privacy_risk_units, "privacy/risk units"),
        ):
            _non_negative(value, name)

    def to_dict(self) -> JSONObject:
        return {
            "activities": self.activities,
            "compute_units": self.compute_units,
            "wall_time_seconds": self.wall_time_seconds,
            "attention_units": self.attention_units,
            "privacy_risk_units": self.privacy_risk_units,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CognitiveResourceVector:
        return cls(
            activities=int(cast(int, data.get("activities", 0))),
            compute_units=float(cast(float, data.get("compute_units", 0.0))),
            wall_time_seconds=float(cast(float, data.get("wall_time_seconds", 0.0))),
            attention_units=float(cast(float, data.get("attention_units", 0.0))),
            privacy_risk_units=float(cast(float, data.get("privacy_risk_units", 0.0))),
        )

    def plus(self, other: CognitiveResourceVector) -> CognitiveResourceVector:
        return CognitiveResourceVector(
            activities=self.activities + other.activities,
            compute_units=round(self.compute_units + other.compute_units, 12),
            wall_time_seconds=round(self.wall_time_seconds + other.wall_time_seconds, 12),
            attention_units=round(self.attention_units + other.attention_units, 12),
            privacy_risk_units=round(
                self.privacy_risk_units + other.privacy_risk_units,
                12,
            ),
        )

    def minus(self, other: CognitiveResourceVector) -> CognitiveResourceVector:
        values = (
            self.activities - other.activities,
            self.compute_units - other.compute_units,
            self.wall_time_seconds - other.wall_time_seconds,
            self.attention_units - other.attention_units,
            self.privacy_risk_units - other.privacy_risk_units,
        )
        if any(value < -1e-9 for value in values):
            raise ValueError("cognitive resource use exceeds its budget")
        return CognitiveResourceVector(
            activities=max(0, int(values[0])),
            compute_units=round(max(0.0, values[1]), 12),
            wall_time_seconds=round(max(0.0, values[2]), 12),
            attention_units=round(max(0.0, values[3]), 12),
            privacy_risk_units=round(max(0.0, values[4]), 12),
        )

    def fits_within(self, ceiling: CognitiveResourceVector) -> bool:
        return (
            self.activities <= ceiling.activities
            and self.compute_units <= ceiling.compute_units + 1e-12
            and self.wall_time_seconds <= ceiling.wall_time_seconds + 1e-12
            and self.attention_units <= ceiling.attention_units + 1e-12
            and self.privacy_risk_units <= ceiling.privacy_risk_units + 1e-12
        )


@dataclass(frozen=True, slots=True)
class BackgroundCognitiveBudget:
    budget_id: str
    ceiling: CognitiveResourceVector

    @classmethod
    def create(cls, *, ceiling: CognitiveResourceVector) -> BackgroundCognitiveBudget:
        payload: JSONObject = {"ceiling": ceiling.to_dict()}
        return cls(budget_id=_canonical_id("cognitive-budget", payload), ceiling=ceiling)

    def __post_init__(self) -> None:
        _require_text(self.budget_id, "background cognitive budget id")
        if self.ceiling.activities <= 0:
            raise ValueError("background cognitive budget must permit at least one activity")
        expected_id = _canonical_id("cognitive-budget", {"ceiling": self.ceiling.to_dict()})
        if self.budget_id != expected_id:
            raise ValueError("background cognitive budget id does not match its ceiling")

    def to_dict(self) -> JSONObject:
        return {"budget_id": self.budget_id, "ceiling": self.ceiling.to_dict()}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> BackgroundCognitiveBudget:
        return cls(
            budget_id=str(data["budget_id"]),
            ceiling=CognitiveResourceVector.from_dict(cast(Mapping[str, object], data["ceiling"])),
        )


@dataclass(frozen=True, slots=True)
class EndogenousPolicySnapshot:
    policy_id: str
    version: str
    selector_id: str
    selector_version: int
    compute_cost_weight: float
    delay_cost_weight: float
    attention_cost_weight: float
    opportunity_cost_weight: float
    privacy_risk_cost_weight: float
    minimum_net_voc: float = 0.0

    @classmethod
    def create(
        cls,
        *,
        version: str,
        selector_id: str = STABLE_GREEDY_SELECTOR_ID,
        selector_version: int = STABLE_GREEDY_SELECTOR_VERSION,
        compute_cost_weight: float = 1.0,
        delay_cost_weight: float = 1.0,
        attention_cost_weight: float = 1.0,
        opportunity_cost_weight: float = 1.0,
        privacy_risk_cost_weight: float = 1.0,
        minimum_net_voc: float = 0.0,
    ) -> EndogenousPolicySnapshot:
        payload: JSONObject = {
            "version": version,
            "selector_id": selector_id,
            "selector_version": selector_version,
            "compute_cost_weight": compute_cost_weight,
            "delay_cost_weight": delay_cost_weight,
            "attention_cost_weight": attention_cost_weight,
            "opportunity_cost_weight": opportunity_cost_weight,
            "privacy_risk_cost_weight": privacy_risk_cost_weight,
            "minimum_net_voc": minimum_net_voc,
        }
        return cls(
            policy_id=_canonical_id("endogenous-policy", payload),
            version=version,
            selector_id=selector_id,
            selector_version=selector_version,
            compute_cost_weight=compute_cost_weight,
            delay_cost_weight=delay_cost_weight,
            attention_cost_weight=attention_cost_weight,
            opportunity_cost_weight=opportunity_cost_weight,
            privacy_risk_cost_weight=privacy_risk_cost_weight,
            minimum_net_voc=minimum_net_voc,
        )

    def __post_init__(self) -> None:
        _require_text(self.policy_id, "endogenous policy id")
        _require_text(self.version, "endogenous policy version")
        _require_text(self.selector_id, "endogenous agenda selector id")
        if self.selector_version <= 0:
            raise ValueError("endogenous agenda selector version must be positive")
        for value, name in (
            (self.compute_cost_weight, "compute cost weight"),
            (self.delay_cost_weight, "delay cost weight"),
            (self.attention_cost_weight, "attention cost weight"),
            (self.opportunity_cost_weight, "opportunity cost weight"),
            (self.privacy_risk_cost_weight, "privacy/risk cost weight"),
            (self.minimum_net_voc, "minimum NetVOC"),
        ):
            _non_negative(value, name)
        identity: JSONObject = {
            "version": self.version,
            "selector_id": self.selector_id,
            "selector_version": self.selector_version,
            "compute_cost_weight": self.compute_cost_weight,
            "delay_cost_weight": self.delay_cost_weight,
            "attention_cost_weight": self.attention_cost_weight,
            "opportunity_cost_weight": self.opportunity_cost_weight,
            "privacy_risk_cost_weight": self.privacy_risk_cost_weight,
            "minimum_net_voc": self.minimum_net_voc,
        }
        if self.policy_id != _canonical_id("endogenous-policy", identity):
            raise ValueError("endogenous policy id does not match its immutable weights")

    def to_dict(self) -> JSONObject:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "selector_id": self.selector_id,
            "selector_version": self.selector_version,
            "compute_cost_weight": self.compute_cost_weight,
            "delay_cost_weight": self.delay_cost_weight,
            "attention_cost_weight": self.attention_cost_weight,
            "opportunity_cost_weight": self.opportunity_cost_weight,
            "privacy_risk_cost_weight": self.privacy_risk_cost_weight,
            "minimum_net_voc": self.minimum_net_voc,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> EndogenousPolicySnapshot:
        return cls(
            policy_id=str(data["policy_id"]),
            version=str(data["version"]),
            selector_id=str(data["selector_id"]),
            selector_version=int(cast(int, data["selector_version"])),
            compute_cost_weight=float(cast(float, data["compute_cost_weight"])),
            delay_cost_weight=float(cast(float, data["delay_cost_weight"])),
            attention_cost_weight=float(cast(float, data["attention_cost_weight"])),
            opportunity_cost_weight=float(cast(float, data["opportunity_cost_weight"])),
            privacy_risk_cost_weight=float(cast(float, data["privacy_risk_cost_weight"])),
            minimum_net_voc=float(cast(float, data.get("minimum_net_voc", 0.0))),
        )

    def to_event(self, *, source: str, recorded_at: datetime) -> Event:
        return _event(
            event_id=f"endogenous-policy-recorded:{self.policy_id}",
            event_type=POLICY_SNAPSHOT_RECORDED_EVENT,
            source=source,
            subject=self.policy_id,
            timestamp=recorded_at,
            payload=self.to_dict(),
        )


@dataclass(frozen=True, slots=True)
class CognitionScanRequest:
    request_id: str
    policy_id: str
    budget: BackgroundCognitiveBudget
    requested_at: datetime
    expires_at: datetime

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        budget: BackgroundCognitiveBudget,
        requested_at: datetime,
        expires_at: datetime,
    ) -> CognitionScanRequest:
        payload: JSONObject = {
            "policy_id": policy_id,
            "budget": budget.to_dict(),
            "requested_at": requested_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        return cls(
            request_id=_canonical_id("cognition-scan", payload),
            policy_id=policy_id,
            budget=budget,
            requested_at=requested_at,
            expires_at=expires_at,
        )

    def __post_init__(self) -> None:
        _require_text(self.request_id, "cognition scan request id")
        _require_text(self.policy_id, "cognition scan policy id")
        _require_aware(self.requested_at, "cognition scan requested_at")
        _require_aware(self.expires_at, "cognition scan expires_at")
        if self.expires_at <= self.requested_at:
            raise ValueError("cognition scan expiry must follow its request time")
        identity: JSONObject = {
            "policy_id": self.policy_id,
            "budget": self.budget.to_dict(),
            "requested_at": self.requested_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }
        if self.request_id != _canonical_id("cognition-scan", identity):
            raise ValueError("cognition scan request id does not match its content")

    def to_dict(self) -> JSONObject:
        return {
            "request_id": self.request_id,
            "policy_id": self.policy_id,
            "budget": self.budget.to_dict(),
            "requested_at": self.requested_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CognitionScanRequest:
        return cls(
            request_id=str(data["request_id"]),
            policy_id=str(data["policy_id"]),
            budget=BackgroundCognitiveBudget.from_dict(cast(Mapping[str, object], data["budget"])),
            requested_at=_datetime(data, "requested_at"),
            expires_at=_datetime(data, "expires_at"),
        )

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"cognition-scan-requested:{self.request_id}",
            event_type=COGNITION_SCAN_REQUESTED_EVENT,
            source=source,
            subject=self.request_id,
            timestamp=self.requested_at,
            payload=self.to_dict(),
        )


@dataclass(frozen=True, slots=True)
class DreamEpoch:
    epoch_id: str
    consumer_id: str
    trigger_event_id: str
    event_log_cursor: int
    policy_id: str
    policy_version: str
    selector_id: str
    selector_version: int
    budget: BackgroundCognitiveBudget
    started_at: datetime
    expires_at: datetime
    authority_ceiling: CognitiveAuthorityCeiling

    @classmethod
    def start(
        cls,
        *,
        consumer_id: str,
        trigger_event_id: str,
        event_log_cursor: int,
        policy: EndogenousPolicySnapshot,
        budget: BackgroundCognitiveBudget,
        started_at: datetime,
        expires_at: datetime,
    ) -> DreamEpoch:
        payload: JSONObject = {
            "consumer_id": consumer_id,
            "trigger_event_id": trigger_event_id,
            "event_log_cursor": event_log_cursor,
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
            "selector_id": policy.selector_id,
            "selector_version": policy.selector_version,
            "budget": budget.to_dict(),
            "started_at": started_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "authority_ceiling": CognitiveAuthorityCeiling.DREAM_PROPOSAL_ONLY.value,
        }
        return cls(
            epoch_id=_canonical_id("dream-epoch", payload),
            consumer_id=consumer_id,
            trigger_event_id=trigger_event_id,
            event_log_cursor=event_log_cursor,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            selector_id=policy.selector_id,
            selector_version=policy.selector_version,
            budget=budget,
            started_at=started_at,
            expires_at=expires_at,
            authority_ceiling=CognitiveAuthorityCeiling.DREAM_PROPOSAL_ONLY,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.epoch_id, "dream epoch id"),
            (self.consumer_id, "dream epoch consumer id"),
            (self.trigger_event_id, "dream epoch trigger event id"),
            (self.policy_id, "dream epoch policy id"),
            (self.policy_version, "dream epoch policy version"),
            (self.selector_id, "dream epoch selector id"),
        ):
            _require_text(value, name)
        if self.selector_version <= 0:
            raise ValueError("dream epoch selector version must be positive")
        if self.event_log_cursor <= 0:
            raise ValueError("dream epoch cursor must identify a canonical event")
        _require_aware(self.started_at, "dream epoch started_at")
        _require_aware(self.expires_at, "dream epoch expires_at")
        if self.expires_at <= self.started_at:
            raise ValueError("dream epoch expiry must follow its start")
        identity: JSONObject = {
            "consumer_id": self.consumer_id,
            "trigger_event_id": self.trigger_event_id,
            "event_log_cursor": self.event_log_cursor,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "selector_id": self.selector_id,
            "selector_version": self.selector_version,
            "budget": self.budget.to_dict(),
            "started_at": self.started_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "authority_ceiling": self.authority_ceiling.value,
        }
        if self.epoch_id != _canonical_id("dream-epoch", identity):
            raise ValueError("dream epoch id does not match its immutable content")

    def to_dict(self) -> JSONObject:
        return {
            "epoch_id": self.epoch_id,
            "consumer_id": self.consumer_id,
            "trigger_event_id": self.trigger_event_id,
            "event_log_cursor": self.event_log_cursor,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "selector_id": self.selector_id,
            "selector_version": self.selector_version,
            "budget": self.budget.to_dict(),
            "started_at": self.started_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "authority_ceiling": self.authority_ceiling.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DreamEpoch:
        return cls(
            epoch_id=str(data["epoch_id"]),
            consumer_id=str(data["consumer_id"]),
            trigger_event_id=str(data["trigger_event_id"]),
            event_log_cursor=int(cast(int, data["event_log_cursor"])),
            policy_id=str(data["policy_id"]),
            policy_version=str(data["policy_version"]),
            selector_id=str(data["selector_id"]),
            selector_version=int(cast(int, data["selector_version"])),
            budget=BackgroundCognitiveBudget.from_dict(cast(Mapping[str, object], data["budget"])),
            started_at=_datetime(data, "started_at"),
            expires_at=_datetime(data, "expires_at"),
            authority_ceiling=CognitiveAuthorityCeiling(str(data["authority_ceiling"])),
        )

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"dream-epoch-started:{self.epoch_id}",
            event_type=DREAM_EPOCH_STARTED_EVENT,
            source=source,
            subject=self.epoch_id,
            timestamp=self.started_at,
            payload=self.to_dict(),
            causation_id=self.trigger_event_id,
        )


@dataclass(frozen=True, slots=True)
class Inquiry:
    inquiry_id: str
    question: str
    origin: EndogenousDrive
    governing_intent_refs: tuple[GoverningIntentRef, ...]
    evidence_refs: tuple[str, ...]
    target_refs: tuple[str, ...]
    decision_relevance: float
    expected_information_value: float
    uncertainty: float
    possible_methods: tuple[str, ...]
    estimated_cognitive_cost: float
    privacy_risk_cost: float
    deadline: datetime | None
    expires_at: datetime
    status: InquiryStatus
    causal_cursor: int
    created_at: datetime
    producer_id: str

    @classmethod
    def create(
        cls,
        *,
        question: str,
        origin: EndogenousDrive,
        governing_intent_refs: tuple[GoverningIntentRef, ...],
        evidence_refs: tuple[str, ...],
        target_refs: tuple[str, ...],
        decision_relevance: float,
        expected_information_value: float,
        uncertainty: float,
        possible_methods: tuple[str, ...],
        estimated_cognitive_cost: float,
        privacy_risk_cost: float,
        expires_at: datetime,
        causal_cursor: int,
        created_at: datetime,
        producer_id: str,
        deadline: datetime | None = None,
    ) -> Inquiry:
        intents = tuple(sorted(set(governing_intent_refs)))
        evidence = tuple(sorted(set(evidence_refs)))
        targets = tuple(sorted(set(target_refs)))
        methods = tuple(sorted(set(possible_methods)))
        semantic_identity: JSONObject = {
            "question": question,
            "origin": origin.value,
            "governing_intent_refs": [value.to_dict() for value in intents],
            "evidence_refs": list(evidence),
            "target_refs": list(targets),
            "producer_id": producer_id,
        }
        return cls(
            inquiry_id=_canonical_id("inquiry", semantic_identity),
            question=question,
            origin=origin,
            governing_intent_refs=intents,
            evidence_refs=evidence,
            target_refs=targets,
            decision_relevance=decision_relevance,
            expected_information_value=expected_information_value,
            uncertainty=uncertainty,
            possible_methods=methods,
            estimated_cognitive_cost=estimated_cognitive_cost,
            privacy_risk_cost=privacy_risk_cost,
            deadline=deadline,
            expires_at=expires_at,
            status=InquiryStatus.OPEN,
            causal_cursor=causal_cursor,
            created_at=created_at,
            producer_id=producer_id,
        )

    def __post_init__(self) -> None:
        for text_value, name in (
            (self.inquiry_id, "inquiry id"),
            (self.question, "inquiry question"),
            (self.producer_id, "inquiry producer id"),
        ):
            _require_text(text_value, name)
        if not self.governing_intent_refs:
            raise ValueError("inquiry requires at least one governing intent reference")
        if len(set(self.governing_intent_refs)) != len(self.governing_intent_refs):
            raise ValueError("inquiry governing intent references must be unique")
        _unique(self.evidence_refs, "inquiry evidence refs", required=True)
        _unique(self.target_refs, "inquiry target refs", required=True)
        _unique(self.possible_methods, "inquiry methods", required=True)
        for number_value, name in (
            (self.decision_relevance, "inquiry decision relevance"),
            (self.expected_information_value, "inquiry information value"),
            (self.uncertainty, "inquiry uncertainty"),
        ):
            _bounded(number_value, name)
        _non_negative(self.estimated_cognitive_cost, "inquiry cognitive cost")
        _non_negative(self.privacy_risk_cost, "inquiry privacy/risk cost")
        if self.causal_cursor <= 0:
            raise ValueError("inquiry causal cursor must identify a canonical cut")
        _require_aware(self.created_at, "inquiry created_at")
        _require_aware(self.expires_at, "inquiry expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("inquiry expiry must follow creation")
        if self.deadline is not None:
            _require_aware(self.deadline, "inquiry deadline")
            if self.deadline < self.created_at:
                raise ValueError("inquiry deadline cannot precede creation")
        identity: JSONObject = {
            "question": self.question,
            "origin": self.origin.value,
            "governing_intent_refs": [value.to_dict() for value in self.governing_intent_refs],
            "evidence_refs": list(self.evidence_refs),
            "target_refs": list(self.target_refs),
            "producer_id": self.producer_id,
        }
        if self.inquiry_id != _canonical_id("inquiry", identity):
            raise ValueError("inquiry id does not match its semantic identity")

    def to_dict(self) -> JSONObject:
        return {
            "inquiry_id": self.inquiry_id,
            "question": self.question,
            "origin": self.origin.value,
            "governing_intent_refs": [value.to_dict() for value in self.governing_intent_refs],
            "evidence_refs": list(self.evidence_refs),
            "target_refs": list(self.target_refs),
            "decision_relevance": self.decision_relevance,
            "expected_information_value": self.expected_information_value,
            "uncertainty": self.uncertainty,
            "possible_methods": list(self.possible_methods),
            "estimated_cognitive_cost": self.estimated_cognitive_cost,
            "privacy_risk_cost": self.privacy_risk_cost,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "expires_at": self.expires_at.isoformat(),
            "status": self.status.value,
            "causal_cursor": self.causal_cursor,
            "created_at": self.created_at.isoformat(),
            "producer_id": self.producer_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Inquiry:
        refs = cast(tuple[object, ...] | list[object], data["governing_intent_refs"])
        return cls(
            inquiry_id=str(data["inquiry_id"]),
            question=str(data["question"]),
            origin=EndogenousDrive(str(data["origin"])),
            governing_intent_refs=tuple(
                GoverningIntentRef.from_dict(cast(Mapping[str, object], value)) for value in refs
            ),
            evidence_refs=_strings(data, "evidence_refs"),
            target_refs=_strings(data, "target_refs"),
            decision_relevance=float(cast(float, data["decision_relevance"])),
            expected_information_value=float(cast(float, data["expected_information_value"])),
            uncertainty=float(cast(float, data["uncertainty"])),
            possible_methods=_strings(data, "possible_methods"),
            estimated_cognitive_cost=float(cast(float, data["estimated_cognitive_cost"])),
            privacy_risk_cost=float(cast(float, data["privacy_risk_cost"])),
            deadline=_optional_datetime(data, "deadline"),
            expires_at=_datetime(data, "expires_at"),
            status=InquiryStatus(str(data["status"])),
            causal_cursor=int(cast(int, data["causal_cursor"])),
            created_at=_datetime(data, "created_at"),
            producer_id=str(data["producer_id"]),
        )

    def to_event(self, *, source: str, epoch_id: str) -> Event:
        payload: JSONObject = {"epoch_id": epoch_id, "inquiry": self.to_dict()}
        return _event(
            event_id=f"inquiry-recorded:{self.inquiry_id}",
            event_type=INQUIRY_RECORDED_EVENT,
            source=source,
            subject=self.inquiry_id,
            timestamp=self.created_at,
            payload=payload,
        )


@dataclass(frozen=True, slots=True)
class ValueOfCognitionInputs:
    expected_decision_improvement: float
    compute_cost_basis: float
    delay_cost_basis: float
    attention_cost_basis: float
    opportunity_cost_basis: float
    privacy_risk_cost_basis: float

    def __post_init__(self) -> None:
        for value, name in (
            (self.expected_decision_improvement, "expected decision improvement"),
            (self.compute_cost_basis, "compute cost basis"),
            (self.delay_cost_basis, "delay cost basis"),
            (self.attention_cost_basis, "attention cost basis"),
            (self.opportunity_cost_basis, "opportunity cost basis"),
            (self.privacy_risk_cost_basis, "privacy/risk cost basis"),
        ):
            _non_negative(value, name)

    def to_dict(self) -> JSONObject:
        return {
            "expected_decision_improvement": self.expected_decision_improvement,
            "compute_cost_basis": self.compute_cost_basis,
            "delay_cost_basis": self.delay_cost_basis,
            "attention_cost_basis": self.attention_cost_basis,
            "opportunity_cost_basis": self.opportunity_cost_basis,
            "privacy_risk_cost_basis": self.privacy_risk_cost_basis,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ValueOfCognitionInputs:
        return cls(
            expected_decision_improvement=float(cast(float, data["expected_decision_improvement"])),
            compute_cost_basis=float(cast(float, data["compute_cost_basis"])),
            delay_cost_basis=float(cast(float, data["delay_cost_basis"])),
            attention_cost_basis=float(cast(float, data["attention_cost_basis"])),
            opportunity_cost_basis=float(cast(float, data["opportunity_cost_basis"])),
            privacy_risk_cost_basis=float(cast(float, data["privacy_risk_cost_basis"])),
        )


@dataclass(frozen=True, slots=True)
class IntrinsicActivity:
    activity_id: str
    kind: IntrinsicActivityKind
    inquiry_id: str
    governing_intent_refs: tuple[GoverningIntentRef, ...]
    evidence_refs: tuple[str, ...]
    target_refs: tuple[str, ...]
    voc_inputs: ValueOfCognitionInputs
    urgency: float
    confidence: float
    interruptible: bool
    expires_at: datetime
    resources: CognitiveResourceVector
    causal_cursor: int
    producer_id: str

    @classmethod
    def create(
        cls,
        *,
        kind: IntrinsicActivityKind,
        inquiry_id: str,
        governing_intent_refs: tuple[GoverningIntentRef, ...],
        evidence_refs: tuple[str, ...],
        target_refs: tuple[str, ...],
        voc_inputs: ValueOfCognitionInputs,
        urgency: float,
        confidence: float,
        interruptible: bool,
        expires_at: datetime,
        resources: CognitiveResourceVector,
        causal_cursor: int,
        producer_id: str,
    ) -> IntrinsicActivity:
        intents = tuple(sorted(set(governing_intent_refs)))
        evidence = tuple(sorted(set(evidence_refs)))
        targets = tuple(sorted(set(target_refs)))
        identity: JSONObject = {
            "kind": kind.value,
            "inquiry_id": inquiry_id,
            "governing_intent_refs": [value.to_dict() for value in intents],
            "evidence_refs": list(evidence),
            "target_refs": list(targets),
            "voc_inputs": voc_inputs.to_dict(),
            "urgency": urgency,
            "confidence": confidence,
            "interruptible": interruptible,
            "expires_at": expires_at.isoformat(),
            "resources": resources.to_dict(),
            "causal_cursor": causal_cursor,
            "producer_id": producer_id,
        }
        return cls(
            activity_id=_canonical_id("intrinsic-activity", identity),
            kind=kind,
            inquiry_id=inquiry_id,
            governing_intent_refs=intents,
            evidence_refs=evidence,
            target_refs=targets,
            voc_inputs=voc_inputs,
            urgency=urgency,
            confidence=confidence,
            interruptible=interruptible,
            expires_at=expires_at,
            resources=resources,
            causal_cursor=causal_cursor,
            producer_id=producer_id,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.activity_id, "intrinsic activity id"),
            (self.inquiry_id, "intrinsic activity inquiry id"),
            (self.producer_id, "intrinsic activity producer id"),
        ):
            _require_text(value, name)
        if not self.governing_intent_refs:
            raise ValueError("intrinsic activity requires governing intent")
        if len(set(self.governing_intent_refs)) != len(self.governing_intent_refs):
            raise ValueError("intrinsic activity governing intent refs must be unique")
        _unique(self.evidence_refs, "intrinsic activity evidence refs", required=True)
        _unique(self.target_refs, "intrinsic activity target refs", required=True)
        _bounded(self.urgency, "intrinsic activity urgency")
        _bounded(self.confidence, "intrinsic activity confidence")
        _require_aware(self.expires_at, "intrinsic activity expires_at")
        if self.resources.activities != 1:
            raise ValueError("each intrinsic activity consumes exactly one activity slot")
        if self.causal_cursor <= 0:
            raise ValueError("intrinsic activity causal cursor must identify a canonical cut")
        identity = self.to_dict()
        identity.pop("activity_id")
        if self.activity_id != _canonical_id("intrinsic-activity", identity):
            raise ValueError("intrinsic activity id does not match its immutable content")

    def to_dict(self) -> JSONObject:
        return {
            "activity_id": self.activity_id,
            "kind": self.kind.value,
            "inquiry_id": self.inquiry_id,
            "governing_intent_refs": [value.to_dict() for value in self.governing_intent_refs],
            "evidence_refs": list(self.evidence_refs),
            "target_refs": list(self.target_refs),
            "voc_inputs": self.voc_inputs.to_dict(),
            "urgency": self.urgency,
            "confidence": self.confidence,
            "interruptible": self.interruptible,
            "expires_at": self.expires_at.isoformat(),
            "resources": self.resources.to_dict(),
            "causal_cursor": self.causal_cursor,
            "producer_id": self.producer_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> IntrinsicActivity:
        refs = cast(tuple[object, ...] | list[object], data["governing_intent_refs"])
        return cls(
            activity_id=str(data["activity_id"]),
            kind=IntrinsicActivityKind(str(data["kind"])),
            inquiry_id=str(data["inquiry_id"]),
            governing_intent_refs=tuple(
                GoverningIntentRef.from_dict(cast(Mapping[str, object], value)) for value in refs
            ),
            evidence_refs=_strings(data, "evidence_refs"),
            target_refs=_strings(data, "target_refs"),
            voc_inputs=ValueOfCognitionInputs.from_dict(
                cast(Mapping[str, object], data["voc_inputs"])
            ),
            urgency=float(cast(float, data["urgency"])),
            confidence=float(cast(float, data["confidence"])),
            interruptible=bool(data["interruptible"]),
            expires_at=_datetime(data, "expires_at"),
            resources=CognitiveResourceVector.from_dict(
                cast(Mapping[str, object], data["resources"])
            ),
            causal_cursor=int(cast(int, data["causal_cursor"])),
            producer_id=str(data["producer_id"]),
        )

    def to_event(self, *, source: str, epoch_id: str, recorded_at: datetime) -> Event:
        payload: JSONObject = {"epoch_id": epoch_id, "activity": self.to_dict()}
        return _event(
            event_id=f"intrinsic-activity-recorded:{epoch_id}:{self.activity_id}",
            event_type=INTRINSIC_ACTIVITY_RECORDED_EVENT,
            source=source,
            subject=self.activity_id,
            timestamp=recorded_at,
            payload=payload,
        )


@dataclass(frozen=True, slots=True)
class ValueOfCognitionEstimate:
    estimate_id: str
    epoch_id: str
    activity_id: str
    policy_id: str
    expected_decision_improvement: float
    compute_cost: float
    delay_cost: float
    attention_cost: float
    opportunity_cost: float
    privacy_risk_cost: float
    net_value: float
    evaluated_at: datetime

    def __post_init__(self) -> None:
        for text_value, name in (
            (self.estimate_id, "VOC estimate id"),
            (self.epoch_id, "VOC epoch id"),
            (self.activity_id, "VOC activity id"),
            (self.policy_id, "VOC policy id"),
        ):
            _require_text(text_value, name)
        for number_value, name in (
            (self.expected_decision_improvement, "VOC expected improvement"),
            (self.compute_cost, "VOC compute cost"),
            (self.delay_cost, "VOC delay cost"),
            (self.attention_cost, "VOC attention cost"),
            (self.opportunity_cost, "VOC opportunity cost"),
            (self.privacy_risk_cost, "VOC privacy/risk cost"),
        ):
            _non_negative(number_value, name)
        if not math.isfinite(self.net_value):
            raise ValueError("VOC net value must be finite")
        expected_net = round(
            self.expected_decision_improvement
            - self.compute_cost
            - self.delay_cost
            - self.attention_cost
            - self.opportunity_cost
            - self.privacy_risk_cost,
            12,
        )
        if self.net_value != expected_net:
            raise ValueError("VOC net value does not match its recorded terms")
        _require_aware(self.evaluated_at, "VOC evaluated_at")

    def to_dict(self) -> JSONObject:
        return {
            "estimate_id": self.estimate_id,
            "epoch_id": self.epoch_id,
            "activity_id": self.activity_id,
            "policy_id": self.policy_id,
            "expected_decision_improvement": self.expected_decision_improvement,
            "compute_cost": self.compute_cost,
            "delay_cost": self.delay_cost,
            "attention_cost": self.attention_cost,
            "opportunity_cost": self.opportunity_cost,
            "privacy_risk_cost": self.privacy_risk_cost,
            "net_value": self.net_value,
            "evaluated_at": self.evaluated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ValueOfCognitionEstimate:
        return cls(
            estimate_id=str(data["estimate_id"]),
            epoch_id=str(data["epoch_id"]),
            activity_id=str(data["activity_id"]),
            policy_id=str(data["policy_id"]),
            expected_decision_improvement=float(cast(float, data["expected_decision_improvement"])),
            compute_cost=float(cast(float, data["compute_cost"])),
            delay_cost=float(cast(float, data["delay_cost"])),
            attention_cost=float(cast(float, data["attention_cost"])),
            opportunity_cost=float(cast(float, data["opportunity_cost"])),
            privacy_risk_cost=float(cast(float, data["privacy_risk_cost"])),
            net_value=float(cast(float, data["net_value"])),
            evaluated_at=_datetime(data, "evaluated_at"),
        )

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"voc-evaluated:{self.epoch_id}:{self.activity_id}",
            event_type=VOC_EVALUATED_EVENT,
            source=source,
            subject=self.activity_id,
            timestamp=self.evaluated_at,
            payload=self.to_dict(),
        )


@dataclass(frozen=True, slots=True)
class AgendaDecision:
    activity_id: str
    disposition: ActivityDisposition
    reason: str

    def __post_init__(self) -> None:
        _require_text(self.activity_id, "agenda activity id")
        _require_text(self.reason, "agenda decision reason")

    def to_dict(self) -> JSONObject:
        return {
            "activity_id": self.activity_id,
            "disposition": self.disposition.value,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AgendaDecision:
        return cls(
            activity_id=str(data["activity_id"]),
            disposition=ActivityDisposition(str(data["disposition"])),
            reason=str(data["reason"]),
        )


@dataclass(frozen=True, slots=True)
class IntrinsicAgendaSelection:
    selection_id: str
    epoch_id: str
    policy_id: str
    decisions: tuple[AgendaDecision, ...]
    consumed: CognitiveResourceVector
    remaining: CognitiveResourceVector
    selected_at: datetime

    @classmethod
    def create(
        cls,
        *,
        epoch_id: str,
        policy_id: str,
        decisions: tuple[AgendaDecision, ...],
        consumed: CognitiveResourceVector,
        remaining: CognitiveResourceVector,
        selected_at: datetime,
    ) -> IntrinsicAgendaSelection:
        identity: JSONObject = {
            "epoch_id": epoch_id,
            "policy_id": policy_id,
            "decisions": [value.to_dict() for value in decisions],
            "consumed": consumed.to_dict(),
            "remaining": remaining.to_dict(),
            "selected_at": selected_at.isoformat(),
        }
        return cls(
            selection_id=_canonical_id("intrinsic-agenda", identity),
            epoch_id=epoch_id,
            policy_id=policy_id,
            decisions=decisions,
            consumed=consumed,
            remaining=remaining,
            selected_at=selected_at,
        )

    def __post_init__(self) -> None:
        _require_text(self.selection_id, "intrinsic agenda selection id")
        _require_text(self.epoch_id, "intrinsic agenda epoch id")
        _require_text(self.policy_id, "intrinsic agenda policy id")
        if not self.decisions:
            raise ValueError("intrinsic agenda selection requires candidate decisions")
        activity_ids = tuple(value.activity_id for value in self.decisions)
        _unique(activity_ids, "intrinsic agenda activity ids", required=True)
        _require_aware(self.selected_at, "intrinsic agenda selected_at")
        identity: JSONObject = {
            "epoch_id": self.epoch_id,
            "policy_id": self.policy_id,
            "decisions": [value.to_dict() for value in self.decisions],
            "consumed": self.consumed.to_dict(),
            "remaining": self.remaining.to_dict(),
            "selected_at": self.selected_at.isoformat(),
        }
        if self.selection_id != _canonical_id("intrinsic-agenda", identity):
            raise ValueError("intrinsic agenda id does not match its semantic decision")

    @property
    def selected_activity_ids(self) -> tuple[str, ...]:
        return tuple(
            value.activity_id
            for value in self.decisions
            if value.disposition is ActivityDisposition.SELECTED
        )

    @property
    def deferred_activity_ids(self) -> tuple[str, ...]:
        return tuple(
            value.activity_id
            for value in self.decisions
            if value.disposition is ActivityDisposition.DEFERRED
        )

    @property
    def suppressed_activity_ids(self) -> tuple[str, ...]:
        return tuple(
            value.activity_id
            for value in self.decisions
            if value.disposition is ActivityDisposition.SUPPRESSED
        )

    def to_dict(self) -> JSONObject:
        return {
            "selection_id": self.selection_id,
            "epoch_id": self.epoch_id,
            "policy_id": self.policy_id,
            "decisions": [value.to_dict() for value in self.decisions],
            "consumed": self.consumed.to_dict(),
            "remaining": self.remaining.to_dict(),
            "selected_at": self.selected_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> IntrinsicAgendaSelection:
        decisions = cast(tuple[object, ...] | list[object], data["decisions"])
        return cls(
            selection_id=str(data["selection_id"]),
            epoch_id=str(data["epoch_id"]),
            policy_id=str(data["policy_id"]),
            decisions=tuple(
                AgendaDecision.from_dict(cast(Mapping[str, object], value)) for value in decisions
            ),
            consumed=CognitiveResourceVector.from_dict(
                cast(Mapping[str, object], data["consumed"])
            ),
            remaining=CognitiveResourceVector.from_dict(
                cast(Mapping[str, object], data["remaining"])
            ),
            selected_at=_datetime(data, "selected_at"),
        )

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"intrinsic-agenda-selected:{self.selection_id}",
            event_type=AGENDA_SELECTED_EVENT,
            source=source,
            subject=self.epoch_id,
            timestamp=self.selected_at,
            payload=self.to_dict(),
        )


@dataclass(frozen=True, slots=True)
class CalibrationExchange:
    exchange_id: str
    proposition: str
    local_confidence: float
    peer_confidence: float
    local_evidence_refs: tuple[str, ...]
    peer_evidence_refs: tuple[str, ...]
    local_assumptions: tuple[str, ...]
    peer_assumptions: tuple[str, ...]
    governing_intent_refs: tuple[GoverningIntentRef, ...]
    peer_id: str
    protocol_version: str
    request_provenance_ref: str
    response_provenance_ref: str
    recorded_at: datetime

    @classmethod
    def create(
        cls,
        *,
        proposition: str,
        local_confidence: float,
        peer_confidence: float,
        local_evidence_refs: tuple[str, ...],
        peer_evidence_refs: tuple[str, ...],
        local_assumptions: tuple[str, ...],
        peer_assumptions: tuple[str, ...],
        governing_intent_refs: tuple[GoverningIntentRef, ...],
        peer_id: str,
        protocol_version: str,
        request_provenance_ref: str,
        response_provenance_ref: str,
        recorded_at: datetime,
    ) -> CalibrationExchange:
        intents = tuple(sorted(set(governing_intent_refs)))
        identity: JSONObject = {
            "proposition": proposition,
            "local_confidence": local_confidence,
            "peer_confidence": peer_confidence,
            "local_evidence_refs": list(sorted(set(local_evidence_refs))),
            "peer_evidence_refs": list(sorted(set(peer_evidence_refs))),
            "local_assumptions": list(sorted(set(local_assumptions))),
            "peer_assumptions": list(sorted(set(peer_assumptions))),
            "governing_intent_refs": [value.to_dict() for value in intents],
            "peer_id": peer_id,
            "protocol_version": protocol_version,
            "request_provenance_ref": request_provenance_ref,
            "response_provenance_ref": response_provenance_ref,
            "recorded_at": recorded_at.isoformat(),
        }
        return cls(
            exchange_id=_canonical_id("calibration-exchange", identity),
            proposition=proposition,
            local_confidence=local_confidence,
            peer_confidence=peer_confidence,
            local_evidence_refs=tuple(sorted(set(local_evidence_refs))),
            peer_evidence_refs=tuple(sorted(set(peer_evidence_refs))),
            local_assumptions=tuple(sorted(set(local_assumptions))),
            peer_assumptions=tuple(sorted(set(peer_assumptions))),
            governing_intent_refs=intents,
            peer_id=peer_id,
            protocol_version=protocol_version,
            request_provenance_ref=request_provenance_ref,
            response_provenance_ref=response_provenance_ref,
            recorded_at=recorded_at,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.exchange_id, "calibration exchange id"),
            (self.proposition, "calibration proposition"),
            (self.peer_id, "calibration peer id"),
            (self.protocol_version, "calibration protocol version"),
            (self.request_provenance_ref, "calibration request provenance"),
            (self.response_provenance_ref, "calibration response provenance"),
        ):
            _require_text(value, name)
        _bounded(self.local_confidence, "local calibration confidence")
        _bounded(self.peer_confidence, "peer calibration confidence")
        _unique(self.local_evidence_refs, "local calibration evidence", required=True)
        _unique(self.peer_evidence_refs, "peer calibration evidence", required=True)
        _unique(self.local_assumptions, "local calibration assumptions")
        _unique(self.peer_assumptions, "peer calibration assumptions")
        if not self.governing_intent_refs:
            raise ValueError("calibration exchange requires governing intent")
        if len(set(self.governing_intent_refs)) != len(self.governing_intent_refs):
            raise ValueError("calibration governing intent refs must be unique")
        _require_aware(self.recorded_at, "calibration recorded_at")
        identity = self.to_dict()
        identity.pop("exchange_id")
        if self.exchange_id != _canonical_id("calibration-exchange", identity):
            raise ValueError("calibration exchange id does not match its immutable content")

    def to_dict(self) -> JSONObject:
        return {
            "exchange_id": self.exchange_id,
            "proposition": self.proposition,
            "local_confidence": self.local_confidence,
            "peer_confidence": self.peer_confidence,
            "local_evidence_refs": list(self.local_evidence_refs),
            "peer_evidence_refs": list(self.peer_evidence_refs),
            "local_assumptions": list(self.local_assumptions),
            "peer_assumptions": list(self.peer_assumptions),
            "governing_intent_refs": [value.to_dict() for value in self.governing_intent_refs],
            "peer_id": self.peer_id,
            "protocol_version": self.protocol_version,
            "request_provenance_ref": self.request_provenance_ref,
            "response_provenance_ref": self.response_provenance_ref,
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CalibrationExchange:
        refs = cast(tuple[object, ...] | list[object], data["governing_intent_refs"])
        return cls(
            exchange_id=str(data["exchange_id"]),
            proposition=str(data["proposition"]),
            local_confidence=float(cast(float, data["local_confidence"])),
            peer_confidence=float(cast(float, data["peer_confidence"])),
            local_evidence_refs=_strings(data, "local_evidence_refs"),
            peer_evidence_refs=_strings(data, "peer_evidence_refs"),
            local_assumptions=_strings(data, "local_assumptions"),
            peer_assumptions=_strings(data, "peer_assumptions"),
            governing_intent_refs=tuple(
                GoverningIntentRef.from_dict(cast(Mapping[str, object], value)) for value in refs
            ),
            peer_id=str(data["peer_id"]),
            protocol_version=str(data["protocol_version"]),
            request_provenance_ref=str(data["request_provenance_ref"]),
            response_provenance_ref=str(data["response_provenance_ref"]),
            recorded_at=_datetime(data, "recorded_at"),
        )

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"calibration-exchange-recorded:{self.exchange_id}",
            event_type=CALIBRATION_EXCHANGE_RECORDED_EVENT,
            source=source,
            subject=self.exchange_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )


def dream_epoch_preempted_event(
    epoch: DreamEpoch,
    *,
    foreground_event: Event,
    source: str,
    preempted_at: datetime,
) -> Event:
    payload: JSONObject = {
        "epoch_id": epoch.epoch_id,
        "foreground_event_id": foreground_event.id,
        "preempted_at": preempted_at.isoformat(),
        "reason": "foreground demand preempts background cognition",
    }
    return _event(
        event_id=f"dream-epoch-preempted:{epoch.epoch_id}:{foreground_event.id}",
        event_type=DREAM_EPOCH_PREEMPTED_EVENT,
        source=source,
        subject=epoch.epoch_id,
        timestamp=preempted_at,
        payload=payload,
        causation_id=foreground_event.id,
    )


def dream_epoch_expired_event(
    epoch: DreamEpoch,
    *,
    source: str,
    expired_at: datetime,
) -> Event:
    payload: JSONObject = {
        "epoch_id": epoch.epoch_id,
        "expired_at": expired_at.isoformat(),
    }
    return _event(
        event_id=f"dream-epoch-expired:{epoch.epoch_id}",
        event_type=DREAM_EPOCH_EXPIRED_EVENT,
        source=source,
        subject=epoch.epoch_id,
        timestamp=expired_at,
        payload=payload,
    )


def dream_epoch_abandoned_event(
    epoch: DreamEpoch,
    *,
    reason: DreamAbandonmentReason,
    source: str,
    abandoned_at: datetime,
) -> Event:
    payload: JSONObject = {
        "epoch_id": epoch.epoch_id,
        "reason": reason.value,
        "abandoned_at": abandoned_at.isoformat(),
    }
    return _event(
        event_id=f"dream-epoch-abandoned:{epoch.epoch_id}",
        event_type=DREAM_EPOCH_ABANDONED_EVENT,
        source=source,
        subject=epoch.epoch_id,
        timestamp=abandoned_at,
        payload=payload,
        causation_id=epoch.trigger_event_id,
    )
