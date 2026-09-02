"""Immutable contracts for deterministic historical-cognition reconsideration."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import cast

from ..endogenous.models import GoverningIntentRef
from ..events import Event
from ..information.models import validate_opaque_governance_id
from ..types import JSONObject, JSONValue, parse_datetime

MANDATE_RECORDED_EVENT = "reconsideration.mandate_recorded"
MANDATE_REVOKED_EVENT = "reconsideration.mandate_revoked"
POLICY_RECORDED_EVENT = "reconsideration.policy_recorded"
SCAN_REQUESTED_EVENT = "reconsideration.scan_requested"
CANDIDATE_RECORDED_EVENT = "reconsideration.candidate_recorded"
ALLOCATION_RECORDED_EVENT = "reconsideration.allocation_recorded"
ALLOCATION_TRACE_RECORDED_EVENT = "reconsideration.allocation_trace_recorded"
ALLOCATION_OUTCOME_LINKED_EVENT = "reconsideration.allocation_outcome_linked"
SHADOW_PROPOSAL_RECORDED_EVENT = "reconsideration.shadow_proposal_recorded"

STABLE_RECONSIDERATION_ALLOCATOR_ID = "stable-greedy-reconsideration"
STABLE_RECONSIDERATION_ALLOCATOR_VERSION = 1
DETERMINISTIC_ESTIMATOR_VERSION = "deterministic/none"

RECONSIDERATION_EVENT_TYPES = (
    MANDATE_RECORDED_EVENT,
    MANDATE_REVOKED_EVENT,
    POLICY_RECORDED_EVENT,
    SCAN_REQUESTED_EVENT,
    CANDIDATE_RECORDED_EVENT,
    ALLOCATION_RECORDED_EVENT,
    ALLOCATION_TRACE_RECORDED_EVENT,
    ALLOCATION_OUTCOME_LINKED_EVENT,
    SHADOW_PROPOSAL_RECORDED_EVENT,
)


class MandateIssuerKind(StrEnum):
    USER = "user"
    CONSTITUTIONAL = "constitutional"


class CognitiveBasisKind(StrEnum):
    LIVE_GOVERNING_INTENT = "live_governing_intent"
    RECONSIDERATION_MANDATE = "reconsideration_mandate"


class HistoricalCognitionKind(StrEnum):
    INQUIRY = "inquiry"


class SurfacingPolicy(StrEnum):
    SHADOW_QUESTION_ONLY = "shadow_question_only"


class AllocationLabel(StrEnum):
    SELECTED = "SELECTED"
    DEFERRED_BY_CONSTRAINT = "DEFERRED_BY_CONSTRAINT"
    SUPPRESSED = "SUPPRESSED"
    EXPLICITLY_REJECTED = "EXPLICITLY_REJECTED"


class EstimateEvidenceKind(StrEnum):
    EXPLICIT = "explicit"
    VOLUNTARY_REENGAGEMENT = "voluntary_reengagement"
    REPEATED_INTEREST = "repeated_interest"
    INFERRED = "inferred"


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


def _bounded(value: float, name: str) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between zero and one")


def _non_negative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")


def _unique(values: tuple[str, ...], name: str, *, required: bool = False) -> None:
    if required and not values:
        raise ValueError(f"{name} must not be empty")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} values must be non-empty")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} values must be unique")


def _datetime(data: Mapping[str, object], key: str) -> datetime:
    value = parse_datetime(cast(str | datetime | None, data.get(key)))
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _optional_datetime(data: Mapping[str, object], key: str) -> datetime | None:
    return parse_datetime(cast(str | datetime | None, data.get(key)))


def _strings(data: Mapping[str, object], key: str) -> tuple[str, ...]:
    values = cast(tuple[object, ...] | list[object], data.get(key, ()))
    return tuple(str(value) for value in values)


def _event(
    *,
    event_id: str,
    event_type: str,
    source: str,
    subject: str,
    timestamp: datetime,
    payload: Mapping[str, JSONValue],
    causation_id: str | None = None,
) -> Event:
    return Event(
        id=event_id,
        type=event_type,
        source=source,
        subject=subject,
        timestamp=timestamp,
        payload=payload,
        causation_id=causation_id,
    )


@dataclass(frozen=True, slots=True)
class ScarceCognitionCostSnapshot:
    compute_units: float = 0.0
    wall_time_seconds: float = 0.0
    monetary_cost: float = 0.0
    attention_units: float = 0.0
    context_switching_units: float = 0.0
    intrusion_units: float = 0.0
    interruption_units: float = 0.0
    privacy_exposure_units: float = 0.0
    opportunity_cost_units: float = 0.0
    revalidation_units: float = 0.0

    def __post_init__(self) -> None:
        for value, name in (
            (self.compute_units, "compute units"),
            (self.wall_time_seconds, "wall time"),
            (self.monetary_cost, "monetary cost"),
            (self.attention_units, "attention units"),
            (self.context_switching_units, "context switching cost"),
            (self.intrusion_units, "intrusion cost"),
            (self.interruption_units, "interruption units"),
            (self.privacy_exposure_units, "privacy exposure"),
            (self.opportunity_cost_units, "opportunity cost"),
            (self.revalidation_units, "revalidation cost"),
        ):
            _non_negative(value, name)

    def to_dict(self) -> JSONObject:
        return {
            "compute_units": self.compute_units,
            "wall_time_seconds": self.wall_time_seconds,
            "monetary_cost": self.monetary_cost,
            "attention_units": self.attention_units,
            "context_switching_units": self.context_switching_units,
            "intrusion_units": self.intrusion_units,
            "interruption_units": self.interruption_units,
            "privacy_exposure_units": self.privacy_exposure_units,
            "opportunity_cost_units": self.opportunity_cost_units,
            "revalidation_units": self.revalidation_units,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ScarceCognitionCostSnapshot:
        return cls(
            compute_units=float(cast(float, data.get("compute_units", 0.0))),
            wall_time_seconds=float(cast(float, data.get("wall_time_seconds", 0.0))),
            monetary_cost=float(cast(float, data.get("monetary_cost", 0.0))),
            attention_units=float(cast(float, data.get("attention_units", 0.0))),
            context_switching_units=float(cast(float, data.get("context_switching_units", 0.0))),
            intrusion_units=float(cast(float, data.get("intrusion_units", 0.0))),
            interruption_units=float(cast(float, data.get("interruption_units", 0.0))),
            privacy_exposure_units=float(cast(float, data.get("privacy_exposure_units", 0.0))),
            opportunity_cost_units=float(cast(float, data.get("opportunity_cost_units", 0.0))),
            revalidation_units=float(cast(float, data.get("revalidation_units", 0.0))),
        )

    def plus(self, other: ScarceCognitionCostSnapshot) -> ScarceCognitionCostSnapshot:
        return ScarceCognitionCostSnapshot(
            **{
                name: round(getattr(self, name) + getattr(other, name), 12)
                for name in self.__dataclass_fields__
            }
        )

    def minus(self, other: ScarceCognitionCostSnapshot) -> ScarceCognitionCostSnapshot:
        values = {
            name: round(getattr(self, name) - getattr(other, name), 12)
            for name in self.__dataclass_fields__
        }
        if any(value < -1e-9 for value in values.values()):
            raise ValueError("scarce cognition use exceeds its budget")
        return ScarceCognitionCostSnapshot(
            **{name: max(0.0, value) for name, value in values.items()}
        )

    def fits_within(self, ceiling: ScarceCognitionCostSnapshot) -> bool:
        return all(
            getattr(self, name) <= getattr(ceiling, name) + 1e-12
            for name in self.__dataclass_fields__
        )


@dataclass(frozen=True, slots=True)
class ScarceCognitionBudget:
    budget_id: str
    max_candidates: int
    ceiling: ScarceCognitionCostSnapshot

    @classmethod
    def create(
        cls,
        *,
        max_candidates: int,
        ceiling: ScarceCognitionCostSnapshot,
    ) -> ScarceCognitionBudget:
        payload: JSONObject = {
            "max_candidates": max_candidates,
            "ceiling": ceiling.to_dict(),
        }
        return cls(_canonical_id("scarce-cognition-budget", payload), max_candidates, ceiling)

    def __post_init__(self) -> None:
        _require_text(self.budget_id, "scarce cognition budget id")
        if self.max_candidates <= 0:
            raise ValueError("scarce cognition budget must permit at least one candidate")
        identity: JSONObject = {
            "max_candidates": self.max_candidates,
            "ceiling": self.ceiling.to_dict(),
        }
        if self.budget_id != _canonical_id("scarce-cognition-budget", identity):
            raise ValueError("scarce cognition budget id does not match its ceiling")

    def to_dict(self) -> JSONObject:
        return {
            "budget_id": self.budget_id,
            "max_candidates": self.max_candidates,
            "ceiling": self.ceiling.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ScarceCognitionBudget:
        return cls(
            budget_id=str(data["budget_id"]),
            max_candidates=int(cast(int, data["max_candidates"])),
            ceiling=ScarceCognitionCostSnapshot.from_dict(
                cast(Mapping[str, object], data["ceiling"])
            ),
        )

    def fits_within(self, other: ScarceCognitionBudget) -> bool:
        return self.max_candidates <= other.max_candidates and self.ceiling.fits_within(
            other.ceiling
        )


@dataclass(frozen=True, slots=True)
class ReconsiderationMandate:
    mandate_id: str
    revision_id: str
    revision: int
    issuer_id: str
    issuer_kind: MandateIssuerKind
    authority_id: str
    authorization_ref: str
    scope: str
    candidate_classes: tuple[str, ...]
    candidate_domains: tuple[str, ...]
    budget: ScarceCognitionBudget
    minimum_interval_seconds: float
    trigger_event_types: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    maximum_interruption_units: float
    surfacing_policy: SurfacingPolicy
    information_use_purpose: str
    information_policy_ids: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        mandate_id: str,
        revision: int,
        issuer_id: str,
        issuer_kind: MandateIssuerKind,
        authority_id: str,
        authorization_ref: str,
        scope: str,
        candidate_classes: tuple[str, ...],
        candidate_domains: tuple[str, ...],
        budget: ScarceCognitionBudget,
        minimum_interval_seconds: float,
        trigger_event_types: tuple[str, ...],
        issued_at: datetime,
        expires_at: datetime,
        maximum_interruption_units: float,
        surfacing_policy: SurfacingPolicy,
        information_use_purpose: str,
        information_policy_ids: tuple[str, ...],
    ) -> ReconsiderationMandate:
        classes = tuple(sorted(set(candidate_classes)))
        domains = tuple(sorted(set(candidate_domains)))
        triggers = tuple(sorted(set(trigger_event_types)))
        policies = tuple(sorted(set(information_policy_ids)))
        payload: JSONObject = {
            "mandate_id": mandate_id,
            "revision": revision,
            "issuer_id": issuer_id,
            "issuer_kind": issuer_kind.value,
            "authority_id": authority_id,
            "authorization_ref": authorization_ref,
            "scope": scope,
            "candidate_classes": list(classes),
            "candidate_domains": list(domains),
            "budget": budget.to_dict(),
            "minimum_interval_seconds": minimum_interval_seconds,
            "trigger_event_types": list(triggers),
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "maximum_interruption_units": maximum_interruption_units,
            "surfacing_policy": surfacing_policy.value,
            "information_use_purpose": information_use_purpose,
            "information_policy_ids": list(policies),
        }
        return cls(
            mandate_id=mandate_id,
            revision_id=_canonical_id("reconsideration-mandate", payload),
            revision=revision,
            issuer_id=issuer_id,
            issuer_kind=issuer_kind,
            authority_id=authority_id,
            authorization_ref=authorization_ref,
            scope=scope,
            candidate_classes=classes,
            candidate_domains=domains,
            budget=budget,
            minimum_interval_seconds=minimum_interval_seconds,
            trigger_event_types=triggers,
            issued_at=issued_at,
            expires_at=expires_at,
            maximum_interruption_units=maximum_interruption_units,
            surfacing_policy=surfacing_policy,
            information_use_purpose=information_use_purpose,
            information_policy_ids=policies,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.mandate_id, "mandate id"),
            (self.revision_id, "mandate revision id"),
            (self.issuer_id, "mandate issuer"),
            (self.authority_id, "mandate authority"),
            (self.authorization_ref, "mandate authorization ref"),
            (self.scope, "mandate scope"),
            (self.information_use_purpose, "mandate information-use purpose"),
        ):
            _require_text(value, name)
        if self.revision <= 0:
            raise ValueError("mandate revision must be positive")
        if not self.authorization_ref.startswith("event:"):
            raise ValueError("mandate authorization must cite a canonical event")
        _unique(self.candidate_classes, "mandate candidate classes", required=True)
        _unique(self.candidate_domains, "mandate candidate domains", required=True)
        _unique(self.trigger_event_types, "mandate trigger event types")
        _unique(self.information_policy_ids, "mandate information policy ids", required=True)
        _non_negative(self.minimum_interval_seconds, "mandate minimum interval")
        _non_negative(self.maximum_interruption_units, "mandate interruption ceiling")
        _require_aware(self.issued_at, "mandate issued_at")
        _require_aware(self.expires_at, "mandate expires_at")
        if self.expires_at <= self.issued_at:
            raise ValueError("mandate expiry must follow issuance")
        identity = self.to_dict()
        identity.pop("revision_id")
        if self.revision_id != _canonical_id("reconsideration-mandate", identity):
            raise ValueError("mandate revision id does not match immutable content")

    def to_dict(self) -> JSONObject:
        return {
            "mandate_id": self.mandate_id,
            "revision_id": self.revision_id,
            "revision": self.revision,
            "issuer_id": self.issuer_id,
            "issuer_kind": self.issuer_kind.value,
            "authority_id": self.authority_id,
            "authorization_ref": self.authorization_ref,
            "scope": self.scope,
            "candidate_classes": list(self.candidate_classes),
            "candidate_domains": list(self.candidate_domains),
            "budget": self.budget.to_dict(),
            "minimum_interval_seconds": self.minimum_interval_seconds,
            "trigger_event_types": list(self.trigger_event_types),
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "maximum_interruption_units": self.maximum_interruption_units,
            "surfacing_policy": self.surfacing_policy.value,
            "information_use_purpose": self.information_use_purpose,
            "information_policy_ids": list(self.information_policy_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconsiderationMandate:
        value = cls.create(
            mandate_id=str(data["mandate_id"]),
            revision=int(cast(int, data["revision"])),
            issuer_id=str(data["issuer_id"]),
            issuer_kind=MandateIssuerKind(str(data["issuer_kind"])),
            authority_id=str(data["authority_id"]),
            authorization_ref=str(data["authorization_ref"]),
            scope=str(data["scope"]),
            candidate_classes=_strings(data, "candidate_classes"),
            candidate_domains=_strings(data, "candidate_domains"),
            budget=ScarceCognitionBudget.from_dict(cast(Mapping[str, object], data["budget"])),
            minimum_interval_seconds=float(cast(float, data["minimum_interval_seconds"])),
            trigger_event_types=_strings(data, "trigger_event_types"),
            issued_at=_datetime(data, "issued_at"),
            expires_at=_datetime(data, "expires_at"),
            maximum_interruption_units=float(cast(float, data["maximum_interruption_units"])),
            surfacing_policy=SurfacingPolicy(str(data["surfacing_policy"])),
            information_use_purpose=str(data["information_use_purpose"]),
            information_policy_ids=_strings(data, "information_policy_ids"),
        )
        if value.revision_id != str(data["revision_id"]):
            raise ValueError("mandate revision id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"reconsideration-mandate-recorded:{self.revision_id}",
            event_type=MANDATE_RECORDED_EVENT,
            source=source,
            subject=self.mandate_id,
            timestamp=self.issued_at,
            payload=self.to_dict(),
            causation_id=self.authorization_ref.removeprefix("event:"),
        )


@dataclass(frozen=True, slots=True)
class ReconsiderationMandateRevocation:
    revocation_id: str
    mandate_id: str
    mandate_revision_id: str
    issuer_id: str
    authority_id: str
    authorization_ref: str
    reason: str
    revoked_at: datetime

    @classmethod
    def create(
        cls,
        *,
        mandate_id: str,
        mandate_revision_id: str,
        issuer_id: str,
        authority_id: str,
        authorization_ref: str,
        reason: str,
        revoked_at: datetime,
    ) -> ReconsiderationMandateRevocation:
        payload: JSONObject = {
            "mandate_id": mandate_id,
            "mandate_revision_id": mandate_revision_id,
            "issuer_id": issuer_id,
            "authority_id": authority_id,
            "authorization_ref": authorization_ref,
            "reason": reason,
            "revoked_at": revoked_at.isoformat(),
        }
        return cls(
            _canonical_id("reconsideration-revocation", payload),
            mandate_id,
            mandate_revision_id,
            issuer_id,
            authority_id,
            authorization_ref,
            reason,
            revoked_at,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.revocation_id, "mandate revocation id"),
            (self.mandate_id, "revoked mandate id"),
            (self.mandate_revision_id, "revoked mandate revision"),
            (self.issuer_id, "revocation issuer"),
            (self.authority_id, "revocation authority"),
            (self.authorization_ref, "revocation authorization ref"),
            (self.reason, "revocation reason"),
        ):
            _require_text(value, name)
        if not self.authorization_ref.startswith("event:"):
            raise ValueError("revocation authorization must cite a canonical event")
        _require_aware(self.revoked_at, "revoked_at")
        identity = self.to_dict()
        identity.pop("revocation_id")
        if self.revocation_id != _canonical_id("reconsideration-revocation", identity):
            raise ValueError("mandate revocation id does not match immutable content")

    def to_dict(self) -> JSONObject:
        return {
            "revocation_id": self.revocation_id,
            "mandate_id": self.mandate_id,
            "mandate_revision_id": self.mandate_revision_id,
            "issuer_id": self.issuer_id,
            "authority_id": self.authority_id,
            "authorization_ref": self.authorization_ref,
            "reason": self.reason,
            "revoked_at": self.revoked_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconsiderationMandateRevocation:
        value = cls.create(
            mandate_id=str(data["mandate_id"]),
            mandate_revision_id=str(data["mandate_revision_id"]),
            issuer_id=str(data["issuer_id"]),
            authority_id=str(data["authority_id"]),
            authorization_ref=str(data["authorization_ref"]),
            reason=str(data["reason"]),
            revoked_at=_datetime(data, "revoked_at"),
        )
        if value.revocation_id != str(data["revocation_id"]):
            raise ValueError("mandate revocation id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"reconsideration-mandate-revoked:{self.revocation_id}",
            event_type=MANDATE_REVOKED_EVENT,
            source=source,
            subject=self.mandate_id,
            timestamp=self.revoked_at,
            payload=self.to_dict(),
            causation_id=self.authorization_ref.removeprefix("event:"),
        )


@dataclass(frozen=True, slots=True)
class CurrentCognitiveBasis:
    basis_id: str
    kind: CognitiveBasisKind
    live_intent_ref: GoverningIntentRef | None = None
    mandate_revision_id: str | None = None

    @classmethod
    def from_live_intent(cls, ref: GoverningIntentRef) -> CurrentCognitiveBasis:
        payload: JSONObject = {
            "kind": CognitiveBasisKind.LIVE_GOVERNING_INTENT.value,
            "ref": ref.to_dict(),
        }
        return cls(
            _canonical_id("cognitive-basis", payload),
            CognitiveBasisKind.LIVE_GOVERNING_INTENT,
            ref,
            None,
        )

    @classmethod
    def from_mandate(cls, mandate_revision_id: str) -> CurrentCognitiveBasis:
        payload: JSONObject = {
            "kind": CognitiveBasisKind.RECONSIDERATION_MANDATE.value,
            "mandate_revision_id": mandate_revision_id,
        }
        return cls(
            _canonical_id("cognitive-basis", payload),
            CognitiveBasisKind.RECONSIDERATION_MANDATE,
            None,
            mandate_revision_id,
        )

    def __post_init__(self) -> None:
        _require_text(self.basis_id, "current cognitive basis id")
        if self.kind is CognitiveBasisKind.LIVE_GOVERNING_INTENT:
            if self.live_intent_ref is None or self.mandate_revision_id is not None:
                raise ValueError("live cognitive basis requires only a live intent reference")
            identity: JSONObject = {
                "kind": self.kind.value,
                "ref": self.live_intent_ref.to_dict(),
            }
        else:
            if self.mandate_revision_id is None or self.live_intent_ref is not None:
                raise ValueError("mandate cognitive basis requires only a mandate revision")
            identity = {
                "kind": self.kind.value,
                "mandate_revision_id": self.mandate_revision_id,
            }
        if self.basis_id != _canonical_id("cognitive-basis", identity):
            raise ValueError("current cognitive basis id does not match immutable content")

    def to_dict(self) -> JSONObject:
        return {
            "basis_id": self.basis_id,
            "kind": self.kind.value,
            "live_intent_ref": self.live_intent_ref.to_dict() if self.live_intent_ref else None,
            "mandate_revision_id": self.mandate_revision_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CurrentCognitiveBasis:
        kind = CognitiveBasisKind(str(data["kind"]))
        if kind is CognitiveBasisKind.LIVE_GOVERNING_INTENT:
            value = cls.from_live_intent(
                GoverningIntentRef.from_dict(cast(Mapping[str, object], data["live_intent_ref"]))
            )
        else:
            value = cls.from_mandate(str(data["mandate_revision_id"]))
        if value.basis_id != str(data["basis_id"]):
            raise ValueError("current cognitive basis id does not match immutable content")
        return value


@dataclass(frozen=True, slots=True)
class HistoricalCognitionRef:
    kind: HistoricalCognitionKind
    inquiry_id: str
    epoch_id: str
    historical_causal_cursor: int
    historical_governing_intent_refs: tuple[GoverningIntentRef, ...]
    historical_evidence_refs: tuple[str, ...]
    governed_information_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.inquiry_id, "historical inquiry id")
        _require_text(self.epoch_id, "historical epoch id")
        if self.historical_causal_cursor <= 0:
            raise ValueError("historical causal cursor must identify a canonical cut")
        if not self.historical_governing_intent_refs:
            raise ValueError("historical cognition requires its original governing intent")
        _unique(self.historical_evidence_refs, "historical evidence refs", required=True)
        _unique(self.governed_information_ids, "governed historical information", required=True)

    def to_dict(self) -> JSONObject:
        return {
            "kind": self.kind.value,
            "inquiry_id": self.inquiry_id,
            "epoch_id": self.epoch_id,
            "historical_causal_cursor": self.historical_causal_cursor,
            "historical_governing_intent_refs": [
                value.to_dict() for value in self.historical_governing_intent_refs
            ],
            "historical_evidence_refs": list(self.historical_evidence_refs),
            "governed_information_ids": list(self.governed_information_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> HistoricalCognitionRef:
        refs = cast(tuple[object, ...] | list[object], data["historical_governing_intent_refs"])
        return cls(
            kind=HistoricalCognitionKind(str(data["kind"])),
            inquiry_id=str(data["inquiry_id"]),
            epoch_id=str(data["epoch_id"]),
            historical_causal_cursor=int(cast(int, data["historical_causal_cursor"])),
            historical_governing_intent_refs=tuple(
                GoverningIntentRef.from_dict(cast(Mapping[str, object], value)) for value in refs
            ),
            historical_evidence_refs=_strings(data, "historical_evidence_refs"),
            governed_information_ids=_strings(data, "governed_information_ids"),
        )


@dataclass(frozen=True, slots=True)
class EvidenceBackedEstimate:
    value: float
    kind: EstimateEvidenceKind
    confidence: float
    evidence_refs: tuple[str, ...]
    observed_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        _bounded(self.value, "estimate value")
        _bounded(self.confidence, "estimate confidence")
        _unique(self.evidence_refs, "estimate evidence refs", required=True)
        _require_aware(self.observed_at, "estimate observed_at")
        _require_aware(self.valid_until, "estimate valid_until")
        if self.valid_until <= self.observed_at:
            raise ValueError("estimate validity must follow its observation")

    def to_dict(self) -> JSONObject:
        return {
            "value": self.value,
            "kind": self.kind.value,
            "confidence": self.confidence,
            "evidence_refs": list(self.evidence_refs),
            "observed_at": self.observed_at.isoformat(),
            "valid_until": self.valid_until.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> EvidenceBackedEstimate:
        return cls(
            value=float(cast(float, data["value"])),
            kind=EstimateEvidenceKind(str(data["kind"])),
            confidence=float(cast(float, data["confidence"])),
            evidence_refs=_strings(data, "evidence_refs"),
            observed_at=_datetime(data, "observed_at"),
            valid_until=_datetime(data, "valid_until"),
        )


@dataclass(frozen=True, slots=True)
class ReconsiderationFeatureSnapshot:
    unresolvedness: float
    evidence_freshness: float
    meaningful_new_evidence: float
    opportunity_window: float
    current_basis_validity: float
    value_alignment_estimate: EvidenceBackedEstimate | None
    expected_outcome_value: EvidenceBackedEstimate | None
    motivation_estimate: EvidenceBackedEstimate | None
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, name in (
            (self.unresolvedness, "unresolvedness"),
            (self.evidence_freshness, "evidence freshness"),
            (self.meaningful_new_evidence, "meaningful new evidence"),
            (self.opportunity_window, "opportunity window"),
            (self.current_basis_validity, "current basis validity"),
        ):
            _bounded(value, name)
        _unique(self.provenance_refs, "feature provenance refs", required=True)

    @property
    def critical_features_known(self) -> bool:
        return all(
            value is not None
            for value in (
                self.value_alignment_estimate,
                self.expected_outcome_value,
                self.motivation_estimate,
            )
        )

    def estimates(self) -> tuple[EvidenceBackedEstimate, ...]:
        return tuple(
            value
            for value in (
                self.value_alignment_estimate,
                self.expected_outcome_value,
                self.motivation_estimate,
            )
            if value is not None
        )

    def to_dict(self) -> JSONObject:
        return {
            "unresolvedness": self.unresolvedness,
            "evidence_freshness": self.evidence_freshness,
            "meaningful_new_evidence": self.meaningful_new_evidence,
            "opportunity_window": self.opportunity_window,
            "current_basis_validity": self.current_basis_validity,
            "value_alignment_estimate": (
                self.value_alignment_estimate.to_dict() if self.value_alignment_estimate else None
            ),
            "expected_outcome_value": (
                self.expected_outcome_value.to_dict() if self.expected_outcome_value else None
            ),
            "motivation_estimate": (
                self.motivation_estimate.to_dict() if self.motivation_estimate else None
            ),
            "provenance_refs": list(self.provenance_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconsiderationFeatureSnapshot:
        def estimate(key: str) -> EvidenceBackedEstimate | None:
            raw = data.get(key)
            return (
                EvidenceBackedEstimate.from_dict(cast(Mapping[str, object], raw))
                if raw is not None
                else None
            )

        return cls(
            unresolvedness=float(cast(float, data["unresolvedness"])),
            evidence_freshness=float(cast(float, data["evidence_freshness"])),
            meaningful_new_evidence=float(cast(float, data["meaningful_new_evidence"])),
            opportunity_window=float(cast(float, data["opportunity_window"])),
            current_basis_validity=float(cast(float, data["current_basis_validity"])),
            value_alignment_estimate=estimate("value_alignment_estimate"),
            expected_outcome_value=estimate("expected_outcome_value"),
            motivation_estimate=estimate("motivation_estimate"),
            provenance_refs=_strings(data, "provenance_refs"),
        )


@dataclass(frozen=True, slots=True)
class ReconsiderationSeed:
    inquiry_id: str
    domain: str
    current_evidence_refs: tuple[str, ...]
    governed_information_ids: tuple[str, ...]
    features: ReconsiderationFeatureSnapshot
    costs: ScarceCognitionCostSnapshot

    def __post_init__(self) -> None:
        _require_text(self.inquiry_id, "reconsideration seed inquiry id")
        _require_text(self.domain, "reconsideration seed domain")
        _unique(self.current_evidence_refs, "current revalidation evidence", required=True)
        _unique(self.governed_information_ids, "seed governed information", required=True)
        object.__setattr__(
            self,
            "current_evidence_refs",
            tuple(sorted(self.current_evidence_refs)),
        )
        object.__setattr__(
            self,
            "governed_information_ids",
            tuple(sorted(self.governed_information_ids)),
        )

    def to_dict(self) -> JSONObject:
        return {
            "inquiry_id": self.inquiry_id,
            "domain": self.domain,
            "current_evidence_refs": list(self.current_evidence_refs),
            "governed_information_ids": list(self.governed_information_ids),
            "features": self.features.to_dict(),
            "costs": self.costs.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ReconsiderationCandidateInput:
    candidate_id: str
    historical: HistoricalCognitionRef
    derived_information_id: str
    seed: ReconsiderationSeed
    information_access_decision_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.candidate_id, "reconsideration input candidate id")
        validate_opaque_governance_id(
            self.derived_information_id,
            "reconsideration candidate derived information id",
        )
        if self.historical.inquiry_id != self.seed.inquiry_id:
            raise ValueError("candidate input historical Inquiry differs from its seed")
        _unique(
            self.information_access_decision_ids,
            "reconsideration access decisions",
            required=True,
        )
        object.__setattr__(
            self,
            "information_access_decision_ids",
            tuple(sorted(self.information_access_decision_ids)),
        )

    def to_dict(self) -> JSONObject:
        return {
            "candidate_id": self.candidate_id,
            "historical": self.historical.to_dict(),
            "derived_information_id": self.derived_information_id,
            "seed": self.seed.to_dict(),
            "information_access_decision_ids": list(self.information_access_decision_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconsiderationCandidateInput:
        seed_data = cast(Mapping[str, object], data["seed"])
        seed = ReconsiderationSeed(
            inquiry_id=str(seed_data["inquiry_id"]),
            domain=str(seed_data["domain"]),
            current_evidence_refs=_strings(seed_data, "current_evidence_refs"),
            governed_information_ids=_strings(seed_data, "governed_information_ids"),
            features=ReconsiderationFeatureSnapshot.from_dict(
                cast(Mapping[str, object], seed_data["features"])
            ),
            costs=ScarceCognitionCostSnapshot.from_dict(
                cast(Mapping[str, object], seed_data["costs"])
            ),
        )
        return cls(
            candidate_id=str(data["candidate_id"]),
            historical=HistoricalCognitionRef.from_dict(
                cast(Mapping[str, object], data["historical"])
            ),
            derived_information_id=str(data["derived_information_id"]),
            seed=seed,
            information_access_decision_ids=_strings(
                data,
                "information_access_decision_ids",
            ),
        )


@dataclass(frozen=True, slots=True)
class ReconsiderationPolicySnapshot:
    policy_id: str
    version: str
    allocator_id: str
    allocator_version: int
    feature_weights: Mapping[str, float]
    cost_weights: Mapping[str, float]
    minimum_net_voc: float
    foreground_event_types: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        version: str,
        feature_weights: Mapping[str, float] | None = None,
        cost_weights: Mapping[str, float] | None = None,
        minimum_net_voc: float = 0.0,
        foreground_event_types: tuple[str, ...] = (
            "work.order_recorded",
            "decision.proposed",
        ),
    ) -> ReconsiderationPolicySnapshot:
        features = dict(
            feature_weights
            or {
                "unresolvedness": 1.0,
                "evidence_freshness": 0.5,
                "meaningful_new_evidence": 1.0,
                "opportunity_window": 0.5,
                "current_basis_validity": 1.0,
                "value_alignment_estimate": 1.0,
                "expected_outcome_value": 1.0,
                "motivation_estimate": 0.5,
            }
        )
        costs = dict(
            cost_weights
            or {
                "compute_units": 1.0,
                "wall_time_seconds": 0.01,
                "monetary_cost": 1.0,
                "attention_units": 1.0,
                "context_switching_units": 1.0,
                "intrusion_units": 1.0,
                "interruption_units": 1.0,
                "privacy_exposure_units": 1.0,
                "opportunity_cost_units": 1.0,
                "revalidation_units": 1.0,
            }
        )
        foreground = tuple(sorted(set(foreground_event_types)))
        payload: JSONObject = {
            "version": version,
            "allocator_id": STABLE_RECONSIDERATION_ALLOCATOR_ID,
            "allocator_version": STABLE_RECONSIDERATION_ALLOCATOR_VERSION,
            "feature_weights": cast(JSONObject, features),
            "cost_weights": cast(JSONObject, costs),
            "minimum_net_voc": minimum_net_voc,
            "foreground_event_types": list(foreground),
        }
        return cls(
            _canonical_id("reconsideration-policy", payload),
            version,
            STABLE_RECONSIDERATION_ALLOCATOR_ID,
            STABLE_RECONSIDERATION_ALLOCATOR_VERSION,
            features,
            costs,
            minimum_net_voc,
            foreground,
        )

    def __post_init__(self) -> None:
        _require_text(self.policy_id, "reconsideration policy id")
        _require_text(self.version, "reconsideration policy version")
        _require_text(self.allocator_id, "reconsideration allocator id")
        if self.allocator_version <= 0:
            raise ValueError("reconsideration allocator version must be positive")
        if set(self.feature_weights) != {
            "unresolvedness",
            "evidence_freshness",
            "meaningful_new_evidence",
            "opportunity_window",
            "current_basis_validity",
            "value_alignment_estimate",
            "expected_outcome_value",
            "motivation_estimate",
        }:
            raise ValueError("reconsideration feature weights are incomplete")
        if set(self.cost_weights) != set(ScarceCognitionCostSnapshot.__dataclass_fields__):
            raise ValueError("reconsideration cost weights are incomplete")
        for value in (*self.feature_weights.values(), *self.cost_weights.values()):
            _non_negative(value, "reconsideration policy weight")
        _non_negative(self.minimum_net_voc, "minimum reconsideration NetVOC")
        _unique(self.foreground_event_types, "foreground event types", required=True)
        identity: JSONObject = {
            "version": self.version,
            "allocator_id": self.allocator_id,
            "allocator_version": self.allocator_version,
            "feature_weights": cast(JSONObject, dict(self.feature_weights)),
            "cost_weights": cast(JSONObject, dict(self.cost_weights)),
            "minimum_net_voc": self.minimum_net_voc,
            "foreground_event_types": list(self.foreground_event_types),
        }
        if self.policy_id != _canonical_id("reconsideration-policy", identity):
            raise ValueError("reconsideration policy identity is inconsistent")
        object.__setattr__(self, "feature_weights", MappingProxyType(dict(self.feature_weights)))
        object.__setattr__(self, "cost_weights", MappingProxyType(dict(self.cost_weights)))

    def to_dict(self) -> JSONObject:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "allocator_id": self.allocator_id,
            "allocator_version": self.allocator_version,
            "feature_weights": dict(self.feature_weights),
            "cost_weights": dict(self.cost_weights),
            "minimum_net_voc": self.minimum_net_voc,
            "foreground_event_types": list(self.foreground_event_types),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconsiderationPolicySnapshot:
        value = cls.create(
            version=str(data["version"]),
            feature_weights={
                str(key): float(cast(float, value))
                for key, value in cast(Mapping[str, object], data["feature_weights"]).items()
            },
            cost_weights={
                str(key): float(cast(float, value))
                for key, value in cast(Mapping[str, object], data["cost_weights"]).items()
            },
            minimum_net_voc=float(cast(float, data["minimum_net_voc"])),
            foreground_event_types=_strings(data, "foreground_event_types"),
        )
        if value.policy_id != str(data["policy_id"]):
            raise ValueError("reconsideration policy id does not match immutable content")
        return value

    def to_event(self, *, source: str, recorded_at: datetime) -> Event:
        return _event(
            event_id=f"reconsideration-policy-recorded:{self.policy_id}",
            event_type=POLICY_RECORDED_EVENT,
            source=source,
            subject=self.policy_id,
            timestamp=recorded_at,
            payload=self.to_dict(),
        )


@dataclass(frozen=True, slots=True)
class ReconsiderationScanRequest:
    request_id: str
    basis: CurrentCognitiveBasis
    policy_id: str
    budget: ScarceCognitionBudget
    maximum_interruption_units: float
    candidate_inputs: tuple[ReconsiderationCandidateInput, ...]
    information_use_purpose: str
    information_policy_ids: tuple[str, ...]
    requested_at: datetime
    trigger_event_id: str | None
    foreground_demand_refs: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        basis: CurrentCognitiveBasis,
        policy_id: str,
        budget: ScarceCognitionBudget,
        maximum_interruption_units: float,
        candidate_inputs: tuple[ReconsiderationCandidateInput, ...],
        information_use_purpose: str,
        information_policy_ids: tuple[str, ...],
        requested_at: datetime,
        trigger_event_id: str | None,
        foreground_demand_refs: tuple[str, ...] = (),
    ) -> ReconsiderationScanRequest:
        inputs = tuple(sorted(candidate_inputs, key=lambda value: value.seed.inquiry_id))
        policies = tuple(sorted(set(information_policy_ids)))
        foreground = tuple(sorted(set(foreground_demand_refs)))
        payload: JSONObject = {
            "basis": basis.to_dict(),
            "policy_id": policy_id,
            "budget": budget.to_dict(),
            "maximum_interruption_units": maximum_interruption_units,
            "candidate_inputs": [value.to_dict() for value in inputs],
            "information_use_purpose": information_use_purpose,
            "information_policy_ids": list(policies),
            "requested_at": requested_at.isoformat(),
            "trigger_event_id": trigger_event_id,
            "foreground_demand_refs": list(foreground),
        }
        return cls(
            _canonical_id("reconsideration-scan", payload),
            basis,
            policy_id,
            budget,
            maximum_interruption_units,
            inputs,
            information_use_purpose,
            policies,
            requested_at,
            trigger_event_id,
            foreground,
        )

    def __post_init__(self) -> None:
        _require_text(self.request_id, "reconsideration scan id")
        _require_text(self.policy_id, "reconsideration scan policy")
        _require_text(self.information_use_purpose, "reconsideration information purpose")
        _non_negative(self.maximum_interruption_units, "scan interruption ceiling")
        if not self.candidate_inputs:
            raise ValueError("reconsideration scan requires candidate inputs")
        inquiry_ids = tuple(value.seed.inquiry_id for value in self.candidate_inputs)
        _unique(inquiry_ids, "reconsideration scan inquiry ids", required=True)
        _unique(
            tuple(value.candidate_id for value in self.candidate_inputs),
            "reconsideration scan candidate ids",
            required=True,
        )
        _unique(self.information_policy_ids, "scan information policy ids", required=True)
        _unique(self.foreground_demand_refs, "scan foreground demand refs")
        _require_aware(self.requested_at, "reconsideration requested_at")
        identity = self.to_dict()
        identity.pop("request_id")
        if self.request_id != _canonical_id("reconsideration-scan", identity):
            raise ValueError("reconsideration scan id does not match immutable content")

    def to_dict(self) -> JSONObject:
        return {
            "request_id": self.request_id,
            "basis": self.basis.to_dict(),
            "policy_id": self.policy_id,
            "budget": self.budget.to_dict(),
            "maximum_interruption_units": self.maximum_interruption_units,
            "candidate_inputs": [value.to_dict() for value in self.candidate_inputs],
            "information_use_purpose": self.information_use_purpose,
            "information_policy_ids": list(self.information_policy_ids),
            "requested_at": self.requested_at.isoformat(),
            "trigger_event_id": self.trigger_event_id,
            "foreground_demand_refs": list(self.foreground_demand_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconsiderationScanRequest:
        inputs = cast(tuple[object, ...] | list[object], data["candidate_inputs"])
        value = cls.create(
            basis=CurrentCognitiveBasis.from_dict(cast(Mapping[str, object], data["basis"])),
            policy_id=str(data["policy_id"]),
            budget=ScarceCognitionBudget.from_dict(cast(Mapping[str, object], data["budget"])),
            maximum_interruption_units=float(cast(float, data["maximum_interruption_units"])),
            candidate_inputs=tuple(
                ReconsiderationCandidateInput.from_dict(cast(Mapping[str, object], item))
                for item in inputs
            ),
            information_use_purpose=str(data["information_use_purpose"]),
            information_policy_ids=_strings(data, "information_policy_ids"),
            requested_at=_datetime(data, "requested_at"),
            trigger_event_id=(
                str(data["trigger_event_id"]) if data.get("trigger_event_id") is not None else None
            ),
            foreground_demand_refs=_strings(data, "foreground_demand_refs"),
        )
        if value.request_id != str(data["request_id"]):
            raise ValueError("reconsideration scan id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"reconsideration-scan-requested:{self.request_id}",
            event_type=SCAN_REQUESTED_EVENT,
            source=source,
            subject=self.request_id,
            timestamp=self.requested_at,
            payload=self.to_dict(),
            causation_id=self.trigger_event_id,
        )


@dataclass(frozen=True, slots=True)
class ReconsiderationCandidate:
    candidate_id: str
    derived_information_id: str
    scan_request_id: str
    historical: HistoricalCognitionRef
    current_basis: CurrentCognitiveBasis
    domain: str
    current_causal_cursor: int
    current_evidence_refs: tuple[str, ...]
    information_access_decision_ids: tuple[str, ...]
    features: ReconsiderationFeatureSnapshot
    costs: ScarceCognitionCostSnapshot
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        scan_request_id: str,
        derived_information_id: str,
        historical: HistoricalCognitionRef,
        current_basis: CurrentCognitiveBasis,
        domain: str,
        current_causal_cursor: int,
        current_evidence_refs: tuple[str, ...],
        information_access_decision_ids: tuple[str, ...],
        features: ReconsiderationFeatureSnapshot,
        costs: ScarceCognitionCostSnapshot,
        created_at: datetime,
    ) -> ReconsiderationCandidate:
        evidence = tuple(sorted(set(current_evidence_refs)))
        decisions = tuple(sorted(set(information_access_decision_ids)))
        candidate_id = cls.identity_for(
            historical=historical,
            current_basis=current_basis,
            domain=domain,
            current_evidence_refs=evidence,
            features=features,
            costs=costs,
        )
        return cls(
            candidate_id,
            derived_information_id,
            scan_request_id,
            historical,
            current_basis,
            domain,
            current_causal_cursor,
            evidence,
            decisions,
            features,
            costs,
            created_at,
        )

    @staticmethod
    def identity_for(
        *,
        historical: HistoricalCognitionRef,
        current_basis: CurrentCognitiveBasis,
        domain: str,
        current_evidence_refs: tuple[str, ...],
        features: ReconsiderationFeatureSnapshot,
        costs: ScarceCognitionCostSnapshot,
    ) -> str:
        identity: JSONObject = {
            "historical": historical.to_dict(),
            "current_basis": current_basis.to_dict(),
            "domain": domain,
            "current_evidence_refs": list(sorted(set(current_evidence_refs))),
            "features": features.to_dict(),
            "costs": costs.to_dict(),
        }
        return _canonical_id("reconsideration-candidate", identity)

    def __post_init__(self) -> None:
        for value, name in (
            (self.candidate_id, "reconsideration candidate id"),
            (self.scan_request_id, "reconsideration scan id"),
            (self.domain, "reconsideration candidate domain"),
        ):
            _require_text(value, name)
        validate_opaque_governance_id(
            self.derived_information_id,
            "candidate derived information id",
        )
        if self.current_causal_cursor <= self.historical.historical_causal_cursor:
            raise ValueError("reconsideration requires a fresh current causal cut")
        _unique(self.current_evidence_refs, "candidate current evidence", required=True)
        _unique(
            self.information_access_decision_ids,
            "candidate information access decisions",
            required=True,
        )
        _require_aware(self.created_at, "candidate created_at")
        if self.candidate_id != self.identity_for(
            historical=self.historical,
            current_basis=self.current_basis,
            domain=self.domain,
            current_evidence_refs=self.current_evidence_refs,
            features=self.features,
            costs=self.costs,
        ):
            raise ValueError("reconsideration candidate id does not match semantic basis")

    def to_dict(self) -> JSONObject:
        return {
            "candidate_id": self.candidate_id,
            "derived_information_id": self.derived_information_id,
            "scan_request_id": self.scan_request_id,
            "historical": self.historical.to_dict(),
            "current_basis": self.current_basis.to_dict(),
            "domain": self.domain,
            "current_causal_cursor": self.current_causal_cursor,
            "current_evidence_refs": list(self.current_evidence_refs),
            "information_access_decision_ids": list(self.information_access_decision_ids),
            "features": self.features.to_dict(),
            "costs": self.costs.to_dict(),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconsiderationCandidate:
        value = cls.create(
            scan_request_id=str(data["scan_request_id"]),
            derived_information_id=str(data["derived_information_id"]),
            historical=HistoricalCognitionRef.from_dict(
                cast(Mapping[str, object], data["historical"])
            ),
            current_basis=CurrentCognitiveBasis.from_dict(
                cast(Mapping[str, object], data["current_basis"])
            ),
            domain=str(data["domain"]),
            current_causal_cursor=int(cast(int, data["current_causal_cursor"])),
            current_evidence_refs=_strings(data, "current_evidence_refs"),
            information_access_decision_ids=_strings(data, "information_access_decision_ids"),
            features=ReconsiderationFeatureSnapshot.from_dict(
                cast(Mapping[str, object], data["features"])
            ),
            costs=ScarceCognitionCostSnapshot.from_dict(cast(Mapping[str, object], data["costs"])),
            created_at=_datetime(data, "created_at"),
        )
        if value.candidate_id != str(data["candidate_id"]):
            raise ValueError("reconsideration candidate id does not match semantic basis")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"reconsideration-candidate-recorded:{self.candidate_id}",
            event_type=CANDIDATE_RECORDED_EVENT,
            source=source,
            subject=self.candidate_id,
            timestamp=self.created_at,
            payload=self.to_dict(),
            causation_id=f"reconsideration-scan-requested:{self.scan_request_id}",
        )


@dataclass(frozen=True, slots=True)
class HardGateOutcome:
    gate: str
    passed: bool
    reason: str

    def __post_init__(self) -> None:
        _require_text(self.gate, "hard gate name")
        _require_text(self.reason, "hard gate reason")

    def to_dict(self) -> JSONObject:
        return {"gate": self.gate, "passed": self.passed, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> HardGateOutcome:
        return cls(str(data["gate"]), bool(data["passed"]), str(data["reason"]))


@dataclass(frozen=True, slots=True)
class ReconsiderationDecision:
    candidate_id: str
    label: AllocationLabel
    expected_benefit: float
    total_cost: float
    net_voc: float
    hard_gates: tuple[HardGateOutcome, ...]
    causal_reason: str
    binding_constraint: str | None

    def __post_init__(self) -> None:
        _require_text(self.candidate_id, "allocation candidate id")
        for value, name in (
            (self.expected_benefit, "expected reconsideration benefit"),
            (self.total_cost, "total reconsideration cost"),
        ):
            _non_negative(value, name)
        if not math.isfinite(self.net_voc):
            raise ValueError("reconsideration NetVOC must be finite")
        if round(self.expected_benefit - self.total_cost, 12) != self.net_voc:
            raise ValueError("reconsideration NetVOC does not match its terms")
        if not self.hard_gates:
            raise ValueError("allocation decision requires hard-gate outcomes")
        _require_text(self.causal_reason, "allocation causal reason")

    def to_dict(self) -> JSONObject:
        return {
            "candidate_id": self.candidate_id,
            "label": self.label.value,
            "expected_benefit": self.expected_benefit,
            "total_cost": self.total_cost,
            "net_voc": self.net_voc,
            "hard_gates": [value.to_dict() for value in self.hard_gates],
            "causal_reason": self.causal_reason,
            "binding_constraint": self.binding_constraint,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconsiderationDecision:
        gates = cast(tuple[object, ...] | list[object], data["hard_gates"])
        return cls(
            candidate_id=str(data["candidate_id"]),
            label=AllocationLabel(str(data["label"])),
            expected_benefit=float(cast(float, data["expected_benefit"])),
            total_cost=float(cast(float, data["total_cost"])),
            net_voc=float(cast(float, data["net_voc"])),
            hard_gates=tuple(
                HardGateOutcome.from_dict(cast(Mapping[str, object], value)) for value in gates
            ),
            causal_reason=str(data["causal_reason"]),
            binding_constraint=(
                str(data["binding_constraint"])
                if data.get("binding_constraint") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ReconsiderationAllocation:
    allocation_id: str
    derived_information_id: str
    scan_request_id: str
    policy_id: str
    policy_version: str
    budget: ScarceCognitionBudget
    decisions: tuple[ReconsiderationDecision, ...]
    consumed_candidates: int
    consumed: ScarceCognitionCostSnapshot
    remaining: ScarceCognitionCostSnapshot
    foreground_demand_refs: tuple[str, ...]
    allocated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        derived_information_id: str,
        scan_request_id: str,
        policy_id: str,
        policy_version: str,
        budget: ScarceCognitionBudget,
        decisions: tuple[ReconsiderationDecision, ...],
        consumed_candidates: int,
        consumed: ScarceCognitionCostSnapshot,
        remaining: ScarceCognitionCostSnapshot,
        foreground_demand_refs: tuple[str, ...],
        allocated_at: datetime,
    ) -> ReconsiderationAllocation:
        foreground = tuple(sorted(set(foreground_demand_refs)))
        identity: JSONObject = {
            "derived_information_id": derived_information_id,
            "scan_request_id": scan_request_id,
            "policy_id": policy_id,
            "policy_version": policy_version,
            "budget": budget.to_dict(),
            "decisions": [value.to_dict() for value in decisions],
            "consumed_candidates": consumed_candidates,
            "consumed": consumed.to_dict(),
            "remaining": remaining.to_dict(),
            "foreground_demand_refs": list(foreground),
            "allocated_at": allocated_at.isoformat(),
        }
        return cls(
            _canonical_id("reconsideration-allocation", identity),
            derived_information_id,
            scan_request_id,
            policy_id,
            policy_version,
            budget,
            decisions,
            consumed_candidates,
            consumed,
            remaining,
            foreground,
            allocated_at,
        )

    def __post_init__(self) -> None:
        _require_text(self.allocation_id, "reconsideration allocation id")
        _require_text(self.scan_request_id, "allocation scan id")
        _require_text(self.policy_id, "allocation policy id")
        _require_text(self.policy_version, "allocation policy version")
        validate_opaque_governance_id(
            self.derived_information_id,
            "allocation derived information id",
        )
        if not self.decisions:
            raise ValueError("reconsideration allocation requires decisions")
        _unique(
            tuple(value.candidate_id for value in self.decisions),
            "allocation candidate ids",
            required=True,
        )
        selected = sum(value.label is AllocationLabel.SELECTED for value in self.decisions)
        if selected != self.consumed_candidates or selected > self.budget.max_candidates:
            raise ValueError("allocation candidate consumption is inconsistent")
        _require_aware(self.allocated_at, "allocated_at")
        _unique(self.foreground_demand_refs, "allocation foreground demand refs")
        identity = self.to_dict()
        identity.pop("allocation_id")
        if self.allocation_id != _canonical_id("reconsideration-allocation", identity):
            raise ValueError("allocation id does not match deterministic decision")

    @property
    def selected_candidate_ids(self) -> tuple[str, ...]:
        return tuple(
            value.candidate_id
            for value in self.decisions
            if value.label is AllocationLabel.SELECTED
        )

    def to_dict(self) -> JSONObject:
        return {
            "allocation_id": self.allocation_id,
            "derived_information_id": self.derived_information_id,
            "scan_request_id": self.scan_request_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "budget": self.budget.to_dict(),
            "decisions": [value.to_dict() for value in self.decisions],
            "consumed_candidates": self.consumed_candidates,
            "consumed": self.consumed.to_dict(),
            "remaining": self.remaining.to_dict(),
            "foreground_demand_refs": list(self.foreground_demand_refs),
            "allocated_at": self.allocated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconsiderationAllocation:
        decisions = cast(tuple[object, ...] | list[object], data["decisions"])
        value = cls.create(
            derived_information_id=str(data["derived_information_id"]),
            scan_request_id=str(data["scan_request_id"]),
            policy_id=str(data["policy_id"]),
            policy_version=str(data["policy_version"]),
            budget=ScarceCognitionBudget.from_dict(cast(Mapping[str, object], data["budget"])),
            decisions=tuple(
                ReconsiderationDecision.from_dict(cast(Mapping[str, object], item))
                for item in decisions
            ),
            consumed_candidates=int(cast(int, data["consumed_candidates"])),
            consumed=ScarceCognitionCostSnapshot.from_dict(
                cast(Mapping[str, object], data["consumed"])
            ),
            remaining=ScarceCognitionCostSnapshot.from_dict(
                cast(Mapping[str, object], data["remaining"])
            ),
            foreground_demand_refs=_strings(data, "foreground_demand_refs"),
            allocated_at=_datetime(data, "allocated_at"),
        )
        if value.allocation_id != str(data["allocation_id"]):
            raise ValueError("allocation id does not match deterministic decision")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"reconsideration-allocation-recorded:{self.allocation_id}",
            event_type=ALLOCATION_RECORDED_EVENT,
            source=source,
            subject=self.scan_request_id,
            timestamp=self.allocated_at,
            payload=self.to_dict(),
            causation_id=f"reconsideration-scan-requested:{self.scan_request_id}",
        )


@dataclass(frozen=True, slots=True)
class CognitiveAllocationTrace:
    trace_id: str
    derived_information_id: str
    allocation_id: str
    candidate_id: str
    candidate_provenance: HistoricalCognitionRef
    current_basis: CurrentCognitiveBasis
    feature_snapshot: ReconsiderationFeatureSnapshot
    cost_snapshot: ScarceCognitionCostSnapshot
    hard_gate_outcomes: tuple[HardGateOutcome, ...]
    policy_id: str
    policy_version: str
    estimator_version: str
    budget: ScarceCognitionBudget
    decision: AllocationLabel
    causal_reason: str
    binding_constraint: str | None
    behavior_policy_probability: float | None
    subsequent_outcome_refs: tuple[str, ...]
    recorded_at: datetime

    @classmethod
    def create(
        cls,
        *,
        derived_information_id: str,
        allocation: ReconsiderationAllocation,
        candidate: ReconsiderationCandidate,
        decision: ReconsiderationDecision,
    ) -> CognitiveAllocationTrace:
        payload: JSONObject = {
            "derived_information_id": derived_information_id,
            "allocation_id": allocation.allocation_id,
            "candidate_id": candidate.candidate_id,
            "candidate_provenance": candidate.historical.to_dict(),
            "current_basis": candidate.current_basis.to_dict(),
            "feature_snapshot": candidate.features.to_dict(),
            "cost_snapshot": candidate.costs.to_dict(),
            "hard_gate_outcomes": [value.to_dict() for value in decision.hard_gates],
            "policy_id": allocation.policy_id,
            "policy_version": allocation.policy_version,
            "estimator_version": DETERMINISTIC_ESTIMATOR_VERSION,
            "budget": allocation.budget.to_dict(),
            "decision": decision.label.value,
            "causal_reason": decision.causal_reason,
            "binding_constraint": decision.binding_constraint,
            "behavior_policy_probability": None,
            "subsequent_outcome_refs": [],
            "recorded_at": allocation.allocated_at.isoformat(),
        }
        return cls(
            _canonical_id("cognitive-allocation-trace", payload),
            derived_information_id,
            allocation.allocation_id,
            candidate.candidate_id,
            candidate.historical,
            candidate.current_basis,
            candidate.features,
            candidate.costs,
            decision.hard_gates,
            allocation.policy_id,
            allocation.policy_version,
            DETERMINISTIC_ESTIMATOR_VERSION,
            allocation.budget,
            decision.label,
            decision.causal_reason,
            decision.binding_constraint,
            None,
            (),
            allocation.allocated_at,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.trace_id, "allocation trace id"),
            (self.allocation_id, "trace allocation id"),
            (self.candidate_id, "trace candidate id"),
            (self.policy_id, "trace policy id"),
            (self.policy_version, "trace policy version"),
            (self.estimator_version, "trace estimator version"),
            (self.causal_reason, "trace causal reason"),
        ):
            _require_text(value, name)
        validate_opaque_governance_id(
            self.derived_information_id,
            "trace derived information id",
        )
        if self.behavior_policy_probability is not None:
            _bounded(self.behavior_policy_probability, "behavior policy probability")
        _unique(self.subsequent_outcome_refs, "subsequent outcome refs")
        _require_aware(self.recorded_at, "trace recorded_at")

    def to_dict(self) -> JSONObject:
        return {
            "trace_id": self.trace_id,
            "derived_information_id": self.derived_information_id,
            "allocation_id": self.allocation_id,
            "candidate_id": self.candidate_id,
            "candidate_provenance": self.candidate_provenance.to_dict(),
            "current_basis": self.current_basis.to_dict(),
            "feature_snapshot": self.feature_snapshot.to_dict(),
            "cost_snapshot": self.cost_snapshot.to_dict(),
            "hard_gate_outcomes": [value.to_dict() for value in self.hard_gate_outcomes],
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "estimator_version": self.estimator_version,
            "budget": self.budget.to_dict(),
            "decision": self.decision.value,
            "causal_reason": self.causal_reason,
            "binding_constraint": self.binding_constraint,
            "behavior_policy_probability": self.behavior_policy_probability,
            "subsequent_outcome_refs": list(self.subsequent_outcome_refs),
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CognitiveAllocationTrace:
        gates = cast(tuple[object, ...] | list[object], data["hard_gate_outcomes"])
        value = cls(
            trace_id=str(data["trace_id"]),
            derived_information_id=str(data["derived_information_id"]),
            allocation_id=str(data["allocation_id"]),
            candidate_id=str(data["candidate_id"]),
            candidate_provenance=HistoricalCognitionRef.from_dict(
                cast(Mapping[str, object], data["candidate_provenance"])
            ),
            current_basis=CurrentCognitiveBasis.from_dict(
                cast(Mapping[str, object], data["current_basis"])
            ),
            feature_snapshot=ReconsiderationFeatureSnapshot.from_dict(
                cast(Mapping[str, object], data["feature_snapshot"])
            ),
            cost_snapshot=ScarceCognitionCostSnapshot.from_dict(
                cast(Mapping[str, object], data["cost_snapshot"])
            ),
            hard_gate_outcomes=tuple(
                HardGateOutcome.from_dict(cast(Mapping[str, object], item)) for item in gates
            ),
            policy_id=str(data["policy_id"]),
            policy_version=str(data["policy_version"]),
            estimator_version=str(data["estimator_version"]),
            budget=ScarceCognitionBudget.from_dict(cast(Mapping[str, object], data["budget"])),
            decision=AllocationLabel(str(data["decision"])),
            causal_reason=str(data["causal_reason"]),
            binding_constraint=(
                str(data["binding_constraint"])
                if data.get("binding_constraint") is not None
                else None
            ),
            behavior_policy_probability=(
                float(cast(float, data["behavior_policy_probability"]))
                if data.get("behavior_policy_probability") is not None
                else None
            ),
            subsequent_outcome_refs=_strings(data, "subsequent_outcome_refs"),
            recorded_at=_datetime(data, "recorded_at"),
        )
        if value.behavior_policy_probability is not None:
            raise ValueError("deterministic v1 traces cannot record behavior propensities")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"cognitive-allocation-trace-recorded:{self.trace_id}",
            event_type=ALLOCATION_TRACE_RECORDED_EVENT,
            source=source,
            subject=self.candidate_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
            causation_id=f"reconsideration-allocation-recorded:{self.allocation_id}",
        )


@dataclass(frozen=True, slots=True)
class CognitiveAllocationOutcomeLink:
    link_id: str
    trace_id: str
    outcome_ref: str
    outcome_kind: str
    linked_at: datetime

    @classmethod
    def create(
        cls,
        *,
        trace_id: str,
        outcome_ref: str,
        outcome_kind: str,
        linked_at: datetime,
    ) -> CognitiveAllocationOutcomeLink:
        payload: JSONObject = {
            "trace_id": trace_id,
            "outcome_ref": outcome_ref,
            "outcome_kind": outcome_kind,
            "linked_at": linked_at.isoformat(),
        }
        return cls(
            _canonical_id("cognitive-allocation-outcome", payload),
            trace_id,
            outcome_ref,
            outcome_kind,
            linked_at,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.link_id, "allocation outcome link id"),
            (self.trace_id, "allocation outcome trace id"),
            (self.outcome_ref, "allocation outcome ref"),
            (self.outcome_kind, "allocation outcome kind"),
        ):
            _require_text(value, name)
        if not self.outcome_ref.startswith("event:"):
            raise ValueError("allocation outcome must cite a canonical event")
        _require_aware(self.linked_at, "allocation outcome linked_at")
        identity = self.to_dict()
        identity.pop("link_id")
        if self.link_id != _canonical_id("cognitive-allocation-outcome", identity):
            raise ValueError("allocation outcome link id does not match immutable content")

    def to_dict(self) -> JSONObject:
        return {
            "link_id": self.link_id,
            "trace_id": self.trace_id,
            "outcome_ref": self.outcome_ref,
            "outcome_kind": self.outcome_kind,
            "linked_at": self.linked_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CognitiveAllocationOutcomeLink:
        value = cls.create(
            trace_id=str(data["trace_id"]),
            outcome_ref=str(data["outcome_ref"]),
            outcome_kind=str(data["outcome_kind"]),
            linked_at=_datetime(data, "linked_at"),
        )
        if value.link_id != str(data["link_id"]):
            raise ValueError("allocation outcome link id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"cognitive-allocation-outcome-linked:{self.link_id}",
            event_type=ALLOCATION_OUTCOME_LINKED_EVENT,
            source=source,
            subject=self.trace_id,
            timestamp=self.linked_at,
            payload=self.to_dict(),
            causation_id=self.outcome_ref.removeprefix("event:"),
        )


@dataclass(frozen=True, slots=True)
class ReconsiderationShadowProposal:
    proposal_id: str
    candidate_id: str
    allocation_id: str
    allocation_trace_id: str
    historical_inquiry_id: str
    template_kind: str
    authority_ceiling: SurfacingPolicy
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        candidate: ReconsiderationCandidate,
        allocation: ReconsiderationAllocation,
        trace: CognitiveAllocationTrace,
    ) -> ReconsiderationShadowProposal:
        template_kind = "historical_inquiry_reconsideration"
        payload: JSONObject = {
            "candidate_id": candidate.candidate_id,
            "allocation_id": allocation.allocation_id,
            "allocation_trace_id": trace.trace_id,
            "historical_inquiry_id": candidate.historical.inquiry_id,
            "template_kind": template_kind,
            "authority_ceiling": SurfacingPolicy.SHADOW_QUESTION_ONLY.value,
            "created_at": allocation.allocated_at.isoformat(),
        }
        return cls(
            _canonical_id("reconsideration-shadow-proposal", payload),
            candidate.candidate_id,
            allocation.allocation_id,
            trace.trace_id,
            candidate.historical.inquiry_id,
            template_kind,
            SurfacingPolicy.SHADOW_QUESTION_ONLY,
            allocation.allocated_at,
        )

    def __post_init__(self) -> None:
        for value, name in (
            (self.proposal_id, "shadow proposal id"),
            (self.candidate_id, "shadow proposal candidate"),
            (self.allocation_id, "shadow proposal allocation"),
            (self.allocation_trace_id, "shadow proposal trace"),
            (self.historical_inquiry_id, "shadow proposal historical inquiry"),
            (self.template_kind, "shadow proposal template kind"),
        ):
            _require_text(value, name)
        _require_aware(self.created_at, "shadow proposal created_at")

    def to_dict(self) -> JSONObject:
        return {
            "proposal_id": self.proposal_id,
            "candidate_id": self.candidate_id,
            "allocation_id": self.allocation_id,
            "allocation_trace_id": self.allocation_trace_id,
            "historical_inquiry_id": self.historical_inquiry_id,
            "template_kind": self.template_kind,
            "authority_ceiling": self.authority_ceiling.value,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReconsiderationShadowProposal:
        return cls(
            proposal_id=str(data["proposal_id"]),
            candidate_id=str(data["candidate_id"]),
            allocation_id=str(data["allocation_id"]),
            allocation_trace_id=str(data["allocation_trace_id"]),
            historical_inquiry_id=str(data["historical_inquiry_id"]),
            template_kind=str(data["template_kind"]),
            authority_ceiling=SurfacingPolicy(str(data["authority_ceiling"])),
            created_at=_datetime(data, "created_at"),
        )

    def to_event(self, *, source: str) -> Event:
        return _event(
            event_id=f"reconsideration-shadow-proposal-recorded:{self.proposal_id}",
            event_type=SHADOW_PROPOSAL_RECORDED_EVENT,
            source=source,
            subject=self.candidate_id,
            timestamp=self.created_at,
            payload=self.to_dict(),
            causation_id=f"cognitive-allocation-trace-recorded:{self.allocation_trace_id}",
        )
