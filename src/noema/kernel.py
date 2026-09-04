"""Event-sourced kernel shared by autonomous agents."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import cast

from .delivery import TransactionalDeliveryStore, event_topic
from .events import AsyncEventBus, Event, EventSchemaRegistry
from .situation import SituationModel, SituationSnapshot
from .store import EventStore, InMemoryEventStore
from .tracing import NullTracer, Tracer


class NoemaKernel:
    """Persist, project, and publish every event in causal order."""

    def __init__(
        self,
        *,
        store: EventStore | None = None,
        bus: AsyncEventBus | None = None,
        situation: SituationModel | None = None,
        schemas: EventSchemaRegistry | None = None,
        tracer: Tracer | None = None,
        distributed: bool = False,
        topic_prefix: str = "noema",
    ) -> None:
        self.store = store or InMemoryEventStore()
        self.bus = bus or AsyncEventBus()
        self.situation = situation or SituationModel()
        if schemas is None:
            schemas = EventSchemaRegistry()
            # Imported lazily to keep the event primitive independent while
            # making legacy strategic migration the default runtime behavior.
            from .deliberative_attention.schemas import (
                register_deliberative_attention_event_schemas,
            )
            from .information.schemas import register_information_event_schemas
            from .intent.schemas import register_intent_event_schemas

            register_intent_event_schemas(schemas)
            register_information_event_schemas(schemas)
            register_deliberative_attention_event_schemas(schemas)
        self.schemas = schemas
        self.tracer = tracer or NullTracer()
        self.distributed = distributed
        self.topic_prefix = topic_prefix
        if distributed and not callable(getattr(self.store, "append_with_outbox", None)):
            raise TypeError("distributed kernels require a transactional delivery store")
        self._emit_lock = asyncio.Lock()
        self._startup_sequence = 0
        self._pending_broker_echoes: set[str] = set()
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
            await self._rebuild_situation()
        self._startup_sequence = await self.store.latest_sequence()
        await self.bus.start()
        self._started = True

    async def emit(self, event: Event) -> Event:
        return await self._commit(
            event,
            distribute=True,
            expected_head_sequence=None,
        )

    async def emit_if_head(
        self,
        event: Event,
        *,
        expected_head_sequence: int,
    ) -> Event:
        """Commit only if no other canonical event followed the observed head."""

        return await self._commit(
            event,
            distribute=True,
            expected_head_sequence=expected_head_sequence,
        )

    async def ingest(self, event: Event) -> Event:
        """Commit a broker-delivered event without creating another outbox row."""

        return await self._commit(
            event,
            distribute=False,
            expected_head_sequence=None,
        )

    async def _commit(
        self,
        event: Event,
        *,
        distribute: bool,
        expected_head_sequence: int | None,
    ) -> Event:
        if not self._started:
            await self.start()
        attributes = {
            "noema.event_id": event.id,
            "noema.event_type": event.type,
            "noema.event_source": event.source,
        }
        if event.correlation_id is not None:
            attributes["noema.correlation_id"] = event.correlation_id
        async with self.tracer.span("noema.event.commit", attributes):
            async with self._emit_lock:
                if self.distributed and distribute:
                    delivery_store = cast(TransactionalDeliveryStore, self.store)
                    topic = event_topic(event, prefix=self.topic_prefix)
                    if expected_head_sequence is None:
                        stored = await delivery_store.append_with_outbox(
                            event,
                            topic=topic,
                        )
                    else:
                        stored = await delivery_store.append_with_outbox_if_head(
                            event,
                            topic=topic,
                            expected_head_sequence=expected_head_sequence,
                        )
                else:
                    if expected_head_sequence is None:
                        stored = await self.store.append(event)
                    else:
                        stored = await self.store.append_if_head(
                            event,
                            expected_head_sequence=expected_head_sequence,
                        )
                if stored.sequence is not None and stored.sequence <= self.situation.version:
                    if distribute:
                        # Idempotent local re-emission of canonical history.
                        return stored
                    if stored.id in self._pending_broker_echoes:
                        # The broker echoed an event already projected by this runtime.
                        self._pending_broker_echoes.discard(stored.id)
                        return stored
                    if stored.sequence <= self._startup_sequence:
                        # A new durable consumer may receive history already rebuilt at start.
                        return stored
                    # Concurrent outbox publishers may deliver database sequences out of
                    # order. Rebuild the projection from canonical order before notifying
                    # local subscribers about this late arrival.
                    await self._rebuild_situation()
                    projected = self.schemas.normalize(stored)
                    await self.bus.publish(projected)
                    return stored
                projected = self.schemas.normalize(stored)
                await self.situation.apply(projected)
                await self.bus.publish(projected)
                if distribute:
                    self._pending_broker_echoes.add(stored.id)
                return stored

    async def _rebuild_situation(self) -> None:
        events = await self.store.read()
        await self.situation.rebuild(self.schemas.normalize(event) for event in events)

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

    async def __aenter__(self) -> NoemaKernel:
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.stop()
