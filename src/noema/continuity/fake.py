"""Deterministic fake source ecology for continuity acceptance tests."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from ..types import JSONScalar


@dataclass(frozen=True, slots=True)
class FakeObservation:
    cursor: str
    occurred_at: datetime
    subject: str
    predicate: str
    value: JSONScalar
    confidence: float
    impact_summary: str
    issue_priority: float = 0.0
    affects_current_plan: bool = False

    def __post_init__(self) -> None:
        if not self.cursor.strip() or not self.subject.strip() or not self.predicate.strip():
            raise ValueError("fake observation cursor and semantic key must be non-empty")
        if self.occurred_at.tzinfo is None:
            raise ValueError("fake observation occurred_at must be timezone-aware")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("fake observation confidence must be between zero and one")
        if not self.impact_summary.strip():
            raise ValueError("fake observation impact summary must be non-empty")
        if not 0.0 <= self.issue_priority <= 1.0:
            raise ValueError("fake observation issue priority must be between zero and one")


@dataclass(frozen=True, slots=True)
class FakeRefreshResult:
    source_id: str
    available: bool
    cursor: str | None
    observations: tuple[FakeObservation, ...]
    cost: float

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("fake refresh result source id must be non-empty")
        if self.cursor is not None and not self.cursor.strip():
            raise ValueError("fake refresh result cursor must be non-empty")
        if not math.isfinite(self.cost) or self.cost < 0.0:
            raise ValueError("fake refresh result cost cannot be negative")
        if not self.available and self.observations:
            raise ValueError("an unavailable fake source cannot return observations")
        cursors = [observation.cursor for observation in self.observations]
        if len(set(cursors)) != len(cursors):
            raise ValueError("fake refresh result cursors must be unique")


class FakeSource:
    """Replay source deltas by cursor without network, UI, model, or wall-time waits."""

    def __init__(
        self,
        source_id: str,
        *,
        hazard: float,
        cursor: str | None = None,
        observations: tuple[FakeObservation, ...] = (),
        refresh_cost: float = 0.0,
        available: bool = True,
    ) -> None:
        if not source_id.strip():
            raise ValueError("fake source id must be non-empty")
        if not math.isfinite(hazard) or hazard < 0.0:
            raise ValueError("fake source hazard cannot be negative")
        if not math.isfinite(refresh_cost) or refresh_cost < 0.0:
            raise ValueError("fake source refresh cost cannot be negative")
        cursors = [observation.cursor for observation in observations]
        if len(set(cursors)) != len(cursors):
            raise ValueError("fake source observation cursors must be unique")
        if cursor is not None and not cursor.strip():
            raise ValueError("fake source initial cursor must be non-empty")
        if cursor is not None and cursor in cursors:
            raise ValueError("fake source initial cursor cannot duplicate an observation cursor")
        if tuple(sorted(observations, key=lambda item: item.occurred_at)) != observations:
            raise ValueError("fake source observations must be ordered by occurred_at")
        self.source_id = source_id
        self.hazard = hazard
        self.cursor = cursor
        self.observations = observations
        self.refresh_cost = refresh_cost
        self.available = available
        self._cursor_positions = {
            observation_cursor: index for index, observation_cursor in enumerate(cursors)
        }
        if cursor is not None:
            self._cursor_positions[cursor] = -1

    def refresh(self, *, after_cursor: str | None, observed_at: datetime) -> FakeRefreshResult:
        if observed_at.tzinfo is None:
            raise ValueError("fake refresh observation time must be timezone-aware")
        if after_cursor is not None and after_cursor not in self._cursor_positions:
            raise ValueError(f"unknown fake source cursor: {after_cursor}")
        if not self.available:
            return FakeRefreshResult(
                source_id=self.source_id,
                available=False,
                cursor=after_cursor,
                observations=(),
                cost=self.refresh_cost,
            )
        start = self._cursor_positions[after_cursor] + 1 if after_cursor is not None else 0
        observations = tuple(
            observation
            for observation in self.observations[start:]
            if observation.occurred_at <= observed_at
        )
        cursor = observations[-1].cursor if observations else after_cursor
        return FakeRefreshResult(
            source_id=self.source_id,
            available=True,
            cursor=cursor,
            observations=observations,
            cost=self.refresh_cost,
        )

    def unseen_changes(self, *, after_cursor: str | None, at: datetime) -> int:
        if after_cursor is not None and after_cursor not in self._cursor_positions:
            raise ValueError(f"unknown fake source cursor: {after_cursor}")
        start = self._cursor_positions[after_cursor] + 1 if after_cursor is not None else 0
        return sum(observation.occurred_at <= at for observation in self.observations[start:])
