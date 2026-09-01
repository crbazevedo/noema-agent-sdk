"""Schema-v2 migration for the pre-stewardship Goal and Commitment events."""

from __future__ import annotations

from dataclasses import replace

from ..events import Event, EventSchemaRegistry
from ..types import JSONObject, JSONValue

LEGACY_INTENT_KEY = "_intent_v2"

_COMMITMENT_STATE = {
    "open": "accepted",
    "in_progress": "active",
    "completed": "closed",
    "failed": "closed",
    "cancelled": "closed",
}
_COMMITMENT_CLOSURE = {
    "completed": "fulfilled",
    "failed": "failed",
    "cancelled": "cancelled",
}


def _legacy_context(event: Event, operation: str) -> JSONObject:
    return {
        "operation": operation,
        "legacy_event_type": event.type,
        "author": event.source,
        "origin": {
            "provenance_id": f"legacy-origin:{event.id}",
            "kind": "legacy_unverified",
            "principal_id": event.source,
            "authentication_ref": f"legacy-event:{event.id}",
        },
        "intent_authority": {
            "authority_id": f"legacy-authority:{event.id}",
            "principal_id": event.source,
            "scope": "delegated",
            "allowed_goal_kinds": ["legacy_unclassified"],
            "goal_refs": [],
            "provenance_ref": f"legacy-event:{event.id}",
        },
    }


def _upcast_goal_created(event: Event) -> Event:
    payload = dict(event.payload)
    payload.setdefault("id", event.subject or event.id)
    payload.setdefault("priority", 0.5)
    payload.setdefault("utility", 1.0)
    payload.setdefault("status", "active")
    payload.setdefault("success_criteria", [])
    payload.setdefault("owner", event.source)
    payload[LEGACY_INTENT_KEY] = _legacy_context(event, "create")
    return replace(event, payload=payload, schema_version=2)


def _upcast_goal_updated(event: Event) -> Event:
    payload = dict(event.payload)
    payload.setdefault("id", event.subject)
    payload[LEGACY_INTENT_KEY] = _legacy_context(event, "patch")
    return replace(event, payload=payload, schema_version=2)


def _mapped_commitment_payload(event: Event, operation: str) -> JSONObject:
    payload = dict(event.payload)
    payload.setdefault("id", event.subject or event.id)
    raw_status = str(payload.get("status", "open"))
    payload["status"] = _COMMITMENT_STATE.get(raw_status, raw_status)
    closure = _COMMITMENT_CLOSURE.get(raw_status)
    if closure is not None:
        payload["closure_reason"] = closure
    payload[LEGACY_INTENT_KEY] = _legacy_context(event, operation)
    return payload


def _upcast_commitment_created(event: Event) -> Event:
    payload = _mapped_commitment_payload(event, "create")
    payload.setdefault("owner", event.source)
    payload.setdefault("priority", 0.5)
    payload.setdefault("terminal", True)
    payload.setdefault("attention_cost", 1.0)
    payload.setdefault("social_cost_of_failure", 0.0)
    return replace(event, payload=payload, schema_version=2)


def _upcast_commitment_updated(event: Event) -> Event:
    payload = dict(event.payload)
    payload.setdefault("id", event.subject)
    if "status" in payload:
        raw_status = str(payload["status"])
        payload["status"] = _COMMITMENT_STATE.get(raw_status, raw_status)
        closure = _COMMITMENT_CLOSURE.get(raw_status)
        if closure is not None:
            payload["closure_reason"] = closure
    payload[LEGACY_INTENT_KEY] = _legacy_context(event, "patch")
    return replace(event, payload=payload, schema_version=2)


def _upcast_commitment_terminal(event: Event) -> Event:
    suffix = event.type.split(".", 1)[1]
    payload = dict(event.payload)
    payload.setdefault("id", event.subject)
    payload["status"] = "closed"
    payload["closure_reason"] = _COMMITMENT_CLOSURE[suffix]
    payload[LEGACY_INTENT_KEY] = _legacy_context(event, "terminal")
    return replace(event, payload=payload, schema_version=2)


def _validate_legacy_v2(event: Event) -> None:
    metadata = event.payload.get(LEGACY_INTENT_KEY)
    if not isinstance(metadata, dict) or not str(metadata.get("operation", "")).strip():
        raise ValueError(f"{event.type} v2 requires deterministic migration metadata")


def register_intent_event_schemas(registry: EventSchemaRegistry) -> None:
    """Register deterministic legacy migration without rewriting stored history."""

    upcasters = {
        "goal.created": _upcast_goal_created,
        "goal.updated": _upcast_goal_updated,
        "commitment.created": _upcast_commitment_created,
        "commitment.updated": _upcast_commitment_updated,
        "commitment.completed": _upcast_commitment_terminal,
        "commitment.failed": _upcast_commitment_terminal,
        "commitment.cancelled": _upcast_commitment_terminal,
    }
    for event_type, upcaster in upcasters.items():
        registry.register(event_type, 1, upcast_to_next=upcaster)
        registry.register(event_type, 2, validator=_validate_legacy_v2)


def is_legacy_intent_event(event: Event) -> bool:
    return event.schema_version == 2 and LEGACY_INTENT_KEY in event.payload


def legacy_context(event: Event) -> dict[str, JSONValue]:
    value = event.payload.get(LEGACY_INTENT_KEY)
    if not isinstance(value, dict):
        raise ValueError("event does not carry legacy intent migration context")
    return value
