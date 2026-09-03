"""Crash-recoverable worker from dormant discovery to v0.6.1 allocation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

from .checkpoints import ConsumerCheckpoint, ConsumerCheckpointProjection
from .events import Event
from .information import OpaqueInformationIdDeriver, PrincipalSnapshot
from .kernel import NoemaKernel
from .reconsideration.discovery import (
    DeterministicDormantInquiryDetector,
    DeterministicReconsiderationSeedAssembler,
    DiscoveryNomination,
    ReconsiderationDiscoveryAuthority,
)
from .reconsideration.discovery_models import (
    EVIDENCE_QUALIFICATION_BOUND_EVENT,
    EvidenceQualificationBinding,
    EvidenceQualificationRole,
    InquiryReconsiderationScopeBinding,
    ReconsiderationDiscoveryPolicySnapshot,
    ReconsiderationOpportunity,
    allocation_context_fingerprint,
)
from .reconsideration.discovery_projection import ReconsiderationDiscoveryProjection
from .reconsideration.models import (
    CognitiveBasisKind,
    CurrentCognitiveBasis,
    ReconsiderationAllocation,
    ReconsiderationSeed,
    ScarceCognitionBudget,
)
from .reconsideration.projection import ReconsiderationProjection
from .reconsideration_worker import ReconsiderationShadowWorker
from .store import ConcurrentAppendError
from .types import JSONValue, utc_now


@dataclass(frozen=True, slots=True)
class DiscoveryRunResult:
    trigger_event_id: str
    opportunities: tuple[ReconsiderationOpportunity, ...]
    seeds: tuple[ReconsiderationSeed, ...]
    allocation: ReconsiderationAllocation | None


class ReconsiderationDiscoveryWorker:
    """Nominate dormant Inquiries and delegate allocation to the v0.6.1 worker."""

    def __init__(
        self,
        kernel: NoemaKernel,
        *,
        reconsideration_worker: ReconsiderationShadowWorker,
        authority: ReconsiderationDiscoveryAuthority,
        derived_information_id_deriver: OpaqueInformationIdDeriver,
        policy: ReconsiderationDiscoveryPolicySnapshot | None = None,
        clock: Callable[[], datetime] = utc_now,
        detector: DeterministicDormantInquiryDetector | None = None,
        seed_assembler: DeterministicReconsiderationSeedAssembler | None = None,
        consumer_id: str = "dormant-cognition-discovery",
        source: str = "reconsideration:discovery-worker",
    ) -> None:
        if kernel is not reconsideration_worker.kernel:
            raise ValueError("discovery and allocation workers must share one canonical kernel")
        if not consumer_id.strip() or not source.strip():
            raise ValueError("discovery worker ids must be non-empty")
        self.kernel = kernel
        self.reconsideration_worker = reconsideration_worker
        self.authority = authority
        self.derived_information_id_deriver = derived_information_id_deriver
        self.policy = policy or ReconsiderationDiscoveryPolicySnapshot.create(
            version="deterministic-v1"
        )
        if (
            self.policy.foreground_event_types
            != self.reconsideration_worker.policy.foreground_event_types
        ):
            raise ValueError("discovery and allocation foreground policies must match")
        self.clock = clock
        self.detector = detector or DeterministicDormantInquiryDetector()
        self.seed_assembler = seed_assembler or DeterministicReconsiderationSeedAssembler()
        self.consumer_id = consumer_id
        self.source = source
        self._checkpoint_lock = asyncio.Lock()

    async def record_policy(self) -> ReconsiderationDiscoveryPolicySnapshot:
        stored = await self.kernel.emit(
            self.policy.to_event(source=self.source, recorded_at=self._now())
        )
        return ReconsiderationDiscoveryPolicySnapshot.from_dict(stored.payload)

    async def bind_inquiry_scope(
        self,
        *,
        inquiry_id: str,
        domain_ids: tuple[str, ...],
        governed_information_ids: tuple[str, ...],
        evidence_refs: tuple[str, ...],
        resolver_id: str,
        resolver_version: str,
        authorization_ref: str,
        information_use_purpose: str,
        information_policy_ids: tuple[str, ...],
        principal: PrincipalSnapshot,
        actor_id: str,
        source_trust_domain: str,
        locality: str,
        bound_at: datetime | None = None,
    ) -> InquiryReconsiderationScopeBinding:
        await self.record_policy()
        at = bound_at or self._now()
        decisions = await self.reconsideration_worker.admit_information_use(
            governed_information_ids,
            principal=principal,
            actor_id=actor_id,
            purpose=information_use_purpose,
            source_trust_domain=source_trust_domain,
            locality=locality,
            at=at,
        )
        stable_key = _stable_key(
            {
                "inquiry_id": inquiry_id,
                "domain_ids": list(tuple(sorted(set(domain_ids)))),
                "governed_information_ids": list(tuple(sorted(set(governed_information_ids)))),
                "resolver_id": resolver_id,
                "resolver_version": resolver_version,
                "authorization_ref": authorization_ref,
            }
        )
        information_id = self._derived_information_id(
            namespace="reconsideration-scope-binding",
            stable_key=stable_key,
        )
        await self.reconsideration_worker.ensure_derived_governance(
            information_id=information_id,
            source_information_ids=governed_information_ids,
            policy_ids=information_policy_ids,
            recorded_at=at,
        )
        binding = InquiryReconsiderationScopeBinding.create(
            inquiry_id=inquiry_id,
            domain_ids=domain_ids,
            governed_information_ids=governed_information_ids,
            evidence_refs=tuple(sorted({*evidence_refs, authorization_ref})),
            resolver_id=resolver_id,
            resolver_version=resolver_version,
            authority_id=self.authority.authority_id,
            authorization_ref=authorization_ref,
            derived_information_id=information_id,
            information_use_purpose=information_use_purpose,
            information_policy_ids=information_policy_ids,
            information_access_decision_ids=decisions,
            bound_at=at,
        )
        if not self.authority.authenticates_scope(binding):
            raise PermissionError("Inquiry scope resolver is not authenticated")
        stored = await self._append_exact(
            binding.to_event(source=self.source),
            authority_id=self.authority.authority_id,
        )
        return InquiryReconsiderationScopeBinding.from_dict(stored.payload)

    async def bind_evidence_qualification(
        self,
        *,
        assertion_ref: str,
        role: EvidenceQualificationRole,
        target_refs: tuple[str, ...],
        qualifier_id: str,
        qualifier_version: str,
        authorization_ref: str,
        governed_information_ids: tuple[str, ...],
        information_use_purpose: str,
        information_policy_ids: tuple[str, ...],
        principal: PrincipalSnapshot,
        actor_id: str,
        source_trust_domain: str,
        locality: str,
        bound_at: datetime | None = None,
    ) -> EvidenceQualificationBinding:
        await self.record_policy()
        at = bound_at or self._now()
        decisions = await self.reconsideration_worker.admit_information_use(
            governed_information_ids,
            principal=principal,
            actor_id=actor_id,
            purpose=information_use_purpose,
            source_trust_domain=source_trust_domain,
            locality=locality,
            at=at,
        )
        stable_key = _stable_key(
            {
                "assertion_ref": assertion_ref,
                "role": role.value,
                "target_refs": list(tuple(sorted(set(target_refs)))),
                "qualifier_id": qualifier_id,
                "qualifier_version": qualifier_version,
                "authorization_ref": authorization_ref,
            }
        )
        information_id = self._derived_information_id(
            namespace="reconsideration-evidence-binding",
            stable_key=stable_key,
        )
        await self.reconsideration_worker.ensure_derived_governance(
            information_id=information_id,
            source_information_ids=governed_information_ids,
            policy_ids=information_policy_ids,
            recorded_at=at,
        )
        binding = EvidenceQualificationBinding.create(
            assertion_ref=assertion_ref,
            role=role,
            target_refs=target_refs,
            qualifier_id=qualifier_id,
            qualifier_version=qualifier_version,
            authority_id=self.authority.authority_id,
            authorization_ref=authorization_ref,
            governed_information_ids=governed_information_ids,
            derived_information_id=information_id,
            information_use_purpose=information_use_purpose,
            information_policy_ids=information_policy_ids,
            information_access_decision_ids=decisions,
            bound_at=at,
        )
        if not self.authority.authenticates_qualification(binding):
            raise PermissionError("evidence qualification authority is not authenticated")
        stored = await self._append_exact(
            binding.to_event(source=self.source),
            authority_id=self.authority.authority_id,
        )
        return EvidenceQualificationBinding.from_dict(stored.payload)

    async def run_trigger(
        self,
        *,
        trigger_event_id: str,
        basis: CurrentCognitiveBasis,
        principal: PrincipalSnapshot,
        actor_id: str,
        source_trust_domain: str,
        locality: str,
        budget: ScarceCognitionBudget | None = None,
        information_use_purpose: str | None = None,
        information_policy_ids: tuple[str, ...] | None = None,
    ) -> DiscoveryRunResult:
        if not self.kernel.started:
            await self.kernel.start()
        await self.record_policy()
        history = await self._normalized_history()
        trigger = next((event for event in history if event.id == trigger_event_id), None)
        if trigger is None or trigger.sequence is None:
            raise ValueError("discovery trigger is not canonical")

        evaluation = ReconsiderationDiscoveryProjection()
        evaluation.rebuild(history, through_sequence=trigger.sequence)
        effective_budget, interruption, purpose, policies = self._effective_context(
            evaluation.reconsideration,
            basis=basis,
            budget=budget,
            information_use_purpose=information_use_purpose,
            information_policy_ids=information_policy_ids,
            at=trigger.timestamp,
            trigger_type=trigger.type,
        )
        foreground = await self.reconsideration_worker.canonical_foreground_refs(
            evaluation.reconsideration,
            basis=basis,
        )
        nominations = self.detector.discover(
            endogenous=evaluation.endogenous,
            reconsideration=evaluation.reconsideration,
            memory=evaluation.memory,
            trigger=trigger,
            basis=basis,
            policy=self.policy,
            scope_bindings=evaluation.scope_bindings,
            qualification_bindings=evaluation.qualification_bindings,
            current_budget=effective_budget,
            current_maximum_interruption_units=interruption,
            current_foreground_refs=foreground,
            canonical_events=tuple(
                event for event in history if (event.sequence or 0) <= trigger.sequence
            ),
            at=trigger.timestamp,
        )
        opportunities: list[ReconsiderationOpportunity] = []
        for nomination in nominations:
            opportunity = await self._admit_opportunity(
                nomination,
                trigger=trigger,
                basis=basis,
                principal=principal,
                actor_id=actor_id,
                source_trust_domain=source_trust_domain,
                locality=locality,
                information_use_purpose=purpose,
                information_policy_ids=policies,
            )
            opportunities.append(opportunity)

        projection = await self.current_projection()
        if not opportunities:
            opportunities = list(projection.opportunities_for_trigger(trigger.id))
        seeds: list[ReconsiderationSeed] = []
        for opportunity in opportunities:
            inquiry = projection.endogenous.inquiry(opportunity.historical_inquiry_id)
            scope = projection.scope_binding(opportunity.scope_binding_id)
            if inquiry is None or scope is None:
                raise ValueError("admitted opportunity lost its canonical sources")
            qualifications = tuple(
                projection.qualification(value) for value in opportunity.qualification_ids
            )
            if any(value is None for value in qualifications):
                raise ValueError("admitted opportunity lost a qualification binding")
            domain = self._domain_for(opportunity, scope, projection.reconsideration)
            seeds.append(
                self.seed_assembler.assemble(
                    opportunity=opportunity,
                    inquiry=inquiry,
                    scope=scope,
                    qualifications=tuple(value for value in qualifications if value is not None),
                    memory=projection.memory,
                    reconsideration=projection.reconsideration,
                    domain=domain,
                )
            )

        allocation = await self._handoff(
            trigger=trigger,
            basis=basis,
            seeds=tuple(seeds),
            principal=principal,
            actor_id=actor_id,
            source_trust_domain=source_trust_domain,
            locality=locality,
            budget=budget,
            information_use_purpose=information_use_purpose,
            information_policy_ids=information_policy_ids,
            opportunities=tuple(opportunities),
        )
        if trigger.type in self._recognized_trigger_types():
            await self._advance_checkpoint(
                trigger,
                opportunities[-1].opportunity_id if opportunities else None,
            )
        return DiscoveryRunResult(
            trigger_event_id=trigger.id,
            opportunities=tuple(opportunities),
            seeds=tuple(seeds),
            allocation=allocation,
        )

    async def recover(
        self,
        *,
        principal: PrincipalSnapshot,
        actor_id: str,
        source_trust_domain: str,
        locality: str,
    ) -> tuple[DiscoveryRunResult, ...]:
        """Resume after the checkpoint while auditing older partial handoffs."""

        history = await self._normalized_history()
        projection = ReconsiderationDiscoveryProjection()
        projection.rebuild(history)
        checkpoints = ConsumerCheckpointProjection()
        checkpoints.rebuild(history)
        checkpoint = checkpoints.get(self.consumer_id)
        lower_bound = checkpoint.last_completed_sequence if checkpoint is not None else 0
        recognized_types = self._recognized_trigger_types()
        recovery_time = self._now()
        trigger_ids = {
            event.id
            for event in history
            if event.type in recognized_types and (event.sequence or 0) > lower_bound
        }
        for trigger_id in {value.trigger_event_id for value in projection.opportunities}:
            opportunities = projection.opportunities_for_trigger(trigger_id)
            allocation = self._existing_allocation(projection.reconsideration, opportunities)
            basis_is_current = any(
                projection.reconsideration.basis_is_current(
                    value.current_cognitive_basis,
                    at=recovery_time,
                )
                for value in opportunities
            )
            if allocation is None:
                if basis_is_current:
                    trigger_ids.add(trigger_id)
                continue
            scan = projection.reconsideration.scan(allocation.scan_request_id)
            if scan is None:  # pragma: no cover - allocation replay enforces this relation
                raise AssertionError("reconsideration allocation lost its originating scan")
            if not self.reconsideration_worker.scan_outputs_complete(
                projection.reconsideration,
                scan,
                at=recovery_time,
            ):
                await self.reconsideration_worker.recover()
                projection = await self.current_projection()
        recovered: list[DiscoveryRunResult] = []

        def trigger_sequence(event_id: str) -> int:
            event = projection.event(event_id)
            return event.sequence or 0 if event is not None else 0

        for trigger_id in sorted(trigger_ids, key=trigger_sequence):
            existing = projection.opportunities_for_trigger(trigger_id)
            basis = (
                existing[0].current_cognitive_basis
                if existing
                else self._recoverable_basis(
                    projection,
                    trigger_id,
                )
            )
            if basis is None:
                continue
            try:
                result = await self.run_trigger(
                    trigger_event_id=trigger_id,
                    basis=basis,
                    principal=principal,
                    actor_id=actor_id,
                    source_trust_domain=source_trust_domain,
                    locality=locality,
                )
            except (PermissionError, ValueError):
                continue
            if result.opportunities:
                recovered.append(result)
                projection = await self.current_projection()
        return tuple(recovered)

    def _recognized_trigger_types(self) -> set[str]:
        return {
            *self.policy.explicit_user_event_types,
            *self.policy.explicit_relevance_event_types,
            *self.policy.opportunity_event_types,
            EVIDENCE_QUALIFICATION_BOUND_EVENT,
            "intent.goal_revision_recorded",
            "rule.evaluation_traced",
        }

    async def current_projection(self) -> ReconsiderationDiscoveryProjection:
        projection = ReconsiderationDiscoveryProjection()
        projection.rebuild(await self._normalized_history())
        return projection

    async def _admit_opportunity(
        self,
        nomination: DiscoveryNomination,
        *,
        trigger: Event,
        basis: CurrentCognitiveBasis,
        principal: PrincipalSnapshot,
        actor_id: str,
        source_trust_domain: str,
        locality: str,
        information_use_purpose: str,
        information_policy_ids: tuple[str, ...],
    ) -> ReconsiderationOpportunity:
        governed_sources = {
            *nomination.scope_binding.governed_information_ids,
            *(
                item
                for value in nomination.qualifications
                for item in value.governed_information_ids
            ),
        }
        at = self._now()
        decisions = await self.reconsideration_worker.admit_information_use(
            tuple(sorted(governed_sources)),
            principal=principal,
            actor_id=actor_id,
            purpose=information_use_purpose,
            source_trust_domain=source_trust_domain,
            locality=locality,
            at=at,
        )
        stable_key = _stable_key(
            {
                "inquiry_id": nomination.descriptor.inquiry_id,
                "basis_id": basis.basis_id,
                "kind": nomination.kind.value,
                "reasons": [value.value for value in nomination.reasons],
                "trigger_event_id": trigger.id,
                "scope_binding_id": nomination.scope_binding.binding_id,
                "qualification_ids": [
                    value.qualification_id for value in nomination.qualifications
                ],
                "existing_candidate_id": nomination.existing_candidate_id,
                "allocation_context_fingerprint": (nomination.allocation_context_fingerprint),
                "discovery_policy_id": self.policy.policy_id,
                "seed_policy_version": self.policy.seed_policy_version,
                "seed_costs": self.policy.seed_costs.to_dict(),
            }
        )
        information_id = self._derived_information_id(
            namespace="reconsideration-opportunity",
            stable_key=stable_key,
        )
        lineage_sources = (
            nomination.scope_binding.derived_information_id,
            *(value.derived_information_id for value in nomination.qualifications),
        )
        await self.reconsideration_worker.ensure_derived_governance(
            information_id=information_id,
            source_information_ids=lineage_sources,
            policy_ids=information_policy_ids,
            recorded_at=at,
        )
        while True:
            history = await self._normalized_history()
            projection = ReconsiderationDiscoveryProjection()
            projection.rebuild(history)
            opportunity = ReconsiderationOpportunity.create(
                historical_inquiry_id=nomination.descriptor.inquiry_id,
                current_cognitive_basis=basis,
                kind=nomination.kind,
                discovery_reasons=nomination.reasons,
                trigger_event_id=trigger.id,
                evidence_refs=nomination.evidence_refs,
                scope_binding_id=nomination.scope_binding.binding_id,
                qualification_ids=tuple(
                    value.qualification_id for value in nomination.qualifications
                ),
                existing_candidate_id=nomination.existing_candidate_id,
                allocation_context_fingerprint=nomination.allocation_context_fingerprint,
                discovery_policy_id=self.policy.policy_id,
                evaluation_cut=trigger.sequence or 0,
                admitted_at_head=projection.event_cursor,
                created_at=at,
                derived_information_id=information_id,
                seed_policy_version=self.policy.seed_policy_version,
                seed_costs=self.policy.seed_costs,
                information_use_purpose=information_use_purpose,
                information_policy_ids=information_policy_ids,
                information_access_decision_ids=decisions,
            )
            event = opportunity.to_event(source=self.source)
            existing = projection.event(event.id)
            if existing is not None:
                return ReconsiderationOpportunity.from_dict(existing.payload)
            admitted = replace(
                event,
                metadata={
                    **event.metadata,
                    "validated_at_event_cursor": projection.event_cursor,
                },
            )
            probe = ReconsiderationDiscoveryProjection()
            probe.rebuild(history)
            probe.apply(admitted.with_sequence(projection.event_cursor + 1))
            try:
                stored = await self.kernel.emit_if_head(
                    admitted,
                    expected_head_sequence=projection.event_cursor,
                )
                return ReconsiderationOpportunity.from_dict(stored.payload)
            except ConcurrentAppendError:
                continue

    async def _handoff(
        self,
        *,
        trigger: Event,
        basis: CurrentCognitiveBasis,
        seeds: tuple[ReconsiderationSeed, ...],
        principal: PrincipalSnapshot,
        actor_id: str,
        source_trust_domain: str,
        locality: str,
        budget: ScarceCognitionBudget | None,
        information_use_purpose: str | None,
        information_policy_ids: tuple[str, ...] | None,
        opportunities: tuple[ReconsiderationOpportunity, ...],
    ) -> ReconsiderationAllocation | None:
        if not seeds:
            return None
        current = await self.reconsideration_worker.current_projection()
        existing = self._existing_allocation(current, opportunities)
        if existing is not None:
            await self.reconsideration_worker.recover()
            refreshed = await self.reconsideration_worker.current_projection()
            return self._existing_allocation(refreshed, opportunities) or existing
        handoff_trigger: str | None = None
        if basis.kind is CognitiveBasisKind.RECONSIDERATION_MANDATE:
            assert basis.mandate_revision_id is not None
            mandate = current.mandates.revision(basis.mandate_revision_id)
            if mandate is not None and mandate.trigger_event_types:
                handoff_trigger = trigger.id
        try:
            return await self.reconsideration_worker.run_scan(
                basis=basis,
                seeds=seeds,
                principal=principal,
                actor_id=actor_id,
                source_trust_domain=source_trust_domain,
                locality=locality,
                budget=budget,
                information_use_purpose=information_use_purpose,
                information_policy_ids=information_policy_ids,
                trigger_event_id=handoff_trigger,
            )
        except ValueError as error:
            if "trigger was already consumed" not in str(error):
                raise
            await self.reconsideration_worker.recover()
            refreshed = await self.reconsideration_worker.current_projection()
            return self._existing_allocation(refreshed, opportunities)

    @staticmethod
    def _existing_allocation(
        projection: ReconsiderationProjection,
        opportunities: tuple[ReconsiderationOpportunity, ...],
    ) -> ReconsiderationAllocation | None:
        candidate_floors: dict[str, int] = {}
        for opportunity in opportunities:
            event = projection.event(
                f"reconsideration-opportunity-recorded:{opportunity.opportunity_id}"
            )
            floor = event.sequence if event is not None and event.sequence is not None else 0
            if opportunity.existing_candidate_id is not None:
                candidate_floors[opportunity.existing_candidate_id] = floor
                continue
            opportunity_ref = (
                f"event:reconsideration-opportunity-recorded:{opportunity.opportunity_id}"
            )
            for candidate in projection.candidates:
                if opportunity_ref in candidate.current_evidence_refs:
                    candidate_floors[candidate.candidate_id] = floor
        matching = tuple(
            allocation
            for allocation in projection.allocations
            if (
                allocation_event := projection.event(
                    f"reconsideration-allocation-recorded:{allocation.allocation_id}"
                )
            )
            is not None
            if any(
                decision.candidate_id in candidate_floors
                and (allocation_event.sequence or 0) > candidate_floors[decision.candidate_id]
                for decision in allocation.decisions
            )
        )
        if not matching:
            return None

        def allocation_sequence(value: ReconsiderationAllocation) -> int:
            event = projection.event(f"reconsideration-allocation-recorded:{value.allocation_id}")
            return event.sequence if event is not None and event.sequence is not None else 0

        return max(matching, key=allocation_sequence)

    def _effective_context(
        self,
        projection: ReconsiderationProjection,
        *,
        basis: CurrentCognitiveBasis,
        budget: ScarceCognitionBudget | None,
        information_use_purpose: str | None,
        information_policy_ids: tuple[str, ...] | None,
        at: datetime,
        trigger_type: str,
    ) -> tuple[ScarceCognitionBudget, float, str, tuple[str, ...]]:
        if not projection.basis_is_current(basis, at=at):
            raise ValueError("discovery requires a current cognitive basis at its trigger cut")
        if basis.kind is CognitiveBasisKind.RECONSIDERATION_MANDATE:
            assert basis.mandate_revision_id is not None
            mandate = projection.mandates.revision(basis.mandate_revision_id)
            if mandate is None:
                raise ValueError("discovery references an unknown mandate")
            if mandate.trigger_event_types and trigger_type not in mandate.trigger_event_types:
                raise ValueError("discovery trigger is outside its mandate")
            return (
                budget or mandate.budget,
                mandate.maximum_interruption_units,
                information_use_purpose or mandate.information_use_purpose,
                information_policy_ids or mandate.information_policy_ids,
            )
        if budget is None or information_use_purpose is None or information_policy_ids is None:
            raise ValueError(
                "live-intent discovery requires explicit budget and information policy"
            )
        return (
            budget,
            budget.ceiling.interruption_units,
            information_use_purpose,
            tuple(sorted(set(information_policy_ids))),
        )

    @staticmethod
    def _domain_for(
        opportunity: ReconsiderationOpportunity,
        scope: InquiryReconsiderationScopeBinding,
        projection: ReconsiderationProjection,
    ) -> str:
        if opportunity.current_cognitive_basis.kind is CognitiveBasisKind.RECONSIDERATION_MANDATE:
            revision_id = opportunity.current_cognitive_basis.mandate_revision_id
            assert revision_id is not None
            mandate = projection.mandates.revision(revision_id)
            if mandate is None:
                raise ValueError("seed assembly lost its mandate")
            domains = set(scope.domain_ids).intersection(mandate.candidate_domains)
        else:
            domains = set(scope.domain_ids)
        if len(domains) != 1:
            raise ValueError("seed assembly requires exactly one classified domain")
        return next(iter(domains))

    def _recoverable_basis(
        self,
        projection: ReconsiderationDiscoveryProjection,
        trigger_event_id: str,
    ) -> CurrentCognitiveBasis | None:
        trigger = projection.event(trigger_event_id)
        if trigger is None:
            return None
        active = tuple(
            value
            for value in projection.reconsideration.mandates.mandates
            if (not value.trigger_event_types or trigger.type in value.trigger_event_types)
            and projection.reconsideration.mandates.is_active_revision(
                value.revision_id,
                at=trigger.timestamp,
            )
        )
        if len(active) != 1:
            return None
        return CurrentCognitiveBasis.from_mandate(active[0].revision_id)

    async def _append_exact(
        self,
        event: Event,
        *,
        authority_id: str,
    ) -> Event:
        while True:
            history = await self._normalized_history()
            projection = ReconsiderationDiscoveryProjection()
            projection.rebuild(history)
            existing = projection.event(event.id)
            if existing is not None:
                return existing
            metadata: dict[str, JSONValue] = dict(event.metadata)
            metadata["validated_at_event_cursor"] = projection.event_cursor
            metadata["validated_discovery_authority_id"] = authority_id
            admitted = replace(event, metadata=metadata)
            probe = ReconsiderationDiscoveryProjection()
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
        opportunity_id: str | None,
    ) -> ConsumerCheckpoint:
        if trigger.sequence is None:
            raise ValueError("discovery checkpoint requires a canonical trigger")
        async with self._checkpoint_lock:
            history = await self._normalized_history()
            checkpoints = ConsumerCheckpointProjection()
            checkpoints.rebuild(history)
            current = checkpoints.get(self.consumer_id)
            if current is not None and current.last_completed_sequence >= trigger.sequence:
                return current
            checkpoint = ConsumerCheckpoint(
                consumer_id=self.consumer_id,
                last_completed_sequence=trigger.sequence,
                observed_head_sequence=max(
                    await self.kernel.store.latest_sequence(),
                    trigger.sequence,
                    current.observed_head_sequence if current else 0,
                ),
                epoch_id=opportunity_id or f"trigger:{trigger.id}",
            )
            stored = await self.kernel.emit(
                checkpoint.to_event(
                    source=self.source,
                    timestamp=trigger.timestamp,
                    causation_id=trigger.id,
                )
            )
            return ConsumerCheckpoint.from_event(stored)

    def _derived_information_id(self, *, namespace: str, stable_key: str) -> str:
        return self.derived_information_id_deriver.derive(
            namespace=namespace,
            stable_key=stable_key,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("discovery worker clock must be timezone-aware")
        return value

    async def _normalized_history(self) -> list[Event]:
        return [self.kernel.schemas.normalize(event) for event in await self.kernel.history()]


def _stable_key(payload: dict[str, JSONValue]) -> str:
    return allocation_context_fingerprint(payload)
