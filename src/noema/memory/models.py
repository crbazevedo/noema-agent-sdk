"""Immutable epistemic records for persistent cognitive memory."""

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
from ..types import JSONObject, JSONScalar, JSONValue, parse_datetime

ASSERTION_RECORDED_EVENT = "memory.assertion_recorded"
ASSERTION_SUPERSEDED_EVENT = "memory.assertion_superseded"
EVIDENCE_LINKED_EVENT = "memory.evidence_linked"
VALIDITY_CLOSED_EVENT = "memory.validity_closed"
CONTRADICTION_DETECTED_EVENT = "memory.contradiction_detected"
CONTRADICTION_RESOLVED_EVENT = "memory.contradiction_resolved"

MEMORY_EVENT_TYPES = (
    ASSERTION_RECORDED_EVENT,
    ASSERTION_SUPERSEDED_EVENT,
    EVIDENCE_LINKED_EVENT,
    VALIDITY_CLOSED_EVENT,
    CONTRADICTION_DETECTED_EVENT,
    CONTRADICTION_RESOLVED_EVENT,
)


class EpistemicType(StrEnum):
    """How an assertion or evidence item came to be known."""

    OBSERVED = "observed"
    INFERRED = "inferred"
    REPORTED = "reported"
    ASSUMED = "assumed"
    SIMULATED = "simulated"


class AssertionStatus(StrEnum):
    """The role assigned when an immutable assertion is recorded."""

    ACTIVE = "active"
    HYPOTHESIS = "hypothesis"


class EvidenceRelation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    REFINES = "refines"
    SUPERSEDES = "supersedes"
    DERIVED_FROM = "derived_from"


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _canonical_id(prefix: str, payload: Mapping[str, JSONValue]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:32]}"


def _datetime(data: Mapping[str, object], key: str) -> datetime:
    value = parse_datetime(cast(str | datetime | None, data.get(key)))
    if value is None:
        raise ValueError(f"{key} is required")
    return value


