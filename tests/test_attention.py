from __future__ import annotations

import unittest

from noema import AttentionAccount, AttentionAllocator, WorkItem


class AttentionTests(unittest.IsolatedAsyncioTestCase):
    def test_allocator_optimizes_portfolio_not_raw_value(self) -> None:
        allocator = AttentionAllocator()
        expensive = WorkItem("expensive", impact=20, attention_cost=20)
        small_a = WorkItem("a", impact=9, attention_cost=4)
        small_b = WorkItem("b", impact=9, attention_cost=4)
        selected = allocator.select([expensive, small_a, small_b], budget=8)
        self.assertEqual({item.key for item in selected}, {"a", "b"})

    async def test_attention_lease_releases_concurrency_capacity(self) -> None:
        account = AttentionAccount(5)
        lease = await account.acquire(4)
        self.assertIsNotNone(lease)
        self.assertEqual(account.available, 1)
        assert lease is not None
        await lease.settle(actual_cost=3)
        self.assertEqual(account.available, 5)
        self.assertEqual(account.spent_total, 3)
