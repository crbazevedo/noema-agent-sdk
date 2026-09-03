"""Deterministic discovery and seed assembly for dormant historical Inquiries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..autonomic.models import AutonomicRule, Signal
from ..endogenous.models import Inquiry
from ..endogenous.projection import EndogenousProjection
from ..events import Event
from ..memory.models import EpistemicType, SemanticAssertion
from ..memory.projection import MemoryProjection
from ..situation import GoalStatus
from .discovery_models import (
    DETERMINISTIC_DISCOVERY_SEED_POLICY_VERSION,
    EVIDENCE_QUALIFICATION_BOUND_EVENT,
    DiscoveryReason,
    DormancyReason,
    DormantInquiryDescriptor,
    EvidenceQualificationBinding,
    EvidenceQualificationRole,
    InquiryReconsiderationScopeBinding,
    ReconsiderationDiscoveryPolicySnapshot,
    ReconsiderationOpportunity,
    ReconsiderationOpportunityKind,
    allocation_context_fingerprint,
    numeric_assertion_value,
)
from .models import (
    AllocationLabel,
    CognitiveBasisKind,
    CurrentCognitiveBasis,
    EstimateEvidenceKind,
    EvidenceBackedEstimate,
    ReconsiderationCandidate,
    ReconsiderationFeatureSnapshot,
    ReconsiderationSeed,
    ScarceCognitionBudget,
)
from .projection import ReconsiderationProjection


class ReconsiderationDiscoveryAuthority(Protocol):
    @property
    def authority_id(self) -> str: ...

    def authenticates_scope(self, binding: InquiryReconsiderationScopeBinding) -> bool: ...

    def authenticates_qualification(self, binding: EvidenceQualificationBinding) -> bool: ...


@dataclass(frozen=True, slots=True)
class StaticReconsiderationDiscoveryAuthority:
    """Narrow deterministic authority fixture for scope and role bindings."""

    authority_id: str
    scope_resolvers: tuple[tuple[str, str], ...]
    qualification_resolvers: tuple[tuple[str, str], ...]
    qualification_roles: tuple[EvidenceQualificationRole, ...]

    def __post_init__(self) -> None:
        if not self.authority_id.strip():
            raise ValueError("discovery authority id must be non-empty")
        if not self.scope_resolvers or not self.qualification_resolvers:
            raise ValueError("discovery authority requires explicit resolver versions")
        if not self.qualification_roles:
            raise ValueError("discovery authority requires explicit qualification roles")
        if len(set(self.scope_resolvers)) != len(self.scope_resolvers):
            raise ValueError("scope resolver versions must be unique")
        if len(set(self.qualification_resolvers)) != len(self.qualification_resolvers):
            raise ValueError("qualification resolver versions must be unique")
        if len(set(self.qualification_roles)) != len(self.qualification_roles):
            raise ValueError("qualification authority roles must be unique")

    def authenticates_scope(self, binding: InquiryReconsiderationScopeBinding) -> bool:
        return (
            binding.authority_id == self.authority_id
            and (
                binding.resolver_id,
                binding.resolver_version,
            )
            in self.scope_resolvers
        )

    def authenticates_qualification(self, binding: EvidenceQualificationBinding) -> bool:
        return (
            binding.authority_id == self.authority_id
            and (binding.qualifier_id, binding.qualifier_version) in self.qualification_resolvers
            and binding.role in self.qualification_roles
        )


class DormantInquiryIndex:
    """A rebuildable complement of the existing v0.6 eligibility projection."""

    def __init__(self, descriptors: tuple[DormantInquiryDescriptor, ...]) -> None:
        self._descriptors = descriptors

    @property
    def dormant(self) -> tuple[DormantInquiryDescriptor, ...]:
        return self._descriptors

    def get(self, inquiry_id: str) -> DormantInquiryDescriptor | None:
        return next(
            (value for value in self._descriptors if value.inquiry_id == inquiry_id),
            None,
        )

    @classmethod
    def derive(
        cls,
        *,
        endogenous: EndogenousProjection,
        reconsideration: ReconsiderationProjection,
        at: datetime,
    ) -> DormantInquiryIndex:
        if at.tzinfo is None:
            raise ValueError("dormancy evaluation time must be timezone-aware")
        eligible = {value.inquiry_id for value in endogenous.eligible_inquiries(at=at)}
        descriptors: list[DormantInquiryDescriptor] = []
        for inquiry in endogenous.inquiries:
            if inquiry.inquiry_id in eligible:
                continue
            inquiry_event = endogenous.event(f"inquiry-recorded:{inquiry.inquiry_id}")
            if inquiry_event is None:
                raise ValueError("canonical Inquiry lost its event envelope")
            epoch_id = str(inquiry_event.payload["epoch_id"])
            reasons: set[DormancyReason] = set()
            if inquiry.expires_at <= at:
                reasons.add(DormancyReason.INQUIRY_EXPIRED)
            for ref in inquiry.governing_intent_refs:
                current = endogenous.strategy.current_goal_revision(ref.goal_id)
                if current is None or current.revision_id != ref.goal_revision_id:
                    reasons.add(DormancyReason.INTENT_REVISION_STALE)
                if current is not None and current.status in {
                    GoalStatus.COMPLETED,
                    GoalStatus.FAILED,
                    GoalStatus.CANCELLED,
                }:
                    reasons.add(DormancyReason.INTENT_TERMINAL)
            try:
                dream_status = endogenous.epoch_status(epoch_id).value
            except KeyError:
                dream_status = None
            last_considered = max(
                (
                    value.current_causal_cursor
                    for value in reconsideration.candidates
                    if value.historical.inquiry_id == inquiry.inquiry_id
                ),
                default=0,
            )
            descriptors.append(
                DormantInquiryDescriptor(
                    inquiry_id=inquiry.inquiry_id,
                    epoch_id=epoch_id,
                    historical_causal_cursor=inquiry.causal_cursor,
                    reasons=tuple(sorted(reasons, key=lambda value: value.value)),
                    target_refs=inquiry.target_refs,
                    dream_status=dream_status,
                    last_considered_cut=last_considered,
                )
            )
        return cls(tuple(sorted(descriptors, key=lambda value: value.inquiry_id)))


@dataclass(frozen=True, slots=True)
class DiscoveryNomination:
    descriptor: DormantInquiryDescriptor
    scope_binding: InquiryReconsiderationScopeBinding
    qualifications: tuple[EvidenceQualificationBinding, ...]
    reasons: tuple[DiscoveryReason, ...]
    kind: ReconsiderationOpportunityKind
    existing_candidate_id: str | None
    allocation_context_fingerprint: str | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiscoveryAddress:
    """Cheap projected address used before scarce semantic evaluation is spent."""

    descriptor: DormantInquiryDescriptor
    preliminary_reason_rank: int
    address_kind_rank: int


def qualification_is_current(
    memory: MemoryProjection,
    binding: EvidenceQualificationBinding,
    *,
    at: datetime,
) -> bool:
    assertion = memory.get_assertion(binding.assertion_ref)
    if assertion is None or binding.bound_at > at:
        return False
    visible = {value.assertion_id for value in memory.visible_assertions(valid_at=at, known_at=at)}
    return binding.assertion_ref in visible and not memory.is_contradicted(
        binding.assertion_ref,
        valid_at=at,
        known_at=at,
    )


def validate_qualification_temporality(
    *,
    events_by_id: Mapping[str, Event],
    memory: MemoryProjection,
    binding: EvidenceQualificationBinding,
    inquiry: Inquiry,
    evaluation_cut: int,
) -> None:
    """Require current applicability while allowing old durable source evidence."""

    assertion = memory.get_assertion(binding.assertion_ref)
    assertion_event = events_by_id.get(f"memory-assertion:{binding.assertion_ref}")
    binding_event = events_by_id.get(
        f"reconsideration-evidence-qualified:{binding.qualification_id}"
    )
    if (
        assertion is None
        or assertion_event is None
        or assertion_event.sequence is None
        or binding_event is None
        or binding_event.sequence is None
        or assertion_event.sequence > evaluation_cut
        or binding_event.sequence > evaluation_cut
    ):
        raise ValueError("qualification evidence is outside its evaluation cut")
    if binding_event.sequence <= inquiry.causal_cursor:
        raise ValueError("qualification must currently re-attest its historical Inquiry")
    if assertion_event.sequence <= inquiry.causal_cursor:
        raise ValueError(f"{binding.role.value} assertion must follow the historical Inquiry")
    if binding.role in {
        EvidenceQualificationRole.DURABLE_VALUE,
        EvidenceQualificationRole.PREFERENCE,
    }:
        return
    source_sequences = tuple(
        event.sequence
        for ref in assertion.source_refs
        if ref.startswith("event:")
        and (event := events_by_id.get(ref.removeprefix("event:"))) is not None
        and event.sequence is not None
    )
    derivation_sequences = tuple(
        event.sequence
        for ref in assertion.derivation_refs
        if (event := events_by_id.get(f"memory-assertion:{ref}")) is not None
        and event.sequence is not None
    )
    if not any(
        value > inquiry.causal_cursor for value in (*source_sequences, *derivation_sequences)
    ):
        raise ValueError(f"{binding.role.value} lacks a post-Inquiry evidence basis")


def signal_is_valid_discovery_evidence(
    trigger: Event,
    *,
    inquiry: Inquiry,
    policy: ReconsiderationDiscoveryPolicySnapshot,
    canonical_events: tuple[Event, ...],
) -> bool:
    if trigger.type != "rule.evaluation_traced" or trigger.sequence is None:
        return False
    raw_signal = trigger.payload.get("signal_would_emit")
    if (
        not bool(trigger.payload.get("candidate"))
        or not bool(trigger.payload.get("activated"))
        or not isinstance(raw_signal, dict)
    ):
        return False
    signal = Signal.from_dict(raw_signal)
    rule_ref = f"{trigger.payload.get('rule_id')}@{trigger.payload.get('version')}"
    if (
        trigger.subject != rule_ref
        or signal.rule_ref != rule_ref
        or signal.evaluation_epoch_id != str(trigger.payload.get("epoch_id"))
        or signal.kind not in policy.permitted_signal_kinds
        or not signal.active_at(trigger.timestamp)
        or signal.subject not in {inquiry.inquiry_id, *inquiry.target_refs}
        or trigger.payload.get("evaluated_at") != trigger.timestamp.isoformat()
    ):
        return False
    raw_evidence = trigger.payload.get("evidence_refs")
    if not isinstance(raw_evidence, list) or tuple(
        sorted(str(value) for value in raw_evidence)
    ) != tuple(sorted(signal.evidence_event_ids)):
        return False
    events_by_id = {value.id: value for value in canonical_events}
    if not signal.evidence_event_ids or any(
        (evidence := events_by_id.get(event_id)) is None
        or evidence.sequence is None
        or evidence.sequence >= trigger.sequence
        for event_id in signal.evidence_event_ids
    ):
        return False
    for event in canonical_events:
        if (
            event.type != "rule.version_registered"
            or event.sequence is None
            or event.sequence >= trigger.sequence
        ):
            continue
        raw_rule = event.payload.get("rule")
        if not isinstance(raw_rule, dict):
            continue
        try:
            rule = AutonomicRule.from_dict(raw_rule)
        except (KeyError, TypeError, ValueError):
            continue
        if rule.ref == rule_ref:
            return True
    return False


class DeterministicDormantInquiryDetector:
    """Cheap nomination policy; it neither estimates NetVOC nor allocates cognition."""

    def discover(
        self,
        *,
        endogenous: EndogenousProjection,
        reconsideration: ReconsiderationProjection,
        memory: MemoryProjection,
        trigger: Event,
        basis: CurrentCognitiveBasis,
        policy: ReconsiderationDiscoveryPolicySnapshot,
        scope_bindings: tuple[InquiryReconsiderationScopeBinding, ...],
        qualification_bindings: tuple[EvidenceQualificationBinding, ...],
        current_budget: ScarceCognitionBudget,
        current_maximum_interruption_units: float,
        current_foreground_refs: tuple[str, ...],
        canonical_events: tuple[Event, ...],
        at: datetime,
    ) -> tuple[DiscoveryNomination, ...]:
        if trigger.sequence is None:
            raise ValueError("discovery requires a canonical trigger")
        if at.tzinfo is None:
            raise ValueError("discovery evaluation time must be timezone-aware")
        if current_foreground_refs or not self._agenda_has_slack(endogenous, basis=basis):
            return ()
        index = DormantInquiryIndex.derive(
            endogenous=endogenous,
            reconsideration=reconsideration,
            at=at,
        )
        scopes = {value.inquiry_id: value for value in scope_bindings}
        current_context = _allocation_context(
            reconsideration=reconsideration,
            basis=basis,
            budget=current_budget,
            maximum_interruption_units=current_maximum_interruption_units,
            foreground_refs=current_foreground_refs,
        )
        addressed = self._addressed_descriptors(
            index=index,
            endogenous=endogenous,
            reconsideration=reconsideration,
            trigger=trigger,
            basis=basis,
            policy=policy,
        )
        precedence = {value: index for index, value in enumerate(policy.reason_precedence)}
        relevant = tuple(
            value.descriptor
            for value in sorted(
                addressed,
                key=lambda value: (
                    value.preliminary_reason_rank,
                    value.address_kind_rank,
                    value.descriptor.last_considered_cut,
                    value.descriptor.inquiry_id,
                ),
            )
            if value.descriptor.inquiry_id in scopes
        )[: policy.max_dormant_inquiries_examined]
        inquiries = {
            descriptor.inquiry_id: endogenous.inquiry(descriptor.inquiry_id)
            for descriptor in relevant
        }
        batch_qualifications = self._bounded_qualifications(
            descriptors=relevant,
            inquiries=tuple(value for value in inquiries.values() if value is not None),
            qualifications=qualification_bindings,
            trigger=trigger,
            limit=policy.max_qualification_bindings_consumed,
        )
        current_qualifications = tuple(
            value
            for value in batch_qualifications
            if self._qualification_is_current(memory, value, at=at)
        )
        events_by_id = {event.id: event for event in canonical_events}
        qualifications_by_inquiry: dict[str, tuple[EvidenceQualificationBinding, ...]] = {}
        for descriptor in relevant:
            inquiry = inquiries[descriptor.inquiry_id]
            if inquiry is None:
                continue
            valid: list[EvidenceQualificationBinding] = []
            for binding in current_qualifications:
                if not self._targets_inquiry(binding.target_refs, inquiry):
                    continue
                try:
                    validate_qualification_temporality(
                        events_by_id=events_by_id,
                        memory=memory,
                        binding=binding,
                        inquiry=inquiry,
                        evaluation_cut=trigger.sequence,
                    )
                except ValueError:
                    continue
                valid.append(binding)
            qualifications_by_inquiry[descriptor.inquiry_id] = tuple(valid)
        nominations: list[DiscoveryNomination] = []
        for descriptor in relevant:
            inquiry = inquiries[descriptor.inquiry_id]
            scope = scopes.get(descriptor.inquiry_id)
            if inquiry is None or scope is None:
                continue
            qualifications = qualifications_by_inquiry.get(descriptor.inquiry_id, ())
            reasons = self._reasons(
                inquiry=inquiry,
                trigger=trigger,
                policy=policy,
                qualifications=qualifications,
                endogenous=endogenous,
                canonical_events=canonical_events,
            )
            existing = self._deferred_candidate(
                reconsideration,
                inquiry_id=inquiry.inquiry_id,
                basis_id=basis.basis_id,
                current_context=current_context,
                at=at,
            )
            if existing is not None:
                candidate, context = existing
                reasons = (*reasons, DiscoveryReason.DEFERRED_ALLOCATION_CONTEXT_CHANGED)
                kind = ReconsiderationOpportunityKind.REALLOCATE_EXISTING
                existing_candidate_id = candidate.candidate_id
                context_fingerprint: str | None = context
            else:
                kind = ReconsiderationOpportunityKind.NEW_REVALIDATION
                existing_candidate_id = None
                context_fingerprint = None
                if not self._critical_roles_are_separate(qualifications, inquiry=inquiry):
                    continue
            reasons = self._ordered_reasons(reasons, policy)
            if not reasons:
                continue
            evidence = {f"event:{trigger.id}"}
            for binding in qualifications:
                evidence.add(f"event:memory-assertion:{binding.assertion_ref}")
                evidence.add(f"event:reconsideration-evidence-qualified:{binding.qualification_id}")
            nominations.append(
                DiscoveryNomination(
                    descriptor=descriptor,
                    scope_binding=scope,
                    qualifications=qualifications,
                    reasons=reasons,
                    kind=kind,
                    existing_candidate_id=existing_candidate_id,
                    allocation_context_fingerprint=context_fingerprint,
                    evidence_refs=tuple(sorted(evidence)),
                )
            )
        return tuple(
            sorted(
                nominations,
                key=lambda value: (
                    min(precedence[reason] for reason in value.reasons),
                    value.descriptor.last_considered_cut,
                    value.descriptor.inquiry_id,
                ),
            )[: policy.max_opportunities_emitted]
        )

    def _addressed_descriptors(
        self,
        *,
        index: DormantInquiryIndex,
        endogenous: EndogenousProjection,
        reconsideration: ReconsiderationProjection,
        trigger: Event,
        basis: CurrentCognitiveBasis,
        policy: ReconsiderationDiscoveryPolicySnapshot,
    ) -> tuple[DiscoveryAddress, ...]:
        """Produce cheap deterministic addresses before semantic evaluation."""

        trigger_targets = set(self._trigger_targets(trigger))
        raw_signal = trigger.payload.get("signal_would_emit")
        if isinstance(raw_signal, dict) and isinstance(raw_signal.get("subject"), str):
            trigger_targets.add(str(raw_signal["subject"]))
        deferred_inquiry_ids = {
            value.historical.inquiry_id
            for value in reconsideration.candidates
            if value.current_basis.basis_id == basis.basis_id
        }
        reason_rank = {value: index for index, value in enumerate(policy.reason_precedence)}
        relevant: list[DiscoveryAddress] = []
        for descriptor in index.dormant:
            inquiry = endogenous.inquiry(descriptor.inquiry_id)
            if inquiry is None:
                continue
            directly_addressed = self._targets_inquiry(tuple(trigger_targets), inquiry)
            lineage_addressed = self._same_goal_lineage_reactivated(
                trigger,
                inquiry,
                endogenous,
            )
            deferred_addressed = inquiry.inquiry_id in deferred_inquiry_ids
            preliminary: list[tuple[int, int]] = []
            if directly_addressed:
                direct_reason = self._direct_reason_class(trigger, policy)
                if direct_reason is not None and direct_reason in reason_rank:
                    preliminary.append((reason_rank[direct_reason], 0))
            if (
                lineage_addressed
                and DiscoveryReason.SAME_GOAL_LINEAGE_REACTIVATED in reason_rank
            ):
                preliminary.append((reason_rank[DiscoveryReason.SAME_GOAL_LINEAGE_REACTIVATED], 1))
            if (
                deferred_addressed
                and DiscoveryReason.DEFERRED_ALLOCATION_CONTEXT_CHANGED in reason_rank
            ):
                preliminary.append(
                    (reason_rank[DiscoveryReason.DEFERRED_ALLOCATION_CONTEXT_CHANGED], 2)
                )
            if preliminary:
                rank, kind = min(preliminary)
                relevant.append(DiscoveryAddress(descriptor, rank, kind))
        return tuple(relevant)

    @staticmethod
    def _direct_reason_class(
        trigger: Event,
        policy: ReconsiderationDiscoveryPolicySnapshot,
    ) -> DiscoveryReason | None:
        if trigger.type in policy.explicit_user_event_types:
            return DiscoveryReason.EXPLICIT_USER_REENGAGEMENT
        if trigger.type in policy.explicit_relevance_event_types or trigger.type in {
            EVIDENCE_QUALIFICATION_BOUND_EVENT,
            "rule.evaluation_traced",
        }:
            return DiscoveryReason.EXPLICIT_RELEVANCE_SIGNAL
        if trigger.type in policy.opportunity_event_types:
            return DiscoveryReason.OPPORTUNITY_WINDOW_OPENED
        return None

    def _bounded_qualifications(
        self,
        *,
        descriptors: tuple[DormantInquiryDescriptor, ...],
        inquiries: tuple[Inquiry, ...],
        qualifications: tuple[EvidenceQualificationBinding, ...],
        trigger: Event,
        limit: int,
    ) -> tuple[EvidenceQualificationBinding, ...]:
        """Apply one qualification budget across the already narrowed batch."""

        descriptor_order = {
            descriptor.inquiry_id: position for position, descriptor in enumerate(descriptors)
        }
        addressed: list[tuple[int, EvidenceQualificationBinding]] = []
        for binding in qualifications:
            matching = tuple(
                descriptor_order[inquiry.inquiry_id]
                for inquiry in inquiries
                if self._targets_inquiry(binding.target_refs, inquiry)
            )
            if matching:
                addressed.append((min(matching), binding))
        addressed.sort(
            key=lambda item: (
                item[0],
                0
                if trigger.id
                == f"reconsideration-evidence-qualified:{item[1].qualification_id}"
                else 1,
                item[1].qualification_id,
            )
        )
        return tuple(value for _position, value in addressed[:limit])

    @staticmethod
    def _qualification_is_current(
        memory: MemoryProjection,
        binding: EvidenceQualificationBinding,
        *,
        at: datetime,
    ) -> bool:
        return qualification_is_current(memory, binding, at=at)

    @staticmethod
    def _agenda_has_slack(
        endogenous: EndogenousProjection,
        *,
        basis: CurrentCognitiveBasis,
    ) -> bool:
        allowed_goal_id = (
            basis.live_intent_ref.goal_id
            if basis.kind is CognitiveBasisKind.LIVE_GOVERNING_INTENT
            and basis.live_intent_ref is not None
            else None
        )
        return not any(
            goal.status in {GoalStatus.ACTIVE, GoalStatus.BLOCKED}
            and goal.goal_id != allowed_goal_id
            for goal in endogenous.strategy.goal_revisions
            if endogenous.strategy.current_goal_revision(goal.goal_id) == goal
        )

    def _reasons(
        self,
        *,
        inquiry: Inquiry,
        trigger: Event,
        policy: ReconsiderationDiscoveryPolicySnapshot,
        qualifications: tuple[EvidenceQualificationBinding, ...],
        endogenous: EndogenousProjection,
        canonical_events: tuple[Event, ...],
    ) -> tuple[DiscoveryReason, ...]:
        reasons: list[DiscoveryReason] = []
        target_match = self._targets_inquiry(self._trigger_targets(trigger), inquiry)
        qualification_trigger = any(
            trigger.id == f"reconsideration-evidence-qualified:{value.qualification_id}"
            for value in qualifications
        )
        trigger_targets_inquiry = target_match or qualification_trigger
        if target_match and trigger.type in policy.explicit_user_event_types:
            reasons.append(DiscoveryReason.EXPLICIT_USER_REENGAGEMENT)
        if target_match and trigger.type in policy.explicit_relevance_event_types:
            reasons.append(DiscoveryReason.EXPLICIT_RELEVANCE_SIGNAL)
        if target_match and trigger.type in policy.opportunity_event_types:
            reasons.append(DiscoveryReason.OPPORTUNITY_WINDOW_OPENED)
        if signal_is_valid_discovery_evidence(
            trigger,
            inquiry=inquiry,
            policy=policy,
            canonical_events=canonical_events,
        ):
            reasons.append(DiscoveryReason.EXPLICIT_RELEVANCE_SIGNAL)
        if self._same_goal_lineage_reactivated(trigger, inquiry, endogenous):
            reasons.append(DiscoveryReason.SAME_GOAL_LINEAGE_REACTIVATED)
        if trigger_targets_inquiry and any(
            value.role is EvidenceQualificationRole.CURRENT_REVALIDATION for value in qualifications
        ):
            reasons.append(DiscoveryReason.EXPLICIT_RELEVANCE_SIGNAL)
        if trigger_targets_inquiry and any(
            value.role is EvidenceQualificationRole.OPPORTUNITY for value in qualifications
        ):
            reasons.append(DiscoveryReason.OPPORTUNITY_WINDOW_OPENED)
        if trigger_targets_inquiry and any(
            value.role is EvidenceQualificationRole.DURABLE_VALUE for value in qualifications
        ):
            reasons.append(DiscoveryReason.QUALIFIED_PERSISTENT_VALUE)
        return tuple(reasons)

    @staticmethod
    def _targets_inquiry(target_refs: tuple[str | None, ...], inquiry: Inquiry) -> bool:
        targets = {inquiry.inquiry_id, *inquiry.target_refs}
        return any(value in targets for value in target_refs if value is not None)

    @staticmethod
    def _trigger_targets(trigger: Event) -> tuple[str | None, ...]:
        raw = trigger.payload.get("target_refs", [])
        structured = (
            tuple(value for value in raw if isinstance(value, str)) if isinstance(raw, list) else ()
        )
        return ((trigger.subject,) if trigger.subject else ()) + structured

    @staticmethod
    def _same_goal_lineage_reactivated(
        trigger: Event,
        inquiry: Inquiry,
        endogenous: EndogenousProjection,
    ) -> bool:
        if trigger.type != "intent.goal_revision_recorded":
            return False
        current = endogenous.strategy.current_goal_revision(trigger.subject or "")
        if current is None or current.status not in {GoalStatus.ACTIVE, GoalStatus.BLOCKED}:
            return False
        return any(
            ref.goal_id == current.goal_id and ref.goal_revision_id != current.revision_id
            for ref in inquiry.governing_intent_refs
        )

    @staticmethod
    def _critical_roles_are_separate(
        qualifications: tuple[EvidenceQualificationBinding, ...],
        *,
        inquiry: Inquiry,
    ) -> bool:
        required = (
            EvidenceQualificationRole.VALUE_ALIGNMENT,
            EvidenceQualificationRole.MOTIVATION,
            EvidenceQualificationRole.EXPECTED_OUTCOME_VALUE,
        )
        selected: list[EvidenceQualificationBinding] = []
        for role in required:
            matches = tuple(value for value in qualifications if value.role is role)
            if len(matches) != 1:
                return False
            selected.append(matches[0])
        refs = [value.assertion_ref for value in selected]
        durable_refs = {
            value.assertion_ref
            for value in qualifications
            if value.role is EvidenceQualificationRole.DURABLE_VALUE
        }
        stable_targets = {inquiry.inquiry_id, *inquiry.target_refs}
        common_anchor = set.intersection(
            *(set(value.target_refs).intersection(stable_targets) for value in selected)
        )
        return (
            len(set(refs)) == len(refs)
            and not durable_refs.intersection(refs)
            and bool(common_anchor)
        )

    @staticmethod
    def _ordered_reasons(
        reasons: tuple[DiscoveryReason, ...],
        policy: ReconsiderationDiscoveryPolicySnapshot,
    ) -> tuple[DiscoveryReason, ...]:
        unique = set(reasons)
        return tuple(value for value in policy.reason_precedence if value in unique)

    @staticmethod
    def _deferred_candidate(
        reconsideration: ReconsiderationProjection,
        *,
        inquiry_id: str,
        basis_id: str,
        current_context: str,
        at: datetime,
    ) -> tuple[ReconsiderationCandidate, str] | None:
        matches: list[tuple[int, ReconsiderationCandidate, AllocationLabel, str]] = []
        for candidate in reconsideration.candidates:
            if (
                candidate.historical.inquiry_id != inquiry_id
                or candidate.current_basis.basis_id != basis_id
                or reconsideration.candidate_was_selected(candidate.candidate_id)
            ):
                continue
            if any(estimate.valid_until <= at for estimate in candidate.features.estimates()):
                continue
            for allocation in reconsideration.allocations:
                decision = next(
                    (
                        value
                        for value in allocation.decisions
                        if value.candidate_id == candidate.candidate_id
                    ),
                    None,
                )
                if decision is None:
                    continue
                event = reconsideration.event(
                    f"reconsideration-allocation-recorded:{allocation.allocation_id}"
                )
                scan = reconsideration.scan(allocation.scan_request_id)
                if event is None or event.sequence is None or scan is None:
                    continue
                old_context = allocation_context_fingerprint(
                    {
                        "basis_id": scan.basis.basis_id,
                        "policy_id": scan.policy_id,
                        "budget": scan.budget.to_dict(),
                        "maximum_interruption_units": scan.maximum_interruption_units,
                        "foreground_demand_refs": list(allocation.foreground_demand_refs),
                    }
                )
                matches.append((event.sequence, candidate, decision.label, old_context))
        if not matches:
            return None
        _sequence, candidate, label, old_context = max(matches, key=lambda value: value[0])
        if label is not AllocationLabel.DEFERRED_BY_CONSTRAINT or old_context == current_context:
            return None
        return candidate, current_context


def _allocation_context(
    *,
    reconsideration: ReconsiderationProjection,
    basis: CurrentCognitiveBasis,
    budget: ScarceCognitionBudget,
    maximum_interruption_units: float,
    foreground_refs: tuple[str, ...],
) -> str:
    latest_policy = reconsideration.latest_policy
    return allocation_context_fingerprint(
        {
            "basis_id": basis.basis_id,
            "policy_id": latest_policy.policy_id if latest_policy is not None else "pending",
            "budget": budget.to_dict(),
            "maximum_interruption_units": maximum_interruption_units,
            "foreground_demand_refs": list(tuple(sorted(set(foreground_refs)))),
        }
    )


class DeterministicReconsiderationSeedAssembler:
    """Build v0.6.1 inputs from qualified memory without creating assertions."""

    def assemble(
        self,
        *,
        opportunity: ReconsiderationOpportunity,
        inquiry: Inquiry,
        scope: InquiryReconsiderationScopeBinding,
        qualifications: tuple[EvidenceQualificationBinding, ...],
        memory: MemoryProjection,
        reconsideration: ReconsiderationProjection,
        domain: str,
    ) -> ReconsiderationSeed:
        if opportunity.seed_policy_version != DETERMINISTIC_DISCOVERY_SEED_POLICY_VERSION:
            raise ValueError("unsupported deterministic discovery seed policy version")
        if opportunity.kind is ReconsiderationOpportunityKind.REALLOCATE_EXISTING:
            assert opportunity.existing_candidate_id is not None
            candidate = reconsideration.candidate(opportunity.existing_candidate_id)
            if candidate is None:
                raise ValueError("reallocation opportunity lost its existing candidate")
            scan = reconsideration.scan(candidate.scan_request_id)
            if scan is None:
                raise ValueError("reallocation candidate lost its originating scan")
            candidate_input = next(
                value
                for value in scan.candidate_inputs
                if value.candidate_id == candidate.candidate_id
            )
            return candidate_input.seed

        by_role: dict[EvidenceQualificationRole, EvidenceQualificationBinding] = {}
        for binding in qualifications:
            if binding.role in by_role:
                raise ValueError("seed assembly fails closed on ambiguous qualification roles")
            by_role[binding.role] = binding
        required = (
            EvidenceQualificationRole.VALUE_ALIGNMENT,
            EvidenceQualificationRole.MOTIVATION,
            EvidenceQualificationRole.EXPECTED_OUTCOME_VALUE,
        )
        if any(role not in by_role for role in required):
            raise ValueError("seed assembly requires separately qualified critical features")
        if len({by_role[role].assertion_ref for role in required}) != len(required):
            raise ValueError("one assertion cannot fill multiple critical qualification roles")
        durable = by_role.get(EvidenceQualificationRole.DURABLE_VALUE)
        if durable is not None and durable.assertion_ref in {
            by_role[role].assertion_ref for role in required
        }:
            raise ValueError("a durable value cannot stand in for a candidate estimate")
        stable_targets = {inquiry.inquiry_id, *inquiry.target_refs}
        common_anchor = set.intersection(
            *(
                set(by_role[role].target_refs).intersection(stable_targets)
                for role in required
            )
        )
        if not common_anchor:
            raise ValueError("critical candidate estimates require one common target anchor")

        evaluation_event = reconsideration.event(opportunity.trigger_event_id)
        if evaluation_event is None or evaluation_event.sequence != opportunity.evaluation_cut:
            raise ValueError("seed assembly lost the opportunity evaluation event")
        assertions = {
            role: self._current_assertion(memory, by_role[role], at=evaluation_event.timestamp)
            for role in required
        }
        estimates = {role: self._estimate(memory, assertions[role], role=role) for role in required}
        evidence = set(opportunity.evidence_refs)
        evidence.add(f"event:reconsideration-opportunity-recorded:{opportunity.opportunity_id}")
        governed = set(scope.governed_information_ids)
        for binding in qualifications:
            governed.update(binding.governed_information_ids)
        evidence_freshness = float(
            all(
                qualification_is_current(memory, by_role[role], at=evaluation_event.timestamp)
                for role in required
            )
        )
        meaningful_new_evidence = float(
            self._has_meaningful_new_evidence(
                inquiry=inquiry,
                binding=by_role.get(EvidenceQualificationRole.CURRENT_REVALIDATION),
                memory=memory,
                reconsideration=reconsideration,
                at=evaluation_event.timestamp,
            )
        )
        return ReconsiderationSeed(
            inquiry_id=inquiry.inquiry_id,
            domain=domain,
            current_evidence_refs=tuple(sorted(evidence)),
            governed_information_ids=tuple(sorted(governed)),
            features=ReconsiderationFeatureSnapshot(
                unresolvedness=inquiry.uncertainty,
                evidence_freshness=evidence_freshness,
                meaningful_new_evidence=meaningful_new_evidence,
                opportunity_window=(
                    1.0
                    if DiscoveryReason.OPPORTUNITY_WINDOW_OPENED in opportunity.discovery_reasons
                    else 0.0
                ),
                current_basis_validity=1.0,
                value_alignment_estimate=estimates[EvidenceQualificationRole.VALUE_ALIGNMENT],
                expected_outcome_value=estimates[EvidenceQualificationRole.EXPECTED_OUTCOME_VALUE],
                motivation_estimate=estimates[EvidenceQualificationRole.MOTIVATION],
                provenance_refs=tuple(sorted(evidence)),
            ),
            costs=opportunity.seed_costs,
        )

    @staticmethod
    def _has_meaningful_new_evidence(
        *,
        inquiry: Inquiry,
        binding: EvidenceQualificationBinding | None,
        memory: MemoryProjection,
        reconsideration: ReconsiderationProjection,
        at: datetime,
    ) -> bool:
        if (
            binding is None
            or not qualification_is_current(memory, binding, at=at)
            or not set(binding.target_refs).intersection(
                {inquiry.inquiry_id, *inquiry.target_refs}
            )
        ):
            return False
        assertion = memory.get_assertion(binding.assertion_ref)
        assertion_event = reconsideration.event(f"memory-assertion:{binding.assertion_ref}")
        binding_event = reconsideration.event(
            f"reconsideration-evidence-qualified:{binding.qualification_id}"
        )
        if (
            assertion is None
            or assertion_event is None
            or assertion_event.sequence is None
            or binding_event is None
            or binding_event.sequence is None
        ):
            return False
        source_sequences = tuple(
            event.sequence
            for ref in assertion.source_refs
            if ref.startswith("event:")
            and (event := reconsideration.event(ref.removeprefix("event:"))) is not None
            and event.sequence is not None
        )
        return (
            assertion_event.sequence > inquiry.causal_cursor
            and binding_event.sequence > inquiry.causal_cursor
            and any(value > inquiry.causal_cursor for value in source_sequences)
        )

    @staticmethod
    def _current_assertion(
        memory: MemoryProjection,
        binding: EvidenceQualificationBinding,
        *,
        at: datetime,
    ) -> SemanticAssertion:
        if not qualification_is_current(memory, binding, at=at):
            raise ValueError("seed assembly requires a current uncontradicted assertion")
        assertion = memory.get_assertion(binding.assertion_ref)
        if assertion is None:  # pragma: no cover - guarded above
            raise AssertionError("current assertion disappeared")
        return assertion

    @staticmethod
    def _estimate(
        memory: MemoryProjection,
        assertion: SemanticAssertion,
        *,
        role: EvidenceQualificationRole,
    ) -> EvidenceBackedEstimate:
        boundaries = tuple(
            value
            for value in (
                assertion.fresh_until,
                memory.effective_valid_to(assertion, known_at=assertion.recorded_at),
            )
            if value is not None
        )
        if not boundaries:
            raise ValueError(f"{role.value} current qualification requires a finite validity")
        valid_until = min(boundaries)
        evidence_kind = (
            EstimateEvidenceKind.EXPLICIT
            if assertion.epistemic_type in {EpistemicType.OBSERVED, EpistemicType.REPORTED}
            else EstimateEvidenceKind.INFERRED
        )
        return EvidenceBackedEstimate(
            value=numeric_assertion_value(assertion.value, role=role),
            kind=evidence_kind,
            confidence=assertion.confidence,
            evidence_refs=(f"event:memory-assertion:{assertion.assertion_id}",),
            observed_at=assertion.recorded_at,
            valid_until=valid_until,
        )
