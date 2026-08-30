"""Immutable contracts for effect-free autonomic shadow evaluation."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import cast

from ..events import Event
from ..types import JSONObject, JSONValue, parse_datetime


def canonical_bytes(value: JSONObject) -> bytes:
    """Serialize a JSON object deterministically for replay comparisons."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def stable_id(prefix: str, value: JSONObject) -> str:
    digest = hashlib.sha256(canonical_bytes(value)).hexdigest()[:32]
    return f"{prefix}:{digest}"


class RuleFamily(StrEnum):
    """The only encodings admitted by the first shadow kernel."""

    PREDICATE = "predicate"
    TEMPORAL = "temporal"
    SCORING = "scoring"


class ValueSource(StrEnum):
    EVENT = "event"
    FACT = "fact"


class ComparisonOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"
    CONTAINS = "contains"


class SignalRole(StrEnum):
    EXCITATORY = "excitatory"
    INHIBITORY = "inhibitory"


class InhibitionMode(StrEnum):
    HARD = "hard"
    MODULATE = "modulate"


class SalienceDisposition(StrEnum):
    WAKE = "wake"
    REMEMBER = "remember"
    REFLEX_PROPOSAL = "reflex_proposal"
    SUPPRESS = "suppress"
    DEFER = "defer"


@dataclass(frozen=True, slots=True)
class ValueRef:
    source: ValueSource
    key: str

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("value reference key must be non-empty")

    def to_dict(self) -> JSONObject:
        return {"source": self.source.value, "key": self.key}

    @classmethod
    def from_dict(cls, data: JSONObject) -> ValueRef:
        return cls(source=ValueSource(str(data["source"])), key=str(data["key"]))


@dataclass(frozen=True, slots=True)
class PredicateClause:
    ref: ValueRef
    operator: ComparisonOperator
    value: JSONValue

    def __post_init__(self) -> None:
        if isinstance(self.value, (list, dict)):
            raise ValueError("the first shadow kernel admits immutable scalar literals only")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("rule literals must be finite")

    def to_dict(self) -> JSONObject:
        return {
            "ref": self.ref.to_dict(),
            "operator": self.operator.value,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: JSONObject) -> PredicateClause:
        return cls(
            ref=ValueRef.from_dict(cast(JSONObject, data["ref"])),
            operator=ComparisonOperator(str(data["operator"])),
            value=data.get("value"),
        )


@dataclass(frozen=True, slots=True)
class PredicateSpec:
    all_of: tuple[PredicateClause, ...]

    def __post_init__(self) -> None:
        if not self.all_of:
            raise ValueError("predicate rules require at least one clause")

    def to_dict(self) -> JSONObject:
        return {"all_of": [clause.to_dict() for clause in self.all_of]}

    @classmethod
    def from_dict(cls, data: JSONObject) -> PredicateSpec:
        return cls(
            all_of=tuple(
                PredicateClause.from_dict(cast(JSONObject, item))
                for item in cast(list[JSONValue], data["all_of"])
            )
        )


@dataclass(frozen=True, slots=True)
class ScoringFeature:
    name: str
    condition: PredicateClause
    weight: float

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("scoring feature name must be non-empty")
        if not math.isfinite(self.weight) or self.weight < 0.0 or self.weight > 1.0:
            raise ValueError("scoring feature weight must be between zero and one")

    def to_dict(self) -> JSONObject:
        return {
            "name": self.name,
            "condition": self.condition.to_dict(),
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: JSONObject) -> ScoringFeature:
        return cls(
            name=str(data["name"]),
            condition=PredicateClause.from_dict(cast(JSONObject, data["condition"])),
            weight=float(cast(float, data["weight"])),
        )


@dataclass(frozen=True, slots=True)
class ScoringSpec:
    features: tuple[ScoringFeature, ...]
    bias: float = 0.0

    def __post_init__(self) -> None:
        if not self.features:
            raise ValueError("scoring rules require at least one feature")
        if not math.isfinite(self.bias) or self.bias < 0.0 or self.bias > 1.0:
            raise ValueError("scoring bias must be between zero and one")
        if self.bias + sum(feature.weight for feature in self.features) > 1.000000001:
            raise ValueError("scoring bias and feature weights must sum to at most one")

    def to_dict(self) -> JSONObject:
        return {
            "features": [feature.to_dict() for feature in self.features],
            "bias": self.bias,
        }

    @classmethod
    def from_dict(cls, data: JSONObject) -> ScoringSpec:
        return cls(
            features=tuple(
                ScoringFeature.from_dict(cast(JSONObject, item))
                for item in cast(list[JSONValue], data["features"])
            ),
            bias=float(cast(float, data.get("bias", 0.0))),
        )


