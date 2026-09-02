"""Crash-recoverable, proposal-only worker for historical Inquiry reconsideration."""

from __future__ import annotations

import asyncio
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
    InformationOperation,
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
        consumer_id: str = "cognitive-reconsideration-shadow",
        source: str = "reconsideration:shadow-worker",
    ) -> None:
        if not consumer_id.strip() or not source.strip():
            raise ValueError("reconsideration worker ids must be non-empty")
        self.kernel = kernel
        self.authority = authority
        self.policy = policy or ReconsiderationPolicySnapshot.create(version="deterministic-v1")
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
        requested_at: datetime | None = None,
        budget: ScarceCognitionBudget | None = None,
        information_use_purpose: str | None = None,
        information_policy_ids: tuple[str, ...] | None = None,
        trigger_event_id: str | None = None,
        foreground_demand_refs: tuple[str, ...] = (),
    ) -> ReconsiderationAllocation | None:
        """Revalidate explicit historical Inquiry seeds under one current basis."""

        if not seeds:
            raise ValueError("reconsideration scan requires historical Inquiry seeds")
        if not self.kernel.started:
            await self.kernel.start()
        at = requested_at or utc_now()
        projection = await self.current_projection()
        mandate = None
        if basis.kind is CognitiveBasisKind.RECONSIDERATION_MANDATE:
            assert basis.mandate_revision_id is not None
            mandate = projection.mandates.revision(basis.mandate_revision_id)
            if mandate is None:
                raise ValueError("reconsideration scan references an unknown mandate")
            effective_budget = budget or mandate.budget
            purpose = information_use_purpose or mandate.information_use_purpose
            policies = information_policy_ids or mandate.information_policy_ids
        else:
            if budget is None or information_use_purpose is None or information_policy_ids is None:
                raise ValueError(
                    "live-intent reconsideration requires explicit budget and information policy"
                )
            effective_budget = budget
            purpose = information_use_purpose
            policies = information_policy_ids

        novel_seeds = tuple(
            seed
            for seed in seeds
            if projection.find_candidate(
                inquiry_id=seed.inquiry_id,
                basis_id=basis.basis_id,
                current_evidence_refs=seed.current_evidence_refs,
                domain=seed.domain,
                governed_information_ids=seed.governed_information_ids,
                features=seed.features,
                costs=seed.costs,
            )
            is None
        )
        if not novel_seeds:
            existing = projection.find_candidate(
                inquiry_id=seeds[0].inquiry_id,
                basis_id=basis.basis_id,
                current_evidence_refs=seeds[0].current_evidence_refs,
                domain=seeds[0].domain,
                governed_information_ids=seeds[0].governed_information_ids,
                features=seeds[0].features,
                costs=seeds[0].costs,
            )
            if existing is None:  # pragma: no cover - guarded by the filter above
                return None
            return projection.allocation_for_scan(existing.scan_request_id)

        await self.kernel.emit(self.policy.to_event(source=self.source, recorded_at=at))
        candidate_inputs: list[ReconsiderationCandidateInput] = []
        for seed in novel_seeds:
            decisions = await self._admit_information_use(
                seed,
                principal=principal,
                actor_id=actor_id,
                purpose=purpose,
                source_trust_domain=source_trust_domain,
                locality=locality,
                at=at,
            )
            candidate_inputs.append(
                ReconsiderationCandidateInput(
                    seed=seed,
                    information_access_decision_ids=tuple(decisions),
                )
            )
        scan = ReconsiderationScanRequest.create(
            basis=basis,
            policy_id=self.policy.policy_id,
            budget=effective_budget,
            candidate_inputs=tuple(candidate_inputs),
            information_use_purpose=purpose,
            information_policy_ids=tuple(sorted(set(policies))),
            requested_at=at,
            trigger_event_id=trigger_event_id,
            foreground_demand_refs=foreground_demand_refs,
        )
        stored = await self._append_exact(scan.to_event(source=self.source))
        return await self._process_scan(stored)

    async def recover(self) -> tuple[ReconsiderationAllocation, ...]:
        history = await self._normalized_history()
        checkpoints = ConsumerCheckpointProjection()
        checkpoints.rebuild(history)
        checkpoint = checkpoints.get(self.consumer_id)
        after = checkpoint.last_completed_sequence if checkpoint else 0
        recovered: list[ReconsiderationAllocation] = []
        for event in history:
            if event.sequence is None or event.sequence <= after:
                continue
            if event.type != SCAN_REQUESTED_EVENT:
                continue
            allocation = await self._process_scan(event)
            if allocation is not None:
                recovered.append(allocation)
        return tuple(recovered)

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

    async def _process_scan(self, scan_event: Event) -> ReconsiderationAllocation | None:
        if scan_event.sequence is None:
            raise ValueError("reconsideration scan must be canonical")
        scan = ReconsiderationScanRequest.from_dict(scan_event.payload)
        projection = await self.current_projection()
        existing = projection.allocation_for_scan(scan.request_id)
        if existing is not None:
            await self._advance_checkpoint(scan_event, existing.allocation_id)
            return existing

        for candidate_input in scan.candidate_inputs:
            seed = candidate_input.seed
            inquiry = projection.endogenous.inquiry(seed.inquiry_id)
            if inquiry is None:
                raise ValueError("reconsideration seed references an unknown Inquiry")
            historical = self._historical_ref(
                projection,
                inquiry,
                governed_information_ids=seed.governed_information_ids,
            )
            candidate = ReconsiderationCandidate.create(
                scan_request_id=scan.request_id,
                historical=historical,
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
        candidates = projection.candidates_for_scan(scan.request_id)
        policy = projection.policy(scan.policy_id)
        if policy is None:
            raise ValueError("reconsideration scan lost its pinned policy")
        allocation = allocate_reconsideration(
            scan=scan,
            policy=policy,
            candidates=candidates,
            allocated_at=scan.requested_at,
        )
        stored_allocation = await self._append_exact(allocation.to_event(source=self.source))
        allocation = ReconsiderationAllocation.from_dict(stored_allocation.payload)

        projection = await self.current_projection()
        by_id = {
            value.candidate_id: value for value in projection.candidates_for_scan(scan.request_id)
        }
        for decision in allocation.decisions:
            candidate = by_id[decision.candidate_id]
            trace = CognitiveAllocationTrace.create(
                allocation=allocation,
                candidate=candidate,
                decision=decision,
            )
            await self._append_exact(trace.to_event(source=self.source))
            if decision.label is not AllocationLabel.SELECTED:
                continue
            inquiry = projection.endogenous.inquiry(candidate.historical.inquiry_id)
            if inquiry is None:  # pragma: no cover - validated by canonical projection
                raise AssertionError("selected reconsideration lost historical inquiry")
            proposal = ReconsiderationShadowProposal.create(
                candidate=candidate,
                allocation=allocation,
                trace=trace,
                historical_question=inquiry.question,
            )
            await self._append_exact(proposal.to_event(source=self.source))
        await self._advance_checkpoint(scan_event, allocation.allocation_id)
        return allocation

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
        decision_ids: list[str] = []
        for information_id in seed.governed_information_ids:
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
