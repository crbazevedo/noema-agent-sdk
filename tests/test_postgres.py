from __future__ import annotations

import asyncio
import os
import unittest
from uuid import uuid4

from noema import Event, InboxDisposition
from noema.adapters.stores import PostgresEventStore

POSTGRES_DSN = os.getenv("NOEMA_TEST_POSTGRES_DSN")


@unittest.skipUnless(POSTGRES_DSN, "NOEMA_TEST_POSTGRES_DSN is not configured")
class PostgresConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        assert POSTGRES_DSN is not None
        self.first = await PostgresEventStore.connect(POSTGRES_DSN)
        self.second = await PostgresEventStore.connect(POSTGRES_DSN)

    async def asyncTearDown(self) -> None:
        await self.first.close()
        await self.second.close()

    async def test_concurrent_duplicate_append_has_one_canonical_sequence(self) -> None:
        event = Event(f"test.concurrent.{uuid4()}", "postgres-test")
        first, second = await asyncio.gather(
            self.first.append(event),
            self.second.append(event),
        )
        self.assertEqual(first.id, event.id)
        self.assertEqual(second.id, event.id)
        self.assertEqual(first.sequence, second.sequence)

    async def test_concurrent_inbox_claim_has_one_lease_winner(self) -> None:
        message_id = f"message-{uuid4()}"
        first, second = await asyncio.gather(
            self.first.claim_inbox(message_id, "shared-consumer", lease_seconds=10),
            self.second.claim_inbox(message_id, "shared-consumer", lease_seconds=10),
        )
        self.assertCountEqual(
            (first.disposition, second.disposition),
            (InboxDisposition.ACQUIRED, InboxDisposition.BUSY),
        )
