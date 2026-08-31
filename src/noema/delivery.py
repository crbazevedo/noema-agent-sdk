"""At-least-once event delivery with transactional outbox/inbox semantics."""

from __future__ import annotations

import asyncio
import fnmatch
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from .events import Event
from .types import utc_now


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    id: str
    event: Event
    topic: str
    attempts: int
    fencing_token: int


class InboxDisposition(StrEnum):
    ACQUIRED = "acquired"
    COMPLETED = "completed"
    BUSY = "busy"


@dataclass(frozen=True, slots=True)
class InboxClaim:
    disposition: InboxDisposition
    fencing_token: int | None = None


class TransactionalDeliveryStore(Protocol):
    async def append_with_outbox(self, event: Event, *, topic: str) -> Event: ...

    async def append_with_outbox_if_head(
        self,
        event: Event,
        *,
        topic: str,
        expected_head_sequence: int,
    ) -> Event: ...

    async def claim_outbox(
        self,
        worker_id: str,
        *,
        limit: int,
        lease_seconds: float,
    ) -> list[OutboxRecord]: ...

    async def complete_outbox(self, record_id: str, fencing_token: int) -> bool: ...

    async def retry_outbox(
        self,
        record_id: str,
        fencing_token: int,
        *,
        error: str,
        available_at: datetime,
    ) -> bool: ...

    async def claim_inbox(
        self,
        message_id: str,
        consumer_id: str,
        *,
        lease_seconds: float,
    ) -> InboxClaim: ...

    async def complete_inbox(
        self,
        message_id: str,
        consumer_id: str,
        fencing_token: int,
    ) -> bool: ...

    async def retry_inbox(
        self,
        message_id: str,
        consumer_id: str,
        fencing_token: int,
        *,
        error: str,
        available_at: datetime,
    ) -> bool: ...


class BrokerMessage(Protocol):
    id: str
    subject: str
    payload: bytes
    attempts: int

    async def ack(self) -> None: ...

    async def nak(self, *, delay_seconds: float = 0.0) -> None: ...


class BrokerSubscription(Protocol):
    async def get(self, *, timeout: float | None = None) -> BrokerMessage | None: ...

    async def close(self) -> None: ...


class EventBroker(Protocol):
    async def publish(self, subject: str, payload: bytes, *, message_id: str) -> None: ...

    async def subscribe(self, subject: str, *, durable: str) -> BrokerSubscription: ...

    async def close(self) -> None: ...


@dataclass(slots=True)
class _MemoryMessage:
    id: str
    subject: str
    payload: bytes
    queue: asyncio.Queue[_MemoryMessage | None]
    attempts: int = 1
    acknowledged: bool = False

    async def ack(self) -> None:
        self.acknowledged = True

    async def nak(self, *, delay_seconds: float = 0.0) -> None:
        self.attempts += 1
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        await self.queue.put(self)


class _MemorySubscription:
    def __init__(self, queue: asyncio.Queue[_MemoryMessage | None]) -> None:
        self._queue = queue
        self._closed = False

    async def get(self, *, timeout: float | None = None) -> BrokerMessage | None:
        if self._closed:
            return None
        try:
            if timeout is None:
                message = await self._queue.get()
            else:
                async with asyncio.timeout(timeout):
                    message = await self._queue.get()
        except TimeoutError:
            return None
        if message is None:
            return None
        return message

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._queue.put(None)


class InMemoryBroker:
    """Deterministic broker fake with publish-failure injection."""

    def __init__(self, *, fail_publishes: int = 0, queue_size: int = 1000) -> None:
        self.fail_publishes = fail_publishes
        self.queue_size = queue_size
        self.published: list[tuple[str, str]] = []
        self._subscriptions: dict[tuple[str, str], asyncio.Queue[_MemoryMessage | None]] = {}
        self._closed = False

    async def publish(self, subject: str, payload: bytes, *, message_id: str) -> None:
        if self._closed:
            raise RuntimeError("broker is closed")
        if self.fail_publishes > 0:
            self.fail_publishes -= 1
            raise ConnectionError("injected broker publish failure")
        self.published.append((subject, message_id))
        for (pattern, _), queue in tuple(self._subscriptions.items()):
            if _subject_matches(subject, pattern):
                await queue.put(_MemoryMessage(message_id, subject, payload, queue))

    async def subscribe(self, subject: str, *, durable: str) -> BrokerSubscription:
        if self._closed:
            raise RuntimeError("broker is closed")
        key = (subject, durable)
        if key in self._subscriptions:
            raise ValueError(f"durable subscription already active: {durable}")
        queue: asyncio.Queue[_MemoryMessage | None] = asyncio.Queue(self.queue_size)
        self._subscriptions[key] = queue
        return _MemorySubscription(queue)

    async def close(self) -> None:
        if self._closed:
            return
        for queue in self._subscriptions.values():
            await queue.put(None)
        self._subscriptions.clear()
        self._closed = True


