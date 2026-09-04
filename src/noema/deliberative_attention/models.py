"""Canonical learning-grade observations of actual attention decisions.

This module deliberately records decisions made elsewhere.  It does not decide
what deserves attention and contains no habit-mining or effect-plane behavior.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import cast

from ..events import Event
from ..information import Classification, validate_opaque_governance_id
from ..types import JSONObject, JSONScalar, JSONValue, parse_datetime

SOURCE_POLICY_RECORDED_EVENT = "attention.source_policy_recorded"
FEATURE_SCHEMA_RECORDED_EVENT = "attention.feature_schema_recorded"
DISPOSITION_RECORDED_EVENT = "attention.disposition_recorded"
DISPOSITION_OUTCOME_LINKED_EVENT = "attention.disposition_outcome_linked"
DISPOSITION_FEEDBACK_RECORDED_EVENT = "attention.disposition_feedback_recorded"

DELIBERATIVE_ATTENTION_EVENT_TYPES = (
    SOURCE_POLICY_RECORDED_EVENT,
    FEATURE_SCHEMA_RECORDED_EVENT,
    DISPOSITION_RECORDED_EVENT,
    DISPOSITION_OUTCOME_LINKED_EVENT,
    DISPOSITION_FEEDBACK_RECORDED_EVENT,
)


def _content_id(prefix: str, payload: Mapping[str, JSONValue]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:32]}"


def _require_text(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_non_negative(value: int | float | None, name: str) -> None:
    if value is None:
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _unique_text(values: tuple[str, ...], name: str, *, required: bool = False) -> None:
    if required and not values:
        raise ValueError(f"{name} must be non-empty")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} must contain non-empty values")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _strings(data: Mapping[str, object], key: str) -> tuple[str, ...]:
    values = cast(tuple[object, ...] | list[object], data.get(key, ()))
    return tuple(str(value) for value in values)


def _datetime(data: Mapping[str, object], key: str) -> datetime:
    value = parse_datetime(cast(str | datetime | None, data.get(key)))
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _optional_int(data: Mapping[str, object], key: str) -> int | None:
    value = data.get(key)
    return None if value is None else int(cast(int, value))


def _optional_float(data: Mapping[str, object], key: str) -> float | None:
    value = data.get(key)
    return None if value is None else float(cast(float, value))


def _event(
    *,
    event_id: str,
    event_type: str,
    source: str,
    subject: str,
    timestamp: datetime,
    payload: Mapping[str, JSONValue],
    causation_id: str | None = None,
) -> Event:
    return Event(
        id=event_id,
        type=event_type,
        source=source,
        subject=subject,
        timestamp=timestamp,
        payload=payload,
        causation_id=causation_id,
    )


def _validate_envelope(
    event: Event,
    *,
    event_id: str,
    subject: str,
    timestamp: datetime,
    causation_id: str | None = None,
) -> None:
    if (
        event.id != event_id
        or event.subject != subject
        or event.timestamp != timestamp
        or event.causation_id != causation_id
    ):
        raise ValueError("deliberative-attention event envelope is inconsistent")


class AttentionFeatureType(StrEnum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"


class FeatureMissingness(StrEnum):
    REQUIRED_EXPOSURE_INCOMPLETE = "required_exposure_incomplete"
    OPTIONAL_UNKNOWN = "optional_unknown"


class AttentionDisposition(StrEnum):
    WAKE = "wake"
    REMEMBER = "remember"
    DEFER = "defer"
    SUPPRESS = "suppress"


class AttentionOutcome(StrEnum):
    TIMELY_USER_DECISION = "timely_user_decision"
    HANDLED_WITHIN_WINDOW = "handled_within_window"
    MISSED_OPPORTUNITY = "missed_opportunity"
    FALSE_WAKE = "false_wake"
    FALSE_SUPPRESSION = "false_suppression"
    UNKNOWN = "unknown"


class AttentionFeedback(StrEnum):
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    TEMPORARY_OVERRIDE = "temporary_override"
    CONTEXTUAL_EXCEPTION = "contextual_exception"
    PREFERENCE_REVISED = "preference_revised"
    EXPLICITLY_REJECTED = "explicitly_rejected"
    PERMANENT_PROHIBITION = "permanent_prohibition"


class AttentionAuthorityCeiling(StrEnum):
    INTERNAL_ATTENTION_ONLY = "internal_attention_only"


class OutcomeEvidenceClass(StrEnum):
    RESOLVED_POSITIVE = "resolved_positive"
    RESOLVED_NEGATIVE = "resolved_negative"
    CENSORED = "censored"


@dataclass(frozen=True, slots=True)
class AttentionFeatureDefinition:
    name: str
    value_type: AttentionFeatureType
    required: bool
    policy_safe: bool
    missingness: FeatureMissingness
    sensitivity: Classification = Classification.INTERNAL
    allowed_values: tuple[JSONScalar, ...] = ()
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        _require_text(self.name, "attention feature name")
        if self.required != (
            self.missingness is FeatureMissingness.REQUIRED_EXPOSURE_INCOMPLETE
        ):
            raise ValueError("feature required flag and missingness semantics disagree")
        if self.minimum is not None and not math.isfinite(self.minimum):
            raise ValueError("feature minimum must be finite")
        if self.maximum is not None and not math.isfinite(self.maximum):
            raise ValueError("feature maximum must be finite")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("feature minimum cannot exceed maximum")
        if self.value_type not in {AttentionFeatureType.INTEGER, AttentionFeatureType.NUMBER} and (
            self.minimum is not None or self.maximum is not None
        ):
            raise ValueError("only numeric attention features may have bounds")
        if self.value_type is AttentionFeatureType.STRING and not self.allowed_values:
            raise ValueError("policy-safe string features require an explicit enum")
        for value in self.allowed_values:
            self.validate(value)

    def validate(self, value: JSONScalar) -> None:
        if self.value_type is AttentionFeatureType.BOOLEAN:
            valid_type = isinstance(value, bool)
        elif self.value_type is AttentionFeatureType.INTEGER:
            valid_type = isinstance(value, int) and not isinstance(value, bool)
        elif self.value_type is AttentionFeatureType.NUMBER:
            valid_type = isinstance(value, (int, float)) and not isinstance(value, bool)
        else:
            valid_type = isinstance(value, str)
        if not valid_type:
            raise ValueError(f"attention feature {self.name} has the wrong type")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"attention feature {self.name} must be finite")
        if self.allowed_values and value not in self.allowed_values:
            raise ValueError(f"attention feature {self.name} is outside its allowed values")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.minimum is not None and value < self.minimum:
                raise ValueError(f"attention feature {self.name} is below its minimum")
            if self.maximum is not None and value > self.maximum:
                raise ValueError(f"attention feature {self.name} is above its maximum")

    def to_dict(self) -> JSONObject:
        return {
            "name": self.name,
            "value_type": self.value_type.value,
            "required": self.required,
            "policy_safe": self.policy_safe,
            "missingness": self.missingness.value,
            "sensitivity": self.sensitivity.value,
            "allowed_values": list(self.allowed_values),
            "minimum": self.minimum,
            "maximum": self.maximum,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AttentionFeatureDefinition:
        raw_values = cast(tuple[object, ...] | list[object], data.get("allowed_values", ()))
        values: list[JSONScalar] = []
        for value in raw_values:
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError("attention feature enums must contain JSON scalar values")
            values.append(value)
        return cls(
            name=str(data["name"]),
            value_type=AttentionFeatureType(str(data["value_type"])),
            required=bool(data["required"]),
            policy_safe=bool(data["policy_safe"]),
            missingness=FeatureMissingness(str(data["missingness"])),
            sensitivity=Classification(
                str(data.get("sensitivity", Classification.INTERNAL.value))
            ),
            allowed_values=tuple(values),
            minimum=_optional_float(data, "minimum"),
            maximum=_optional_float(data, "maximum"),
        )


@dataclass(frozen=True, slots=True)
class AttentionFeatureSchemaSnapshot:
    schema_id: str
    version: str
    features: tuple[AttentionFeatureDefinition, ...]
    recorded_at: datetime

    @classmethod
    def create(
        cls,
        *,
        version: str,
        features: tuple[AttentionFeatureDefinition, ...],
        recorded_at: datetime,
    ) -> AttentionFeatureSchemaSnapshot:
        normalized = tuple(sorted(features, key=lambda value: value.name))
        identity: JSONObject = {
            "version": version,
            "features": [value.to_dict() for value in normalized],
            "recorded_at": recorded_at.isoformat(),
        }
        return cls(
            schema_id=_content_id("attention-feature-schema", identity),
            version=version,
            features=normalized,
            recorded_at=recorded_at,
        )

    def __post_init__(self) -> None:
        _require_text(self.schema_id, "attention feature schema id")
        _require_text(self.version, "attention feature schema version")
        if not self.features:
            raise ValueError("attention feature schema must define at least one feature")
        names = tuple(value.name for value in self.features)
        if len(set(names)) != len(names):
            raise ValueError("attention feature names must be unique")
        _require_aware(self.recorded_at, "attention feature schema recorded_at")

    def validate_snapshot(self, values: Mapping[str, JSONScalar]) -> bool:
        definitions = {value.name: value for value in self.features}
        unknown = set(values) - set(definitions)
        if unknown:
            raise ValueError(
                f"attention feature snapshot contains unknown fields: {sorted(unknown)}"
            )
        for name, value in values.items():
            definition = definitions[name]
            if not definition.policy_safe:
                raise ValueError(f"attention feature {name} is not policy-safe")
            definition.validate(value)
        return all(
            not definition.required or definition.name in values
            for definition in self.features
        )

    def extract_snapshot(self, payload: Mapping[str, JSONValue]) -> dict[str, JSONScalar]:
        """Extract only declared policy-safe scalars from a source payload."""

        values: dict[str, JSONScalar] = {}
        for definition in self.features:
            if definition.name not in payload:
                continue
            raw = payload[definition.name]
            if raw is not None and not isinstance(raw, (str, int, float, bool)):
                raise ValueError(
                    f"attention feature {definition.name} is not a JSON scalar"
                )
            values[definition.name] = raw
        self.validate_snapshot(values)
        return values

    def to_dict(self) -> JSONObject:
        return {
            "schema_id": self.schema_id,
            "version": self.version,
            "features": [value.to_dict() for value in self.features],
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AttentionFeatureSchemaSnapshot:
        raw_features = cast(tuple[object, ...] | list[object], data["features"])
        value = cls(
            schema_id=str(data["schema_id"]),
            version=str(data["version"]),
            features=tuple(
                AttentionFeatureDefinition.from_dict(cast(Mapping[str, object], item))
                for item in raw_features
            ),
            recorded_at=_datetime(data, "recorded_at"),
        )
        expected = cls.create(
            version=value.version,
            features=value.features,
            recorded_at=value.recorded_at,
        )
        if value != expected:
            raise ValueError("attention feature schema id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"attention-feature-schema-recorded:{self.schema_id}",
            event_type=FEATURE_SCHEMA_RECORDED_EVENT,
            source=source,
            subject=self.schema_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> AttentionFeatureSchemaSnapshot:
        if event.type != FEATURE_SCHEMA_RECORDED_EVENT:
            raise ValueError("event is not an attention feature schema")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"attention-feature-schema-recorded:{value.schema_id}",
            subject=value.schema_id,
            timestamp=value.recorded_at,
        )
        return value


@dataclass(frozen=True, slots=True)
class AttentionSourcePolicySnapshot:
    policy_id: str
    version: str
    feature_schema_id: str
    source_event_types: tuple[str, ...]
    scope: str
    information_id_payload_fields: tuple[str, ...]
    recorded_at: datetime
    source_prefixes: tuple[str, ...] = ()
    subject_prefixes: tuple[str, ...] = ()
    required_payload_fields: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        version: str,
        feature_schema_id: str,
        source_event_types: tuple[str, ...],
        scope: str,
        information_id_payload_fields: tuple[str, ...],
        recorded_at: datetime,
        source_prefixes: tuple[str, ...] = (),
        subject_prefixes: tuple[str, ...] = (),
        required_payload_fields: tuple[str, ...] = (),
    ) -> AttentionSourcePolicySnapshot:
        normalized_event_types = tuple(sorted(set(source_event_types)))
        normalized_source_prefixes = tuple(sorted(set(source_prefixes)))
        normalized_subject_prefixes = tuple(sorted(set(subject_prefixes)))
        normalized_required_fields = tuple(sorted(set(required_payload_fields)))
        normalized_information_fields = tuple(
            sorted(set(information_id_payload_fields))
        )
        identity: JSONObject = {
            "version": version,
            "feature_schema_id": feature_schema_id,
            "source_event_types": list(normalized_event_types),
            "scope": scope,
            "information_id_payload_fields": list(normalized_information_fields),
            "source_prefixes": list(normalized_source_prefixes),
            "subject_prefixes": list(normalized_subject_prefixes),
            "required_payload_fields": list(normalized_required_fields),
            "recorded_at": recorded_at.isoformat(),
        }
        return cls(
            policy_id=_content_id("attention-source-policy", identity),
            version=version,
            feature_schema_id=feature_schema_id,
            source_event_types=normalized_event_types,
            scope=scope,
            information_id_payload_fields=normalized_information_fields,
            recorded_at=recorded_at,
            source_prefixes=normalized_source_prefixes,
            subject_prefixes=normalized_subject_prefixes,
            required_payload_fields=normalized_required_fields,
        )

    def __post_init__(self) -> None:
        _require_text(self.policy_id, "attention source policy id")
        _require_text(self.version, "attention source policy version")
        _require_text(self.feature_schema_id, "attention source policy schema id")
        _require_text(self.scope, "attention source policy scope")
        for values, name, required in (
            (self.source_event_types, "attention source event types", True),
            (self.source_prefixes, "attention source prefixes", False),
            (self.subject_prefixes, "attention subject prefixes", False),
            (self.required_payload_fields, "attention required payload fields", False),
            (
                self.information_id_payload_fields,
                "attention information-id payload fields",
                True,
            ),
        ):
            _unique_text(values, name, required=required)
        if any(
            value.startswith("attention.") or value == "runtime.consumer_checkpoint_advanced"
            for value in self.source_event_types
        ):
            raise ValueError("attention telemetry cannot recursively recognize its own events")
        _require_aware(self.recorded_at, "attention source policy recorded_at")

    def recognizes(self, event: Event, *, activated_at_sequence: int) -> bool:
        if event.sequence is None or event.sequence <= activated_at_sequence:
            return False
        if event.type not in self.source_event_types:
            return False
        if self.source_prefixes and not any(
            event.source.startswith(prefix) for prefix in self.source_prefixes
        ):
            return False
        if self.subject_prefixes and (
            event.subject is None
            or not any(event.subject.startswith(prefix) for prefix in self.subject_prefixes)
        ):
            return False
        return all(
            field in event.payload
            for field in (
                *self.required_payload_fields,
                *self.information_id_payload_fields,
            )
        )

    def extract_governed_information_ids(
        self, payload: Mapping[str, JSONValue]
    ) -> tuple[str, ...]:
        """Extract only the opaque information IDs named by this policy."""

        values: list[str] = []
        for field_name in self.information_id_payload_fields:
            raw = payload.get(field_name)
            if not isinstance(raw, str):
                raise ValueError(
                    f"attention information-id field {field_name} must contain an opaque id"
                )
            validate_opaque_governance_id(raw, "attention governed information id")
            values.append(raw)
        result = tuple(sorted(set(values)))
        if not result:
            raise ValueError("attention source policy yielded no governed information")
        return result

    def to_dict(self) -> JSONObject:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "feature_schema_id": self.feature_schema_id,
            "source_event_types": list(self.source_event_types),
            "scope": self.scope,
            "information_id_payload_fields": list(
                self.information_id_payload_fields
            ),
            "source_prefixes": list(self.source_prefixes),
            "subject_prefixes": list(self.subject_prefixes),
            "required_payload_fields": list(self.required_payload_fields),
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AttentionSourcePolicySnapshot:
        value = cls(
            policy_id=str(data["policy_id"]),
            version=str(data["version"]),
            feature_schema_id=str(data["feature_schema_id"]),
            source_event_types=_strings(data, "source_event_types"),
            scope=str(data["scope"]),
            information_id_payload_fields=_strings(
                data, "information_id_payload_fields"
            ),
            source_prefixes=_strings(data, "source_prefixes"),
            subject_prefixes=_strings(data, "subject_prefixes"),
            required_payload_fields=_strings(data, "required_payload_fields"),
            recorded_at=_datetime(data, "recorded_at"),
        )
        expected = cls.create(
            version=value.version,
            feature_schema_id=value.feature_schema_id,
            source_event_types=value.source_event_types,
            scope=value.scope,
            information_id_payload_fields=value.information_id_payload_fields,
            source_prefixes=value.source_prefixes,
            subject_prefixes=value.subject_prefixes,
            required_payload_fields=value.required_payload_fields,
            recorded_at=value.recorded_at,
        )
        if value != expected:
            raise ValueError("attention source policy id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"attention-source-policy-recorded:{self.policy_id}",
            event_type=SOURCE_POLICY_RECORDED_EVENT,
            source=source,
            subject=self.policy_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> AttentionSourcePolicySnapshot:
        if event.type != SOURCE_POLICY_RECORDED_EVENT:
            raise ValueError("event is not an attention source policy")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"attention-source-policy-recorded:{value.policy_id}",
            subject=value.policy_id,
            timestamp=value.recorded_at,
        )
        return value


@dataclass(frozen=True, slots=True)
class AttentionCostSnapshot:
    model_call_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    wall_time_seconds: float | None = None
    human_attention_units: float | None = None
    deliberative_compute_units: float | None = None
    metric_version: str = "attention-cost-v1"

    def __post_init__(self) -> None:
        _require_text(self.metric_version, "attention cost metric version")
        for value, name in (
            (self.model_call_count, "model call count"),
            (self.input_tokens, "input token count"),
            (self.output_tokens, "output token count"),
            (self.wall_time_seconds, "attention wall time"),
            (self.human_attention_units, "human attention units"),
            (self.deliberative_compute_units, "deliberative compute units"),
        ):
            _require_non_negative(value, name)

    def to_dict(self) -> JSONObject:
        return {
            "model_call_count": self.model_call_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "wall_time_seconds": self.wall_time_seconds,
            "human_attention_units": self.human_attention_units,
            "deliberative_compute_units": self.deliberative_compute_units,
            "metric_version": self.metric_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AttentionCostSnapshot:
        return cls(
            model_call_count=_optional_int(data, "model_call_count"),
            input_tokens=_optional_int(data, "input_tokens"),
            output_tokens=_optional_int(data, "output_tokens"),
            wall_time_seconds=_optional_float(data, "wall_time_seconds"),
            human_attention_units=_optional_float(data, "human_attention_units"),
            deliberative_compute_units=_optional_float(data, "deliberative_compute_units"),
            metric_version=str(data.get("metric_version", "attention-cost-v1")),
        )


@dataclass(frozen=True, slots=True)
class AttentionDispositionDecision:
    disposition: AttentionDisposition
    features: Mapping[str, JSONScalar]
    situation_causal_cursor: int
    decision_mechanism_id: str
    decision_mechanism_version: str
    decision_configuration_ref: str
    decision_refs: tuple[str, ...]
    governing_intent_refs: tuple[str, ...]
    authority_ceiling: AttentionAuthorityCeiling
    governed_information_ids: tuple[str, ...]
    valid_at: datetime
    known_at: datetime
    decided_at: datetime
    costs: AttentionCostSnapshot = field(default_factory=AttentionCostSnapshot)

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", dict(self.features))
        if self.situation_causal_cursor <= 0:
            raise ValueError("attention decision requires a positive situation cursor")
        for value, name in (
            (self.decision_mechanism_id, "attention decision mechanism id"),
            (self.decision_mechanism_version, "attention decision mechanism version"),
            (self.decision_configuration_ref, "attention decision configuration ref"),
        ):
            _require_text(value, name)
        _unique_text(self.decision_refs, "attention decision refs")
        _unique_text(self.governing_intent_refs, "attention governing intent refs", required=True)
        _unique_text(
            self.governed_information_ids,
            "attention governed information ids",
            required=True,
        )
        for value in self.governed_information_ids:
            validate_opaque_governance_id(value, "attention governed information id")
        for timestamp, timestamp_name in (
            (self.valid_at, "attention valid_at"),
            (self.known_at, "attention known_at"),
            (self.decided_at, "attention decided_at"),
        ):
            _require_aware(timestamp, timestamp_name)
        if self.valid_at > self.known_at or self.known_at > self.decided_at:
            raise ValueError(
                "attention decision times must satisfy valid_at <= known_at <= decided_at"
            )
        for feature_name, feature_value in self.features.items():
            _require_text(feature_name, "attention feature name")
            if feature_value is not None and not isinstance(
                feature_value, (str, int, float, bool)
            ):
                raise ValueError("attention feature snapshot may contain only JSON scalar values")
            if isinstance(feature_value, float) and not math.isfinite(feature_value):
                raise ValueError("attention feature values must be finite")

    def to_dict(self) -> JSONObject:
        return {
            "disposition": self.disposition.value,
            "features": dict(self.features),
            "situation_causal_cursor": self.situation_causal_cursor,
            "decision_mechanism_id": self.decision_mechanism_id,
            "decision_mechanism_version": self.decision_mechanism_version,
            "decision_configuration_ref": self.decision_configuration_ref,
            "decision_refs": list(self.decision_refs),
            "governing_intent_refs": list(self.governing_intent_refs),
            "authority_ceiling": self.authority_ceiling.value,
            "governed_information_ids": list(self.governed_information_ids),
            "valid_at": self.valid_at.isoformat(),
            "known_at": self.known_at.isoformat(),
            "decided_at": self.decided_at.isoformat(),
            "costs": self.costs.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AttentionDispositionDecision:
        raw_features = cast(Mapping[str, object], data["features"])
        features: dict[str, JSONScalar] = {}
        for key, value in raw_features.items():
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError("attention feature snapshot may contain only JSON scalar values")
            features[str(key)] = value
        return cls(
            disposition=AttentionDisposition(str(data["disposition"])),
            features=features,
            situation_causal_cursor=int(cast(int, data["situation_causal_cursor"])),
            decision_mechanism_id=str(data["decision_mechanism_id"]),
            decision_mechanism_version=str(data["decision_mechanism_version"]),
            decision_configuration_ref=str(data["decision_configuration_ref"]),
            decision_refs=_strings(data, "decision_refs"),
            governing_intent_refs=_strings(data, "governing_intent_refs"),
            authority_ceiling=AttentionAuthorityCeiling(str(data["authority_ceiling"])),
            governed_information_ids=_strings(data, "governed_information_ids"),
            valid_at=_datetime(data, "valid_at"),
            known_at=_datetime(data, "known_at"),
            decided_at=_datetime(data, "decided_at"),
            costs=AttentionCostSnapshot.from_dict(
                cast(Mapping[str, object], data.get("costs", {}))
            ),
        )


@dataclass(frozen=True, slots=True)
class AttentionDispositionRecord:
    disposition_id: str
    source_event_id: str
    source_event_sequence: int
    source_policy_id: str
    feature_schema_id: str
    decision: AttentionDispositionDecision
    derived_information_id: str
    information_policy_ids: tuple[str, ...]
    source_information_access_decision_ids: tuple[str, ...]
    derived_information_access_decision_ids: tuple[str, ...]
    admitted_predecessor_head: int

    @classmethod
    def create(
        cls,
        *,
        source_event_id: str,
        source_event_sequence: int,
        source_policy_id: str,
        feature_schema_id: str,
        decision: AttentionDispositionDecision,
        derived_information_id: str,
        information_policy_ids: tuple[str, ...],
        source_information_access_decision_ids: tuple[str, ...],
        derived_information_access_decision_ids: tuple[str, ...],
        admitted_predecessor_head: int,
    ) -> AttentionDispositionRecord:
        identity: JSONObject = {
            "source_event_id": source_event_id,
            "source_policy_id": source_policy_id,
            "feature_schema_id": feature_schema_id,
        }
        return cls(
            disposition_id=_content_id("attention-disposition", identity),
            source_event_id=source_event_id,
            source_event_sequence=source_event_sequence,
            source_policy_id=source_policy_id,
            feature_schema_id=feature_schema_id,
            decision=decision,
            derived_information_id=derived_information_id,
            information_policy_ids=tuple(sorted(set(information_policy_ids))),
            source_information_access_decision_ids=tuple(
                sorted(set(source_information_access_decision_ids))
            ),
            derived_information_access_decision_ids=tuple(
                sorted(set(derived_information_access_decision_ids))
            ),
            admitted_predecessor_head=admitted_predecessor_head,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.disposition_id, "attention disposition id"),
            (self.source_event_id, "attention source event id"),
            (self.source_policy_id, "attention source policy id"),
            (self.feature_schema_id, "attention feature schema id"),
        ):
            _require_text(value, name)
        if self.source_event_sequence <= 0:
            raise ValueError("attention disposition source sequence must be positive")
        if self.admitted_predecessor_head < self.source_event_sequence:
            raise ValueError("attention disposition cannot precede its source event")
        if self.decision.situation_causal_cursor < self.source_event_sequence:
            raise ValueError("attention situation cut cannot precede its source event")
        if self.decision.situation_causal_cursor > self.admitted_predecessor_head:
            raise ValueError("attention situation cut cannot follow its admitted head")
        validate_opaque_governance_id(
            self.derived_information_id, "attention derived information id"
        )
        _unique_text(self.information_policy_ids, "attention information policy ids", required=True)
        _unique_text(
            self.source_information_access_decision_ids,
            "attention source access decision ids",
            required=True,
        )
        _unique_text(
            self.derived_information_access_decision_ids,
            "attention derived access decision ids",
            required=True,
        )
        for value in (
            *self.information_policy_ids,
            *self.source_information_access_decision_ids,
            *self.derived_information_access_decision_ids,
        ):
            validate_opaque_governance_id(value, "attention governance reference")

    def to_dict(self) -> JSONObject:
        return {
            "disposition_id": self.disposition_id,
            "source_event_id": self.source_event_id,
            "source_event_sequence": self.source_event_sequence,
            "source_policy_id": self.source_policy_id,
            "feature_schema_id": self.feature_schema_id,
            "decision": self.decision.to_dict(),
            "derived_information_id": self.derived_information_id,
            "information_policy_ids": list(self.information_policy_ids),
            "source_information_access_decision_ids": list(
                self.source_information_access_decision_ids
            ),
            "derived_information_access_decision_ids": list(
                self.derived_information_access_decision_ids
            ),
            "admitted_predecessor_head": self.admitted_predecessor_head,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AttentionDispositionRecord:
        value = cls(
            disposition_id=str(data["disposition_id"]),
            source_event_id=str(data["source_event_id"]),
            source_event_sequence=int(cast(int, data["source_event_sequence"])),
            source_policy_id=str(data["source_policy_id"]),
            feature_schema_id=str(data["feature_schema_id"]),
            decision=AttentionDispositionDecision.from_dict(
                cast(Mapping[str, object], data["decision"])
            ),
            derived_information_id=str(data["derived_information_id"]),
            information_policy_ids=_strings(data, "information_policy_ids"),
            source_information_access_decision_ids=_strings(
                data, "source_information_access_decision_ids"
            ),
            derived_information_access_decision_ids=_strings(
                data, "derived_information_access_decision_ids"
            ),
            admitted_predecessor_head=int(cast(int, data["admitted_predecessor_head"])),
        )
        expected = cls.create(
            source_event_id=value.source_event_id,
            source_event_sequence=value.source_event_sequence,
            source_policy_id=value.source_policy_id,
            feature_schema_id=value.feature_schema_id,
            decision=value.decision,
            derived_information_id=value.derived_information_id,
            information_policy_ids=value.information_policy_ids,
            source_information_access_decision_ids=(
                value.source_information_access_decision_ids
            ),
            derived_information_access_decision_ids=(
                value.derived_information_access_decision_ids
            ),
            admitted_predecessor_head=value.admitted_predecessor_head,
        )
        if value != expected:
            raise ValueError("attention disposition id does not match its opportunity")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"attention-disposition-recorded:{self.disposition_id}",
            event_type=DISPOSITION_RECORDED_EVENT,
            source=source,
            subject=self.disposition_id,
            timestamp=self.decision.decided_at,
            payload=self.to_dict(),
            causation_id=self.source_event_id,
        )

    @classmethod
    def from_event(cls, event: Event) -> AttentionDispositionRecord:
        if event.type != DISPOSITION_RECORDED_EVENT:
            raise ValueError("event is not an attention disposition")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"attention-disposition-recorded:{value.disposition_id}",
            subject=value.disposition_id,
            timestamp=value.decision.decided_at,
            causation_id=value.source_event_id,
        )
        return value


@dataclass(frozen=True, slots=True)
class AttentionDispositionOutcomeLink:
    link_id: str
    disposition_id: str
    outcome_event_id: str
    outcome: AttentionOutcome
    observed_at: datetime
    recorded_at: datetime
    governed_information_ids: tuple[str, ...]
    derived_information_id: str
    information_policy_ids: tuple[str, ...]
    information_access_decision_ids: tuple[str, ...]
    admitted_predecessor_head: int

    @classmethod
    def create(
        cls,
        *,
        disposition_id: str,
        outcome_event_id: str,
        outcome: AttentionOutcome,
        observed_at: datetime,
        recorded_at: datetime,
        governed_information_ids: tuple[str, ...],
        derived_information_id: str,
        information_policy_ids: tuple[str, ...],
        information_access_decision_ids: tuple[str, ...],
        admitted_predecessor_head: int,
    ) -> AttentionDispositionOutcomeLink:
        return cls(
            link_id=_content_id(
                "attention-outcome-link", {"disposition_id": disposition_id}
            ),
            disposition_id=disposition_id,
            outcome_event_id=outcome_event_id,
            outcome=outcome,
            observed_at=observed_at,
            recorded_at=recorded_at,
            governed_information_ids=tuple(sorted(set(governed_information_ids))),
            derived_information_id=derived_information_id,
            information_policy_ids=tuple(sorted(set(information_policy_ids))),
            information_access_decision_ids=tuple(
                sorted(set(information_access_decision_ids))
            ),
            admitted_predecessor_head=admitted_predecessor_head,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.link_id, "attention outcome link id"),
            (self.disposition_id, "attention outcome disposition id"),
            (self.outcome_event_id, "attention outcome event id"),
        ):
            _require_text(value, name)
        _require_aware(self.observed_at, "attention outcome observed_at")
        _require_aware(self.recorded_at, "attention outcome recorded_at")
        if self.observed_at > self.recorded_at:
            raise ValueError("attention outcome cannot be recorded before observation")
        if self.admitted_predecessor_head <= 0:
            raise ValueError("attention outcome requires a positive admitted head")
        _validate_governance_refs(self)

    @property
    def evidence_class(self) -> OutcomeEvidenceClass:
        if self.outcome in {
            AttentionOutcome.TIMELY_USER_DECISION,
            AttentionOutcome.HANDLED_WITHIN_WINDOW,
        }:
            return OutcomeEvidenceClass.RESOLVED_POSITIVE
        if self.outcome in {
            AttentionOutcome.MISSED_OPPORTUNITY,
            AttentionOutcome.FALSE_WAKE,
            AttentionOutcome.FALSE_SUPPRESSION,
        }:
            return OutcomeEvidenceClass.RESOLVED_NEGATIVE
        return OutcomeEvidenceClass.CENSORED

    def to_dict(self) -> JSONObject:
        return {
            "link_id": self.link_id,
            "disposition_id": self.disposition_id,
            "outcome_event_id": self.outcome_event_id,
            "outcome": self.outcome.value,
            "observed_at": self.observed_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
            "governed_information_ids": list(self.governed_information_ids),
            "derived_information_id": self.derived_information_id,
            "information_policy_ids": list(self.information_policy_ids),
            "information_access_decision_ids": list(self.information_access_decision_ids),
            "admitted_predecessor_head": self.admitted_predecessor_head,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AttentionDispositionOutcomeLink:
        value = cls(
            link_id=str(data["link_id"]),
            disposition_id=str(data["disposition_id"]),
            outcome_event_id=str(data["outcome_event_id"]),
            outcome=AttentionOutcome(str(data["outcome"])),
            observed_at=_datetime(data, "observed_at"),
            recorded_at=_datetime(data, "recorded_at"),
            governed_information_ids=_strings(data, "governed_information_ids"),
            derived_information_id=str(data["derived_information_id"]),
            information_policy_ids=_strings(data, "information_policy_ids"),
            information_access_decision_ids=_strings(
                data, "information_access_decision_ids"
            ),
            admitted_predecessor_head=int(cast(int, data["admitted_predecessor_head"])),
        )
        expected = cls.create(
            disposition_id=value.disposition_id,
            outcome_event_id=value.outcome_event_id,
            outcome=value.outcome,
            observed_at=value.observed_at,
            recorded_at=value.recorded_at,
            governed_information_ids=value.governed_information_ids,
            derived_information_id=value.derived_information_id,
            information_policy_ids=value.information_policy_ids,
            information_access_decision_ids=value.information_access_decision_ids,
            admitted_predecessor_head=value.admitted_predecessor_head,
        )
        if value != expected:
            raise ValueError("attention outcome link id does not match its disposition")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"attention-disposition-outcome-linked:{self.link_id}",
            event_type=DISPOSITION_OUTCOME_LINKED_EVENT,
            source=source,
            subject=self.disposition_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
            causation_id=self.outcome_event_id,
        )

    @classmethod
    def from_event(cls, event: Event) -> AttentionDispositionOutcomeLink:
        if event.type != DISPOSITION_OUTCOME_LINKED_EVENT:
            raise ValueError("event is not an attention outcome link")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"attention-disposition-outcome-linked:{value.link_id}",
            subject=value.disposition_id,
            timestamp=value.recorded_at,
            causation_id=value.outcome_event_id,
        )
        return value


@dataclass(frozen=True, slots=True)
class AttentionDispositionFeedbackRecord:
    feedback_id: str
    disposition_id: str
    feedback_event_id: str
    feedback: AttentionFeedback
    actor_id: str
    actor_provenance_ref: str
    recorded_at: datetime
    governed_information_ids: tuple[str, ...]
    derived_information_id: str
    information_policy_ids: tuple[str, ...]
    information_access_decision_ids: tuple[str, ...]
    admitted_predecessor_head: int

    @classmethod
    def create(
        cls,
        *,
        disposition_id: str,
        feedback_event_id: str,
        feedback: AttentionFeedback,
        actor_id: str,
        actor_provenance_ref: str,
        recorded_at: datetime,
        governed_information_ids: tuple[str, ...],
        derived_information_id: str,
        information_policy_ids: tuple[str, ...],
        information_access_decision_ids: tuple[str, ...],
        admitted_predecessor_head: int,
    ) -> AttentionDispositionFeedbackRecord:
        identity: JSONObject = {
            "disposition_id": disposition_id,
            "feedback_event_id": feedback_event_id,
            "feedback": feedback.value,
            "actor_id": actor_id,
            "actor_provenance_ref": actor_provenance_ref,
        }
        return cls(
            feedback_id=_content_id("attention-feedback", identity),
            disposition_id=disposition_id,
            feedback_event_id=feedback_event_id,
            feedback=feedback,
            actor_id=actor_id,
            actor_provenance_ref=actor_provenance_ref,
            recorded_at=recorded_at,
            governed_information_ids=tuple(sorted(set(governed_information_ids))),
            derived_information_id=derived_information_id,
            information_policy_ids=tuple(sorted(set(information_policy_ids))),
            information_access_decision_ids=tuple(
                sorted(set(information_access_decision_ids))
            ),
            admitted_predecessor_head=admitted_predecessor_head,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.feedback_id, "attention feedback id"),
            (self.disposition_id, "attention feedback disposition id"),
            (self.feedback_event_id, "attention feedback event id"),
            (self.actor_id, "attention feedback actor id"),
            (self.actor_provenance_ref, "attention feedback actor provenance"),
        ):
            _require_text(value, name)
        _require_aware(self.recorded_at, "attention feedback recorded_at")
        if self.admitted_predecessor_head <= 0:
            raise ValueError("attention feedback requires a positive admitted head")
        _validate_governance_refs(self)

    def to_dict(self) -> JSONObject:
        return {
            "feedback_id": self.feedback_id,
            "disposition_id": self.disposition_id,
            "feedback_event_id": self.feedback_event_id,
            "feedback": self.feedback.value,
            "actor_id": self.actor_id,
            "actor_provenance_ref": self.actor_provenance_ref,
            "recorded_at": self.recorded_at.isoformat(),
            "governed_information_ids": list(self.governed_information_ids),
            "derived_information_id": self.derived_information_id,
            "information_policy_ids": list(self.information_policy_ids),
            "information_access_decision_ids": list(self.information_access_decision_ids),
            "admitted_predecessor_head": self.admitted_predecessor_head,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AttentionDispositionFeedbackRecord:
        value = cls(
            feedback_id=str(data["feedback_id"]),
            disposition_id=str(data["disposition_id"]),
            feedback_event_id=str(data["feedback_event_id"]),
            feedback=AttentionFeedback(str(data["feedback"])),
            actor_id=str(data["actor_id"]),
            actor_provenance_ref=str(data["actor_provenance_ref"]),
            recorded_at=_datetime(data, "recorded_at"),
            governed_information_ids=_strings(data, "governed_information_ids"),
            derived_information_id=str(data["derived_information_id"]),
            information_policy_ids=_strings(data, "information_policy_ids"),
            information_access_decision_ids=_strings(
                data, "information_access_decision_ids"
            ),
            admitted_predecessor_head=int(cast(int, data["admitted_predecessor_head"])),
        )
        expected = cls.create(
            disposition_id=value.disposition_id,
            feedback_event_id=value.feedback_event_id,
            feedback=value.feedback,
            actor_id=value.actor_id,
            actor_provenance_ref=value.actor_provenance_ref,
            recorded_at=value.recorded_at,
            governed_information_ids=value.governed_information_ids,
            derived_information_id=value.derived_information_id,
            information_policy_ids=value.information_policy_ids,
            information_access_decision_ids=value.information_access_decision_ids,
            admitted_predecessor_head=value.admitted_predecessor_head,
        )
        if value != expected:
            raise ValueError("attention feedback id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"attention-disposition-feedback-recorded:{self.feedback_id}",
            event_type=DISPOSITION_FEEDBACK_RECORDED_EVENT,
            source=source,
            subject=self.disposition_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
            causation_id=self.feedback_event_id,
        )

    @classmethod
    def from_event(cls, event: Event) -> AttentionDispositionFeedbackRecord:
        if event.type != DISPOSITION_FEEDBACK_RECORDED_EVENT:
            raise ValueError("event is not an attention feedback record")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"attention-disposition-feedback-recorded:{value.feedback_id}",
            subject=value.disposition_id,
            timestamp=value.recorded_at,
            causation_id=value.feedback_event_id,
        )
        return value


def _validate_governance_refs(
    value: AttentionDispositionOutcomeLink | AttentionDispositionFeedbackRecord,
) -> None:
    _unique_text(
        value.governed_information_ids,
        "attention linked governed information ids",
        required=True,
    )
    _unique_text(
        value.information_policy_ids,
        "attention linked information policy ids",
        required=True,
    )
    _unique_text(
        value.information_access_decision_ids,
        "attention linked access decision ids",
        required=True,
    )
    for reference in (
        *value.governed_information_ids,
        value.derived_information_id,
        *value.information_policy_ids,
        *value.information_access_decision_ids,
    ):
        validate_opaque_governance_id(reference, "attention linked governance reference")


@dataclass(frozen=True, slots=True)
class RecognizedAttentionOpportunity:
    source_event_id: str
    source_event_sequence: int
    source_policy_id: str
    feature_schema_id: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source_event_id, self.source_policy_id, self.feature_schema_id)


@dataclass(frozen=True, slots=True)
class AttentionDenominatorAudit:
    source_policy_id: str
    feature_schema_id: str
    start_sequence: int
    end_sequence: int
    recognized_opportunities: tuple[RecognizedAttentionOpportunity, ...]
    disposition_records: tuple[AttentionDispositionRecord, ...]
    missing_dispositions: tuple[RecognizedAttentionOpportunity, ...]
    duplicate_disposition_keys: tuple[tuple[str, str, str], ...]
    feature_complete_ids: tuple[str, ...]
    feature_incomplete_ids: tuple[str, ...]
    outcome_resolved_ids: tuple[str, ...]
    outcome_censored_ids: tuple[str, ...]
    feedback_observed_ids: tuple[str, ...]

    @property
    def denominator_complete(self) -> bool:
        return bool(self.recognized_opportunities) and not (
            self.missing_dispositions or self.duplicate_disposition_keys
        )
