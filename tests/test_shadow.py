from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from noema import (
    CONSUMER_CHECKPOINT_EVENT,
    AutonomicRule,
    AutonomicShadowWorker,
    ComparisonOperator,
    Event,
    InMemoryEventStore,
    InMemoryTelemetry,
    NoemaKernel,
    PredicateClause,
    PredicateSpec,
    RuleFamily,
    SalienceDisposition,
    SignalTemplate,
    SQLiteEventStore,
    ValueRef,
    ValueSource,
)

START = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


class FailOnceEventStore(InMemoryEventStore):
    def __init__(self) -> None:
        super().__init__()
        self.fail_before_type: str | None = None
        self.fail_after_type: str | None = None

    async def append(self, event: Event) -> Event:
        if event.type == self.fail_before_type:
            self.fail_before_type = None
            raise RuntimeError(f"crash before {event.type}")
        stored = await super().append(event)
        if event.type == self.fail_after_type:
            self.fail_after_type = None
            raise RuntimeError(f"crash after {event.type}")
        return stored


def ready_rule(version: int) -> AutonomicRule:
    return AutonomicRule(
        rule_id="work.ready",
        version=version,
        purpose="Observe work readiness without causing an effect",
        family=RuleFamily.PREDICATE,
        trigger="work.ready",
        spec=PredicateSpec(
            (
                PredicateClause(
                    ValueRef(ValueSource.EVENT, "payload.ready"),
                    ComparisonOperator.EQUALS,
                    True,
                ),
            )
        ),
        output=SignalTemplate(
            "work.ready",
            salience=0.9,
            urgency=0.95,
            expected_value=2.0,
            suggested_disposition=SalienceDisposition.WAKE,
        ),
    )


class AutonomicShadowWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_continuous_worker_persists_only_shadow_observations(self) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        await kernel.emit(
            ready_rule(1).to_event(
                source="test",
                timestamp=START - timedelta(seconds=1),
            )
        )
        worker = AutonomicShadowWorker(kernel, clock=lambda: START)
        await worker.start()
        trigger = await kernel.emit(
            Event(
                "work.ready",
                "test",
                {"ready": True},
                subject="work:1",
                id="continuous-ready",
                timestamp=START + timedelta(seconds=1),
            )
        )
        await kernel.bus.drain()
        recheck = await kernel.emit(
            Event(
                "system.tick",
                "test",
                {},
                id="continuous-recheck",
                timestamp=START + timedelta(seconds=2),
            )
        )
        await kernel.bus.drain()
        history = await kernel.history()
        evaluations = [event for event in history if event.type == "rule.evaluation_traced"]
        decisions = [event for event in history if event.type == "rule.salience_decision_shadowed"]

        self.assertIsNotNone(worker.epoch)
        self.assertIsNotNone(worker.checkpoint)
        assert worker.epoch is not None
        assert worker.checkpoint is not None
        self.assertLess(worker.epoch.event_log_cursor, trigger.sequence or 0)
        self.assertEqual(worker.checkpoint.last_completed_sequence, recheck.sequence)
        self.assertEqual(len(evaluations), 1)
        self.assertIsNotNone(evaluations[0].payload["signal_would_emit"])
        self.assertEqual(len(decisions), 2)
        self.assertEqual(decisions[0].payload["disposition"], "wake")
        self.assertIs(decisions[0].payload["shadow"], True)
        self.assertEqual(decisions[0].payload["trigger_event_id"], trigger.id)
        self.assertEqual(decisions[0].causation_id, trigger.id)
        self.assertEqual(decisions[1].payload["trigger_event_id"], recheck.id)
        self.assertNotEqual(decisions[0].id, decisions[1].id)
        self.assertFalse(
            any(event.type.startswith(("action.", "capability.")) for event in history)
        )
        self.assertIsInstance(worker.telemetry, InMemoryTelemetry)
        telemetry = worker.telemetry
        assert isinstance(telemetry, InMemoryTelemetry)
        metric_names = {metric.name for metric in telemetry.metrics}
        self.assertTrue(
            {
                "shadow.events_replayed_per_trigger",
                "shadow.situation_rebuild_ms",
                "shadow.rule_evaluation_ms",
                "shadow.salience_resolution_ms",
                "shadow.event_write_ms",
                "consumer.processing_lag_events",
            }.issubset(metric_names)
        )

        await worker.stop()
        await kernel.stop()

    async def test_crash_before_trace_replays_trigger_from_durable_checkpoint(self) -> None:
        store = FailOnceEventStore()
        kernel, worker = await self._started_worker(store)
        baseline = worker.checkpoint
        assert baseline is not None
        store.fail_before_type = "rule.evaluation_traced"
        trigger = await self._emit_ready(kernel, "crash-before-trace")
        await kernel.bus.drain()

        self.assertEqual(worker.checkpoint, baseline)
        self.assertTrue(
            any(
                event.id == trigger.id and "before rule.evaluation_traced" in str(error)
                for event, error in kernel.bus.errors
            )
        )
        await worker.stop()

        recovered = AutonomicShadowWorker(kernel, clock=lambda: START + timedelta(minutes=1))
        await recovered.start()
        await kernel.bus.drain()
        history = await kernel.history()
        self.assertEqual(self._event_count(history, "rule.evaluation_traced"), 1)
        self.assertEqual(self._event_count(history, "rule.salience_decision_shadowed"), 1)
        assert recovered.checkpoint is not None
        self.assertEqual(recovered.checkpoint.last_completed_sequence, trigger.sequence)

        await recovered.stop()
        await kernel.stop()

    async def test_completed_checkpoint_restores_epoch_and_signal_workspace(self) -> None:
        store = FailOnceEventStore()
        kernel, worker = await self._started_worker(store)
        await self._emit_ready(kernel, "completed-before-restart")
        await kernel.bus.drain()
        original_epoch = worker.epoch
        assert original_epoch is not None
        await worker.stop()

        recovered = AutonomicShadowWorker(kernel, clock=lambda: START + timedelta(minutes=1))
        await recovered.start()
        self.assertEqual(recovered.epoch, original_epoch)
        await kernel.emit(
            Event(
                "system.tick",
                "test",
                {},
                id="tick-after-restart",
                timestamp=START + timedelta(seconds=3),
            )
        )
        await kernel.bus.drain()
        decisions = [
            event
            for event in await kernel.history()
            if event.type == "rule.salience_decision_shadowed"
        ]
        self.assertEqual(len(decisions), 2)
        self.assertEqual(decisions[-1].payload["trigger_event_id"], "tick-after-restart")

        await recovered.stop()
        await kernel.stop()

    async def test_sqlite_process_restart_restores_durable_checkpoint(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "shadow.db"
            first_kernel = NoemaKernel(store=SQLiteEventStore(path))
            await first_kernel.start()
            await first_kernel.emit(ready_rule(1).to_event(source="test", timestamp=START))
            first_worker = AutonomicShadowWorker(
                first_kernel,
                clock=lambda: START + timedelta(seconds=1),
            )
            await first_worker.start()
            trigger = await self._emit_ready(first_kernel, "sqlite-before-restart")
            await first_kernel.bus.drain()
            original_checkpoint = first_worker.checkpoint
            original_epoch = first_worker.epoch
            await first_worker.stop()
            await first_kernel.stop()

            second_kernel = NoemaKernel(store=SQLiteEventStore(path))
            await second_kernel.start()
            second_worker = AutonomicShadowWorker(
                second_kernel,
                clock=lambda: START + timedelta(minutes=1),
            )
            await second_worker.start()
            self.assertEqual(second_worker.checkpoint, original_checkpoint)
            self.assertEqual(second_worker.epoch, original_epoch)
            assert second_worker.checkpoint is not None
            self.assertEqual(second_worker.checkpoint.last_completed_sequence, trigger.sequence)

            await second_worker.stop()
            await second_kernel.stop()

    async def test_crash_after_trace_before_decision_reuses_trace_idempotently(self) -> None:
        store = FailOnceEventStore()
        kernel, worker = await self._started_worker(store)
        baseline = worker.checkpoint
        assert baseline is not None
        store.fail_before_type = "rule.salience_decision_shadowed"
        trigger = await self._emit_ready(kernel, "crash-before-decision")
        await kernel.bus.drain()
        history = await kernel.history()

        self.assertEqual(self._event_count(history, "rule.evaluation_traced"), 1)
        self.assertEqual(self._event_count(history, "rule.salience_decision_shadowed"), 0)
        self.assertEqual(worker.checkpoint, baseline)
        await worker.stop()

        recovered = AutonomicShadowWorker(kernel, clock=lambda: START + timedelta(minutes=1))
        await recovered.start()
        await kernel.bus.drain()
        history = await kernel.history()
        traces = [event for event in history if event.type == "rule.evaluation_traced"]
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].causation_id, trigger.id)
        self.assertEqual(self._event_count(history, "rule.salience_decision_shadowed"), 1)
        assert recovered.checkpoint is not None
        self.assertEqual(recovered.checkpoint.last_completed_sequence, trigger.sequence)

        await recovered.stop()
        await kernel.stop()

    async def test_replaying_completed_outputs_is_idempotent_before_checkpoint(self) -> None:
        store = FailOnceEventStore()
        kernel, worker = await self._started_worker(store)
        baseline = worker.checkpoint
        assert baseline is not None
        store.fail_before_type = CONSUMER_CHECKPOINT_EVENT
        trigger = await self._emit_ready(kernel, "crash-before-checkpoint")
        await kernel.bus.drain()
        history = await kernel.history()

        self.assertEqual(self._event_count(history, "rule.evaluation_traced"), 1)
        self.assertEqual(self._event_count(history, "rule.salience_decision_shadowed"), 1)
        self.assertEqual(worker.checkpoint, baseline)
        await worker.stop()

        recovered = AutonomicShadowWorker(kernel, clock=lambda: START + timedelta(minutes=1))
        await recovered.start()
        await kernel.bus.drain()
        history = await kernel.history()
        self.assertEqual(self._event_count(history, "rule.evaluation_traced"), 1)
        self.assertEqual(self._event_count(history, "rule.salience_decision_shadowed"), 1)
        completed = [
            event
            for event in history
            if event.type == CONSUMER_CHECKPOINT_EVENT
            and event.payload["last_completed_sequence"] == trigger.sequence
        ]
        self.assertEqual(len(completed), 1)

        await recovered.stop()
        await kernel.stop()

    async def _started_worker(
        self,
        store: FailOnceEventStore,
    ) -> tuple[NoemaKernel, AutonomicShadowWorker]:
        kernel = NoemaKernel(store=store)
        await kernel.start()
        await kernel.emit(ready_rule(1).to_event(source="test", timestamp=START))
        worker = AutonomicShadowWorker(kernel, clock=lambda: START + timedelta(seconds=1))
        await worker.start()
        await kernel.bus.drain()
        return kernel, worker

    @staticmethod
    async def _emit_ready(kernel: NoemaKernel, event_id: str) -> Event:
        return await kernel.emit(
            Event(
                "work.ready",
                "test",
                {"ready": True},
                subject=f"work:{event_id}",
                id=event_id,
                timestamp=START + timedelta(seconds=2),
            )
        )

    @staticmethod
    def _event_count(history: list[Event], event_type: str) -> int:
        return sum(event.type == event_type for event in history)

    async def test_new_rule_version_waits_for_explicit_epoch_rotation(self) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        await kernel.emit(ready_rule(1).to_event(source="test", timestamp=START))
        worker = AutonomicShadowWorker(kernel, clock=lambda: START + timedelta(seconds=1))
        await worker.start()

        await kernel.emit(
            ready_rule(2).to_event(source="test", timestamp=START + timedelta(seconds=2))
        )
        await kernel.emit(
            Event(
                "work.ready",
                "test",
                {"ready": True},
                subject="work:1",
                id="before-rotation",
                timestamp=START + timedelta(seconds=3),
            )
        )
        await kernel.bus.drain()
        await worker.rotate_epoch()
        await kernel.emit(
            Event(
                "work.ready",
                "test",
                {"ready": True},
                subject="work:2",
                id="after-rotation",
                timestamp=START + timedelta(seconds=4),
            )
        )
        await kernel.bus.drain()

        evaluations = [
            event for event in await kernel.history() if event.type == "rule.evaluation_traced"
        ]
        self.assertEqual([event.payload["version"] for event in evaluations], [1, 2])

        await worker.stop()
        await kernel.stop()
