from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from noema import ConcurrentAppendError, Event, InMemoryEventStore, SQLiteEventStore


class EventStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_in_memory_store_is_idempotent_by_event_id(self) -> None:
        store = InMemoryEventStore()
        event = Event("test.event", "test")
        first = await store.append(event)
        second = await store.append(event)
        self.assertEqual(first.sequence, 1)
        self.assertEqual(second.sequence, 1)
        self.assertEqual(len(await store.read()), 1)

    async def test_sqlite_store_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite3"
            store = SQLiteEventStore(path)
            stored = await store.append(
                Event(
                    "external.metric",
                    "sensor",
                    {"value": 0.9},
                    correlation_id="corr-1",
                )
            )
            self.assertEqual(stored.sequence, 1)
            events = await store.read(types=["external.metric"])
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].payload["value"], 0.9)
            self.assertEqual(events[0].correlation_id, "corr-1")
            self.assertEqual(await store.latest_sequence(), 1)
            await store.close()

    async def test_in_memory_conditional_append_has_one_head_winner(self) -> None:
        store = InMemoryEventStore()
        results = await asyncio.gather(
            store.append_if_head(
                Event("test.first", "test"),
                expected_head_sequence=0,
            ),
            store.append_if_head(
                Event("test.second", "test"),
                expected_head_sequence=0,
            ),
            return_exceptions=True,
        )

        self.assertEqual(sum(isinstance(value, Event) for value in results), 1)
        self.assertEqual(
            sum(isinstance(value, ConcurrentAppendError) for value in results),
            1,
        )
        self.assertEqual(len(await store.read()), 1)

    async def test_sqlite_conditional_append_is_atomic_across_connections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite3"
            first = SQLiteEventStore(path)
            second = SQLiteEventStore(path)
            results = await asyncio.gather(
                first.append_if_head(
                    Event("test.first", "test"),
                    expected_head_sequence=0,
                ),
                second.append_if_head(
                    Event("test.second", "test"),
                    expected_head_sequence=0,
                ),
                return_exceptions=True,
            )

            self.assertEqual(sum(isinstance(value, Event) for value in results), 1)
            self.assertEqual(
                sum(isinstance(value, ConcurrentAppendError) for value in results),
                1,
            )
            self.assertEqual(len(await first.read()), 1)
            await first.close()
            await second.close()

    async def test_conditional_append_preserves_event_id_idempotency(self) -> None:
        store = InMemoryEventStore()
        event = Event("test.once", "test")
        stored = await store.append_if_head(event, expected_head_sequence=0)
        repeated = await store.append_if_head(event, expected_head_sequence=0)

        self.assertEqual(repeated, stored)
        self.assertEqual(len(await store.read()), 1)


class ReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_history_rebuilds_situation_after_restart(self) -> None:
        from noema import NoemaKernel

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite3"
            first_store = SQLiteEventStore(path)
            first_kernel = NoemaKernel(store=first_store)
            await first_kernel.start()
            await first_kernel.emit(
                Event("fact.observed", "sensor", {"key": "system.mode", "value": "active"})
            )
            await first_kernel.stop()

            second_store = SQLiteEventStore(path)
            second_kernel = NoemaKernel(store=second_store)
            await second_kernel.start(replay=True)
            snapshot = await second_kernel.snapshot()
            self.assertEqual(snapshot.fact("system.mode"), "active")
            self.assertEqual(snapshot.version, 1)
            await second_kernel.stop()
