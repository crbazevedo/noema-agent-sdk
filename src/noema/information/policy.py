"""Deterministic composition and evaluation for information governance."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from .models import (
    AccessContext,
    Classification,
    DecisionDisposition,
    DecisionReason,
    DeclassificationDecision,
    DeclassificationRequest,
    DeclassifiedDisclosureView,
    DisclosureDecision,
    DisclosureForm,
    DisclosureRequest,
    GovernedInformationRef,
    InformationAccessDecision,
    InformationAccessRequest,
    InformationLineage,
    InformationOperation,
    InformationPolicy,
    PolicyBinding,
    PolicyComposition,
    PolicyConflict,
    PolicyConflictKind,
    PolicyDecision,
    PrincipalSnapshot,
    QuarantinedInformationRef,
    QuarantinePolicy,
    RetentionPolicy,
)

_INTERNAL_OPERATIONS = (
    InformationOperation.READ,
    InformationOperation.RETRIEVE,
    InformationOperation.REASON,
    InformationOperation.MODEL_CONTEXT,
    InformationOperation.WORK_ASSIGN,
    InformationOperation.DELETE,
    InformationOperation.CLASSIFY,
    InformationOperation.SHARED_INDEX,
    InformationOperation.TELEMETRY,
    InformationOperation.EXTERNAL_CONNECTOR,
    InformationOperation.CROSS_AGENT_SHARE,
)
_CONTENT_OPERATIONS = _INTERNAL_OPERATIONS
_PURPOSE_OPERATIONS = (
    *_CONTENT_OPERATIONS,
    InformationOperation.DISCLOSE,
    InformationOperation.DECLASSIFY,
)
_RECIPIENT_OPERATIONS = (*_CONTENT_OPERATIONS, InformationOperation.DISCLOSE)
_TRUST_DOMAIN_OPERATIONS = (*_RECIPIENT_OPERATIONS, InformationOperation.DECLASSIFY)
_LOCALITY_OPERATIONS = _TRUST_DOMAIN_OPERATIONS
_PROVIDER_REQUIRED_OPERATIONS = (
    InformationOperation.MODEL_CONTEXT,
    InformationOperation.EXTERNAL_CONNECTOR,
)
_SHARING_OPERATIONS = (
    InformationOperation.WORK_ASSIGN,
    InformationOperation.SHARED_INDEX,
    InformationOperation.CROSS_AGENT_SHARE,
)
_PRINCIPAL_DESTINATION_OPERATIONS = (
    InformationOperation.WORK_ASSIGN,
    InformationOperation.CROSS_AGENT_SHARE,
)
_ALL_RESTRICTED_OPERATIONS = tuple(
    operation
    for operation in InformationOperation
    if operation not in {InformationOperation.UNKNOWN, InformationOperation.CLASSIFY}
)

_CLASSIFICATION_RANK = {
    Classification.PUBLIC: 0,
    Classification.INTERNAL: 1,
    Classification.CONFIDENTIAL: 2,
    Classification.RESTRICTED: 3,
    Classification.UNKNOWN: 4,
}


class GovernanceState(Protocol):
    """Read-only canonical state required by the pure policy engine."""

    def policy(self, policy_id: str) -> InformationPolicy | None: ...

    def binding(self, information_id: str) -> PolicyBinding | None: ...

    def lineage(self, information_id: str) -> InformationLineage | None: ...

    def quarantine(self, information_id: str) -> QuarantinedInformationRef | None: ...

    def declassified_view(self, information_id: str) -> DeclassifiedDisclosureView | None: ...

    @property
    def event_cursor(self) -> int: ...


def _intersection(values: Iterable[tuple[str, ...]]) -> tuple[str, ...]:
    materialized = tuple(values)
    if not materialized:
        return ()
    result = set(materialized[0])
    for current in materialized[1:]:
        result.intersection_update(current)
    return tuple(sorted(result))


def _enum_intersection(
    values: Iterable[tuple[DisclosureForm, ...]],
) -> tuple[DisclosureForm, ...]:
    materialized = tuple(values)
    if not materialized:
        return ()
    result = set(materialized[0])
    for current in materialized[1:]:
        result.intersection_update(current)
    return tuple(sorted(result, key=str))


def _conflict(
    kind: PolicyConflictKind,
    operations: tuple[InformationOperation, ...],
) -> PolicyConflict:
    return PolicyConflict(kind, operations)


def compose_policies(
    policies: Iterable[InformationPolicy],
    *,
    source_information_ids: tuple[str, ...],
    extra_conflicts: tuple[PolicyConflict, ...] = (),
) -> PolicyComposition:
    """Compose every source restriction without pretending fields are uniform."""

    values = tuple(sorted(policies, key=lambda value: value.policy_id))
    if not values:
        return _failed_composition(
            source_information_ids,
            (
                *extra_conflicts,
                _conflict(
                    PolicyConflictKind.MISSING_POLICY_VERSION,
                    _ALL_RESTRICTED_OPERATIONS,
                ),
            ),
        )

    classification = max(
        (value.classification for value in values),
        key=_CLASSIFICATION_RANK.__getitem__,
    )
    purposes = _intersection(value.allowed_purposes for value in values)
    recipients = _intersection(value.allowed_recipients for value in values)
    trust_domains = _intersection(value.allowed_trust_domains for value in values)
    localities = _intersection(value.allowed_localities for value in values)
    providers = _intersection(value.allowed_providers for value in values)
    disclosure_forms = _enum_intersection(value.disclosure_forms for value in values)
    declassification_authorities = _intersection(
        value.declassification_authorities for value in values
    )

    retain_until_values = tuple(
        value.retention.retain_until for value in values if value.retention.retain_until is not None
    )
    delete_after_values = tuple(
        value.retention.delete_after for value in values if value.retention.delete_after is not None
    )
    holds = {hold.hold_id: hold for value in values for hold in value.retention.holds}
    retention = RetentionPolicy(
        retain_until=max(retain_until_values) if retain_until_values else None,
        delete_after=min(delete_after_values) if delete_after_values else None,
        deletion_required=any(value.retention.deletion_required for value in values),
        holds=tuple(holds[key] for key in sorted(holds)),
    )

    conflicts = list(extra_conflicts)
    if classification is Classification.UNKNOWN:
        conflicts.append(
            _conflict(PolicyConflictKind.UNKNOWN_CLASSIFICATION, _ALL_RESTRICTED_OPERATIONS)
        )
    for condition, kind, operations in (
        (not purposes, PolicyConflictKind.EMPTY_PURPOSES, _PURPOSE_OPERATIONS),
        (not recipients, PolicyConflictKind.EMPTY_RECIPIENTS, _RECIPIENT_OPERATIONS),
        (
            not trust_domains,
            PolicyConflictKind.EMPTY_TRUST_DOMAINS,
            _TRUST_DOMAIN_OPERATIONS,
        ),
        (not localities, PolicyConflictKind.EMPTY_LOCALITIES, _LOCALITY_OPERATIONS),
        (
            not providers,
            PolicyConflictKind.EMPTY_PROVIDERS,
            _PROVIDER_REQUIRED_OPERATIONS,
        ),
        (
            not disclosure_forms,
            PolicyConflictKind.EMPTY_DISCLOSURE_FORMS,
            (InformationOperation.DISCLOSE,),
        ),
        (
            not declassification_authorities,
            PolicyConflictKind.NO_DECLASSIFICATION_AUTHORITY,
            (InformationOperation.DECLASSIFY,),
        ),
    ):
        if condition:
            conflicts.append(_conflict(kind, operations))
    if retention.active_holds:
        conflicts.append(
            _conflict(
                PolicyConflictKind.LEGAL_HOLD_DELETION,
                (InformationOperation.DELETE,),
            )
        )
    if (
        retention.retain_until is not None
        and retention.delete_after is not None
        and retention.delete_after <= retention.retain_until
    ):
        conflicts.append(
            _conflict(
                PolicyConflictKind.RETENTION_WINDOW,
                (InformationOperation.DELETE,),
            )
        )

    return PolicyComposition.create(
        source_policy_ids=tuple(value.policy_id for value in values),
        source_information_ids=source_information_ids,
        origin_domains=tuple(domain for value in values for domain in value.origin_domains),
        classification=classification,
        allowed_purposes=purposes,
        allowed_recipients=recipients,
        allowed_trust_domains=trust_domains,
        allowed_localities=localities,
        allowed_providers=providers,
        cross_agent_sharing=all(value.cross_agent_sharing for value in values),
        retention=retention,
        disclosure_forms=disclosure_forms,
        declassification_authorities=declassification_authorities,
        conflicts=tuple(conflicts),
    )


def _failed_composition(
    source_information_ids: tuple[str, ...],
    conflicts: tuple[PolicyConflict, ...],
) -> PolicyComposition:
    return PolicyComposition.create(
        source_policy_ids=(),
        source_information_ids=source_information_ids,
        origin_domains=("unknown",),
        classification=Classification.UNKNOWN,
        allowed_purposes=(),
        allowed_recipients=(),
        allowed_trust_domains=(),
        allowed_localities=(),
        allowed_providers=(),
        cross_agent_sharing=False,
        retention=RetentionPolicy(),
        disclosure_forms=(),
        declassification_authorities=(),
        conflicts=conflicts,
    )


class InformationGovernanceEngine:
    """Pure, fail-closed decisions over immutable canonical state and context."""

    def __init__(self, state: GovernanceState) -> None:
        self._state = state

    @property
    def state(self) -> GovernanceState:
        return self._state

    def composition_for(self, information_ref: GovernedInformationRef) -> PolicyComposition:
        information_id = information_ref.information_id
        quarantine = self._state.quarantine(information_id)
        if quarantine is not None:
            return _failed_composition(
                (information_id,),
                (_conflict(PolicyConflictKind.QUARANTINED, _ALL_RESTRICTED_OPERATIONS),),
            )

        declassified_view = self._state.declassified_view(information_id)
        if declassified_view is not None:
            approved = self._state.policy(declassified_view.approved_policy_id)
            if approved is None:
                return _failed_composition(
                    declassified_view.source_lineage_refs,
                    (
                        _conflict(
                            PolicyConflictKind.MISSING_POLICY_VERSION,
                            _ALL_RESTRICTED_OPERATIONS,
                        ),
                    ),
                )
            return compose_policies(
                (approved,),
                source_information_ids=declassified_view.source_lineage_refs,
            )

        policy_ids: set[str] = set()
        source_ids: set[str] = set()
        conflicts: list[PolicyConflict] = []
        self._resolve(
            information_id,
            policy_ids=policy_ids,
            source_ids=source_ids,
            conflicts=conflicts,
            visiting=set(),
        )
        policies: list[InformationPolicy] = []
        for policy_id in sorted(policy_ids):
            policy = self._state.policy(policy_id)
            if policy is None:
                conflicts.append(
                    _conflict(
                        PolicyConflictKind.MISSING_POLICY_VERSION,
                        _ALL_RESTRICTED_OPERATIONS,
                    )
                )
            else:
                policies.append(policy)
        return compose_policies(
            policies,
            source_information_ids=tuple(sorted(source_ids or {information_id})),
            extra_conflicts=tuple(conflicts),
        )

    def context_for(
        self,
        *,
        information_ref: GovernedInformationRef,
        actor_id: str,
        principal: PrincipalSnapshot,
        purpose: str,
        operation: InformationOperation,
        source_trust_domain: str,
        destination_trust_domain: str | None,
        recipient: str | None,
        decision_time: datetime,
        locality: str,
        provider_id: str | None = None,
        provider_security_posture: tuple[str, ...] = (),
        disclosure_form: DisclosureForm | None = None,
    ) -> AccessContext:
        composition = self.composition_for(information_ref)
        return AccessContext.create(
            actor_id=actor_id,
            principal=principal,
            purpose=purpose,
            operation=operation,
            source_trust_domain=source_trust_domain,
            destination_trust_domain=destination_trust_domain,
            recipient=recipient,
            decision_time=decision_time,
            policy_ids=composition.source_policy_ids,
            source_lineage_refs=composition.source_information_ids,
            locality=locality,
            provider_id=provider_id,
            provider_security_posture=provider_security_posture,
            disclosure_form=disclosure_form,
        )

    def decide_access(self, request: InformationAccessRequest) -> InformationAccessDecision:
        composition = self.composition_for(request.information_ref)
        quarantine = self._state.quarantine(request.information_ref.information_id)
        decision = (
            self._evaluate_quarantine(quarantine.policy, request.context)
            if quarantine is not None
            else self._evaluate_access(composition, request.context)
        )
        return InformationAccessDecision.create(
            request=request,
            composition_id=composition.composition_id,
            policy_decision=decision,
            decided_at=request.context.decision_time,
            causal_event_cursor=self._state.event_cursor,
        )

    def decide_disclosure(self, request: DisclosureRequest) -> DisclosureDecision:
        composition = self.composition_for(request.information_ref)
        reasons, conflicts = self._common_reasons(
            composition, request.context, InformationOperation.DISCLOSE
        )
        context = request.context
        if context.recipient not in composition.allowed_recipients:
            reasons.add(DecisionReason.RECIPIENT_NOT_PERMITTED)
        if context.destination_trust_domain not in composition.allowed_trust_domains:
            reasons.add(DecisionReason.TRUST_DOMAIN_NOT_PERMITTED)
        if context.disclosure_form not in composition.disclosure_forms:
            reasons.add(DecisionReason.DISCLOSURE_FORM_NOT_PERMITTED)
        if (
            context.operation is InformationOperation.CROSS_AGENT_SHARE
            and not composition.cross_agent_sharing
        ):
            reasons.add(DecisionReason.SHARING_NOT_PERMITTED)
        decision = _decision(InformationOperation.DISCLOSE, reasons, conflicts)
        return DisclosureDecision.create(
            request=request,
            composition_id=composition.composition_id,
            policy_decision=decision,
            decided_at=context.decision_time,
            causal_event_cursor=self._state.event_cursor,
        )

    def decide_declassification(self, request: DeclassificationRequest) -> DeclassificationDecision:
        composition = self.composition_for(request.information_ref)
        reasons, conflicts = self._common_reasons(
            composition, request.context, InformationOperation.DECLASSIFY
        )
        proposed = self._state.policy(request.proposed_policy_id)
        identities = request.context.principal.recipient_identities
        if proposed is None:
            conflicts.add(PolicyConflictKind.MISSING_POLICY_VERSION)
            reasons.add(DecisionReason.POLICY_CONFLICT)
        if not identities.intersection(composition.declassification_authorities):
            reasons.add(DecisionReason.DECLASSIFICATION_AUTHORITY_REQUIRED)
        if (
            proposed is not None
            and _CLASSIFICATION_RANK[proposed.classification]
            >= _CLASSIFICATION_RANK[composition.classification]
        ):
            reasons.add(DecisionReason.DECLASSIFICATION_AUTHORITY_REQUIRED)
        decision = _decision(InformationOperation.DECLASSIFY, reasons, conflicts)
        return DeclassificationDecision.create(
            request=request,
            composition_id=composition.composition_id,
            policy_decision=decision,
            decided_at=request.context.decision_time,
            causal_event_cursor=self._state.event_cursor,
        )

    def _resolve(
        self,
        information_id: str,
        *,
        policy_ids: set[str],
        source_ids: set[str],
        conflicts: list[PolicyConflict],
        visiting: set[str],
    ) -> None:
        if information_id in visiting:
            conflicts.append(
                _conflict(PolicyConflictKind.INCOMPLETE_LINEAGE, _ALL_RESTRICTED_OPERATIONS)
            )
            return
        binding = self._state.binding(information_id)
        lineage = self._state.lineage(information_id)
        if binding is None or lineage is None or binding.lineage_id != lineage.lineage_id:
            conflicts.append(
                _conflict(PolicyConflictKind.INCOMPLETE_LINEAGE, _ALL_RESTRICTED_OPERATIONS)
            )
            source_ids.add(information_id)
            return
        policy_ids.update(binding.policy_ids)
        if not lineage.source_information_ids:
            source_ids.add(information_id)
            return
        visiting.add(information_id)
        for parent in lineage.source_information_ids:
            self._resolve(
                parent,
                policy_ids=policy_ids,
                source_ids=source_ids,
                conflicts=conflicts,
                visiting=visiting,
            )
        visiting.remove(information_id)

    def _evaluate_access(
        self, composition: PolicyComposition, context: AccessContext
    ) -> PolicyDecision:
        operation = context.operation
        if operation is InformationOperation.UNKNOWN:
            return PolicyDecision(
                operation,
                DecisionDisposition.DENY,
                (DecisionReason.UNKNOWN_OPERATION,),
                (),
            )
        reasons, conflicts = self._common_reasons(composition, context, operation)
        if operation in _CONTENT_OPERATIONS:
            if not context.principal.recipient_identities.intersection(
                composition.allowed_recipients
            ):
                reasons.add(DecisionReason.RECIPIENT_NOT_PERMITTED)
        if operation in _PRINCIPAL_DESTINATION_OPERATIONS:
            if context.recipient != context.principal.principal_id:
                reasons.add(DecisionReason.RECIPIENT_NOT_PERMITTED)
            if context.destination_trust_domain not in context.principal.trust_domains:
                reasons.add(DecisionReason.PRINCIPAL_TRUST_DOMAIN_MISMATCH)
            if context.destination_trust_domain not in composition.allowed_trust_domains:
                reasons.add(DecisionReason.TRUST_DOMAIN_NOT_PERMITTED)
        if operation in _SHARING_OPERATIONS and not composition.cross_agent_sharing:
            reasons.add(DecisionReason.SHARING_NOT_PERMITTED)
        if operation is InformationOperation.DELETE:
            if (
                composition.retention.retain_until is not None
                and context.decision_time < composition.retention.retain_until
            ):
                reasons.add(DecisionReason.RETENTION_REQUIRES_PRESERVATION)
        return _decision(operation, reasons, conflicts)

    @staticmethod
    def _evaluate_quarantine(
        policy: QuarantinePolicy,
        context: AccessContext,
    ) -> PolicyDecision:
        if (
            context.operation is InformationOperation.CLASSIFY
            and not policy.human_resolution_required
            and context.locality in policy.allowed_localities
            and context.source_trust_domain in policy.allowed_trust_domains
        ):
            return PolicyDecision(
                context.operation,
                DecisionDisposition.ALLOW,
                (DecisionReason.PERMITTED,),
                (),
            )
        return PolicyDecision(
            context.operation,
            DecisionDisposition.DENY,
            (DecisionReason.QUARANTINED,),
            (PolicyConflictKind.QUARANTINED,),
        )

    @staticmethod
    def _common_reasons(
        composition: PolicyComposition,
        context: AccessContext,
        operation: InformationOperation,
    ) -> tuple[set[DecisionReason], set[PolicyConflictKind]]:
        reasons: set[DecisionReason] = set()
        conflicts = {value.kind for value in composition.conflicts_for(operation)}
        if conflicts:
            reasons.add(DecisionReason.POLICY_CONFLICT)
        if tuple(sorted(context.policy_ids)) != composition.source_policy_ids:
            reasons.add(DecisionReason.CONTEXT_POLICY_MISMATCH)
        if tuple(sorted(context.source_lineage_refs)) != composition.source_information_ids:
            reasons.add(DecisionReason.CONTEXT_LINEAGE_MISMATCH)
        if operation in _PURPOSE_OPERATIONS:
            if context.purpose not in composition.allowed_purposes:
                reasons.add(DecisionReason.PURPOSE_NOT_PERMITTED)
        if operation in _LOCALITY_OPERATIONS:
            if context.locality not in composition.allowed_localities:
                reasons.add(DecisionReason.LOCALITY_NOT_PERMITTED)
        if operation in _TRUST_DOMAIN_OPERATIONS:
            if context.source_trust_domain not in composition.allowed_trust_domains:
                reasons.add(DecisionReason.TRUST_DOMAIN_NOT_PERMITTED)
        if operation in _PROVIDER_REQUIRED_OPERATIONS or (
            operation is InformationOperation.DISCLOSE
            and context.provider_id is not None
        ):
            if context.provider_id not in composition.allowed_providers:
                reasons.add(DecisionReason.PROVIDER_NOT_PERMITTED)
        return reasons, conflicts


def _decision(
    operation: InformationOperation,
    reasons: set[DecisionReason],
    conflicts: set[PolicyConflictKind],
) -> PolicyDecision:
    if not reasons and not conflicts:
        return PolicyDecision(
            operation,
            DecisionDisposition.ALLOW,
            (DecisionReason.PERMITTED,),
            (),
        )
    if conflicts:
        reasons.add(DecisionReason.POLICY_CONFLICT)
    return PolicyDecision(
        operation,
        DecisionDisposition.DENY,
        tuple(sorted(reasons, key=lambda value: value.value)),
        tuple(sorted(conflicts, key=lambda value: value.value)),
    )