@dataclass(frozen=True, slots=True)
class TemporalSpec:
    anchor_event_type: str
    min_elapsed_seconds: float
    reset_event_types: tuple[str, ...] = ()
    current_conditions: tuple[PredicateClause, ...] = ()
    same_subject: bool = True

    def __post_init__(self) -> None:
        if not self.anchor_event_type:
            raise ValueError("temporal anchor event type must be non-empty")
        if not math.isfinite(self.min_elapsed_seconds) or self.min_elapsed_seconds < 0:
            raise ValueError("temporal elapsed duration cannot be negative")

    def to_dict(self) -> JSONObject:
        return {
            "anchor_event_type": self.anchor_event_type,
            "min_elapsed_seconds": self.min_elapsed_seconds,
            "reset_event_types": list(self.reset_event_types),
            "current_conditions": [clause.to_dict() for clause in self.current_conditions],
            "same_subject": self.same_subject,
        }

    @classmethod
    def from_dict(cls, data: JSONObject) -> TemporalSpec:
        return cls(
            anchor_event_type=str(data["anchor_event_type"]),
            min_elapsed_seconds=float(cast(float, data["min_elapsed_seconds"])),
            reset_event_types=tuple(
                str(value) for value in cast(list[JSONValue], data.get("reset_event_types", []))
            ),
            current_conditions=tuple(
                PredicateClause.from_dict(cast(JSONObject, item))
                for item in cast(list[JSONValue], data.get("current_conditions", []))
            ),
            same_subject=bool(data.get("same_subject", True)),
        )


RuleSpec = PredicateSpec | TemporalSpec | ScoringSpec


@dataclass(frozen=True, slots=True)
class SignalTemplate:
    kind: str
    salience: float
    confidence: float = 1.0
    urgency: float = 0.0
    expected_value: float = 0.0
    ttl_seconds: float = 3600.0
    role: SignalRole = SignalRole.EXCITATORY
    inhibits: tuple[str, ...] = ()
    inhibition_mode: InhibitionMode | None = None
    modulation_strength: float | None = None
    suggested_disposition: SalienceDisposition = SalienceDisposition.REMEMBER
    subject: str | None = None

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("signal kind must be non-empty")
        for name, value in (
            ("salience", self.salience),
            ("confidence", self.confidence),
            ("urgency", self.urgency),
        ):
            if not math.isfinite(value) or value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be between zero and one")
        if not math.isfinite(self.expected_value) or self.expected_value < 0.0:
            raise ValueError("expected value cannot be negative")
        if not math.isfinite(self.ttl_seconds) or self.ttl_seconds <= 0.0:
            raise ValueError("signal ttl must be positive")
        self._validate_inhibition()

    def _validate_inhibition(self) -> None:
        if self.role is SignalRole.EXCITATORY:
            if (
                self.inhibits
                or self.inhibition_mode is not None
                or self.modulation_strength is not None
            ):
                raise ValueError("excitatory signals cannot carry inhibition configuration")
            return
        if not self.inhibits or self.inhibition_mode is None:
            raise ValueError("inhibitory signals require targets and an explicit mode")
        if self.inhibition_mode is InhibitionMode.HARD:
            if self.modulation_strength is not None:
                raise ValueError("hard inhibition does not accept a modulation strength")
            return
        strength = self.modulation_strength
        if strength is None or not math.isfinite(strength) or strength <= 0.0 or strength > 1.0:
            raise ValueError("graded modulation strength must be within (0, 1]")

    def to_dict(self) -> JSONObject:
        return {
            "kind": self.kind,
            "salience": self.salience,
            "confidence": self.confidence,
            "urgency": self.urgency,
            "expected_value": self.expected_value,
            "ttl_seconds": self.ttl_seconds,
            "role": self.role.value,
            "inhibits": list(self.inhibits),
            "inhibition_mode": (
                self.inhibition_mode.value if self.inhibition_mode is not None else None
            ),
            "modulation_strength": self.modulation_strength,
            "suggested_disposition": self.suggested_disposition.value,
            "subject": self.subject,
        }

    @classmethod
    def from_dict(cls, data: JSONObject) -> SignalTemplate:
        return cls(
            kind=str(data["kind"]),
            salience=float(cast(float, data["salience"])),
            confidence=float(cast(float, data.get("confidence", 1.0))),
            urgency=float(cast(float, data.get("urgency", 0.0))),
            expected_value=float(cast(float, data.get("expected_value", 0.0))),
            ttl_seconds=float(cast(float, data.get("ttl_seconds", 3600.0))),
            role=SignalRole(str(data.get("role", SignalRole.EXCITATORY.value))),
            inhibits=tuple(str(value) for value in cast(list[JSONValue], data.get("inhibits", []))),
            inhibition_mode=(
                InhibitionMode(str(data["inhibition_mode"]))
                if data.get("inhibition_mode") is not None
                else None
            ),
            modulation_strength=(
                float(cast(float, data["modulation_strength"]))
                if data.get("modulation_strength") is not None
                else None
            ),
            suggested_disposition=SalienceDisposition(
                str(data.get("suggested_disposition", SalienceDisposition.REMEMBER.value))
            ),
            subject=str(data["subject"]) if data.get("subject") is not None else None,
        )


