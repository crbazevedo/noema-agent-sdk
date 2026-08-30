"""Asynchronous event scheduler for self-triggering autonomous systems."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from .events import Event
from .kernel import NoemaKernel

EventFactory = Callable[[], Event]


@dataclass(frozen=True, slots=True)
class ScheduleHandle:
    id: str
    task: asyncio.Task[None]

    def cancel(self) -> None:
        self.task.cancel()


class AsyncScheduler:
    def __init__(self, kernel: NoemaKernel) -> None:
        self.kernel = kernel
        self._handles: dict[str, ScheduleHandle] = {}
        self._stopped = False

    def every(
        self,
        seconds: float,
        event_factory: EventFactory,
        *,
        jitter_seconds: float = 0.0,
        fire_immediately: bool = False,
    ) -> ScheduleHandle:
        if seconds <= 0:
            raise ValueError("schedule interval must be positive")
        if jitter_seconds < 0:
            raise ValueError("jitter cannot be negative")
        schedule_id = str(uuid4())
        task = asyncio.create_task(
            self._run_periodic(
                seconds,
                event_factory,
                jitter_seconds=jitter_seconds,
                fire_immediately=fire_immediately,
            ),
            name=f"noema-schedule-periodic:{schedule_id}",
        )
        handle = ScheduleHandle(schedule_id, task)
        self._handles[schedule_id] = handle
        task.add_done_callback(lambda _: self._handles.pop(schedule_id, None))
        return handle

    def at(self, when: datetime, event_factory: EventFactory) -> ScheduleHandle:
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        schedule_id = str(uuid4())
        task = asyncio.create_task(
            self._run_once(when, event_factory),
            name=f"noema-schedule-once:{schedule_id}",
        )
        handle = ScheduleHandle(schedule_id, task)
        self._handles[schedule_id] = handle
        task.add_done_callback(lambda _: self._handles.pop(schedule_id, None))
        return handle

    async def cancel(self, schedule_id: str) -> None:
        handle = self._handles.pop(schedule_id, None)
        if handle is None:
            return
        handle.cancel()
        await asyncio.gather(handle.task, return_exceptions=True)

    async def stop(self) -> None:
        if self._stopped:
            return
        handles = tuple(self._handles.values())
        self._handles.clear()
        for handle in handles:
            handle.cancel()
        await asyncio.gather(*(handle.task for handle in handles), return_exceptions=True)
        self._stopped = True

    async def _run_periodic(
        self,
        seconds: float,
        event_factory: EventFactory,
        *,
        jitter_seconds: float,
        fire_immediately: bool,
    ) -> None:
        if fire_immediately:
            await self.kernel.emit(event_factory())
        while True:
            delay = seconds + random.uniform(-jitter_seconds, jitter_seconds)
            await asyncio.sleep(max(0.0, delay))
            await self.kernel.emit(event_factory())

    async def _run_once(self, when: datetime, event_factory: EventFactory) -> None:
        now = datetime.now(timezone.utc)
        await asyncio.sleep(max(0.0, (when - now).total_seconds()))
        await self.kernel.emit(event_factory())
