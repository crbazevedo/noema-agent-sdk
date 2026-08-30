"""Asynchronous event primitives.

The bus guarantees FIFO delivery per subscription. Different subscriptions run
independently, so a slow observer does not block every consumer. Events are
immutable and carry correlation/causation metadata for reconstructing agency.
"""

from __future__ import annotations

import asyncio
import fnmatch
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any
from uuid import uuid4

from .types import JSONObject, JSONValue, parse_datetime, utc_now

EventHandler = Callable[["Event"], Awaitable[None]]
EventErrorHandler = Callable[["Event", BaseException], Awaitable[None]]
EventValidator = Callable[["Event"], None]
EventUpcaster = Callable[["Event"], "Event"]

CURRENT_EVENT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class Event:
    """Immutable fact that occurred in or around an agent system."""

    type: str
    source: str
    payload: Mapping[str, JSONValue] = field(default_factory=dict)
    subject: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=utc_now)
    correlation_id: str | None = None
    causation_id: str | None = None
    priority: int = 0
    sequence: int | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)
    schema_version: int = CURRENT_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.type or not self.type.strip():
            raise ValueError("event type must be non-empty")
        if not self.source or not self.source.strip():
            raise ValueError("event source must be non-empty")
        if self.timestamp.tzinfo is None:
            raise ValueError("event timestamp must be timezone-aware")
        if self.schema_version <= 0:
            raise ValueError("event schema_version must be positive")
        object.__setattr__(self, "payload", dict(self.payload))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def with_sequence(self, sequence: int) -> Event:
        return replace(self, sequence=sequence)

    def caused_by(self, parent: Event, *, source: str | None = None) -> Event:
        """Return a copy linked to a parent event's causal chain."""

        return replace(
            self,
            source=source or self.source,
            correlation_id=parent.correlation_id or parent.id,
            causation_id=parent.id,
        )

    def to_dict(self) -> JSONObject:
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "subject": self.subject,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "priority": self.priority,
            "sequence": self.sequence,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Event:
        timestamp = parse_datetime(data.get("timestamp"))
        if timestamp is None:
            timestamp = utc_now()
        return cls(
            id=str(data.get("id") or uuid4()),
            type=str(data["type"]),
            source=str(data["source"]),
            subject=str(data["subject"]) if data.get("subject") is not None else None,
            timestamp=timestamp,
            correlation_id=(
                str(data["correlation_id"]) if data.get("correlation_id") is not None else None
            ),
            causation_id=(
                str(data["causation_id"]) if data.get("causation_id") is not None else None
            ),
            priority=int(data.get("priority", 0)),
            sequence=int(data["sequence"]) if data.get("sequence") is not None else None,
            payload=dict(data.get("payload", {})),
            metadata=dict(data.get("metadata", {})),
            schema_version=int(data.get("schema_version", CURRENT_EVENT_SCHEMA_VERSION)),
        )


class EventSchemaRegistry:
    """Validate and upcast typed event payloads without rewriting history.

    Stored events retain the schema version in which they were originally
    observed.  Upcasters create a projection-time representation, preserving
    the event id and causal metadata while keeping the append-only log intact.
    """

    def __init__(self) -> None:
        self._current: dict[str, int] = {}
        self._validators: dict[tuple[str, int], EventValidator] = {}
        self._upcasters: dict[tuple[str, int], EventUpcaster] = {}

    def register(
        self,
        event_type: str,
        version: int,
        *,
        validator: EventValidator | None = None,
        upcast_to_next: EventUpcaster | None = None,
    ) -> None:
        if not event_type:
            raise ValueError("event_type must be non-empty")
        if version <= 0:
            raise ValueError("schema version must be positive")
        key = (event_type, version)
        if key in self._validators or key in self._upcasters:
            raise ValueError(f"schema already registered: {event_type} v{version}")
        if validator is not None:
            self._validators[key] = validator
        if upcast_to_next is not None:
            self._upcasters[key] = upcast_to_next
        self._current[event_type] = max(version, self._current.get(event_type, 0))

    def current_version(self, event_type: str) -> int:
        return self._current.get(event_type, CURRENT_EVENT_SCHEMA_VERSION)

    def normalize(self, event: Event) -> Event:
        current = self.current_version(event.type)
        if event.schema_version > current:
            raise ValueError(
                f"unsupported future schema for {event.type}: v{event.schema_version} > v{current}"
            )
        normalized = event
        while normalized.schema_version < current:
            upcaster = self._upcasters.get((normalized.type, normalized.schema_version))
            if upcaster is None:
                raise ValueError(
                    f"missing upcaster for {normalized.type} v{normalized.schema_version}"
                )
            previous = normalized
            normalized = upcaster(normalized)
            expected = previous.schema_version + 1
            if normalized.schema_version != expected:
                raise ValueError(
                    f"upcaster for {previous.type} v{previous.schema_version} "
                    f"must produce v{expected}"
                )
            if normalized.id != previous.id or normalized.sequence != previous.sequence:
                raise ValueError("event upcasters must preserve id and sequence")
        validator = self._validators.get((normalized.type, normalized.schema_version))
        if validator is not None:
            validator(normalized)
        return normalized


