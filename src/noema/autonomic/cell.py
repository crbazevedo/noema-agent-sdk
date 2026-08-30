"""Stateless, deterministic cells for autonomic shadow evaluation."""

from __future__ import annotations

import fnmatch
import time
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real
from typing import cast

from ..events import Event
from ..situation import SituationModel, SituationSnapshot
from ..types import JSONObject, JSONValue
from .models import (
    AutonomicRule,
    ComparisonOperator,
    EvaluationEpoch,
    PredicateClause,
    PredicateSpec,
    RuleEvaluationTrace,
    RuleFamily,
    ScoringSpec,
    TemporalSpec,
    ValueSource,
    build_signal,
    stable_id,
)


@dataclass(frozen=True, slots=True)
class _EvaluationResult:
    score: float
    matched: tuple[str, ...]
    failed: tuple[str, ...]
    evidence: tuple[str, ...]


class RuleCell:
    """Effect-free evaluation boundary over caller-supplied canonical state.

    A cell holds no durable situation or temporal truth. Callers provide the
    current event, the current situation projection, and canonical event
    history. The only outputs are shadow traces containing hypothetical signals.
    """

    def __init__(self, cell_id: str, *, subscriptions: Sequence[str] = ("*",)) -> None:
        if not cell_id:
            raise ValueError("cell id must be non-empty")
        if not subscriptions or any(not pattern for pattern in subscriptions):
            raise ValueError("a rule cell requires non-empty subscriptions")
        self.cell_id = cell_id
        self.subscriptions = tuple(subscriptions)

    def accepts(self, event: Event) -> bool:
        return any(fnmatch.fnmatchcase(event.type, pattern) for pattern in self.subscriptions)

    def evaluate(
        self,
        epoch: EvaluationEpoch,
        event: Event,
        situation: SituationSnapshot,
        *,
        history: Sequence[Event],
    ) -> tuple[RuleEvaluationTrace, ...]:
        if not self.accepts(event) or (
            event.sequence is not None and event.sequence <= epoch.event_log_cursor
        ):
            return ()
        traces: list[RuleEvaluationTrace] = []
        for rule in epoch.ruleset.rules:
            if not fnmatch.fnmatchcase(event.type, rule.trigger):
                continue
            started_ns = time.perf_counter_ns()
            result = self._evaluate_rule(rule, event, situation, history)
            score = round(min(1.0, max(0.0, result.score)), 12)
            activated = score >= rule.threshold
            signal = (
                build_signal(
                    rule=rule,
                    epoch=epoch,
                    event=event,
                    activation_score=score,
                    evidence_event_ids=result.evidence,
                )
                if activated
                else None
            )
            identity: JSONObject = {
                "cell_id": self.cell_id,
                "epoch_id": epoch.epoch_id,
                "rule_ref": rule.ref,
                "event_id": event.id,
            }
            runtime_cost_us = max(0, (time.perf_counter_ns() - started_ns) // 1000)
            traces.append(
                RuleEvaluationTrace(
                    trace_id=stable_id("rule-trace", identity),
                    rule_id=rule.rule_id,
                    version=rule.version,
                    epoch_id=epoch.epoch_id,
                    evaluated_at=event.timestamp,
                    candidate=True,
                    activated=activated,
                    activation_score=score,
                    threshold=rule.threshold,
                    matched_conditions=result.matched,
                    failed_conditions=result.failed,
                    evidence_refs=result.evidence,
                    signal_would_emit=signal,
                    runtime_cost_us=runtime_cost_us,
                )
            )
        return tuple(traces)

    async def replay(
        self,
        epoch: EvaluationEpoch,
        events: Sequence[Event],
    ) -> tuple[RuleEvaluationTrace, ...]:
        """Rebuild situation state and shadow-evaluate one canonical replay."""

        situation = SituationModel()
        history: list[Event] = []
        traces: list[RuleEvaluationTrace] = []
        for index, event in enumerate(events, start=1):
            await situation.apply(event)
            history.append(event)
            logical_sequence = event.sequence or epoch.event_log_cursor + index
            if logical_sequence <= epoch.event_log_cursor:
                continue
            snapshot = await situation.snapshot()
            traces.extend(self.evaluate(epoch, event, snapshot, history=history))
        return tuple(traces)

    def _evaluate_rule(
        self,
        rule: AutonomicRule,
        event: Event,
        situation: SituationSnapshot,
        history: Sequence[Event],
    ) -> _EvaluationResult:
        if rule.family is RuleFamily.PREDICATE:
            return self._evaluate_predicate(cast(PredicateSpec, rule.spec), event, situation)
        if rule.family is RuleFamily.SCORING:
            return self._evaluate_scoring(cast(ScoringSpec, rule.spec), event, situation)
        return self._evaluate_temporal(cast(TemporalSpec, rule.spec), event, situation, history)

    def _evaluate_predicate(
        self,
        spec: PredicateSpec,
        event: Event,
        situation: SituationSnapshot,
    ) -> _EvaluationResult:
        matched, failed, evidence = self._evaluate_clauses(spec.all_of, event, situation)
        return _EvaluationResult(
            score=1.0 if not failed else 0.0,
            matched=matched,
            failed=failed,
            evidence=evidence,
        )

    def _evaluate_scoring(
        self,
        spec: ScoringSpec,
        event: Event,
        situation: SituationSnapshot,
    ) -> _EvaluationResult:
        score = spec.bias
        matched: list[str] = []
        failed: list[str] = []
        evidence = {event.id}
        for feature in spec.features:
            description, condition_matched, ref_evidence = self._evaluate_clause(
                feature.condition,
                event,
                situation,
            )
            evidence.update(ref_evidence)
            if condition_matched:
                score += feature.weight
                matched.append(f"{feature.name}:{description}")
            else:
                failed.append(f"{feature.name}:{description}")
        return _EvaluationResult(
            score=score,
            matched=tuple(matched),
            failed=tuple(failed),
            evidence=tuple(sorted(evidence)),
        )

    def _evaluate_temporal(
        self,
        spec: TemporalSpec,
        event: Event,
        situation: SituationSnapshot,
        history: Sequence[Event],
    ) -> _EvaluationResult:
        matched, failed, condition_evidence = self._evaluate_clauses(
            spec.current_conditions,
            event,
            situation,
        )
        relevant = [
            (index, item)
            for index, item in enumerate(history)
            if item.timestamp <= event.timestamp
            and (not spec.same_subject or item.subject == event.subject)
        ]
        anchors = [entry for entry in relevant if entry[1].type == spec.anchor_event_type]
        evidence = set(condition_evidence)
        evidence.add(event.id)
        if not anchors:
            return _EvaluationResult(
                score=0.0,
                matched=matched,
                failed=failed + (f"missing anchor:{spec.anchor_event_type}",),
                evidence=tuple(sorted(evidence)),
            )
        anchor_index, anchor = max(anchors, key=lambda entry: entry[0])
        evidence.add(anchor.id)
        resets = [
            item
            for index, item in relevant
            if index > anchor_index
            if item.type in spec.reset_event_types
        ]
        if resets:
            latest_reset = resets[-1]
            evidence.add(latest_reset.id)
            failed = failed + (f"reset:{latest_reset.type}",)
        else:
            matched = matched + ("no reset after anchor",)
        elapsed = (event.timestamp - anchor.timestamp).total_seconds()
        elapsed_description = f"elapsed_seconds>={spec.min_elapsed_seconds:g}"
        if elapsed >= spec.min_elapsed_seconds:
            matched = matched + (elapsed_description,)
        else:
            failed = failed + (elapsed_description,)
        return _EvaluationResult(
            score=1.0 if not failed else 0.0,
            matched=matched,
            failed=failed,
            evidence=tuple(sorted(evidence)),
        )

    def _evaluate_clauses(
        self,
        clauses: Sequence[PredicateClause],
        event: Event,
        situation: SituationSnapshot,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        matched: list[str] = []
        failed: list[str] = []
        evidence = {event.id}
        for clause in clauses:
            description, condition_matched, ref_evidence = self._evaluate_clause(
                clause,
                event,
                situation,
            )
            evidence.update(ref_evidence)
            (matched if condition_matched else failed).append(description)
        return tuple(matched), tuple(failed), tuple(sorted(evidence))

    def _evaluate_clause(
        self,
        clause: PredicateClause,
        event: Event,
        situation: SituationSnapshot,
    ) -> tuple[str, bool, tuple[str, ...]]:
        actual: JSONValue
        evidence = {event.id}
        if clause.ref.source is ValueSource.FACT:
            fact = situation.facts.get(clause.ref.key)
            actual = None if fact is None else fact.value
            if fact is not None and fact.evidence_event_id is not None:
                evidence.add(fact.evidence_event_id)
        else:
            actual = self._event_value(event, clause.ref.key)
        result = self._compare(actual, clause.operator, clause.value)
        description = f"{clause.ref.source.value}.{clause.ref.key} {clause.operator.value}"
        return description, result, tuple(sorted(evidence))

    @staticmethod
    def _event_value(event: Event, key: str) -> JSONValue:
        if key == "type":
            return event.type
        if key == "subject":
            return event.subject
        value: JSONValue = cast(JSONValue, event.payload)
        path = key.removeprefix("payload.")
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
        return value

    @staticmethod
    def _compare(actual: JSONValue, operator: ComparisonOperator, expected: JSONValue) -> bool:
        if operator is ComparisonOperator.EQUALS:
            return actual == expected
        if operator is ComparisonOperator.NOT_EQUALS:
            return actual != expected
        if operator is ComparisonOperator.CONTAINS:
            if isinstance(actual, str):
                return isinstance(expected, str) and expected in actual
            if isinstance(actual, list):
                return expected in actual
            if isinstance(actual, dict):
                return isinstance(expected, str) and expected in actual
            return False
        if (
            isinstance(actual, bool)
            or isinstance(expected, bool)
            or not isinstance(actual, Real)
            or not isinstance(expected, Real)
        ):
            return False
        if operator is ComparisonOperator.GREATER_THAN:
            return actual > expected
        if operator is ComparisonOperator.GREATER_OR_EQUAL:
            return actual >= expected
        if operator is ComparisonOperator.LESS_THAN:
            return actual < expected
        if operator is ComparisonOperator.LESS_OR_EQUAL:
            return actual <= expected
        return False
