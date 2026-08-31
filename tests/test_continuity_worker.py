from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from noema import (
    ActionPrerequisite,
    AwarenessDemand,
    ContinuityProjection,
    EpistemicType,
    Event,
    FakeObservation,
    FakeSource,
    InMemoryTelemetry,
    MemoryProjection,
    MemoryProjector,
    NoemaKernel,
    ObservationBudget,
    OrientationBarrier,
    OrientationStatus,
    ReconciliationDisposition,
    SemanticAssertion,
    SituatedContinuityWorker,
    SourceState,
    TemporalService,
)

FRIDAY = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
MONDAY = FRIDAY + timedelta(hours=65)


def awareness_demand(source_id: str) -> AwarenessDemand:
    return AwarenessDemand(
        source_id=source_id,
        governing_goal_refs=("goal:release-review",),
        relevance=1.0,
        decision_sensitivity=1.0,
        required_freshness=0.8,
        required_confidence=0.8,
    )


def observation(
    cursor: str,
    occurred_at: datetime,
    subject: str,
    predicate: str,
    value: str,
    summary: str,
    priority: float,
) -> FakeObservation:
    return FakeObservation(
        cursor=cursor,
        occurred_at=occurred_at,
        subject=subject,
        predicate=predicate,
        value=value,
        confidence=0.99,
        impact_summary=summary,
        issue_priority=priority,
        affects_current_plan=True,
    )


class SituatedContinuityWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.kernel = NoemaKernel()
        await self.kernel.start()
        self.memory_worker = MemoryProjector(self.kernel, clock=lambda: MONDAY)
        await self.memory_worker.start()

    async def asyncTearDown(self) -> None:
        await self.memory_worker.stop()
        await self.kernel.stop()

    async def _seed_assertion(
        self,
        subject: str,
        predicate: str,
        value: str,
    ) -> SemanticAssertion:
        source_event = await self.kernel.emit(
            Event(
                "external.source_observed",
                "test:friday-baseline",
                {"value": value, "occurred_at": FRIDAY.isoformat()},
                id=f"baseline:{subject}:{predicate}",
                subject=subject,
                timestamp=FRIDAY,
            )
        )
        assertion = SemanticAssertion.create(
            subject=subject,
            predicate=predicate,
            value=value,
            epistemic_type=EpistemicType.OBSERVED,
            confidence=0.99,
            valid_from=FRIDAY,
            recorded_at=FRIDAY,
            source_refs=(f"event:{source_event.id}",),
            fresh_until=MONDAY + timedelta(days=1),
            mutable_world=True,
        )
        await self.kernel.emit(assertion.to_event(source="test:friday-baseline"))
        return assertion

    async def _record_assertion(
        self,
        *,
        subject: str,
        predicate: str,
        value: str,
        valid_from: datetime,
        recorded_at: datetime,
        supersedes: str | None = None,
    ) -> SemanticAssertion:
        source_event = await self.kernel.emit(
            Event(
                "external.source_observed",
                "test:historical-state",
                {"value": value, "occurred_at": valid_from.isoformat()},
                id=f"history:{subject}:{predicate}:{value}",
                subject=subject,
                timestamp=recorded_at,
            )
        )
        assertion = SemanticAssertion.create(
            subject=subject,
            predicate=predicate,
            value=value,
            epistemic_type=EpistemicType.OBSERVED,
            confidence=0.99,
            valid_from=valid_from,
            recorded_at=recorded_at,
            source_refs=(f"event:{source_event.id}",),
            fresh_until=MONDAY + timedelta(days=1),
            supersedes=supersedes,
            mutable_world=True,
        )
        await self.kernel.emit(assertion.to_event(source="test:historical-state"))
        return assertion

    async def test_sixty_five_hour_wake_selectively_reconstructs_changed_world(self) -> None:
        changes = {
            "repo": observation(
                "repo-1",
                FRIDAY + timedelta(hours=10),
                "pull-request:42",
                "status",
                "merged",
                "The pull request merged while Noema was asleep",
                0.7,
            ),
            "calendar": observation(
                "calendar-1",
                FRIDAY + timedelta(hours=35),
                "review:architecture",
                "scheduled_at",
                "2026-08-31T13:00:00+00:00",
                "The review moved earlier",
                0.85,
            ),
            "delegation": observation(
                "delegation-1",
                FRIDAY + timedelta(hours=20),
                "delegation:research",
                "status",
                "complete",
                "The delegated research completed",
                0.6,
            ),
            "dependency": observation(
                "dependency-1",
                FRIDAY + timedelta(hours=30),
                "dependency:core",
                "version",
                "3.2",
                "Dependency 3.2 changes the active integration plan",
                0.98,
            ),
        }
        hazards = {
            "repo": 1.2,
            "calendar": 1.2,
            "delegation": 0.8,
            "dependency": 0.7,
            "documents": 1.5,
            "preferences": 0.01,
        }
        sources = {
            source_id: FakeSource(
                source_id,
                hazard=hazard,
                cursor="friday",
                observations=((changes[source_id],) if source_id in changes else ()),
                refresh_cost=1.0,
            )
            for source_id, hazard in hazards.items()
        }
        monotonic_values = iter((100.0, 100.25))
        telemetry = InMemoryTelemetry()
        worker = SituatedContinuityWorker(
            self.kernel,
            sources=sources,
            temporal=TemporalService(
                wall_clock=lambda: MONDAY,
                monotonic_clock=lambda: next(monotonic_values),
            ),
            telemetry=telemetry,
        )
        for source_id, hazard in hazards.items():
            await worker.record_source_state(
                SourceState(
                    source_id=source_id,
                    domain=source_id,
                    last_observed_at=FRIDAY,
                    last_cursor="friday",
                    change_hazard=hazard,
                    confidence=1.0,
                    refresh_cost=1.0,
                    captured_at=FRIDAY,
                )
            )
        prior = {
            "repo": await self._seed_assertion("pull-request:42", "status", "open"),
            "calendar": await self._seed_assertion(
                "review:architecture", "scheduled_at", "2026-09-01T14:00:00+00:00"
            ),
            "delegation": await self._seed_assertion("delegation:research", "status", "running"),
            "dependency": await self._seed_assertion("dependency:core", "version", "3.1"),
        }
        await self.kernel.bus.drain()

        report = await worker.wake(
            demands=tuple(awareness_demand(source_id) for source_id in changes),
            previous_active_at=FRIDAY,
            budget=ObservationBudget(max_cost=4.0, max_sources=4),
        )
        await self.kernel.bus.drain()

        self.assertEqual(report.status, OrientationStatus.ORIENTED)
        self.assertEqual(report.epoch.elapsed_wall_time, timedelta(hours=65))
        self.assertEqual(
            report.refreshed_source_ids,
            ("calendar", "delegation", "dependency", "repo"),
        )
        self.assertNotIn("documents", report.refreshed_source_ids)
        self.assertNotIn("preferences", report.refreshed_source_ids)
        self.assertEqual(report.metrics.events_fetched, 4)
        self.assertEqual(report.metrics.beliefs_updated, 4)
        latency = next(
            metric
            for metric in telemetry.metrics
            if metric.name == "continuity.orientation_latency_seconds"
        )
        self.assertEqual(latency.value, 0.25)
        self.assertNotIn("orientation_latency_seconds", report.metrics.to_dict())
        self.assertIsNotNone(report.highest_value_issue)
        assert report.highest_value_issue is not None
        self.assertEqual(report.highest_value_issue.source_id, "dependency")

        delayed_world_time = changes["repo"].occurred_at
        friday_knowledge = self.memory_worker.projection.belief(
            "pull-request:42",
            "status",
            valid_at=delayed_world_time,
            known_at=FRIDAY,
            include_stale=True,
        )
        monday_knowledge = self.memory_worker.projection.belief(
            "pull-request:42",
            "status",
            valid_at=delayed_world_time,
            known_at=MONDAY,
            include_stale=True,
        )
        self.assertEqual(friday_knowledge.value, "open")
        self.assertEqual(friday_knowledge.assertions, (prior["repo"],))
        self.assertEqual(monday_knowledge.value, "merged")

        history = await self.kernel.history()
        reconstructed = ContinuityProjection()
        reconstructed.rebuild(history)
        self.assertEqual(reconstructed.latest_report, report)
        observed = next(event for event in history if event.id == "fake-observation:repo:repo-1")
        self.assertEqual(observed.timestamp, MONDAY)
        self.assertEqual(observed.payload["occurred_at"], delayed_world_time.isoformat())
        self.assertFalse(
            any(
                event.type.startswith(("action.", "capability.", "deliberation."))
                for event in history
            )
        )

    async def test_no_change_eight_hour_wake_does_no_deliberate_work(self) -> None:
        woke_at = FRIDAY + timedelta(hours=8)
        source = FakeSource(
            "preferences",
            hazard=0.01,
            cursor="friday",
            refresh_cost=1.0,
        )
        monotonic_values = iter((20.0, 20.01))
        worker = SituatedContinuityWorker(
            self.kernel,
            sources={"preferences": source},
            temporal=TemporalService(
                wall_clock=lambda: woke_at,
                monotonic_clock=lambda: next(monotonic_values),
            ),
        )
        await worker.record_source_state(
            SourceState(
                source_id="preferences",
                domain="preferences",
                last_observed_at=FRIDAY,
                last_cursor="friday",
                change_hazard=0.01,
                confidence=1.0,
                refresh_cost=1.0,
                captured_at=FRIDAY,
            )
        )

        report = await worker.wake(
            demands=(awareness_demand("preferences"),),
            previous_active_at=FRIDAY,
        )

        self.assertEqual(report.status, OrientationStatus.ORIENTED)
        self.assertEqual(report.refreshed_source_ids, ())
        self.assertEqual(report.changed_source_ids, ())
        self.assertEqual(report.metrics.events_fetched, 0)
        self.assertEqual(report.metrics.beliefs_updated, 0)
        self.assertIn("no consequential action", report.summary.lower())
        history = await self.kernel.history()
        self.assertFalse(
            any(
                event.type.startswith(("action.", "capability.", "deliberation."))
                for event in history
            )
        )

    async def test_unavailable_source_keeps_orientation_explicitly_incomplete(self) -> None:
        source = FakeSource(
            "calendar",
            hazard=2.0,
            cursor="friday",
            refresh_cost=1.0,
            available=False,
        )
        monotonic_values = iter((30.0, 30.1))
        worker = SituatedContinuityWorker(
            self.kernel,
            sources={"calendar": source},
            temporal=TemporalService(
                wall_clock=lambda: MONDAY,
                monotonic_clock=lambda: next(monotonic_values),
            ),
        )
        await worker.record_source_state(
            SourceState(
                source_id="calendar",
                domain="calendar",
                last_observed_at=FRIDAY,
                last_cursor="friday",
                change_hazard=2.0,
                confidence=1.0,
                refresh_cost=1.0,
                captured_at=FRIDAY,
            )
        )

        report = await worker.wake(
            demands=(awareness_demand("calendar"),),
            previous_active_at=FRIDAY,
        )

        self.assertEqual(report.status, OrientationStatus.INCOMPLETE)
        self.assertEqual(report.unavailable_source_ids, ("calendar",))
        self.assertEqual(report.coverage.gaps[0].source_id, "calendar")
        calendar_decision = next(
            decision for decision in report.decisions if decision.source_id == "calendar"
        )
        self.assertEqual(
            calendar_decision.disposition,
            ReconciliationDisposition.MARK_UNCERTAIN,
        )
        barrier = OrientationBarrier().evaluate(
            "accept-calendar-invite",
            (ActionPrerequisite("calendar", 0.8, 0.8),),
            report.coverage,
        )
        self.assertTrue(barrier.shadow)
        self.assertTrue(barrier.would_block)

    async def test_late_observation_inserts_between_valid_time_neighbors(self) -> None:
        await self.memory_worker.stop()
        merged_at = FRIDAY + timedelta(hours=2)
        closed_at = FRIDAY + timedelta(hours=18)
        open_assertion = await self._record_assertion(
            subject="pull-request:42",
            predicate="status",
            value="open",
            valid_from=FRIDAY,
            recorded_at=FRIDAY,
        )
        closed_assertion = await self._record_assertion(
            subject="pull-request:42",
            predicate="status",
            value="closed",
            valid_from=closed_at,
            recorded_at=closed_at,
            supersedes=open_assertion.assertion_id,
        )
        source = FakeSource(
            "repo",
            hazard=1.0,
            cursor="saturday",
            observations=(
                observation(
                    "late-merge",
                    merged_at,
                    "pull-request:42",
                    "status",
                    "merged",
                    "The merge was reported after a later state was already known",
                    0.8,
                ),
            ),
            refresh_cost=1.0,
        )
        monotonic_values = iter((40.0, 40.2))
        worker = SituatedContinuityWorker(
            self.kernel,
            sources={"repo": source},
            temporal=TemporalService(
                wall_clock=lambda: MONDAY,
                monotonic_clock=lambda: next(monotonic_values),
            ),
        )
        await worker.record_source_state(
            SourceState(
                source_id="repo",
                domain="repository",
                last_observed_at=closed_at,
                last_cursor="saturday",
                change_hazard=1.0,
                confidence=1.0,
                refresh_cost=1.0,
                captured_at=closed_at,
            )
        )

        report = await worker.wake(
            demands=(awareness_demand("repo"),),
            previous_active_at=FRIDAY,
        )

        self.assertEqual(report.status, OrientationStatus.ORIENTED)
        self.assertEqual(self.memory_worker.projection.assertions, ())
        memory = MemoryProjection()
        memory.rebuild(await self.kernel.history())
        merged_assertion = next(
            assertion for assertion in memory.assertions if assertion.value == "merged"
        )
        self.assertEqual(merged_assertion.supersedes, open_assertion.assertion_id)
        self.assertEqual(merged_assertion.valid_to, closed_assertion.valid_from)
        self.assertEqual(
            memory.belief(
                "pull-request:42",
                "status",
                valid_at=FRIDAY + timedelta(hours=1),
                known_at=MONDAY,
                include_stale=True,
            ).value,
            "open",
        )
        self.assertEqual(
            memory.belief(
                "pull-request:42",
                "status",
                valid_at=FRIDAY + timedelta(hours=3),
                known_at=MONDAY,
                include_stale=True,
            ).value,
            "merged",
        )
        self.assertEqual(
            memory.belief(
                "pull-request:42",
                "status",
                valid_at=FRIDAY + timedelta(hours=42),
                known_at=MONDAY,
                include_stale=True,
            ).value,
            "closed",
        )

    async def test_runtime_latency_does_not_change_semantic_report_identity(self) -> None:
        async def run(duration: float) -> tuple[str, float]:
            kernel = NoemaKernel()
            await kernel.start()
            telemetry = InMemoryTelemetry()
            monotonic_values = iter((10.0, 10.0 + duration))
            worker = SituatedContinuityWorker(
                kernel,
                sources={
                    "preferences": FakeSource(
                        "preferences",
                        hazard=0.01,
                        cursor="baseline",
                        refresh_cost=1.0,
                    )
                },
                temporal=TemporalService(
                    wall_clock=lambda: FRIDAY + timedelta(hours=8),
                    monotonic_clock=lambda: next(monotonic_values),
                ),
                telemetry=telemetry,
            )
            await worker.record_source_state(
                SourceState(
                    source_id="preferences",
                    domain="preferences",
                    last_observed_at=FRIDAY,
                    last_cursor="baseline",
                    change_hazard=0.01,
                    confidence=1.0,
                    refresh_cost=1.0,
                    captured_at=FRIDAY,
                )
            )
            report = await worker.wake(
                demands=(awareness_demand("preferences"),),
                previous_active_at=FRIDAY,
            )
            latency = next(
                metric.value
                for metric in telemetry.metrics
                if metric.name == "continuity.orientation_latency_seconds"
            )
            await kernel.stop()
            return report.report_id, latency

        fast_id, fast_latency = await run(0.1)
        slow_id, slow_latency = await run(4.7)

        self.assertEqual(fast_id, slow_id)
        self.assertEqual(fast_latency, 0.1)
        self.assertEqual(slow_latency, 4.7)


if __name__ == "__main__":
    unittest.main()
