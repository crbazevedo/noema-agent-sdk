"""Event-sourced kernel shared by autonomous agents."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from .events import AsyncEventBus, Event
from .situation import SituationModel, SituationSnapshot
from .store import EventStore, InMemoryEventStore


class NoemaKernel:
    """Persist, project, and publish every event in causal order."""

    def __init__(
        self,
        *,
        store: EventStore | None = None,
        bus: AsyncEventBus | None = None,
        situation: SituationModel | None = None,
    ) -> None:
        self.store = store or InMemoryEventStore()
        self.bus = bus or AsyncEventBus()
        self.situation = situation or SituationModel()
        self._emit_lock = asyncio.Lock()
        self._started = False
        self._stopped = False

    @property
    def started(self) -> bool:
        return self._started and not self._stopped

    async def start(self, *, replay: bool = True) -> None:
        if self._stopped:
            raise RuntimeError("kernel has already been stopped")
        if self._started:
            return
        if replay:
            events = await self.store.read()
            await self.situation.rebuild(events)
        await self.bus.start()
        self._started = True

    async def emit(self, event: Event) -> Event:
        if not self._started:
            await self.start()
        async with self._emit_lock:
            stored = await self.store.append(event)
            if stored.sequence is not None and stored.sequence <= self.situation.version:
                # Idempotent re-emission of an already projected event.
                return stored
            await self.situation.apply(stored)
            await self.bus.publish(stored)
            return stored

    async def emit_many(self, events: Sequence[Event]) -> tuple[Event, ...]:
        stored: list[Event] = []
        for event in events:
            stored.append(await self.emit(event))
        return tuple(stored)

    async def snapshot(self) -> SituationSnapshot:
        return await self.situation.snapshot()

    async def history(
        self,
        *,
        after_sequence: int = 0,
        limit: int | None = None,
        types: Sequence[str] | None = None,
    ) -> list[Event]:
        return await self.store.read(
            after_sequence=after_sequence,
            limit=limit,
            types=types,
        )

    async def stop(self) -> None:
        if self._stopped:
            return
        await self.bus.stop()
        await self.store.close()
        self._stopped = True
        self._started = False

    async def __aenter__(self) -> "NoemaKernel":
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.stop()
