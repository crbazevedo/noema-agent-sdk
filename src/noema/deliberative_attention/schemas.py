"""Schema-registry validators for deliberative-attention events."""

from __future__ import annotations

from collections.abc import Callable

from ..events import Event, EventSchemaRegistry
from .models import (
    DISPOSITION_FEEDBACK_RECORDED_EVENT,
    DISPOSITION_OUTCOME_LINKED_EVENT,
    DISPOSITION_RECORDED_EVENT,
    FEATURE_SCHEMA_RECORDED_EVENT,
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


def register_deliberative_attention_event_schemas(registry: EventSchemaRegistry) -> None:
    for event_type in _VALIDATORS:
        registry.register(event_type, 1, validator=_validate)
