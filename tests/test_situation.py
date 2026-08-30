from __future__ import annotations

import unittest
from datetime import timedelta

from noema import Event, NoemaKernel
from noema.types import utc_now


class SituationTests(unittest.IsolatedAsyncioTestCase):
    async def test_projects_graph_goals_commitments_and_risks(self) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        await kernel.emit(
            Event(
                "entity.upserted",
                "test",
                {"id": "service:api", "kind": "service", "attributes": {"tier": 1}},
            )
        )
        await kernel.emit(
            Event(
                "entity.upserted",
                "test",
                {"id": "team:platform", "kind": "team"},
            )
        )
        await kernel.emit(
            Event(
                "relation.upserted",
                "test",
                {
                    "id": "owns:platform:api",
                    "source_id": "team:platform",
                    "target_id": "service:api",
                    "kind": "owns",
                },
            )
        )
        await kernel.emit(Event("fact.observed", "test", {"key": "api.health", "value": "ok"}))
        await kernel.emit(
            Event(
                "goal.created",
                "test",
                {"id": "g1", "description": "Keep API healthy", "priority": 1.0},
            )
        )
        await kernel.emit(
            Event(
                "commitment.created",
                "test",
                {
                    "id": "c1",
                    "description": "Review SLO",
                    "owner": "agent",
                    "deadline": (utc_now() + timedelta(hours=1)).isoformat(),
                },
            )
        )
        await kernel.emit(
            Event(
                "risk.detected",
                "test",
                {"id": "r1", "description": "Latency", "severity": 0.8},
            )
        )
        snapshot = await kernel.snapshot()
        self.assertEqual(snapshot.fact("api.health"), "ok")
        self.assertEqual(snapshot.entities["service:api"].kind, "service")
        self.assertEqual(snapshot.relations_from("team:platform", kind="owns")[0].target_id, "service:api")
        self.assertEqual(len(snapshot.active_goals()), 1)
        self.assertEqual(len(snapshot.open_commitments()), 1)
        self.assertEqual(len(snapshot.active_risks()), 1)
        await kernel.stop()
