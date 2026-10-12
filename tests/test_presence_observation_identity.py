from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from noema import (
    AgentPresence,
    DurableWorkCoordinator,
    FakePlanner,
    NoemaKernel,
    PresenceStatus,
    WorkProjection,
)


class PresenceObservationIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_distinct_occurrences_same_tick_and_real_redelivery(self):
        at = datetime(2026, 10, 12, tzinfo=UTC)
        kernel = NoemaKernel()
        await kernel.start()
        events = []
        for occurrence, status in (("s1", "available"), ("s2", "offline"), ("s3", "available")):
            presence = AgentPresence(
                "worker",
                PresenceStatus(status),
                1,
                at,
                at + timedelta(hours=1),
                observation_id=occurrence,
            )
            events.append(await kernel.emit(presence.to_event(source="source")))
        self.assertEqual(len({e.id for e in events}), 3)
        projection = WorkProjection()
        projection.rebuild(await kernel.history())
        self.assertEqual(projection.presence("worker").status, PresenceStatus.AVAILABLE)
        count = len(await kernel.history())
        await kernel.emit(events[-1])
        self.assertEqual(len(await kernel.history()), count)
        await kernel.stop()

    async def test_legacy_no_occurrence_id_keeps_payload_and_roundtrip(self):
        at = datetime(2026, 10, 12, tzinfo=UTC)
        presence = AgentPresence("worker", PresenceStatus.AVAILABLE, 1, at, at + timedelta(hours=1))
        self.assertNotIn("observation_id", presence.to_dict())
        event = presence.to_event(source="source")
        # Golden payload/ID from frozen pre-extension commit c7cf5e1.
        self.assertEqual(event.id, "agent-presence:6ac6aea08b9a231c1a58edefb1edae95")
        self.assertEqual(
            presence.to_dict(),
            {
                "agent_id": "worker",
                "status": "available",
                "max_concurrency": 1,
                "observed_at": "2026-10-12T00:00:00+00:00",
                "valid_until": "2026-10-12T01:00:00+00:00",
            },
        )
        self.assertEqual(AgentPresence.from_event(event), presence)
        self.assertEqual(AgentPresence.from_event(event).to_event(source="source").id, event.id)

    async def test_conflicting_source_occurrence_rejected_without_second_event(self):
        at = datetime(2026, 10, 12, tzinfo=UTC)
        kernel = NoemaKernel()
        await kernel.start()
        coordinator = DurableWorkCoordinator(
            kernel,
            planner=FakePlanner(
                nodes=(), dependencies=(), assumptions=(), done_conditions=(), replan_event_types=()
            ),
        )
        first = AgentPresence(
            "worker",
            PresenceStatus.AVAILABLE,
            1,
            at,
            at + timedelta(hours=1),
            observation_id="same-source-occurrence",
        )
        changed = AgentPresence(
            "worker",
            PresenceStatus.OFFLINE,
            1,
            at,
            at + timedelta(hours=1),
            observation_id="same-source-occurrence",
        )
        self.assertEqual(first.to_event(source="source").id, changed.to_event(source="source").id)
        await coordinator.record_presence(first)
        with self.assertRaisesRegex(ValueError, "canonical event id conflict"):
            await coordinator.record_presence(changed)
        self.assertEqual(len(await kernel.history()), 1)
        with self.assertRaises(ValueError):
            AgentPresence(
                "worker",
                PresenceStatus.AVAILABLE,
                1,
                at,
                at + timedelta(hours=1),
                observation_id="",
            )
        await kernel.stop()
