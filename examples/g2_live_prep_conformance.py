"""Bounded G2 rehearsal for a governed, provider-bound fictional context.

This example deliberately makes no network or audio call.  It composes existing
public SDK primitives at the application boundary and records the exact request a
mock provider would receive.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from noema import (
    Classification,
    DecisionDisposition,
    DisclosureForm,
    DisclosureRequest,
    GovernanceAdmissionReceipt,
    GovernedInformationRef,
    HmacOpaqueInformationIdDeriver,
    InformationAccessDecision,
    InformationAccessRequest,
    InformationGovernanceAdmission,
    InformationGovernanceEngine,
    InformationGovernanceProjection,
    InformationLineage,
    InformationOperation,
    InformationPolicy,
    LineageTransformation,
    ModelCapabilities,
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    NoemaKernel,
    PolicyBinding,
    PrincipalSnapshot,
    RetentionPolicy,
)
from noema.information import DisclosureDecision

CORPUS_SOURCE_SHA = "621be5a8a0823c1a02c893edc69967f552e0895d"
CORPUS_SHA256 = "30b7f207ab11bf286e8bf4db320bd7c3fcad724d56995a395e23096fc0902f80"
PURPOSE = "prepare-fictional-meeting"
SOURCE_DOMAIN = "trust-domain:fictional-local"
DESTINATION_DOMAIN = "trust-domain:mock-provider"
PROVIDER_ID = "mock-remote-provider"
PROVIDER_RECIPIENT = "provider:mock-remote"
AUTHORIZED_ROLE = "role:g2-live-prep"
FIXTURE_TIME = datetime(2031, 5, 14, 14, 5, tzinfo=UTC)


class SourceWorldProvenance(StrEnum):
    """What kind of world claim the source carries."""

    FICTIONAL = "fictional"
    USER_REPORTED = "user-reported"
    DOCUMENTARY = "documentary"


class GenerationMechanism(StrEnum):
    """How a response was generated, independently of source provenance."""

    DETERMINISTIC_FIXTURE = "deterministic-fixture"
    MOCKED_PROVIDER_BOUNDARY = "mocked-provider-boundary"
    MODEL_BACKED = "model-backed"


class PhysicalPlaybackEvidence(StrEnum):
    """Whether physical playback was actually observed."""

    NOT_RUN = "not-run"
    OBSERVED = "observed"


@dataclass(frozen=True, slots=True)
class ProviderTarget:
    provider_id: str
    destination_trust_domain: str
    recipient: str
    purpose: str
    locality: str = "local"


@dataclass(frozen=True, slots=True)
class GovernedContextMaterial:
    """Application-held content whose transmitted bytes derive its governed ref."""

    information_ref: GovernedInformationRef
    source_information_ref: GovernedInformationRef
    namespace: str
    message: ModelMessage
    disclosure_form: DisclosureForm
    source_provenance: SourceWorldProvenance

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.message.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EvidenceDimensions:
    source_world: tuple[SourceWorldProvenance, ...]
    generation: GenerationMechanism
    physical_playback: PhysicalPlaybackEvidence


@dataclass(frozen=True, slots=True)
class GovernedModelDispatch:
    request: ModelRequest
    response: ModelResponse
    access_receipts: tuple[GovernanceAdmissionReceipt[InformationAccessDecision], ...]
    disclosure_receipts: tuple[GovernanceAdmissionReceipt[DisclosureDecision], ...]
    evidence: EvidenceDimensions


@dataclass(slots=True)
class CapturingModelProvider:
    """No-network provider boundary that records the exact transmitted request."""

    name: str = PROVIDER_ID
    model: str = "mock-g2-model"
    capabilities: ModelCapabilities = field(
        default_factory=lambda: ModelCapabilities(
            structured_output=False,
            privacy_class="mock-remote",
        )
    )
    requests: list[ModelRequest] = field(default_factory=list)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            provider=self.name,
            model=self.model,
            text="Fictional rehearsal: keep the experiment conditional on capacity confirmation.",
            response_id="mock-response:g2-live-prep",
            finish_reason="completed",
            usage=ModelUsage(input_tokens=64, output_tokens=12, total_tokens=76),
            metadata={"generation_mechanism": GenerationMechanism.MOCKED_PROVIDER_BOUNDARY},
        )


def _content_key(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def derive_content_ref(
    deriver: HmacOpaqueInformationIdDeriver,
    *,
    namespace: str,
    content: str,
) -> GovernedInformationRef:
    """Bind an opaque example reference to the exact UTF-8 content."""

    return GovernedInformationRef.create(
        namespace=namespace,
        stable_key=_content_key(content),
        deriver=deriver,
    )


async def record_fictional_material(
    kernel: NoemaKernel,
    deriver: HmacOpaqueInformationIdDeriver,
    *,
    recorded_at: datetime = FIXTURE_TIME,
    allowed_secondary_uses: tuple[InformationOperation, ...] = (),
) -> GovernedContextMaterial:
    """Record fictional source, redacted view lineage, policy, and binding."""

    source_content = (
        "FICTIONAL Project Meridian source. Ava proposed a bounded experiment. "
        "Capacity remains unconfirmed; reservation expires Friday. "
        "Internal drafting note: omit this sentence from provider context."
    )
    admitted_content = json.dumps(
        {
            "fictional": True,
            "meeting_objective": "Decide whether to reserve a bounded experiment slot.",
            "conditional_agreement": "Proceed only if capacity is confirmed.",
            "unresolved_fact": "Capacity owner has not confirmed availability.",
            "reservation_deadline": "Friday 17:00 UTC",
            "fictional_owner": "Ava Example",
            "alternative": "Defer the reservation and retain the current process.",
            "counterexample": "If capacity is unavailable, reservation is not recommended.",
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    source_ref = derive_content_ref(
        deriver,
        namespace="g2-live-prep-source",
        content=source_content,
    )
    namespace = "g2-live-prep-redacted-view"
    transmitted_ref = derive_content_ref(
        deriver,
        namespace=namespace,
        content=admitted_content,
    )
    policy = InformationPolicy.create(
        version=1,
        origin_domains=(SourceWorldProvenance.FICTIONAL.value,),
        classification=Classification.CONFIDENTIAL,
        allowed_purposes=(PURPOSE,),
        allowed_recipients=(AUTHORIZED_ROLE, PROVIDER_RECIPIENT),
        allowed_trust_domains=(SOURCE_DOMAIN, DESTINATION_DOMAIN),
        allowed_localities=("local",),
        allowed_providers=(PROVIDER_ID,),
        cross_agent_sharing=False,
        retention=RetentionPolicy(),
        disclosure_forms=(DisclosureForm.REDACTED,),
        declassification_authorities=(),
        recorded_at=recorded_at,
        allowed_secondary_uses=allowed_secondary_uses,
    )
    source_lineage = InformationLineage.create(
        information_id=source_ref.information_id,
        source_information_ids=(),
        transformation=LineageTransformation.SOURCE,
        recorded_at=recorded_at,
    )
    source_binding = PolicyBinding.create(
        information_id=source_ref.information_id,
        lineage_id=source_lineage.lineage_id,
        policy_ids=(policy.policy_id,),
        bound_at=recorded_at,
    )
    view_lineage = InformationLineage.create(
        information_id=transmitted_ref.information_id,
        source_information_ids=(source_ref.information_id,),
        transformation=LineageTransformation.REDACTION,
        recorded_at=recorded_at,
    )
    view_binding = PolicyBinding.create(
        information_id=transmitted_ref.information_id,
        lineage_id=view_lineage.lineage_id,
        policy_ids=(policy.policy_id,),
        bound_at=recorded_at,
    )
    for event in (
        policy.to_event(source="example:g2-live-prep"),
        source_lineage.to_event(source="example:g2-live-prep"),
        source_binding.to_event(source="example:g2-live-prep"),
        view_lineage.to_event(source="example:g2-live-prep"),
        view_binding.to_event(source="example:g2-live-prep"),
    ):
        await kernel.emit(event)
    return GovernedContextMaterial(
        information_ref=transmitted_ref,
        source_information_ref=source_ref,
        namespace=namespace,
        message=ModelMessage("user", admitted_content),
        disclosure_form=DisclosureForm.REDACTED,
        source_provenance=SourceWorldProvenance.FICTIONAL,
    )


def principal_snapshot(
    *,
    captured_at: datetime,
    has_live_prep_role: bool,
) -> PrincipalSnapshot:
    """Build a fixture snapshot from external role state; do not authenticate here."""

    return PrincipalSnapshot.create(
        principal_id="principal:fictional-user",
        roles=(AUTHORIZED_ROLE,) if has_live_prep_role else (),
        groups=(),
        trust_domains=(SOURCE_DOMAIN,),
        captured_at=captured_at,
    )


def _require_material_binding(
    material: GovernedContextMaterial,
    deriver: HmacOpaqueInformationIdDeriver,
) -> None:
    expected = derive_content_ref(
        deriver,
        namespace=material.namespace,
        content=material.message.content,
    )
    if expected != material.information_ref:
        raise PermissionError("transmitted content does not derive the governed information ref")


def _require_canonical_material(
    material: GovernedContextMaterial,
    projection: InformationGovernanceProjection,
    engine: InformationGovernanceEngine,
) -> None:
    lineage = projection.lineage(material.information_ref.information_id)
    if (
        lineage is None
        or lineage.transformation is not LineageTransformation.REDACTION
        or lineage.source_information_ids
        != (material.source_information_ref.information_id,)
        or material.disclosure_form is not DisclosureForm.REDACTED
    ):
        raise PermissionError("material does not resolve to its canonical redacted lineage")
    composition = engine.composition_for(material.information_ref)
    if material.source_provenance.value not in composition.origin_domains:
        raise PermissionError("source-world provenance differs from canonical policy lineage")


def _require_admitted_target(
    access: InformationAccessDecision,
    disclosure: DisclosureDecision,
    *,
    information_ref: GovernedInformationRef,
    disclosure_form: DisclosureForm,
    target: ProviderTarget,
) -> None:
    contexts = (access.request.context, disclosure.request.context)
    if not access.allowed or not disclosure.allowed:
        raise PermissionError("model context requires allowed access and disclosure")
    for context in contexts:
        if (
            context.provider_id != target.provider_id
            or context.destination_trust_domain != target.destination_trust_domain
            or context.recipient != target.recipient
            or context.purpose != target.purpose
            or context.locality != target.locality
            or context.disclosure_form is not disclosure_form
        ):
            raise PermissionError("admission does not match the actual provider-bound use")
    if (
        access.request.information_ref != information_ref
        or disclosure.request.information_ref != information_ref
    ):
        raise PermissionError("admission refers to different information")


async def dispatch_governed_context(
    *,
    kernel: NoemaKernel,
    projection: InformationGovernanceProjection,
    provider: ModelProvider,
    deriver: HmacOpaqueInformationIdDeriver,
    materials: Sequence[GovernedContextMaterial],
    principal: PrincipalSnapshot,
    target: ProviderTarget,
    decision_time: datetime,
    correlation_id: str,
    generation_mechanism: GenerationMechanism,
) -> GovernedModelDispatch:
    """Admit every context item, re-resolve it, then call the exact mock provider."""

    if not materials:
        raise ValueError("governed provider dispatch requires context material")
    if provider.name != target.provider_id:
        raise PermissionError("selected provider differs from the governed target")
    admission = InformationGovernanceAdmission(
        kernel,
        projection,
        source="example:g2-live-prep",
    )
    access_receipts: list[GovernanceAdmissionReceipt[InformationAccessDecision]] = []
    disclosure_receipts: list[GovernanceAdmissionReceipt[DisclosureDecision]] = []
    for material in materials:
        _require_material_binding(material, deriver)
        projection.rebuild(await kernel.history())
        engine = InformationGovernanceEngine(projection)
        _require_canonical_material(material, projection, engine)
        context = engine.context_for(
            information_ref=material.information_ref,
            actor_id="agent:fictional-companion",
            principal=principal,
            purpose=target.purpose,
            operation=InformationOperation.MODEL_CONTEXT,
            source_trust_domain=SOURCE_DOMAIN,
            destination_trust_domain=target.destination_trust_domain,
            recipient=target.recipient,
            decision_time=decision_time,
            locality=target.locality,
            provider_id=target.provider_id,
            provider_security_posture=("no-training", "no-storage"),
            disclosure_form=material.disclosure_form,
        )
        access = await admission.admit_access(
            InformationAccessRequest.create(
                information_ref=material.information_ref,
                context=context,
            )
        )
        access_receipts.append(access)
        if access.record.policy_decision.disposition is not DecisionDisposition.ALLOW:
            raise PermissionError("current access admission denied model context")
        disclosure = await admission.admit_disclosure(
            DisclosureRequest.create(
                information_ref=material.information_ref,
                context=context,
            )
        )
        disclosure_receipts.append(disclosure)
        if disclosure.record.policy_decision.disposition is not DecisionDisposition.ALLOW:
            raise PermissionError("current disclosure admission denied model context")

    projection.rebuild(await kernel.history())
    for material, access, disclosure in zip(
        materials,
        access_receipts,
        disclosure_receipts,
        strict=True,
    ):
        resolved_access = projection.access_decision(access.record.decision_id)
        resolved_disclosure = projection.disclosure_decision(disclosure.record.decision_id)
        if resolved_access != access.record or resolved_disclosure != disclosure.record:
            raise PermissionError("provider dispatch requires resolved canonical admissions")
        _require_admitted_target(
            access.record,
            disclosure.record,
            information_ref=material.information_ref,
            disclosure_form=material.disclosure_form,
            target=target,
        )

    last_sequence = disclosure_receipts[-1].canonical_sequence
    history = await kernel.history()
    if not history or history[-1].sequence != last_sequence:
        raise PermissionError("canonical state changed after provider-use admission")
    request = ModelRequest(
        messages=tuple(material.message for material in materials),
        correlation_id=correlation_id,
        metadata={
            "purpose": target.purpose,
            "provider_id": target.provider_id,
            "destination_trust_domain": target.destination_trust_domain,
            "information_refs": [
                material.information_ref.information_id for material in materials
            ],
            "content_sha256": [material.content_sha256 for material in materials],
            "access_decision_ids": [receipt.record.decision_id for receipt in access_receipts],
            "disclosure_decision_ids": [
                receipt.record.decision_id for receipt in disclosure_receipts
            ],
        },
    )
    response = await provider.generate(request)
    if response.provider != target.provider_id:
        raise ValueError("model response identifies a different provider")
    return GovernedModelDispatch(
        request=request,
        response=response,
        access_receipts=tuple(access_receipts),
        disclosure_receipts=tuple(disclosure_receipts),
        evidence=EvidenceDimensions(
            source_world=tuple(material.source_provenance for material in materials),
            generation=generation_mechanism,
            physical_playback=PhysicalPlaybackEvidence.NOT_RUN,
        ),
    )


async def _run() -> dict[str, object]:
    kernel = NoemaKernel()
    await kernel.start()
    try:
        deriver = HmacOpaqueInformationIdDeriver(
            b"fictional-g2-key-material-32-byte"
        )
        material = await record_fictional_material(kernel, deriver)
        projection = InformationGovernanceProjection()
        provider = CapturingModelProvider()
        dispatch = await dispatch_governed_context(
            kernel=kernel,
            projection=projection,
            provider=provider,
            deriver=deriver,
            materials=(material,),
            principal=principal_snapshot(
                captured_at=FIXTURE_TIME,
                has_live_prep_role=True,
            ),
            target=ProviderTarget(
                provider_id=PROVIDER_ID,
                destination_trust_domain=DESTINATION_DOMAIN,
                recipient=PROVIDER_RECIPIENT,
                purpose=PURPOSE,
            ),
            decision_time=FIXTURE_TIME + timedelta(minutes=1),
            correlation_id="g2-fictional-live-prep",
            generation_mechanism=GenerationMechanism.MOCKED_PROVIDER_BOUNDARY,
        )
        return {
            "provider_calls": len(provider.requests),
            "information_ref": material.information_ref.information_id,
            "content_sha256": material.content_sha256,
            "source_world": [value.value for value in dispatch.evidence.source_world],
            "generation": dispatch.evidence.generation.value,
            "physical_playback": dispatch.evidence.physical_playback.value,
            "access_allowed": all(value.record.allowed for value in dispatch.access_receipts),
            "disclosure_allowed": all(
                value.record.allowed for value in dispatch.disclosure_receipts
            ),
        }
    finally:
        await kernel.stop()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(_run()), indent=2, sort_keys=True))
