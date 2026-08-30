"""NATS JetStream adapter for Noema's portable broker protocol."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from ...delivery import BrokerMessage, BrokerSubscription


class _NATSMessage:
    def __init__(self, message: Any) -> None:
        self._message = message
        headers = message.headers or {}
        self.id = str(headers.get("Noema-Event-Id") or _event_id(message.data))
        self.subject = str(message.subject)
        self.payload = bytes(message.data)
        metadata = getattr(message, "metadata", None)
        self.attempts = int(getattr(metadata, "num_delivered", 1))

    async def ack(self) -> None:
        await self._message.ack()

    async def nak(self, *, delay_seconds: float = 0.0) -> None:
        if delay_seconds > 0:
            await self._message.nak(delay=delay_seconds)
        else:
            await self._message.nak()


class _NATSSubscription:
    def __init__(self, subscription: Any) -> None:
        self._subscription = subscription
        self._closed = False

    async def get(self, *, timeout: float | None = None) -> BrokerMessage | None:
        if self._closed:
            return None
        try:
            messages = await self._subscription.fetch(1, timeout=timeout or 1.0)
        except BaseException as exc:
            if exc.__class__.__name__ in {"TimeoutError", "FetchTimeoutError"}:
                return None
            raise
        if not messages:
            return None
        return _NATSMessage(messages[0])

    async def close(self) -> None:
        # Keep the durable JetStream consumer so it can resume after restart.
        self._closed = True


class NATSBroker:
    """JetStream transport; the EventStore remains the canonical history."""

    def __init__(self, connection: Any, jetstream: Any, *, stream_name: str) -> None:
        self._connection = connection
        self._jetstream = jetstream
        self.stream_name = stream_name
        self._closed = False

    @classmethod
    async def connect(
        cls,
        servers: Sequence[str] = ("nats://127.0.0.1:4222",),
        *,
        stream_name: str = "NOEMA",
        subjects: Sequence[str] = ("noema.>",),
        connect_timeout: float = 5.0,
    ) -> NATSBroker:
        try:
            import nats
            from nats.js.errors import NotFoundError
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "NATS support requires `pip install 'noema-agent-sdk[nats]'`"
            ) from exc
        connection = await nats.connect(
            servers=list(servers),
            connect_timeout=connect_timeout,
            allow_reconnect=True,
            max_reconnect_attempts=-1,
        )
        jetstream = connection.jetstream()
        try:
            await jetstream.stream_info(stream_name)
        except NotFoundError:
            await jetstream.add_stream(
                name=stream_name,
                subjects=list(subjects),
                storage="file",
            )
        except BaseException:
            await connection.close()
            raise
        return cls(connection, jetstream, stream_name=stream_name)

    async def publish(self, subject: str, payload: bytes, *, message_id: str) -> None:
        if self._closed:
            raise RuntimeError("broker is closed")
        await self._jetstream.publish(
            subject,
            payload,
            headers={
                "Nats-Msg-Id": message_id,
                "Noema-Event-Id": message_id,
            },
        )

    async def subscribe(self, subject: str, *, durable: str) -> BrokerSubscription:
        if self._closed:
            raise RuntimeError("broker is closed")
        subscription = await self._jetstream.pull_subscribe(
            subject,
            durable=durable,
            stream=self.stream_name,
        )
        return _NATSSubscription(subscription)

    async def close(self) -> None:
        if self._closed:
            return
        await self._connection.drain()
        self._closed = True


def _event_id(payload: bytes) -> str:
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("NATS message does not contain a valid Noema event") from exc
    if not isinstance(data, dict) or not data.get("id"):
        raise ValueError("NATS message does not contain an event id")
    return str(data["id"])
