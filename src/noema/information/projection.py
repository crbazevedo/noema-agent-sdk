"""Canonical replay projection for information policy and material decisions."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from ..events import Event
from ..types import JSONObject
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
from .policy import InformationGovernanceEngine

ValueT = TypeVar("ValueT")


class InformationGovernanceProjection:
    """Rebuild governance state and rerun material decisions from canonical history."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._last_event_id: str | None = None
        self._last_sequence = 0
        self._policies: dict[str, InformationPolicy] = {}
        self._lineages: dict[str, InformationLineage] = {}
        self._bindings: dict[str, PolicyBinding] = {}
        self._quarantines: dict[str, QuarantinedInformationRef] = {}
        self._quarantine_records: dict[str, QuarantinedInformationRef] = {}
        self._access_decisions: dict[str, InformationAccessDecision] = {}
        self._disclosure_decisions: dict[str, DisclosureDecision] = {}
        self._declassification_decisions: dict[str, DeclassificationDecision] = {}
        self._declassified_views: dict[str, DeclassifiedDisclosureView] = {}

    @property
    def event_cursor(self) -> int:
        return self._last_sequence

    @property
    def policies(self) -> tuple[InformationPolicy, ...]:
        return tuple(self._policies[key] for key in sorted(self._policies))

    @property
    def lineages(self) -> tuple[InformationLineage, ...]:
        return tuple(self._lineages[key] for key in sorted(self._lineages))

    @property
    def bindings(self) -> tuple[PolicyBinding, ...]:
        return tuple(self._bindings[key] for key in sorted(self._bindings))

    @property
    def quarantines(self) -> tuple[QuarantinedInformationRef, ...]:
        return tuple(self._quarantines[key] for key in sorted(self._quarantines))

    @property
    def quarantine_records(self) -> tuple[QuarantinedInformationRef, ...]:
        return tuple(
            self._quarantine_records[key] for key in sorted(self._quarantine_records)
        )

    @property
    def access_decisions(self) -> tuple[InformationAccessDecision, ...]:
        return tuple(self._access_decisions[key] for key in sorted(self._access_decisions))

    @property
    def disclosure_decisions(self) -> tuple[DisclosureDecision, ...]:
        return tuple(self._disclosure_decisions[key] for key in sorted(self._disclosure_decisions))

    @property
    def declassification_decisions(self) -> tuple[DeclassificationDecision, ...]:
        return tuple(
            self._declassification_decisions[key]
            for key in sorted(self._declassification_decisions)
        )

    @property
    def declassified_views(self) -> tuple[DeclassifiedDisclosureView, ...]:
        return tuple(
            self._declassified_views[key] for key in sorted(self._declassified_views)
        )

    def policy(self, policy_id: str) -> InformationPolicy | None:
        return self._policies.get(policy_id)

    def lineage(self, information_id: str) -> InformationLineage | None:
        return self._lineages.get(information_id)

    def binding(self, information_id: str) -> PolicyBinding | None:
        return self._bindings.get(information_id)

    def quarantine(self, information_id: str) -> QuarantinedInformationRef | None:
        return self._quarantines.get(information_id)

    def access_decision(self, decision_id: str) -> InformationAccessDecision | None:
        return self._access_decisions.get(decision_id)

    def disclosure_decision(self, decision_id: str) -> DisclosureDecision | None:
        return self._disclosure_decisions.get(decision_id)

    def declassification_decision(
        self, decision_id: str
    ) -> DeclassificationDecision | None:
        return self._declassification_decisions.get(decision_id)

    def declassified_view(
        self, information_id: str
    ) -> DeclassifiedDisclosureView | None:
        return self._declassified_views.get(information_id)

    def apply(self, event: Event) -> bool:
        if event.sequence is None:
            raise ValueError("information governance requires canonical sequenced events")
        if event.sequence <= self._last_sequence:
            if event.sequence == self._last_sequence and event.id == self._last_event_id:
                return False
            raise ValueError("governance events must be applied in canonical order")

        handled = False
        if event.type == POLICY_RECORDED_EVENT:
            policy = InformationPolicy.from_event(event)
            self._put_immutable(self._policies, policy.policy_id, policy, "policy")
            handled = True
        elif event.type == LINEAGE_RECORDED_EVENT:
            lineage = InformationLineage.from_event(event)
            existing_lineage = self._lineages.get(lineage.information_id)
            if existing_lineage is not None and existing_lineage != lineage:
                raise ValueError("information lineage is immutable")
            for source_id in lineage.source_information_ids:
                if source_id not in self._lineages:
                    raise ValueError("derived lineage references an unknown source")
            self._lineages[lineage.information_id] = lineage
            handled = True
        elif event.type == POLICY_BOUND_EVENT:
            binding = PolicyBinding.from_event(event)
            bound_lineage = self._lineages.get(binding.information_id)
            if bound_lineage is None or bound_lineage.lineage_id != binding.lineage_id:
                raise ValueError("policy binding requires its exact canonical lineage")
            if not binding.policy_ids:
                raise ValueError("policy binding requires at least one policy version")
            if any(policy_id not in self._policies for policy_id in binding.policy_ids):
                raise ValueError("policy binding references an unknown policy version")
            existing_binding = self._bindings.get(binding.information_id)
            if existing_binding is not None and existing_binding != binding:
                raise ValueError("policy binding is immutable")
            self._bindings[binding.information_id] = binding
            self._quarantines.pop(binding.information_id, None)
            handled = True
        elif event.type == INFORMATION_QUARANTINED_EVENT:
            quarantine = QuarantinedInformationRef.from_event(event)
            existing_record = self._quarantine_records.get(quarantine.quarantine_id)
            existing_active = self._quarantines.get(quarantine.information_id)
            if existing_record is not None and existing_record != quarantine:
                raise ValueError("conflicting quarantine identity")
            if existing_active is not None and existing_active != quarantine:
                raise ValueError("information already has a different quarantine")
            self._quarantine_records[quarantine.quarantine_id] = quarantine
            self._quarantines[quarantine.information_id] = quarantine
            handled = True
        elif event.type == INFORMATION_ACCESS_DECIDED_EVENT:
            access_decision = InformationAccessDecision.from_event(event)
            self._require_exact_decision_cursor(
                access_decision.causal_event_cursor,
                "access decision",
            )
            expected_access = InformationGovernanceEngine(self).decide_access(
                access_decision.request
            )
            if access_decision != expected_access:
                raise ValueError("access decision differs from deterministic policy evaluation")
            self._put_immutable(
                self._access_decisions,
                access_decision.decision_id,
                access_decision,
                "access decision",
            )
            handled = True
        elif event.type == DISCLOSURE_DECIDED_EVENT:
            disclosure_decision = DisclosureDecision.from_event(event)
            self._require_exact_decision_cursor(
                disclosure_decision.causal_event_cursor,
                "disclosure decision",
            )
            expected_disclosure = InformationGovernanceEngine(self).decide_disclosure(
                disclosure_decision.request
            )
            if disclosure_decision != expected_disclosure:
                raise ValueError("disclosure decision differs from deterministic policy evaluation")
            self._put_immutable(
                self._disclosure_decisions,
                disclosure_decision.decision_id,
                disclosure_decision,
                "disclosure decision",
            )
            handled = True
        elif event.type == DECLASSIFICATION_DECIDED_EVENT:
            declassification_decision = DeclassificationDecision.from_event(event)
            self._require_exact_decision_cursor(
                declassification_decision.causal_event_cursor,
                "declassification decision",
            )
            expected_declassification = InformationGovernanceEngine(self).decide_declassification(
                declassification_decision.request
            )
            if declassification_decision != expected_declassification:
                raise ValueError(
                    "declassification decision differs from deterministic policy evaluation"
                )
            self._put_immutable(
                self._declassification_decisions,
                declassification_decision.decision_id,
                declassification_decision,
                "declassification decision",
            )
            handled = True
        elif event.type == DECLASSIFIED_VIEW_RECORDED_EVENT:
            view = DeclassifiedDisclosureView.from_event(event)
            self._require_exact_decision_cursor(
                view.causal_event_cursor,
                "declassified view",
            )
            decision = self._declassification_decisions.get(
                view.declassification_decision_id
            )
            if decision is None or not decision.allowed:
                raise ValueError(
                    "declassified view requires its canonical allowed decision"
                )
            expected_view = DeclassifiedDisclosureView.create(
                decision=decision,
                created_at=view.created_at,
                causal_event_cursor=self._last_sequence,
            )
            if view != expected_view:
                raise ValueError("declassified view differs from its canonical decision")
            if view.approved_policy_id not in self._policies:
                raise ValueError("declassified view references an unknown approved policy")
            self._put_immutable(
                self._declassified_views,
                view.information_ref.information_id,
                view,
                "declassified view",
            )
            handled = True
        elif event.type == SECURITY_AUDIT_RECEIPT_EVENT:
            # Receipts are valid canonical records, but never authorization state.
            SecurityAuditReceipt.from_event(event)

        self._last_event_id = event.id
        self._last_sequence = event.sequence
        return handled

    def rebuild(self, events: Iterable[Event]) -> None:
        self._reset()
        for event in events:
            self.apply(event)

    def semantic_snapshot(self) -> JSONObject:
        """Stable state digest input used by replay parity tests and recovery."""

        return {
            "event_cursor": self.event_cursor,
            "policies": [value.to_dict() for value in self.policies],
            "lineages": [value.to_dict() for value in self.lineages],
            "bindings": [value.to_dict() for value in self.bindings],
            "quarantines": [value.to_dict() for value in self.quarantines],
            "quarantine_records": [
                value.to_dict() for value in self.quarantine_records
            ],
            "access_decisions": [value.to_dict() for value in self.access_decisions],
            "disclosure_decisions": [value.to_dict() for value in self.disclosure_decisions],
            "declassification_decisions": [
                value.to_dict() for value in self.declassification_decisions
            ],
            "declassified_views": [
                value.to_dict() for value in self.declassified_views
            ],
        }

    @staticmethod
    def _put_immutable(mapping: dict[str, ValueT], key: str, value: ValueT, name: str) -> None:
        existing = mapping.get(key)
        if existing is not None and existing != value:
            raise ValueError(f"conflicting {name} identity: {key}")
        mapping[key] = value

    def _require_exact_decision_cursor(self, cursor: int, name: str) -> None:
        if cursor != self._last_sequence:
            raise ValueError(f"{name} does not cite the exact preceding canonical head")