@dataclass(frozen=True, slots=True)
class AutonomicRule:
    rule_id: str
    version: int
    purpose: str
    family: RuleFamily
    trigger: str
    spec: RuleSpec
    output: SignalTemplate
    threshold: float = 1.0
    precedence: int = 0
    intent_text: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.rule_id or not self.purpose or not self.trigger:
            raise ValueError("rule id, purpose, and trigger must be non-empty")
        if self.version <= 0:
            raise ValueError("rule version must be positive")
        if not math.isfinite(self.threshold) or self.threshold < 0.0 or self.threshold > 1.0:
            raise ValueError("rule threshold must be between zero and one")
        expected_type: type[RuleSpec]
        if self.family is RuleFamily.PREDICATE:
            expected_type = PredicateSpec
        elif self.family is RuleFamily.TEMPORAL:
            expected_type = TemporalSpec
        else:
            expected_type = ScoringSpec
        if not isinstance(self.spec, expected_type):
            raise ValueError(f"{self.family.value} rule has the wrong typed specification")

    @property
    def ref(self) -> str:
        return f"{self.rule_id}@{self.version}"

    def to_dict(self) -> JSONObject:
        return {
            "rule_id": self.rule_id,
            "version": self.version,
            "purpose": self.purpose,
            "family": self.family.value,
            "trigger": self.trigger,
            "spec": self.spec.to_dict(),
            "output": self.output.to_dict(),
            "threshold": self.threshold,
            "precedence": self.precedence,
            "intent_text": self.intent_text,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: JSONObject) -> AutonomicRule:
        family = RuleFamily(str(data["family"]))
        spec_data = cast(JSONObject, data["spec"])
        spec_types: dict[RuleFamily, type[PredicateSpec | TemporalSpec | ScoringSpec]] = {
            RuleFamily.PREDICATE: PredicateSpec,
            RuleFamily.TEMPORAL: TemporalSpec,
            RuleFamily.SCORING: ScoringSpec,
        }
        spec = spec_types[family].from_dict(spec_data)
        return cls(
            rule_id=str(data["rule_id"]),
            version=int(cast(int, data["version"])),
            purpose=str(data["purpose"]),
            family=family,
            trigger=str(data["trigger"]),
            spec=spec,
            output=SignalTemplate.from_dict(cast(JSONObject, data["output"])),
            threshold=float(cast(float, data.get("threshold", 1.0))),
            precedence=int(cast(int, data.get("precedence", 0))),
            intent_text=(str(data["intent_text"]) if data.get("intent_text") is not None else None),
            evidence_refs=tuple(
                str(value) for value in cast(list[JSONValue], data.get("evidence_refs", []))
            ),
        )

    def to_event(self, *, source: str, timestamp: datetime, event_id: str | None = None) -> Event:
        payload: JSONObject = {"rule": self.to_dict()}
        return Event(
            type="rule.version_registered",
            source=source,
            subject=self.rule_id,
            payload=payload,
            timestamp=timestamp,
            id=event_id or stable_id("event", payload),
        )


