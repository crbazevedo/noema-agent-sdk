"""Admission and crash-recoverable observation for actual attention decisions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from ..checkpoints import ConsumerCheckpoint, ConsumerCheckpointProjection
from ..events import Event
from ..information import (
    DecisionDisposition,
    GovernedInformationRef,
    InformationAccessRequest,
    InformationGovernanceAdmission,
    InformationGovernanceEngine,
    InformationLineage,
    InformationOperation,
    LineageTransformation,
    OpaqueInformationIdDeriver,
    PolicyBinding,
    PrincipalSnapshot,
    StaleGovernanceDecisionError,
)
from ..kernel import NoemaKernel
from ..store import ConcurrentAppendError
from ..types import JSONValue
from .models import (
    AttentionDispositionDecision,
    AttentionDispositionFeedbackRecord,
    AttentionDispositionOutcomeLink,
    AttentionDispositionRecord,
    AttentionFeatureSchemaSnapshot,
    AttentionFeedback,
    AttentionOutcome,
    AttentionSourcePolicySnapshot,
)
from .projection import AttentionExposureProjection


class AttentionSemanticConflictError(RuntimeError):
    """Two incompatible observations claimed the same semantic opportunity."""


@dataclass(frozen=True, slots=True)
class AttentionTelemetryContext:
    principal: PrincipalSnapshot
    actor_id: str
    purpose: str
    source_trust_domain: str
    locality: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.actor_id, "attention telemetry actor id"),
            (self.purpose, "attention telemetry purpose"),
            (self.source_trust_domain, "attention telemetry trust domain"),
            (self.locality, "attention telemetry locality"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True, slots=True)
class AttentionOpportunity:
    """Transient provider input; the canonical denominator stays event-derived."""

    source_event: Event
    source_policy: AttentionSourcePolicySnapshot
    feature_schema: AttentionFeatureSchemaSnapshot


class AttentionDispositionProvider(Protocol):
    """Application boundary that supplies—not infers—the actual disposition."""

    async def decide(
        self, opportunity: AttentionOpportunity
    ) -> AttentionDispositionDecision: ...


AfterDispositionHook = Callable[[AttentionDispositionRecord], Awaitable[None]]


class DeliberativeAttentionRecorder:
    """Record policy-safe observations against exact canonical state."""

    def __init__(
        self,
        kernel: NoemaKernel,
        *,
        derived_information_id_deriver: OpaqueInformationIdDeriver,
        source: str = "attention:telemetry",
    ) -> None:
        if not source.strip():
            raise ValueError("attention telemetry source must be non-empty")
        self.kernel = kernel
        self.derived_information_id_deriver = derived_information_id_deriver
        self.source = source

    async def register_contracts(
        self,
        *,
        feature_schema: AttentionFeatureSchemaSnapshot,
        source_policy: AttentionSourcePolicySnapshot,
    ) -> None:
        if source_policy.feature_schema_id != feature_schema.schema_id:
            raise ValueError("attention source policy and feature schema do not match")
        for event in (
            feature_schema.to_event(source=self.source),
            source_policy.to_event(source=self.source),
        ):
            stored = await self.kernel.emit(event)
            if replace(stored, sequence=None) != event:
                raise AttentionSemanticConflictError(
                    f"canonical event id conflicts with attention contract: {event.id}"
                )

    async def current_projection(self) -> AttentionExposureProjection:
        projection = AttentionExposureProjection()
        projection.rebuild(await self._normalized_history())
        return projection

    async def record_disposition(
        self,
        *,
        source_event_id: str,
        source_policy_id: str,
        decision: AttentionDispositionDecision,
        telemetry_context: AttentionTelemetryContext,
    ) -> AttentionDispositionRecord:
        projection = await self.current_projection()
        policy = projection.policy(source_policy_id)
        if policy is None:
            raise ValueError("attention disposition references an unknown source policy")
        existing = projection.disposition_for(
            source_event_id=source_event_id,
            source_policy_id=source_policy_id,
            feature_schema_id=policy.feature_schema_id,
        )
        if existing is not None:
            return self._reuse_disposition(existing, decision)
        source_ref = projection.event_reference(source_event_id)
        policy_sequence = projection.policy_sequence(source_policy_id)
        if source_ref is None or policy_sequence is None:
            raise ValueError("attention disposition source is not canonical")
        _, source_sequence, _ = source_ref
        if projection.recognized_opportunity(
            source_event_id=source_event_id,
            source_policy_id=source_policy_id,
            feature_schema_id=policy.feature_schema_id,
        ) is None:
            raise ValueError("attention source is not a recognized opportunity")
        schema = projection.schema(policy.feature_schema_id)
        if schema is None:
            raise ValueError("attention disposition feature schema is not canonical")
        schema.validate_snapshot(decision.features)
        derived_information_id = self._derived_information_id(
            namespace="attention-disposition",
            stable_key=f"{source_event_id}:{source_policy_id}:{policy.feature_schema_id}",
        )
        policy_ids = await self._ensure_derived_governance(
            information_id=derived_information_id,
            source_information_ids=decision.governed_information_ids,
            recorded_at=decision.decided_at,
        )
        access_decision_id = await self._admit_telemetry_access(
            information_id=derived_information_id,
            context=telemetry_context,
            at=decision.decided_at,
        )

        while True:
            projection = await self.current_projection()
            existing = projection.disposition_for(
                source_event_id=source_event_id,
                source_policy_id=source_policy_id,
                feature_schema_id=policy.feature_schema_id,
            )
            if existing is not None:
                return self._reuse_disposition(existing, decision)
            candidate = AttentionDispositionRecord.create(
                source_event_id=source_event_id,
                source_event_sequence=source_sequence,
                source_policy_id=source_policy_id,
                feature_schema_id=policy.feature_schema_id,
                decision=decision,
                derived_information_id=derived_information_id,
                information_policy_ids=policy_ids,
                information_access_decision_ids=(access_decision_id,),
                admitted_predecessor_head=projection.event_cursor,
            )
            try:
                return AttentionDispositionRecord.from_event(
                    await self._append_exact(candidate.to_event(source=self.source), projection)
                )
            except ConcurrentAppendError:
                continue

    async def link_outcome(
        self,
        *,
        disposition_id: str,
        outcome_event_id: str,
        outcome: AttentionOutcome,
        observed_at: datetime,
        recorded_at: datetime,
        governed_information_ids: tuple[str, ...],
        telemetry_context: AttentionTelemetryContext,
    ) -> AttentionDispositionOutcomeLink:
        projection = await self.current_projection()
        disposition = projection.disposition(disposition_id)
        if disposition is None:
            raise ValueError("attention outcome references an unknown disposition")
        existing = projection.outcome_for(disposition_id)
        if existing is not None:
            if (
                existing.outcome_event_id != outcome_event_id
                or existing.outcome is not outcome
                or existing.observed_at != observed_at
                or existing.recorded_at != recorded_at
            ):
                raise AttentionSemanticConflictError(
                    "conflicting outcomes for one attention disposition"
                )
            return existing
        sources = tuple(
            sorted({disposition.derived_information_id, *governed_information_ids})
        )
        derived_information_id = self._derived_information_id(
            namespace="attention-outcome",
            stable_key=disposition_id,
        )
        policy_ids = await self._ensure_derived_governance(
            information_id=derived_information_id,
            source_information_ids=sources,
            recorded_at=recorded_at,
        )
        access_decision_id = await self._admit_telemetry_access(
            information_id=derived_information_id,
            context=telemetry_context,
            at=recorded_at,
        )
        while True:
            projection = await self.current_projection()
            existing = projection.outcome_for(disposition_id)
            if existing is not None:
                if (
                    existing.outcome_event_id != outcome_event_id
                    or existing.outcome is not outcome
                    or existing.observed_at != observed_at
                    or existing.recorded_at != recorded_at
                ):
                    raise AttentionSemanticConflictError(
                        "conflicting outcomes for one attention disposition"
                    )
                return existing
            candidate = AttentionDispositionOutcomeLink.create(
                disposition_id=disposition_id,
                outcome_event_id=outcome_event_id,
                outcome=outcome,
                observed_at=observed_at,
                recorded_at=recorded_at,
                governed_information_ids=sources,
                derived_information_id=derived_information_id,
                information_policy_ids=policy_ids,
                information_access_decision_ids=(access_decision_id,),
                admitted_predecessor_head=projection.event_cursor,
            )
            try:
                return AttentionDispositionOutcomeLink.from_event(
                    await self._append_exact(candidate.to_event(source=self.source), projection)
                )
            except ConcurrentAppendError:
                continue

    async def record_feedback(
        self,
        *,
        disposition_id: str,
        feedback_event_id: str,
        feedback: AttentionFeedback,
        actor_id: str,
        actor_provenance_ref: str,
        recorded_at: datetime,
        governed_information_ids: tuple[str, ...],
        telemetry_context: AttentionTelemetryContext,
    ) -> AttentionDispositionFeedbackRecord:
        projection = await self.current_projection()
        disposition = projection.disposition(disposition_id)
        if disposition is None:
            raise ValueError("attention feedback references an unknown disposition")
        existing_feedback = next(
            (
                value
                for value in projection.feedback_for(disposition_id)
                if value.feedback_event_id == feedback_event_id
                and value.feedback is feedback
                and value.actor_id == actor_id
                and value.actor_provenance_ref == actor_provenance_ref
            ),
            None,
        )
        if existing_feedback is not None:
            if existing_feedback.recorded_at != recorded_at:
                raise AttentionSemanticConflictError(
                    "conflicting attention feedback record time"
                )
            return existing_feedback
        sources = tuple(
            sorted({disposition.derived_information_id, *governed_information_ids})
        )
        stable_key = ":".join(
            (
                disposition_id,
                feedback_event_id,
                feedback.value,
                actor_id,
                actor_provenance_ref,
            )
        )
        derived_information_id = self._derived_information_id(
            namespace="attention-feedback",
            stable_key=stable_key,
        )
        policy_ids = await self._ensure_derived_governance(
            information_id=derived_information_id,
            source_information_ids=sources,
            recorded_at=recorded_at,
        )
        access_decision_id = await self._admit_telemetry_access(
            information_id=derived_information_id,
            context=telemetry_context,
            at=recorded_at,
        )
        while True:
            projection = await self.current_projection()
            candidate = AttentionDispositionFeedbackRecord.create(
                disposition_id=disposition_id,
                feedback_event_id=feedback_event_id,
                feedback=feedback,
                actor_id=actor_id,
                actor_provenance_ref=actor_provenance_ref,
                recorded_at=recorded_at,
                governed_information_ids=sources,
                derived_information_id=derived_information_id,
                information_policy_ids=policy_ids,
                information_access_decision_ids=(access_decision_id,),
                admitted_predecessor_head=projection.event_cursor,
            )
            existing = next(
                (
                    value
                    for value in projection.feedback_for(disposition_id)
                    if value.feedback_id == candidate.feedback_id
                ),
                None,
            )
            if existing is not None:
                if (
                    existing.feedback is not feedback
                    or existing.feedback_event_id != feedback_event_id
                    or existing.actor_id != actor_id
                    or existing.actor_provenance_ref != actor_provenance_ref
                    or existing.recorded_at != recorded_at
                ):
                    raise AttentionSemanticConflictError(
                        "conflicting attention feedback identity"
                    )
                return existing
            try:
                return AttentionDispositionFeedbackRecord.from_event(
                    await self._append_exact(candidate.to_event(source=self.source), projection)
                )
            except ConcurrentAppendError:
                continue

    async def _append_exact(
        self,
        event: Event,
        projection: AttentionExposureProjection,
    ) -> Event:
        metadata: dict[str, JSONValue] = dict(event.metadata)
        metadata["validated_at_event_cursor"] = projection.event_cursor
        admitted = replace(event, metadata=metadata)
        history = await self._normalized_history()
        actual_head = max((item.sequence or 0 for item in history), default=0)
        if actual_head != projection.event_cursor:
            raise ConcurrentAppendError(
                expected_head_sequence=projection.event_cursor,
                actual_head_sequence=actual_head,
            )
        probe = AttentionExposureProjection()
        probe.rebuild(history)
        probe.apply(admitted.with_sequence(projection.event_cursor + 1))
        stored = await self.kernel.emit_if_head(
            admitted,
            expected_head_sequence=projection.event_cursor,
        )
        if replace(stored, sequence=None) != admitted:
            raise AttentionSemanticConflictError(
                f"canonical event id conflicts with attention observation: {event.id}"
            )
        return stored

    async def _ensure_derived_governance(
        self,
        *,
        information_id: str,
        source_information_ids: tuple[str, ...],
        recorded_at: datetime,
    ) -> tuple[str, ...]:
        sources = tuple(sorted(set(source_information_ids)))
        if not sources:
            raise ValueError("attention derived information requires source lineage")
        while True:
            projection = await self.current_projection()
            lineage = projection.information.lineage(information_id)
            if lineage is not None:
                if (
                    lineage.source_information_ids != sources
                    or lineage.transformation is not LineageTransformation.DERIVATION
                ):
                    raise AttentionSemanticConflictError(
                        "attention derived-information lineage changed in place"
                    )
                break
            for source_id in sources:
                if projection.information.lineage(source_id) is None:
                    raise ValueError("attention source information lacks canonical lineage")
            proposed = InformationLineage.create(
                information_id=information_id,
                source_information_ids=sources,
                transformation=LineageTransformation.DERIVATION,
                recorded_at=recorded_at,
            )
            event = proposed.to_event(source=self.source)
            try:
                await self.kernel.emit_if_head(
                    replace(
                        event,
                        metadata={"validated_at_event_cursor": projection.event_cursor},
                    ),
                    expected_head_sequence=projection.event_cursor,
                )
            except ConcurrentAppendError:
                continue

        projection = await self.current_projection()
        source_policy_ids: set[str] = set()
        engine = InformationGovernanceEngine(projection.information)
        for source_id in sources:
            composition = engine.composition_for(GovernedInformationRef(source_id))
            if composition.conflicts_for(InformationOperation.TELEMETRY):
                raise PermissionError("attention source policy conflicts prohibit telemetry")
            source_policy_ids.update(composition.source_policy_ids)
        policies = tuple(sorted(source_policy_ids))
        if not policies:
            raise ValueError("attention derived information lacks source policies")
        while True:
            projection = await self.current_projection()
            binding = projection.information.binding(information_id)
            if binding is not None:
                if binding.lineage_id != lineage.lineage_id or binding.policy_ids != policies:
                    raise AttentionSemanticConflictError(
                        "attention derived-information policy binding changed in place"
                    )
                return policies
            proposed_binding = PolicyBinding.create(
                information_id=information_id,
                lineage_id=lineage.lineage_id,
                policy_ids=policies,
                bound_at=recorded_at,
            )
            event = proposed_binding.to_event(source=self.source)
            try:
                await self.kernel.emit_if_head(
                    replace(
                        event,
                        metadata={"validated_at_event_cursor": projection.event_cursor},
                    ),
                    expected_head_sequence=projection.event_cursor,
                )
            except ConcurrentAppendError:
                continue

    async def _admit_telemetry_access(
        self,
        *,
        information_id: str,
        context: AttentionTelemetryContext,
        at: datetime,
    ) -> str:
        while True:
            projection = await self.current_projection()
            engine = InformationGovernanceEngine(projection.information)
            information_ref = GovernedInformationRef(information_id)
            request = InformationAccessRequest.create(
                information_ref=information_ref,
                context=engine.context_for(
                    information_ref=information_ref,
                    actor_id=context.actor_id,
                    principal=context.principal,
                    purpose=context.purpose,
                    operation=InformationOperation.TELEMETRY,
                    source_trust_domain=context.source_trust_domain,
                    destination_trust_domain=None,
                    recipient=None,
                    decision_time=at,
                    locality=context.locality,
                ),
            )
            try:
                receipt = await InformationGovernanceAdmission(
                    self.kernel,
                    projection.information,
                    source=self.source,
                ).admit_access(
                    request,
                    expected_disposition=DecisionDisposition.ALLOW,
                    expected_causal_cursor=projection.event_cursor,
                )
                return receipt.record.decision_id
            except ConcurrentAppendError:
                continue
            except StaleGovernanceDecisionError:
                # A head race is retryable; a stable denial will reproduce and escape below.
                refreshed = await self.current_projection()
                refreshed_engine = InformationGovernanceEngine(refreshed.information)
                refreshed_context = refreshed_engine.context_for(
                    information_ref=information_ref,
                    actor_id=context.actor_id,
                    principal=context.principal,
                    purpose=context.purpose,
                    operation=InformationOperation.TELEMETRY,
                    source_trust_domain=context.source_trust_domain,
                    destination_trust_domain=None,
                    recipient=None,
                    decision_time=at,
                    locality=context.locality,
                )
                denied = refreshed_engine.decide_access(
                    InformationAccessRequest.create(
                        information_ref=information_ref,
                        context=refreshed_context,
                    )
                )
                if denied.policy_decision.disposition is DecisionDisposition.DENY:
                    raise PermissionError(
                        "information policy denies attention telemetry"
                    ) from None
                continue

    def _derived_information_id(self, *, namespace: str, stable_key: str) -> str:
        return self.derived_information_id_deriver.derive(
            namespace=namespace,
            stable_key=stable_key,
        )

    @staticmethod
    def _reuse_disposition(
        existing: AttentionDispositionRecord,
        decision: AttentionDispositionDecision,
    ) -> AttentionDispositionRecord:
        if existing.decision != decision:
            raise AttentionSemanticConflictError(
                "conflicting actual dispositions for one attention opportunity"
            )
        return existing

    async def _normalized_history(self) -> list[Event]:
        return [self.kernel.schemas.normalize(event) for event in await self.kernel.history()]


class DeliberativeAttentionWorker:
    """Observe every policy-recognized source and checkpoint only after durability."""

    def __init__(
        self,
        recorder: DeliberativeAttentionRecorder,
        *,
        feature_schema: AttentionFeatureSchemaSnapshot,
        source_policy: AttentionSourcePolicySnapshot,
        provider: AttentionDispositionProvider,
        telemetry_context: AttentionTelemetryContext,
        consumer_id: str = "deliberative-attention-v1",
        after_disposition: AfterDispositionHook | None = None,
    ) -> None:
        if not consumer_id.strip():
            raise ValueError("attention telemetry consumer id must be non-empty")
        if source_policy.feature_schema_id != feature_schema.schema_id:
            raise ValueError("attention worker policy and feature schema do not match")
        self.recorder = recorder
        self.feature_schema = feature_schema
        self.source_policy = source_policy
        self.provider = provider
        self.telemetry_context = telemetry_context
        self.consumer_id = consumer_id
        self.after_disposition = after_disposition

    async def register_contracts(self) -> None:
        await self.recorder.register_contracts(
            feature_schema=self.feature_schema,
            source_policy=self.source_policy,
        )

    async def process_available(self) -> tuple[AttentionDispositionRecord, ...]:
        await self.register_contracts()
        history = await self.recorder._normalized_history()
        projection = AttentionExposureProjection()
        projection.rebuild(history)
        policy_sequence = projection.policy_sequence(self.source_policy.policy_id)
        if policy_sequence is None:
            raise ValueError("attention source policy did not become canonical")
        checkpoints = ConsumerCheckpointProjection()
        checkpoints.rebuild(history)
        current = checkpoints.get(self.consumer_id)
        completed = current.last_completed_sequence if current is not None else 0
        records: list[AttentionDispositionRecord] = []
        pending_checkpoint: Event | None = None
        for event in history:
            if event.sequence is None or event.sequence <= completed:
                continue
            pending_checkpoint = event
            if not self.source_policy.recognizes(
                event, activated_at_sequence=policy_sequence
            ):
                continue
            existing = projection.disposition_for(
                source_event_id=event.id,
                source_policy_id=self.source_policy.policy_id,
                feature_schema_id=self.feature_schema.schema_id,
            )
            if existing is None:
                decision = await self.provider.decide(
                    AttentionOpportunity(
                        source_event=event,
                        source_policy=self.source_policy,
                        feature_schema=self.feature_schema,
                    )
                )
                existing = await self.recorder.record_disposition(
                    source_event_id=event.id,
                    source_policy_id=self.source_policy.policy_id,
                    decision=decision,
                    telemetry_context=self.telemetry_context,
                )
                if self.after_disposition is not None:
                    await self.after_disposition(existing)
            records.append(existing)
            await self._advance_checkpoint(event, epoch_id=existing.disposition_id)
            completed = event.sequence
            pending_checkpoint = None
            projection = await self.recorder.current_projection()
        if pending_checkpoint is not None:
            await self._advance_checkpoint(pending_checkpoint, epoch_id=None)
        return tuple(records)

    async def _advance_checkpoint(
        self,
        completed_event: Event,
        *,
        epoch_id: str | None,
    ) -> ConsumerCheckpoint:
        if completed_event.sequence is None:
            raise ValueError("attention checkpoint requires a canonical input")
        while True:
            history = await self.recorder._normalized_history()
            checkpoints = ConsumerCheckpointProjection()
            checkpoints.rebuild(history)
            current = checkpoints.get(self.consumer_id)
            if current is not None and current.last_completed_sequence >= completed_event.sequence:
                return current
            observed_head = max(
                (event.sequence or 0 for event in history),
                default=completed_event.sequence,
            )
            checkpoint = ConsumerCheckpoint(
                consumer_id=self.consumer_id,
                last_completed_sequence=completed_event.sequence,
                observed_head_sequence=observed_head,
                epoch_id=epoch_id,
            )
            event = checkpoint.to_event(
                source=self.recorder.source,
                timestamp=completed_event.timestamp,
                causation_id=completed_event.id,
            )
            try:
                stored = await self.recorder.kernel.emit_if_head(
                    event,
                    expected_head_sequence=observed_head,
                )
                return ConsumerCheckpoint.from_event(stored)
            except ConcurrentAppendError:
                continue
