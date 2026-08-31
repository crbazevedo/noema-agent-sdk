"""Crash-recoverable projector for persistent cognitive memory."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime

from .checkpoints import (
    CONSUMER_CHECKPOINT_EVENT,
    ConsumerCheckpoint,
    ConsumerCheckpointProjection,
)
from .events import Event
from .kernel import NoemaKernel
from .memory import MemoryProjection
from .telemetry import InMemoryTelemetry, Metric, TelemetrySink
from .types import utc_now

Clock = Callable[[], datetime]


class MemoryProjector:
    """Project canonical history, writing derived memory events before checkpoints."""

    def __init__(
        self,
        kernel: NoemaKernel,
        *,
        projection: MemoryProjection | None = None,
        telemetry: TelemetrySink | None = None,
        consumer_id: str = "persistent-cognitive-memory",
        source: str = "memory:projector",
        clock: Clock = utc_now,
    ) -> None:
        if not consumer_id.strip() or not source.strip():
            raise ValueError("memory projector consumer id and source must be non-empty")
        self.kernel = kernel
        self.projection = projection or MemoryProjection()
        self.telemetry = telemetry or InMemoryTelemetry()
        self.consumer_id = consumer_id
        self.source = source
        self.clock = clock
        self._checkpoint: ConsumerCheckpoint | None = None
        self._subscription_id: str | None = None
        self._processed_event_ids: set[str] = set()
        self._ready = asyncio.Event()
        self._lock = asyncio.Lock()
        self._started = False

    @property
    def checkpoint(self) -> ConsumerCheckpoint | None:
        return self._checkpoint

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        if not self.kernel.started:
            await self.kernel.start()
        self._ready.clear()
        self._subscription_id = await self.kernel.bus.subscribe("*", self._handle_event)
        try:
            history = await self.kernel.history()
            checkpoint = self._restore_projection(history)
            self._started = True
            self._ready.set()
            after_sequence = checkpoint.last_completed_sequence if checkpoint is not None else 0
            catchup = await self.kernel.history(after_sequence=after_sequence)
            for event in catchup:
                await self._handle_event(event)
        except BaseException:
            self._started = False
            self._ready.set()
            subscription_id = self._subscription_id
            self._subscription_id = None
            if subscription_id is not None:
                await self.kernel.bus.unsubscribe(subscription_id)
            raise

    async def stop(self) -> None:
        if not self._started and self._subscription_id is None:
            return
        self._started = False
        self._ready.set()
        subscription_id = self._subscription_id
        self._subscription_id = None
        if subscription_id is not None:
            await self.kernel.bus.unsubscribe(subscription_id)

    async def _handle_event(self, event: Event) -> None:
        await self._ready.wait()
        if not self._started:
            return
        async with self._lock:
            if event.id in self._processed_event_ids:
                return
            self._processed_event_ids.add(event.id)
            try:
                if event.type == CONSUMER_CHECKPOINT_EVENT:
                    return
                if event.sequence is None:
                    raise ValueError("memory projector requires canonical sequenced events")
                checkpoint = self._checkpoint
                if checkpoint is not None and event.sequence <= checkpoint.last_completed_sequence:
                    return
                await self._process_event(event)
            except asyncio.CancelledError:
                self._processed_event_ids.discard(event.id)
                raise
            except BaseException:
                await self._recover_projection()
                raise

    async def _process_event(self, event: Event) -> None:
        if event.sequence is None:
            raise ValueError("memory projector requires a canonical event sequence")
        observed_head = await self.kernel.store.latest_sequence()
        pending = list(self.projection.apply(event, derived_source=self.source))
        writes = 0
        while pending:
            output = pending.pop(0)
            stored = await self.kernel.emit(output)
            writes += 1
            pending.extend(self.projection.apply(stored, derived_source=self.source))
        await self._advance_checkpoint(
            completed_sequence=event.sequence,
            observed_head_sequence=max(
                observed_head,
                await self.kernel.store.latest_sequence(),
                event.sequence,
            ),
            causation_id=event.id,
        )
        await self.telemetry.record(
            Metric(
                "memory.projector.derived_events_written",
                float(writes),
                {"consumer": self.consumer_id},
            )
        )

    async def _recover_projection(self) -> None:
        """Discard speculative state and return to the last durable checkpoint."""

        history = await self.kernel.history()
        self._restore_projection(history)
        self._processed_event_ids.clear()

    def _restore_projection(self, history: list[Event]) -> ConsumerCheckpoint | None:
        checkpoints = ConsumerCheckpointProjection()
        checkpoints.rebuild(history)
        checkpoint = checkpoints.get(self.consumer_id)
        through_sequence = checkpoint.event_sequence if checkpoint is not None else 0
        self.projection.rebuild(history, through_sequence=through_sequence)
        self._checkpoint = checkpoint
        return checkpoint

    async def _advance_checkpoint(
        self,
        *,
        completed_sequence: int,
        observed_head_sequence: int,
        causation_id: str,
    ) -> ConsumerCheckpoint:
        current = self._checkpoint
        if current is not None and completed_sequence < current.last_completed_sequence:
            raise ValueError("memory projector checkpoint cannot regress")
        if current is not None:
            observed_head_sequence = max(
                observed_head_sequence,
                current.observed_head_sequence,
            )
        candidate = ConsumerCheckpoint(
            consumer_id=self.consumer_id,
            last_completed_sequence=completed_sequence,
            observed_head_sequence=observed_head_sequence,
        )
        stored = await self.kernel.emit(
            candidate.to_event(
                source=self.source,
                timestamp=self.clock(),
                causation_id=causation_id,
            )
        )
        checkpoint = ConsumerCheckpoint.from_event(stored)
        self._checkpoint = checkpoint
        return checkpoint
