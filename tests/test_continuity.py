from __future__ import annotations

import math
import unittest
from datetime import UTC, datetime, timedelta, timezone

from noema import (
    ActionPrerequisite,
    AwarenessCoverage,
    AwarenessDemand,
    FreshnessModel,
    ObservationBudget,
    OrientationBarrier,
    SourceState,
    TemporalService,
    WakeReconciler,
)

FRIDAY = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
MONDAY = FRIDAY + timedelta(hours=65)


def source_state(
    source_id: str,
    *,
    hazard: float = 1.0,
    confidence: float = 1.0,
) -> SourceState:
    return SourceState(
        source_id=source_id,
        domain="test",
        last_observed_at=FRIDAY,
        last_cursor="baseline",
        change_hazard=hazard,
        confidence=confidence,
        refresh_cost=1.0,
        captured_at=FRIDAY,
    )


def demand(
    source_id: str,
    *,
    relevance: float = 1.0,
    sensitivity: float = 1.0,
) -> AwarenessDemand:
    return AwarenessDemand(
        source_id=source_id,
        governing_goal_refs=("goal:current",),
        relevance=relevance,
        decision_sensitivity=sensitivity,
        required_freshness=0.8,
        required_confidence=0.8,
    )


class TemporalServiceTests(unittest.TestCase):
    def test_wall_monotonic_and_world_time_remain_distinct(self) -> None:
        monotonic_values = iter((40.0, 42.5))
        service = TemporalService(
            wall_clock=lambda: MONDAY,
            monotonic_clock=lambda: next(monotonic_values),
            timezone=timezone(timedelta(hours=-3)),
        )

        self.assertEqual(service.wall_now(), MONDAY.astimezone(service.timezone))
        self.assertEqual(
            service.sleep_interval(FRIDAY, woke_at=MONDAY).elapsed_wall_time,
            timedelta(hours=65),
        )
        started = service.monotonic_now()
        self.assertEqual(
            service.elapsed_monotonic(started, ended=service.monotonic_now()),
            timedelta(seconds=2.5),
        )


class FreshnessAndReconciliationTests(unittest.TestCase):
    def test_freshness_decay_is_domain_hazard_sensitive(self) -> None:
        model = FreshnessModel()

        stable = model.evaluate(change_hazard=0.01, elapsed=timedelta(days=3))
        volatile = model.evaluate(change_hazard=2.0, elapsed=timedelta(days=3))

        self.assertTrue(math.isclose(stable, math.exp(-0.03)))
        self.assertTrue(math.isclose(volatile, math.exp(-6.0)))
        self.assertGreater(stable, volatile)

    def test_one_hundred_sources_refresh_only_four_demanded_sources(self) -> None:
        states = tuple(source_state(f"source-{index:03d}") for index in range(100))
        demands = tuple(demand(f"source-{index:03d}") for index in range(4))
        freshness = {state.source_id: 0.1 for state in states}

        plan = WakeReconciler().plan(
            states,
            demands,
            freshness_by_source=freshness,
            budget=ObservationBudget(max_cost=4.0, max_sources=4),
            created_at=MONDAY,
        )

        self.assertEqual(
            tuple(request.source_id for request in plan.requests),
            ("source-000", "source-001", "source-002", "source-003"),
        )
        self.assertEqual(plan.total_refresh_cost, 4.0)
        self.assertTrue(all(request.priority > 0.0 for request in plan.requests))

    def test_accumulated_staleness_wins_a_one_source_budget(self) -> None:
        states = (source_state("very-stale"), source_state("mildly-stale"))
        demands = (demand("very-stale"), demand("mildly-stale"))

        plan = WakeReconciler().plan(
            states,
            demands,
            freshness_by_source={"very-stale": 0.1, "mildly-stale": 0.7},
            budget=ObservationBudget(max_cost=1.0, max_sources=1),
            created_at=MONDAY,
        )

        self.assertEqual(tuple(request.source_id for request in plan.requests), ("very-stale",))

    def test_high_freshness_low_confidence_is_refreshable(self) -> None:
        state = source_state("uncertain", confidence=0.2)

        plan = WakeReconciler().plan(
            (state,),
            (demand("uncertain"),),
            freshness_by_source={"uncertain": 0.95},
            budget=ObservationBudget(max_cost=1.0, max_sources=1),
            created_at=MONDAY,
        )

        self.assertEqual(tuple(request.source_id for request in plan.requests), ("uncertain",))
        self.assertGreater(plan.requests[0].priority, 0.0)

    def test_orientation_barrier_exposes_missing_prerequisites_in_shadow(self) -> None:
        state = source_state("calendar")
        coverage = AwarenessCoverage.from_inputs(
            (state,),
            (demand("calendar"),),
            freshness_by_source={"calendar": 0.1},
        )

        decision = OrientationBarrier().evaluate(
            "reschedule-review",
            (ActionPrerequisite("calendar", 0.8, 0.8),),
            coverage,
        )

        self.assertTrue(decision.shadow)
        self.assertTrue(decision.would_block)
        self.assertEqual(decision.missing_prerequisites[0].source_id, "calendar")


if __name__ == "__main__":
    unittest.main()
