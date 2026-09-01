"""Crash-recoverable, effect-free worker for endogenous cognition scans."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from typing import cast

from .checkpoints import ConsumerCheckpoint, ConsumerCheckpointProjection
from .endogenous.detectors import DeterministicEndogenousDetector
from .endogenous.models import (
    COGNITION_SCAN_REQUESTED_EVENT,
    BackgroundCognitiveBudget,
    CalibrationExchange,
    CognitionScanRequest,
    DreamEpoch,
    DreamEpochStatus,
    EndogenousPolicySnapshot,
    GoverningIntentRef,
    IntrinsicAgendaSelection,
    dream_epoch_expired_event,
    dream_epoch_preempted_event,
)
from .endogenous.policy import evaluate_value_of_cognition, select_intrinsic_agenda
from .endogenous.projection import EndogenousProjection
from .events import Event
from .kernel import NoemaKernel
from .memory import MemoryProjection
from .store import ConcurrentAppendError
from .types import JSONValue, utc_now

Clock = Callable[[], datetime]


class EndogenousShadowWorker:
    """Discover and select internal questions without dispatching or acting.

    Existing scheduling infrastructure may call :meth:`run_scan`. Recovery uses
    the canonical scan event and generic consumer checkpoint; the worker owns no
    scheduler, task queue, or private offset.
    """

    def __init__(
        self,
        kernel: NoemaKernel,
        *,
        policy: EndogenousPolicySnapshot | None = None,
        detector: DeterministicEndogenousDetector | None = None,
        consumer_id: str = "endogenous-cognition-shadow",
        source: str = "endogenous:shadow-worker",
        foreground_event_types: tuple[str, ...] = (
            "work.order_recorded",
            "decision.proposed",
        ),
        clock: Clock = utc_now,
    ) -> None:
        if not consumer_id.strip() or not source.strip():
            raise ValueError("endogenous worker consumer id and source must be non-empty")
        if not foreground_event_types or any(not value.strip() for value in foreground_event_types):
            raise ValueError("endogenous worker requires explicit foreground event types")
        self.kernel = kernel
        self.policy = policy or EndogenousPolicySnapshot.create(version="deterministic-v1")
        self.detector = detector or DeterministicEndogenousDetector()
        self.consumer_id = consumer_id
        self.source = source
        self.foreground_event_types = tuple(sorted(set(foreground_event_types)))
        self.clock = clock

    async def run_scan(
        self,
        *,
        budget: BackgroundCognitiveBudget,
        started_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> IntrinsicAgendaSelection | None:
        """Record and process one internally scheduled, model-free scan."""

        if not self.kernel.started:
            await self.kernel.start()
        started = started_at or self.clock()
        expiry = expires_at or started + timedelta(minutes=5)
        await self.kernel.emit(self.policy.to_event(source=self.source, recorded_at=started))
        request = CognitionScanRequest.create(
            policy_id=self.policy.policy_id,
            budget=budget,
            requested_at=started,
            expires_at=expiry,
        )
        stored = await self.kernel.emit(request.to_event(source=self.source))
        return await self._process_scan(stored)

    async def record_calibration(
        self,
        exchange: CalibrationExchange,
    ) -> CalibrationExchange:
        """Record one evidence-preserving disagreement contract."""

        if not self.kernel.started:
            await self.kernel.start()
        event = exchange.to_event(source=self.source)
        stored = await self._append_cas(
            event,
            intent_refs=exchange.governing_intent_refs,
            at=exchange.recorded_at,
        )
        if stored is None:
            raise ValueError("calibration exchange lost current governing intent")
        return CalibrationExchange.from_dict(stored.payload)

    async def recover(self) -> tuple[IntrinsicAgendaSelection, ...]:
        """Replay pending scan and foreground triggers after the durable checkpoint."""

        if not self.kernel.started:
            await self.kernel.start()
        history = await self._normalized_history()
        checkpoints = ConsumerCheckpointProjection()
        checkpoints.rebuild(history)
        checkpoint = checkpoints.get(self.consumer_id)
        after = checkpoint.last_completed_sequence if checkpoint is not None else 0
        recovered: list[IntrinsicAgendaSelection] = []
        for event in history:
            if event.sequence is None or event.sequence <= after:
                continue
            if event.type == COGNITION_SCAN_REQUESTED_EVENT:
                selection = await self._process_scan(event)
                if selection is not None:
                    recovered.append(selection)
            elif event.type in self.foreground_event_types:
                await self._process_foreground(event)
        return tuple(recovered)

    async def preempt_for_foreground(self, event: Event) -> tuple[DreamEpoch, ...]:
        """Durably preempt active DREAM epochs for an already-canonical event."""

        if event.sequence is None:
            raise ValueError("foreground preemption requires a canonical event")
        if event.type not in self.foreground_event_types:
            raise ValueError(f"event is not configured as foreground demand: {event.type}")
        return await self._process_foreground(event)

    async def expire_epochs(self, *, at: datetime | None = None) -> tuple[DreamEpoch, ...]:
        """Durably close active epochs whose pinned expiry has passed."""

        expired_at = at or self.clock()
        projection = await self.current_projection()
        expired: list[DreamEpoch] = []
        for epoch in projection.active_epochs:
            if epoch.expires_at > expired_at:
                continue
            event = dream_epoch_expired_event(
                epoch,
                source=self.source,
                expired_at=expired_at,
            )
            stored = await self._append_transition(event, epoch_id=epoch.epoch_id)
            if stored is not None:
                expired.append(epoch)
        return tuple(expired)

    async def current_projection(self) -> EndogenousProjection:
        projection = EndogenousProjection()
        projection.rebuild(await self._normalized_history())
        return projection

    async def _process_scan(self, trigger: Event) -> IntrinsicAgendaSelection | None:
        if trigger.sequence is None:
            raise ValueError("endogenous scan requires a canonical trigger")
        request = CognitionScanRequest.from_dict(trigger.payload)

        full_projection = await self.current_projection()
        existing_epoch = full_projection.epoch_for_trigger(trigger.id)
        if existing_epoch is not None:
            existing_selection = full_projection.selection(existing_epoch.epoch_id)
            if existing_selection is not None:
                await self._advance_checkpoint(
                    completed_sequence=trigger.sequence,
                    epoch_id=existing_epoch.epoch_id,
                    causation_id=trigger.id,
                    timestamp=request.requested_at,
                )
                return existing_selection

        history = await self._normalized_history()
        cut = tuple(
            event
            for event in history
            if event.sequence is not None and event.sequence <= trigger.sequence
        )
        cut_projection = EndogenousProjection()
        cut_projection.rebuild(cut)
        memory = MemoryProjection()
        memory.rebuild(cut, through_sequence=trigger.sequence)
        candidates = self.detector.detect(
            history=cut,
            strategy=cut_projection.strategy,
            memory=memory,
            calibrations=cut_projection.calibrations,
            at=request.requested_at,
            causal_cursor=trigger.sequence,
        )
        if not candidates:
            await self._advance_checkpoint(
                completed_sequence=trigger.sequence,
                epoch_id=None,
                causation_id=trigger.id,
                timestamp=request.requested_at,
            )
            return None

        policy = cut_projection.policy(request.policy_id)
        if policy is None:
            raise ValueError("cognition scan policy is absent at its canonical cut")
        epoch = existing_epoch
        if epoch is None:
            epoch = DreamEpoch.start(
                trigger_event_id=trigger.id,
                event_log_cursor=trigger.sequence,
                policy=policy,
                budget=request.budget,
                started_at=request.requested_at,
                expires_at=request.expires_at,
            )
            started_event = await self._append_epoch_start(epoch)
            if started_event is None:
                await self._advance_checkpoint(
                    completed_sequence=trigger.sequence,
                    epoch_id=None,
                    causation_id=trigger.id,
                    timestamp=request.requested_at,
                )
                return None

        for candidate in candidates:
            projection = await self.current_projection()
            known_inquiry = projection.inquiry(candidate.inquiry.inquiry_id)
            if known_inquiry is None:
                stored = await self._append_epoch_output(
                    candidate.inquiry.to_event(source=self.source, epoch_id=epoch.epoch_id),
                    epoch_id=epoch.epoch_id,
                    intent_refs=candidate.inquiry.governing_intent_refs,
                    at=epoch.started_at,
                )
                if stored is None:
                    return None
            elif (
                known_inquiry.question != candidate.inquiry.question
                or known_inquiry.governing_intent_refs != candidate.inquiry.governing_intent_refs
                or known_inquiry.evidence_refs != candidate.inquiry.evidence_refs
            ):
                raise ValueError("content-addressed inquiry changed between scans")

            stored_activity = await self._append_epoch_output(
                candidate.activity.to_event(
                    source=self.source,
                    epoch_id=epoch.epoch_id,
                    recorded_at=epoch.started_at,
                ),
                epoch_id=epoch.epoch_id,
                intent_refs=candidate.activity.governing_intent_refs,
                at=epoch.started_at,
            )
            if stored_activity is None:
                return None
            estimate = evaluate_value_of_cognition(
                candidate.activity,
                epoch=epoch,
                policy=policy,
                evaluated_at=epoch.started_at,
            )
            stored_estimate = await self._append_epoch_output(
                estimate.to_event(source=self.source),
                epoch_id=epoch.epoch_id,
                intent_refs=candidate.activity.governing_intent_refs,
                at=epoch.started_at,
            )
            if stored_estimate is None:
                return None

        projection = await self.current_projection()
        existing_selection = projection.selection(epoch.epoch_id)
        if existing_selection is not None:
            selection = existing_selection
        else:
            activities = projection.activities_for_epoch(epoch.epoch_id)
            estimates = projection.estimates_for_epoch(epoch.epoch_id)
            selection = select_intrinsic_agenda(
                epoch=epoch,
                policy=policy,
                activities=activities,
                estimates=estimates,
                selected_at=epoch.started_at,
            )
            refs = tuple(
                sorted({ref for activity in activities for ref in activity.governing_intent_refs})
            )
            stored_selection = await self._append_epoch_output(
                selection.to_event(source=self.source),
                epoch_id=epoch.epoch_id,
                intent_refs=refs,
                at=selection.selected_at,
            )
            if stored_selection is None:
                return None
        await self._advance_checkpoint(
            completed_sequence=trigger.sequence,
            epoch_id=epoch.epoch_id,
            causation_id=trigger.id,
            timestamp=request.requested_at,
        )
        return selection

    async def _process_foreground(self, event: Event) -> tuple[DreamEpoch, ...]:
        if event.sequence is None:
            raise ValueError("foreground demand requires canonical sequence")
        projection = await self.current_projection()
        preempted: list[DreamEpoch] = []
        for epoch in projection.active_epochs:
            preempted_at = max(epoch.started_at, event.timestamp)
            transition = dream_epoch_preempted_event(
                epoch,
                foreground_event=event,
                source=self.source,
                preempted_at=preempted_at,
            )
            stored = await self._append_transition(transition, epoch_id=epoch.epoch_id)
            if stored is not None:
                preempted.append(epoch)
        await self._advance_checkpoint(
            completed_sequence=event.sequence,
            epoch_id=preempted[-1].epoch_id if preempted else None,
            causation_id=event.id,
            timestamp=max(
                event.timestamp,
                max((value.started_at for value in preempted), default=event.timestamp),
            ),
        )
        return tuple(preempted)

    async def _append_epoch_start(self, epoch: DreamEpoch) -> Event | None:
        while True:
            projection = await self.current_projection()
            existing = projection.event(f"dream-epoch-started:{epoch.epoch_id}")
            if existing is not None:
                return existing
            if projection.event_cursor != epoch.event_log_cursor:
                return None
            event = self._with_admission_receipt(epoch.to_event(source=self.source), projection)
            try:
                return await self.kernel.emit_if_head(
                    event,
                    expected_head_sequence=projection.event_cursor,
                )
            except ConcurrentAppendError:
                continue

    async def _append_epoch_output(
        self,
        event: Event,
        *,
        epoch_id: str,
        intent_refs: tuple[GoverningIntentRef, ...],
        at: datetime,
    ) -> Event | None:
        while True:
            projection = await self.current_projection()
            existing = projection.event(event.id)
            if existing is not None:
                return existing
            epoch = projection.epoch(epoch_id)
            if (
                epoch is None
                or projection.epoch_status(epoch_id) is not DreamEpochStatus.ACTIVE
                or at >= epoch.expires_at
                or not projection.intent_refs_are_current(intent_refs)
            ):
                return None
            admitted = self._with_admission_receipt(event, projection)
            try:
                return await self.kernel.emit_if_head(
                    admitted,
                    expected_head_sequence=projection.event_cursor,
                )
            except ConcurrentAppendError:
                continue

    async def _append_cas(
        self,
        event: Event,
        *,
        intent_refs: tuple[GoverningIntentRef, ...],
        at: datetime,
    ) -> Event | None:
        del at  # the immutable event carries its own semantic time
        while True:
            projection = await self.current_projection()
            existing = projection.event(event.id)
            if existing is not None:
                return existing
            if not projection.intent_refs_are_current(intent_refs):
                return None
            evidence = (
                *cast(tuple[str, ...], event.payload.get("local_evidence_refs", ())),
                *cast(tuple[str, ...], event.payload.get("peer_evidence_refs", ())),
                str(event.payload.get("request_provenance_ref", "")),
                str(event.payload.get("response_provenance_ref", "")),
            )
            if any(
                not value.startswith("event:")
                or projection.event(value.removeprefix("event:")) is None
                for value in evidence
            ):
                raise ValueError("calibration evidence must resolve at admission")
            admitted = self._with_admission_receipt(event, projection)
            try:
                return await self.kernel.emit_if_head(
                    admitted,
                    expected_head_sequence=projection.event_cursor,
                )
            except ConcurrentAppendError:
                continue

    async def _append_transition(self, event: Event, *, epoch_id: str) -> Event | None:
        while True:
            projection = await self.current_projection()
            existing = projection.event(event.id)
            if existing is not None:
                return existing
            epoch = projection.epoch(epoch_id)
            if epoch is None or projection.epoch_status(epoch_id) is not DreamEpochStatus.ACTIVE:
                return None
            admitted = self._with_admission_receipt(event, projection)
            try:
                return await self.kernel.emit_if_head(
                    admitted,
                    expected_head_sequence=projection.event_cursor,
                )
            except ConcurrentAppendError:
                continue

    @staticmethod
    def _with_admission_receipt(event: Event, projection: EndogenousProjection) -> Event:
        metadata: dict[str, JSONValue] = dict(event.metadata)
        metadata["validated_at_event_cursor"] = projection.event_cursor
        return replace(event, metadata=metadata)

    async def _advance_checkpoint(
        self,
        *,
        completed_sequence: int,
        epoch_id: str | None,
        causation_id: str,
        timestamp: datetime,
    ) -> ConsumerCheckpoint:
        history = await self._normalized_history()
        checkpoints = ConsumerCheckpointProjection()
        checkpoints.rebuild(history)
        current = checkpoints.get(self.consumer_id)
        if current is not None and current.last_completed_sequence >= completed_sequence:
            return current
        observed_head = max(
            current.observed_head_sequence if current is not None else 0,
            await self.kernel.store.latest_sequence(),
            completed_sequence,
        )
        candidate = ConsumerCheckpoint(
            consumer_id=self.consumer_id,
            last_completed_sequence=completed_sequence,
            observed_head_sequence=observed_head,
            epoch_id=epoch_id,
        )
        stored = await self.kernel.emit(
            candidate.to_event(
                source=self.source,
                timestamp=timestamp,
                causation_id=causation_id,
            )
        )
        return ConsumerCheckpoint.from_event(stored)

    async def _normalized_history(self) -> list[Event]:
        return [self.kernel.schemas.normalize(event) for event in await self.kernel.history()]
