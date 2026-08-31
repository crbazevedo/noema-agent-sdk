"""Pure selective-refresh planning and shadow orientation gating."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from .models import (
    AwarenessCoverage,
    AwarenessDemand,
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
        relevance_floor: float = 0.15,
    ) -> None:
        if not 0.0 <= relevance_floor <= 1.0:
            raise ValueError("relevance floor must be between zero and one")
        self.relevance_floor = relevance_floor

    def plan(
        self,
        states: tuple[SourceState, ...],
        demands: tuple[AwarenessDemand, ...],
        *,
        freshness_by_source: Mapping[str, float],
        budget: ObservationBudget,
        created_at: datetime,
    ) -> ReconciliationPlan:
        if created_at.tzinfo is None:
            raise ValueError("wake reconciliation time must be timezone-aware")
        unique_ids = {state.source_id for state in states}
        if len(unique_ids) != len(states):
            raise ValueError("wake reconciliation source ids must be unique")
        demand_by_id = {demand.source_id: demand for demand in demands}
        if len(demand_by_id) != len(demands):
            raise ValueError("wake reconciliation demand source ids must be unique")
        unknown_demands = set(demand_by_id) - unique_ids
        if unknown_demands:
            raise ValueError(
                f"wake reconciliation demands reference unknown sources: {sorted(unknown_demands)}"
            )
        missing_freshness = set(demand_by_id) - set(freshness_by_source)
        if missing_freshness:
            raise ValueError(
                f"wake reconciliation demands lack freshness estimates: {sorted(missing_freshness)}"
            )

        needs = {
            state.source_id: (
                self.refresh_need(
                    state,
                    demand_by_id[state.source_id],
                    current_freshness=freshness_by_source[state.source_id],
                )
                if state.source_id in demand_by_id
                else 0.0
            )
            for state in states
        }
        candidates = [
            state
            for state in states
            if (demand := demand_by_id.get(state.source_id)) is not None
            and demand.importance >= self.relevance_floor
            and (
                freshness_by_source[state.source_id] < demand.required_freshness
                or state.confidence < demand.required_confidence
            )
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
            demand = demand_by_id.get(state.source_id)
            need = needs[state.source_id]
            if state.source_id in selected:
                if demand is None:
                    raise AssertionError("selected refresh source requires awareness demand")
                request = RefreshRequest.create(
                    source_id=state.source_id,
                    reason="insufficient decision-relevant freshness or confidence",
                    desired_freshness=demand.required_freshness,
                    desired_confidence=demand.required_confidence,
                    priority=need,
                    max_cost=state.refresh_cost,
                    created_at=created_at,
                )
                decisions.append(
                    ReconciliationDecision(
                        source_id=state.source_id,
                        disposition=ReconciliationDisposition.REFRESH,
                        refresh_need=need,
                        reason="epistemic coverage is below the decision threshold",
                        request=request,
                    )
                )
            elif demand is None or demand.importance < self.relevance_floor:
                decisions.append(
                    ReconciliationDecision(
                        source_id=state.source_id,
                        disposition=ReconciliationDisposition.ACCEPT_EXISTING,
                        refresh_need=need,
                        reason="source is not relevant to the current decision",
                    )
                )
            elif (
                freshness_by_source[state.source_id] >= demand.required_freshness
                and state.confidence >= demand.required_confidence
            ):
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
    def refresh_need(
        state: SourceState,
        demand: AwarenessDemand,
        *,
        current_freshness: float,
    ) -> float:
        if state.source_id != demand.source_id:
            raise ValueError("refresh-need source and demand ids must match")
        if not math.isfinite(current_freshness) or not 0.0 <= current_freshness <= 1.0:
            raise ValueError("current freshness must be between zero and one")
        freshness_gap = max(
            0.0,
            1.0 - current_freshness / demand.required_freshness,
        )
        confidence_gap = max(
            0.0,
            1.0 - state.confidence / demand.required_confidence,
        )
        return demand.importance * (1.0 - (1.0 - freshness_gap) * (1.0 - confidence_gap))

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