@dataclass(frozen=True, slots=True)
class RulesetSnapshot:
    snapshot_id: str
    digest: str
    rules: tuple[AutonomicRule, ...]

    def __post_init__(self) -> None:
        refs = [rule.ref for rule in self.rules]
        if refs != sorted(refs) or len(refs) != len(set(refs)):
            raise ValueError("ruleset rules must have unique refs in canonical order")
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("a ruleset cannot pin multiple versions of one rule")
        expected = hashlib.sha256(
            canonical_bytes({"rules": [rule.to_dict() for rule in self.rules]})
        ).hexdigest()
        if self.digest != expected:
            raise ValueError("ruleset digest does not match its immutable rule versions")
        if self.snapshot_id != f"ruleset:{expected[:32]}":
            raise ValueError("ruleset identity must be derived from its content digest")

    @property
    def rule_refs(self) -> tuple[str, ...]:
        return tuple(rule.ref for rule in self.rules)

    def to_dict(self, *, include_rules: bool = False) -> JSONObject:
        data: JSONObject = {
            "snapshot_id": self.snapshot_id,
            "digest": self.digest,
            "rule_refs": list(self.rule_refs),
        }
        if include_rules:
            data["rules"] = [rule.to_dict() for rule in self.rules]
        return data

    def to_event(
        self,
        *,
        source: str,
        timestamp: datetime,
        event_id: str | None = None,
    ) -> Event:
        payload = self.to_dict()
        return Event(
            type="rule.ruleset_materialized",
            source=source,
            subject=self.snapshot_id,
            payload=payload,
            timestamp=timestamp,
            id=event_id or stable_id("event", payload),
        )


@dataclass(frozen=True, slots=True)
class EvaluationEpoch:
    epoch_id: str
    ruleset: RulesetSnapshot
    started_at: datetime
    event_log_cursor: int

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("evaluation epoch started_at must be timezone-aware")
        if self.event_log_cursor < 0:
            raise ValueError("evaluation cursor cannot be negative")

    @classmethod
    def open(
        cls,
        ruleset: RulesetSnapshot,
        *,
        started_at: datetime,
        event_log_cursor: int,
        epoch_id: str | None = None,
    ) -> EvaluationEpoch:
        identity: JSONObject = {
            "ruleset_digest": ruleset.digest,
            "started_at": started_at.isoformat(),
            "event_log_cursor": event_log_cursor,
        }
        return cls(
            epoch_id=epoch_id or stable_id("evaluation-epoch", identity),
            ruleset=ruleset,
            started_at=started_at,
            event_log_cursor=event_log_cursor,
        )

    def to_dict(self) -> JSONObject:
        return {
            "epoch_id": self.epoch_id,
            "ruleset_id": self.ruleset.snapshot_id,
            "ruleset_digest": self.ruleset.digest,
            "started_at": self.started_at.isoformat(),
            "event_log_cursor": self.event_log_cursor,
        }

    def to_event(self, *, source: str) -> Event:
        payload = self.to_dict()
        return Event(
            type="rule.evaluation_epoch_started",
            source=source,
            subject=self.epoch_id,
            payload=payload,
            timestamp=self.started_at,
            id=stable_id("event", {"epoch_id": self.epoch_id}),
        )


