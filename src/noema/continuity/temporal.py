"""Explicit wall, monotonic, and world-time utilities for situated continuity."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from time import monotonic

from ..types import utc_now

WallClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]


@dataclass(frozen=True, slots=True)
class SleepInterval:
    started_at: datetime
    woke_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.started_at, "started_at")
        _require_aware(self.woke_at, "woke_at")
        if self.woke_at < self.started_at:
            raise ValueError("wake time cannot precede sleep time")

    @property
    def elapsed_wall_time(self) -> timedelta:
        return self.woke_at - self.started_at


class TemporalService:
    """Keep restart-safe wall time separate from local monotonic duration time."""

    def __init__(
        self,
        *,
        wall_clock: WallClock = utc_now,
        monotonic_clock: MonotonicClock = monotonic,
        timezone: tzinfo = UTC,
    ) -> None:
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self.timezone = timezone

    def wall_now(self) -> datetime:
        value = self._wall_clock()
        _require_aware(value, "wall clock")
        return value.astimezone(self.timezone)

    def monotonic_now(self) -> float:
        value = self._monotonic_clock()
        if not math.isfinite(value):
            raise ValueError("monotonic clock must return a finite value")
        return value

    def elapsed_wall(self, since: datetime, *, until: datetime | None = None) -> timedelta:
        _require_aware(since, "since")
        end = until or self.wall_now()
        _require_aware(end, "until")
        if end < since:
            raise ValueError("wall time cannot move backwards across an awake epoch")
        return end - since

    @staticmethod
    def elapsed_monotonic(started: float, *, ended: float) -> timedelta:
        if not math.isfinite(started) or not math.isfinite(ended):
            raise ValueError("monotonic time must be finite")
        if ended < started:
            raise ValueError("monotonic time cannot move backwards")
        return timedelta(seconds=ended - started)

    def deadline_after(
        self,
        duration: timedelta,
        *,
        from_time: datetime | None = None,
    ) -> datetime:
        if duration < timedelta(0):
            raise ValueError("deadline duration cannot be negative")
        start = from_time or self.wall_now()
        _require_aware(start, "from_time")
        return start + duration

    def sleep_interval(
        self,
        started_at: datetime,
        *,
        woke_at: datetime | None = None,
    ) -> SleepInterval:
        return SleepInterval(started_at, woke_at or self.wall_now())


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
