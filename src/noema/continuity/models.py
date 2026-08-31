"""Immutable contracts for wake epochs, source awareness, and orientation."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import cast

from ..events import Event
from ..types import JSONObject, JSONValue, parse_datetime

AWAKE_EPOCH_STARTED_EVENT = "continuity.awake_epoch_started"
AWAKE_EPOCH_COMPLETED_EVENT = "continuity.awake_epoch_completed"
SOURCE_STATE_RECORDED_EVENT = "continuity.source_state_recorded"
REFRESH_REQUESTED_EVENT = "continuity.refresh_requested"
SOURCE_REFRESHED_EVENT = "continuity.source_refreshed"
SOURCE_REFRESH_FAILED_EVENT = "continuity.source_refresh_failed"
ORIENTATION_COMPLETED_EVENT = "continuity.orientation_completed"


class OrientationStatus(StrEnum):
    ORIENTING = "orienting"
    ORIENTED = "oriented"
    INCOMPLETE = "incomplete"


class ReconciliationDisposition(StrEnum):
    REFRESH = "refresh"
    ACCEPT_EXISTING = "accept_existing"
    MARK_UNCERTAIN = "mark_uncertain"
    DEFER = "defer"


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _bounded(value: float, name: str) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between zero and one")


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


@dataclass(frozen=True, slots=True)
class AwakeEpoch:
    epoch_id: str
    woke_at: datetime
    previous_active_at: datetime
    elapsed_wall_time: timedelta
    event_log_cursor_before: int
    event_log_cursor_after: int
    active_evaluation_epoch_id: str | None
    orientation_status: OrientationStatus
    oriented_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.epoch_id.strip():
            raise ValueError("awake epoch id must be non-empty")
        _require_aware(self.woke_at, "woke_at")
        _require_aware(self.previous_active_at, "previous_active_at")
        if self.woke_at < self.previous_active_at:
            raise ValueError("awake epoch cannot precede previous activity")
        if self.elapsed_wall_time != self.woke_at - self.previous_active_at:
            raise ValueError("awake epoch elapsed wall time is inconsistent")
        if self.event_log_cursor_before < 0:
            raise ValueError("awake epoch cursor cannot be negative")
        if self.event_log_cursor_after < self.event_log_cursor_before:
            raise ValueError("awake epoch cursor cannot regress")
        if self.active_evaluation_epoch_id is not None and not self.active_evaluation_epoch_id:
            raise ValueError("active evaluation epoch id must be non-empty")
        if self.orientation_status is OrientationStatus.ORIENTING:
            if self.oriented_at is not None:
                raise ValueError("an orienting epoch cannot have oriented_at")
        elif self.oriented_at is None:
            raise ValueError("a completed awake epoch requires oriented_at")
        if self.oriented_at is not None:
            _require_aware(self.oriented_at, "oriented_at")
            if self.oriented_at < self.woke_at:
                raise ValueError("orientation cannot complete before wake")

    @classmethod
    def start(
        cls,
        *,
        woke_at: datetime,
        previous_active_at: datetime,
        event_log_cursor_before: int,
        event_log_cursor_after: int,
        active_evaluation_epoch_id: str | None = None,
    ) -> AwakeEpoch:
        payload: JSONObject = {
            "woke_at": woke_at.isoformat(),
            "previous_active_at": previous_active_at.isoformat(),
            "event_log_cursor_before": event_log_cursor_before,
            "event_log_cursor_after": event_log_cursor_after,
            "active_evaluation_epoch_id": active_evaluation_epoch_id,
        }
        return cls(
            epoch_id=_canonical_id("awake-epoch", payload),
            woke_at=woke_at,
            previous_active_at=previous_active_at,
            elapsed_wall_time=woke_at - previous_active_at,
            event_log_cursor_before=event_log_cursor_before,
            event_log_cursor_after=event_log_cursor_after,
            active_evaluation_epoch_id=active_evaluation_epoch_id,
            orientation_status=OrientationStatus.ORIENTING,
        )

    def complete(
        self,
        *,
        status: OrientationStatus,
        oriented_at: datetime,
        event_log_cursor_after: int,
    ) -> AwakeEpoch:
        if status is OrientationStatus.ORIENTING:
            raise ValueError("completed awake epoch requires a terminal orientation status")
        return replace(
            self,
            orientation_status=status,
            oriented_at=oriented_at,
            event_log_cursor_after=event_log_cursor_after,
        )

    def to_dict(self) -> JSONObject:
        return {
            "epoch_id": self.epoch_id,
            "woke_at": self.woke_at.isoformat(),
            "previous_active_at": self.previous_active_at.isoformat(),
            "elapsed_wall_seconds": self.elapsed_wall_time.total_seconds(),
            "event_log_cursor_before": self.event_log_cursor_before,
            "event_log_cursor_after": self.event_log_cursor_after,
            "active_evaluation_epoch_id": self.active_evaluation_epoch_id,
            "orientation_status": self.orientation_status.value,
            "oriented_at": self.oriented_at.isoformat() if self.oriented_at else None,
        }

    def to_event(self, *, source: str) -> Event:
        event_type = (
            AWAKE_EPOCH_STARTED_EVENT
            if self.orientation_status is OrientationStatus.ORIENTING
            else AWAKE_EPOCH_COMPLETED_EVENT
        )
        return Event(
            id=_canonical_id(f"event:{event_type}", self.to_dict()),
            type=event_type,
            source=source,
            subject=self.epoch_id,
            timestamp=self.oriented_at or self.woke_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AwakeEpoch:
        return cls(
            epoch_id=str(data["epoch_id"]),
            woke_at=_datetime(data, "woke_at"),
            previous_active_at=_datetime(data, "previous_active_at"),
            elapsed_wall_time=timedelta(seconds=float(cast(float, data["elapsed_wall_seconds"]))),
            event_log_cursor_before=int(cast(int, data["event_log_cursor_before"])),
            event_log_cursor_after=int(cast(int, data["event_log_cursor_after"])),
            active_evaluation_epoch_id=(
                str(data["active_evaluation_epoch_id"])
                if data.get("active_evaluation_epoch_id") is not None
                else None
            ),
            orientation_status=OrientationStatus(str(data["orientation_status"])),
            oriented_at=parse_datetime(cast(str | None, data.get("oriented_at"))),
        )

    @classmethod
    def from_event(cls, event: Event) -> AwakeEpoch:
        if event.type not in {AWAKE_EPOCH_STARTED_EVENT, AWAKE_EPOCH_COMPLETED_EVENT}:
            raise ValueError(f"not an awake epoch event: {event.type}")
        epoch = cls.from_dict(event.payload)
        if event.subject != epoch.epoch_id:
            raise ValueError("awake epoch event subject is inconsistent")
        if event.timestamp != (epoch.oriented_at or epoch.woke_at):
            raise ValueError("awake epoch event timestamp is inconsistent")
        return epoch


@dataclass(frozen=True, slots=True)
class SourceState:
    source_id: str
    domain: str
    last_observed_at: datetime
    last_cursor: str | None
    change_hazard: float
    current_freshness: float
    confidence: float
    goal_relevance: float
    decision_sensitivity: float
    refresh_cost: float
    captured_at: datetime

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.domain.strip():
            raise ValueError("source id and domain must be non-empty")
        _require_aware(self.last_observed_at, "last_observed_at")
        _require_aware(self.captured_at, "captured_at")
        if self.captured_at < self.last_observed_at:
            raise ValueError("source state cannot be captured before observation")
        if self.last_cursor is not None and not self.last_cursor.strip():
            raise ValueError("source cursor must be non-empty when supplied")
        if not math.isfinite(self.change_hazard) or self.change_hazard < 0.0:
            raise ValueError("source change hazard cannot be negative")
        _bounded(self.current_freshness, "current_freshness")
        _bounded(self.confidence, "confidence")
        _bounded(self.goal_relevance, "goal_relevance")
        _bounded(self.decision_sensitivity, "decision_sensitivity")
        if not math.isfinite(self.refresh_cost) or self.refresh_cost < 0.0:
            raise ValueError("source refresh cost cannot be negative")

    def with_freshness(self, freshness: float, *, captured_at: datetime) -> SourceState:
        return replace(self, current_freshness=freshness, captured_at=captured_at)

    def refreshed(
        self,
        *,
        observed_at: datetime,
        cursor: str | None,
        confidence: float = 1.0,
    ) -> SourceState:
        return replace(
            self,
            last_observed_at=observed_at,
            last_cursor=cursor,
            current_freshness=1.0,
            confidence=confidence,
            captured_at=observed_at,
        )

    def to_dict(self) -> JSONObject:
        return {
            "source_id": self.source_id,
            "domain": self.domain,
            "last_observed_at": self.last_observed_at.isoformat(),
            "last_cursor": self.last_cursor,
            "change_hazard": self.change_hazard,
            "current_freshness": self.current_freshness,
            "confidence": self.confidence,
            "goal_relevance": self.goal_relevance,
            "decision_sensitivity": self.decision_sensitivity,
            "refresh_cost": self.refresh_cost,
            "captured_at": self.captured_at.isoformat(),
        }

    def to_event(self, *, source: str, causation_id: str | None = None) -> Event:
        payload = self.to_dict()
        return Event(
            id=_canonical_id("event:continuity.source-state", payload),
            type=SOURCE_STATE_RECORDED_EVENT,
            source=source,
            subject=self.source_id,
            timestamp=self.captured_at,
            causation_id=causation_id,
            payload=payload,
        )

    @classmethod
    def from_event(cls, event: Event) -> SourceState:
        if event.type != SOURCE_STATE_RECORDED_EVENT:
            raise ValueError(f"not a source-state event: {event.type}")
        data = event.payload
        state = cls(
            source_id=str(data["source_id"]),
            domain=str(data["domain"]),
            last_observed_at=_datetime(data, "last_observed_at"),
            last_cursor=(str(data["last_cursor"]) if data.get("last_cursor") else None),
            change_hazard=float(cast(float, data["change_hazard"])),
            current_freshness=float(cast(float, data["current_freshness"])),
            confidence=float(cast(float, data["confidence"])),
            goal_relevance=float(cast(float, data["goal_relevance"])),
            decision_sensitivity=float(cast(float, data["decision_sensitivity"])),
            refresh_cost=float(cast(float, data["refresh_cost"])),
            captured_at=_datetime(data, "captured_at"),
        )
        if event.subject != state.source_id or event.timestamp != state.captured_at:
            raise ValueError("source-state event envelope is inconsistent")
        return state


@dataclass(frozen=True, slots=True)
class CoverageEntry:
    source_id: str
    domain: str
    confidence: float
    freshness: float
    importance: float
    required_freshness: float = 0.8
    required_confidence: float = 0.8

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.domain.strip():
            raise ValueError("coverage source id and domain must be non-empty")
        for value, name in (
            (self.confidence, "confidence"),
            (self.freshness, "freshness"),
            (self.importance, "importance"),
            (self.required_freshness, "required_freshness"),
            (self.required_confidence, "required_confidence"),
        ):
            _bounded(value, name)

    @property
    def sufficient(self) -> bool:
        return (
            self.freshness >= self.required_freshness
            and self.confidence >= self.required_confidence
        )

    @property
    def weighted_uncertainty(self) -> float:
        return self.importance * (1.0 - min(self.freshness, self.confidence))

    def to_dict(self) -> JSONObject:
        return {
            "source_id": self.source_id,
            "domain": self.domain,
            "confidence": self.confidence,
            "freshness": self.freshness,
            "importance": self.importance,
            "required_freshness": self.required_freshness,
            "required_confidence": self.required_confidence,
            "sufficient": self.sufficient,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CoverageEntry:
        entry = cls(
            source_id=str(data["source_id"]),
            domain=str(data["domain"]),
            confidence=float(cast(float, data["confidence"])),
            freshness=float(cast(float, data["freshness"])),
            importance=float(cast(float, data["importance"])),
            required_freshness=float(cast(float, data["required_freshness"])),
            required_confidence=float(cast(float, data["required_confidence"])),
        )
        if bool(data.get("sufficient", entry.sufficient)) is not entry.sufficient:
            raise ValueError("coverage entry sufficiency is inconsistent")
        return entry


@dataclass(frozen=True, slots=True)
class AwarenessCoverage:
    entries: tuple[CoverageEntry, ...]
    relevance_floor: float = 0.15

    def __post_init__(self) -> None:
        _bounded(self.relevance_floor, "relevance_floor")
        ids = [entry.source_id for entry in self.entries]
        if len(set(ids)) != len(ids):
            raise ValueError("awareness coverage source ids must be unique")

    @classmethod
    def from_states(
        cls,
        states: Iterable[SourceState],
        *,
        required_freshness: float = 0.8,
        required_confidence: float = 0.8,
        relevance_floor: float = 0.15,
    ) -> AwarenessCoverage:
        entries = tuple(
            CoverageEntry(
                source_id=state.source_id,
                domain=state.domain,
                confidence=state.confidence,
                freshness=state.current_freshness,
                importance=state.goal_relevance * state.decision_sensitivity,
                required_freshness=required_freshness,
                required_confidence=required_confidence,
            )
            for state in sorted(states, key=lambda item: item.source_id)
        )
        return cls(entries, relevance_floor=relevance_floor)

    @property
    def relevant_entries(self) -> tuple[CoverageEntry, ...]:
        return tuple(entry for entry in self.entries if entry.importance >= self.relevance_floor)

    @property
    def gaps(self) -> tuple[CoverageEntry, ...]:
        return tuple(entry for entry in self.relevant_entries if not entry.sufficient)

    @property
    def sufficient(self) -> bool:
        return not self.gaps

    @property
    def weighted_uncertainty(self) -> float:
        return sum(entry.weighted_uncertainty for entry in self.relevant_entries)

    def get(self, source_id: str) -> CoverageEntry | None:
        return next((entry for entry in self.entries if entry.source_id == source_id), None)

    def to_dict(self) -> JSONObject:
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "relevance_floor": self.relevance_floor,
            "sufficient": self.sufficient,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AwarenessCoverage:
        raw_entries = cast(list[object] | tuple[object, ...], data.get("entries", ()))
        coverage = cls(
            tuple(
                CoverageEntry.from_dict(cast(Mapping[str, object], value)) for value in raw_entries
            ),
            relevance_floor=float(cast(float, data["relevance_floor"])),
        )
        if bool(data.get("sufficient", coverage.sufficient)) is not coverage.sufficient:
            raise ValueError("awareness coverage sufficiency is inconsistent")
        return coverage


@dataclass(frozen=True, slots=True)
class ObservationBudget:
    max_cost: float
    max_sources: int

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_cost) or self.max_cost < 0.0:
            raise ValueError("observation budget cost cannot be negative")
        if self.max_sources < 0:
            raise ValueError("observation budget source count cannot be negative")


@dataclass(frozen=True, slots=True)
class RefreshRequest:
    request_id: str
    source_id: str
    reason: str
    desired_freshness: float
    priority: float
    max_cost: float
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        source_id: str,
        reason: str,
        desired_freshness: float,
        priority: float,
        max_cost: float,
        created_at: datetime,
    ) -> RefreshRequest:
        payload: JSONObject = {
            "source_id": source_id,
            "reason": reason,
            "desired_freshness": desired_freshness,
            "priority": priority,
            "max_cost": max_cost,
            "created_at": created_at.isoformat(),
        }
        return cls(
            request_id=_canonical_id("refresh-request", payload),
            source_id=source_id,
            reason=reason,
            desired_freshness=desired_freshness,
            priority=priority,
            max_cost=max_cost,
            created_at=created_at,
        )

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.source_id.strip() or not self.reason.strip():
            raise ValueError("refresh request identity, source, and reason must be non-empty")
        _bounded(self.desired_freshness, "desired_freshness")
        _bounded(self.priority, "priority")
        if not math.isfinite(self.max_cost) or self.max_cost < 0.0:
            raise ValueError("refresh request max cost cannot be negative")
        _require_aware(self.created_at, "created_at")

    def to_dict(self) -> JSONObject:
        return {
            "request_id": self.request_id,
            "source_id": self.source_id,
            "reason": self.reason,
            "desired_freshness": self.desired_freshness,
            "priority": self.priority,
            "max_cost": self.max_cost,
            "created_at": self.created_at.isoformat(),
        }

    def to_event(self, *, source: str, causation_id: str) -> Event:
        return Event(
            id=f"continuity-refresh:{self.request_id}",
            type=REFRESH_REQUESTED_EVENT,
            source=source,
            subject=self.source_id,
            timestamp=self.created_at,
            causation_id=causation_id,
            payload=self.to_dict(),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RefreshRequest:
        request = cls(
            request_id=str(data["request_id"]),
            source_id=str(data["source_id"]),
            reason=str(data["reason"]),
            desired_freshness=float(cast(float, data["desired_freshness"])),
            priority=float(cast(float, data["priority"])),
            max_cost=float(cast(float, data["max_cost"])),
            created_at=_datetime(data, "created_at"),
        )
        expected = cls.create(
            source_id=request.source_id,
            reason=request.reason,
            desired_freshness=request.desired_freshness,
            priority=request.priority,
            max_cost=request.max_cost,
            created_at=request.created_at,
        )
        if request.request_id != expected.request_id:
            raise ValueError("refresh request id does not match its immutable content")
        return request


@dataclass(frozen=True, slots=True)
class ReconciliationDecision:
    source_id: str
    disposition: ReconciliationDisposition
    refresh_need: float
    reason: str
    request: RefreshRequest | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.reason.strip():
            raise ValueError("reconciliation source and reason must be non-empty")
        _bounded(self.refresh_need, "refresh_need")
        if (self.disposition is ReconciliationDisposition.REFRESH) != (self.request is not None):
            raise ValueError("only refresh decisions carry a refresh request")
        if self.request is not None and self.request.source_id != self.source_id:
            raise ValueError("refresh decision and request source ids must match")

    def to_dict(self) -> JSONObject:
        return {
            "source_id": self.source_id,
            "disposition": self.disposition.value,
            "refresh_need": self.refresh_need,
            "reason": self.reason,
            "request": self.request.to_dict() if self.request else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconciliationDecision:
        request_data = data.get("request")
        request = (
            RefreshRequest.from_dict(cast(Mapping[str, object], request_data))
            if request_data is not None
            else None
        )
        return cls(
            source_id=str(data["source_id"]),
            disposition=ReconciliationDisposition(str(data["disposition"])),
            refresh_need=float(cast(float, data["refresh_need"])),
            reason=str(data["reason"]),
            request=request,
        )


@dataclass(frozen=True, slots=True)
class ReconciliationPlan:
    decisions: tuple[ReconciliationDecision, ...]
    total_refresh_cost: float

    def __post_init__(self) -> None:
        source_ids = [decision.source_id for decision in self.decisions]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("reconciliation plan source ids must be unique")
        if not math.isfinite(self.total_refresh_cost) or self.total_refresh_cost < 0.0:
            raise ValueError("reconciliation plan refresh cost cannot be negative")

    @property
    def requests(self) -> tuple[RefreshRequest, ...]:
        return tuple(
            decision.request for decision in self.decisions if decision.request is not None
        )


@dataclass(frozen=True, slots=True)
class OrientationIssue:
    source_id: str
    summary: str
    priority: float
    affects_current_plan: bool = True

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.summary.strip():
            raise ValueError("orientation issue source and summary must be non-empty")
        _bounded(self.priority, "issue priority")

    def to_dict(self) -> JSONObject:
        return {
            "source_id": self.source_id,
            "summary": self.summary,
            "priority": self.priority,
            "affects_current_plan": self.affects_current_plan,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> OrientationIssue:
        return cls(
            source_id=str(data["source_id"]),
            summary=str(data["summary"]),
            priority=float(cast(float, data["priority"])),
            affects_current_plan=bool(data.get("affects_current_plan", True)),
        )


@dataclass(frozen=True, slots=True)
class OrientationMetrics:
    sources_considered: int
    sources_refreshed: int
    events_fetched: int
    beliefs_updated: int
    stale_beliefs_retained: int
    orientation_latency_seconds: float
    observation_cost: float
    unnecessary_refresh_rate: float
    missed_change_rate: float
    decision_relevant_uncertainty_removed: float

    def __post_init__(self) -> None:
        counts = (
            self.sources_considered,
            self.sources_refreshed,
            self.events_fetched,
            self.beliefs_updated,
            self.stale_beliefs_retained,
        )
        if any(value < 0 for value in counts):
            raise ValueError("orientation metric counts cannot be negative")
        if self.sources_refreshed > self.sources_considered:
            raise ValueError("refreshed source count cannot exceed considered sources")
        if self.stale_beliefs_retained > self.sources_considered:
            raise ValueError("retained stale source count cannot exceed considered sources")
        for value, name in (
            (self.orientation_latency_seconds, "orientation_latency_seconds"),
            (self.observation_cost, "observation_cost"),
            (
                self.decision_relevant_uncertainty_removed,
                "decision_relevant_uncertainty_removed",
            ),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} cannot be negative or non-finite")
        _bounded(self.unnecessary_refresh_rate, "unnecessary_refresh_rate")
        _bounded(self.missed_change_rate, "missed_change_rate")

    @property
    def orientation_efficiency(self) -> float:
        if self.observation_cost == 0.0:
            return 0.0 if self.decision_relevant_uncertainty_removed == 0.0 else 1.0
        return self.decision_relevant_uncertainty_removed / self.observation_cost

    def to_dict(self) -> JSONObject:
        return {
            "sources_considered": self.sources_considered,
            "sources_refreshed": self.sources_refreshed,
            "events_fetched": self.events_fetched,
            "beliefs_updated": self.beliefs_updated,
            "stale_beliefs_retained": self.stale_beliefs_retained,
            "orientation_latency_seconds": self.orientation_latency_seconds,
            "observation_cost": self.observation_cost,
            "unnecessary_refresh_rate": self.unnecessary_refresh_rate,
            "missed_change_rate": self.missed_change_rate,
            "decision_relevant_uncertainty_removed": self.decision_relevant_uncertainty_removed,
            "orientation_efficiency": self.orientation_efficiency,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> OrientationMetrics:
        metrics = cls(
            sources_considered=int(cast(int, data["sources_considered"])),
            sources_refreshed=int(cast(int, data["sources_refreshed"])),
            events_fetched=int(cast(int, data["events_fetched"])),
            beliefs_updated=int(cast(int, data["beliefs_updated"])),
            stale_beliefs_retained=int(cast(int, data["stale_beliefs_retained"])),
            orientation_latency_seconds=float(cast(float, data["orientation_latency_seconds"])),
            observation_cost=float(cast(float, data["observation_cost"])),
            unnecessary_refresh_rate=float(cast(float, data["unnecessary_refresh_rate"])),
            missed_change_rate=float(cast(float, data["missed_change_rate"])),
            decision_relevant_uncertainty_removed=float(
                cast(float, data["decision_relevant_uncertainty_removed"])
            ),
        )
        recorded_efficiency = float(
            cast(float, data.get("orientation_efficiency", metrics.orientation_efficiency))
        )
        if not math.isclose(recorded_efficiency, metrics.orientation_efficiency):
            raise ValueError("orientation efficiency is inconsistent with its components")
        return metrics


@dataclass(frozen=True, slots=True)
class OrientationReport:
    report_id: str
    epoch: AwakeEpoch
    status: OrientationStatus
    coverage: AwarenessCoverage
    decisions: tuple[ReconciliationDecision, ...]
    refreshed_source_ids: tuple[str, ...]
    changed_source_ids: tuple[str, ...]
    unavailable_source_ids: tuple[str, ...]
    issues: tuple[OrientationIssue, ...]
    highest_value_issue: OrientationIssue | None
    metrics: OrientationMetrics
    summary: str

    @classmethod
    def create(
        cls,
        *,
        epoch: AwakeEpoch,
        status: OrientationStatus,
        coverage: AwarenessCoverage,
        decisions: tuple[ReconciliationDecision, ...],
        refreshed_source_ids: tuple[str, ...],
        changed_source_ids: tuple[str, ...],
        unavailable_source_ids: tuple[str, ...],
        issues: tuple[OrientationIssue, ...],
        highest_value_issue: OrientationIssue | None,
        metrics: OrientationMetrics,
        summary: str,
    ) -> OrientationReport:
        identity: JSONObject = {
            "epoch": epoch.to_dict(),
            "status": status.value,
            "coverage": coverage.to_dict(),
            "decisions": [decision.to_dict() for decision in decisions],
            "refreshed_source_ids": list(refreshed_source_ids),
            "changed_source_ids": list(changed_source_ids),
            "unavailable_source_ids": list(unavailable_source_ids),
            "issues": [issue.to_dict() for issue in issues],
            "highest_value_issue": (highest_value_issue.to_dict() if highest_value_issue else None),
            "metrics": metrics.to_dict(),
            "summary": summary,
        }
        return cls(
            report_id=_canonical_id("orientation-report", identity),
            epoch=epoch,
            status=status,
            coverage=coverage,
            decisions=decisions,
            refreshed_source_ids=refreshed_source_ids,
            changed_source_ids=changed_source_ids,
            unavailable_source_ids=unavailable_source_ids,
            issues=issues,
            highest_value_issue=highest_value_issue,
            metrics=metrics,
            summary=summary,
        )

    def __post_init__(self) -> None:
        if not self.report_id.strip() or not self.summary.strip():
            raise ValueError("orientation report id and summary must be non-empty")
        if self.status is OrientationStatus.ORIENTING:
            raise ValueError("orientation report requires a terminal status")
        if self.epoch.orientation_status is not self.status:
            raise ValueError("orientation report and awake epoch status must match")
        if (self.status is OrientationStatus.ORIENTED) != self.coverage.sufficient:
            raise ValueError("orientation report status and coverage must agree")
        for values, name in (
            (self.refreshed_source_ids, "refreshed source"),
            (self.changed_source_ids, "changed source"),
            (self.unavailable_source_ids, "unavailable source"),
        ):
            if len(set(values)) != len(values) or any(not value.strip() for value in values):
                raise ValueError(f"orientation report {name} ids must be unique and non-empty")
        if set(self.refreshed_source_ids) & set(self.unavailable_source_ids):
            raise ValueError("a source cannot be both refreshed and unavailable")
        if not set(self.changed_source_ids).issubset(self.refreshed_source_ids):
            raise ValueError("changed sources must have been refreshed")
        if self.metrics.sources_refreshed != len(self.refreshed_source_ids):
            raise ValueError("orientation report refresh count is inconsistent")
        coverage_ids = {entry.source_id for entry in self.coverage.entries}
        decision_ids = {decision.source_id for decision in self.decisions}
        if self.metrics.sources_considered != len(coverage_ids):
            raise ValueError("orientation report considered-source count is inconsistent")
        if decision_ids != coverage_ids or len(self.decisions) != len(decision_ids):
            raise ValueError("orientation report requires one decision per covered source")
        if not (
            set(self.refreshed_source_ids)
            | set(self.unavailable_source_ids)
            | set(self.changed_source_ids)
        ).issubset(coverage_ids):
            raise ValueError("orientation report source outcomes require coverage entries")
        if any(issue.source_id not in coverage_ids for issue in self.issues):
            raise ValueError("orientation report issues require coverage entries")
        if self.highest_value_issue is not None:
            if self.highest_value_issue not in self.issues:
                raise ValueError("highest-value issue must be present in report issues")
            if any(issue.priority > self.highest_value_issue.priority for issue in self.issues):
                raise ValueError("highest-value issue does not have the greatest priority")

    def to_dict(self) -> JSONObject:
        return {
            "report_id": self.report_id,
            "epoch": self.epoch.to_dict(),
            "status": self.status.value,
            "coverage": self.coverage.to_dict(),
            "decisions": [decision.to_dict() for decision in self.decisions],
            "refreshed_source_ids": list(self.refreshed_source_ids),
            "changed_source_ids": list(self.changed_source_ids),
            "unavailable_source_ids": list(self.unavailable_source_ids),
            "issues": [issue.to_dict() for issue in self.issues],
            "highest_value_issue": (
                self.highest_value_issue.to_dict() if self.highest_value_issue else None
            ),
            "metrics": self.metrics.to_dict(),
            "summary": self.summary,
        }

    def to_event(self, *, source: str, causation_id: str) -> Event:
        return Event(
            id=f"continuity-orientation:{self.report_id}",
            type=ORIENTATION_COMPLETED_EVENT,
            source=source,
            subject=self.epoch.epoch_id,
            timestamp=self.epoch.oriented_at or self.epoch.woke_at,
            causation_id=causation_id,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> OrientationReport:
        if event.type != ORIENTATION_COMPLETED_EVENT:
            raise ValueError(f"not an orientation report event: {event.type}")
        data = event.payload
        raw_decisions = cast(list[object] | tuple[object, ...], data.get("decisions", ()))
        raw_issues = cast(list[object] | tuple[object, ...], data.get("issues", ()))
        highest_data = data.get("highest_value_issue")
        report = cls(
            report_id=str(data["report_id"]),
            epoch=AwakeEpoch.from_dict(cast(Mapping[str, object], data["epoch"])),
            status=OrientationStatus(str(data["status"])),
            coverage=AwarenessCoverage.from_dict(cast(Mapping[str, object], data["coverage"])),
            decisions=tuple(
                ReconciliationDecision.from_dict(cast(Mapping[str, object], value))
                for value in raw_decisions
            ),
            refreshed_source_ids=tuple(
                str(value)
                for value in cast(
                    list[object] | tuple[object, ...],
                    data.get("refreshed_source_ids", ()),
                )
            ),
            changed_source_ids=tuple(
                str(value)
                for value in cast(
                    list[object] | tuple[object, ...],
                    data.get("changed_source_ids", ()),
                )
            ),
            unavailable_source_ids=tuple(
                str(value)
                for value in cast(
                    list[object] | tuple[object, ...],
                    data.get("unavailable_source_ids", ()),
                )
            ),
            issues=tuple(
                OrientationIssue.from_dict(cast(Mapping[str, object], value))
                for value in raw_issues
            ),
            highest_value_issue=(
                OrientationIssue.from_dict(cast(Mapping[str, object], highest_data))
                if highest_data is not None
                else None
            ),
            metrics=OrientationMetrics.from_dict(cast(Mapping[str, object], data["metrics"])),
            summary=str(data["summary"]),
        )
        expected_id = cls.create(
            epoch=report.epoch,
            status=report.status,
            coverage=report.coverage,
            decisions=report.decisions,
            refreshed_source_ids=report.refreshed_source_ids,
            changed_source_ids=report.changed_source_ids,
            unavailable_source_ids=report.unavailable_source_ids,
            issues=report.issues,
            highest_value_issue=report.highest_value_issue,
            metrics=report.metrics,
            summary=report.summary,
        ).report_id
        if report.report_id != expected_id:
            raise ValueError("orientation report id does not match its immutable content")
        if event.id != f"continuity-orientation:{report.report_id}":
            raise ValueError("orientation report event id is inconsistent")
        if event.subject != report.epoch.epoch_id:
            raise ValueError("orientation report event subject is inconsistent")
        if event.timestamp != (report.epoch.oriented_at or report.epoch.woke_at):
            raise ValueError("orientation report event timestamp is inconsistent")
        if event.causation_id is None:
            raise ValueError("orientation report event requires completed-epoch causation")
        return report


class ContinuityProjection:
    """Rebuild source cursors and awake epochs from canonical continuity events."""

    def __init__(self) -> None:
        self._source_states: dict[str, SourceState] = {}
        self._epochs: dict[str, AwakeEpoch] = {}
        self._reports: dict[str, OrientationReport] = {}

    @property
    def source_states(self) -> tuple[SourceState, ...]:
        return tuple(self._source_states[key] for key in sorted(self._source_states))

    @property
    def epochs(self) -> tuple[AwakeEpoch, ...]:
        return tuple(
            sorted(self._epochs.values(), key=lambda epoch: (epoch.woke_at, epoch.epoch_id))
        )

    @property
    def latest_epoch(self) -> AwakeEpoch | None:
        return self.epochs[-1] if self._epochs else None

    @property
    def reports(self) -> tuple[OrientationReport, ...]:
        return tuple(
            sorted(
                self._reports.values(),
                key=lambda report: (
                    report.epoch.oriented_at or report.epoch.woke_at,
                    report.report_id,
                ),
            )
        )

    @property
    def latest_report(self) -> OrientationReport | None:
        return self.reports[-1] if self._reports else None

    def apply(self, event: Event) -> bool:
        if event.type == SOURCE_STATE_RECORDED_EVENT:
            state = SourceState.from_event(event)
            current_state = self._source_states.get(state.source_id)
            if current_state is not None and state.captured_at < current_state.captured_at:
                raise ValueError(f"source state regressed for {state.source_id}")
            self._source_states[state.source_id] = state
            return True
        if event.type in {AWAKE_EPOCH_STARTED_EVENT, AWAKE_EPOCH_COMPLETED_EVENT}:
            epoch = AwakeEpoch.from_event(event)
            current_epoch = self._epochs.get(epoch.epoch_id)
            if (
                current_epoch is not None
                and current_epoch.orientation_status is not OrientationStatus.ORIENTING
                and epoch != current_epoch
            ):
                raise ValueError(f"completed awake epoch changed: {epoch.epoch_id}")
            self._epochs[epoch.epoch_id] = epoch
            return True
        if event.type == ORIENTATION_COMPLETED_EVENT:
            report = OrientationReport.from_event(event)
            existing = self._reports.get(report.report_id)
            if existing is not None and existing != report:
                raise ValueError(f"orientation report changed: {report.report_id}")
            self._reports[report.report_id] = report
            return True
        return False

    def rebuild(self, events: Iterable[Event]) -> None:
        self._source_states.clear()
        self._epochs.clear()
        self._reports.clear()
        for event in events:
            self.apply(event)
