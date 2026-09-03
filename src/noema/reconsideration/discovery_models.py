"""Immutable contracts for deterministic dormant-Inquiry discovery."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from ..events import Event
from ..information.models import validate_opaque_governance_id
from ..types import JSONObject, JSONValue, parse_datetime
from .models import CurrentCognitiveBasis, ScarceCognitionCostSnapshot

DISCOVERY_POLICY_RECORDED_EVENT = "reconsideration.discovery_policy_recorded"
INQUIRY_SCOPE_BOUND_EVENT = "reconsideration.inquiry_scope_bound"
EVIDENCE_QUALIFICATION_BOUND_EVENT = "reconsideration.evidence_qualification_bound"
OPPORTUNITY_RECORDED_EVENT = "reconsideration.opportunity_recorded"
DETERMINISTIC_DISCOVERY_SEED_POLICY_VERSION = "deterministic-seed-v1"

RECONSIDERATION_DISCOVERY_EVENT_TYPES = (
    DISCOVERY_POLICY_RECORDED_EVENT,
    INQUIRY_SCOPE_BOUND_EVENT,
    EVIDENCE_QUALIFICATION_BOUND_EVENT,
    OPPORTUNITY_RECORDED_EVENT,
)


class DormancyReason(StrEnum):
    INTENT_REVISION_STALE = "INTENT_REVISION_STALE"
    INTENT_TERMINAL = "INTENT_TERMINAL"
    INQUIRY_EXPIRED = "INQUIRY_EXPIRED"


class DiscoveryReason(StrEnum):
    EXPLICIT_USER_REENGAGEMENT = "EXPLICIT_USER_REENGAGEMENT"
    EXPLICIT_RELEVANCE_SIGNAL = "EXPLICIT_RELEVANCE_SIGNAL"
    OPPORTUNITY_WINDOW_OPENED = "OPPORTUNITY_WINDOW_OPENED"
    SAME_GOAL_LINEAGE_REACTIVATED = "SAME_GOAL_LINEAGE_REACTIVATED"
    QUALIFIED_PERSISTENT_VALUE = "QUALIFIED_PERSISTENT_VALUE"
    DEFERRED_ALLOCATION_CONTEXT_CHANGED = "DEFERRED_ALLOCATION_CONTEXT_CHANGED"


class EvidenceQualificationRole(StrEnum):
    CURRENT_REVALIDATION = "CURRENT_REVALIDATION"
    DURABLE_VALUE = "DURABLE_VALUE"
    VALUE_ALIGNMENT = "VALUE_ALIGNMENT"
    PREFERENCE = "PREFERENCE"
    MOTIVATION = "MOTIVATION"
    OPPORTUNITY = "OPPORTUNITY"
    EXPECTED_OUTCOME_VALUE = "EXPECTED_OUTCOME_VALUE"


class ReconsiderationOpportunityKind(StrEnum):
    NEW_REVALIDATION = "NEW_REVALIDATION"
    REALLOCATE_EXISTING = "REALLOCATE_EXISTING"


def _canonical_id(prefix: str, payload: Mapping[str, JSONValue]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:32]}"


def _require_text(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _unique(values: tuple[str, ...], name: str, *, required: bool = False) -> None:
    if required and not values:
        raise ValueError(f"{name} must not be empty")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} values must be non-empty")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} values must be unique")


def _strings(data: Mapping[str, object], key: str) -> tuple[str, ...]:
    values = cast(tuple[object, ...] | list[object], data.get(key, ()))
    return tuple(str(value) for value in values)


def _datetime(data: Mapping[str, object], key: str) -> datetime:
    value = parse_datetime(cast(str | datetime | None, data.get(key)))
    if value is None:
        raise ValueError(f"{key} is required")
    return value


@dataclass(frozen=True, slots=True)
class DormantInquiryDescriptor:
    """Disposable explanation of why a canonical Inquiry is not v0.6-current."""

    inquiry_id: str
    epoch_id: str
    historical_causal_cursor: int
    reasons: tuple[DormancyReason, ...]
    target_refs: tuple[str, ...]
    dream_status: str | None
    last_considered_cut: int

    def __post_init__(self) -> None:
        _require_text(self.inquiry_id, "dormant inquiry id")
        _require_text(self.epoch_id, "dormant inquiry epoch id")
        if self.historical_causal_cursor <= 0:
            raise ValueError("dormant inquiry requires a historical causal cursor")
        if not self.reasons or len(set(self.reasons)) != len(self.reasons):
            raise ValueError("dormant inquiry reasons must be non-empty and unique")
        _unique(self.target_refs, "dormant inquiry target refs", required=True)
        if self.last_considered_cut < 0:
            raise ValueError("last-considered cut cannot be negative")


@dataclass(frozen=True, slots=True)
class ReconsiderationDiscoveryPolicySnapshot:
    """Version-pinned nomination bounds; deliberately not a value optimizer."""

    policy_id: str
    version: str
    max_dormant_inquiries_examined: int
    max_opportunities_emitted: int
    max_qualification_bindings_consumed: int
    reason_precedence: tuple[DiscoveryReason, ...]
    explicit_user_event_types: tuple[str, ...]
    explicit_relevance_event_types: tuple[str, ...]
    opportunity_event_types: tuple[str, ...]
    foreground_event_types: tuple[str, ...]
    permitted_signal_kinds: tuple[str, ...]
    seed_policy_version: str
    seed_costs: ScarceCognitionCostSnapshot

    @classmethod
    def create(
        cls,
        *,
        version: str,
        max_dormant_inquiries_examined: int = 64,
        max_opportunities_emitted: int = 8,
        max_qualification_bindings_consumed: int = 32,
        reason_precedence: tuple[DiscoveryReason, ...] = (
            DiscoveryReason.EXPLICIT_USER_REENGAGEMENT,
            DiscoveryReason.EXPLICIT_RELEVANCE_SIGNAL,
            DiscoveryReason.OPPORTUNITY_WINDOW_OPENED,
            DiscoveryReason.SAME_GOAL_LINEAGE_REACTIVATED,
            DiscoveryReason.QUALIFIED_PERSISTENT_VALUE,
            DiscoveryReason.DEFERRED_ALLOCATION_CONTEXT_CHANGED,
        ),
        explicit_user_event_types: tuple[str, ...] = ("user.reconsideration_requested",),
        explicit_relevance_event_types: tuple[str, ...] = ("reconsideration.relevance_asserted",),
        opportunity_event_types: tuple[str, ...] = ("reconsideration.opportunity_window_opened",),
        foreground_event_types: tuple[str, ...] = (
            "work.order_recorded",
            "decision.proposed",
        ),
        permitted_signal_kinds: tuple[str, ...] = ("reconsideration_relevance",),
        seed_policy_version: str = DETERMINISTIC_DISCOVERY_SEED_POLICY_VERSION,
        seed_costs: ScarceCognitionCostSnapshot | None = None,
    ) -> ReconsiderationDiscoveryPolicySnapshot:
        reasons = tuple(reason_precedence)
        user_events = tuple(sorted(set(explicit_user_event_types)))
        relevance_events = tuple(sorted(set(explicit_relevance_event_types)))
        opportunity_events = tuple(sorted(set(opportunity_event_types)))
        foreground_events = tuple(sorted(set(foreground_event_types)))
        signal_kinds = tuple(sorted(set(permitted_signal_kinds)))
        costs = seed_costs or ScarceCognitionCostSnapshot(
            compute_units=0.5,
            wall_time_seconds=10.0,
            monetary_cost=0.0,
            attention_units=0.1,
            context_switching_units=0.1,
            intrusion_units=0.0,
            interruption_units=0.1,
            privacy_exposure_units=0.1,
            opportunity_cost_units=0.1,
            revalidation_units=0.2,
        )
        payload: JSONObject = {
            "version": version,
            "max_dormant_inquiries_examined": max_dormant_inquiries_examined,
            "max_opportunities_emitted": max_opportunities_emitted,
            "max_qualification_bindings_consumed": max_qualification_bindings_consumed,
            "reason_precedence": [value.value for value in reasons],
            "explicit_user_event_types": list(user_events),
            "explicit_relevance_event_types": list(relevance_events),
            "opportunity_event_types": list(opportunity_events),
            "foreground_event_types": list(foreground_events),
            "permitted_signal_kinds": list(signal_kinds),
            "seed_policy_version": seed_policy_version,
            "seed_costs": costs.to_dict(),
        }
        return cls(
            _canonical_id("reconsideration-discovery-policy", payload),
            version,
            max_dormant_inquiries_examined,
            max_opportunities_emitted,
            max_qualification_bindings_consumed,
            reasons,
            user_events,
            relevance_events,
            opportunity_events,
            foreground_events,
            signal_kinds,
            seed_policy_version,
            costs,
        )

    def __post_init__(self) -> None:
        _require_text(self.policy_id, "discovery policy id")
        _require_text(self.version, "discovery policy version")
        _require_text(self.seed_policy_version, "seed policy version")
        for value, name in (
            (self.max_dormant_inquiries_examined, "dormant examination limit"),
            (self.max_opportunities_emitted, "opportunity emission limit"),
            (self.max_qualification_bindings_consumed, "qualification consumption limit"),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if not self.reason_precedence or len(set(self.reason_precedence)) != len(
            self.reason_precedence
        ):
            raise ValueError("discovery reason precedence must be non-empty and unique")
        for values, name in (
            (self.explicit_user_event_types, "explicit user event types"),
            (self.explicit_relevance_event_types, "explicit relevance event types"),
            (self.opportunity_event_types, "opportunity event types"),
            (self.foreground_event_types, "foreground event types"),
            (self.permitted_signal_kinds, "permitted signal kinds"),
        ):
            _unique(values, name)
        identity: JSONObject = {
            "version": self.version,
            "max_dormant_inquiries_examined": self.max_dormant_inquiries_examined,
            "max_opportunities_emitted": self.max_opportunities_emitted,
            "max_qualification_bindings_consumed": (self.max_qualification_bindings_consumed),
            "reason_precedence": [value.value for value in self.reason_precedence],
            "explicit_user_event_types": list(self.explicit_user_event_types),
            "explicit_relevance_event_types": list(self.explicit_relevance_event_types),
            "opportunity_event_types": list(self.opportunity_event_types),
            "foreground_event_types": list(self.foreground_event_types),
            "permitted_signal_kinds": list(self.permitted_signal_kinds),
            "seed_policy_version": self.seed_policy_version,
            "seed_costs": self.seed_costs.to_dict(),
        }
        expected = _canonical_id("reconsideration-discovery-policy", identity)
        if self.policy_id != expected:
            raise ValueError("discovery policy id does not match immutable content")

    def to_dict(self) -> JSONObject:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "max_dormant_inquiries_examined": self.max_dormant_inquiries_examined,
            "max_opportunities_emitted": self.max_opportunities_emitted,
            "max_qualification_bindings_consumed": self.max_qualification_bindings_consumed,
            "reason_precedence": [value.value for value in self.reason_precedence],
            "explicit_user_event_types": list(self.explicit_user_event_types),
            "explicit_relevance_event_types": list(self.explicit_relevance_event_types),
            "opportunity_event_types": list(self.opportunity_event_types),
            "foreground_event_types": list(self.foreground_event_types),
            "permitted_signal_kinds": list(self.permitted_signal_kinds),
            "seed_policy_version": self.seed_policy_version,
            "seed_costs": self.seed_costs.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconsiderationDiscoveryPolicySnapshot:
        value = cls.create(
            version=str(data["version"]),
            max_dormant_inquiries_examined=int(cast(int, data["max_dormant_inquiries_examined"])),
            max_opportunities_emitted=int(cast(int, data["max_opportunities_emitted"])),
            max_qualification_bindings_consumed=int(
                cast(int, data["max_qualification_bindings_consumed"])
            ),
            reason_precedence=tuple(
                DiscoveryReason(value) for value in _strings(data, "reason_precedence")
            ),
            explicit_user_event_types=_strings(data, "explicit_user_event_types"),
            explicit_relevance_event_types=_strings(data, "explicit_relevance_event_types"),
            opportunity_event_types=_strings(data, "opportunity_event_types"),
            foreground_event_types=_strings(data, "foreground_event_types"),
            permitted_signal_kinds=_strings(data, "permitted_signal_kinds"),
            seed_policy_version=str(data["seed_policy_version"]),
            seed_costs=ScarceCognitionCostSnapshot.from_dict(
                cast(Mapping[str, object], data["seed_costs"])
            ),
        )
        if value.policy_id != str(data["policy_id"]):
            raise ValueError("discovery policy id does not match immutable content")
        return value

    def to_event(self, *, source: str, recorded_at: datetime) -> Event:
        _require_aware(recorded_at, "discovery policy recorded_at")
        return Event(
            id=f"reconsideration-discovery-policy-recorded:{self.policy_id}",
            type=DISCOVERY_POLICY_RECORDED_EVENT,
            source=source,
            subject=self.policy_id,
            timestamp=recorded_at,
            payload=self.to_dict(),
        )


@dataclass(frozen=True, slots=True)
class InquiryReconsiderationScopeBinding:
    binding_id: str
    inquiry_id: str
    domain_ids: tuple[str, ...]
    governed_information_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    resolver_id: str
    resolver_version: str
    authority_id: str
    authorization_ref: str
    derived_information_id: str
    information_use_purpose: str
    information_policy_ids: tuple[str, ...]
    information_access_decision_ids: tuple[str, ...]
    bound_at: datetime

    @classmethod
    def create(
        cls,
        *,
        inquiry_id: str,
        domain_ids: tuple[str, ...],
        governed_information_ids: tuple[str, ...],
        evidence_refs: tuple[str, ...],
        resolver_id: str,
        resolver_version: str,
        authority_id: str,
        authorization_ref: str,
        derived_information_id: str,
        information_use_purpose: str,
        information_policy_ids: tuple[str, ...],
        information_access_decision_ids: tuple[str, ...],
        bound_at: datetime,
    ) -> InquiryReconsiderationScopeBinding:
        domains = tuple(sorted(set(domain_ids)))
        information = tuple(sorted(set(governed_information_ids)))
        evidence = tuple(sorted(set(evidence_refs)))
        policies = tuple(sorted(set(information_policy_ids)))
        decisions = tuple(sorted(set(information_access_decision_ids)))
        payload: JSONObject = {
            "inquiry_id": inquiry_id,
            "domain_ids": list(domains),
            "governed_information_ids": list(information),
            "evidence_refs": list(evidence),
            "resolver_id": resolver_id,
            "resolver_version": resolver_version,
            "authority_id": authority_id,
            "authorization_ref": authorization_ref,
            "derived_information_id": derived_information_id,
            "information_use_purpose": information_use_purpose,
            "information_policy_ids": list(policies),
            "information_access_decision_ids": list(decisions),
            "bound_at": bound_at.isoformat(),
        }
        return cls(
            _canonical_id("inquiry-reconsideration-scope", payload),
            inquiry_id,
            domains,
            information,
            evidence,
            resolver_id,
            resolver_version,
            authority_id,
            authorization_ref,
            derived_information_id,
            information_use_purpose,
            policies,
            decisions,
            bound_at,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.binding_id, "scope binding id"),
            (self.inquiry_id, "scope binding inquiry id"),
            (self.resolver_id, "scope resolver id"),
            (self.resolver_version, "scope resolver version"),
            (self.authority_id, "scope authority id"),
            (self.authorization_ref, "scope authorization ref"),
            (self.information_use_purpose, "scope information purpose"),
        ):
            _require_text(value, name)
        for values, name in (
            (self.domain_ids, "scope domains"),
            (self.governed_information_ids, "scope governed information"),
            (self.evidence_refs, "scope evidence"),
            (self.information_policy_ids, "scope information policies"),
            (self.information_access_decision_ids, "scope information decisions"),
        ):
            _unique(values, name, required=True)
        if not self.authorization_ref.startswith("event:"):
            raise ValueError("scope authorization must cite a canonical event")
        validate_opaque_governance_id(
            self.derived_information_id, "scope binding derived information id"
        )
        _require_aware(self.bound_at, "scope binding bound_at")
        identity = self.to_dict()
        identity.pop("binding_id")
        expected = _canonical_id("inquiry-reconsideration-scope", identity)
        if self.binding_id != expected:
            raise ValueError("scope binding id does not match immutable content")

    def to_dict(self) -> JSONObject:
        return {
            "binding_id": self.binding_id,
            "inquiry_id": self.inquiry_id,
            "domain_ids": list(self.domain_ids),
            "governed_information_ids": list(self.governed_information_ids),
            "evidence_refs": list(self.evidence_refs),
            "resolver_id": self.resolver_id,
            "resolver_version": self.resolver_version,
            "authority_id": self.authority_id,
            "authorization_ref": self.authorization_ref,
            "derived_information_id": self.derived_information_id,
            "information_use_purpose": self.information_use_purpose,
            "information_policy_ids": list(self.information_policy_ids),
            "information_access_decision_ids": list(self.information_access_decision_ids),
            "bound_at": self.bound_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> InquiryReconsiderationScopeBinding:
        value = cls.create(
            inquiry_id=str(data["inquiry_id"]),
            domain_ids=_strings(data, "domain_ids"),
            governed_information_ids=_strings(data, "governed_information_ids"),
            evidence_refs=_strings(data, "evidence_refs"),
            resolver_id=str(data["resolver_id"]),
            resolver_version=str(data["resolver_version"]),
            authority_id=str(data["authority_id"]),
            authorization_ref=str(data["authorization_ref"]),
            derived_information_id=str(data["derived_information_id"]),
            information_use_purpose=str(data["information_use_purpose"]),
            information_policy_ids=_strings(data, "information_policy_ids"),
            information_access_decision_ids=_strings(data, "information_access_decision_ids"),
            bound_at=_datetime(data, "bound_at"),
        )
        if value.binding_id != str(data["binding_id"]):
            raise ValueError("scope binding id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return Event(
            id=f"reconsideration-inquiry-scope-bound:{self.binding_id}",
            type=INQUIRY_SCOPE_BOUND_EVENT,
            source=source,
            subject=self.inquiry_id,
            timestamp=self.bound_at,
            payload=self.to_dict(),
            causation_id=self.authorization_ref.removeprefix("event:"),
        )


@dataclass(frozen=True, slots=True)
class EvidenceQualificationBinding:
    """A role/target binding over memory-owned epistemic state."""

    qualification_id: str
    assertion_ref: str
    role: EvidenceQualificationRole
    target_refs: tuple[str, ...]
    qualifier_id: str
    qualifier_version: str
    authority_id: str
    authorization_ref: str
    governed_information_ids: tuple[str, ...]
    derived_information_id: str
    information_use_purpose: str
    information_policy_ids: tuple[str, ...]
    information_access_decision_ids: tuple[str, ...]
    bound_at: datetime

    @classmethod
    def create(
        cls,
        *,
        assertion_ref: str,
        role: EvidenceQualificationRole,
        target_refs: tuple[str, ...],
        qualifier_id: str,
        qualifier_version: str,
        authority_id: str,
        authorization_ref: str,
        governed_information_ids: tuple[str, ...],
        derived_information_id: str,
        information_use_purpose: str,
        information_policy_ids: tuple[str, ...],
        information_access_decision_ids: tuple[str, ...],
        bound_at: datetime,
    ) -> EvidenceQualificationBinding:
        targets = tuple(sorted(set(target_refs)))
        information = tuple(sorted(set(governed_information_ids)))
        policies = tuple(sorted(set(information_policy_ids)))
        decisions = tuple(sorted(set(information_access_decision_ids)))
        payload: JSONObject = {
            "assertion_ref": assertion_ref,
            "role": role.value,
            "target_refs": list(targets),
            "qualifier_id": qualifier_id,
            "qualifier_version": qualifier_version,
            "authority_id": authority_id,
            "authorization_ref": authorization_ref,
            "governed_information_ids": list(information),
            "derived_information_id": derived_information_id,
            "information_use_purpose": information_use_purpose,
            "information_policy_ids": list(policies),
            "information_access_decision_ids": list(decisions),
            "bound_at": bound_at.isoformat(),
        }
        return cls(
            _canonical_id("evidence-qualification", payload),
            assertion_ref,
            role,
            targets,
            qualifier_id,
            qualifier_version,
            authority_id,
            authorization_ref,
            information,
            derived_information_id,
            information_use_purpose,
            policies,
            decisions,
            bound_at,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.qualification_id, "qualification id"),
            (self.assertion_ref, "qualification assertion ref"),
            (self.qualifier_id, "qualifier id"),
            (self.qualifier_version, "qualifier version"),
            (self.authority_id, "qualification authority id"),
            (self.authorization_ref, "qualification authorization ref"),
            (self.information_use_purpose, "qualification information purpose"),
        ):
            _require_text(value, name)
        if not self.assertion_ref.startswith("assertion:"):
            raise ValueError("qualification must bind a SemanticAssertion reference")
        if not self.authorization_ref.startswith("event:"):
            raise ValueError("qualification authorization must cite a canonical event")
        for values, name in (
            (self.target_refs, "qualification targets"),
            (self.governed_information_ids, "qualification governed information"),
            (self.information_policy_ids, "qualification information policies"),
            (self.information_access_decision_ids, "qualification information decisions"),
        ):
            _unique(values, name, required=True)
        validate_opaque_governance_id(
            self.derived_information_id, "qualification derived information id"
        )
        _require_aware(self.bound_at, "qualification bound_at")
        identity = self.to_dict()
        identity.pop("qualification_id")
        expected = _canonical_id("evidence-qualification", identity)
        if self.qualification_id != expected:
            raise ValueError("qualification id does not match immutable content")

    def to_dict(self) -> JSONObject:
        return {
            "qualification_id": self.qualification_id,
            "assertion_ref": self.assertion_ref,
            "role": self.role.value,
            "target_refs": list(self.target_refs),
            "qualifier_id": self.qualifier_id,
            "qualifier_version": self.qualifier_version,
            "authority_id": self.authority_id,
            "authorization_ref": self.authorization_ref,
            "governed_information_ids": list(self.governed_information_ids),
            "derived_information_id": self.derived_information_id,
            "information_use_purpose": self.information_use_purpose,
            "information_policy_ids": list(self.information_policy_ids),
            "information_access_decision_ids": list(self.information_access_decision_ids),
            "bound_at": self.bound_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> EvidenceQualificationBinding:
        value = cls.create(
            assertion_ref=str(data["assertion_ref"]),
            role=EvidenceQualificationRole(str(data["role"])),
            target_refs=_strings(data, "target_refs"),
            qualifier_id=str(data["qualifier_id"]),
            qualifier_version=str(data["qualifier_version"]),
            authority_id=str(data["authority_id"]),
            authorization_ref=str(data["authorization_ref"]),
            governed_information_ids=_strings(data, "governed_information_ids"),
            derived_information_id=str(data["derived_information_id"]),
            information_use_purpose=str(data["information_use_purpose"]),
            information_policy_ids=_strings(data, "information_policy_ids"),
            information_access_decision_ids=_strings(data, "information_access_decision_ids"),
            bound_at=_datetime(data, "bound_at"),
        )
        if value.qualification_id != str(data["qualification_id"]):
            raise ValueError("qualification id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return Event(
            id=f"reconsideration-evidence-qualified:{self.qualification_id}",
            type=EVIDENCE_QUALIFICATION_BOUND_EVENT,
            source=source,
            subject=self.assertion_ref,
            timestamp=self.bound_at,
            payload=self.to_dict(),
            causation_id=self.authorization_ref.removeprefix("event:"),
        )


@dataclass(frozen=True, slots=True)
class ReconsiderationOpportunity:
    opportunity_id: str
    historical_inquiry_id: str
    current_cognitive_basis: CurrentCognitiveBasis
    kind: ReconsiderationOpportunityKind
    discovery_reasons: tuple[DiscoveryReason, ...]
    trigger_event_id: str
    evidence_refs: tuple[str, ...]
    scope_binding_id: str
    qualification_ids: tuple[str, ...]
    existing_candidate_id: str | None
    allocation_context_fingerprint: str | None
    discovery_policy_id: str
    evaluation_cut: int
    admitted_at_head: int
    created_at: datetime
    derived_information_id: str
    seed_policy_version: str
    seed_costs: ScarceCognitionCostSnapshot
    information_use_purpose: str
    information_policy_ids: tuple[str, ...]
    information_access_decision_ids: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        historical_inquiry_id: str,
        current_cognitive_basis: CurrentCognitiveBasis,
        kind: ReconsiderationOpportunityKind,
        discovery_reasons: tuple[DiscoveryReason, ...],
        trigger_event_id: str,
        evidence_refs: tuple[str, ...],
        scope_binding_id: str,
        qualification_ids: tuple[str, ...],
        existing_candidate_id: str | None,
        allocation_context_fingerprint: str | None,
        discovery_policy_id: str,
        evaluation_cut: int,
        admitted_at_head: int,
        created_at: datetime,
        derived_information_id: str,
        seed_policy_version: str,
        seed_costs: ScarceCognitionCostSnapshot,
        information_use_purpose: str,
        information_policy_ids: tuple[str, ...],
        information_access_decision_ids: tuple[str, ...],
    ) -> ReconsiderationOpportunity:
        reasons = tuple(discovery_reasons)
        evidence = tuple(sorted(set(evidence_refs)))
        qualifications = tuple(sorted(set(qualification_ids)))
        policies = tuple(sorted(set(information_policy_ids)))
        decisions = tuple(sorted(set(information_access_decision_ids)))
        identity: JSONObject = {
            "historical_inquiry_id": historical_inquiry_id,
            "current_cognitive_basis": current_cognitive_basis.to_dict(),
            "kind": kind.value,
            "discovery_reasons": [value.value for value in reasons],
            "trigger_event_id": trigger_event_id,
            "evidence_refs": list(evidence),
            "scope_binding_id": scope_binding_id,
            "qualification_ids": list(qualifications),
            "existing_candidate_id": existing_candidate_id,
            "allocation_context_fingerprint": allocation_context_fingerprint,
            "discovery_policy_id": discovery_policy_id,
            "evaluation_cut": evaluation_cut,
            "derived_information_id": derived_information_id,
            "seed_policy_version": seed_policy_version,
            "seed_costs": seed_costs.to_dict(),
            "information_use_purpose": information_use_purpose,
            "information_policy_ids": list(policies),
        }
        return cls(
            _canonical_id("reconsideration-opportunity", identity),
            historical_inquiry_id,
            current_cognitive_basis,
            kind,
            reasons,
            trigger_event_id,
            evidence,
            scope_binding_id,
            qualifications,
            existing_candidate_id,
            allocation_context_fingerprint,
            discovery_policy_id,
            evaluation_cut,
            admitted_at_head,
            created_at,
            derived_information_id,
            seed_policy_version,
            seed_costs,
            information_use_purpose,
            policies,
            decisions,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.opportunity_id, "opportunity id"),
            (self.historical_inquiry_id, "opportunity inquiry id"),
            (self.trigger_event_id, "opportunity trigger event id"),
            (self.scope_binding_id, "opportunity scope binding id"),
            (self.discovery_policy_id, "opportunity discovery policy id"),
            (self.seed_policy_version, "opportunity seed policy version"),
            (self.information_use_purpose, "opportunity information purpose"),
        ):
            _require_text(value, name)
        if not self.discovery_reasons or len(set(self.discovery_reasons)) != len(
            self.discovery_reasons
        ):
            raise ValueError("opportunity discovery reasons must be non-empty and unique")
        _unique(self.evidence_refs, "opportunity evidence", required=True)
        _unique(self.qualification_ids, "opportunity qualifications")
        _unique(self.information_policy_ids, "opportunity policies", required=True)
        _unique(self.information_access_decision_ids, "opportunity access decisions", required=True)
        if self.evaluation_cut <= 0 or self.admitted_at_head < self.evaluation_cut:
            raise ValueError("opportunity causal cuts are inconsistent")
        _require_aware(self.created_at, "opportunity created_at")
        validate_opaque_governance_id(
            self.derived_information_id, "opportunity derived information id"
        )
        if self.kind is ReconsiderationOpportunityKind.REALLOCATE_EXISTING:
            if self.existing_candidate_id is None or self.allocation_context_fingerprint is None:
                raise ValueError("reallocation opportunity requires candidate and context")
        elif self.existing_candidate_id is not None:
            raise ValueError("new revalidation cannot claim an existing candidate")
        identity: JSONObject = {
            "historical_inquiry_id": self.historical_inquiry_id,
            "current_cognitive_basis": self.current_cognitive_basis.to_dict(),
            "kind": self.kind.value,
            "discovery_reasons": [value.value for value in self.discovery_reasons],
            "trigger_event_id": self.trigger_event_id,
            "evidence_refs": list(self.evidence_refs),
            "scope_binding_id": self.scope_binding_id,
            "qualification_ids": list(self.qualification_ids),
            "existing_candidate_id": self.existing_candidate_id,
            "allocation_context_fingerprint": self.allocation_context_fingerprint,
            "discovery_policy_id": self.discovery_policy_id,
            "evaluation_cut": self.evaluation_cut,
            "derived_information_id": self.derived_information_id,
            "seed_policy_version": self.seed_policy_version,
            "seed_costs": self.seed_costs.to_dict(),
            "information_use_purpose": self.information_use_purpose,
            "information_policy_ids": list(self.information_policy_ids),
        }
        expected = _canonical_id("reconsideration-opportunity", identity)
        if self.opportunity_id != expected:
            raise ValueError("opportunity id does not match semantic causal inputs")

    def to_dict(self) -> JSONObject:
        return {
            "opportunity_id": self.opportunity_id,
            "historical_inquiry_id": self.historical_inquiry_id,
            "current_cognitive_basis": self.current_cognitive_basis.to_dict(),
            "kind": self.kind.value,
            "discovery_reasons": [value.value for value in self.discovery_reasons],
            "trigger_event_id": self.trigger_event_id,
            "evidence_refs": list(self.evidence_refs),
            "scope_binding_id": self.scope_binding_id,
            "qualification_ids": list(self.qualification_ids),
            "existing_candidate_id": self.existing_candidate_id,
            "allocation_context_fingerprint": self.allocation_context_fingerprint,
            "discovery_policy_id": self.discovery_policy_id,
            "evaluation_cut": self.evaluation_cut,
            "admitted_at_head": self.admitted_at_head,
            "created_at": self.created_at.isoformat(),
            "derived_information_id": self.derived_information_id,
            "seed_policy_version": self.seed_policy_version,
            "seed_costs": self.seed_costs.to_dict(),
            "information_use_purpose": self.information_use_purpose,
            "information_policy_ids": list(self.information_policy_ids),
            "information_access_decision_ids": list(self.information_access_decision_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconsiderationOpportunity:
        value = cls.create(
            historical_inquiry_id=str(data["historical_inquiry_id"]),
            current_cognitive_basis=CurrentCognitiveBasis.from_dict(
                cast(Mapping[str, object], data["current_cognitive_basis"])
            ),
            kind=ReconsiderationOpportunityKind(str(data["kind"])),
            discovery_reasons=tuple(
                DiscoveryReason(value) for value in _strings(data, "discovery_reasons")
            ),
            trigger_event_id=str(data["trigger_event_id"]),
            evidence_refs=_strings(data, "evidence_refs"),
            scope_binding_id=str(data["scope_binding_id"]),
            qualification_ids=_strings(data, "qualification_ids"),
            existing_candidate_id=(
                str(data["existing_candidate_id"])
                if data.get("existing_candidate_id") is not None
                else None
            ),
            allocation_context_fingerprint=(
                str(data["allocation_context_fingerprint"])
                if data.get("allocation_context_fingerprint") is not None
                else None
            ),
            discovery_policy_id=str(data["discovery_policy_id"]),
            evaluation_cut=int(cast(int, data["evaluation_cut"])),
            admitted_at_head=int(cast(int, data["admitted_at_head"])),
            created_at=_datetime(data, "created_at"),
            derived_information_id=str(data["derived_information_id"]),
            seed_policy_version=str(data["seed_policy_version"]),
            seed_costs=ScarceCognitionCostSnapshot.from_dict(
                cast(Mapping[str, object], data["seed_costs"])
            ),
            information_use_purpose=str(data["information_use_purpose"]),
            information_policy_ids=_strings(data, "information_policy_ids"),
            information_access_decision_ids=_strings(data, "information_access_decision_ids"),
        )
        if value.opportunity_id != str(data["opportunity_id"]):
            raise ValueError("opportunity id does not match semantic causal inputs")
        return value

    def to_event(self, *, source: str) -> Event:
        return Event(
            id=f"reconsideration-opportunity-recorded:{self.opportunity_id}",
            type=OPPORTUNITY_RECORDED_EVENT,
            source=source,
            subject=self.historical_inquiry_id,
            timestamp=self.created_at,
            payload=self.to_dict(),
            causation_id=self.trigger_event_id,
        )


def allocation_context_fingerprint(payload: Mapping[str, JSONValue]) -> str:
    return _canonical_id("allocation-context", payload)


def numeric_assertion_value(value: object, *, role: EvidenceQualificationRole) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{role.value} qualification requires a numeric assertion value")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{role.value} assertion value must be between zero and one")
    return result
