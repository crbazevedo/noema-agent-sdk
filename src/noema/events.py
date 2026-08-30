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

    def __post_init__(self) -> None:
        if not self.type or not self.type.strip():
            raise ValueError("event type must be non-empty")
        if not self.source or not self.source.strip():
            raise ValueError("event source must be non-empty")
        if self.timestamp.tzinfo is None:
            raise ValueError("event timestamp must be timezone-aware")
        object.__setattr__(self, "payload", dict(self.payload))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def with_sequence(self, sequence: int) -> "Event":
        return replace(self, sequence=sequence)

    def caused_by(self, parent: "Event", *, source: str | None = None) -> "Event":
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
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Event":
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
                str(data["correlation_id"])
                if data.get("correlation_id") is not None
                else None
            ),
            causation_id=(
                str(data["causation_id"])
                if data.get("causation_id") is not None
                else None
            ),
            priority=int(data.get("priority", 0)),
            sequence=int(data["sequence"]) if data.get("sequence") is not None else None,
            payload=dict(data.get("payload", {})),
            metadata=dict(data.get("metadata", {})),
        )


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
