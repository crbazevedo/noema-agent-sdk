from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from noema import (
    AutonomicRule,
    AutonomicShadowWorker,
    ComparisonOperator,
    Event,
    NoemaKernel,
    PredicateClause,
    PredicateSpec,
    RuleFamily,
    SalienceDisposition,
    SignalTemplate,
    ValueRef,
    ValueSource,
)

START = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


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
        assert worker.epoch is not None
        self.assertLess(worker.epoch.event_log_cursor, trigger.sequence or 0)
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

        await worker.stop()
        await kernel.stop()

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
