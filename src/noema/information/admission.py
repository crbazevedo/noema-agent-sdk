"""Exact-head admission for material information-governance state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Generic, TypeVar

from ..events import Event
from ..kernel import NoemaKernel
from .models import (
    AccessContext,
    DecisionDisposition,
    DeclassificationDecision,
    DeclassificationRequest,
    DeclassifiedDisclosureView,
    DisclosureDecision,
    DisclosureRequest,
    GovernedInformationRef,
    InformationAccessDecision,
    InformationAccessRequest,
    SecurityAuditReceipt,
)
from .policy import InformationGovernanceEngine
from .projection import InformationGovernanceProjection

RecordT = TypeVar(
    "RecordT",
    InformationAccessDecision,
    DisclosureDecision,
    DeclassificationDecision,
    DeclassifiedDisclosureView,
)


class StaleGovernanceDecisionError(RuntimeError):
    """The current canonical policy no longer yields the expected outcome."""


@dataclass(frozen=True, slots=True)
class GovernanceAdmissionReceipt(Generic[RecordT]):
    """Proof that a governance record immediately followed its evaluated head."""

    record: RecordT
    canonical_event: Event

    def __post_init__(self) -> None:
        if self.canonical_event.sequence is None:
            raise ValueError("governance admission receipt requires a canonical event")
        expected_event = self.record.to_event(source=self.canonical_event.source)
        if replace(self.canonical_event, sequence=None) != expected_event:
            raise ValueError("governance admission receipt event differs from its record")
        if self.canonical_event.sequence != self.record.causal_event_cursor + 1:
            raise ValueError("governance admission receipt is not exact-head evidence")

    @property
    def canonical_sequence(self) -> int:
        sequence = self.canonical_event.sequence
        if sequence is None:  # pragma: no cover - guarded by construction
            raise AssertionError("canonical governance event lost its sequence")
        return sequence


@dataclass(frozen=True, slots=True)
class DeclassificationAdmission:
    decision: GovernanceAdmissionReceipt[DeclassificationDecision]
    view: GovernanceAdmissionReceipt[DeclassifiedDisclosureView] | None


class InformationGovernanceAdmission:
    """Re-evaluate material decisions and append them with canonical-head CAS."""

    def __init__(
        self,
        kernel: NoemaKernel,
        projection: InformationGovernanceProjection,
        *,
        source: str = "information:governance",
    ) -> None:
        if not source.strip():
            raise ValueError("governance admission source must be non-empty")
        self._kernel = kernel
        self._projection = projection
        self._source = source

    async def admit_access(
        self,
        request: InformationAccessRequest,
        *,
        expected_disposition: DecisionDisposition | None = None,
        expected_causal_cursor: int | None = None,
    ) -> GovernanceAdmissionReceipt[InformationAccessDecision]:
        await self._reload()
        self._require_causal_cursor(expected_causal_cursor)
        engine = InformationGovernanceEngine(self._projection)
        refreshed = InformationAccessRequest.create(
            information_ref=request.information_ref,
            context=self._refresh_context(engine, request.context, request.information_ref),
        )
        decision = engine.decide_access(refreshed)
        self._require_disposition(decision.policy_decision.disposition, expected_disposition)
        event = decision.to_event(source=self._source)
        stored = await self._emit_if_head(event, decision.causal_event_cursor)
        self._projection.apply(stored)
        return GovernanceAdmissionReceipt(decision, stored)

    async def admit_disclosure(
        self,
        request: DisclosureRequest,
        *,
        expected_disposition: DecisionDisposition | None = None,
        expected_causal_cursor: int | None = None,
    ) -> GovernanceAdmissionReceipt[DisclosureDecision]:
        await self._reload()
        self._require_causal_cursor(expected_causal_cursor)
        engine = InformationGovernanceEngine(self._projection)
        refreshed = DisclosureRequest.create(
            information_ref=request.information_ref,
            context=self._refresh_context(engine, request.context, request.information_ref),
        )
        decision = engine.decide_disclosure(refreshed)
        self._require_disposition(decision.policy_decision.disposition, expected_disposition)
        event = decision.to_event(source=self._source)
        stored = await self._emit_if_head(event, decision.causal_event_cursor)
        self._projection.apply(stored)
        return GovernanceAdmissionReceipt(decision, stored)

    async def admit_declassification(
        self,
        request: DeclassificationRequest,
        *,
        expected_disposition: DecisionDisposition | None = None,
        expected_causal_cursor: int | None = None,
    ) -> GovernanceAdmissionReceipt[DeclassificationDecision]:
        await self._reload()
        self._require_causal_cursor(expected_causal_cursor)
        engine = InformationGovernanceEngine(self._projection)
        refreshed = DeclassificationRequest.create(
            information_ref=request.information_ref,
            proposed_policy_id=request.proposed_policy_id,
            context=self._refresh_context(engine, request.context, request.information_ref),
        )
        decision = engine.decide_declassification(refreshed)
        self._require_disposition(decision.policy_decision.disposition, expected_disposition)
        event = decision.to_event(source=self._source)
        stored = await self._emit_if_head(event, decision.causal_event_cursor)
        self._projection.apply(stored)
        return GovernanceAdmissionReceipt(decision, stored)

    async def declassify(
        self,
        request: DeclassificationRequest,
        *,
        created_at: datetime,
    ) -> DeclassificationAdmission:
        decision_receipt = await self.admit_declassification(request)
        if not decision_receipt.record.allowed:
            return DeclassificationAdmission(decision_receipt, None)
        view_receipt = await self.admit_declassified_view(
            decision_receipt.record.decision_id,
            created_at=created_at,
        )
        return DeclassificationAdmission(decision_receipt, view_receipt)

    async def admit_declassified_view(
        self,
        decision_id: str,
        *,
        created_at: datetime,
    ) -> GovernanceAdmissionReceipt[DeclassifiedDisclosureView]:
        await self._reload()
        decision = self._projection.declassification_decision(decision_id)
        if decision is None or not decision.allowed:
            raise ValueError("declassified view requires a canonical allowed decision")
        view = DeclassifiedDisclosureView.create(
            decision=decision,
            created_at=created_at,
            causal_event_cursor=self._projection.event_cursor,
        )
        stored = await self._emit_if_head(
            view.to_event(source=self._source),
            view.causal_event_cursor,
        )
        self._projection.apply(stored)
        return GovernanceAdmissionReceipt(view, stored)

    async def record_audit_receipt(
        self,
        decision: InformationAccessDecision | DisclosureDecision,
    ) -> SecurityAuditReceipt:
        """Record non-authorizing sampled evidence without persisting the decision."""

        receipt = SecurityAuditReceipt.from_decision(decision)
        stored = await self._kernel.emit(receipt.to_event(source=self._source))
        if replace(stored, sequence=None) != receipt.to_event(source=self._source):
            raise ValueError(f"canonical event id conflict: {stored.id}")
        return receipt

    async def _reload(self) -> None:
        self._projection.rebuild(await self._kernel.history())

    async def _emit_if_head(self, event: Event, causal_cursor: int) -> Event:
        stored = await self._kernel.emit_if_head(
            event,
            expected_head_sequence=causal_cursor,
        )
        if replace(stored, sequence=None) != event:
            raise ValueError(f"canonical event id conflict: {event.id}")
        return stored

    @staticmethod
    def _refresh_context(
        engine: InformationGovernanceEngine,
        context: AccessContext,
        information_ref: GovernedInformationRef,
    ) -> AccessContext:
        return engine.context_for(
            information_ref=information_ref,
            actor_id=context.actor_id,
            principal=context.principal,
            purpose=context.purpose,
            operation=context.operation,
            source_trust_domain=context.source_trust_domain,
            destination_trust_domain=context.destination_trust_domain,
            recipient=context.recipient,
            decision_time=context.decision_time,
            locality=context.locality,
            provider_id=context.provider_id,
            provider_security_posture=context.provider_security_posture,
            disclosure_form=context.disclosure_form,
        )

    @staticmethod
    def _require_disposition(
        actual: DecisionDisposition,
        expected: DecisionDisposition | None,
    ) -> None:
        if expected is not None and actual is not expected:
            raise StaleGovernanceDecisionError(
                "canonical policy changed the material decision disposition"
            )

    def _require_causal_cursor(self, expected: int | None) -> None:
        if expected is not None and self._projection.event_cursor != expected:
            raise StaleGovernanceDecisionError(
                "canonical head changed before governance admission"
            )
