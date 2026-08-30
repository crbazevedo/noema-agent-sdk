"""Deterministic shadow resolution of signals into attention dispositions."""

from __future__ import annotations

import fnmatch
import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from ..types import JSONObject
from .models import (
    SalienceDecision,
    SalienceDisposition,
    Signal,
    SignalRole,
    stable_id,
)


class SalienceResolver:
    """Aggregate, inhibit, prioritize, and budget shadow signals.

    The resolver returns descriptions of what the aware layer *would* receive.
    It never wakes a model, publishes an event, or proposes an executable
    capability call.
    """

    def __init__(
        self,
        *,
        wake_threshold: float = 0.75,
        remember_threshold: float = 0.35,
        urgency_threshold: float = 0.9,
        expected_value_scale: float = 1.0,
        wake_budget: int | None = None,
    ) -> None:
        for name, value in (
            ("wake_threshold", wake_threshold),
            ("remember_threshold", remember_threshold),
            ("urgency_threshold", urgency_threshold),
        ):
            if not math.isfinite(value) or value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be between zero and one")
        if not math.isfinite(expected_value_scale) or expected_value_scale <= 0.0:
            raise ValueError("expected value scale must be positive and finite")
        if wake_budget is not None and wake_budget < 0:
            raise ValueError("wake budget cannot be negative")
        self.wake_threshold = wake_threshold
        self.remember_threshold = remember_threshold
        self.urgency_threshold = urgency_threshold
        self.expected_value_scale = expected_value_scale
        self.wake_budget = wake_budget

    def resolve(self, signals: Sequence[Signal], *, at: datetime) -> tuple[SalienceDecision, ...]:
        if at.tzinfo is None:
            raise ValueError("salience resolution time must be timezone-aware")
        active_by_id: dict[str, Signal] = {}
        for signal in signals:
            if not signal.active_at(at):
                continue
            previous = active_by_id.get(signal.signal_id)
            if previous is not None and previous != signal:
                raise ValueError(f"conflicting content for signal id {signal.signal_id}")
            active_by_id[signal.signal_id] = signal
        active = tuple(sorted(active_by_id.values(), key=self._key))
        inhibitors = tuple(signal for signal in active if signal.role is SignalRole.INHIBITORY)
        groups: dict[str, list[Signal]] = defaultdict(list)
        for signal in active:
            if signal.role is SignalRole.EXCITATORY:
                groups[signal.subject].append(signal)

        decisions = [
            self._resolve_subject(subject, tuple(subject_signals), inhibitors)
            for subject, subject_signals in sorted(groups.items())
        ]
        return self._apply_wake_budget(decisions)

    def _resolve_subject(
        self,
        subject: str,
        signals: tuple[Signal, ...],
        inhibitors: tuple[Signal, ...],
    ) -> SalienceDecision:
        blocked_ids: set[str] = set()
        blocking_by_id: dict[str, Signal] = {}
        for signal in signals:
            for inhibitor in inhibitors:
                if inhibitor.subject not in {"*", subject}:
                    continue
                if inhibitor.precedence < signal.precedence:
                    continue
                if any(fnmatch.fnmatchcase(signal.kind, pattern) for pattern in inhibitor.inhibits):
                    blocked_ids.add(signal.signal_id)
                    blocking_by_id[inhibitor.signal_id] = inhibitor
        blocking = tuple(blocking_by_id[key] for key in sorted(blocking_by_id))
        effective = tuple(signal for signal in signals if signal.signal_id not in blocked_ids)
        scored = effective or signals
        score = round(
            1.0 - math.prod(1.0 - self._contribution(signal) for signal in scored),
            12,
        )
        requested = {signal.suggested_disposition for signal in effective}
        max_urgency = max((signal.urgency for signal in effective), default=0.0)
        reasons: list[str] = [f"aggregated {len(signals)} signal(s)"]
        if blocking and not effective:
            disposition = SalienceDisposition.SUPPRESS
            reasons.append("all signals inhibited by equal-or-higher precedence")
        else:
            if blocking:
                reasons.append(f"inhibited {len(blocked_ids)} lower-precedence signal(s)")
            disposition = self._unopposed_disposition(requested, score, max_urgency, reasons)

        signal_ids = tuple(signal.signal_id for signal in signals)
        inhibited_by = tuple(inhibitor.signal_id for inhibitor in blocking)
        evidence_event_ids = tuple(
            sorted(
                {
                    event_id
                    for signal in (*signals, *blocking)
                    for event_id in signal.evidence_event_ids
                }
            )
        )
        identity: JSONObject = {
            "subject": subject,
            "disposition": disposition.value,
            "signal_ids": list(signal_ids),
            "inhibited_by": list(inhibited_by),
        }
        return SalienceDecision(
            decision_id=stable_id("salience-decision", identity),
            subject=subject,
            disposition=disposition,
            score=score,
            signal_ids=signal_ids,
            evidence_event_ids=evidence_event_ids,
            inhibited_by=inhibited_by,
            reasons=tuple(reasons),
        )

    def _unopposed_disposition(
        self,
        requested: set[SalienceDisposition],
        score: float,
        max_urgency: float,
        reasons: list[str],
    ) -> SalienceDisposition:
        if SalienceDisposition.REFLEX_PROPOSAL in requested and score >= self.wake_threshold:
            reasons.append("bounded reflex proposal threshold reached")
            return SalienceDisposition.REFLEX_PROPOSAL
        if SalienceDisposition.WAKE in requested and (
            score >= self.wake_threshold or max_urgency >= self.urgency_threshold
        ):
            reasons.append("wake threshold reached")
            return SalienceDisposition.WAKE
        if score >= self.remember_threshold:
            reasons.append("retention threshold reached")
            return SalienceDisposition.REMEMBER
        reasons.append("below current attention thresholds")
        return SalienceDisposition.DEFER

    def _contribution(self, signal: Signal) -> float:
        normalized_value = signal.expected_value / (
            signal.expected_value + self.expected_value_scale
        )
        weighted = 0.7 * signal.salience + 0.2 * signal.urgency + 0.1 * normalized_value
        return min(1.0, signal.confidence * weighted)

    def _apply_wake_budget(
        self,
        decisions: list[SalienceDecision],
    ) -> tuple[SalienceDecision, ...]:
        if self.wake_budget is None:
            return tuple(decisions)
        wake_rank = sorted(
            (
                decision
                for decision in decisions
                if decision.disposition is SalienceDisposition.WAKE
            ),
            key=lambda decision: (-decision.score, decision.subject),
        )
        allowed = {decision.decision_id for decision in wake_rank[: self.wake_budget]}
        budgeted: list[SalienceDecision] = []
        for decision in decisions:
            if (
                decision.disposition is SalienceDisposition.WAKE
                and decision.decision_id not in allowed
            ):
                identity: JSONObject = {
                    "subject": decision.subject,
                    "disposition": SalienceDisposition.DEFER.value,
                    "signal_ids": list(decision.signal_ids),
                    "reason": "wake budget exhausted",
                }
                decision = SalienceDecision(
                    decision_id=stable_id("salience-decision", identity),
                    subject=decision.subject,
                    disposition=SalienceDisposition.DEFER,
                    score=decision.score,
                    signal_ids=decision.signal_ids,
                    evidence_event_ids=decision.evidence_event_ids,
                    inhibited_by=decision.inhibited_by,
                    reasons=decision.reasons + ("wake budget exhausted",),
                )
            budgeted.append(decision)
        return tuple(budgeted)

    @staticmethod
    def _key(signal: Signal) -> tuple[str, str, str]:
        return signal.subject, signal.kind, signal.signal_id
