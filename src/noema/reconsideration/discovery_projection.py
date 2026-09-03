"""Replayable legality projection for dormant-cognition discovery."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TypeVar

from ..endogenous.models import Inquiry
from ..endogenous.projection import EndogenousProjection
from ..events import Event
from ..information.models import InformationOperation, LineageTransformation
from ..information.policy import InformationGovernanceEngine
from ..information.projection import InformationGovernanceProjection
from ..memory.projection import MemoryProjection
from ..situation import GoalStatus
from ..types import JSONObject
from .discovery import (
    DormantInquiryIndex,
    qualification_is_current,
    signal_is_valid_discovery_evidence,
)
from .discovery_models import (
    DISCOVERY_POLICY_RECORDED_EVENT,
    EVIDENCE_QUALIFICATION_BOUND_EVENT,
    INQUIRY_SCOPE_BOUND_EVENT,
    OPPORTUNITY_RECORDED_EVENT,
    DiscoveryReason,
    EvidenceQualificationBinding,
    EvidenceQualificationRole,
    InquiryReconsiderationScopeBinding,
    ReconsiderationDiscoveryPolicySnapshot,
    ReconsiderationOpportunity,
    ReconsiderationOpportunityKind,
)
from .models import AllocationLabel, CognitiveBasisKind, CurrentCognitiveBasis
from .projection import ReconsiderationProjection

ValueT = TypeVar("ValueT")


class ReconsiderationDiscoveryProjection:
    """Rebuild discovery policies, bindings, and immutable nominations."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._events: dict[str, Event] = {}
        self._last_sequence = 0
        self._endogenous = EndogenousProjection()
        self._reconsideration = ReconsiderationProjection()
        self._memory = MemoryProjection()
        self._information = InformationGovernanceProjection()
        self._policies: dict[str, ReconsiderationDiscoveryPolicySnapshot] = {}
        self._scope_bindings: dict[str, InquiryReconsiderationScopeBinding] = {}
        self._scope_by_inquiry: dict[str, str] = {}
        self._qualifications: dict[str, EvidenceQualificationBinding] = {}
        self._opportunities: dict[str, ReconsiderationOpportunity] = {}

    @property
    def event_cursor(self) -> int:
        return self._last_sequence

    @property
    def endogenous(self) -> EndogenousProjection:
        return self._endogenous

    @property
    def reconsideration(self) -> ReconsiderationProjection:
        return self._reconsideration

    @property
    def memory(self) -> MemoryProjection:
        return self._memory

    @property
    def information(self) -> InformationGovernanceProjection:
        return self._information

    @property
    def policies(self) -> tuple[ReconsiderationDiscoveryPolicySnapshot, ...]:
        return tuple(self._policies[key] for key in sorted(self._policies))

    @property
    def scope_bindings(self) -> tuple[InquiryReconsiderationScopeBinding, ...]:
        return tuple(self._scope_bindings[key] for key in sorted(self._scope_bindings))

    @property
    def qualification_bindings(self) -> tuple[EvidenceQualificationBinding, ...]:
        return tuple(self._qualifications[key] for key in sorted(self._qualifications))

    @property
    def opportunities(self) -> tuple[ReconsiderationOpportunity, ...]:
        return tuple(self._opportunities[key] for key in sorted(self._opportunities))

    def event(self, event_id: str) -> Event | None:
        return self._events.get(event_id)

    def policy(self, policy_id: str) -> ReconsiderationDiscoveryPolicySnapshot | None:
        return self._policies.get(policy_id)

    def scope_binding(self, binding_id: str) -> InquiryReconsiderationScopeBinding | None:
        return self._scope_bindings.get(binding_id)

    def scope_for_inquiry(self, inquiry_id: str) -> InquiryReconsiderationScopeBinding | None:
        binding_id = self._scope_by_inquiry.get(inquiry_id)
        return self._scope_bindings.get(binding_id) if binding_id is not None else None

    def qualification(self, qualification_id: str) -> EvidenceQualificationBinding | None:
        return self._qualifications.get(qualification_id)

    def opportunity(self, opportunity_id: str) -> ReconsiderationOpportunity | None:
        return self._opportunities.get(opportunity_id)

    def opportunities_for_trigger(
        self,
        trigger_event_id: str,
    ) -> tuple[ReconsiderationOpportunity, ...]:
        return tuple(
            value for value in self.opportunities if value.trigger_event_id == trigger_event_id
        )

    def apply(self, event: Event) -> bool:
        existing = self._events.get(event.id)
        if existing is not None:
            if existing != event:
                raise ValueError(f"conflicting discovery event identity: {event.id}")
            return False
        if event.sequence is None:
            raise ValueError("discovery projection requires canonical events")
        if event.sequence <= self._last_sequence:
            raise ValueError("discovery events must be applied in canonical order")

        handled = self._apply_event(event)
        self._endogenous.apply(event)
        self._reconsideration.apply(event)
        self._memory.apply(event)
        self._information.apply(event)
        self._events[event.id] = event
        self._last_sequence = event.sequence
        return handled

    def rebuild(
        self,
        events: Iterable[Event],
        *,
        through_sequence: int | None = None,
    ) -> None:
        self._reset()
        for event in events:
            if through_sequence is not None and (event.sequence or 0) > through_sequence:
                continue
            self.apply(event)

    def _apply_event(self, event: Event) -> bool:
        if event.type == DISCOVERY_POLICY_RECORDED_EVENT:
            policy = ReconsiderationDiscoveryPolicySnapshot.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=f"reconsideration-discovery-policy-recorded:{policy.policy_id}",
                subject=policy.policy_id,
            )
            self._put_immutable(self._policies, policy.policy_id, policy, "discovery policy")
            return True
        if event.type == INQUIRY_SCOPE_BOUND_EVENT:
            self._require_exact_head(event)
            scope_binding = InquiryReconsiderationScopeBinding.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=f"reconsideration-inquiry-scope-bound:{scope_binding.binding_id}",
                subject=scope_binding.inquiry_id,
                timestamp=scope_binding.bound_at,
            )
            self._validate_authorization(
                event,
                authorization_ref=scope_binding.authorization_ref,
                authority_id=scope_binding.authority_id,
            )
            inquiry = self._endogenous.inquiry(scope_binding.inquiry_id)
            if inquiry is None:
                raise ValueError("scope binding references an unknown canonical Inquiry")
            self._validate_event_refs(scope_binding.evidence_refs)
            self._validate_access(
                decision_ids=scope_binding.information_access_decision_ids,
                governed_information_ids=scope_binding.governed_information_ids,
                purpose=scope_binding.information_use_purpose,
                policy_ids=scope_binding.information_policy_ids,
            )
            self._validate_derived_information(
                information_id=scope_binding.derived_information_id,
                source_information_ids=scope_binding.governed_information_ids,
                policy_ids=scope_binding.information_policy_ids,
            )
            existing_id = self._scope_by_inquiry.get(scope_binding.inquiry_id)
            if existing_id is not None and existing_id != scope_binding.binding_id:
                raise ValueError("multiple Inquiry scope bindings fail closed in v0.6.2")
            self._put_immutable(
                self._scope_bindings,
                scope_binding.binding_id,
                scope_binding,
                "Inquiry scope binding",
            )
            self._scope_by_inquiry[scope_binding.inquiry_id] = scope_binding.binding_id
            return True
        if event.type == EVIDENCE_QUALIFICATION_BOUND_EVENT:
            self._require_exact_head(event)
            qualification_binding = EvidenceQualificationBinding.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=(
                    f"reconsideration-evidence-qualified:{qualification_binding.qualification_id}"
                ),
                subject=qualification_binding.assertion_ref,
                timestamp=qualification_binding.bound_at,
            )
            self._validate_authorization(
                event,
                authorization_ref=qualification_binding.authorization_ref,
                authority_id=qualification_binding.authority_id,
            )
            assertion = self._memory.get_assertion(qualification_binding.assertion_ref)
            if assertion is None:
                raise ValueError("qualification binding references an unknown SemanticAssertion")
            if not qualification_is_current(
                self._memory,
                qualification_binding,
                at=qualification_binding.bound_at,
            ):
                raise ValueError("qualification binding requires current uncontradicted evidence")
            assertion_event = self._events.get(
                f"memory-assertion:{qualification_binding.assertion_ref}"
            )
            if assertion_event is None:
                raise ValueError("qualification assertion lacks a canonical event")
            self._validate_access(
                decision_ids=qualification_binding.information_access_decision_ids,
                governed_information_ids=qualification_binding.governed_information_ids,
                purpose=qualification_binding.information_use_purpose,
                policy_ids=qualification_binding.information_policy_ids,
            )
            self._validate_derived_information(
                information_id=qualification_binding.derived_information_id,
                source_information_ids=qualification_binding.governed_information_ids,
                policy_ids=qualification_binding.information_policy_ids,
            )
            self._put_immutable(
                self._qualifications,
                qualification_binding.qualification_id,
                qualification_binding,
                "evidence qualification binding",
            )
            return True
        if event.type == OPPORTUNITY_RECORDED_EVENT:
            self._require_exact_head(event)
            opportunity = ReconsiderationOpportunity.from_dict(event.payload)
            self._validate_envelope(
                event,
                event_id=f"reconsideration-opportunity-recorded:{opportunity.opportunity_id}",
                subject=opportunity.historical_inquiry_id,
                timestamp=opportunity.created_at,
            )
            if opportunity.admitted_at_head != self._last_sequence:
                raise ValueError("opportunity does not carry its actual admitted predecessor head")
            if event.causation_id != opportunity.trigger_event_id:
                raise ValueError("opportunity causation differs from its trigger")
            trigger = self._events.get(opportunity.trigger_event_id)
            if trigger is None or trigger.sequence != opportunity.evaluation_cut:
                raise ValueError("opportunity evaluation cut must equal its canonical trigger")
            evaluation_endogenous, evaluation_reconsideration, evaluation_memory = (
                self._cognitive_state_at(opportunity.evaluation_cut)
            )
            discovery_policy = self._policies.get(opportunity.discovery_policy_id)
            if discovery_policy is None:
                raise ValueError("opportunity references an unknown discovery policy")
            self._require_event_at_or_before(
                f"reconsideration-discovery-policy-recorded:{discovery_policy.policy_id}",
                opportunity.evaluation_cut,
                "opportunity discovery policy",
            )
            if opportunity.seed_policy_version != discovery_policy.seed_policy_version:
                raise ValueError("opportunity seed policy differs from its discovery policy")
            if opportunity.seed_costs != discovery_policy.seed_costs:
                raise ValueError("opportunity seed costs differ from its pinned policy")
            if (
                len(self.opportunities_for_trigger(trigger.id))
                >= discovery_policy.max_opportunities_emitted
            ):
                raise ValueError("opportunity exceeds its trigger's discovery budget")
            if not self._reconsideration.basis_is_current(
                opportunity.current_cognitive_basis,
                at=opportunity.created_at,
            ):
                raise ValueError("opportunity cognitive basis is no longer current")
            if not evaluation_reconsideration.basis_is_current(
                opportunity.current_cognitive_basis,
                at=trigger.timestamp,
            ):
                raise ValueError("opportunity cognitive basis was invalid at its evaluation cut")
            inquiry = self._require_dormant_inquiry(
                opportunity,
                endogenous=evaluation_endogenous,
                reconsideration=evaluation_reconsideration,
                at=trigger.timestamp,
            )
            if not self._agenda_has_slack(
                evaluation_endogenous,
                opportunity.current_cognitive_basis,
            ):
                raise ValueError("foreground cognition blocked discovery at its evaluation cut")
            if self._foreground_refs(
                evaluation_reconsideration,
                basis=opportunity.current_cognitive_basis,
                event_types=discovery_policy.foreground_event_types,
                through_sequence=opportunity.evaluation_cut,
            ):
                raise ValueError("foreground demand blocked discovery at its evaluation cut")
            if not self._agenda_has_slack(
                self._endogenous,
                opportunity.current_cognitive_basis,
            ):
                raise ValueError("foreground cognition blocks dormant discovery at admission")
            if self._foreground_refs(
                self._reconsideration,
                basis=opportunity.current_cognitive_basis,
                event_types=discovery_policy.foreground_event_types,
                through_sequence=opportunity.admitted_at_head,
            ):
                raise ValueError("foreground demand blocks dormant discovery at admission")
            scope = self._scope_bindings.get(opportunity.scope_binding_id)
            if scope is None or scope.inquiry_id != inquiry.inquiry_id:
                raise ValueError("opportunity lacks its exact Inquiry scope binding")
            self._require_event_at_or_before(
                f"reconsideration-inquiry-scope-bound:{scope.binding_id}",
                opportunity.evaluation_cut,
                "opportunity scope binding",
            )
            domain = self._require_one_domain_intersection(opportunity, scope)
            if not domain:
                raise AssertionError("validated scope domain disappeared")
            qualifications = tuple(
                self._require_qualification(value) for value in opportunity.qualification_ids
            )
            if len(qualifications) > discovery_policy.max_qualification_bindings_consumed:
                raise ValueError("opportunity exceeds its qualification-consumption budget")
            for qualification in qualifications:
                self._require_event_at_or_before(
                    f"reconsideration-evidence-qualified:{qualification.qualification_id}",
                    opportunity.evaluation_cut,
                    "opportunity qualification",
                )
                if not self._targets_inquiry(qualification, inquiry):
                    raise ValueError("opportunity qualification is not target-specific")
                if not qualification_is_current(
                    evaluation_memory,
                    qualification,
                    at=trigger.timestamp,
                ):
                    raise ValueError(
                        "opportunity qualification was not current at its evaluation cut"
                    )
                if not qualification_is_current(
                    self._memory,
                    qualification,
                    at=opportunity.created_at,
                ):
                    raise ValueError("opportunity qualification is no longer current")
                self._validate_qualification_temporality(
                    qualification,
                    inquiry=inquiry,
                    evaluation_cut=opportunity.evaluation_cut,
                )
            self._validate_reason_evidence(
                opportunity,
                trigger,
                inquiry,
                qualifications,
                discovery_policy,
                evaluation_endogenous,
            )
            self._validate_kind(
                opportunity,
                qualifications,
                reconsideration=evaluation_reconsideration,
                through_sequence=opportunity.evaluation_cut,
            )
            self._validate_kind(
                opportunity,
                qualifications,
                reconsideration=self._reconsideration,
                through_sequence=opportunity.admitted_at_head,
            )
            self._validate_event_refs(opportunity.evidence_refs)
            source_information_ids = (
                scope.derived_information_id,
                *(value.derived_information_id for value in qualifications),
            )
            self._validate_derived_information(
                information_id=opportunity.derived_information_id,
                source_information_ids=source_information_ids,
                policy_ids=opportunity.information_policy_ids,
            )
            governed_sources = {
                *scope.governed_information_ids,
                *(item for value in qualifications for item in value.governed_information_ids),
            }
            self._validate_access(
                decision_ids=opportunity.information_access_decision_ids,
                governed_information_ids=tuple(sorted(governed_sources)),
                purpose=opportunity.information_use_purpose,
                policy_ids=opportunity.information_policy_ids,
            )
            self._put_immutable(
                self._opportunities,
                opportunity.opportunity_id,
                opportunity,
                "reconsideration opportunity",
            )
            return True
        return False

    @staticmethod
    def _require_dormant_inquiry(
        opportunity: ReconsiderationOpportunity,
        *,
        endogenous: EndogenousProjection,
        reconsideration: ReconsiderationProjection,
        at: datetime,
    ) -> Inquiry:
        inquiry = endogenous.inquiry(opportunity.historical_inquiry_id)
        if inquiry is None:
            raise ValueError("opportunity references an unknown Inquiry")
        dormant = DormantInquiryIndex.derive(
            endogenous=endogenous,
            reconsideration=reconsideration,
            at=at,
        )
        if dormant.get(inquiry.inquiry_id) is None:
            raise ValueError("current Inquiry cannot be admitted as a dormant opportunity")
        return inquiry

    @staticmethod
    def _agenda_has_slack(
        endogenous: EndogenousProjection,
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

    def _require_one_domain_intersection(
        self,
        opportunity: ReconsiderationOpportunity,
        scope: InquiryReconsiderationScopeBinding,
    ) -> str:
        basis = opportunity.current_cognitive_basis
        if basis.kind is CognitiveBasisKind.RECONSIDERATION_MANDATE:
            assert basis.mandate_revision_id is not None
            mandate = self._reconsideration.mandates.revision(basis.mandate_revision_id)
            if mandate is None:
                raise ValueError("opportunity mandate is absent")
            intersection = set(scope.domain_ids).intersection(mandate.candidate_domains)
            if opportunity.information_use_purpose != mandate.information_use_purpose:
                raise ValueError("opportunity purpose differs from its mandate")
            if opportunity.information_policy_ids != mandate.information_policy_ids:
                raise ValueError("opportunity policies differ from its mandate")
        else:
            intersection = set(scope.domain_ids)
        if len(intersection) != 1:
            raise ValueError("Inquiry scope must resolve to exactly one current domain")
        return next(iter(intersection))

    def _validate_reason_evidence(
        self,
        opportunity: ReconsiderationOpportunity,
        trigger: Event,
        inquiry: Inquiry,
        qualifications: tuple[EvidenceQualificationBinding, ...],
        policy: ReconsiderationDiscoveryPolicySnapshot,
        endogenous: EndogenousProjection,
    ) -> None:
        roles = {value.role for value in qualifications}
        target_match = any(
            value in {inquiry.inquiry_id, *inquiry.target_refs}
            for value in self._trigger_targets(trigger)
        )
        qualification_trigger = any(
            trigger.id == f"reconsideration-evidence-qualified:{value.qualification_id}"
            for value in qualifications
        )
        trigger_targets_inquiry = target_match or qualification_trigger
        for reason in opportunity.discovery_reasons:
            valid = False
            if reason is DiscoveryReason.EXPLICIT_USER_REENGAGEMENT:
                valid = target_match and trigger.type in policy.explicit_user_event_types
            elif reason is DiscoveryReason.EXPLICIT_RELEVANCE_SIGNAL:
                valid = (
                    (target_match and trigger.type in policy.explicit_relevance_event_types)
                    or (
                        trigger_targets_inquiry
                        and EvidenceQualificationRole.CURRENT_REVALIDATION in roles
                    )
                    or signal_is_valid_discovery_evidence(
                        trigger,
                        inquiry=inquiry,
                        policy=policy,
                        canonical_events=tuple(
                            event
                            for event in self._events.values()
                            if (event.sequence or 0) <= opportunity.evaluation_cut
                        ),
                    )
                )
            elif reason is DiscoveryReason.OPPORTUNITY_WINDOW_OPENED:
                valid = (target_match and trigger.type in policy.opportunity_event_types) or (
                    trigger_targets_inquiry and EvidenceQualificationRole.OPPORTUNITY in roles
                )
            elif reason is DiscoveryReason.SAME_GOAL_LINEAGE_REACTIVATED:
                valid = self._same_goal_reactivation(trigger, inquiry, endogenous)
            elif reason is DiscoveryReason.QUALIFIED_PERSISTENT_VALUE:
                valid = trigger_targets_inquiry and EvidenceQualificationRole.DURABLE_VALUE in roles
            elif reason is DiscoveryReason.DEFERRED_ALLOCATION_CONTEXT_CHANGED:
                valid = opportunity.kind is ReconsiderationOpportunityKind.REALLOCATE_EXISTING
            if not valid:
                raise ValueError(f"opportunity reason lacks exact evidence: {reason.value}")

    @staticmethod
    def _trigger_targets(trigger: Event) -> tuple[str, ...]:
        raw = trigger.payload.get("target_refs", [])
        structured = (
            tuple(value for value in raw if isinstance(value, str)) if isinstance(raw, list) else ()
        )
        return ((trigger.subject,) if trigger.subject else ()) + structured

    @staticmethod
    def _same_goal_reactivation(
        trigger: Event,
        inquiry: Inquiry,
        endogenous: EndogenousProjection,
    ) -> bool:
        if trigger.type != "intent.goal_revision_recorded":
            return False
        current = endogenous.strategy.current_goal_revision(trigger.subject or "")
        return bool(
            current is not None
            and current.status in {GoalStatus.ACTIVE, GoalStatus.BLOCKED}
            and any(
                ref.goal_id == current.goal_id and ref.goal_revision_id != current.revision_id
                for ref in inquiry.governing_intent_refs
            )
        )

    def _validate_kind(
        self,
        opportunity: ReconsiderationOpportunity,
        qualifications: tuple[EvidenceQualificationBinding, ...],
        *,
        reconsideration: ReconsiderationProjection,
        through_sequence: int,
    ) -> None:
        if opportunity.kind is ReconsiderationOpportunityKind.NEW_REVALIDATION:
            required = (
                EvidenceQualificationRole.DURABLE_VALUE,
                EvidenceQualificationRole.MOTIVATION,
                EvidenceQualificationRole.EXPECTED_OUTCOME_VALUE,
            )
            refs: list[str] = []
            for role in required:
                matches = tuple(value for value in qualifications if value.role is role)
                if len(matches) != 1:
                    raise ValueError("new revalidation requires one binding per critical role")
                refs.append(matches[0].assertion_ref)
            if len(set(refs)) != len(refs):
                raise ValueError("critical qualification roles require distinct assertions")
            return
        assert opportunity.existing_candidate_id is not None
        candidate = reconsideration.candidate(opportunity.existing_candidate_id)
        if candidate is None or reconsideration.candidate_was_selected(candidate.candidate_id):
            raise ValueError("reallocation requires an unselected existing candidate")
        latest: tuple[int, AllocationLabel] | None = None
        for allocation in reconsideration.allocations:
            decision = next(
                (
                    value
                    for value in allocation.decisions
                    if value.candidate_id == candidate.candidate_id
                ),
                None,
            )
            event = self._events.get(
                f"reconsideration-allocation-recorded:{allocation.allocation_id}"
            )
            if (
                decision is None
                or event is None
                or event.sequence is None
                or event.sequence > through_sequence
            ):
                continue
            if latest is None or event.sequence > latest[0]:
                latest = (event.sequence, decision.label)
        if latest is None or latest[1] is not AllocationLabel.DEFERRED_BY_CONSTRAINT:
            raise ValueError("reallocation requires the latest disposition to be deferred")

    def _validate_qualification_temporality(
        self,
        binding: EvidenceQualificationBinding,
        *,
        inquiry: Inquiry,
        evaluation_cut: int,
    ) -> None:
        assertion = self._memory.get_assertion(binding.assertion_ref)
        assertion_event = self._events.get(f"memory-assertion:{binding.assertion_ref}")
        binding_event = self._events.get(
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
        if (
            assertion_event.sequence <= inquiry.causal_cursor
            or binding_event.sequence <= inquiry.causal_cursor
        ):
            raise ValueError("qualification must currently re-attest its historical Inquiry")
        roles_requiring_post_cut_basis = {
            EvidenceQualificationRole.CURRENT_REVALIDATION,
            EvidenceQualificationRole.MOTIVATION,
            EvidenceQualificationRole.OPPORTUNITY,
            EvidenceQualificationRole.EXPECTED_OUTCOME_VALUE,
        }
        if binding.role not in roles_requiring_post_cut_basis:
            return
        source_sequences = tuple(
            event.sequence
            for ref in assertion.source_refs
            if ref.startswith("event:")
            and (event := self._events.get(ref.removeprefix("event:"))) is not None
            and event.sequence is not None
        )
        if not any(value > inquiry.causal_cursor for value in source_sequences):
            raise ValueError(f"{binding.role.value} lacks a post-Inquiry evidence basis")

    def _foreground_refs(
        self,
        reconsideration: ReconsiderationProjection,
        *,
        basis: CurrentCognitiveBasis,
        event_types: tuple[str, ...],
        through_sequence: int,
    ) -> tuple[str, ...]:
        cutoff = 0
        for allocation in reconsideration.allocations:
            scan = reconsideration.scan(allocation.scan_request_id)
            event = reconsideration.event(
                f"reconsideration-allocation-recorded:{allocation.allocation_id}"
            )
            if (
                scan is not None
                and scan.basis.basis_id == basis.basis_id
                and event is not None
                and event.sequence is not None
                and event.sequence <= through_sequence
            ):
                cutoff = max(cutoff, event.sequence)
        if cutoff == 0 and basis.mandate_revision_id is not None:
            event = reconsideration.event(
                f"reconsideration-mandate-recorded:{basis.mandate_revision_id}"
            )
            if event is not None and event.sequence is not None:
                cutoff = event.sequence
        if cutoff == 0 and basis.live_intent_ref is not None:
            event = reconsideration.event(
                f"goal-revision-recorded:{basis.live_intent_ref.goal_revision_id}"
            )
            if event is not None and event.sequence is not None:
                cutoff = event.sequence
        return tuple(
            f"event:{event.id}"
            for event in sorted(
                self._events.values(),
                key=lambda value: value.sequence or 0,
            )
            if event.sequence is not None
            and cutoff < event.sequence <= through_sequence
            and event.type in event_types
        )

    def _cognitive_state_at(
        self,
        through_sequence: int,
    ) -> tuple[EndogenousProjection, ReconsiderationProjection, MemoryProjection]:
        endogenous = EndogenousProjection()
        reconsideration = ReconsiderationProjection()
        memory = MemoryProjection()
        events = sorted(
            (
                event
                for event in self._events.values()
                if event.sequence is not None and event.sequence <= through_sequence
            ),
            key=lambda event: event.sequence or 0,
        )
        for event in events:
            endogenous.apply(event)
            reconsideration.apply(event)
            memory.apply(event)
        return endogenous, reconsideration, memory

    def _require_event_at_or_before(
        self,
        event_id: str,
        through_sequence: int,
        label: str,
    ) -> Event:
        event = self._events.get(event_id)
        if event is None or event.sequence is None or event.sequence > through_sequence:
            raise ValueError(f"{label} is outside the opportunity evaluation cut")
        return event

    def _validate_access(
        self,
        *,
        decision_ids: tuple[str, ...],
        governed_information_ids: tuple[str, ...],
        purpose: str,
        policy_ids: tuple[str, ...],
    ) -> None:
        governance = InformationGovernanceEngine(self._information)
        information: list[str] = []
        for decision_id in decision_ids:
            decision = self._information.access_decision(decision_id)
            if decision is None or not decision.allowed:
                raise ValueError("discovery requires allowed information decisions")
            if not governance.decide_access(decision.request).allowed:
                raise ValueError("discovery information use is no longer allowed")
            context = decision.request.context
            if context.operation is not InformationOperation.REASON:
                raise ValueError("discovery information use must be admitted for reasoning")
            if context.purpose != purpose or context.policy_ids != policy_ids:
                raise ValueError("discovery information decision context is inconsistent")
            information.append(decision.request.information_ref.information_id)
        if tuple(sorted(information)) != tuple(sorted(set(governed_information_ids))):
            raise ValueError("discovery access decisions do not cover every governed source")

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
            raise ValueError("discovery artifact lacks exact source lineage")
        if (
            binding is None
            or binding.lineage_id != lineage.lineage_id
            or binding.policy_ids != tuple(sorted(set(policy_ids)))
        ):
            raise ValueError("discovery artifact lacks inherited policy binding")

    def _validate_authorization(
        self,
        event: Event,
        *,
        authorization_ref: str,
        authority_id: str,
    ) -> None:
        authorization_id = authorization_ref.removeprefix("event:")
        if event.causation_id != authorization_id or authorization_id not in self._events:
            raise ValueError("discovery binding lacks canonical authorization")
        if event.metadata.get("validated_discovery_authority_id") != authority_id:
            raise ValueError("discovery binding lacks an authenticated authority receipt")

    def _validate_event_refs(self, refs: tuple[str, ...]) -> None:
        for ref in refs:
            if not ref.startswith("event:") or ref.removeprefix("event:") not in self._events:
                raise ValueError(f"unknown canonical discovery evidence: {ref}")

    def _require_qualification(self, qualification_id: str) -> EvidenceQualificationBinding:
        value = self._qualifications.get(qualification_id)
        if value is None:
            raise ValueError("opportunity references an unknown qualification binding")
        return value

    @staticmethod
    def _targets_inquiry(binding: EvidenceQualificationBinding, inquiry: Inquiry) -> bool:
        targets = {inquiry.inquiry_id, *inquiry.target_refs}
        return bool(set(binding.target_refs).intersection(targets))

    def _require_exact_head(self, event: Event) -> None:
        if event.metadata.get("validated_at_event_cursor") != self._last_sequence:
            raise ValueError("discovery transition lacks exact-head admission evidence")

    @staticmethod
    def _validate_envelope(
        event: Event,
        *,
        event_id: str,
        subject: str,
        timestamp: datetime | None = None,
    ) -> None:
        if event.id != event_id or event.subject != subject:
            raise ValueError("discovery event envelope is inconsistent")
        if timestamp is not None and event.timestamp != timestamp:
            raise ValueError("discovery event timestamp is inconsistent")

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
            "policies": [value.to_dict() for value in self.policies],
            "scope_bindings": [value.to_dict() for value in self.scope_bindings],
            "qualification_bindings": [value.to_dict() for value in self.qualification_bindings],
            "opportunities": [value.to_dict() for value in self.opportunities],
        }
