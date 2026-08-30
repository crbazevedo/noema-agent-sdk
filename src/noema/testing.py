"""Testing utilities for deterministic autonomous-system tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from .events import Event
from .kernel import NoemaKernel


async def wait_for(
    predicate: Callable[[], bool],
    *,
    timeout: float = 2.0,
    interval: float = 0.01,
) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(interval)


class EventCollector:
    def __init__(self, kernel: NoemaKernel, pattern: str = "*") -> None:
        self.kernel = kernel
        self.pattern = pattern
        self.events: list[Event] = []
        self._subscription_id: str | None = None

    async def start(self) -> EventCollector:
        self._subscription_id = await self.kernel.bus.subscribe(self.pattern, self._collect)
        return self

    async def stop(self) -> None:
        if self._subscription_id is not None:
            await self.kernel.bus.unsubscribe(self._subscription_id)
            self._subscription_id = None

    async def _collect(self, event: Event) -> None:
        self.events.append(event)

    def of_type(self, event_type: str) -> list[Event]:
        return [event for event in self.events if event.type == event_type]