class OutboxPublisher:
    """Publish committed events and acknowledge outbox rows after broker ack."""

    def __init__(
        self,
        store: TransactionalDeliveryStore,
        broker: EventBroker,
        *,
        worker_id: str | None = None,
        batch_size: int = 100,
        lease_seconds: float = 30.0,
        poll_seconds: float = 0.1,
        max_backoff_seconds: float = 30.0,
    ) -> None:
        if batch_size <= 0 or lease_seconds <= 0 or poll_seconds <= 0:
            raise ValueError("outbox publisher limits must be positive")
        self.store = store
        self.broker = broker
        self.worker_id = worker_id or f"outbox-{uuid4()}"
        self.batch_size = batch_size
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name=f"noema:{self.worker_id}")

    async def run_once(self) -> int:
        records = await self.store.claim_outbox(
            self.worker_id,
            limit=self.batch_size,
            lease_seconds=self.lease_seconds,
        )
        completed = 0
        for record in records:
            try:
                await self.broker.publish(
                    record.topic,
                    json.dumps(
                        record.event.to_dict(),
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8"),
                    message_id=record.event.id,
                )
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                delay = min(
                    self.max_backoff_seconds,
                    self.poll_seconds * (2 ** min(record.attempts, 12)),
                )
                await self.store.retry_outbox(
                    record.id,
                    record.fencing_token,
                    error=repr(exc),
                    available_at=utc_now() + timedelta(seconds=delay),
                )
            else:
                if await self.store.complete_outbox(record.id, record.fencing_token):
                    completed += 1
        return completed

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            completed = await self.run_once()
            if completed == 0:
                try:
                    async with asyncio.timeout(self.poll_seconds):
                        await self._stop.wait()
                except TimeoutError:
                    pass


EventDeliveryHandler = Callable[[Event], Awaitable[None]]


class InboxConsumer:
    """Deduplicate broker messages before passing events to a local runtime."""

    def __init__(
        self,
        store: TransactionalDeliveryStore,
        broker: EventBroker,
        handler: EventDeliveryHandler,
        *,
        subject: str = "noema.>",
        consumer_id: str,
        lease_seconds: float = 30.0,
        retry_seconds: float = 0.25,
        fetch_timeout_seconds: float = 0.25,
    ) -> None:
        if not consumer_id:
            raise ValueError("consumer_id must be non-empty")
        self.store = store
        self.broker = broker
        self.handler = handler
        self.subject = subject
        self.consumer_id = consumer_id
        self.lease_seconds = lease_seconds
        self.retry_seconds = retry_seconds
        self.fetch_timeout_seconds = fetch_timeout_seconds
        self._subscription: BrokerSubscription | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._subscription = await self.broker.subscribe(
            self.subject,
            durable=self.consumer_id,
        )
        self._stop.clear()
        self._task = asyncio.create_task(
            self._run(),
            name=f"noema:inbox:{self.consumer_id}",
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        if self._subscription is not None:
            await self._subscription.close()
            self._subscription = None

    async def process_once(self, *, timeout: float | None = None) -> bool:
        if self._subscription is None:
            raise RuntimeError("inbox consumer is not started")
        message = await self._subscription.get(timeout=timeout)
        if message is None:
            return False
        claim = await self.store.claim_inbox(
            message.id,
            self.consumer_id,
            lease_seconds=self.lease_seconds,
        )
        if claim.disposition == InboxDisposition.COMPLETED:
            await message.ack()
            return True
        if claim.disposition == InboxDisposition.BUSY:
            await message.nak(delay_seconds=self.retry_seconds)
            return False
        assert claim.fencing_token is not None
        try:
            payload = json.loads(message.payload)
            if not isinstance(payload, Mapping):
                raise ValueError("broker event payload must be a JSON object")
            await self.handler(Event.from_dict(payload))
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            await self.store.retry_inbox(
                message.id,
                self.consumer_id,
                claim.fencing_token,
                error=repr(exc),
                available_at=utc_now() + timedelta(seconds=self.retry_seconds),
            )
            await message.nak(delay_seconds=self.retry_seconds)
            return False
        completed = await self.store.complete_inbox(
            message.id,
            self.consumer_id,
            claim.fencing_token,
        )
        if completed:
            await message.ack()
        else:
            await message.nak(delay_seconds=self.retry_seconds)
        return completed

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self.process_once(timeout=self.fetch_timeout_seconds)


def event_topic(event: Event, *, prefix: str = "noema") -> str:
    return f"{prefix}.{event.type}"


def _subject_matches(subject: str, pattern: str) -> bool:
    translated = pattern.replace(">", "*")
    return fnmatch.fnmatchcase(subject, translated)
