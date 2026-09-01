"""Situation detectors convert observations into higher-level signals."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from .events import Event
from .kernel import NoemaKernel
from .situation import CommitmentStatus, SituationSnapshot
from .types import utc_now


class SituationDetector(Protocol):
    async def detect(
        self,
        event: Event,
        situation: SituationSnapshot,
    ) -> Sequence[Event]: ...


class DetectorEngine:
    def __init__(
        self,
        *,
        kernel: NoemaKernel,
        detectors: Sequence[SituationDetector],
        engine_id: str = "detectors",
    ) -> None:
        self.kernel = kernel
        self.detectors = tuple(detectors)
        self.engine_id = engine_id
        self._subscription_id: str | None = None

    async def start(self) -> None:
        await self.kernel.start()
        if self._subscription_id is None:
            self._subscription_id = await self.kernel.bus.subscribe("*", self._on_event)

    async def stop(self) -> None:
        if self._subscription_id is not None:
            await self.kernel.bus.unsubscribe(self._subscription_id)
            self._subscription_id = None

    async def _on_event(self, event: Event) -> None:
        if event.source == self.engine_id or event.type.startswith("signal."):
            return
        snapshot = await self.kernel.snapshot()
        results = await asyncio.gather(
            *(detector.detect(event, snapshot) for detector in self.detectors)
        )
        for detected_events in results:
            for detected in detected_events:
                await self.kernel.emit(detected.caused_by(event, source=self.engine_id))


@dataclass(frozen=True, slots=True)
class DeadlineRiskDetector:
    """Raise a risk signal when open commitments approach their deadline."""

    horizon: timedelta = timedelta(hours=24)
    minimum_priority: float = 0.0

    async def detect(
        self,
        event: Event,
        situation: SituationSnapshot,
    ) -> Sequence[Event]:
        if event.type != "timer.heartbeat":
            return ()
        now = utc_now()
        events: list[Event] = []
        for commitment in situation.commitments.values():
            if commitment.status not in {
                CommitmentStatus.ACCEPTED,
                CommitmentStatus.ACTIVE,
                CommitmentStatus.OPEN,
                CommitmentStatus.IN_PROGRESS,
            }:
                continue
            if commitment.deadline is None or commitment.priority < self.minimum_priority:
                continue
            remaining = commitment.deadline - now
            if remaining > self.horizon:
                continue
            risk_id = f"deadline:{commitment.id}"
            existing = situation.risks.get(risk_id)
            if existing is not None and existing.active:
                continue
            severity = min(
                1.0, max(0.1, 1.0 - remaining.total_seconds() / self.horizon.total_seconds())
            )
            events.append(
                Event(
                    type="risk.detected",
                    source="deadline-detector",
                    subject=risk_id,
                    priority=int(10 * severity),
                    payload={
                        "id": risk_id,
                        "description": f"Commitment approaching deadline: {commitment.description}",
                        "severity": severity,
                        "probability": 1.0,
                        "impact": max(commitment.priority, commitment.social_cost_of_failure),
                        "mitigation": "reprioritize, complete, renegotiate, or cancel explicitly",
                    },
                )
            )
        return tuple(events)
