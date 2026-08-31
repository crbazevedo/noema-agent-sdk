"""PostgreSQL event store with transactional outbox and durable inbox."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from ...delivery import InboxClaim, InboxDisposition, OutboxRecord
from ...events import Event
from ...store import ConcurrentAppendError
from ...types import utc_now


class PostgresEventStore:
    """Cloud-neutral PostgreSQL implementation of Noema durability contracts."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._lock = asyncio.Lock()
        self._closed = False

    @classmethod
    async def connect(cls, dsn: str, *, initialize: bool = True) -> PostgresEventStore:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "PostgreSQL support requires `pip install 'noema-agent-sdk[postgres]'`"
            ) from exc
        connection = await psycopg.AsyncConnection.connect(
            dsn,
            row_factory=dict_row,
            autocommit=True,
        )
        store = cls(connection)
        if initialize:
            await store.initialize()
        return store

    async def initialize(self) -> None:
        self._ensure_open()
        statements = (
            """
            CREATE TABLE IF NOT EXISTS noema_events (
                sequence BIGSERIAL PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                source TEXT NOT NULL,
                subject TEXT,
                timestamp TIMESTAMPTZ NOT NULL,
                correlation_id TEXT,
                causation_id TEXT,
                priority INTEGER NOT NULL,
                payload_json JSONB NOT NULL,
                metadata_json JSONB NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_noema_events_type_sequence
            ON noema_events(event_type, sequence)
            """,
            """
            CREATE TABLE IF NOT EXISTS noema_outbox (
                id BIGSERIAL PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE REFERENCES noema_events(event_id),
                topic TEXT NOT NULL,
                event_json JSONB NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                available_at TIMESTAMPTZ NOT NULL,
                lease_owner TEXT,
                lease_until TIMESTAMPTZ,
                fencing_token BIGINT NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                published_at TIMESTAMPTZ
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_noema_outbox_ready
            ON noema_outbox(published_at, available_at, lease_until)
            """,
            """
            CREATE TABLE IF NOT EXISTS noema_inbox (
                message_id TEXT NOT NULL,
                consumer_id TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                available_at TIMESTAMPTZ NOT NULL,
                lease_until TIMESTAMPTZ,
                fencing_token BIGINT NOT NULL DEFAULT 0,
                last_error TEXT,
                received_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                PRIMARY KEY (message_id, consumer_id)
            )
            """,
        )
        async with self._lock, self._connection.transaction():
            for statement in statements:
                await self._connection.execute(statement)

    async def append(self, event: Event) -> Event:
        return await self._append(
            event,
            outbox_topic=None,
            expected_head_sequence=None,
        )

    async def append_if_head(
        self,
        event: Event,
        *,
        expected_head_sequence: int,
    ) -> Event:
        if expected_head_sequence < 0:
            raise ValueError("expected event head sequence cannot be negative")
        return await self._append(
            event,
            outbox_topic=None,
            expected_head_sequence=expected_head_sequence,
        )

    async def append_with_outbox(self, event: Event, *, topic: str) -> Event:
        if not topic:
            raise ValueError("outbox topic must be non-empty")
        return await self._append(
            event,
            outbox_topic=topic,
            expected_head_sequence=None,
        )

    async def append_with_outbox_if_head(
        self,
        event: Event,
        *,
        topic: str,
        expected_head_sequence: int,
    ) -> Event:
        if not topic:
            raise ValueError("outbox topic must be non-empty")
        if expected_head_sequence < 0:
            raise ValueError("expected event head sequence cannot be negative")
        return await self._append(
            event,
            outbox_topic=topic,
            expected_head_sequence=expected_head_sequence,
        )

    async def _append(
        self,
        event: Event,
        *,
        outbox_topic: str | None,
        expected_head_sequence: int | None,
    ) -> Event:
        self._ensure_open()
        async with self._lock, self._connection.transaction():
            existing = None
            if expected_head_sequence is not None:
                # EXCLUSIVE conflicts with the ROW EXCLUSIVE lock taken by every
                # INSERT, so the head check and insert are atomic across writers.
                await self._connection.execute(
                    "LOCK TABLE noema_events IN EXCLUSIVE MODE"
                )
                cursor = await self._connection.execute(
                    "SELECT * FROM noema_events WHERE event_id = %s",
                    (event.id,),
                )
                existing = await cursor.fetchone()
                if existing is None:
                    cursor = await self._connection.execute(
                        "SELECT COALESCE(MAX(sequence), 0) AS latest FROM noema_events"
                    )
                    head = await cursor.fetchone()
                    actual_head_sequence = int(head["latest"])
                    if actual_head_sequence != expected_head_sequence:
                        raise ConcurrentAppendError(
                            expected_head_sequence=expected_head_sequence,
                            actual_head_sequence=actual_head_sequence,
                        )
            if existing is not None:
                stored = self._row_to_event(existing)
            else:
                cursor = await self._connection.execute(
                    """
                    INSERT INTO noema_events (
                        event_id, event_type, source, subject, timestamp,
                        correlation_id, causation_id, priority, payload_json,
                        metadata_json, schema_version
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s
                    )
                    ON CONFLICT(event_id) DO NOTHING
                    RETURNING sequence
                    """,
                    (
                        event.id,
                        event.type,
                        event.source,
                        event.subject,
                        event.timestamp,
                        event.correlation_id,
                        event.causation_id,
                        event.priority,
                        json.dumps(
                            dict(event.payload), separators=(",", ":"), sort_keys=True
                        ),
                        json.dumps(
                            dict(event.metadata), separators=(",", ":"), sort_keys=True
                        ),
                        event.schema_version,
                    ),
                )
                inserted = await cursor.fetchone()
                if inserted is None:
                    cursor = await self._connection.execute(
                        "SELECT * FROM noema_events WHERE event_id = %s",
                        (event.id,),
                    )
                    row = await cursor.fetchone()
                    if row is None:
                        raise RuntimeError(
                            "event insert conflicted without an existing event"
                        )
                    stored = self._row_to_event(row)
                else:
                    stored = event.with_sequence(int(inserted["sequence"]))
            if stored.sequence is None:
                raise RuntimeError("stored event is missing a canonical sequence")
            if outbox_topic is not None:
                now = utc_now()
                await self._connection.execute(
                    """
                    INSERT INTO noema_outbox (
                        event_id, topic, event_json, available_at, created_at
                    ) VALUES (%s, %s, %s::jsonb, %s, %s)
                    ON CONFLICT(event_id) DO NOTHING
                    """,
                    (
                        stored.id,
                        outbox_topic,
                        json.dumps(stored.to_dict(), separators=(",", ":"), sort_keys=True),
                        now,
                        now,
                    ),
                )
            return stored

    async def read(
        self,
        *,
        after_sequence: int = 0,
        limit: int | None = None,
        types: Sequence[str] | None = None,
    ) -> list[Event]:
        self._ensure_open()
        clauses = ["sequence > %s"]
        parameters: list[object] = [after_sequence]
        if types:
            clauses.append("event_type = ANY(%s)")
            parameters.append(list(types))
        query = "SELECT * FROM noema_events WHERE " + " AND ".join(clauses)
        query += " ORDER BY sequence ASC"
        if limit is not None:
            query += " LIMIT %s"
            parameters.append(limit)
        async with self._lock:
            cursor = await self._connection.execute(query, parameters)
            rows = await cursor.fetchall()
        return [self._row_to_event(row) for row in rows]

    async def latest_sequence(self) -> int:
        self._ensure_open()
        async with self._lock:
            cursor = await self._connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS latest FROM noema_events"
            )
            row = await cursor.fetchone()
        return int(row["latest"])

    async def claim_outbox(
        self,
        worker_id: str,
        *,
        limit: int,
        lease_seconds: float,
    ) -> list[OutboxRecord]:
        self._ensure_open()
        now = utc_now()
        lease_until = now + timedelta(seconds=lease_seconds)
        async with self._lock, self._connection.transaction():
            cursor = await self._connection.execute(
                """
                SELECT * FROM noema_outbox
                WHERE published_at IS NULL
                  AND available_at <= %s
                  AND (lease_until IS NULL OR lease_until <= %s)
                ORDER BY id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (now, now, limit),
            )
            rows = await cursor.fetchall()
            records: list[OutboxRecord] = []
            for row in rows:
                fencing_token = int(row["fencing_token"]) + 1
                attempts = int(row["attempts"]) + 1
                await self._connection.execute(
                    """
                    UPDATE noema_outbox
                    SET lease_owner = %s, lease_until = %s,
                        fencing_token = %s, attempts = %s
                    WHERE id = %s AND published_at IS NULL
                    """,
                    (worker_id, lease_until, fencing_token, attempts, row["id"]),
                )
                event_data = row["event_json"]
                if isinstance(event_data, str):
                    event_data = json.loads(event_data)
                records.append(
                    OutboxRecord(
                        id=str(row["id"]),
                        event=Event.from_dict(event_data),
                        topic=str(row["topic"]),
                        attempts=attempts,
                        fencing_token=fencing_token,
                    )
                )
            return records

    async def complete_outbox(self, record_id: str, fencing_token: int) -> bool:
        self._ensure_open()
        async with self._lock, self._connection.transaction():
            cursor = await self._connection.execute(
                """
                UPDATE noema_outbox
                SET published_at = %s, lease_owner = NULL, lease_until = NULL
                WHERE id = %s AND fencing_token = %s AND published_at IS NULL
                """,
                (utc_now(), int(record_id), fencing_token),
            )
            return bool(cursor.rowcount == 1)

    async def retry_outbox(
        self,
        record_id: str,
        fencing_token: int,
        *,
        error: str,
        available_at: datetime,
    ) -> bool:
        self._ensure_open()
        async with self._lock, self._connection.transaction():
            cursor = await self._connection.execute(
                """
                UPDATE noema_outbox
                SET available_at = %s, last_error = %s,
                    lease_owner = NULL, lease_until = NULL
                WHERE id = %s AND fencing_token = %s AND published_at IS NULL
                """,
                (available_at, error, int(record_id), fencing_token),
            )
            return bool(cursor.rowcount == 1)

    async def claim_inbox(
        self,
        message_id: str,
        consumer_id: str,
        *,
        lease_seconds: float,
    ) -> InboxClaim:
        self._ensure_open()
        now = utc_now()
        lease_until = now + timedelta(seconds=lease_seconds)
        async with self._lock, self._connection.transaction():
            # Materialize the coordination row before locking it. Two workers
            # may observe the same new broker message concurrently; ON CONFLICT
            # turns that race into a normal lease contest instead of a unique
            # constraint failure.
            await self._connection.execute(
                """
                INSERT INTO noema_inbox (
                    message_id, consumer_id, status, attempts, available_at,
                    lease_until, fencing_token, received_at
                ) VALUES (%s, %s, 'pending', 0, %s, NULL, 0, %s)
                ON CONFLICT(message_id, consumer_id) DO NOTHING
                """,
                (message_id, consumer_id, now, now),
            )
            cursor = await self._connection.execute(
                """
                SELECT * FROM noema_inbox
                WHERE message_id = %s AND consumer_id = %s
                FOR UPDATE
                """,
                (message_id, consumer_id),
            )
            row = await cursor.fetchone()
            if row is None:
                raise RuntimeError("inbox row disappeared during claim")
            if row["status"] == "completed":
                return InboxClaim(InboxDisposition.COMPLETED)
            if row["available_at"] > now or (
                row["lease_until"] is not None and row["lease_until"] > now
            ):
                return InboxClaim(InboxDisposition.BUSY)
            fencing_token = int(row["fencing_token"]) + 1
            await self._connection.execute(
                """
                UPDATE noema_inbox
                SET status = 'processing', attempts = attempts + 1,
                    lease_until = %s, fencing_token = %s
                WHERE message_id = %s AND consumer_id = %s
                """,
                (lease_until, fencing_token, message_id, consumer_id),
            )
            return InboxClaim(InboxDisposition.ACQUIRED, fencing_token)

    async def complete_inbox(
        self,
        message_id: str,
        consumer_id: str,
        fencing_token: int,
    ) -> bool:
        self._ensure_open()
        async with self._lock, self._connection.transaction():
            cursor = await self._connection.execute(
                """
                UPDATE noema_inbox
                SET status = 'completed', completed_at = %s, lease_until = NULL
                WHERE message_id = %s AND consumer_id = %s
                  AND fencing_token = %s AND status = 'processing'
                """,
                (utc_now(), message_id, consumer_id, fencing_token),
            )
            return bool(cursor.rowcount == 1)

    async def retry_inbox(
        self,
        message_id: str,
        consumer_id: str,
        fencing_token: int,
        *,
        error: str,
        available_at: datetime,
    ) -> bool:
        self._ensure_open()
        async with self._lock, self._connection.transaction():
            cursor = await self._connection.execute(
                """
                UPDATE noema_inbox
                SET status = 'pending', available_at = %s,
                    last_error = %s, lease_until = NULL
                WHERE message_id = %s AND consumer_id = %s
                  AND fencing_token = %s AND status = 'processing'
                """,
                (available_at, error, message_id, consumer_id, fencing_token),
            )
            return bool(cursor.rowcount == 1)

    async def close(self) -> None:
        if self._closed:
            return
        async with self._lock:
            await self._connection.close()
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("event store is closed")

    @staticmethod
    def _row_to_event(row: Mapping[str, Any]) -> Event:
        payload = row["payload_json"]
        metadata = row["metadata_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return Event.from_dict(
            {
                "id": row["event_id"],
                "type": row["event_type"],
                "source": row["source"],
                "subject": row["subject"],
                "timestamp": row["timestamp"],
                "correlation_id": row["correlation_id"],
                "causation_id": row["causation_id"],
                "priority": row["priority"],
                "sequence": row["sequence"],
                "payload": payload,
                "metadata": metadata,
                "schema_version": row["schema_version"],
            }
        )
