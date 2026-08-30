from __future__ import annotations

import unittest

from noema import AsyncScheduler, Event, NoemaKernel
from noema.testing import EventCollector, wait_for


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_periodic_events_trigger_without_human_input(self) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        collector = await EventCollector(kernel, "timer.tick").start()
        scheduler = AsyncScheduler(kernel)
        handle = scheduler.every(
            0.01,
            lambda: Event("timer.tick", "scheduler"),
            fire_immediately=True,
        )
        await wait_for(lambda: len(collector.events) >= 2, timeout=1)
        await scheduler.cancel(handle.id)
        await collector.stop()
        await kernel.stop()