class SecurityAuditProjection:
    """Bounded audit evidence that is deliberately not authorization state."""

    def __init__(self, *, max_receipts: int = 1024) -> None:
        if max_receipts <= 0:
            raise ValueError("security audit receipt bound must be positive")
        self._max_receipts = max_receipts
        self._reset()

    def _reset(self) -> None:
        self._last_event_id: str | None = None
        self._receipts: dict[str, SecurityAuditReceipt] = {}
        self._receipt_order: list[str] = []
        self._last_sequence = 0

    @property
    def event_cursor(self) -> int:
        return self._last_sequence

    @property
    def receipts(self) -> tuple[SecurityAuditReceipt, ...]:
        return tuple(self._receipts[key] for key in self._receipt_order)

    def apply(self, event: Event) -> bool:
        if event.sequence is None:
            raise ValueError("security audit projection requires canonical events")
        if event.sequence <= self._last_sequence:
            if event.sequence == self._last_sequence and event.id == self._last_event_id:
                return False
            raise ValueError("security audit events must be applied in canonical order")
        handled = False
        if event.type == SECURITY_AUDIT_RECEIPT_EVENT:
            receipt = SecurityAuditReceipt.from_event(event)
            InformationGovernanceProjection._put_immutable(
                self._receipts,
                receipt.receipt_id,
                receipt,
                "audit receipt",
            )
            self._receipt_order.append(receipt.receipt_id)
            if len(self._receipt_order) > self._max_receipts:
                expired_id = self._receipt_order.pop(0)
                self._receipts.pop(expired_id, None)
            handled = True
        self._last_event_id = event.id
        self._last_sequence = event.sequence
        return handled

    def rebuild(self, events: Iterable[Event]) -> None:
        self._reset()
        for event in events:
            self.apply(event)
