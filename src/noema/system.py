"""Multi-agent system composition and lifecycle."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol

from .agent import AutonomousAgent
from .detectors import DetectorEngine
from .events import Event
from .kernel import NoemaKernel
from .scheduler import AsyncScheduler


class RuntimeService(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class NoemaSystem:
    """Run autonomous agents, detectors, scheduling, and a shared world model."""

    def __init__(
        self,
        *,
        kernel: NoemaKernel | None = None,
        agents: Sequence[AutonomousAgent] = (),
        detector_engines: Sequence[DetectorEngine] = (),
        services: Sequence[RuntimeService] = (),
    ) -> None:
        self.kernel = kernel or NoemaKernel()
        self.scheduler = AsyncScheduler(self.kernel)
        self._agents: list[AutonomousAgent] = list(agents)
        self._detector_engines: list[DetectorEngine] = list(detector_engines)
        self._services: list[RuntimeService] = list(services)
        self._started = False
        self._stop_event = asyncio.Event()

    @property
    def agents(self) -> tuple[AutonomousAgent, ...]:
        return tuple(self._agents)

    def add_agent(self, agent: AutonomousAgent) -> None:
        if agent.kernel is not self.kernel:
            raise ValueError("all agents in a system must share the system kernel")
        self._agents.append(agent)

    def add_detector_engine(self, engine: DetectorEngine) -> None:
        if engine.kernel is not self.kernel:
            raise ValueError("detector engine must share the system kernel")
        self._detector_engines.append(engine)

    async def start(self) -> None:
        if self._started:
            return
        await self.kernel.start()
        started_services: list[RuntimeService] = []
        started_engines: list[DetectorEngine] = []
        started_agents: list[AutonomousAgent] = []
        try:
            for service in self._services:
                started_services.append(service)
                await service.start()
            for engine in self._detector_engines:
                started_engines.append(engine)
                await engine.start()
            for agent in self._agents:
                started_agents.append(agent)
                await agent.start()
        except BaseException:
            for agent in reversed(started_agents):
                try:
                    await agent.stop(graceful=False)
                except BaseException:
                    pass
            for engine in reversed(started_engines):
                try:
                    await engine.stop()
                except BaseException:
                    pass
            for service in reversed(started_services):
                try:
                    await service.stop()
                except BaseException:
                    pass
            try:
                await self.kernel.stop()
            except BaseException:
                pass
            raise
        self._started = True
        self._stop_event.clear()

    async def emit(self, event: Event) -> Event:
        return await self.kernel.emit(event)

    async def wait_until_idle(self, *, timeout: float = 10.0) -> None:
        async with asyncio.timeout(timeout):
            while True:
                await self.kernel.bus.drain()
                await asyncio.gather(
                    *(agent.wait_until_idle(timeout=timeout) for agent in self._agents)
                )
                await self.kernel.bus.drain()
                if all(
                    agent.status().queued_events == 0 and agent.status().active_actions == 0
                    for agent in self._agents
                ):
                    return
                await asyncio.sleep(0.01)

    async def run_forever(self) -> None:
        await self.start()
        await self._stop_event.wait()

    async def stop(self) -> None:
        if not self._started:
            return
        self._stop_event.set()
        await self.scheduler.stop()
        for agent in reversed(self._agents):
            await agent.stop()
        for engine in reversed(self._detector_engines):
            await engine.stop()
        for service in reversed(self._services):
            await service.stop()
        await self.kernel.stop()
        self._started = False

    async def __aenter__(self) -> NoemaSystem:
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.stop()
