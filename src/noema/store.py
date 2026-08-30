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
from pathlib import Path
from typing import Protocol

from .events import Event


class EventStore(Protocol):
    async def append(self, event: Event) -> Event: ...

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
                if (event.sequence or 0) > after_sequence
                and (types is None or event.type in types)
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
                metadata_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_type_sequence "
            "ON events(event_type, sequence)"
        )
        connection.commit()

    async def append(self, event: Event) -> Event:
        self._ensure_open()
        async with self._lock:
            return await asyncio.to_thread(self._append_sync, event)

    def _append_sync(self, event: Event) -> Event:
        try:
            cursor = self._connection.execute(
                """
                INSERT INTO events (
                    event_id, event_type, source, subject, timestamp,
                    correlation_id, causation_id, priority,
                    payload_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(dict(event.payload), separators=(",", ":"), sort_keys=True),
                    json.dumps(dict(event.metadata), separators=(",", ":"), sort_keys=True),
                ),
            )
            self._connection.commit()
            return event.with_sequence(int(cursor.lastrowid))
        except sqlite3.IntegrityError:
            row = self._connection.execute(
                "SELECT * FROM events WHERE event_id = ?", (event.id,)
            ).fetchone()
            if row is None:
                raise
            return self._row_to_event(row)

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
