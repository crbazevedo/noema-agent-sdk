"""Schema-registry validators for deliberative-attention events."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ..events import Event, EventSchemaRegistry
from .models import (
    DISPOSITION_FEEDBACK_RECORDED_EVENT,
    DISPOSITION_OUTCOME_LINKED_EVENT,
    DISPOSITION_RECORDED_EVENT,
    FEATURE_SCHEMA_RECORDED_EVENT,
    SOURCE_GOVERNANCE_CONTRACT_VERSION_KEY,
    SOURCE_POLICY_RECORDED_EVENT,
    AttentionDispositionFeedbackRecord,
    AttentionDispositionOutcomeLink,
    AttentionDispositionRecord,
    AttentionFeatureSchemaSnapshot,
    AttentionSourcePolicySnapshot,
)

_VALIDATORS: dict[str, Callable[[Event], object]] = {
    SOURCE_POLICY_RECORDED_EVENT: AttentionSourcePolicySnapshot.from_event,
    FEATURE_SCHEMA_RECORDED_EVENT: AttentionFeatureSchemaSnapshot.from_event,
    DISPOSITION_RECORDED_EVENT: AttentionDispositionRecord.from_event,
    DISPOSITION_OUTCOME_LINKED_EVENT: AttentionDispositionOutcomeLink.from_event,
    DISPOSITION_FEEDBACK_RECORDED_EVENT: AttentionDispositionFeedbackRecord.from_event,
}


def _validate(event: Event) -> None:
    _VALIDATORS[event.type](event)


def _upcast_source_policy_v1(event: Event) -> Event:
    payload = dict(event.payload)
    payload["information_id_payload_fields"] = []
    payload[SOURCE_GOVERNANCE_CONTRACT_VERSION_KEY] = 1
    return replace(event, payload=payload, schema_version=2)


def _upcast_disposition_v1(event: Event) -> Event:
    payload = dict(event.payload)
    legacy_access = payload.pop("information_access_decision_ids", [])
    if not isinstance(legacy_access, list):
        raise ValueError("legacy attention access-decision refs must be a list")
    payload["source_information_access_decision_ids"] = []
    payload["derived_information_access_decision_ids"] = legacy_access
    payload[SOURCE_GOVERNANCE_CONTRACT_VERSION_KEY] = 1
    return replace(event, payload=payload, schema_version=2)


def register_deliberative_attention_event_schemas(registry: EventSchemaRegistry) -> None:
    upcasters = {
        SOURCE_POLICY_RECORDED_EVENT: _upcast_source_policy_v1,
        DISPOSITION_RECORDED_EVENT: _upcast_disposition_v1,
    }
    for event_type in _VALIDATORS:
        upcaster = upcasters.get(event_type)
        if upcaster is None:
            registry.register(event_type, 1, validator=_validate)
            continue
        registry.register(event_type, 1, upcast_to_next=upcaster)
        registry.register(event_type, 2, validator=_validate)