@dataclass(slots=True)
class _Subscription:
    id: str
    pattern: str
    handler: EventHandler
    queue: asyncio.Queue[Event | None]
    task: asyncio.Task[None]


class AsyncEventBus:
    """In-process async event bus with wildcard topic subscriptions.

    Pattern matching uses :mod:`fnmatch`, so patterns such as ``external.*``
    and ``*`` are supported. Each subscriber gets an independent queue and
    worker task, preserving ordering per subscriber while enabling concurrency.
    """

    def __init__(
        self,
        *,
        queue_size: int = 0,
        error_handler: EventErrorHandler | None = None,
    ) -> None:
        self._queue_size = queue_size
        self._error_handler = error_handler
        self._subscriptions: dict[str, _Subscription] = {}
        self._started = False
        self._closed = False
        self._lock = asyncio.Lock()
        self._errors: list[tuple[Event, BaseException]] = []

    @property
    def started(self) -> bool:
        return self._started and not self._closed

    @property
    def subscriber_count(self) -> int:
        return len(self._subscriptions)

    @property
    def errors(self) -> tuple[tuple[Event, BaseException], ...]:
        return tuple(self._errors)

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("event bus has already been closed")
        self._started = True

    async def subscribe(self, pattern: str, handler: EventHandler) -> str:
        if not pattern:
            raise ValueError("subscription pattern must be non-empty")
        if not self._started:
            await self.start()

        subscription_id = str(uuid4())
        queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=self._queue_size)
        task = asyncio.create_task(
            self._worker(subscription_id, queue, handler),
            name=f"noema-event-subscription:{pattern}:{subscription_id}",
        )
        subscription = _Subscription(subscription_id, pattern, handler, queue, task)
        async with self._lock:
            self._subscriptions[subscription_id] = subscription
        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> None:
        async with self._lock:
            subscription = self._subscriptions.pop(subscription_id, None)
        if subscription is None:
            return
        await subscription.queue.put(None)
        await subscription.task

    async def publish(self, event: Event) -> None:
        if self._closed:
            raise RuntimeError("cannot publish to a closed event bus")
        if not self._started:
            await self.start()
        async with self._lock:
            subscriptions = tuple(self._subscriptions.values())
        matching = [
            subscription
            for subscription in subscriptions
            if fnmatch.fnmatchcase(event.type, subscription.pattern)
        ]
        for subscription in matching:
            await subscription.queue.put(event)

    async def drain(self) -> None:
        async with self._lock:
            subscriptions = tuple(self._subscriptions.values())
        await asyncio.gather(
            *(subscription.queue.join() for subscription in subscriptions),
            return_exceptions=False,
        )

    async def stop(self) -> None:
        if self._closed:
            return
        await self.drain()
        async with self._lock:
            subscriptions = tuple(self._subscriptions.values())
            self._subscriptions.clear()
        for subscription in subscriptions:
            await subscription.queue.put(None)
        await asyncio.gather(
            *(subscription.task for subscription in subscriptions),
            return_exceptions=True,
        )
        self._closed = True
        self._started = False

    async def _worker(
        self,
        subscription_id: str,
        queue: asyncio.Queue[Event | None],
        handler: EventHandler,
    ) -> None:
        del subscription_id  # reserved for richer diagnostics
        while True:
            event = await queue.get()
            try:
                if event is None:
                    return
                try:
                    await handler(event)
                except asyncio.CancelledError:
                    raise
                except BaseException as exc:  # isolate subscriber failures
                    self._errors.append((event, exc))
                    if self._error_handler is not None:
                        await self._error_handler(event, exc)
            finally:
                queue.task_done()