@dataclass(frozen=True, slots=True)
class Signal:
    signal_id: str
    kind: str
    subject: str
    confidence: float
    salience: float
    urgency: float
    expected_value: float
    valid_from: datetime
    valid_until: datetime
    evidence_event_ids: tuple[str, ...]
    rule_ref: str
    evaluation_epoch_id: str
    precedence: int = 0
    role: SignalRole = SignalRole.EXCITATORY
    inhibits: tuple[str, ...] = ()
    inhibition_mode: InhibitionMode | None = None
    modulation_strength: float | None = None
    suggested_disposition: SalienceDisposition = SalienceDisposition.REMEMBER
    shadow: bool = True

    def __post_init__(self) -> None:
        if self.valid_from.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("signal validity timestamps must be timezone-aware")
        if self.valid_until <= self.valid_from:
            raise ValueError("signal validity window must be positive")
        for name, value in (
            ("confidence", self.confidence),
            ("salience", self.salience),
            ("urgency", self.urgency),
        ):
            if not math.isfinite(value) or value < 0.0 or value > 1.0:
                raise ValueError(f"signal {name} must be between zero and one")
        if not math.isfinite(self.expected_value) or self.expected_value < 0.0:
            raise ValueError("signal expected value cannot be negative")
        if self.role is SignalRole.EXCITATORY:
            if (
                self.inhibits
                or self.inhibition_mode is not None
                or self.modulation_strength is not None
            ):
                raise ValueError("excitatory signals cannot carry inhibition configuration")
        else:
            if not self.inhibits or self.inhibition_mode is None:
                raise ValueError("inhibitory signals require targets and an explicit mode")
            if self.inhibition_mode is InhibitionMode.HARD:
                if self.modulation_strength is not None:
                    raise ValueError("hard inhibition does not accept a modulation strength")
            else:
                strength = self.modulation_strength
                if (
                    strength is None
                    or not math.isfinite(strength)
                    or strength <= 0.0
                    or strength > 1.0
                ):
                    raise ValueError("graded modulation strength must be within (0, 1]")
        if not self.shadow:
            raise ValueError("the shadow kernel cannot create active signals")

    def active_at(self, at: datetime) -> bool:
        return self.valid_from <= at < self.valid_until

    def to_dict(self) -> JSONObject:
        return {
            "signal_id": self.signal_id,
            "kind": self.kind,
            "subject": self.subject,
            "confidence": self.confidence,
            "salience": self.salience,
            "urgency": self.urgency,
            "expected_value": self.expected_value,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "evidence_event_ids": list(self.evidence_event_ids),
            "rule_ref": self.rule_ref,
            "evaluation_epoch_id": self.evaluation_epoch_id,
            "precedence": self.precedence,
            "role": self.role.value,
            "inhibits": list(self.inhibits),
            "inhibition_mode": (
                self.inhibition_mode.value if self.inhibition_mode is not None else None
            ),
            "modulation_strength": self.modulation_strength,
            "suggested_disposition": self.suggested_disposition.value,
            "shadow": self.shadow,
        }

    @classmethod
    def from_dict(cls, data: JSONObject) -> Signal:
        valid_from = parse_datetime(cast(str, data["valid_from"]))
        valid_until = parse_datetime(cast(str, data["valid_until"]))
        if valid_from is None or valid_until is None:
            raise ValueError("signal validity timestamps are required")
        return cls(
            signal_id=str(data["signal_id"]),
            kind=str(data["kind"]),
            subject=str(data["subject"]),
            confidence=float(cast(float, data["confidence"])),
            salience=float(cast(float, data["salience"])),
            urgency=float(cast(float, data["urgency"])),
            expected_value=float(cast(float, data["expected_value"])),
            valid_from=valid_from,
            valid_until=valid_until,
            evidence_event_ids=tuple(
                str(value) for value in cast(list[JSONValue], data["evidence_event_ids"])
            ),
            rule_ref=str(data["rule_ref"]),
            evaluation_epoch_id=str(data["evaluation_epoch_id"]),
            precedence=int(cast(int, data.get("precedence", 0))),
            role=SignalRole(str(data["role"])),
            inhibits=tuple(str(value) for value in cast(list[JSONValue], data["inhibits"])),
            inhibition_mode=(
                InhibitionMode(str(data["inhibition_mode"]))
                if data.get("inhibition_mode") is not None
                else None
            ),
            modulation_strength=(
                float(cast(float, data["modulation_strength"]))
                if data.get("modulation_strength") is not None
                else None
            ),
            suggested_disposition=SalienceDisposition(str(data["suggested_disposition"])),
            shadow=bool(data.get("shadow", True)),
        )


