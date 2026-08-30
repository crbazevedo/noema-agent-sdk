"""Canonical processing checkpoints for durable event-stream consumers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from .events import Event
from .types import JSONObject

CONSUMER_CHECKPOINT_EVENT = "runtime.consumer_checkpoint_advanced"


@dataclass(frozen=True, slots=True)
class ConsumerCheckpoint:
    """Durable watermark for one logical consumer of the canonical event log.

    ``event_sequence`` is projection metadata: it identifies where the
    checkpoint record itself lives, while ``last_completed_sequence`` identifies
    the input whose required outputs were complete before the record was written.
    """

    consumer_id: str
    last_completed_sequence: int
    observed_head_sequence: int
    epoch_id: str | None = None
    event_sequence: int | None = None

    def __post_init__(self) -> None:
        if not self.consumer_id.strip():
            raise ValueError("consumer checkpoint requires a non-empty consumer id")
        if self.last_completed_sequence < 0:
            raise ValueError("consumer checkpoint sequence cannot be negative")
        if self.observed_head_sequence < self.last_completed_sequence:
            raise ValueError("observed event-log head cannot precede completed sequence")
        if self.epoch_id is not None and not self.epoch_id.strip():
            raise ValueError("consumer checkpoint epoch id must be non-empty when supplied")
        if self.event_sequence is not None and self.event_sequence <= 0:
            raise ValueError("checkpoint event sequence must be positive when supplied")

    @property
    def processing_lag(self) -> int:
        return self.observed_head_sequence - self.last_completed_sequence

    def to_dict(self) -> JSONObject:
        return {
            "consumer_id": self.consumer_id,
            "last_completed_sequence": self.last_completed_sequence,
            "observed_head_sequence": self.observed_head_sequence,
            "processing_lag": self.processing_lag,
            "epoch_id": self.epoch_id,
        }

    def to_event(
        self,
        *,
        source: str,
        timestamp: datetime,
        causation_id: str | None = None,
    ) -> Event:
        payload = self.to_dict()
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return Event(
            type=CONSUMER_CHECKPOINT_EVENT,
            source=source,
            subject=self.consumer_id,
            payload=payload,
            timestamp=timestamp,
            causation_id=causation_id,
            id=f"consumer-checkpoint:{hashlib.sha256(encoded).hexdigest()[:32]}",
        )

    @classmethod
    def from_event(cls, event: Event) -> ConsumerCheckpoint:
        if event.type != CONSUMER_CHECKPOINT_EVENT:
            raise ValueError(f"not a consumer checkpoint event: {event.type}")
        if event.sequence is None:
            raise ValueError("consumer checkpoint must be restored from a canonical event")
        checkpoint = cls(
            consumer_id=str(event.payload["consumer_id"]),
            last_completed_sequence=int(
                cast(int, event.payload["last_completed_sequence"])
            ),
            observed_head_sequence=int(cast(int, event.payload["observed_head_sequence"])),
            epoch_id=(
                str(event.payload["epoch_id"])
                if event.payload.get("epoch_id") is not None
                else None
            ),
            event_sequence=event.sequence,
        )
        if event.subject != checkpoint.consumer_id:
            raise ValueError("consumer checkpoint subject does not match its consumer id")
        if int(cast(int, event.payload["processing_lag"])) != checkpoint.processing_lag:
            raise ValueError("consumer checkpoint processing lag is inconsistent")
        return checkpoint


class ConsumerCheckpointProjection:
    """Rebuild the latest monotonic checkpoint for every consumer."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, ConsumerCheckpoint] = {}

    @property
    def checkpoints(self) -> tuple[ConsumerCheckpoint, ...]:
        return tuple(self._checkpoints[key] for key in sorted(self._checkpoints))

    def get(self, consumer_id: str) -> ConsumerCheckpoint | None:
        return self._checkpoints.get(consumer_id)

    def apply(self, event: Event) -> bool:
        if event.type != CONSUMER_CHECKPOINT_EVENT:
            return False
        checkpoint = ConsumerCheckpoint.from_event(event)
        current = self._checkpoints.get(checkpoint.consumer_id)
        if (
            current is not None
            and checkpoint.last_completed_sequence < current.last_completed_sequence
        ):
            raise ValueError(
                f"consumer checkpoint regressed for {checkpoint.consumer_id}: "
                f"{checkpoint.last_completed_sequence} < {current.last_completed_sequence}"
            )
        if (
            current is not None
            and checkpoint.observed_head_sequence < current.observed_head_sequence
        ):
            raise ValueError(
                f"consumer observed head regressed for {checkpoint.consumer_id}: "
                f"{checkpoint.observed_head_sequence} < {current.observed_head_sequence}"
            )
        self._checkpoints[checkpoint.consumer_id] = checkpoint
        return True

    def rebuild(self, events: Iterable[Event]) -> None:
        self._checkpoints.clear()
        for event in events:
            self.apply(event)
