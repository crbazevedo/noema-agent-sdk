"""Schema-registry validators for canonical information-governance events."""

from __future__ import annotations

from collections.abc import Callable

from ..events import Event, EventSchemaRegistry
from .models import (
    DECLASSIFICATION_DECIDED_EVENT,
    DECLASSIFIED_VIEW_RECORDED_EVENT,
    DISCLOSURE_DECIDED_EVENT,
    INFORMATION_ACCESS_DECIDED_EVENT,
    INFORMATION_QUARANTINED_EVENT,
    LINEAGE_RECORDED_EVENT,
    POLICY_BOUND_EVENT,
    POLICY_RECORDED_EVENT,
    SECURITY_AUDIT_RECEIPT_EVENT,
    DeclassificationDecision,
    DeclassifiedDisclosureView,
    DisclosureDecision,
    InformationAccessDecision,
    InformationLineage,
    InformationPolicy,
    PolicyBinding,
    QuarantinedInformationRef,
    SecurityAuditReceipt,
)

_VALIDATORS: dict[str, Callable[[Event], object]] = {
    POLICY_RECORDED_EVENT: InformationPolicy.from_event,
    LINEAGE_RECORDED_EVENT: InformationLineage.from_event,
    POLICY_BOUND_EVENT: PolicyBinding.from_event,
    INFORMATION_QUARANTINED_EVENT: QuarantinedInformationRef.from_event,
    INFORMATION_ACCESS_DECIDED_EVENT: InformationAccessDecision.from_event,
    DISCLOSURE_DECIDED_EVENT: DisclosureDecision.from_event,
    DECLASSIFICATION_DECIDED_EVENT: DeclassificationDecision.from_event,
    DECLASSIFIED_VIEW_RECORDED_EVENT: DeclassifiedDisclosureView.from_event,
    SECURITY_AUDIT_RECEIPT_EVENT: SecurityAuditReceipt.from_event,
}


def _validate(event: Event) -> None:
    _VALIDATORS[event.type](event)


def register_information_event_schemas(registry: EventSchemaRegistry) -> None:
    """Make safe construction and immutable identity runtime admission rules."""

    for event_type in _VALIDATORS:
        registry.register(event_type, 1, validator=_validate)
