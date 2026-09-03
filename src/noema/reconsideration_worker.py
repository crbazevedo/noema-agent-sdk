"""Crash-recoverable, proposal-only worker for historical Inquiry reconsideration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from .checkpoints import ConsumerCheckpoint, ConsumerCheckpointProjection
from .endogenous.models import Inquiry
from .events import Event
from .information import (
    DecisionDisposition,
    GovernedInformationRef,
    InformationAccessRequest,
    InformationGovernanceAdmission,
    InformationGovernanceEngine,
    InformationLineage,
    InformationOperation,
    LineageTransformation,
    OpaqueInformationIdDeriver,
    PolicyBinding,
    PrincipalSnapshot,
)
from .kernel import NoemaKernel
from .reconsideration.authority import ReconsiderationAuthority
from .reconsideration.models import (
    SCAN_REQUESTED_EVENT,
    AllocationLabel,
    CognitiveAllocationOutcomeLink,
    CognitiveAllocationTrace,
    CognitiveBasisKind,
    CurrentCognitiveBasis,
    HistoricalCognitionKind,
    HistoricalCognitionRef,
    ReconsiderationAllocation,
    ReconsiderationCandidate,
    ReconsiderationCandidateInput,
    ReconsiderationMandate,
    ReconsiderationMandateRevocation,
    ReconsiderationPolicySnapshot,
    ReconsiderationScanRequest,
    ReconsiderationSeed,
    ReconsiderationShadowProposal,
    ScarceCognitionBudget,
)
from .reconsideration.policy import allocate_reconsideration
from .reconsideration.projection import ReconsiderationProjection
from .store import ConcurrentAppendError
from .types import JSONValue, utc_now


class ReconsiderationShadowWorker:
    """Revalidate historical inquiries without creating current work or effects."""

    def __init__(
        self,
        kernel: NoemaKernel,
        *,
        authority: ReconsiderationAuthority,
        policy: ReconsiderationPolicySnapshot | None = None,
        clock: Callable[[], datetime] = utc_now,
        derived_information_id_deriver: OpaqueInformationIdDeriver,
        consumer_id: str = "cognitive-reconsideration-shadow",
        source: str = "reconsideration:shadow-worker",
    ) -> None:
        if not consumer_id.strip() or not source.strip():
            raise ValueError("reconsideration worker ids must be non-empty")
        self.kernel = kernel
        self.authority = authority
        self.policy = policy or ReconsiderationPolicySnapshot.create(version="deterministic-v1")
        self.clock = clock
        self.derived_information_id_deriver = derived_information_id_deriver
        self.consumer_id = consumer_id
        self.source = source
        self._checkpoint_lock = asyncio.Lock()

    async def record_mandate(self, mandate: ReconsiderationMandate) -> ReconsiderationMandate:
        if not self.authority.authenticates_mandate(mandate):
            raise PermissionError("reconsideration mandate issuer is not authenticated")
        stored = await self._append_exact(
            mandate.to_event(source=self.source),
            authority_id=self.authority.authority_id,
        )
        return ReconsiderationMandate.from_dict(stored.payload)

    async def revoke_mandate(
        self,
        revocation: ReconsiderationMandateRevocation,
    ) -> ReconsiderationMandateRevocation:
        if not self.authority.authenticates_revocation(revocation):
            raise PermissionError("reconsideration mandate revocation is not authenticated")
        stored = await self._append_exact(
            revocation.to_event(source=self.source),
            authority_id=self.authority.authority_id,
        )
        return ReconsiderationMandateRevocation.from_dict(stored.payload)

    async def run_scan(
        self,
        *,
        basis: CurrentCognitiveBasis,
        seeds: tuple[ReconsiderationSeed, ...],
        principal: PrincipalSnapshot,
        actor_id: str,
        source_trust_domain: str,
        locality: str,
        budget: ScarceCognitionBudget | None = None,
        information_use_purpose: str | None = None,
        information_policy_ids: tuple[str, ...] | None = None,
        trigger_event_id: str | None = None,
    ) -> ReconsiderationAllocation | None:
        """Revalidate explicit historical Inquiry seeds under one current basis."""

        if not seeds:
            raise ValueError("reconsideration scan requires historical Inquiry seeds")
        if not self.kernel.started:
            await self.kernel.start()
        at = self.clock()
        if at.tzinfo is None:
            raise ValueError("reconsideration worker clock must be timezone-aware")
        projection = await self.current_projection()
        mandate = None
        if basis.kind is CognitiveBasisKind.RECONSIDERATION_MANDATE:
            assert basis.mandate_revision_id is not None
            mandate = projection.mandates.revision(basis.mandate_revision_id)
            if mandate is None:
                raise ValueError("reconsideration scan references an unknown mandate")
            effective_budget = budget or mandate.budget
            maximum_interruption_units = mandate.maximum_interruption_units
            purpose = information_use_purpose or mandate.information_use_purpose
            policies = information_policy_ids or mandate.information_policy_ids
        else:
            if budget is None or information_use_purpose is None or information_policy_ids is None:
                raise ValueError(
                    "live-intent reconsideration requires explicit budget and information policy"
                )
            effective_budget = budget
            maximum_interruption_units = budget.ceiling.interruption_units
            purpose = information_use_purpose
            policies = information_policy_ids
        await self.kernel.emit(self.policy.to_event(source=self.source, recorded_at=at))
        projection = await self.current_projection()
        if trigger_event_id is not None and any(
            value.trigger_event_id == trigger_event_id for value in projection.scans
        ):
            raise ValueError("mandate scan trigger was already consumed")
        prepared: list[
            tuple[
                ReconsiderationSeed,
                HistoricalCognitionRef,
                str,
                str,
            ]
        ] = []
        all_candidate_ids: list[str] = []
        for seed in seeds:
            inquiry = projection.endogenous.inquiry(seed.inquiry_id)
            if inquiry is None:
                raise ValueError("reconsideration seed references an unknown Inquiry")
            historical = self._historical_ref(
                projection,
                inquiry,
                governed_information_ids=seed.governed_information_ids,
            )
            candidate_id = ReconsiderationCandidate.identity_for(
                historical=historical,
                current_basis=basis,
                domain=seed.domain,
                current_evidence_refs=seed.current_evidence_refs,
                features=seed.features,
                costs=seed.costs,
            )
            all_candidate_ids.append(candidate_id)
            if projection.candidate_was_selected(candidate_id):
                continue
            derived_information_id = self._derived_information_id(
                namespace="reconsideration-candidate",
                stable_key=candidate_id,
            )
            existing_candidate = projection.candidate(candidate_id)
            if (
                existing_candidate is not None
                and existing_candidate.derived_information_id != derived_information_id
            ):
                raise ValueError("candidate derived-information identity changed")
            prepared.append((seed, historical, candidate_id, derived_information_id))

        if not prepared:
            return self._latest_allocation_for_candidates(
                projection,
                tuple(all_candidate_ids),
            )

        foreground_refs = await self._canonical_foreground_refs(
            projection,
            basis=basis,
            policy=self.policy,
        )
        candidate_ids = tuple(value[2] for value in prepared)
        existing_context = projection.find_allocation_context(
            basis_id=basis.basis_id,
            candidate_ids=candidate_ids,
            policy_id=self.policy.policy_id,
            budget=effective_budget,
            maximum_interruption_units=maximum_interruption_units,
            trigger_event_id=trigger_event_id,
            foreground_demand_refs=foreground_refs,
        )
        if existing_context is not None:
            return existing_context

        candidate_inputs: list[ReconsiderationCandidateInput] = []
        for seed, historical, candidate_id, derived_information_id in prepared:
            decisions = await self._admit_information_use(
                seed,
                principal=principal,
                actor_id=actor_id,
                purpose=purpose,
                source_trust_domain=source_trust_domain,
                locality=locality,
                at=at,
            )
            await self._ensure_derived_governance(
                information_id=derived_information_id,
                source_information_ids=seed.governed_information_ids,
                policy_ids=tuple(sorted(set(policies))),
                recorded_at=at,
            )
            candidate_inputs.append(
                ReconsiderationCandidateInput(
                    candidate_id=candidate_id,
                    historical=historical,
                    derived_information_id=derived_information_id,
                    seed=seed,
                    information_access_decision_ids=tuple(decisions),
                )
            )
        scan = ReconsiderationScanRequest.create(
            basis=basis,
            policy_id=self.policy.policy_id,
            budget=effective_budget,
            maximum_interruption_units=maximum_interruption_units,
            candidate_inputs=tuple(candidate_inputs),
            information_use_purpose=purpose,
            information_policy_ids=tuple(sorted(set(policies))),
            requested_at=at,
            trigger_event_id=trigger_event_id,
            foreground_demand_refs=foreground_refs,
        )
        stored = await self._append_exact(scan.to_event(source=self.source))
        return await self._process_scan(stored)

    async def recover(self) -> tuple[ReconsiderationAllocation, ...]:
        history = await self._normalized_history()
        checkpoints = ConsumerCheckpointProjection()
        checkpoints.rebuild(history)
        checkpoint = checkpoints.get(self.consumer_id)
        after = checkpoint.last_completed_sequence if checkpoint else 0
        projection = ReconsiderationProjection()
        projection.rebuild(history)
        at = self.clock()
        if at.tzinfo is None:
            raise ValueError("reconsideration worker clock must be timezone-aware")
        recovered: list[ReconsiderationAllocation] = []
        for event in history:
            if event.sequence is None:
                continue
            if event.type != SCAN_REQUESTED_EVENT:
                continue
            scan = ReconsiderationScanRequest.from_dict(event.payload)
            if event.sequence <= after and self._scan_outputs_complete(
                projection,
                scan,
                at=at,
            ):
                continue
            allocation = await self._process_scan(event)
            if allocation is not None:
                recovered.append(allocation)
                projection = await self.current_projection()
        return tuple(recovered)

    @staticmethod
    def _scan_outputs_complete(
        projection: ReconsiderationProjection,
        scan: ReconsiderationScanRequest,
        *,
        at: datetime,
    ) -> bool:
        candidates = projection.candidates_for_scan(scan.request_id)
        if len(candidates) != len(scan.candidate_inputs):
            return False
        allocation = projection.allocation_for_scan(scan.request_id)
        if allocation is None:
            return False
        by_id = {value.candidate_id: value for value in candidates}
        for decision in allocation.decisions:
            trace = projection.trace_for_decision(
                decision.candidate_id,
                allocation.allocation_id,
            )
            if trace is None:
                return False
            if (
                decision.label is AllocationLabel.SELECTED
                and projection.proposal_for_trace(trace.trace_id) is None
                and projection.basis_is_current(
                    by_id[decision.candidate_id].current_basis,
                    at=at,
                )
            ):
                return False
        return True

    async def link_outcome(
        self,
        *,
        trace_id: str,
        outcome_ref: str,
        outcome_kind: str,
        linked_at: datetime | None = None,
    ) -> CognitiveAllocationOutcomeLink:
        """Append later evidence without rewriting the original allocation trace."""

        link = CognitiveAllocationOutcomeLink.create(
            trace_id=trace_id,
            outcome_ref=outcome_ref,
            outcome_kind=outcome_kind,
            linked_at=linked_at or utc_now(),
        )
        stored = await self._append_exact(link.to_event(source=self.source))
        return CognitiveAllocationOutcomeLink.from_dict(stored.payload)

    async def current_projection(self) -> ReconsiderationProjection:
        projection = ReconsiderationProjection()
        projection.rebuild(await self._normalized_history())
        return projection

    async def ensure_derived_governance(
        self,
        *,
        information_id: str,
        source_information_ids: tuple[str, ...],
        policy_ids: tuple[str, ...],
        recorded_at: datetime,
    ) -> None:
        """Share the existing race-safe lineage boundary with discovery artifacts."""

        await self._ensure_derived_governance(
            information_id=information_id,
            source_information_ids=source_information_ids,
            policy_ids=policy_ids,
            recorded_at=recorded_at,
        )

    async def admit_information_use(
        self,
        information_ids: tuple[str, ...],
        *,
        principal: PrincipalSnapshot,
        actor_id: str,
        purpose: str,
        source_trust_domain: str,
        locality: str,
        at: datetime,
    ) -> tuple[str, ...]:
        """Admit exact governed sources for reasoning without constructing a seed."""

        decision_ids: list[str] = []
        for information_id in tuple(sorted(set(information_ids))):
            projection = await self.current_projection()
            engine = InformationGovernanceEngine(projection.information)
            information_ref = GovernedInformationRef(information_id)
            context = engine.context_for(
                information_ref=information_ref,
                actor_id=actor_id,
                principal=principal,
                purpose=purpose,
                operation=InformationOperation.REASON,
                source_trust_domain=source_trust_domain,
                destination_trust_domain=None,
                recipient=None,
                decision_time=at,
                locality=locality,
            )
            request = InformationAccessRequest.create(
                information_ref=information_ref,
                context=context,
            )
            receipt = await InformationGovernanceAdmission(
                self.kernel,
                projection.information,
                source=self.source,
            ).admit_access(
                request,
                expected_disposition=DecisionDisposition.ALLOW,
            )
            decision_ids.append(receipt.record.decision_id)
        return tuple(sorted(decision_ids))

    async def canonical_foreground_refs(
        self,
        projection: ReconsiderationProjection,
        *,
        basis: CurrentCognitiveBasis,
    ) -> tuple[str, ...]:
        """Expose the pinned v0.6.1 foreground view to the discovery layer."""

        return await self._canonical_foreground_refs(
            projection,
            basis=basis,
            policy=self.policy,
        )

    async def _process_scan(self, scan_event: Event) -> ReconsiderationAllocation | None:
        if scan_event.sequence is None:
            raise ValueError("reconsideration scan must be canonical")
        scan = ReconsiderationScanRequest.from_dict(scan_event.payload)
        projection = await self.current_projection()
        for candidate_input in scan.candidate_inputs:
            if projection.candidate(candidate_input.candidate_id) is not None:
                continue
            seed = candidate_input.seed
            candidate = ReconsiderationCandidate.create(
                scan_request_id=scan.request_id,
                derived_information_id=candidate_input.derived_information_id,
                historical=candidate_input.historical,
                current_basis=scan.basis,
                domain=seed.domain,
                current_causal_cursor=scan_event.sequence,
                current_evidence_refs=seed.current_evidence_refs,
                information_access_decision_ids=(candidate_input.information_access_decision_ids),
                features=seed.features,
                costs=seed.costs,
                created_at=scan.requested_at,
            )
            await self._append_exact(candidate.to_event(source=self.source))
            projection = await self.current_projection()

        projection = await self.current_projection()
        allocation = projection.allocation_for_scan(scan.request_id)
        if allocation is None:
            allocation = await self._ensure_allocation(scan_event)

        projection = await self.current_projection()
        by_id = {
            value.candidate_id: value for value in projection.candidates_for_scan(scan.request_id)
        }
        for decision in allocation.decisions:
            candidate = by_id[decision.candidate_id]
            trace = projection.trace_for_decision(
                candidate.candidate_id,
                allocation.allocation_id,
            )
            if trace is None:
                trace_information_id = self._derived_information_id(
                    namespace="reconsideration-trace",
                    stable_key=f"{allocation.allocation_id}:{candidate.candidate_id}",
                )
                await self._ensure_derived_governance(
                    information_id=trace_information_id,
                    source_information_ids=(allocation.derived_information_id,),
                    policy_ids=scan.information_policy_ids,
                    recorded_at=allocation.allocated_at,
                )
                trace = CognitiveAllocationTrace.create(
                    derived_information_id=trace_information_id,
                    allocation=allocation,
                    candidate=candidate,
                    decision=decision,
                )
                stored_trace = await self._append_exact(trace.to_event(source=self.source))
                trace = CognitiveAllocationTrace.from_dict(stored_trace.payload)
                projection = await self.current_projection()
            if decision.label is not AllocationLabel.SELECTED:
                continue
            if projection.proposal_for_trace(trace.trace_id) is None:
                surfacing_time = self.clock()
                if surfacing_time.tzinfo is None:
                    raise ValueError("reconsideration worker clock must be timezone-aware")
                if not projection.basis_is_current(
                    candidate.current_basis,
                    at=surfacing_time,
                ):
                    continue
                proposal = ReconsiderationShadowProposal.create(
                    candidate=candidate,
                    allocation=allocation,
                    trace=trace,
                )
                await self._append_exact(proposal.to_event(source=self.source))
                projection = await self.current_projection()
        await self._advance_checkpoint(scan_event, allocation.allocation_id)
        return allocation

    async def _ensure_allocation(
        self,
        scan_event: Event,
    ) -> ReconsiderationAllocation:
        if scan_event.sequence is None:
            raise ValueError("reconsideration allocation requires a canonical scan")
        scan = ReconsiderationScanRequest.from_dict(scan_event.payload)
        projection = await self.current_projection()
        candidates = projection.candidates_for_scan(scan.request_id)
        if len(candidates) != len(scan.candidate_inputs):
            raise ValueError("reconsideration allocation requires every candidate")
        allocation_information_id = self._derived_information_id(
            namespace="reconsideration-allocation",
            stable_key=scan.request_id,
        )
        await self._ensure_derived_governance(
            information_id=allocation_information_id,
            source_information_ids=tuple(value.derived_information_id for value in candidates),
            policy_ids=scan.information_policy_ids,
            recorded_at=scan.requested_at,
        )
        while True:
            history = await self._normalized_history()
            projection = ReconsiderationProjection()
            projection.rebuild(history)
            existing = projection.allocation_for_scan(scan.request_id)
            if existing is not None:
                return existing
            policy = projection.policy(scan.policy_id)
            if policy is None:
                raise ValueError("reconsideration scan lost its pinned policy")
            candidates = projection.candidates_for_scan(scan.request_id)
            allocated_at = self.clock()
            if allocated_at.tzinfo is None:
                raise ValueError("reconsideration worker clock must be timezone-aware")
            foreground = {
                *scan.foreground_demand_refs,
                *(
                    f"event:{event.id}"
                    for event in history
                    if event.sequence is not None
                    and event.sequence > scan_event.sequence
                    and event.type in policy.foreground_event_types
                ),
            }
            allocation = allocate_reconsideration(
                scan=scan,
                policy=policy,
                candidates=candidates,
                derived_information_id=allocation_information_id,
                foreground_demand_refs=tuple(sorted(foreground)),
                terminal_constraints=projection.allocation_terminal_constraints(
                    scan,
                    candidates,
                    at=allocated_at,
                ),
                allocated_at=allocated_at,
            )
            metadata: dict[str, JSONValue] = dict(allocation.to_event(source=self.source).metadata)
            metadata["validated_at_event_cursor"] = projection.event_cursor
            admitted = replace(
                allocation.to_event(source=self.source),
                metadata=metadata,
            )
            probe = ReconsiderationProjection()
            probe.rebuild(history)
            probe.apply(admitted.with_sequence(projection.event_cursor + 1))
            try:
                stored = await self.kernel.emit_if_head(
                    admitted,
                    expected_head_sequence=projection.event_cursor,
                )
                return ReconsiderationAllocation.from_dict(stored.payload)
            except ConcurrentAppendError:
                continue

    async def _ensure_derived_governance(
        self,
        *,
        information_id: str,
        source_information_ids: tuple[str, ...],
        policy_ids: tuple[str, ...],
        recorded_at: datetime,
    ) -> None:
        sources = tuple(sorted(set(source_information_ids)))
        policies = tuple(sorted(set(policy_ids)))
        while True:
            history = await self._normalized_history()
            projection = ReconsiderationProjection()
            projection.rebuild(history)
            lineage = projection.information.lineage(information_id)
            if lineage is not None:
                if (
                    lineage.source_information_ids != sources
                    or lineage.transformation is not LineageTransformation.DERIVATION
                ):
                    raise ValueError("derived reconsideration lineage changed in place")
                break
            proposed_lineage = InformationLineage.create(
                information_id=information_id,
                source_information_ids=sources,
                transformation=LineageTransformation.DERIVATION,
                recorded_at=recorded_at,
            )
            lineage_event = proposed_lineage.to_event(source=self.source)
            admitted_lineage = replace(
                lineage_event,
                metadata={
                    **lineage_event.metadata,
                    "validated_at_event_cursor": projection.event_cursor,
                },
            )
            probe = ReconsiderationProjection()
            probe.rebuild(history)
            probe.apply(admitted_lineage.with_sequence(projection.event_cursor + 1))
            try:
                stored = await self.kernel.emit_if_head(
                    admitted_lineage,
                    expected_head_sequence=projection.event_cursor,
                )
                lineage = InformationLineage.from_event(stored)
                break
            except ConcurrentAppendError:
                continue

        while True:
            history = await self._normalized_history()
            projection = ReconsiderationProjection()
            projection.rebuild(history)
            binding = projection.information.binding(information_id)
            if binding is not None:
                if binding.lineage_id != lineage.lineage_id or binding.policy_ids != policies:
                    raise ValueError("derived reconsideration policy binding changed in place")
                return
            proposed_binding = PolicyBinding.create(
                information_id=information_id,
                lineage_id=lineage.lineage_id,
                policy_ids=policies,
                bound_at=recorded_at,
            )
            binding_event = proposed_binding.to_event(source=self.source)
            admitted_binding = replace(
                binding_event,
                metadata={
                    **binding_event.metadata,
                    "validated_at_event_cursor": projection.event_cursor,
                },
            )
            probe = ReconsiderationProjection()
            probe.rebuild(history)
            probe.apply(admitted_binding.with_sequence(projection.event_cursor + 1))
            try:
                await self.kernel.emit_if_head(
                    admitted_binding,
                    expected_head_sequence=projection.event_cursor,
                )
                return
            except ConcurrentAppendError:
                continue

    def _derived_information_id(self, *, namespace: str, stable_key: str) -> str:
        return self.derived_information_id_deriver.derive(
            namespace=namespace,
            stable_key=stable_key,
        )

    async def _canonical_foreground_refs(
        self,
        projection: ReconsiderationProjection,
        *,
        basis: CurrentCognitiveBasis,
        policy: ReconsiderationPolicySnapshot,
    ) -> tuple[str, ...]:
        cutoff = 0
        for allocation in projection.allocations:
            scan = projection.scan(allocation.scan_request_id)
            event = projection.event(
                f"reconsideration-allocation-recorded:{allocation.allocation_id}"
            )
            if (
                scan is not None
                and scan.basis.basis_id == basis.basis_id
                and event is not None
                and event.sequence is not None
            ):
                cutoff = max(cutoff, event.sequence)
        if cutoff == 0 and basis.mandate_revision_id is not None:
            mandate_event = projection.event(
                f"reconsideration-mandate-recorded:{basis.mandate_revision_id}"
            )
            if mandate_event is not None and mandate_event.sequence is not None:
                cutoff = mandate_event.sequence
        if cutoff == 0 and basis.live_intent_ref is not None:
            intent_event = projection.event(
                f"goal-revision-recorded:{basis.live_intent_ref.goal_revision_id}"
            )
            if intent_event is not None and intent_event.sequence is not None:
                cutoff = intent_event.sequence
        return tuple(
            f"event:{event.id}"
            for event in await self._normalized_history()
            if event.sequence is not None
            and event.sequence > cutoff
            and event.type in policy.foreground_event_types
        )

    @staticmethod
    def _latest_allocation_for_candidates(
        projection: ReconsiderationProjection,
        candidate_ids: tuple[str, ...],
    ) -> ReconsiderationAllocation | None:
        candidates = set(candidate_ids)
        matching = tuple(
            value
            for value in projection.allocations
            if candidates.intersection(decision.candidate_id for decision in value.decisions)
        )
        if not matching:
            return None

        def allocation_sequence(value: ReconsiderationAllocation) -> int:
            event = projection.event(f"reconsideration-allocation-recorded:{value.allocation_id}")
            return event.sequence or 0 if event is not None else 0

        return max(
            matching,
            key=allocation_sequence,
        )

    async def _admit_information_use(
        self,
        seed: ReconsiderationSeed,
        *,
        principal: PrincipalSnapshot,
        actor_id: str,
        purpose: str,
        source_trust_domain: str,
        locality: str,
        at: datetime,
    ) -> tuple[str, ...]:
        return await self.admit_information_use(
            seed.governed_information_ids,
            principal=principal,
            actor_id=actor_id,
            purpose=purpose,
            source_trust_domain=source_trust_domain,
            locality=locality,
            at=at,
        )

    @staticmethod
    def _historical_ref(
        projection: ReconsiderationProjection,
        inquiry: Inquiry,
        *,
        governed_information_ids: tuple[str, ...],
    ) -> HistoricalCognitionRef:
        event = projection.event(f"inquiry-recorded:{inquiry.inquiry_id}")
        if event is None:
            raise ValueError("historical Inquiry event is absent")
        return HistoricalCognitionRef(
            kind=HistoricalCognitionKind.INQUIRY,
            inquiry_id=inquiry.inquiry_id,
            epoch_id=str(event.payload["epoch_id"]),
            historical_causal_cursor=inquiry.causal_cursor,
            historical_governing_intent_refs=inquiry.governing_intent_refs,
            historical_evidence_refs=inquiry.evidence_refs,
            governed_information_ids=tuple(sorted(set(governed_information_ids))),
        )

    async def _append_exact(
        self,
        event: Event,
        *,
        authority_id: str | None = None,
    ) -> Event:
        while True:
            history = await self._normalized_history()
            projection = ReconsiderationProjection()
            projection.rebuild(history)
            existing = projection.event(event.id)
            if existing is not None:
                return existing
            metadata: dict[str, JSONValue] = dict(event.metadata)
            metadata["validated_at_event_cursor"] = projection.event_cursor
            if authority_id is not None:
                metadata["validated_mandate_authority_id"] = authority_id
            admitted = replace(event, metadata=metadata)

            # Validate the exact transition before it can enter the canonical store.
            probe = ReconsiderationProjection()
            probe.rebuild(history)
            probe.apply(admitted.with_sequence(projection.event_cursor + 1))
            try:
                return await self.kernel.emit_if_head(
                    admitted,
                    expected_head_sequence=projection.event_cursor,
                )
            except ConcurrentAppendError:
                continue

    async def _advance_checkpoint(
        self,
        trigger: Event,
        allocation_id: str,
    ) -> ConsumerCheckpoint:
        if trigger.sequence is None:
            raise ValueError("reconsideration checkpoint requires canonical scan")
        async with self._checkpoint_lock:
            history = await self._normalized_history()
            checkpoints = ConsumerCheckpointProjection()
            checkpoints.rebuild(history)
            current = checkpoints.get(self.consumer_id)
            if current is not None and current.last_completed_sequence >= trigger.sequence:
                return current
            candidate = ConsumerCheckpoint(
                consumer_id=self.consumer_id,
                last_completed_sequence=trigger.sequence,
                observed_head_sequence=max(
                    await self.kernel.store.latest_sequence(),
                    trigger.sequence,
                    current.observed_head_sequence if current else 0,
                ),
                epoch_id=allocation_id,
            )
            stored = await self.kernel.emit(
                candidate.to_event(
                    source=self.source,
                    timestamp=trigger.timestamp,
                    causation_id=trigger.id,
                )
            )
            return ConsumerCheckpoint.from_event(stored)

    async def _normalized_history(self) -> list[Event]:
        return [self.kernel.schemas.normalize(event) for event in await self.kernel.history()]