@dataclass(frozen=True, slots=True)
class SemanticAssertion:
    """A versioned proposition with explicit provenance and bitemporal bounds.

    ``valid_from``/``valid_to`` describe the world. ``recorded_at`` describes
    when the agent learned the proposition. Changes produce another assertion;
    they never mutate this record.
    """

    assertion_id: str
    subject: str
    predicate: str
    value: JSONScalar
    epistemic_type: EpistemicType
    confidence: float
    valid_from: datetime
    valid_to: datetime | None
    recorded_at: datetime
    fresh_until: datetime | None
    evidence_refs: tuple[str, ...]
    derivation_refs: tuple[str, ...] = ()
    supersedes: str | None = None
    status: AssertionStatus = AssertionStatus.ACTIVE
    mutable_world: bool = False

    def __post_init__(self) -> None:
        if not self.assertion_id.strip():
            raise ValueError("assertion id must be non-empty")
        if not self.subject.strip() or not self.predicate.strip():
            raise ValueError("assertion subject and predicate must be non-empty")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("assertion value must be finite")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("assertion confidence must be between zero and one")
        _require_aware(self.valid_from, "valid_from")
        _require_aware(self.recorded_at, "recorded_at")
        if self.valid_to is not None:
            _require_aware(self.valid_to, "valid_to")
            if self.valid_to <= self.valid_from:
                raise ValueError("valid_to must be later than valid_from")
        if self.fresh_until is not None:
            _require_aware(self.fresh_until, "fresh_until")
            if self.fresh_until <= self.recorded_at:
                raise ValueError("fresh_until must be later than recorded_at")
        if self.mutable_world and self.fresh_until is None and self.valid_to is None:
            raise ValueError(
                "mutable-world assertions require fresh_until or a closed validity interval"
            )
        if any(not ref.strip() for ref in (*self.evidence_refs, *self.derivation_refs)):
            raise ValueError("assertion evidence and derivation refs must be non-empty")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("assertion evidence refs must be unique")
        if len(set(self.derivation_refs)) != len(self.derivation_refs):
            raise ValueError("assertion derivation refs must be unique")
        if self.epistemic_type is EpistemicType.ASSUMED:
            if self.derivation_refs:
                raise ValueError("assumptions cannot claim derivation evidence")
        elif not self.evidence_refs and not self.derivation_refs:
            raise ValueError("non-assumed assertions require evidence or derivation")
        if self.epistemic_type is EpistemicType.OBSERVED and any(
            ref.startswith("simulation:") for ref in self.evidence_refs
        ):
            raise ValueError("simulated evidence cannot be recorded as an observation")
        if self.epistemic_type is EpistemicType.INFERRED and not self.derivation_refs:
            raise ValueError("inferred assertions require explicit derivation refs")
        if self.supersedes is not None:
            if not self.supersedes.strip():
                raise ValueError("supersedes must be non-empty when supplied")
            if self.supersedes == self.assertion_id:
                raise ValueError("an assertion cannot supersede itself")

    @classmethod
    def create(
        cls,
        *,
        subject: str,
        predicate: str,
        value: JSONScalar,
        epistemic_type: EpistemicType,
        confidence: float,
        valid_from: datetime,
        recorded_at: datetime,
        evidence_refs: tuple[str, ...],
        valid_to: datetime | None = None,
        fresh_until: datetime | None = None,
        derivation_refs: tuple[str, ...] = (),
        supersedes: str | None = None,
        status: AssertionStatus = AssertionStatus.ACTIVE,
        mutable_world: bool = False,
    ) -> SemanticAssertion:
        payload = cls._identity_payload(
            subject=subject,
            predicate=predicate,
            value=value,
            epistemic_type=epistemic_type,
            confidence=confidence,
            valid_from=valid_from,
            valid_to=valid_to,
            recorded_at=recorded_at,
            fresh_until=fresh_until,
            evidence_refs=evidence_refs,
            derivation_refs=derivation_refs,
            supersedes=supersedes,
            status=status,
            mutable_world=mutable_world,
        )
        return cls(
            assertion_id=_canonical_id("assertion", payload),
            subject=subject,
            predicate=predicate,
            value=value,
            epistemic_type=epistemic_type,
            confidence=confidence,
            valid_from=valid_from,
            valid_to=valid_to,
            recorded_at=recorded_at,
            fresh_until=fresh_until,
            evidence_refs=evidence_refs,
            derivation_refs=derivation_refs,
            supersedes=supersedes,
            status=status,
            mutable_world=mutable_world,
        )

    @staticmethod
    def _identity_payload(
        *,
        subject: str,
        predicate: str,
        value: JSONScalar,
        epistemic_type: EpistemicType,
        confidence: float,
        valid_from: datetime,
        valid_to: datetime | None,
        recorded_at: datetime,
        fresh_until: datetime | None,
        evidence_refs: tuple[str, ...],
        derivation_refs: tuple[str, ...],
        supersedes: str | None,
        status: AssertionStatus,
        mutable_world: bool,
    ) -> JSONObject:
        return {
            "subject": subject,
            "predicate": predicate,
            "value": value,
            "epistemic_type": epistemic_type.value,
            "confidence": confidence,
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat() if valid_to is not None else None,
            "recorded_at": recorded_at.isoformat(),
            "fresh_until": fresh_until.isoformat() if fresh_until is not None else None,
            "evidence_refs": list(evidence_refs),
            "derivation_refs": list(derivation_refs),
            "supersedes": supersedes,
            "status": status.value,
            "mutable_world": mutable_world,
        }

    def to_dict(self) -> JSONObject:
        payload = self._identity_payload(
            subject=self.subject,
            predicate=self.predicate,
            value=self.value,
            epistemic_type=self.epistemic_type,
            confidence=self.confidence,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            recorded_at=self.recorded_at,
            fresh_until=self.fresh_until,
            evidence_refs=self.evidence_refs,
            derivation_refs=self.derivation_refs,
            supersedes=self.supersedes,
            status=self.status,
            mutable_world=self.mutable_world,
        )
        return {"assertion_id": self.assertion_id, **payload}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> SemanticAssertion:
        evidence = cast(list[object] | tuple[object, ...], data.get("evidence_refs", ()))
        derivations = cast(list[object] | tuple[object, ...], data.get("derivation_refs", ()))
        assertion = cls(
            assertion_id=str(data["assertion_id"]),
            subject=str(data["subject"]),
            predicate=str(data["predicate"]),
            value=cast(JSONScalar, data.get("value")),
            epistemic_type=EpistemicType(str(data["epistemic_type"])),
            confidence=float(cast(float, data["confidence"])),
            valid_from=_datetime(data, "valid_from"),
            valid_to=parse_datetime(cast(str | datetime | None, data.get("valid_to"))),
            recorded_at=_datetime(data, "recorded_at"),
            fresh_until=parse_datetime(cast(str | datetime | None, data.get("fresh_until"))),
            evidence_refs=tuple(str(value) for value in evidence),
            derivation_refs=tuple(str(value) for value in derivations),
            supersedes=(str(data["supersedes"]) if data.get("supersedes") else None),
            status=AssertionStatus(str(data.get("status", AssertionStatus.ACTIVE.value))),
            mutable_world=bool(data.get("mutable_world", False)),
        )
        expected = _canonical_id(
            "assertion",
            {key: value for key, value in assertion.to_dict().items() if key != "assertion_id"},
        )
        if assertion.assertion_id != expected:
            raise ValueError("assertion id does not match its immutable content")
        return assertion

    def to_event(self, *, source: str) -> Event:
        return Event(
            id=f"memory-assertion:{self.assertion_id}",
            type=ASSERTION_RECORDED_EVENT,
            source=source,
            subject=self.subject,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> SemanticAssertion:
        if event.type != ASSERTION_RECORDED_EVENT:
            raise ValueError(f"not an assertion event: {event.type}")
        assertion = cls.from_dict(event.payload)
        if event.subject != assertion.subject:
            raise ValueError("assertion event subject does not match its assertion")
        if event.timestamp != assertion.recorded_at:
            raise ValueError("assertion event timestamp does not match recorded_at")
        return assertion


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    """A typed edge between evidence and an assertion."""

    link_id: str
    evidence_ref: str
    assertion_ref: str
    relation: EvidenceRelation
    strength: float
    evidence_type: EpistemicType
    recorded_at: datetime

    def __post_init__(self) -> None:
        if not self.link_id.strip() or not self.evidence_ref.strip():
            raise ValueError("evidence link id and evidence ref must be non-empty")
        if not self.assertion_ref.strip():
            raise ValueError("evidence link assertion ref must be non-empty")
        if not math.isfinite(self.strength) or not 0.0 <= self.strength <= 1.0:
            raise ValueError("evidence strength must be between zero and one")
        _require_aware(self.recorded_at, "recorded_at")

    @classmethod
    def create(
        cls,
        *,
        evidence_ref: str,
        assertion_ref: str,
        relation: EvidenceRelation,
        strength: float,
        evidence_type: EpistemicType,
        recorded_at: datetime,
    ) -> EvidenceLink:
        payload: JSONObject = {
            "evidence_ref": evidence_ref,
            "assertion_ref": assertion_ref,
            "relation": relation.value,
            "strength": strength,
            "evidence_type": evidence_type.value,
            "recorded_at": recorded_at.isoformat(),
        }
        return cls(
            link_id=_canonical_id("evidence-link", payload),
            evidence_ref=evidence_ref,
            assertion_ref=assertion_ref,
            relation=relation,
            strength=strength,
            evidence_type=evidence_type,
            recorded_at=recorded_at,
        )

    def to_dict(self) -> JSONObject:
        return {
            "link_id": self.link_id,
            "evidence_ref": self.evidence_ref,
            "assertion_ref": self.assertion_ref,
            "relation": self.relation.value,
            "strength": self.strength,
            "evidence_type": self.evidence_type.value,
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> EvidenceLink:
        link = cls(
            link_id=str(data["link_id"]),
            evidence_ref=str(data["evidence_ref"]),
            assertion_ref=str(data["assertion_ref"]),
            relation=EvidenceRelation(str(data["relation"])),
            strength=float(cast(float, data["strength"])),
            evidence_type=EpistemicType(str(data["evidence_type"])),
            recorded_at=_datetime(data, "recorded_at"),
        )
        expected = EvidenceLink.create(
            evidence_ref=link.evidence_ref,
            assertion_ref=link.assertion_ref,
            relation=link.relation,
            strength=link.strength,
            evidence_type=link.evidence_type,
            recorded_at=link.recorded_at,
        ).link_id
        if link.link_id != expected:
            raise ValueError("evidence link id does not match its immutable content")
        return link

    def to_event(self, *, source: str) -> Event:
        return Event(
            id=f"memory-evidence:{self.link_id}",
            type=EVIDENCE_LINKED_EVENT,
            source=source,
            subject=self.assertion_ref,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> EvidenceLink:
        if event.type != EVIDENCE_LINKED_EVENT:
            raise ValueError(f"not an evidence-link event: {event.type}")
        link = cls.from_dict(event.payload)
        if event.subject != link.assertion_ref:
            raise ValueError("evidence-link event subject does not match its assertion")
        if event.timestamp != link.recorded_at:
            raise ValueError("evidence-link timestamp does not match recorded_at")
        return link


@dataclass(frozen=True, slots=True)
class AssertionSupersession:
    transition_id: str
    prior_assertion_ref: str
    new_assertion_ref: str
    effective_at: datetime
    recorded_at: datetime

    @classmethod
    def create(
        cls,
        *,
        prior_assertion_ref: str,
        new_assertion_ref: str,
        effective_at: datetime,
        recorded_at: datetime,
    ) -> AssertionSupersession:
        _require_aware(effective_at, "effective_at")
        _require_aware(recorded_at, "recorded_at")
        if not prior_assertion_ref.strip() or not new_assertion_ref.strip():
            raise ValueError("supersession assertion refs must be non-empty")
        if prior_assertion_ref == new_assertion_ref:
            raise ValueError("an assertion cannot supersede itself")
        payload: JSONObject = {
            "prior_assertion_ref": prior_assertion_ref,
            "new_assertion_ref": new_assertion_ref,
            "effective_at": effective_at.isoformat(),
            "recorded_at": recorded_at.isoformat(),
        }
        return cls(
            transition_id=_canonical_id("supersession", payload),
            prior_assertion_ref=prior_assertion_ref,
            new_assertion_ref=new_assertion_ref,
            effective_at=effective_at,
            recorded_at=recorded_at,
        )

    def to_dict(self) -> JSONObject:
        return {
            "transition_id": self.transition_id,
            "prior_assertion_ref": self.prior_assertion_ref,
            "new_assertion_ref": self.new_assertion_ref,
            "effective_at": self.effective_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
        }

    def to_event(self, *, source: str, causation_id: str | None = None) -> Event:
        return Event(
            id=f"memory-supersession:{self.transition_id}",
            type=ASSERTION_SUPERSEDED_EVENT,
            source=source,
            subject=self.prior_assertion_ref,
            timestamp=self.recorded_at,
            causation_id=causation_id,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> AssertionSupersession:
        if event.type != ASSERTION_SUPERSEDED_EVENT:
            raise ValueError(f"not an assertion-superseded event: {event.type}")
        transition = cls.create(
            prior_assertion_ref=str(event.payload["prior_assertion_ref"]),
            new_assertion_ref=str(event.payload["new_assertion_ref"]),
            effective_at=_datetime(event.payload, "effective_at"),
            recorded_at=_datetime(event.payload, "recorded_at"),
        )
        if str(event.payload["transition_id"]) != transition.transition_id:
            raise ValueError("supersession id does not match its immutable content")
        if event.subject != transition.prior_assertion_ref:
            raise ValueError("supersession event subject does not match prior assertion")
        if event.timestamp != transition.recorded_at:
            raise ValueError("supersession timestamp does not match recorded_at")
        return transition


@dataclass(frozen=True, slots=True)
class ValidityClosure:
    closure_id: str
    assertion_ref: str
    valid_to: datetime
    recorded_at: datetime

    @classmethod
    def create(
        cls,
        *,
        assertion_ref: str,
        valid_to: datetime,
        recorded_at: datetime,
    ) -> ValidityClosure:
        if not assertion_ref.strip():
            raise ValueError("validity closure assertion ref must be non-empty")
        _require_aware(valid_to, "valid_to")
        _require_aware(recorded_at, "recorded_at")
        payload: JSONObject = {
            "assertion_ref": assertion_ref,
            "valid_to": valid_to.isoformat(),
            "recorded_at": recorded_at.isoformat(),
        }
        return cls(
            closure_id=_canonical_id("validity-closure", payload),
            assertion_ref=assertion_ref,
            valid_to=valid_to,
            recorded_at=recorded_at,
        )

    def to_dict(self) -> JSONObject:
        return {
            "closure_id": self.closure_id,
            "assertion_ref": self.assertion_ref,
            "valid_to": self.valid_to.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
        }

    def to_event(self, *, source: str) -> Event:
        return Event(
            id=f"memory-validity:{self.closure_id}",
            type=VALIDITY_CLOSED_EVENT,
            source=source,
            subject=self.assertion_ref,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> ValidityClosure:
        if event.type != VALIDITY_CLOSED_EVENT:
            raise ValueError(f"not a validity-closed event: {event.type}")
        closure = cls.create(
            assertion_ref=str(event.payload["assertion_ref"]),
            valid_to=_datetime(event.payload, "valid_to"),
            recorded_at=_datetime(event.payload, "recorded_at"),
        )
        if str(event.payload["closure_id"]) != closure.closure_id:
            raise ValueError("validity closure id does not match its immutable content")
        if event.subject != closure.assertion_ref:
            raise ValueError("validity-closure subject does not match its assertion")
        if event.timestamp != closure.recorded_at:
            raise ValueError("validity-closure timestamp does not match recorded_at")
        return closure


@dataclass(frozen=True, slots=True)
class MemoryContradiction:
    contradiction_id: str
    assertion_refs: tuple[str, str]
    subject: str
    predicate: str
    detected_at: datetime
    resolved_at: datetime | None = None
    resolution_reason: str | None = None

    @classmethod
    def detect(
        cls,
        *,
        assertion_refs: tuple[str, str],
        subject: str,
        predicate: str,
        detected_at: datetime,
    ) -> MemoryContradiction:
        refs = cast(tuple[str, str], tuple(sorted(assertion_refs)))
        if refs[0] == refs[1] or any(not ref.strip() for ref in refs):
            raise ValueError("a contradiction requires two distinct assertion refs")
        if not subject.strip() or not predicate.strip():
            raise ValueError("contradiction subject and predicate must be non-empty")
        _require_aware(detected_at, "detected_at")
        identity: JSONObject = {"assertion_refs": list(refs)}
        return cls(
            contradiction_id=_canonical_id("contradiction", identity),
            assertion_refs=refs,
            subject=subject,
            predicate=predicate,
            detected_at=detected_at,
        )

    def resolve(self, *, resolved_at: datetime, reason: str) -> MemoryContradiction:
        _require_aware(resolved_at, "resolved_at")
        if resolved_at < self.detected_at:
            raise ValueError("a contradiction cannot resolve before detection")
        if not reason.strip():
            raise ValueError("contradiction resolution reason must be non-empty")
        return MemoryContradiction(
            contradiction_id=self.contradiction_id,
            assertion_refs=self.assertion_refs,
            subject=self.subject,
            predicate=self.predicate,
            detected_at=self.detected_at,
            resolved_at=resolved_at,
            resolution_reason=reason,
        )

    def detection_event(self, *, source: str, causation_id: str | None = None) -> Event:
        payload: JSONObject = {
            "contradiction_id": self.contradiction_id,
            "assertion_refs": list(self.assertion_refs),
            "subject": self.subject,
            "predicate": self.predicate,
            "detected_at": self.detected_at.isoformat(),
        }
        return Event(
            id=f"memory-contradiction-detected:{self.contradiction_id}",
            type=CONTRADICTION_DETECTED_EVENT,
            source=source,
            subject=self.subject,
            timestamp=self.detected_at,
            causation_id=causation_id,
            payload=payload,
        )

    def resolution_event(self, *, source: str, causation_id: str | None = None) -> Event:
        if self.resolved_at is None or self.resolution_reason is None:
            raise ValueError("cannot create a resolution event for an unresolved contradiction")
        payload: JSONObject = {
            "contradiction_id": self.contradiction_id,
            "resolved_at": self.resolved_at.isoformat(),
            "reason": self.resolution_reason,
        }
        return Event(
            id=f"memory-contradiction-resolved:{_canonical_id('resolution', payload)}",
            type=CONTRADICTION_RESOLVED_EVENT,
            source=source,
            subject=self.contradiction_id,
            timestamp=self.resolved_at,
            causation_id=causation_id,
            payload=payload,
        )
