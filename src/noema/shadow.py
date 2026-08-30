"""Continuous observational runtime for the Autonomic Shadow Kernel."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime
from time import perf_counter_ns
from typing import cast

from .autonomic import (
    EvaluationEpoch,
    RuleCell,
    RuleRegistry,
    RulesetSnapshot,
    SalienceResolver,
    Signal,
)
from .checkpoints import (
    CONSUMER_CHECKPOINT_EVENT,
    ConsumerCheckpoint,
    ConsumerCheckpointProjection,
)
from .events import Event
from .kernel import NoemaKernel
from .situation import SituationModel
from .telemetry import InMemoryTelemetry, Metric, TelemetrySink
from .types import JSONValue, parse_datetime, utc_now

Clock = Callable[[], datetime]


class AutonomicShadowWorker:
    """Evaluate canonical events continuously and persist observations only.

    Required shadow outputs are appended before the generic consumer checkpoint
    advances. A restart replays every trigger after the latest checkpoint;
    deterministic output identities make partially completed attempts idempotent.
    """

    def __init__(
        self,
        kernel: NoemaKernel,
        *,
        registry: RuleRegistry | None = None,
        cell: RuleCell | None = None,
        resolver: SalienceResolver | None = None,
        telemetry: TelemetrySink | None = None,
        consumer_id: str = "autonomic-shadow",
        source: str = "autonomic:shadow-worker",
        clock: Clock = utc_now,
    ) -> None:
        if not source:
            raise ValueError("shadow worker source must be non-empty")
        if not consumer_id.strip():
            raise ValueError("shadow worker consumer id must be non-empty")
        self.kernel = kernel
        self.registry = registry or RuleRegistry()
        self.cell = cell or RuleCell("continuous-shadow")
        self.resolver = resolver or SalienceResolver()
        self.telemetry = telemetry or InMemoryTelemetry()
        self.consumer_id = consumer_id
        self.source = source
        self.clock = clock
        self._epoch: EvaluationEpoch | None = None
        self._checkpoint: ConsumerCheckpoint | None = None
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
    def checkpoint(self) -> ConsumerCheckpoint | None:
        return self._checkpoint

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        if not self.kernel.started:
            await self.kernel.start()
        self._ready.clear()
        bootstrap_head = await self.kernel.store.latest_sequence()
        self._subscription_id = await self.kernel.bus.subscribe("*", self._handle_event)
        try:
            history = await self.kernel.history()
            self.registry.rebuild(history)
            checkpoints = ConsumerCheckpointProjection()
            checkpoints.rebuild(history)
            checkpoint = checkpoints.get(self.consumer_id)
            if checkpoint is None:
                checkpoint = await self._advance_checkpoint(
                    completed_sequence=bootstrap_head,
                    observed_head_sequence=bootstrap_head,
                    epoch=None,
                    causation_id=None,
                )

            if checkpoint.epoch_id is None:
                epoch = self._new_epoch(checkpoint.last_completed_sequence)
                self._epoch = epoch
                self._started = True
                await self._persist_epoch(epoch)
                checkpoint = await self._advance_checkpoint(
                    completed_sequence=checkpoint.last_completed_sequence,
                    observed_head_sequence=max(
                        checkpoint.observed_head_sequence,
                        await self.kernel.store.latest_sequence(),
                    ),
                    epoch=epoch,
                    causation_id=None,
                )
                self._signals = {}
            else:
                self._epoch = self._restore_epoch(history, checkpoint)
                self._started = True
                self._signals = self._signals_from_history(
                    history,
                    through_sequence=(
                        checkpoint.event_sequence
                        if checkpoint.event_sequence is not None
                        else checkpoint.last_completed_sequence
                    ),
                )

            self._checkpoint = checkpoint
            self._ready.set()
            catchup = await self.kernel.history(
                after_sequence=checkpoint.last_completed_sequence
            )
            for event in catchup:
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
        """Pin all rule registrations after queued trigger processing completes."""

        await self._ready.wait()
        if not self._started:
            raise RuntimeError("shadow worker is not running")
        await self.kernel.bus.drain()
        async with self._lock:
            history = await self.kernel.history()
            self.registry.rebuild(history)
            cursor = max((event.sequence or 0 for event in history), default=0)
            epoch = self._new_epoch(cursor)
            await self._persist_epoch(epoch)
            checkpoint = self._checkpoint
            if checkpoint is None:
                raise RuntimeError("shadow worker has no durable checkpoint")
            self._epoch = epoch
            await self._advance_checkpoint(
                completed_sequence=checkpoint.last_completed_sequence,
                observed_head_sequence=await self.kernel.store.latest_sequence(),
                epoch=epoch,
                causation_id=None,
            )
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

    def _restore_epoch(
        self,
        history: Sequence[Event],
        checkpoint: ConsumerCheckpoint,
    ) -> EvaluationEpoch:
        epoch_id = checkpoint.epoch_id
        if epoch_id is None:
            raise ValueError("cannot restore a checkpoint without an epoch id")
        epoch_event = next(
            (
                event
                for event in reversed(history)
                if event.type == "rule.evaluation_epoch_started"
                and event.payload.get("epoch_id") == epoch_id
            ),
            None,
        )
        if epoch_event is None:
            raise ValueError(f"checkpoint references an unknown evaluation epoch: {epoch_id}")
        ruleset_id = str(epoch_event.payload["ruleset_id"])
        ruleset_event = next(
            (
                event
                for event in reversed(history)
                if event.type == "rule.ruleset_materialized" and event.subject == ruleset_id
            ),
            None,
        )
        if ruleset_event is None:
            raise ValueError(f"evaluation epoch references an unknown ruleset: {ruleset_id}")
        cursor = int(cast(int, epoch_event.payload["event_log_cursor"]))
        refs_value = cast(list[JSONValue], ruleset_event.payload["rule_refs"])
        ruleset = self.registry.snapshot(
            through_sequence=cursor,
            refs=tuple(str(value) for value in refs_value),
        )
        self._verify_ruleset(ruleset, ruleset_id, str(epoch_event.payload["ruleset_digest"]))
        started_at = parse_datetime(str(epoch_event.payload["started_at"]))
        if started_at is None:
            raise ValueError(f"evaluation epoch has no start time: {epoch_id}")
        return EvaluationEpoch(
            epoch_id=epoch_id,
            ruleset=ruleset,
            started_at=started_at,
            event_log_cursor=cursor,
        )

    @staticmethod
    def _verify_ruleset(
        ruleset: RulesetSnapshot,
        expected_id: str,
        expected_digest: str,
    ) -> None:
        if ruleset.snapshot_id != expected_id or ruleset.digest != expected_digest:
            raise ValueError("restored ruleset does not match the checkpointed evaluation epoch")

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
                if event.type == CONSUMER_CHECKPOINT_EVENT:
                    return
                if event.type == "rule.version_registered":
                    self.registry.apply(event)
                    return
                if event.type.startswith("rule."):
                    return
                if event.sequence is None:
                    raise ValueError("shadow worker requires canonical sequenced events")
                checkpoint = self._checkpoint
                if (
                    checkpoint is not None
                    and event.sequence <= checkpoint.last_completed_sequence
                ):
                    return
                await self._process_trigger(event)
            except BaseException:
                self._processed_event_ids.discard(event.id)
                raise

    async def _process_trigger(self, event: Event) -> None:
        epoch = self._epoch
        if epoch is None or event.sequence is None:
            raise RuntimeError("shadow worker has no active evaluation epoch")
        observed_head = await self.kernel.store.latest_sequence()

        rebuild_started = perf_counter_ns()
        history = await self.kernel.history()
        through_event = [
            item
            for item in history
            if item.sequence is not None and item.sequence <= event.sequence
        ]
        situation = SituationModel()
        await situation.rebuild(through_event)
        snapshot = await situation.snapshot()
        rebuild_ms = self._elapsed_ms(rebuild_started)

        evaluation_started = perf_counter_ns()
        traces = self.cell.evaluate(
            epoch,
            event,
            snapshot,
            history=through_event,
        )
        evaluation_ms = self._elapsed_ms(evaluation_started)

        write_ns = 0
        for trace in traces:
            signal = trace.signal_would_emit
            if signal is not None:
                self._signals[signal.signal_id] = signal
            write_started = perf_counter_ns()
            await self.kernel.emit(trace.to_event(source=self.source).caused_by(event))
            write_ns += perf_counter_ns() - write_started

        self._signals = {
            signal_id: signal
            for signal_id, signal in self._signals.items()
            if signal.valid_until > event.timestamp
        }
        resolution_started = perf_counter_ns()
        decisions = self.resolver.resolve(
            tuple(self._signals.values()),
            at=event.timestamp,
        )
        resolution_ms = self._elapsed_ms(resolution_started)
        for decision in decisions:
            write_started = perf_counter_ns()
            await self.kernel.emit(
                decision.to_event(
                    source=self.source,
                    resolved_at=event.timestamp,
                    trigger_event_id=event.id,
                )
            )
            write_ns += perf_counter_ns() - write_started

        processing_lag = max(0, observed_head - event.sequence)
        await self._advance_checkpoint(
            completed_sequence=event.sequence,
            observed_head_sequence=max(observed_head, event.sequence),
            epoch=epoch,
            causation_id=event.id,
        )
        await self._record_processing_metrics(
            events_replayed=len(through_event),
            situation_rebuild_ms=rebuild_ms,
            rule_evaluation_ms=evaluation_ms,
            salience_resolution_ms=resolution_ms,
            shadow_event_write_ms=write_ns / 1_000_000,
            processing_lag=processing_lag,
        )

    async def _advance_checkpoint(
        self,
        *,
        completed_sequence: int,
        observed_head_sequence: int,
        epoch: EvaluationEpoch | None,
        causation_id: str | None,
    ) -> ConsumerCheckpoint:
        current = self._checkpoint
        if current is not None and completed_sequence < current.last_completed_sequence:
            raise ValueError(
                f"consumer checkpoint cannot regress: {completed_sequence} "
                f"< {current.last_completed_sequence}"
            )
        if (
            current is not None
            and observed_head_sequence < current.observed_head_sequence
        ):
            raise ValueError(
                f"consumer observed head cannot regress: {observed_head_sequence} "
                f"< {current.observed_head_sequence}"
            )
        candidate = ConsumerCheckpoint(
            consumer_id=self.consumer_id,
            last_completed_sequence=completed_sequence,
            observed_head_sequence=observed_head_sequence,
            epoch_id=epoch.epoch_id if epoch is not None else None,
        )
        stored = await self.kernel.emit(
            candidate.to_event(
                source=self.source,
                timestamp=self.clock(),
                causation_id=causation_id,
            )
        )
        checkpoint = ConsumerCheckpoint.from_event(stored)
        self._checkpoint = checkpoint
        return checkpoint

    async def _record_processing_metrics(
        self,
        *,
        events_replayed: int,
        situation_rebuild_ms: float,
        rule_evaluation_ms: float,
        salience_resolution_ms: float,
        shadow_event_write_ms: float,
        processing_lag: int,
    ) -> None:
        tags = {"consumer": self.consumer_id}
        values = (
            ("shadow.events_replayed_per_trigger", float(events_replayed)),
            ("shadow.situation_rebuild_ms", situation_rebuild_ms),
            ("shadow.rule_evaluation_ms", rule_evaluation_ms),
            ("shadow.salience_resolution_ms", salience_resolution_ms),
            ("shadow.event_write_ms", shadow_event_write_ms),
            ("consumer.processing_lag_events", float(processing_lag)),
        )
        for name, value in values:
            await self.telemetry.record(Metric(name, value, tags))

    @staticmethod
    def _elapsed_ms(started_ns: int) -> float:
        return (perf_counter_ns() - started_ns) / 1_000_000

    @staticmethod
    def _signals_from_history(
        history: Sequence[Event],
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
