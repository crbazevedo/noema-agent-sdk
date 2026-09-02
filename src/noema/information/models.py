"""Immutable information-governance contracts and safe canonical envelopes."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, cast

from ..events import Event
from ..types import JSONObject, JSONValue, parse_datetime

POLICY_RECORDED_EVENT = "information.policy_recorded"
LINEAGE_RECORDED_EVENT = "information.lineage_recorded"
POLICY_BOUND_EVENT = "information.policy_bound"
INFORMATION_QUARANTINED_EVENT = "information.quarantined"
INFORMATION_ACCESS_DECIDED_EVENT = "information.access_decided"
DISCLOSURE_DECIDED_EVENT = "information.disclosure_decided"
DECLASSIFICATION_DECIDED_EVENT = "information.declassification_decided"
DECLASSIFIED_VIEW_RECORDED_EVENT = "information.declassified_view_recorded"
SECURITY_AUDIT_RECEIPT_EVENT = "information.security_audit_receipt"

INFORMATION_GOVERNANCE_EVENT_TYPES = (
    POLICY_RECORDED_EVENT,
    LINEAGE_RECORDED_EVENT,
    POLICY_BOUND_EVENT,
    INFORMATION_QUARANTINED_EVENT,
    INFORMATION_ACCESS_DECIDED_EVENT,
    DISCLOSURE_DECIDED_EVENT,
    DECLASSIFICATION_DECIDED_EVENT,
    DECLASSIFIED_VIEW_RECORDED_EVENT,
    SECURITY_AUDIT_RECEIPT_EVENT,
)

_OPAQUE_ID = re.compile(r"^[a-z][a-z0-9_]{1,23}_[0-9a-f]{32}$")


def _require_text(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _unique(values: tuple[str, ...], name: str, *, required: bool = False) -> None:
    if required and not values:
        raise ValueError(f"{name} must be non-empty")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} must contain non-empty values")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _ordered(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _canonical_id(prefix: str, payload: Mapping[str, JSONValue]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:32]}"


class OpaqueInformationIdDeriver(Protocol):
    """Boundary port for dictionary-resistant governed-information identifiers."""

    def derive(self, *, namespace: str, stable_key: str) -> str: ...


@dataclass(frozen=True, slots=True)
class HmacOpaqueInformationIdDeriver:
    """Derive opaque identifiers with a caller-owned secret key."""

    derivation_key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.derivation_key) < 32:
            raise ValueError("opaque identifier derivation key must contain at least 32 bytes")

    def derive(self, *, namespace: str, stable_key: str) -> str:
        _require_text(namespace, "information namespace")
        _require_text(stable_key, "information stable key")
        message = json.dumps(
            {"namespace": namespace, "stable_key": stable_key},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        digest = hmac.new(self.derivation_key, message, hashlib.sha256).hexdigest()
        return f"info_{digest[:32]}"


def opaque_information_id(
    *,
    namespace: str,
    stable_key: str,
    derivation_key: bytes,
) -> str:
    """Create a dictionary-resistant opaque id with an explicit secret key."""

    return HmacOpaqueInformationIdDeriver(derivation_key).derive(
        namespace=namespace,
        stable_key=stable_key,
    )


def _require_opaque(value: str, name: str) -> None:
    if _OPAQUE_ID.fullmatch(value) is None:
        raise ValueError(f"{name} must be an opaque governance identifier")


def validate_opaque_governance_id(value: str, name: str = "governance id") -> None:
    """Validate a reference crossing into another core contract."""

    _require_opaque(value, name)


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


class Classification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class InformationOperation(StrEnum):
    READ = "read"
    RETRIEVE = "retrieve"
    REASON = "reason"
    MODEL_CONTEXT = "model_context"
    WORK_ASSIGN = "work_assign"
    DISCLOSE = "disclose"
    DELETE = "delete"
    DECLASSIFY = "declassify"
    CLASSIFY = "classify"
    SHARED_INDEX = "shared_index"
    TELEMETRY = "telemetry"
    EXTERNAL_CONNECTOR = "external_connector"
    CROSS_AGENT_SHARE = "cross_agent_share"
    UNKNOWN = "unknown"


class DecisionDisposition(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class DisclosureForm(StrEnum):
    FULL = "full"
    REDACTED = "redacted"
    ABSTRACTED = "abstracted"


class LineageTransformation(StrEnum):
    SOURCE = "source"
    DERIVATION = "derivation"
    REDACTION = "redaction"
    ABSTRACTION = "abstraction"


class PolicyConflictKind(StrEnum):
    UNKNOWN_CLASSIFICATION = "unknown_classification"
    EMPTY_PURPOSES = "empty_purposes"
    EMPTY_RECIPIENTS = "empty_recipients"
    EMPTY_TRUST_DOMAINS = "empty_trust_domains"
    EMPTY_LOCALITIES = "empty_localities"
    EMPTY_PROVIDERS = "empty_providers"
    EMPTY_DISCLOSURE_FORMS = "empty_disclosure_forms"
    RETENTION_WINDOW = "retention_window"
    LEGAL_HOLD_DELETION = "legal_hold_deletion"
    NO_DECLASSIFICATION_AUTHORITY = "no_declassification_authority"
    INCOMPLETE_LINEAGE = "incomplete_lineage"
    MISSING_POLICY_VERSION = "missing_policy_version"
    QUARANTINED = "quarantined"


class DecisionReason(StrEnum):
    PERMITTED = "permitted"
    POLICY_CONFLICT = "policy_conflict"
    PURPOSE_NOT_PERMITTED = "purpose_not_permitted"
    RECIPIENT_NOT_PERMITTED = "recipient_not_permitted"
    TRUST_DOMAIN_NOT_PERMITTED = "trust_domain_not_permitted"
    PRINCIPAL_TRUST_DOMAIN_MISMATCH = "principal_trust_domain_mismatch"
    LOCALITY_NOT_PERMITTED = "locality_not_permitted"
    PROVIDER_NOT_PERMITTED = "provider_not_permitted"
    SHARING_NOT_PERMITTED = "sharing_not_permitted"
    DISCLOSURE_FORM_NOT_PERMITTED = "disclosure_form_not_permitted"
    RETENTION_REQUIRES_PRESERVATION = "retention_requires_preservation"
    DECLASSIFICATION_AUTHORITY_REQUIRED = "declassification_authority_required"
    CONTEXT_POLICY_MISMATCH = "context_policy_mismatch"
    CONTEXT_LINEAGE_MISMATCH = "context_lineage_mismatch"
    QUARANTINED = "quarantined"
    UNKNOWN_OPERATION = "unknown_operation"


@dataclass(frozen=True, slots=True)
class HoldConstraint:
    hold_id: str
    authority_id: str
    active: bool = True

    def __post_init__(self) -> None:
        _require_opaque(self.hold_id, "hold id")
        _require_text(self.authority_id, "hold authority")

    @classmethod
    def create(cls, *, authority_id: str, stable_key: str, active: bool = True) -> HoldConstraint:
        return cls(
            hold_id=_canonical_id(
                "hold",
                {"authority_id": authority_id, "stable_key": stable_key, "active": active},
            ),
            authority_id=authority_id,
            active=active,
        )

    def to_dict(self) -> JSONObject:
        return {
            "hold_id": self.hold_id,
            "authority_id": self.authority_id,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> HoldConstraint:
        return cls(
            hold_id=str(data["hold_id"]),
            authority_id=str(data["authority_id"]),
            active=bool(data.get("active", True)),
        )


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    retain_until: datetime | None = None
    delete_after: datetime | None = None
    deletion_required: bool = False
    holds: tuple[HoldConstraint, ...] = ()

    def __post_init__(self) -> None:
        if self.retain_until is not None:
            _require_aware(self.retain_until, "retention lower bound")
        if self.delete_after is not None:
            _require_aware(self.delete_after, "deletion duty")
        if self.deletion_required and self.delete_after is None:
            raise ValueError("required deletion needs an explicit deletion time")
        ids = tuple(value.hold_id for value in self.holds)
        if len(set(ids)) != len(ids):
            raise ValueError("retention holds must be unique")

    @property
    def active_holds(self) -> tuple[HoldConstraint, ...]:
        return tuple(value for value in self.holds if value.active)

    def to_dict(self) -> JSONObject:
        return {
            "retain_until": self.retain_until.isoformat() if self.retain_until else None,
            "delete_after": self.delete_after.isoformat() if self.delete_after else None,
            "deletion_required": self.deletion_required,
            "holds": [value.to_dict() for value in self.holds],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RetentionPolicy:
        holds = cast(tuple[object, ...] | list[object], data.get("holds", ()))
        return cls(
            retain_until=_optional_datetime(data, "retain_until"),
            delete_after=_optional_datetime(data, "delete_after"),
            deletion_required=bool(data.get("deletion_required", False)),
            holds=tuple(
                HoldConstraint.from_dict(cast(Mapping[str, object], value)) for value in holds
            ),
        )


@dataclass(frozen=True, slots=True)
class InformationPolicy:
    policy_id: str
    version: int
    origin_domains: tuple[str, ...]
    classification: Classification
    allowed_purposes: tuple[str, ...]
    allowed_recipients: tuple[str, ...]
    allowed_trust_domains: tuple[str, ...]
    allowed_localities: tuple[str, ...]
    allowed_providers: tuple[str, ...]
    cross_agent_sharing: bool
    retention: RetentionPolicy
    disclosure_forms: tuple[DisclosureForm, ...]
    declassification_authorities: tuple[str, ...]
    recorded_at: datetime

    @classmethod
    def create(
        cls,
        *,
        version: int,
        origin_domains: tuple[str, ...],
        classification: Classification,
        allowed_purposes: tuple[str, ...],
        allowed_recipients: tuple[str, ...],
        allowed_trust_domains: tuple[str, ...],
        allowed_localities: tuple[str, ...],
        allowed_providers: tuple[str, ...],
        cross_agent_sharing: bool,
        retention: RetentionPolicy,
        disclosure_forms: tuple[DisclosureForm, ...],
        declassification_authorities: tuple[str, ...],
        recorded_at: datetime,
    ) -> InformationPolicy:
        normalized_origin_domains = _ordered(origin_domains)
        normalized_purposes = _ordered(allowed_purposes)
        normalized_recipients = _ordered(allowed_recipients)
        normalized_trust_domains = _ordered(allowed_trust_domains)
        normalized_localities = _ordered(allowed_localities)
        normalized_providers = _ordered(allowed_providers)
        normalized_forms = tuple(sorted(set(disclosure_forms), key=lambda value: value.value))
        normalized_authorities = _ordered(declassification_authorities)
        identity: JSONObject = {
            "version": version,
            "origin_domains": list(normalized_origin_domains),
            "classification": classification.value,
            "allowed_purposes": list(normalized_purposes),
            "allowed_recipients": list(normalized_recipients),
            "allowed_trust_domains": list(normalized_trust_domains),
            "allowed_localities": list(normalized_localities),
            "allowed_providers": list(normalized_providers),
            "cross_agent_sharing": cross_agent_sharing,
            "retention": retention.to_dict(),
            "disclosure_forms": [value.value for value in normalized_forms],
            "declassification_authorities": list(normalized_authorities),
            "recorded_at": recorded_at.isoformat(),
        }
        return cls(
            policy_id=_canonical_id("ipol", identity),
            version=version,
            origin_domains=normalized_origin_domains,
            classification=classification,
            allowed_purposes=normalized_purposes,
            allowed_recipients=normalized_recipients,
            allowed_trust_domains=normalized_trust_domains,
            allowed_localities=normalized_localities,
            allowed_providers=normalized_providers,
            cross_agent_sharing=cross_agent_sharing,
            retention=retention,
            disclosure_forms=normalized_forms,
            declassification_authorities=normalized_authorities,
            recorded_at=recorded_at,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.policy_id, "information policy id")
        if self.version <= 0:
            raise ValueError("information policy version must be positive")
        _unique(self.origin_domains, "policy origin domains", required=True)
        for values, name in (
            (self.allowed_purposes, "policy purposes"),
            (self.allowed_recipients, "policy recipients"),
            (self.allowed_trust_domains, "policy trust domains"),
            (self.allowed_localities, "policy localities"),
            (self.allowed_providers, "policy providers"),
            (self.declassification_authorities, "policy declassification authorities"),
        ):
            _unique(values, name)
        if len(set(self.disclosure_forms)) != len(self.disclosure_forms):
            raise ValueError("policy disclosure forms must be unique")
        _require_aware(self.recorded_at, "policy recorded_at")

    def to_dict(self) -> JSONObject:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "origin_domains": list(self.origin_domains),
            "classification": self.classification.value,
            "allowed_purposes": list(self.allowed_purposes),
            "allowed_recipients": list(self.allowed_recipients),
            "allowed_trust_domains": list(self.allowed_trust_domains),
            "allowed_localities": list(self.allowed_localities),
            "allowed_providers": list(self.allowed_providers),
            "cross_agent_sharing": self.cross_agent_sharing,
            "retention": self.retention.to_dict(),
            "disclosure_forms": [value.value for value in self.disclosure_forms],
            "declassification_authorities": list(self.declassification_authorities),
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> InformationPolicy:
        value = cls(
            policy_id=str(data["policy_id"]),
            version=int(cast(int, data["version"])),
            origin_domains=_strings(data, "origin_domains"),
            classification=Classification(str(data["classification"])),
            allowed_purposes=_strings(data, "allowed_purposes"),
            allowed_recipients=_strings(data, "allowed_recipients"),
            allowed_trust_domains=_strings(data, "allowed_trust_domains"),
            allowed_localities=_strings(data, "allowed_localities"),
            allowed_providers=_strings(data, "allowed_providers"),
            cross_agent_sharing=bool(data["cross_agent_sharing"]),
            retention=RetentionPolicy.from_dict(cast(Mapping[str, object], data["retention"])),
            disclosure_forms=tuple(
                DisclosureForm(str(item))
                for item in cast(tuple[object, ...] | list[object], data["disclosure_forms"])
            ),
            declassification_authorities=_strings(data, "declassification_authorities"),
            recorded_at=_datetime(data, "recorded_at"),
        )
        expected = cls.create(
            version=value.version,
            origin_domains=value.origin_domains,
            classification=value.classification,
            allowed_purposes=value.allowed_purposes,
            allowed_recipients=value.allowed_recipients,
            allowed_trust_domains=value.allowed_trust_domains,
            allowed_localities=value.allowed_localities,
            allowed_providers=value.allowed_providers,
            cross_agent_sharing=value.cross_agent_sharing,
            retention=value.retention,
            disclosure_forms=value.disclosure_forms,
            declassification_authorities=value.declassification_authorities,
            recorded_at=value.recorded_at,
        )
        if value != expected:
            raise ValueError("information policy id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _governance_event(
            event_type=POLICY_RECORDED_EVENT,
            event_id=f"information-policy-recorded:{self.policy_id}",
            source=source,
            subject=self.policy_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> InformationPolicy:
        if event.type != POLICY_RECORDED_EVENT:
            raise ValueError("event is not an information policy record")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"information-policy-recorded:{value.policy_id}",
            subject=value.policy_id,
            timestamp=value.recorded_at,
        )
        return value


@dataclass(frozen=True, slots=True)
class PrincipalSnapshot:
    snapshot_id: str
    principal_id: str
    roles: tuple[str, ...]
    groups: tuple[str, ...]
    trust_domains: tuple[str, ...]
    captured_at: datetime

    @classmethod
    def create(
        cls,
        *,
        principal_id: str,
        roles: tuple[str, ...],
        groups: tuple[str, ...],
        trust_domains: tuple[str, ...],
        captured_at: datetime,
    ) -> PrincipalSnapshot:
        payload: JSONObject = {
            "principal_id": principal_id,
            "roles": list(_ordered(roles)),
            "groups": list(_ordered(groups)),
            "trust_domains": list(_ordered(trust_domains)),
            "captured_at": captured_at.isoformat(),
        }
        return cls(
            snapshot_id=_canonical_id("principal", payload),
            principal_id=principal_id,
            roles=_ordered(roles),
            groups=_ordered(groups),
            trust_domains=_ordered(trust_domains),
            captured_at=captured_at,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.snapshot_id, "principal snapshot id")
        _require_text(self.principal_id, "principal id")
        _unique(self.roles, "principal roles")
        _unique(self.groups, "principal groups")
        _unique(self.trust_domains, "principal trust domains", required=True)
        _require_aware(self.captured_at, "principal snapshot time")

    @property
    def recipient_identities(self) -> frozenset[str]:
        return frozenset((self.principal_id, *self.roles, *self.groups))

    def to_dict(self) -> JSONObject:
        return {
            "snapshot_id": self.snapshot_id,
            "principal_id": self.principal_id,
            "roles": list(self.roles),
            "groups": list(self.groups),
            "trust_domains": list(self.trust_domains),
            "captured_at": self.captured_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PrincipalSnapshot:
        value = cls(
            snapshot_id=str(data["snapshot_id"]),
            principal_id=str(data["principal_id"]),
            roles=_strings(data, "roles"),
            groups=_strings(data, "groups"),
            trust_domains=_strings(data, "trust_domains"),
            captured_at=_datetime(data, "captured_at"),
        )
        expected = cls.create(
            principal_id=value.principal_id,
            roles=value.roles,
            groups=value.groups,
            trust_domains=value.trust_domains,
            captured_at=value.captured_at,
        )
        if value != expected:
            raise ValueError("principal snapshot id does not match immutable content")
        return value


@dataclass(frozen=True, slots=True)
class AccessContext:
    context_id: str
    actor_id: str
    principal: PrincipalSnapshot
    purpose: str
    operation: InformationOperation
    source_trust_domain: str
    destination_trust_domain: str | None
    recipient: str | None
    decision_time: datetime
    policy_ids: tuple[str, ...]
    source_lineage_refs: tuple[str, ...]
    locality: str
    provider_id: str | None = None
    provider_security_posture: tuple[str, ...] = ()
    disclosure_form: DisclosureForm | None = None

    @classmethod
    def create(
        cls,
        *,
        actor_id: str,
        principal: PrincipalSnapshot,
        purpose: str,
        operation: InformationOperation,
        source_trust_domain: str,
        destination_trust_domain: str | None,
        recipient: str | None,
        decision_time: datetime,
        policy_ids: tuple[str, ...],
        source_lineage_refs: tuple[str, ...],
        locality: str,
        provider_id: str | None = None,
        provider_security_posture: tuple[str, ...] = (),
        disclosure_form: DisclosureForm | None = None,
    ) -> AccessContext:
        payload: JSONObject = {
            "actor_id": actor_id,
            "principal": principal.to_dict(),
            "purpose": purpose,
            "operation": operation.value,
            "source_trust_domain": source_trust_domain,
            "destination_trust_domain": destination_trust_domain,
            "recipient": recipient,
            "decision_time": decision_time.isoformat(),
            "policy_ids": list(_ordered(policy_ids)),
            "source_lineage_refs": list(_ordered(source_lineage_refs)),
            "locality": locality,
            "provider_id": provider_id,
            "provider_security_posture": list(_ordered(provider_security_posture)),
            "disclosure_form": disclosure_form.value if disclosure_form else None,
        }
        return cls(
            context_id=_canonical_id("access", payload),
            actor_id=actor_id,
            principal=principal,
            purpose=purpose,
            operation=operation,
            source_trust_domain=source_trust_domain,
            destination_trust_domain=destination_trust_domain,
            recipient=recipient,
            decision_time=decision_time,
            policy_ids=_ordered(policy_ids),
            source_lineage_refs=_ordered(source_lineage_refs),
            locality=locality,
            provider_id=provider_id,
            provider_security_posture=_ordered(provider_security_posture),
            disclosure_form=disclosure_form,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.context_id, "access context id")
        for value, name in (
            (self.actor_id, "access actor"),
            (self.purpose, "access purpose"),
            (self.source_trust_domain, "source trust domain"),
            (self.locality, "processing locality"),
        ):
            _require_text(value, name)
        _require_aware(self.decision_time, "access decision time")
        _unique(self.policy_ids, "access policy ids")
        _unique(self.source_lineage_refs, "access lineage refs")
        _unique(self.provider_security_posture, "provider posture")
        for value in self.policy_ids:
            _require_opaque(value, "access policy id")
        for value in self.source_lineage_refs:
            _require_opaque(value, "access lineage ref")

    def to_dict(self) -> JSONObject:
        return {
            "context_id": self.context_id,
            "actor_id": self.actor_id,
            "principal": self.principal.to_dict(),
            "purpose": self.purpose,
            "operation": self.operation.value,
            "source_trust_domain": self.source_trust_domain,
            "destination_trust_domain": self.destination_trust_domain,
            "recipient": self.recipient,
            "decision_time": self.decision_time.isoformat(),
            "policy_ids": list(self.policy_ids),
            "source_lineage_refs": list(self.source_lineage_refs),
            "locality": self.locality,
            "provider_id": self.provider_id,
            "provider_security_posture": list(self.provider_security_posture),
            "disclosure_form": self.disclosure_form.value if self.disclosure_form else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AccessContext:
        value = cls.create(
            actor_id=str(data["actor_id"]),
            principal=PrincipalSnapshot.from_dict(cast(Mapping[str, object], data["principal"])),
            purpose=str(data["purpose"]),
            operation=InformationOperation(str(data["operation"])),
            source_trust_domain=str(data["source_trust_domain"]),
            destination_trust_domain=(
                str(data["destination_trust_domain"])
                if data.get("destination_trust_domain") is not None
                else None
            ),
            recipient=str(data["recipient"]) if data.get("recipient") is not None else None,
            decision_time=_datetime(data, "decision_time"),
            policy_ids=_strings(data, "policy_ids"),
            source_lineage_refs=_strings(data, "source_lineage_refs"),
            locality=str(data["locality"]),
            provider_id=(str(data["provider_id"]) if data.get("provider_id") else None),
            provider_security_posture=_strings(data, "provider_security_posture"),
            disclosure_form=(
                DisclosureForm(str(data["disclosure_form"]))
                if data.get("disclosure_form") is not None
                else None
            ),
        )
        if value.context_id != str(data["context_id"]):
            raise ValueError("access context id does not match immutable content")
        return value


@dataclass(frozen=True, slots=True)
class GovernedInformationRef:
    information_id: str

    def __post_init__(self) -> None:
        _require_opaque(self.information_id, "governed information id")

    @classmethod
    def create(
        cls,
        *,
        namespace: str,
        stable_key: str,
        deriver: OpaqueInformationIdDeriver,
    ) -> GovernedInformationRef:
        return cls(deriver.derive(namespace=namespace, stable_key=stable_key))

    def to_dict(self) -> JSONObject:
        return {"information_id": self.information_id}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> GovernedInformationRef:
        return cls(str(data["information_id"]))


@dataclass(frozen=True, slots=True)
class InformationLineage:
    lineage_id: str
    information_id: str
    source_information_ids: tuple[str, ...]
    transformation: LineageTransformation
    recorded_at: datetime

    @classmethod
    def create(
        cls,
        *,
        information_id: str,
        source_information_ids: tuple[str, ...],
        transformation: LineageTransformation,
        recorded_at: datetime,
    ) -> InformationLineage:
        payload: JSONObject = {
            "information_id": information_id,
            "source_information_ids": list(_ordered(source_information_ids)),
            "transformation": transformation.value,
            "recorded_at": recorded_at.isoformat(),
        }
        return cls(
            lineage_id=_canonical_id("lineage", payload),
            information_id=information_id,
            source_information_ids=_ordered(source_information_ids),
            transformation=transformation,
            recorded_at=recorded_at,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.lineage_id, "information lineage id")
        _require_opaque(self.information_id, "lineage information id")
        for value in self.source_information_ids:
            _require_opaque(value, "lineage source information id")
        if len(set(self.source_information_ids)) != len(self.source_information_ids):
            raise ValueError("lineage source information ids must be unique")
        if self.transformation is LineageTransformation.SOURCE:
            if self.source_information_ids:
                raise ValueError("source lineage cannot name parent information")
        elif not self.source_information_ids:
            raise ValueError("derived lineage requires source information")
        if self.information_id in self.source_information_ids:
            raise ValueError("information lineage cannot reference itself")
        _require_aware(self.recorded_at, "lineage recorded_at")

    def to_dict(self) -> JSONObject:
        return {
            "lineage_id": self.lineage_id,
            "information_id": self.information_id,
            "source_information_ids": list(self.source_information_ids),
            "transformation": self.transformation.value,
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> InformationLineage:
        value = cls.create(
            information_id=str(data["information_id"]),
            source_information_ids=_strings(data, "source_information_ids"),
            transformation=LineageTransformation(str(data["transformation"])),
            recorded_at=_datetime(data, "recorded_at"),
        )
        if value.lineage_id != str(data["lineage_id"]):
            raise ValueError("lineage id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _governance_event(
            event_type=LINEAGE_RECORDED_EVENT,
            event_id=f"information-lineage-recorded:{self.lineage_id}",
            source=source,
            subject=self.information_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> InformationLineage:
        if event.type != LINEAGE_RECORDED_EVENT:
            raise ValueError("event is not an information lineage record")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"information-lineage-recorded:{value.lineage_id}",
            subject=value.information_id,
            timestamp=value.recorded_at,
        )
        return value


@dataclass(frozen=True, slots=True)
class PolicyBinding:
    binding_id: str
    information_id: str
    lineage_id: str
    policy_ids: tuple[str, ...]
    bound_at: datetime

    @classmethod
    def create(
        cls,
        *,
        information_id: str,
        lineage_id: str,
        policy_ids: tuple[str, ...],
        bound_at: datetime,
    ) -> PolicyBinding:
        payload: JSONObject = {
            "information_id": information_id,
            "lineage_id": lineage_id,
            "policy_ids": list(_ordered(policy_ids)),
            "bound_at": bound_at.isoformat(),
        }
        return cls(
            binding_id=_canonical_id("binding", payload),
            information_id=information_id,
            lineage_id=lineage_id,
            policy_ids=_ordered(policy_ids),
            bound_at=bound_at,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.binding_id, "policy binding id")
        _require_opaque(self.information_id, "bound information id")
        _require_opaque(self.lineage_id, "binding lineage id")
        for value in self.policy_ids:
            _require_opaque(value, "bound policy id")
        _require_aware(self.bound_at, "policy binding time")

    def to_dict(self) -> JSONObject:
        return {
            "binding_id": self.binding_id,
            "information_id": self.information_id,
            "lineage_id": self.lineage_id,
            "policy_ids": list(self.policy_ids),
            "bound_at": self.bound_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PolicyBinding:
        value = cls.create(
            information_id=str(data["information_id"]),
            lineage_id=str(data["lineage_id"]),
            policy_ids=_strings(data, "policy_ids"),
            bound_at=_datetime(data, "bound_at"),
        )
        if value.binding_id != str(data["binding_id"]):
            raise ValueError("policy binding id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _governance_event(
            event_type=POLICY_BOUND_EVENT,
            event_id=f"information-policy-bound:{self.binding_id}",
            source=source,
            subject=self.information_id,
            timestamp=self.bound_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> PolicyBinding:
        if event.type != POLICY_BOUND_EVENT:
            raise ValueError("event is not an information policy binding")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"information-policy-bound:{value.binding_id}",
            subject=value.information_id,
            timestamp=value.bound_at,
        )
        return value


@dataclass(frozen=True, slots=True)
class QuarantinePolicy:
    allowed_localities: tuple[str, ...] = ("local",)
    allowed_trust_domains: tuple[str, ...] = ("local",)
    human_resolution_required: bool = False

    def __post_init__(self) -> None:
        _unique(self.allowed_localities, "quarantine localities", required=True)
        _unique(self.allowed_trust_domains, "quarantine trust domains", required=True)

    def to_dict(self) -> JSONObject:
        return {
            "allowed_localities": list(self.allowed_localities),
            "allowed_trust_domains": list(self.allowed_trust_domains),
            "human_resolution_required": self.human_resolution_required,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> QuarantinePolicy:
        return cls(
            allowed_localities=_strings(data, "allowed_localities"),
            allowed_trust_domains=_strings(data, "allowed_trust_domains"),
            human_resolution_required=bool(data.get("human_resolution_required", False)),
        )


@dataclass(frozen=True, slots=True)
class QuarantinedInformationRef:
    quarantine_id: str
    information_id: str
    policy: QuarantinePolicy
    quarantined_at: datetime

    @classmethod
    def create(
        cls,
        *,
        information_id: str,
        policy: QuarantinePolicy,
        quarantined_at: datetime,
    ) -> QuarantinedInformationRef:
        payload: JSONObject = {
            "information_id": information_id,
            "policy": policy.to_dict(),
            "quarantined_at": quarantined_at.isoformat(),
        }
        return cls(
            quarantine_id=_canonical_id("quarantine", payload),
            information_id=information_id,
            policy=policy,
            quarantined_at=quarantined_at,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.quarantine_id, "quarantine id")
        _require_opaque(self.information_id, "quarantined information id")
        _require_aware(self.quarantined_at, "quarantine time")

    def to_dict(self) -> JSONObject:
        return {
            "quarantine_id": self.quarantine_id,
            "information_id": self.information_id,
            "policy": self.policy.to_dict(),
            "quarantined_at": self.quarantined_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> QuarantinedInformationRef:
        value = cls.create(
            information_id=str(data["information_id"]),
            policy=QuarantinePolicy.from_dict(cast(Mapping[str, object], data["policy"])),
            quarantined_at=_datetime(data, "quarantined_at"),
        )
        if value.quarantine_id != str(data["quarantine_id"]):
            raise ValueError("quarantine id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _governance_event(
            event_type=INFORMATION_QUARANTINED_EVENT,
            event_id=f"information-quarantined:{self.quarantine_id}",
            source=source,
            subject=self.information_id,
            timestamp=self.quarantined_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> QuarantinedInformationRef:
        if event.type != INFORMATION_QUARANTINED_EVENT:
            raise ValueError("event is not an information quarantine record")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"information-quarantined:{value.quarantine_id}",
            subject=value.information_id,
            timestamp=value.quarantined_at,
        )
        return value


@dataclass(frozen=True, slots=True)
class PolicyConflict:
    kind: PolicyConflictKind
    affected_operations: tuple[InformationOperation, ...]

    def __post_init__(self) -> None:
        if not self.affected_operations:
            raise ValueError("policy conflict must affect at least one operation")
        if len(set(self.affected_operations)) != len(self.affected_operations):
            raise ValueError("policy conflict operations must be unique")

    def to_dict(self) -> JSONObject:
        return {
            "kind": self.kind.value,
            "affected_operations": [value.value for value in self.affected_operations],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PolicyConflict:
        operations = cast(tuple[object, ...] | list[object], data["affected_operations"])
        return cls(
            kind=PolicyConflictKind(str(data["kind"])),
            affected_operations=tuple(InformationOperation(str(value)) for value in operations),
        )


@dataclass(frozen=True, slots=True)
class PolicyComposition:
    composition_id: str
    source_policy_ids: tuple[str, ...]
    source_information_ids: tuple[str, ...]
    origin_domains: tuple[str, ...]
    classification: Classification
    allowed_purposes: tuple[str, ...]
    allowed_recipients: tuple[str, ...]
    allowed_trust_domains: tuple[str, ...]
    allowed_localities: tuple[str, ...]
    allowed_providers: tuple[str, ...]
    cross_agent_sharing: bool
    retention: RetentionPolicy
    disclosure_forms: tuple[DisclosureForm, ...]
    declassification_authorities: tuple[str, ...]
    conflicts: tuple[PolicyConflict, ...]

    @classmethod
    def create(
        cls,
        *,
        source_policy_ids: tuple[str, ...],
        source_information_ids: tuple[str, ...],
        origin_domains: tuple[str, ...],
        classification: Classification,
        allowed_purposes: tuple[str, ...],
        allowed_recipients: tuple[str, ...],
        allowed_trust_domains: tuple[str, ...],
        allowed_localities: tuple[str, ...],
        allowed_providers: tuple[str, ...],
        cross_agent_sharing: bool,
        retention: RetentionPolicy,
        disclosure_forms: tuple[DisclosureForm, ...],
        declassification_authorities: tuple[str, ...],
        conflicts: tuple[PolicyConflict, ...],
    ) -> PolicyComposition:
        normalized_conflicts = tuple(
            sorted(
                set(conflicts),
                key=lambda value: (
                    value.kind.value,
                    tuple(operation.value for operation in value.affected_operations),
                ),
            )
        )
        normalized_forms = tuple(sorted(set(disclosure_forms), key=lambda value: value.value))
        identity: JSONObject = {
            "source_policy_ids": list(_ordered(source_policy_ids)),
            "source_information_ids": list(_ordered(source_information_ids)),
            "origin_domains": list(_ordered(origin_domains)),
            "classification": classification.value,
            "allowed_purposes": list(_ordered(allowed_purposes)),
            "allowed_recipients": list(_ordered(allowed_recipients)),
            "allowed_trust_domains": list(_ordered(allowed_trust_domains)),
            "allowed_localities": list(_ordered(allowed_localities)),
            "allowed_providers": list(_ordered(allowed_providers)),
            "cross_agent_sharing": cross_agent_sharing,
            "retention": retention.to_dict(),
            "disclosure_forms": [value.value for value in normalized_forms],
            "declassification_authorities": list(_ordered(declassification_authorities)),
            "conflicts": [value.to_dict() for value in normalized_conflicts],
        }
        return cls(
            composition_id=_canonical_id("composition", identity),
            source_policy_ids=_ordered(source_policy_ids),
            source_information_ids=_ordered(source_information_ids),
            origin_domains=_ordered(origin_domains),
            classification=classification,
            allowed_purposes=_ordered(allowed_purposes),
            allowed_recipients=_ordered(allowed_recipients),
            allowed_trust_domains=_ordered(allowed_trust_domains),
            allowed_localities=_ordered(allowed_localities),
            allowed_providers=_ordered(allowed_providers),
            cross_agent_sharing=cross_agent_sharing,
            retention=retention,
            disclosure_forms=normalized_forms,
            declassification_authorities=_ordered(declassification_authorities),
            conflicts=normalized_conflicts,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.composition_id, "policy composition id")
        for value in (*self.source_policy_ids, *self.source_information_ids):
            _require_opaque(value, "policy composition reference")
        for values, name in (
            (self.source_policy_ids, "composition policy ids"),
            (self.source_information_ids, "composition information ids"),
            (self.origin_domains, "composition origin domains"),
            (self.allowed_purposes, "composition purposes"),
            (self.allowed_recipients, "composition recipients"),
            (self.allowed_trust_domains, "composition trust domains"),
            (self.allowed_localities, "composition localities"),
            (self.allowed_providers, "composition providers"),
            (
                self.declassification_authorities,
                "composition declassification authorities",
            ),
        ):
            _unique(values, name)
        if len(set(self.disclosure_forms)) != len(self.disclosure_forms):
            raise ValueError("composition disclosure forms must be unique")
        if len(set(self.conflicts)) != len(self.conflicts):
            raise ValueError("composition conflicts must be unique")

    def conflicts_for(self, operation: InformationOperation) -> tuple[PolicyConflict, ...]:
        return tuple(value for value in self.conflicts if operation in value.affected_operations)

    def to_dict(self) -> JSONObject:
        return {
            "composition_id": self.composition_id,
            "source_policy_ids": list(self.source_policy_ids),
            "source_information_ids": list(self.source_information_ids),
            "origin_domains": list(self.origin_domains),
            "classification": self.classification.value,
            "allowed_purposes": list(self.allowed_purposes),
            "allowed_recipients": list(self.allowed_recipients),
            "allowed_trust_domains": list(self.allowed_trust_domains),
            "allowed_localities": list(self.allowed_localities),
            "allowed_providers": list(self.allowed_providers),
            "cross_agent_sharing": self.cross_agent_sharing,
            "retention": self.retention.to_dict(),
            "disclosure_forms": [value.value for value in self.disclosure_forms],
            "declassification_authorities": list(self.declassification_authorities),
            "conflicts": [value.to_dict() for value in self.conflicts],
        }


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    operation: InformationOperation
    disposition: DecisionDisposition
    reasons: tuple[DecisionReason, ...]
    conflicts: tuple[PolicyConflictKind, ...]

    def __post_init__(self) -> None:
        if not self.reasons:
            raise ValueError("policy decision must explain its disposition")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("policy decision reasons must be unique")
        if len(set(self.conflicts)) != len(self.conflicts):
            raise ValueError("policy decision conflicts must be unique")
        if self.disposition is DecisionDisposition.ALLOW:
            if self.reasons != (DecisionReason.PERMITTED,) or self.conflicts:
                raise ValueError("allowed policy decision must be unambiguously permitted")
        elif DecisionReason.PERMITTED in self.reasons:
            raise ValueError("denied policy decision cannot claim permission")

    @property
    def allowed(self) -> bool:
        return self.disposition is DecisionDisposition.ALLOW

    def to_dict(self) -> JSONObject:
        return {
            "operation": self.operation.value,
            "disposition": self.disposition.value,
            "reasons": [value.value for value in self.reasons],
            "conflicts": [value.value for value in self.conflicts],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PolicyDecision:
        return cls(
            operation=InformationOperation(str(data["operation"])),
            disposition=DecisionDisposition(str(data["disposition"])),
            reasons=tuple(
                DecisionReason(str(value))
                for value in cast(tuple[object, ...] | list[object], data["reasons"])
            ),
            conflicts=tuple(
                PolicyConflictKind(str(value))
                for value in cast(tuple[object, ...] | list[object], data["conflicts"])
            ),
        )


@dataclass(frozen=True, slots=True)
class InformationAccessRequest:
    request_id: str
    information_ref: GovernedInformationRef
    context: AccessContext

    @classmethod
    def create(
        cls,
        *,
        information_ref: GovernedInformationRef,
        context: AccessContext,
    ) -> InformationAccessRequest:
        payload: JSONObject = {
            "information_ref": information_ref.to_dict(),
            "context": context.to_dict(),
        }
        return cls(_canonical_id("iarequest", payload), information_ref, context)

    def __post_init__(self) -> None:
        _require_opaque(self.request_id, "information access request id")
        if self.context.operation in {
            InformationOperation.DISCLOSE,
            InformationOperation.DECLASSIFY,
        }:
            raise ValueError("internal access request uses a disclosure-only operation")

    def to_dict(self) -> JSONObject:
        return {
            "request_id": self.request_id,
            "information_ref": self.information_ref.to_dict(),
            "context": self.context.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> InformationAccessRequest:
        value = cls.create(
            information_ref=GovernedInformationRef.from_dict(
                cast(Mapping[str, object], data["information_ref"])
            ),
            context=AccessContext.from_dict(cast(Mapping[str, object], data["context"])),
        )
        if value.request_id != str(data["request_id"]):
            raise ValueError("access request id does not match immutable content")
        return value


@dataclass(frozen=True, slots=True)
class InformationAccessDecision:
    decision_id: str
    request: InformationAccessRequest
    composition_id: str
    policy_decision: PolicyDecision
    decided_at: datetime
    causal_event_cursor: int

    @classmethod
    def create(
        cls,
        *,
        request: InformationAccessRequest,
        composition_id: str,
        policy_decision: PolicyDecision,
        decided_at: datetime,
        causal_event_cursor: int,
    ) -> InformationAccessDecision:
        payload: JSONObject = {
            "request": request.to_dict(),
            "composition_id": composition_id,
            "policy_decision": policy_decision.to_dict(),
            "decided_at": decided_at.isoformat(),
            "causal_event_cursor": causal_event_cursor,
        }
        return cls(
            _canonical_id("iadecision", payload),
            request,
            composition_id,
            policy_decision,
            decided_at,
            causal_event_cursor,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.decision_id, "information access decision id")
        _require_opaque(self.composition_id, "decision composition id")
        _require_aware(self.decided_at, "access decision time")
        if self.causal_event_cursor < 0:
            raise ValueError("access decision causal cursor cannot be negative")
        if self.decided_at != self.request.context.decision_time:
            raise ValueError("access decision must use its immutable context time")
        if self.policy_decision.operation is not self.request.context.operation:
            raise ValueError("access decision operation differs from its context")

    @property
    def allowed(self) -> bool:
        return self.policy_decision.allowed

    def to_dict(self) -> JSONObject:
        return {
            "decision_id": self.decision_id,
            "request": self.request.to_dict(),
            "composition_id": self.composition_id,
            "policy_decision": self.policy_decision.to_dict(),
            "decided_at": self.decided_at.isoformat(),
            "causal_event_cursor": self.causal_event_cursor,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> InformationAccessDecision:
        value = cls.create(
            request=InformationAccessRequest.from_dict(cast(Mapping[str, object], data["request"])),
            composition_id=str(data["composition_id"]),
            policy_decision=PolicyDecision.from_dict(
                cast(Mapping[str, object], data["policy_decision"])
            ),
            decided_at=_datetime(data, "decided_at"),
            causal_event_cursor=int(cast(int, data["causal_event_cursor"])),
        )
        if value.decision_id != str(data["decision_id"]):
            raise ValueError("access decision id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _governance_event(
            event_type=INFORMATION_ACCESS_DECIDED_EVENT,
            event_id=f"information-access-decided:{self.decision_id}",
            source=source,
            subject=self.decision_id,
            timestamp=self.decided_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> InformationAccessDecision:
        if event.type != INFORMATION_ACCESS_DECIDED_EVENT:
            raise ValueError("event is not an information access decision")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"information-access-decided:{value.decision_id}",
            subject=value.decision_id,
            timestamp=value.decided_at,
        )
        return value


@dataclass(frozen=True, slots=True)
class DisclosureRequest:
    request_id: str
    information_ref: GovernedInformationRef
    context: AccessContext

    @classmethod
    def create(
        cls,
        *,
        information_ref: GovernedInformationRef,
        context: AccessContext,
    ) -> DisclosureRequest:
        payload: JSONObject = {
            "information_ref": information_ref.to_dict(),
            "context": context.to_dict(),
        }
        return cls(_canonical_id("disrequest", payload), information_ref, context)

    def __post_init__(self) -> None:
        _require_opaque(self.request_id, "disclosure request id")
        if self.context.destination_trust_domain is None or self.context.recipient is None:
            raise ValueError("disclosure request requires destination and recipient")
        if self.context.disclosure_form is None:
            raise ValueError("disclosure request requires a disclosure form")

    def to_dict(self) -> JSONObject:
        return {
            "request_id": self.request_id,
            "information_ref": self.information_ref.to_dict(),
            "context": self.context.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DisclosureRequest:
        value = cls.create(
            information_ref=GovernedInformationRef.from_dict(
                cast(Mapping[str, object], data["information_ref"])
            ),
            context=AccessContext.from_dict(cast(Mapping[str, object], data["context"])),
        )
        if value.request_id != str(data["request_id"]):
            raise ValueError("disclosure request id does not match immutable content")
        return value


@dataclass(frozen=True, slots=True)
class DisclosureDecision:
    decision_id: str
    request: DisclosureRequest
    composition_id: str
    policy_decision: PolicyDecision
    decided_at: datetime
    causal_event_cursor: int

    @classmethod
    def create(
        cls,
        *,
        request: DisclosureRequest,
        composition_id: str,
        policy_decision: PolicyDecision,
        decided_at: datetime,
        causal_event_cursor: int,
    ) -> DisclosureDecision:
        payload: JSONObject = {
            "request": request.to_dict(),
            "composition_id": composition_id,
            "policy_decision": policy_decision.to_dict(),
            "decided_at": decided_at.isoformat(),
            "causal_event_cursor": causal_event_cursor,
        }
        return cls(
            _canonical_id("disdecision", payload),
            request,
            composition_id,
            policy_decision,
            decided_at,
            causal_event_cursor,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.decision_id, "disclosure decision id")
        _require_opaque(self.composition_id, "disclosure composition id")
        _require_aware(self.decided_at, "disclosure decision time")
        if self.causal_event_cursor < 0:
            raise ValueError("disclosure decision causal cursor cannot be negative")
        if self.decided_at != self.request.context.decision_time:
            raise ValueError("disclosure decision must use its immutable context time")
        if self.policy_decision.operation is not InformationOperation.DISCLOSE:
            raise ValueError("disclosure decision requires a disclosure operation")

    @property
    def allowed(self) -> bool:
        return self.policy_decision.allowed

    def to_dict(self) -> JSONObject:
        return {
            "decision_id": self.decision_id,
            "request": self.request.to_dict(),
            "composition_id": self.composition_id,
            "policy_decision": self.policy_decision.to_dict(),
            "decided_at": self.decided_at.isoformat(),
            "causal_event_cursor": self.causal_event_cursor,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DisclosureDecision:
        value = cls.create(
            request=DisclosureRequest.from_dict(cast(Mapping[str, object], data["request"])),
            composition_id=str(data["composition_id"]),
            policy_decision=PolicyDecision.from_dict(
                cast(Mapping[str, object], data["policy_decision"])
            ),
            decided_at=_datetime(data, "decided_at"),
            causal_event_cursor=int(cast(int, data["causal_event_cursor"])),
        )
        if value.decision_id != str(data["decision_id"]):
            raise ValueError("disclosure decision id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _governance_event(
            event_type=DISCLOSURE_DECIDED_EVENT,
            event_id=f"information-disclosure-decided:{self.decision_id}",
            source=source,
            subject=self.decision_id,
            timestamp=self.decided_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> DisclosureDecision:
        if event.type != DISCLOSURE_DECIDED_EVENT:
            raise ValueError("event is not a disclosure decision")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"information-disclosure-decided:{value.decision_id}",
            subject=value.decision_id,
            timestamp=value.decided_at,
        )
        return value


@dataclass(frozen=True, slots=True)
class DeclassificationRequest:
    request_id: str
    information_ref: GovernedInformationRef
    proposed_policy_id: str
    context: AccessContext

    @classmethod
    def create(
        cls,
        *,
        information_ref: GovernedInformationRef,
        proposed_policy_id: str,
        context: AccessContext,
    ) -> DeclassificationRequest:
        payload: JSONObject = {
            "information_ref": information_ref.to_dict(),
            "proposed_policy_id": proposed_policy_id,
            "context": context.to_dict(),
        }
        return cls(
            _canonical_id("declassrequest", payload),
            information_ref,
            proposed_policy_id,
            context,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.request_id, "declassification request id")
        _require_opaque(self.proposed_policy_id, "proposed policy id")
        if self.context.operation is not InformationOperation.DECLASSIFY:
            raise ValueError("declassification request requires declassify operation")

    def to_dict(self) -> JSONObject:
        return {
            "request_id": self.request_id,
            "information_ref": self.information_ref.to_dict(),
            "proposed_policy_id": self.proposed_policy_id,
            "context": self.context.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DeclassificationRequest:
        value = cls.create(
            information_ref=GovernedInformationRef.from_dict(
                cast(Mapping[str, object], data["information_ref"])
            ),
            proposed_policy_id=str(data["proposed_policy_id"]),
            context=AccessContext.from_dict(cast(Mapping[str, object], data["context"])),
        )
        if value.request_id != str(data["request_id"]):
            raise ValueError("declassification request id does not match immutable content")
        return value


@dataclass(frozen=True, slots=True)
class DeclassificationDecision:
    decision_id: str
    request: DeclassificationRequest
    composition_id: str
    policy_decision: PolicyDecision
    decided_at: datetime
    causal_event_cursor: int

    @classmethod
    def create(
        cls,
        *,
        request: DeclassificationRequest,
        composition_id: str,
        policy_decision: PolicyDecision,
        decided_at: datetime,
        causal_event_cursor: int,
    ) -> DeclassificationDecision:
        payload: JSONObject = {
            "request": request.to_dict(),
            "composition_id": composition_id,
            "policy_decision": policy_decision.to_dict(),
            "decided_at": decided_at.isoformat(),
            "causal_event_cursor": causal_event_cursor,
        }
        return cls(
            _canonical_id("declassdecision", payload),
            request,
            composition_id,
            policy_decision,
            decided_at,
            causal_event_cursor,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.decision_id, "declassification decision id")
        _require_opaque(self.composition_id, "declassification composition id")
        _require_aware(self.decided_at, "declassification decision time")
        if self.causal_event_cursor < 0:
            raise ValueError("declassification decision causal cursor cannot be negative")
        if self.decided_at != self.request.context.decision_time:
            raise ValueError("declassification decision must use its immutable context time")
        if self.policy_decision.operation is not InformationOperation.DECLASSIFY:
            raise ValueError("declassification decision requires a declassify operation")

    @property
    def allowed(self) -> bool:
        return self.policy_decision.allowed

    def to_dict(self) -> JSONObject:
        return {
            "decision_id": self.decision_id,
            "request": self.request.to_dict(),
            "composition_id": self.composition_id,
            "policy_decision": self.policy_decision.to_dict(),
            "decided_at": self.decided_at.isoformat(),
            "causal_event_cursor": self.causal_event_cursor,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DeclassificationDecision:
        value = cls.create(
            request=DeclassificationRequest.from_dict(cast(Mapping[str, object], data["request"])),
            composition_id=str(data["composition_id"]),
            policy_decision=PolicyDecision.from_dict(
                cast(Mapping[str, object], data["policy_decision"])
            ),
            decided_at=_datetime(data, "decided_at"),
            causal_event_cursor=int(cast(int, data["causal_event_cursor"])),
        )
        if value.decision_id != str(data["decision_id"]):
            raise ValueError("declassification decision id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _governance_event(
            event_type=DECLASSIFICATION_DECIDED_EVENT,
            event_id=f"information-declassification-decided:{self.decision_id}",
            source=source,
            subject=self.decision_id,
            timestamp=self.decided_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> DeclassificationDecision:
        if event.type != DECLASSIFICATION_DECIDED_EVENT:
            raise ValueError("event is not a declassification decision")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"information-declassification-decided:{value.decision_id}",
            subject=value.decision_id,
            timestamp=value.decided_at,
        )
        return value


@dataclass(frozen=True, slots=True)
class DeclassifiedDisclosureView:
    """Immutable relaxed view authorized by one canonical declassification decision."""

    view_id: str
    information_ref: GovernedInformationRef
    source_information_ref: GovernedInformationRef
    approved_policy_id: str
    declassification_decision_id: str
    source_policy_ids: tuple[str, ...]
    source_lineage_refs: tuple[str, ...]
    created_at: datetime
    causal_event_cursor: int

    @classmethod
    def create(
        cls,
        *,
        decision: DeclassificationDecision,
        created_at: datetime,
        causal_event_cursor: int,
    ) -> DeclassifiedDisclosureView:
        if not decision.allowed:
            raise ValueError("declassified view requires an allowed declassification decision")
        if created_at < decision.decided_at:
            raise ValueError("declassified view cannot precede its authorizing decision")
        context = decision.request.context
        payload: JSONObject = {
            "source_information_ref": decision.request.information_ref.to_dict(),
            "approved_policy_id": decision.request.proposed_policy_id,
            "declassification_decision_id": decision.decision_id,
            "source_policy_ids": list(context.policy_ids),
            "source_lineage_refs": list(context.source_lineage_refs),
            "created_at": created_at.isoformat(),
            "causal_event_cursor": causal_event_cursor,
        }
        view_id = _canonical_id("declassview", payload)
        return cls(
            view_id=view_id,
            information_ref=GovernedInformationRef(
                _canonical_id("info", {"declassified_view_id": view_id})
            ),
            source_information_ref=decision.request.information_ref,
            approved_policy_id=decision.request.proposed_policy_id,
            declassification_decision_id=decision.decision_id,
            source_policy_ids=context.policy_ids,
            source_lineage_refs=context.source_lineage_refs,
            created_at=created_at,
            causal_event_cursor=causal_event_cursor,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.view_id, "declassified view id")
        _require_opaque(self.approved_policy_id, "declassified view policy id")
        _require_opaque(
            self.declassification_decision_id,
            "declassified view decision id",
        )
        for value in self.source_policy_ids:
            _require_opaque(value, "declassified view source policy id")
        for value in self.source_lineage_refs:
            _require_opaque(value, "declassified view source lineage ref")
        _unique(self.source_policy_ids, "declassified view source policy ids", required=True)
        _unique(
            self.source_lineage_refs,
            "declassified view source lineage refs",
            required=True,
        )
        _require_aware(self.created_at, "declassified view creation time")
        if self.causal_event_cursor < 0:
            raise ValueError("declassified view causal cursor cannot be negative")
        expected_information_id = _canonical_id(
            "info",
            {"declassified_view_id": self.view_id},
        )
        if self.information_ref.information_id != expected_information_id:
            raise ValueError("declassified view information id is inconsistent")

    def to_dict(self) -> JSONObject:
        return {
            "view_id": self.view_id,
            "information_ref": self.information_ref.to_dict(),
            "source_information_ref": self.source_information_ref.to_dict(),
            "approved_policy_id": self.approved_policy_id,
            "declassification_decision_id": self.declassification_decision_id,
            "source_policy_ids": list(self.source_policy_ids),
            "source_lineage_refs": list(self.source_lineage_refs),
            "created_at": self.created_at.isoformat(),
            "causal_event_cursor": self.causal_event_cursor,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DeclassifiedDisclosureView:
        value = cls(
            view_id=str(data["view_id"]),
            information_ref=GovernedInformationRef.from_dict(
                cast(Mapping[str, object], data["information_ref"])
            ),
            source_information_ref=GovernedInformationRef.from_dict(
                cast(Mapping[str, object], data["source_information_ref"])
            ),
            approved_policy_id=str(data["approved_policy_id"]),
            declassification_decision_id=str(data["declassification_decision_id"]),
            source_policy_ids=_strings(data, "source_policy_ids"),
            source_lineage_refs=_strings(data, "source_lineage_refs"),
            created_at=_datetime(data, "created_at"),
            causal_event_cursor=int(cast(int, data["causal_event_cursor"])),
        )
        payload: JSONObject = {
            "source_information_ref": value.source_information_ref.to_dict(),
            "approved_policy_id": value.approved_policy_id,
            "declassification_decision_id": value.declassification_decision_id,
            "source_policy_ids": list(value.source_policy_ids),
            "source_lineage_refs": list(value.source_lineage_refs),
            "created_at": value.created_at.isoformat(),
            "causal_event_cursor": value.causal_event_cursor,
        }
        if value.view_id != _canonical_id("declassview", payload):
            raise ValueError("declassified view id does not match immutable content")
        return value

    def to_event(self, *, source: str) -> Event:
        return _governance_event(
            event_type=DECLASSIFIED_VIEW_RECORDED_EVENT,
            event_id=f"information-declassified-view-recorded:{self.view_id}",
            source=source,
            subject=self.information_ref.information_id,
            timestamp=self.created_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> DeclassifiedDisclosureView:
        if event.type != DECLASSIFIED_VIEW_RECORDED_EVENT:
            raise ValueError("event is not a declassified disclosure view")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"information-declassified-view-recorded:{value.view_id}",
            subject=value.information_ref.information_id,
            timestamp=value.created_at,
        )
        return value


@dataclass(frozen=True, slots=True)
class DisclosureView:
    view_id: str
    information_ref: GovernedInformationRef
    source_information_ref: GovernedInformationRef
    transformation: LineageTransformation
    inherited_policy_ids: tuple[str, ...]
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        source_information_ref: GovernedInformationRef,
        transformation: LineageTransformation,
        inherited_policy_ids: tuple[str, ...],
        created_at: datetime,
    ) -> DisclosureView:
        if transformation not in {
            LineageTransformation.REDACTION,
            LineageTransformation.ABSTRACTION,
        }:
            raise ValueError("disclosure view requires redaction or abstraction")
        payload: JSONObject = {
            "source_information_ref": source_information_ref.to_dict(),
            "transformation": transformation.value,
            "inherited_policy_ids": list(_ordered(inherited_policy_ids)),
            "created_at": created_at.isoformat(),
        }
        view_id = _canonical_id("view", payload)
        information_ref = GovernedInformationRef(
            _canonical_id("info", {"disclosure_view_id": view_id})
        )
        return cls(
            view_id,
            information_ref,
            source_information_ref,
            transformation,
            _ordered(inherited_policy_ids),
            created_at,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.view_id, "disclosure view id")
        for value in self.inherited_policy_ids:
            _require_opaque(value, "disclosure view policy id")
        _require_aware(self.created_at, "disclosure view creation time")

    def lineage(self) -> InformationLineage:
        return InformationLineage.create(
            information_id=self.information_ref.information_id,
            source_information_ids=(self.source_information_ref.information_id,),
            transformation=self.transformation,
            recorded_at=self.created_at,
        )


@dataclass(frozen=True, slots=True)
class SecurityAuditReceipt:
    receipt_id: str
    decision_type: str
    decision_id: str
    context_id: str
    disposition: DecisionDisposition
    recorded_at: datetime

    @classmethod
    def from_decision(
        cls,
        decision: InformationAccessDecision | DisclosureDecision,
    ) -> SecurityAuditReceipt:
        decision_type = (
            "access" if isinstance(decision, InformationAccessDecision) else "disclosure"
        )
        payload: JSONObject = {
            "decision_type": decision_type,
            "decision_id": decision.decision_id,
            "context_id": decision.request.context.context_id,
            "disposition": decision.policy_decision.disposition.value,
            "recorded_at": decision.decided_at.isoformat(),
        }
        return cls(
            _canonical_id("audit", payload),
            decision_type,
            decision.decision_id,
            decision.request.context.context_id,
            decision.policy_decision.disposition,
            decision.decided_at,
        )

    def __post_init__(self) -> None:
        _require_opaque(self.receipt_id, "security audit receipt id")
        _require_opaque(self.decision_id, "audit decision id")
        _require_opaque(self.context_id, "audit context id")
        if self.decision_type not in {"access", "disclosure"}:
            raise ValueError("unsupported security audit receipt type")
        if self.disposition is not DecisionDisposition.ALLOW:
            raise ValueError("material denials require canonical decision admission")
        _require_aware(self.recorded_at, "audit receipt time")

    def to_dict(self) -> JSONObject:
        return {
            "receipt_id": self.receipt_id,
            "decision_type": self.decision_type,
            "decision_id": self.decision_id,
            "context_id": self.context_id,
            "disposition": self.disposition.value,
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> SecurityAuditReceipt:
        return cls(
            receipt_id=str(data["receipt_id"]),
            decision_type=str(data["decision_type"]),
            decision_id=str(data["decision_id"]),
            context_id=str(data["context_id"]),
            disposition=DecisionDisposition(str(data["disposition"])),
            recorded_at=_datetime(data, "recorded_at"),
        )

    def to_event(self, *, source: str) -> Event:
        return _governance_event(
            event_type=SECURITY_AUDIT_RECEIPT_EVENT,
            event_id=f"information-security-audit:{self.receipt_id}",
            source=source,
            subject=self.receipt_id,
            timestamp=self.recorded_at,
            payload=self.to_dict(),
        )

    @classmethod
    def from_event(cls, event: Event) -> SecurityAuditReceipt:
        if event.type != SECURITY_AUDIT_RECEIPT_EVENT:
            raise ValueError("event is not a security audit receipt")
        value = cls.from_dict(event.payload)
        _validate_envelope(
            event,
            event_id=f"information-security-audit:{value.receipt_id}",
            subject=value.receipt_id,
            timestamp=value.recorded_at,
        )
        return value


def validate_governance_event_envelope(
    event: Event,
    *,
    protected_values: tuple[str, ...] = (),
) -> None:
    """Reject protected values from obvious governance envelope/index fields."""

    if event.type not in INFORMATION_GOVERNANCE_EVENT_TYPES:
        raise ValueError("event is outside the information-governance envelope")
    envelope_values = (
        event.id,
        event.source,
        event.subject or "",
        event.correlation_id or "",
        event.causation_id or "",
        json.dumps(dict(event.metadata), sort_keys=True, ensure_ascii=False),
    )
    protected = tuple(value for value in protected_values if value)
    if any(secret in field for secret in protected for field in envelope_values):
        raise ValueError("unsafe information-governance event envelope")
    if event.subject is None or _OPAQUE_ID.fullmatch(event.subject) is None:
        raise ValueError("information-governance event subject must be opaque")


def _governance_event(
    *,
    event_type: str,
    event_id: str,
    source: str,
    subject: str,
    timestamp: datetime,
    payload: Mapping[str, JSONValue],
) -> Event:
    event = Event(
        id=event_id,
        type=event_type,
        source=source,
        subject=subject,
        timestamp=timestamp,
        payload=payload,
    )
    validate_governance_event_envelope(event)
    return event


def _validate_envelope(
    event: Event,
    *,
    event_id: str,
    subject: str,
    timestamp: datetime,
) -> None:
    validate_governance_event_envelope(event)
    if event.id != event_id or event.subject != subject or event.timestamp != timestamp:
        raise ValueError("information-governance event envelope is inconsistent")
