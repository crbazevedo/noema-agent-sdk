"""Replayable state and legality checks for cognitive reconsideration."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TypeVar

from ..endogenous.models import INQUIRY_RECORDED_EVENT
from ..endogenous.projection import EndogenousProjection
from ..events import Event
from ..information.models import InformationOperation, LineageTransformation
from ..information.policy import InformationGovernanceEngine
from ..information.projection import InformationGovernanceProjection
from ..types import JSONObject
from .models import (
    ALLOCATION_OUTCOME_LINKED_EVENT,
    ALLOCATION_RECORDED_EVENT,
    ALLOCATION_TRACE_RECORDED_EVENT,
    CANDIDATE_RECORDED_EVENT,
    MANDATE_RECORDED_EVENT,
    MANDATE_REVOKED_EVENT,
    POLICY_RECORDED_EVENT,
    SCAN_REQUESTED_EVENT,
    SHADOW_PROPOSAL_RECORDED_EVENT,
    AllocationLabel,
    CognitiveAllocationOutcomeLink,
    CognitiveAllocationTrace,
    CognitiveBasisKind,
    HistoricalCognitionKind,
    ReconsiderationAllocation,
    ReconsiderationCandidate,
    ReconsiderationFeatureSnapshot,
    ReconsiderationMandate,
    ReconsiderationMandateRevocation,
    ReconsiderationPolicySnapshot,
    ReconsiderationScanRequest,
    ReconsiderationShadowProposal,
    ScarceCognitionBudget,
    ScarceCognitionCostSnapshot,
)
from .policy import allocate_reconsideration, ensure_allocator_supported

ValueT = TypeVar("ValueT")


class ReconsiderationMandateProjection:
    """Current immutable mandate revisions and their explicit revocations."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._events: dict[str, Event] = {}
        self._last_sequence = 0
        self._revisions: dict[str, ReconsiderationMandate] = {}
        self._current_revision: dict[str, str] = {}
        self._revocations: dict[str, ReconsiderationMandateRevocation] = {}

    @property
    def event_cursor(self) -> int:
        return self._last_sequence

    @property
    def mandates(self) -> tuple[ReconsiderationMandate, ...]:
        return tuple(self._revisions[key] for key in sorted(self._revisions))

    @property
    def revocations(self) -> tuple[ReconsiderationMandateRevocation, ...]:
        return tuple(self._revocations[key] for key in sorted(self._revocations))

    def revision(self, revision_id: str) -> ReconsiderationMandate | None:
        return self._revisions.get(revision_id)

    def current(self, mandate_id: str) -> ReconsiderationMandate | None:
        revision_id = self._current_revision.get(mandate_id)
        return self._revisions.get(revision_id) if revision_id is not None else None

    def is_active_revision(self, revision_id: str, *, at: datetime) -> bool:
        mandate = self._revisions.get(revision_id)
        return bool(
            mandate is not None
            and self._current_revision.get(mandate.mandate_id) == revision_id
            and revision_id not in self._revocations
            and mandate.issued_at <= at < mandate.expires_at
        )

    def apply(self, event: Event) -> bool:
        existing = self._events.get(event.id)
        if existing is not None:
            if existing != event:
                raise ValueError(f"conflicting mandate event identity: {event.id}")
            return False
        if event.sequence is None:
            raise ValueError("mandate projection requires canonical sequenced events")
        if event.sequence <= self._last_sequence:
            raise ValueError("mandate events must be applied in canonical order")
        handled = False
        if event.type == MANDATE_RECORDED_EVENT:
            self._require_exact_head(event)
            mandate = ReconsiderationMandate.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=f"reconsideration-mandate-recorded:{mandate.revision_id}",
                subject=mandate.mandate_id,
                timestamp=mandate.issued_at,
            )
            if event.causation_id != mandate.authorization_ref.removeprefix("event:"):
                raise ValueError("mandate event must cite its authorization evidence")
            if event.causation_id not in self._events:
                raise ValueError("mandate authorization evidence is not canonical")
            if event.metadata.get("validated_mandate_authority_id") != mandate.authority_id:
                raise ValueError("mandate lacks an authenticated authority receipt")
            current = self.current(mandate.mandate_id)
            if current is None:
                if mandate.revision != 1:
                    raise ValueError("first mandate revision must be one")
            elif mandate.revision != current.revision + 1:
                raise ValueError("mandate revisions must advance exactly once")
            self._put_immutable(
                self._revisions,
                mandate.revision_id,
                mandate,
                "mandate revision",
            )
            self._current_revision[mandate.mandate_id] = mandate.revision_id
            handled = True
        elif event.type == MANDATE_REVOKED_EVENT:
            self._require_exact_head(event)
            revocation = ReconsiderationMandateRevocation.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=f"reconsideration-mandate-revoked:{revocation.revocation_id}",
                subject=revocation.mandate_id,
                timestamp=revocation.revoked_at,
            )
            revoked_mandate = self._revisions.get(revocation.mandate_revision_id)
            if (
                revoked_mandate is None
                or revoked_mandate.mandate_id != revocation.mandate_id
                or self._current_revision.get(revocation.mandate_id)
                != revocation.mandate_revision_id
            ):
                raise ValueError("revocation requires the current canonical mandate revision")
            if revocation.revoked_at < revoked_mandate.issued_at:
                raise ValueError("mandate cannot be revoked before issuance")
            if event.causation_id != revocation.authorization_ref.removeprefix("event:"):
                raise ValueError("revocation must cite its authorization evidence")
            if event.causation_id not in self._events:
                raise ValueError("revocation authorization evidence is not canonical")
            if event.metadata.get("validated_mandate_authority_id") != revocation.authority_id:
                raise ValueError("revocation lacks an authenticated authority receipt")
            self._put_immutable(
                self._revocations,
                revocation.mandate_revision_id,
                revocation,
                "mandate revocation",
            )
            handled = True
        self._events[event.id] = event
        self._last_sequence = event.sequence
        return handled

    def rebuild(self, events: Iterable[Event]) -> None:
        self._reset()
        for event in events:
            self.apply(event)

    def _require_exact_head(self, event: Event) -> None:
        if event.metadata.get("validated_at_event_cursor") != self._last_sequence:
            raise ValueError("mandate transition lacks exact-head admission evidence")

    @staticmethod
    def _validate_envelope(
        event: Event,
        *,
        event_id: str,
        subject: str,
        timestamp: datetime,
    ) -> None:
        if event.id != event_id or event.subject != subject or event.timestamp != timestamp:
            raise ValueError("mandate event envelope is inconsistent")

    @staticmethod
    def _put_immutable(
        values: dict[str, ValueT],
        key: str,
        value: ValueT,
        label: str,
    ) -> None:
        existing = values.get(key)
        if existing is not None and existing != value:
            raise ValueError(f"{label} changed in place: {key}")
        values[key] = value


