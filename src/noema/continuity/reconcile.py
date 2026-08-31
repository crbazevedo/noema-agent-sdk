"""Pure selective-refresh planning and shadow orientation gating."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import (
    AwarenessCoverage,
    ObservationBudget,
    ReconciliationDecision,
    ReconciliationDisposition,
    ReconciliationPlan,
    RefreshRequest,
    SourceState,
)


class WakeReconciler:
    """Choose minimum sufficient source refreshes under an observation budget."""

    def __init__(
        self,
        *,
        desired_freshness: float = 0.9,
        relevance_floor: float = 0.15,
    ) -> None:
        if not 0.0 < desired_freshness <= 1.0:
            raise ValueError("desired freshness must be in (0, 1]")
        if not 0.0 <= relevance_floor <= 1.0:
            raise ValueError("relevance floor must be between zero and one")
        self.desired_freshness = desired_freshness
        self.relevance_floor = relevance_floor

    def plan(
        self,
        states: tuple[SourceState, ...],
        *,
        elapsed_wall_time: timedelta,
        budget: ObservationBudget,
        created_at: datetime,
    ) -> ReconciliationPlan:
        if elapsed_wall_time < timedelta(0):
            raise ValueError("wake reconciliation elapsed time cannot be negative")
        if created_at.tzinfo is None:
            raise ValueError("wake reconciliation time must be timezone-aware")
        unique_ids = {state.source_id for state in states}
        if len(unique_ids) != len(states):
            raise ValueError("wake reconciliation source ids must be unique")

        needs = {state.source_id: self.refresh_need(state, elapsed_wall_time) for state in states}
        candidates = [
            state
            for state in states
            if state.goal_relevance * state.decision_sensitivity >= self.relevance_floor
            and state.current_freshness < self.desired_freshness
        ]
        candidates.sort(
            key=lambda state: (
                -(needs[state.source_id] / max(state.refresh_cost, 1e-12)),
                -needs[state.source_id],
                state.source_id,
            )
        )
        selected: set[str] = set()
        remaining_cost = budget.max_cost
        for state in candidates:
            if len(selected) >= budget.max_sources:
                break
            if state.refresh_cost > remaining_cost:
                continue
            selected.add(state.source_id)
            remaining_cost -= state.refresh_cost

        decisions: list[ReconciliationDecision] = []
        for state in sorted(states, key=lambda item: item.source_id):
            importance = state.goal_relevance * state.decision_sensitivity
            need = needs[state.source_id]
            if state.source_id in selected:
                request = RefreshRequest.create(
                    source_id=state.source_id,
                    reason="stale decision-relevant prerequisite",
                    desired_freshness=self.desired_freshness,
                    priority=need,
                    max_cost=state.refresh_cost,
                    created_at=created_at,
                )
                decisions.append(
                    ReconciliationDecision(
                        source_id=state.source_id,
                        disposition=ReconciliationDisposition.REFRESH,
                        refresh_need=need,
                        reason="freshness below the decision threshold",
                        request=request,
                    )
                )
            elif importance < self.relevance_floor:
                decisions.append(
                    ReconciliationDecision(
                        source_id=state.source_id,
                        disposition=ReconciliationDisposition.ACCEPT_EXISTING,
                        refresh_need=need,
                        reason="source is not relevant to the current decision",
                    )
                )
            elif state.current_freshness >= self.desired_freshness:
                decisions.append(
                    ReconciliationDecision(
                        source_id=state.source_id,
                        disposition=ReconciliationDisposition.ACCEPT_EXISTING,
                        refresh_need=need,
                        reason="existing source state is sufficiently fresh",
                    )
                )
            else:
                decisions.append(
                    ReconciliationDecision(
                        source_id=state.source_id,
                        disposition=ReconciliationDisposition.DEFER,
                        refresh_need=need,
                        reason="observation budget exhausted",
                    )
                )
        return ReconciliationPlan(
            decisions=tuple(decisions),
            total_refresh_cost=budget.max_cost - remaining_cost,
        )

    @staticmethod
    def refresh_need(state: SourceState, elapsed_wall_time: timedelta) -> float:
        elapsed_days = elapsed_wall_time / timedelta(days=1)
        raw_need = (
            state.change_hazard * elapsed_days * state.goal_relevance * state.decision_sensitivity
        )
        return 1.0 - math.exp(-raw_need)

    @staticmethod
    def mark_unavailable(decision: ReconciliationDecision) -> ReconciliationDecision:
        return ReconciliationDecision(
            source_id=decision.source_id,
            disposition=ReconciliationDisposition.MARK_UNCERTAIN,
            refresh_need=decision.refresh_need,
            reason="source unavailable; existing state remains stale",
        )


@dataclass(frozen=True, slots=True)
class ActionPrerequisite:
    source_id: str
    minimum_freshness: float
    minimum_confidence: float

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("action prerequisite source id must be non-empty")
        for value, name in (
            (self.minimum_freshness, "minimum_freshness"),
            (self.minimum_confidence, "minimum_confidence"),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between zero and one")


@dataclass(frozen=True, slots=True)
class OrientationBarrierDecision:
    action_id: str
    would_block: bool
    missing_prerequisites: tuple[ActionPrerequisite, ...]
    shadow: bool = True


class OrientationBarrier:
    """Assess stale prerequisites without authorizing, dispatching, or acting."""

    def evaluate(
        self,
        action_id: str,
        prerequisites: tuple[ActionPrerequisite, ...],
        coverage: AwarenessCoverage,
    ) -> OrientationBarrierDecision:
        if not action_id.strip():
            raise ValueError("orientation barrier action id must be non-empty")
        missing = tuple(
            prerequisite
            for prerequisite in prerequisites
            if not self._satisfies(prerequisite, coverage)
        )
        return OrientationBarrierDecision(
            action_id=action_id,
            would_block=bool(missing),
            missing_prerequisites=missing,
            shadow=True,
        )

    @staticmethod
    def _satisfies(
        prerequisite: ActionPrerequisite,
        coverage: AwarenessCoverage,
    ) -> bool:
        entry = coverage.get(prerequisite.source_id)
        return (
            entry is not None
            and entry.freshness >= prerequisite.minimum_freshness
            and entry.confidence >= prerequisite.minimum_confidence
        )
