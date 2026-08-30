"""Portfolio-level attention allocation for autonomous agents."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class WorkItem:
    key: str
    impact: float = 0.0
    urgency: float = 0.0
    information_value: float = 0.0
    risk_reduction: float = 0.0
    maintenance_value: float = 0.0
    attention_cost: float = 1.0
    switching_cost: float = 0.0
    branch_cost: float = 0.0
    deadline: datetime | None = None
    payload: object | None = None

    @property
    def overdue(self) -> bool:
        if self.deadline is None:
            return False
        now = datetime.now(timezone.utc)
        deadline = self.deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return deadline <= now


@dataclass(frozen=True, slots=True)
class AttentionWeights:
    impact: float = 1.0
    urgency: float = 1.0
    information_value: float = 0.8
    risk_reduction: float = 1.0
    maintenance_value: float = 0.7
    switching_cost: float = 1.0
    branch_cost: float = 1.0
    overdue_bonus: float = 1000.0


class AttentionAllocator:
    """Select a bounded portfolio rather than evaluating actions independently."""

    def __init__(self, weights: AttentionWeights | None = None) -> None:
        self.weights = weights or AttentionWeights()

    def score(self, item: WorkItem) -> float:
        weights = self.weights
        benefit = (
            weights.impact * item.impact
            + weights.urgency * item.urgency
            + weights.information_value * item.information_value
            + weights.risk_reduction * item.risk_reduction
            + weights.maintenance_value * item.maintenance_value
        )
        cost = (
            item.attention_cost
            + weights.switching_cost * item.switching_cost
            + weights.branch_cost * item.branch_cost
        )
        return benefit - cost + (weights.overdue_bonus if item.overdue else 0.0)

    def select(self, items: list[WorkItem], budget: float) -> list[WorkItem]:
        if budget < 0:
            raise ValueError("attention budget cannot be negative")
        ranked = sorted(
            items,
            key=lambda item: (
                item.overdue,
                self.score(item) / max(item.attention_cost, 1e-9),
                self.score(item),
            ),
            reverse=True,
        )
        selected: list[WorkItem] = []
        remaining = budget
        for item in ranked:
            if self.score(item) < 0 and not item.overdue:
                continue
            if item.attention_cost <= remaining:
                selected.append(item)
                remaining -= item.attention_cost
        return selected


@dataclass(slots=True)
class AttentionLease:
    account: "AttentionAccount"
    lease_id: str
    reserved: float
    settled: bool = False

    async def settle(self, actual_cost: float | None = None) -> None:
        if self.settled:
            return
        await self.account._settle(self.lease_id, self.reserved, actual_cost)
        self.settled = True

    async def __aenter__(self) -> "AttentionLease":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.settle()


class AttentionAccount:
    """Concurrent attention budget with explicit leases."""

    def __init__(self, capacity: float) -> None:
        if capacity <= 0:
            raise ValueError("attention capacity must be positive")
        self.capacity = capacity
        self._available = capacity
        self._leases: dict[str, float] = {}
        self._spent_total = 0.0
        self._counter = 0
        self._lock = asyncio.Lock()

    @property
    def available(self) -> float:
        return self._available

    @property
    def spent_total(self) -> float:
        return self._spent_total

    async def acquire(self, amount: float) -> AttentionLease | None:
        if amount < 0:
            raise ValueError("attention amount cannot be negative")
        async with self._lock:
            if amount > self._available:
                return None
            self._counter += 1
            lease_id = f"attention-{self._counter}"
            self._available -= amount
            self._leases[lease_id] = amount
            return AttentionLease(self, lease_id, amount)

    async def _settle(
        self,
        lease_id: str,
        reserved: float,
        actual_cost: float | None,
    ) -> None:
        async with self._lock:
            if lease_id not in self._leases:
                return
            self._leases.pop(lease_id)
            actual = reserved if actual_cost is None else max(0.0, actual_cost)
            self._spent_total += actual
            self._available = min(self.capacity, self._available + reserved)

    async def replenish(self, amount: float | None = None) -> None:
        async with self._lock:
            if amount is None:
                self._available = self.capacity - sum(self._leases.values())
            else:
                self._available = min(self.capacity, self._available + max(0.0, amount))
