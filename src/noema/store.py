"""Durable event stores.

The SDK is event-sourced. Situation state can always be reconstructed from the
append-only event log. The SQLite implementation uses only the Python standard
library and moves blocking database work off the event loop.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from .delivery import InboxClaim, InboxDisposition, OutboxRecord
from .events import Event
from .types import utc_now


class ConcurrentAppendError(RuntimeError):
    """The canonical event head changed before a conditional append."""

    def __init__(self, *, expected_head_sequence: int, actual_head_sequence: int) -> None:
        self.expected_head_sequence = expected_head_sequence
        self.actual_head_sequence = actual_head_sequence
        super().__init__(
            "canonical event head changed: "
            f"expected {expected_head_sequence}, found {actual_head_sequence}"
        )


class EventStore(Protocol):
    async def append(self, event: Event) -> Event: ...

    async def append_if_head(
        self,
        event: Event,
        *,
        expected_head_sequence: int,
    ) -> Event: ...

    async def read(
        self,
        *,
        after_sequence: int = 0,
        limit: int | None = None,
        types: Sequence[str] | None = None,
    ) -> list[Event]: ...

    async def latest_sequence(self) -> int: ...

    async def close(self) -> None: ...


class InMemoryEventStore:
    def __init__(self) -> None:
        self._events: list[Event] = []
        self._by_id: dict[str, Event] = {}
        self._lock = asyncio.Lock()

    async def append(self, event: Event) -> Event:
        async with self._lock:
            return self._append_locked(event)

    async def append_if_head(
        self,
        event: Event,
        *,
        expected_head_sequence: int,
    ) -> Event:
        if expected_head_sequence < 0:
            raise ValueError("expected event head sequence cannot be negative")
        async with self._lock:
            existing = self._by_id.get(event.id)
            if existing is not None:
                return existing
            actual_head_sequence = len(self._events)
            if actual_head_sequence != expected_head_sequence:
                raise ConcurrentAppendError(
                    expected_head_sequence=expected_head_sequence,
                    actual_head_sequence=actual_head_sequence,
                )
            return self._append_locked(event)

    def _append_locked(self, event: Event) -> Event:
        existing = self._by_id.get(event.id)
        if existing is not None:
            return existing
        stored = event.with_sequence(len(self._events) + 1)
        self._events.append(stored)
        self._by_id[event.id] = stored
        return stored

    async def read(
        self,
        *,
        after_sequence: int = 0,
        limit: int | None = None,
        types: Sequence[str] | None = None,
    ) -> list[Event]:
        async with self._lock:
            events = [
                event
                for event in self._events
                if (event.sequence or 0) > after_sequence and (types is None or event.type in types)
            ]
        return events if limit is None else events[:limit]

    async def latest_sequence(self) -> int:
        async with self._lock:
            return len(self._events)

    async def close(self) -> None:
        return None


class SQLiteEventStore:
    """SQLite-backed append-only event store.

    A single connection is guarded by an asyncio lock. Database operations run
    through ``asyncio.to_thread`` so the event loop remains responsive.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._closed = False
        self._initialize()

    def _initialize(self) -> None:
        connection = self._connection
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                source TEXT NOT NULL,
                subject TEXT,
                timestamp TEXT NOT NULL,
                correlation_id TEXT,
                causation_id TEXT,
                priority INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(events)").fetchall()
        }
        if "schema_version" not in columns:
            connection.execute(
                "ALTER TABLE events ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_type_sequence ON events(event_type, sequence)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE REFERENCES events(event_id),
                topic TEXT NOT NULL,
                event_json TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                available_at TEXT NOT NULL,
                lease_owner TEXT,
                lease_until TEXT,
                fencing_token INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                published_at TEXT
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_outbox_ready "
            "ON outbox(published_at, available_at, lease_until)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS inbox (
                message_id TEXT NOT NULL,
                consumer_id TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                available_at TEXT NOT NULL,
                lease_until TEXT,
                fencing_token INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                received_at TEXT NOT NULL,
                completed_at TEXT,
                PRIMARY KEY (message_id, consumer_id)
            )
            """
        )
        connection.commit()

    async def append(self, event: Event) -> Event:
        self._ensure_open()
        async with self._lock:
            return await asyncio.to_thread(self._append_sync, event, None, None)

    async def append_if_head(
        self,
        event: Event,
        *,
        expected_head_sequence: int,
    ) -> Event:
        self._ensure_open()
        if expected_head_sequence < 0:
            raise ValueError("expected event head sequence cannot be negative")
        async with self._lock:
            return await asyncio.to_thread(
                self._append_sync,
                event,
                None,
                expected_head_sequence,
            )

    async def append_with_outbox(self, event: Event, *, topic: str) -> Event:
        """Atomically append the canonical event and its transport projection."""

        self._ensure_open()
        if not topic:
            raise ValueError("outbox topic must be non-empty")
        async with self._lock:
            return await asyncio.to_thread(self._append_sync, event, topic, None)

    async def append_with_outbox_if_head(
        self,
        event: Event,
        *,
        topic: str,
        expected_head_sequence: int,
    ) -> Event:
        """Atomically append event/outbox rows only at the expected event head."""

        self._ensure_open()
        if not topic:
            raise ValueError("outbox topic must be non-empty")
        if expected_head_sequence < 0:
            raise ValueError("expected event head sequence cannot be negative")
        async with self._lock:
            return await asyncio.to_thread(
                self._append_sync,
                event,
                topic,
                expected_head_sequence,
            )

    def _append_sync(
        self,
        event: Event,
        outbox_topic: str | None,
        expected_head_sequence: int | None,
    ) -> Event:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self._connection.execute(
                "SELECT * FROM events WHERE event_id = ?", (event.id,)
            ).fetchone()
            if existing is not None:
                stored = self._row_to_event(existing)
            else:
                if expected_head_sequence is not None:
                    actual_head_sequence = self._latest_sequence_sync()
                    if actual_head_sequence != expected_head_sequence:
                        raise ConcurrentAppendError(
                            expected_head_sequence=expected_head_sequence,
                            actual_head_sequence=actual_head_sequence,
                        )
                cursor = self._connection.execute(
                    """
                    INSERT INTO events (
                        event_id, event_type, source, subject, timestamp,
                        correlation_id, causation_id, priority,
                        payload_json, metadata_json, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(event_id) DO NOTHING
                    """,
                    (
                        event.id,
                        event.type,
                        event.source,
                        event.subject,
                        event.timestamp.isoformat(),
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
                if not cursor.rowcount or cursor.lastrowid is None:
                    raise RuntimeError("conditional SQLite event insert did not win")
                stored = event.with_sequence(int(cursor.lastrowid))
            if outbox_topic is not None:
                now = utc_now().isoformat()
                self._connection.execute(
                    """
                    INSERT INTO outbox (
                        event_id, topic, event_json, available_at, created_at
                    ) VALUES (?, ?, ?, ?, ?)
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
            self._connection.commit()
            return stored
        except BaseException:
            self._connection.rollback()
            raise

    async def read(
        self,
        *,
        after_sequence: int = 0,
        limit: int | None = None,
        types: Sequence[str] | None = None,
    ) -> list[Event]:
        self._ensure_open()
        async with self._lock:
            return await asyncio.to_thread(
                self._read_sync,
                after_sequence,
                limit,
                tuple(types) if types is not None else None,
            )

    def _read_sync(
        self,
        after_sequence: int,
        limit: int | None,
        types: tuple[str, ...] | None,
    ) -> list[Event]:
        clauses = ["sequence > ?"]
        parameters: list[object] = [after_sequence]
        if types:
            placeholders = ",".join("?" for _ in types)
            clauses.append(f"event_type IN ({placeholders})")
            parameters.extend(types)
        query = "SELECT * FROM events WHERE " + " AND ".join(clauses)
        query += " ORDER BY sequence ASC"
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)
        rows = self._connection.execute(query, parameters).fetchall()
        return [self._row_to_event(row) for row in rows]

    async def latest_sequence(self) -> int:
        self._ensure_open()
        async with self._lock:
            return await asyncio.to_thread(self._latest_sequence_sync)

    def _latest_sequence_sync(self) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS latest FROM events"
        ).fetchone()
        return int(row["latest"])

    async def claim_outbox(
        self,
        worker_id: str,
        *,
        limit: int,
        lease_seconds: float,
    ) -> list[OutboxRecord]:
        self._ensure_open()
        async with self._lock:
            return await asyncio.to_thread(
                self._claim_outbox_sync,
                worker_id,
                limit,
                lease_seconds,
            )

    def _claim_outbox_sync(
        self,
        worker_id: str,
        limit: int,
        lease_seconds: float,
    ) -> list[OutboxRecord]:
        now = utc_now()
        lease_until = now + timedelta(seconds=lease_seconds)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            rows = self._connection.execute(
                """
                SELECT * FROM outbox
                WHERE published_at IS NULL
                  AND available_at <= ?
                  AND (lease_until IS NULL OR lease_until <= ?)
                ORDER BY id ASC
                LIMIT ?
                """,
                (now.isoformat(), now.isoformat(), limit),
            ).fetchall()
            records: list[OutboxRecord] = []
            for row in rows:
                fencing_token = int(row["fencing_token"]) + 1
                attempts = int(row["attempts"]) + 1
                self._connection.execute(
                    """
                    UPDATE outbox
                    SET lease_owner = ?, lease_until = ?, fencing_token = ?, attempts = ?
                    WHERE id = ? AND published_at IS NULL
                    """,
                    (
                        worker_id,
                        lease_until.isoformat(),
                        fencing_token,
                        attempts,
                        row["id"],
                    ),
                )
                records.append(
                    OutboxRecord(
                        id=str(row["id"]),
                        event=Event.from_dict(json.loads(row["event_json"])),
                        topic=str(row["topic"]),
                        attempts=attempts,
                        fencing_token=fencing_token,
                    )
                )
            self._connection.commit()
            return records
        except BaseException:
            self._connection.rollback()
            raise

    async def complete_outbox(self, record_id: str, fencing_token: int) -> bool:
        self._ensure_open()
        async with self._lock:
            return await asyncio.to_thread(
                self._complete_outbox_sync,
                record_id,
                fencing_token,
            )

    def _complete_outbox_sync(self, record_id: str, fencing_token: int) -> bool:
        cursor = self._connection.execute(
            """
            UPDATE outbox
            SET published_at = ?, lease_owner = NULL, lease_until = NULL
            WHERE id = ? AND fencing_token = ? AND published_at IS NULL
            """,
            (utc_now().isoformat(), int(record_id), fencing_token),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    async def retry_outbox(
        self,
        record_id: str,
        fencing_token: int,
        *,
        error: str,
        available_at: datetime,
    ) -> bool:
        self._ensure_open()
        async with self._lock:
            return await asyncio.to_thread(
                self._retry_outbox_sync,
                record_id,
                fencing_token,
                error,
                available_at,
            )

    def _retry_outbox_sync(
        self,
        record_id: str,
        fencing_token: int,
        error: str,
        available_at: datetime,
    ) -> bool:
        cursor = self._connection.execute(
            """
            UPDATE outbox
            SET available_at = ?, last_error = ?, lease_owner = NULL, lease_until = NULL
            WHERE id = ? AND fencing_token = ? AND published_at IS NULL
            """,
            (available_at.isoformat(), error, int(record_id), fencing_token),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    async def claim_inbox(
        self,
        message_id: str,
        consumer_id: str,
        *,
        lease_seconds: float,
    ) -> InboxClaim:
        self._ensure_open()
        async with self._lock:
            return await asyncio.to_thread(
                self._claim_inbox_sync,
                message_id,
                consumer_id,
                lease_seconds,
            )

    def _claim_inbox_sync(
        self,
        message_id: str,
        consumer_id: str,
        lease_seconds: float,
    ) -> InboxClaim:
        now = utc_now()
        lease_until = now + timedelta(seconds=lease_seconds)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._connection.execute(
                "SELECT * FROM inbox WHERE message_id = ? AND consumer_id = ?",
                (message_id, consumer_id),
            ).fetchone()
            if row is not None and row["status"] == "completed":
                self._connection.commit()
                return InboxClaim(InboxDisposition.COMPLETED)
            if row is not None:
                available_at = datetime.fromisoformat(row["available_at"])
                current_lease = (
                    datetime.fromisoformat(row["lease_until"])
                    if row["lease_until"] is not None
                    else None
                )
                if available_at > now or (current_lease is not None and current_lease > now):
                    self._connection.commit()
                    return InboxClaim(InboxDisposition.BUSY)
                fencing_token = int(row["fencing_token"]) + 1
                self._connection.execute(
                    """
                    UPDATE inbox
                    SET status = 'processing', attempts = attempts + 1,
                        lease_until = ?, fencing_token = ?
                    WHERE message_id = ? AND consumer_id = ?
                    """,
                    (
                        lease_until.isoformat(),
                        fencing_token,
                        message_id,
                        consumer_id,
                    ),
                )
            else:
                fencing_token = 1
                self._connection.execute(
                    """
                    INSERT INTO inbox (
                        message_id, consumer_id, status, attempts, available_at,
                        lease_until, fencing_token, received_at
                    ) VALUES (?, ?, 'processing', 1, ?, ?, 1, ?)
                    """,
                    (
                        message_id,
                        consumer_id,
                        now.isoformat(),
                        lease_until.isoformat(),
                        now.isoformat(),
                    ),
                )
            self._connection.commit()
            return InboxClaim(InboxDisposition.ACQUIRED, fencing_token)
        except BaseException:
            self._connection.rollback()
            raise

    async def complete_inbox(
        self,
        message_id: str,
        consumer_id: str,
        fencing_token: int,
    ) -> bool:
        self._ensure_open()
        async with self._lock:
            return await asyncio.to_thread(
                self._complete_inbox_sync,
                message_id,
                consumer_id,
                fencing_token,
            )

    def _complete_inbox_sync(
        self,
        message_id: str,
        consumer_id: str,
        fencing_token: int,
    ) -> bool:
        cursor = self._connection.execute(
            """
            UPDATE inbox
            SET status = 'completed', completed_at = ?, lease_until = NULL
            WHERE message_id = ? AND consumer_id = ?
              AND fencing_token = ? AND status = 'processing'
            """,
            (utc_now().isoformat(), message_id, consumer_id, fencing_token),
        )
        self._connection.commit()
        return cursor.rowcount == 1

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
        async with self._lock:
            return await asyncio.to_thread(
                self._retry_inbox_sync,
                message_id,
                consumer_id,
                fencing_token,
                error,
                available_at,
            )

    def _retry_inbox_sync(
        self,
        message_id: str,
        consumer_id: str,
        fencing_token: int,
        error: str,
        available_at: datetime,
    ) -> bool:
        cursor = self._connection.execute(
            """
            UPDATE inbox
            SET status = 'pending', available_at = ?, last_error = ?, lease_until = NULL
            WHERE message_id = ? AND consumer_id = ?
              AND fencing_token = ? AND status = 'processing'
            """,
            (
                available_at.isoformat(),
                error,
                message_id,
                consumer_id,
                fencing_token,
            ),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    async def pending_outbox_count(self) -> int:
        self._ensure_open()
        async with self._lock:
            return await asyncio.to_thread(self._pending_outbox_count_sync)

    def _pending_outbox_count_sync(self) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM outbox WHERE published_at IS NULL"
        ).fetchone()
        return int(row["count"])

    async def close(self) -> None:
        if self._closed:
            return
        async with self._lock:
            await asyncio.to_thread(self._connection.close)
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("event store is closed")

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Event:
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
                "payload": json.loads(row["payload_json"]),
                "metadata": json.loads(row["metadata_json"]),
                "schema_version": row["schema_version"],
            }
        )


async def copy_events(source: EventStore, target: EventStore) -> int:
    """Copy all events from one store to another, preserving event ids."""

    copied = 0
    cursor = 0
    while True:
        batch = await source.read(after_sequence=cursor, limit=500)
        if not batch:
            return copied
        for event in batch:
            await target.append(event)
            copied += 1
            cursor = event.sequence or cursor
