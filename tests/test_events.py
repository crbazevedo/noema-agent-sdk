from __future__ import annotations

import unittest
from dataclasses import replace

from noema import AsyncEventBus, Event, EventSchemaRegistry


class EventBusTests(unittest.IsolatedAsyncioTestCase):
    async def test_wildcard_subscription_preserves_order(self) -> None:
        bus = AsyncEventBus()
        received: list[int] = []

        async def handler(event: Event) -> None:
            received.append(int(event.payload["n"]))

        await bus.subscribe("external.*", handler)
        await bus.publish(Event("external.one", "test", {"n": 1}))
        await bus.publish(Event("external.two", "test", {"n": 2}))
        await bus.drain()
        self.assertEqual(received, [1, 2])
        await bus.stop()

    async def test_subscriber_failure_is_isolated(self) -> None:
        bus = AsyncEventBus()
        received: list[str] = []

        async def failing(event: Event) -> None:
            if event.type == "external.fail":
                raise RuntimeError("expected")
            received.append(event.type)

        await bus.subscribe("external.*", failing)
        await bus.publish(Event("external.fail", "test"))
        await bus.publish(Event("external.ok", "test"))
        await bus.drain()
        self.assertEqual(received, ["external.ok"])
        self.assertEqual(len(bus.errors), 1)
        await bus.stop()


class KernelIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_reemitting_same_event_id_is_not_republished(self) -> None:
        from noema import NoemaKernel

        kernel = NoemaKernel()
        await kernel.start()
        received: list[str] = []

        async def handler(event: Event) -> None:
            received.append(event.id)

        await kernel.bus.subscribe("external.*", handler)
        event = Event("external.once", "test")
        await kernel.emit(event)
        await kernel.emit(event)
        await kernel.bus.drain()
        self.assertEqual(received, [event.id])
        await kernel.stop()


class EventSchemaTests(unittest.TestCase):
    def test_schema_version_round_trip_and_projection_upcast(self) -> None:
        legacy = Event("external.metric", "test", {"percent": 50}, schema_version=1)
        restored = Event.from_dict(legacy.to_dict())
        self.assertEqual(restored.schema_version, 1)

        registry = EventSchemaRegistry()
        registry.register(
            "external.metric",
            1,
            upcast_to_next=lambda event: replace(
                event,
                payload={"ratio": float(event.payload["percent"]) / 100},
                schema_version=2,
            ),
        )
        registry.register(
            "external.metric",
            2,
            validator=lambda event: (
                None
                if "ratio" in event.payload
                else (_ for _ in ()).throw(ValueError("ratio required"))
            ),
        )
        current = registry.normalize(legacy)
        self.assertEqual(current.schema_version, 2)
        self.assertEqual(current.payload["ratio"], 0.5)
        self.assertEqual(current.id, legacy.id)