@dataclass(frozen=True, slots=True)
class RuleEvaluationTrace:
    trace_id: str
    rule_id: str
    version: int
    epoch_id: str
    evaluated_at: datetime
    candidate: bool
    activated: bool
    activation_score: float
    threshold: float
    matched_conditions: tuple[str, ...]
    failed_conditions: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    signal_would_emit: Signal | None
    suppressed_by: tuple[str, ...] = ()
    runtime_cost_us: int = 0

    def to_dict(self) -> JSONObject:
        return {
            "trace_id": self.trace_id,
            "rule_id": self.rule_id,
            "version": self.version,
            "epoch_id": self.epoch_id,
            "evaluated_at": self.evaluated_at.isoformat(),
            "candidate": self.candidate,
            "activated": self.activated,
            "activation_score": self.activation_score,
            "threshold": self.threshold,
            "matched_conditions": list(self.matched_conditions),
            "failed_conditions": list(self.failed_conditions),
            "evidence_refs": list(self.evidence_refs),
            "signal_would_emit": (
                self.signal_would_emit.to_dict() if self.signal_would_emit is not None else None
            ),
            "suppressed_by": list(self.suppressed_by),
            "runtime_cost_us": self.runtime_cost_us,
        }

    def semantic_bytes(self) -> bytes:
        semantic = self.to_dict()
        semantic.pop("runtime_cost_us")
        return canonical_bytes(semantic)

    def to_event(self, *, source: str) -> Event:
        payload = self.to_dict()
        return Event(
            type="rule.evaluation_traced",
            source=source,
            subject=f"{self.rule_id}@{self.version}",
            payload=payload,
            timestamp=self.evaluated_at,
            id=stable_id("event", {"trace_id": self.trace_id}),
        )


@dataclass(frozen=True, slots=True)
class SalienceDecision:
    decision_id: str
    subject: str
    disposition: SalienceDisposition
    score: float
    signal_ids: tuple[str, ...]
    evidence_event_ids: tuple[str, ...]
    inhibited_by: tuple[str, ...] = ()
    modulated_by: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    shadow: bool = True

    def __post_init__(self) -> None:
        if not self.shadow:
            raise ValueError("the shadow resolver cannot create active decisions")

    def to_dict(self) -> JSONObject:
        return {
            "decision_id": self.decision_id,
            "subject": self.subject,
            "disposition": self.disposition.value,
            "score": self.score,
            "signal_ids": list(self.signal_ids),
            "evidence_event_ids": list(self.evidence_event_ids),
            "inhibited_by": list(self.inhibited_by),
            "modulated_by": list(self.modulated_by),
            "reasons": list(self.reasons),
            "shadow": self.shadow,
        }

    def to_event(
        self,
        *,
        source: str,
        resolved_at: datetime,
        trigger_event_id: str,
    ) -> Event:
        payload = self.to_dict()
        payload["trigger_event_id"] = trigger_event_id
        return Event(
            type="rule.salience_decision_shadowed",
            source=source,
            subject=self.subject,
            payload=payload,
            timestamp=resolved_at,
            causation_id=trigger_event_id,
            id=stable_id(
                "event",
                {
                    "decision_id": self.decision_id,
                    "trigger_event_id": trigger_event_id,
                },
            ),
        )


def build_signal(
    *,
    rule: AutonomicRule,
    epoch: EvaluationEpoch,
    event: Event,
    activation_score: float,
    evidence_event_ids: tuple[str, ...],
) -> Signal:
    template = rule.output
    subject = template.subject or event.subject or event.id
    identity: JSONObject = {
        "epoch_id": epoch.epoch_id,
        "rule_ref": rule.ref,
        "trigger_event_id": event.id,
        "evidence_event_ids": list(evidence_event_ids),
        "kind": template.kind,
        "subject": subject,
    }
    return Signal(
        signal_id=stable_id("signal", identity),
        kind=template.kind,
        subject=subject,
        confidence=round(template.confidence * activation_score, 12),
        salience=template.salience,
        urgency=template.urgency,
        expected_value=template.expected_value,
        valid_from=event.timestamp,
        valid_until=event.timestamp + timedelta(seconds=template.ttl_seconds),
        evidence_event_ids=evidence_event_ids,
        rule_ref=rule.ref,
        evaluation_epoch_id=epoch.epoch_id,
        precedence=rule.precedence,
        role=template.role,
        inhibits=template.inhibits,
        inhibition_mode=template.inhibition_mode,
        modulation_strength=template.modulation_strength,
        suggested_disposition=template.suggested_disposition,
    )
