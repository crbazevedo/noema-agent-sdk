from __future__ import annotations

import unittest
from datetime import timedelta

from noema import DeadlineRiskDetector, DetectorEngine, Event, NoemaKernel
from noema.types import utc_now


class DetectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_deadline_detector_raises_situation_risk(self) -> None:
        kernel = NoemaKernel()
        engine = DetectorEngine(
            kernel=kernel,
            detectors=[DeadlineRiskDetector(horizon=timedelta(hours=2))],
        )
        await engine.start()
        await kernel.emit(
            Event(
                "commitment.created",
                "test",
                {
                    "id": "c1",
                    "description": "Ship release",
                    "owner": "agent",
                    "priority": 1.0,
                    "deadline": (utc_now() + timedelta(minutes=10)).isoformat(),
                },
            )
        )
        await kernel.emit(Event("timer.heartbeat", "clock"))
        await kernel.bus.drain()
        snapshot = await kernel.snapshot()
        self.assertTrue(snapshot.risks["deadline:c1"].active)
        await engine.stop()
        await kernel.stop()
