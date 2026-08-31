"""Domain-sensitive freshness decay for mutable external sources."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import SourceState


@dataclass(frozen=True, slots=True)
class FreshnessModel:
    """Exponential freshness decay with change hazard measured per day."""

    hazard_time_unit: timedelta = timedelta(days=1)

    def __post_init__(self) -> None:
        if self.hazard_time_unit <= timedelta(0):
            raise ValueError("freshness hazard time unit must be positive")

    def evaluate(
        self,
        *,
        change_hazard: float,
        elapsed: timedelta,
        initial_freshness: float = 1.0,
    ) -> float:
        if change_hazard < 0.0 or not math.isfinite(change_hazard):
            raise ValueError("change hazard cannot be negative")
        if elapsed < timedelta(0):
            raise ValueError("freshness elapsed time cannot be negative")
        if not 0.0 <= initial_freshness <= 1.0:
            raise ValueError("initial freshness must be between zero and one")
        units = elapsed / self.hazard_time_unit
        return initial_freshness * math.exp(-change_hazard * units)

    def source_freshness(self, state: SourceState, *, at: datetime) -> float:
        if at.tzinfo is None:
            raise ValueError("freshness evaluation time must be timezone-aware")
        return self.evaluate(
            change_hazard=state.change_hazard,
            elapsed=at - state.last_observed_at,
        )

    def fresh_until(
        self,
        *,
        observed_at: datetime,
        change_hazard: float,
        minimum_freshness: float = 0.5,
    ) -> datetime:
        if observed_at.tzinfo is None:
            raise ValueError("observation time must be timezone-aware")
        if change_hazard < 0.0 or not math.isfinite(change_hazard):
            raise ValueError("change hazard cannot be negative")
        if not 0.0 < minimum_freshness < 1.0:
            raise ValueError("minimum freshness must be strictly between zero and one")
        if change_hazard == 0.0:
            return observed_at + timedelta(days=36_500)
        units = -math.log(minimum_freshness) / change_hazard
        return observed_at + self.hazard_time_unit * units