class ReconsiderationProjection:
    """Rebuild candidates, allocation traces, and proposal-only outputs."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._events: dict[str, Event] = {}
        self._last_sequence = 0
        self._endogenous = EndogenousProjection()
        self._information = InformationGovernanceProjection()
        self._mandates = ReconsiderationMandateProjection()
        self._policies: dict[str, ReconsiderationPolicySnapshot] = {}
        self._scans: dict[str, ReconsiderationScanRequest] = {}
        self._candidates: dict[str, ReconsiderationCandidate] = {}
        self._candidates_by_scan: dict[str, set[str]] = {}
        self._allocations: dict[str, ReconsiderationAllocation] = {}
        self._allocation_by_scan: dict[str, str] = {}
        self._traces: dict[str, CognitiveAllocationTrace] = {}
        self._trace_by_decision: dict[tuple[str, str], str] = {}
        self._outcome_links: dict[str, CognitiveAllocationOutcomeLink] = {}
        self._proposals: dict[str, ReconsiderationShadowProposal] = {}
        self._proposal_by_trace: dict[str, str] = {}

    @property
    def event_cursor(self) -> int:
        return self._last_sequence

    @property
    def endogenous(self) -> EndogenousProjection:
        return self._endogenous

    @property
    def information(self) -> InformationGovernanceProjection:
        return self._information

    @property
    def mandates(self) -> ReconsiderationMandateProjection:
        return self._mandates

    @property
    def policies(self) -> tuple[ReconsiderationPolicySnapshot, ...]:
        return tuple(self._policies[key] for key in sorted(self._policies))

    @property
    def scans(self) -> tuple[ReconsiderationScanRequest, ...]:
        return tuple(self._scans[key] for key in sorted(self._scans))

    @property
    def candidates(self) -> tuple[ReconsiderationCandidate, ...]:
        return tuple(self._candidates[key] for key in sorted(self._candidates))

    @property
    def allocations(self) -> tuple[ReconsiderationAllocation, ...]:
        return tuple(self._allocations[key] for key in sorted(self._allocations))

    @property
    def traces(self) -> tuple[CognitiveAllocationTrace, ...]:
        return tuple(self._traces[key] for key in sorted(self._traces))

    @property
    def outcome_links(self) -> tuple[CognitiveAllocationOutcomeLink, ...]:
        return tuple(self._outcome_links[key] for key in sorted(self._outcome_links))

    @property
    def proposals(self) -> tuple[ReconsiderationShadowProposal, ...]:
        return tuple(self._proposals[key] for key in sorted(self._proposals))

    def event(self, event_id: str) -> Event | None:
        return self._events.get(event_id)

    def policy(self, policy_id: str) -> ReconsiderationPolicySnapshot | None:
        return self._policies.get(policy_id)

    def scan(self, request_id: str) -> ReconsiderationScanRequest | None:
        return self._scans.get(request_id)

    def candidate(self, candidate_id: str) -> ReconsiderationCandidate | None:
        return self._candidates.get(candidate_id)

    def candidates_for_scan(self, request_id: str) -> tuple[ReconsiderationCandidate, ...]:
        return tuple(
            self._candidates[value]
            for value in sorted(self._candidates_by_scan.get(request_id, ()))
            if value in self._candidates
        )

    def allocation_for_scan(self, request_id: str) -> ReconsiderationAllocation | None:
        allocation_id = self._allocation_by_scan.get(request_id)
        return self._allocations.get(allocation_id) if allocation_id else None

    def trace_for_decision(
        self,
        candidate_id: str,
        allocation_id: str,
    ) -> CognitiveAllocationTrace | None:
        trace_id = self._trace_by_decision.get((candidate_id, allocation_id))
        return self._traces.get(trace_id) if trace_id else None

    def proposal_for_trace(self, trace_id: str) -> ReconsiderationShadowProposal | None:
        proposal_id = self._proposal_by_trace.get(trace_id)
        return self._proposals.get(proposal_id) if proposal_id else None

    def candidate_was_selected(self, candidate_id: str) -> bool:
        return any(
            decision.candidate_id == candidate_id and decision.label is AllocationLabel.SELECTED
            for allocation in self.allocations
            for decision in allocation.decisions
        )

    def basis_is_current(self, basis: object, *, at: datetime) -> bool:
        try:
            self._validate_basis(basis, at=at)
        except (TypeError, ValueError):
            return False
        return True

    def find_allocation_context(
        self,
        *,
        basis_id: str,
        candidate_ids: tuple[str, ...],
        policy_id: str,
        budget: ScarceCognitionBudget,
        maximum_interruption_units: float,
        trigger_event_id: str | None,
        foreground_demand_refs: tuple[str, ...],
    ) -> ReconsiderationAllocation | None:
        expected_candidates = tuple(sorted(candidate_ids))
        expected_foreground = tuple(sorted(set(foreground_demand_refs)))
        matches = tuple(
            allocation
            for allocation in self.allocations
            if (scan := self._scans[allocation.scan_request_id]).basis.basis_id == basis_id
            and tuple(sorted(value.candidate_id for value in scan.candidate_inputs))
            == expected_candidates
            and scan.policy_id == policy_id
            and scan.budget == budget
            and scan.maximum_interruption_units == maximum_interruption_units
            and scan.trigger_event_id == trigger_event_id
            and allocation.foreground_demand_refs == expected_foreground
        )
        if len(matches) > 1:
            raise ValueError("multiple allocations share one deterministic context")
        return matches[0] if matches else None

    def find_candidate(
        self,
        *,
        inquiry_id: str,
        basis_id: str,
        current_evidence_refs: tuple[str, ...],
        domain: str,
        governed_information_ids: tuple[str, ...],
        features: ReconsiderationFeatureSnapshot,
        costs: ScarceCognitionCostSnapshot,
    ) -> ReconsiderationCandidate | None:
        matches = tuple(
            value
            for value in self.candidates
            if value.historical.inquiry_id == inquiry_id
            and value.current_basis.basis_id == basis_id
            and value.current_evidence_refs == tuple(sorted(set(current_evidence_refs)))
            and value.domain == domain
            and value.historical.governed_information_ids
            == tuple(sorted(set(governed_information_ids)))
            and value.features == features
            and value.costs == costs
        )
        if len(matches) > 1:
            raise ValueError("multiple candidates share one unchanged reconsideration basis")
        return matches[0] if matches else None

    def apply(self, event: Event) -> bool:
        existing = self._events.get(event.id)
        if existing is not None:
            if existing != event:
                raise ValueError(f"conflicting reconsideration event identity: {event.id}")
            return False
        if event.sequence is None:
            raise ValueError("reconsideration projection requires canonical events")
        if event.sequence <= self._last_sequence:
            raise ValueError("reconsideration events must be applied in canonical order")

        handled = self._apply_event(event)
        self._endogenous.apply(event)
        self._information.apply(event)
        mandate_handled = self._mandates.apply(event)
        self._events[event.id] = event
        self._last_sequence = event.sequence
        return handled or mandate_handled

    def rebuild(self, events: Iterable[Event]) -> None:
        self._reset()
        for event in events:
            self.apply(event)

    def _apply_event(self, event: Event) -> bool:
        if event.type in {MANDATE_RECORDED_EVENT, MANDATE_REVOKED_EVENT}:
            return False
        if event.type == POLICY_RECORDED_EVENT:
            policy = ReconsiderationPolicySnapshot.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=f"reconsideration-policy-recorded:{policy.policy_id}",
                subject=policy.policy_id,
            )
            ensure_allocator_supported(policy)
            self._put_immutable(self._policies, policy.policy_id, policy, "policy")
            return True
        if event.type == SCAN_REQUESTED_EVENT:
            self._require_exact_head(event)
            scan = ReconsiderationScanRequest.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=f"reconsideration-scan-requested:{scan.request_id}",
                subject=scan.request_id,
                timestamp=scan.requested_at,
            )
            if scan.policy_id not in self._policies:
                raise ValueError("reconsideration scan references an unknown policy")
            self._validate_basis(scan.basis, at=scan.requested_at)
            self._validate_mandate_scan(scan)
            self._validate_scan_trigger(scan)
            for ref in scan.foreground_demand_refs:
                foreground = self._event_ref(ref)
                policy = self._policies[scan.policy_id]
                if foreground.type not in policy.foreground_event_types:
                    raise ValueError("scan cites an event that is not configured foreground demand")
            for candidate_input in scan.candidate_inputs:
                self._validate_scan_candidate_input(
                    scan,
                    candidate_input,
                    scan_sequence=event.sequence,
                )
                if self.candidate_was_selected(candidate_input.candidate_id):
                    raise ValueError("a surfaced candidate is terminal for its semantic basis")
            self._put_immutable(self._scans, scan.request_id, scan, "scan")
            self._candidates_by_scan[scan.request_id] = {
                value.candidate_id for value in scan.candidate_inputs
            }
            return True
        if event.type == CANDIDATE_RECORDED_EVENT:
            self._require_exact_head(event)
            candidate = ReconsiderationCandidate.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=f"reconsideration-candidate-recorded:{candidate.candidate_id}",
                subject=candidate.candidate_id,
                timestamp=candidate.created_at,
            )
            candidate_scan = self._scans.get(candidate.scan_request_id)
            scan_event = self._events.get(
                f"reconsideration-scan-requested:{candidate.scan_request_id}"
            )
            if candidate_scan is None or scan_event is None or scan_event.sequence is None:
                raise ValueError("candidate references an unknown canonical scan")
            if candidate.current_causal_cursor != scan_event.sequence:
                raise ValueError("candidate does not cite its current scan causal cut")
            matching_input = next(
                (
                    value
                    for value in candidate_scan.candidate_inputs
                    if value.candidate_id == candidate.candidate_id
                ),
                None,
            )
            if matching_input is None:
                raise ValueError("candidate was not declared by its scan")
            expected_candidate = self._candidate_from_input(
                candidate_scan,
                matching_input,
                scan_sequence=scan_event.sequence,
            )
            if candidate != expected_candidate:
                raise ValueError("candidate differs from its deterministic scan input")
            self._put_immutable(
                self._candidates,
                candidate.candidate_id,
                candidate,
                "candidate",
            )
            return True
        if event.type == ALLOCATION_RECORDED_EVENT:
            self._require_exact_head(event)
            allocation = ReconsiderationAllocation.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=f"reconsideration-allocation-recorded:{allocation.allocation_id}",
                subject=allocation.scan_request_id,
                timestamp=allocation.allocated_at,
            )
            if allocation.scan_request_id in self._allocation_by_scan:
                raise ValueError("one reconsideration scan cannot allocate twice")
            allocation_scan = self._scans.get(allocation.scan_request_id)
            allocation_policy = self._policies.get(allocation.policy_id)
            if allocation_scan is None or allocation_policy is None:
                raise ValueError("allocation references an unknown scan or policy")
            if allocation.allocated_at < allocation_scan.requested_at:
                raise ValueError("allocation cannot predate its canonical scan")
            candidates = self.candidates_for_scan(allocation_scan.request_id)
            if len(candidates) != len(allocation_scan.candidate_inputs):
                raise ValueError("allocation requires every declared candidate")
            scan_event = self._events[
                f"reconsideration-scan-requested:{allocation_scan.request_id}"
            ]
            assert scan_event.sequence is not None
            allocation_policy_types = set(allocation_policy.foreground_event_types)
            for ref in allocation.foreground_demand_refs:
                foreground = self._event_ref(ref)
                if (
                    foreground.type not in allocation_policy_types
                    or foreground.sequence is None
                    or foreground.sequence > self._last_sequence
                ):
                    raise ValueError("allocation foreground evidence is invalid")
                if (
                    ref not in allocation_scan.foreground_demand_refs
                    and foreground.sequence <= scan_event.sequence
                ):
                    raise ValueError("intervening foreground evidence must follow the scan cut")
            if not set(allocation_scan.foreground_demand_refs).issubset(
                allocation.foreground_demand_refs
            ):
                raise ValueError("allocation lost foreground evidence pinned by its scan")
            self._validate_derived_information(
                information_id=allocation.derived_information_id,
                source_information_ids=tuple(value.derived_information_id for value in candidates),
                policy_ids=allocation_scan.information_policy_ids,
            )
            expected_allocation = allocate_reconsideration(
                scan=allocation_scan,
                policy=allocation_policy,
                candidates=candidates,
                derived_information_id=allocation.derived_information_id,
                foreground_demand_refs=allocation.foreground_demand_refs,
                terminal_constraints=self.allocation_terminal_constraints(
                    allocation_scan,
                    candidates,
                    at=allocation.allocated_at,
                ),
                allocated_at=allocation.allocated_at,
            )
            if allocation != expected_allocation:
                raise ValueError("allocation differs from deterministic policy replay")
            self._allocations[allocation.allocation_id] = allocation
            self._allocation_by_scan[allocation_scan.request_id] = allocation.allocation_id
            return True
        if event.type == ALLOCATION_TRACE_RECORDED_EVENT:
            self._require_exact_head(event)
            trace = CognitiveAllocationTrace.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=f"cognitive-allocation-trace-recorded:{trace.trace_id}",
                subject=trace.candidate_id,
                timestamp=trace.recorded_at,
            )
            trace_allocation = self._allocations.get(trace.allocation_id)
            trace_candidate = self._candidates.get(trace.candidate_id)
            if trace_allocation is None or trace_candidate is None:
                raise ValueError("allocation trace references unknown state")
            decision = next(
                (
                    value
                    for value in trace_allocation.decisions
                    if value.candidate_id == trace.candidate_id
                ),
                None,
            )
            if decision is None:
                raise ValueError("allocation trace candidate was not decided")
            expected_trace = CognitiveAllocationTrace.create(
                derived_information_id=trace.derived_information_id,
                allocation=trace_allocation,
                candidate=trace_candidate,
                decision=decision,
            )
            if trace != expected_trace:
                raise ValueError("allocation trace differs from its canonical decision")
            self._validate_derived_information(
                information_id=trace.derived_information_id,
                source_information_ids=(trace_allocation.derived_information_id,),
                policy_ids=self._scans[trace_allocation.scan_request_id].information_policy_ids,
            )
            decision_key = (trace.candidate_id, trace.allocation_id)
            if decision_key in self._trace_by_decision:
                raise ValueError("candidate allocation decision already has a trace")
            self._traces[trace.trace_id] = trace
            self._trace_by_decision[decision_key] = trace.trace_id
            return True
        if event.type == ALLOCATION_OUTCOME_LINKED_EVENT:
            self._require_exact_head(event)
            outcome_link = CognitiveAllocationOutcomeLink.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=(f"cognitive-allocation-outcome-linked:{outcome_link.link_id}"),
                subject=outcome_link.trace_id,
                timestamp=outcome_link.linked_at,
            )
            if outcome_link.trace_id not in self._traces:
                raise ValueError("allocation outcome link references an unknown trace")
            if event.causation_id != outcome_link.outcome_ref.removeprefix("event:"):
                raise ValueError("allocation outcome link causation is inconsistent")
            self._event_ref(outcome_link.outcome_ref)
            self._put_immutable(
                self._outcome_links,
                outcome_link.link_id,
                outcome_link,
                "allocation outcome link",
            )
            return True
        if event.type == SHADOW_PROPOSAL_RECORDED_EVENT:
            self._require_exact_head(event)
            proposal = ReconsiderationShadowProposal.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=f"reconsideration-shadow-proposal-recorded:{proposal.proposal_id}",
                subject=proposal.candidate_id,
                timestamp=proposal.created_at,
            )
            proposal_candidate = self._candidates.get(proposal.candidate_id)
            proposal_allocation = self._allocations.get(proposal.allocation_id)
            proposal_trace = self._traces.get(proposal.allocation_trace_id)
            if proposal_candidate is None or proposal_allocation is None or proposal_trace is None:
                raise ValueError("shadow proposal references unknown reconsideration state")
            self._validate_basis(proposal_candidate.current_basis, at=proposal.created_at)
            if proposal.candidate_id not in proposal_allocation.selected_candidate_ids:
                raise ValueError("only a selected candidate may produce a shadow proposal")
            expected_proposal = ReconsiderationShadowProposal.create(
                candidate=proposal_candidate,
                allocation=proposal_allocation,
                trace=proposal_trace,
            )
            if proposal != expected_proposal:
                raise ValueError("shadow proposal differs from its selected candidate")
            self._put_immutable(
                self._proposals,
                proposal.proposal_id,
                proposal,
                "shadow proposal",
            )
            existing_proposal = self._proposal_by_trace.get(proposal.allocation_trace_id)
            if existing_proposal is not None and existing_proposal != proposal.proposal_id:
                raise ValueError("allocation trace already has a shadow proposal")
            self._proposal_by_trace[proposal.allocation_trace_id] = proposal.proposal_id
            return True
        return False

    def _validate_basis(self, basis: object, *, at: datetime) -> None:
        from .models import CurrentCognitiveBasis

        if not isinstance(basis, CurrentCognitiveBasis):
            raise TypeError("invalid current cognitive basis")
        if basis.kind is CognitiveBasisKind.LIVE_GOVERNING_INTENT:
            if basis.live_intent_ref is None or not self._endogenous.intent_refs_are_current(
                (basis.live_intent_ref,)
            ):
                raise ValueError("live cognitive basis requires exact ACTIVE or BLOCKED intent")
            return
        if basis.mandate_revision_id is None or not self._mandates.is_active_revision(
            basis.mandate_revision_id, at=at
        ):
            raise ValueError("mandate cognitive basis is not current, active, and unexpired")

    def _validate_mandate_scan(self, scan: ReconsiderationScanRequest) -> None:
        if scan.basis.kind is not CognitiveBasisKind.RECONSIDERATION_MANDATE:
            return
        assert scan.basis.mandate_revision_id is not None
        mandate = self._mandates.revision(scan.basis.mandate_revision_id)
        if mandate is None:
            raise ValueError("scan references an unknown mandate")
        if not scan.budget.fits_within(mandate.budget):
            raise ValueError("scan budget exceeds its mandate")
        if scan.maximum_interruption_units != mandate.maximum_interruption_units:
            raise ValueError("scan interruption ceiling differs from its mandate")
        if scan.information_use_purpose != mandate.information_use_purpose:
            raise ValueError("scan information purpose differs from its mandate")
        if scan.information_policy_ids != mandate.information_policy_ids:
            raise ValueError("scan information policies differ from its mandate")
        previous = tuple(
            value for value in self.scans if value.basis.mandate_revision_id == mandate.revision_id
        )
        if previous:
            latest = max(value.requested_at for value in previous)
            elapsed = (scan.requested_at - latest).total_seconds()
            if elapsed < mandate.minimum_interval_seconds:
                raise ValueError("reconsideration scan violates mandate cadence")

    def _validate_scan_trigger(self, scan: ReconsiderationScanRequest) -> None:
        if scan.basis.kind is not CognitiveBasisKind.RECONSIDERATION_MANDATE:
            return
        assert scan.basis.mandate_revision_id is not None
        mandate = self._mandates.revision(scan.basis.mandate_revision_id)
        assert mandate is not None
        if not mandate.trigger_event_types:
            if scan.trigger_event_id is not None:
                raise ValueError("cadence-only mandate scan cannot claim a trigger")
            return
        if scan.trigger_event_id is None:
            raise ValueError("mandate scan requires an explicit canonical trigger")
        trigger = self._events.get(scan.trigger_event_id)
        if trigger is None or trigger.type not in mandate.trigger_event_types:
            raise ValueError("mandate scan trigger is absent or out of scope")
        mandate_event = self._events.get(f"reconsideration-mandate-recorded:{mandate.revision_id}")
        if (
            mandate_event is None
            or mandate_event.sequence is None
            or trigger.sequence is None
            or trigger.sequence <= mandate_event.sequence
        ):
            raise ValueError("mandate scan trigger predates mandate activation")
        previous_scans = tuple(
            value for value in self.scans if value.basis.mandate_revision_id == mandate.revision_id
        )
        if any(value.trigger_event_id == scan.trigger_event_id for value in previous_scans):
            raise ValueError("mandate scan trigger was already consumed")
        previous_scan_sequences = tuple(
            event.sequence or 0
            for value in previous_scans
            if (event := self._events.get(f"reconsideration-scan-requested:{value.request_id}"))
            is not None
        )
        if previous_scan_sequences and trigger.sequence <= max(previous_scan_sequences):
            raise ValueError("mandate scan trigger is stale")

    def allocation_terminal_constraints(
        self,
        scan: ReconsiderationScanRequest,
        candidates: tuple[ReconsiderationCandidate, ...],
        *,
        at: datetime,
    ) -> dict[str, str]:
        if not self.basis_is_current(scan.basis, at=at):
            return {candidate.candidate_id: "basis_no_longer_current" for candidate in candidates}
        return {
            candidate.candidate_id: "candidate_already_selected"
            for candidate in candidates
            if self.candidate_was_selected(candidate.candidate_id)
        }

    def _validate_scan_candidate_input(
        self,
        scan: ReconsiderationScanRequest,
        candidate_input: object,
        *,
        scan_sequence: int | None,
    ) -> None:
        from .models import ReconsiderationCandidateInput

        if not isinstance(candidate_input, ReconsiderationCandidateInput):
            raise TypeError("invalid reconsideration candidate input")
        if scan_sequence is None:
            raise ValueError("reconsideration scan must be canonical")
        candidate = self._candidate_from_input(
            scan,
            candidate_input,
            scan_sequence=scan_sequence,
        )
        if candidate.candidate_id != candidate_input.candidate_id:
            raise ValueError("scan candidate identity differs from its semantic input")
        self._validate_historical_inquiry(candidate)
        self._validate_evidence_cut(candidate, maximum_sequence=self._last_sequence)
        self._validate_access_decisions(scan, candidate_input)
        self._validate_candidate_scope(candidate)
        self._validate_derived_information(
            information_id=candidate.derived_information_id,
            source_information_ids=candidate.historical.governed_information_ids,
            policy_ids=scan.information_policy_ids,
        )

    @staticmethod
    def _candidate_from_input(
        scan: ReconsiderationScanRequest,
        candidate_input: object,
        *,
        scan_sequence: int,
    ) -> ReconsiderationCandidate:
        from .models import ReconsiderationCandidateInput

        if not isinstance(candidate_input, ReconsiderationCandidateInput):
            raise TypeError("invalid reconsideration candidate input")
        seed = candidate_input.seed
        return ReconsiderationCandidate.create(
            scan_request_id=scan.request_id,
            derived_information_id=candidate_input.derived_information_id,
            historical=candidate_input.historical,
            current_basis=scan.basis,
            domain=seed.domain,
            current_causal_cursor=scan_sequence,
            current_evidence_refs=seed.current_evidence_refs,
            information_access_decision_ids=candidate_input.information_access_decision_ids,
            features=seed.features,
            costs=seed.costs,
            created_at=scan.requested_at,
        )

    def _validate_access_decisions(
        self,
        scan: ReconsiderationScanRequest,
        candidate_input: object,
    ) -> None:
        from .models import ReconsiderationCandidateInput

        if not isinstance(candidate_input, ReconsiderationCandidateInput):
            raise TypeError("invalid reconsideration candidate input")
        decisions = []
        governance = InformationGovernanceEngine(self._information)
        for decision_id in candidate_input.information_access_decision_ids:
            decision = self._information.access_decision(decision_id)
            if decision is None or not decision.allowed:
                raise ValueError("reconsideration requires current allowed information use")
            if not governance.decide_access(decision.request).allowed:
                raise ValueError("reconsideration information use is no longer allowed")
            if decision.request.context.operation is not InformationOperation.REASON:
                raise ValueError("reconsideration information use must be admitted for reasoning")
            if decision.request.context.purpose != scan.information_use_purpose:
                raise ValueError("information decision purpose differs from reconsideration")
            if decision.request.context.policy_ids != scan.information_policy_ids:
                raise ValueError("information decision policy lineage differs from scan")
            decisions.append(decision)
        decision_information = tuple(
            sorted(value.request.information_ref.information_id for value in decisions)
        )
        if decision_information != tuple(sorted(candidate_input.seed.governed_information_ids)):
            raise ValueError("information decisions do not cover every governed source")

    def _validate_historical_inquiry(self, candidate: ReconsiderationCandidate) -> None:
        if candidate.historical.kind is not HistoricalCognitionKind.INQUIRY:
            raise ValueError("v0.6.1 supports historical Inquiry only")
        inquiry = self._endogenous.inquiry(candidate.historical.inquiry_id)
        inquiry_event = self._events.get(f"inquiry-recorded:{candidate.historical.inquiry_id}")
        if inquiry is None or inquiry_event is None or inquiry_event.type != INQUIRY_RECORDED_EVENT:
            raise ValueError("historical inquiry is not canonical")
        if (
            str(inquiry_event.payload["epoch_id"]) != candidate.historical.epoch_id
            or inquiry.causal_cursor != candidate.historical.historical_causal_cursor
            or inquiry.governing_intent_refs
            != candidate.historical.historical_governing_intent_refs
            or inquiry.evidence_refs != candidate.historical.historical_evidence_refs
        ):
            raise ValueError("historical inquiry provenance is inconsistent")
        if inquiry in self._endogenous.eligible_inquiries(at=candidate.created_at):
            raise ValueError("a current inquiry cannot be reconsidered as historical")
        if candidate.current_basis.kind is CognitiveBasisKind.LIVE_GOVERNING_INTENT:
            assert candidate.current_basis.live_intent_ref is not None
            if candidate.current_basis.live_intent_ref.goal_id not in {
                value.goal_id for value in inquiry.governing_intent_refs
            }:
                raise ValueError(
                    "live-intent reconsideration requires the same stable goal lineage"
                )

    def _validate_evidence_cut(
        self,
        candidate: ReconsiderationCandidate,
        *,
        maximum_sequence: int,
    ) -> None:
        refs = {
            *candidate.current_evidence_refs,
            *candidate.features.provenance_refs,
            *(ref for estimate in candidate.features.estimates() for ref in estimate.evidence_refs),
        }
        for ref in refs:
            evidence = self._event_ref(ref)
            sequence = evidence.sequence or 0
            if sequence <= candidate.historical.historical_causal_cursor:
                raise ValueError("reconsideration evidence does not follow the historical cut")
            if sequence > maximum_sequence:
                raise ValueError("reconsideration evidence postdates the scan causal cut")

    def _validate_candidate_scope(self, candidate: ReconsiderationCandidate) -> None:
        if candidate.current_basis.kind is not CognitiveBasisKind.RECONSIDERATION_MANDATE:
            return
        assert candidate.current_basis.mandate_revision_id is not None
        mandate = self._mandates.revision(candidate.current_basis.mandate_revision_id)
        assert mandate is not None
        if HistoricalCognitionKind.INQUIRY.value not in mandate.candidate_classes:
            raise ValueError("historical Inquiry is outside mandate candidate classes")
        if candidate.domain not in mandate.candidate_domains:
            raise ValueError("candidate domain is outside mandate scope")
        if candidate.costs.interruption_units > mandate.maximum_interruption_units:
            raise ValueError("candidate exceeds mandate interruption ceiling")

    def _validate_derived_information(
        self,
        *,
        information_id: str,
        source_information_ids: tuple[str, ...],
        policy_ids: tuple[str, ...],
    ) -> None:
        lineage = self._information.lineage(information_id)
        binding = self._information.binding(information_id)
        if (
            lineage is None
            or lineage.transformation is not LineageTransformation.DERIVATION
            or lineage.source_information_ids != tuple(sorted(set(source_information_ids)))
        ):
            raise ValueError("reconsideration derived information lacks exact source lineage")
        if (
            binding is None
            or binding.lineage_id != lineage.lineage_id
            or binding.policy_ids != tuple(sorted(set(policy_ids)))
        ):
            raise ValueError("reconsideration derived information lacks inherited policy binding")

    def _event_ref(self, ref: str) -> Event:
        if not ref.startswith("event:"):
            raise ValueError(f"unsupported reconsideration evidence reference: {ref}")
        event = self._events.get(ref.removeprefix("event:"))
        if event is None:
            raise ValueError(f"unknown reconsideration evidence event: {ref}")
        return event

    def _require_exact_head(self, event: Event) -> None:
        if event.metadata.get("validated_at_event_cursor") != self._last_sequence:
            raise ValueError("reconsideration transition lacks exact-head admission evidence")

    @staticmethod
    def _validate_envelope(
        event: Event,
        *,
        event_id: str,
        subject: str,
        timestamp: datetime | None = None,
    ) -> None:
        if event.id != event_id or event.subject != subject:
            raise ValueError("reconsideration event envelope is inconsistent")
        if timestamp is not None and event.timestamp != timestamp:
            raise ValueError("reconsideration event timestamp is inconsistent")

    @staticmethod
    def _put_immutable(
        values: dict[str, ValueT],
        key: str,
        value: ValueT,
        label: str,
    ) -> None:
        existing = values.get(key)
        if existing is not None and existing != value:
            raise ValueError(f"{label} changed in place: {key}")
        values[key] = value

    def semantic_snapshot(self) -> JSONObject:
        return {
            "mandates": [value.to_dict() for value in self._mandates.mandates],
            "revocations": [value.to_dict() for value in self._mandates.revocations],
            "policies": [value.to_dict() for value in self.policies],
            "scans": [value.to_dict() for value in self.scans],
            "candidates": [value.to_dict() for value in self.candidates],
            "allocations": [value.to_dict() for value in self.allocations],
            "traces": [value.to_dict() for value in self.traces],
            "outcome_links": [value.to_dict() for value in self.outcome_links],
            "proposals": [value.to_dict() for value in self.proposals],
        }
