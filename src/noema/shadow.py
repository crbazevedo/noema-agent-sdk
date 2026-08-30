"""Continuous observational runtime for the Autonomic Shadow Kernel."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime

from .autonomic import (
    EvaluationEpoch,
    RuleCell,
    RuleRegistry,
    SalienceResolver,
    Signal,
)
from .events import Event
from .kernel import NoemaKernel
from .situation import SituationModel
from .types import utc_now

Clock = Callable[[], datetime]


class AutonomicShadowWorker:
    """Evaluate canonical events continuously and persist observations only.

    The worker is the integration seam around the effect-isolated autonomic
    core. It may append ruleset, epoch, evaluation, and shadow-decision events;
    it has no model, agent, policy, authority, or capability dependency.
    """

    def __init__(
        self,
        kernel: NoemaKernel,
        *,
        registry: RuleRegistry | None = None,
        cell: RuleCell | None = None,
        resolver: SalienceResolver | None = None,
        source: str = "autonomic:shadow-worker",
        clock: Clock = utc_now,
    ) -> None:
        if not source:
            raise ValueError("shadow worker source must be non-empty")
        self.kernel = kernel
        self.registry = registry or RuleRegistry()
        self.cell = cell or RuleCell("continuous-shadow")
        self.resolver = resolver or SalienceResolver()
        self.source = source
        self.clock = clock
        self._epoch: EvaluationEpoch | None = None
        self._signals: dict[str, Signal] = {}
        self._processed_event_ids: set[str] = set()
        self._subscription_id: str | None = None
        self._ready = asyncio.Event()
        self._lock = asyncio.Lock()
        self._started = False

    @property
    def epoch(self) -> EvaluationEpoch | None:
        return self._epoch

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        if not self.kernel.started:
            await self.kernel.start()
        self._ready.clear()
        cursor = await self.kernel.store.latest_sequence()
        self._subscription_id = await self.kernel.bus.subscribe("*", self._handle_event)
        try:
            history = await self.kernel.history()
            self.registry.rebuild(history)
            self._signals = self._signals_from_history(history, through_sequence=cursor)
            self._epoch = self._new_epoch(cursor)
            self._started = True
            await self._persist_epoch(self._epoch)
            self._ready.set()
            for event in history:
                if event.sequence is not None and event.sequence > cursor:
                    await self._handle_event(event)
        except BaseException:
            self._started = False
            self._ready.set()
            subscription_id = self._subscription_id
            self._subscription_id = None
            if subscription_id is not None:
                await self.kernel.bus.unsubscribe(subscription_id)
            raise

    async def rotate_epoch(self) -> EvaluationEpoch:
        """Pin all rule registrations currently durable in the event log."""

        await self._ready.wait()
        if not self._started:
            raise RuntimeError("shadow worker is not running")
        async with self._lock:
            history = await self.kernel.history()
            self.registry.rebuild(history)
            cursor = max((event.sequence or 0 for event in history), default=0)
            epoch = self._new_epoch(cursor)
            self._epoch = epoch
            await self._persist_epoch(epoch)
            return epoch

    async def stop(self) -> None:
        if not self._started and self._subscription_id is None:
            return
        self._started = False
        self._ready.set()
        subscription_id = self._subscription_id
        self._subscription_id = None
        if subscription_id is not None:
            await self.kernel.bus.unsubscribe(subscription_id)

    def _new_epoch(self, cursor: int) -> EvaluationEpoch:
        ruleset = self.registry.snapshot(through_sequence=cursor)
        return EvaluationEpoch.open(
            ruleset,
            started_at=self.clock(),
            event_log_cursor=cursor,
        )

    async def _persist_epoch(self, epoch: EvaluationEpoch) -> None:
        await self.kernel.emit(
            epoch.ruleset.to_event(source=self.source, timestamp=epoch.started_at)
        )
        await self.kernel.emit(epoch.to_event(source=self.source))

    async def _handle_event(self, event: Event) -> None:
        await self._ready.wait()
        if not self._started:
            return
        async with self._lock:
            if event.id in self._processed_event_ids:
                return
            self._processed_event_ids.add(event.id)
            try:
                if event.type == "rule.version_registered":
                    self.registry.apply(event)
                    return
                if event.type.startswith("rule."):
                    return
                epoch = self._epoch
                if epoch is None:
                    return
                history = await self.kernel.history()
                through_event = [
                    item
                    for item in history
                    if item.sequence is not None
                    and event.sequence is not None
                    and item.sequence <= event.sequence
                ]
                situation = SituationModel()
                await situation.rebuild(through_event)
                snapshot = await situation.snapshot()
                traces = self.cell.evaluate(
                    epoch,
                    event,
                    snapshot,
                    history=through_event,
                )
                for trace in traces:
                    signal = trace.signal_would_emit
                    if signal is not None:
                        self._signals[signal.signal_id] = signal
                    await self.kernel.emit(trace.to_event(source=self.source))
                self._signals = {
                    signal_id: signal
                    for signal_id, signal in self._signals.items()
                    if signal.valid_until > event.timestamp
                }
                decisions = self.resolver.resolve(
                    tuple(self._signals.values()),
                    at=event.timestamp,
                )
                for decision in decisions:
                    await self.kernel.emit(
                        decision.to_event(
                            source=self.source,
                            resolved_at=event.timestamp,
                            trigger_event_id=event.id,
                        )
                    )
            except BaseException:
                self._processed_event_ids.discard(event.id)
                raise

    @staticmethod
    def _signals_from_history(
        history: list[Event],
        *,
        through_sequence: int,
    ) -> dict[str, Signal]:
        signals: dict[str, Signal] = {}
        for event in history:
            if (
                event.type != "rule.evaluation_traced"
                or event.sequence is None
                or event.sequence > through_sequence
            ):
                continue
            value = event.payload.get("signal_would_emit")
            if not isinstance(value, dict):
                continue
            signal = Signal.from_dict(value)
            previous = signals.get(signal.signal_id)
            if previous is not None and previous != signal:
                raise ValueError(f"conflicting durable signal {signal.signal_id}")
            signals[signal.signal_id] = signal
        return signals
