from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from noema import (
    AttentionAuthorityCeiling,
    AttentionCostSnapshot,
    AttentionDisposition,
    AttentionDispositionDecision,
    AttentionExposureProjection,
    AttentionFeatureDefinition,
    AttentionFeatureSchemaSnapshot,
    AttentionFeatureType,
    AttentionFeedback,
    AttentionOpportunity,
    AttentionOutcome,
    AttentionSemanticConflictError,
    AttentionSourcePolicySnapshot,
    AttentionTelemetryContext,
    Classification,
    ConsumerCheckpointProjection,
    DeliberativeAttentionRecorder,
    DeliberativeAttentionWorker,
    DisclosureForm,
    Event,
    FeatureMissingness,
    GovernedInformationRef,
    HmacOpaqueInformationIdDeriver,
    InformationLineage,
    InformationOperation,
    InformationPolicy,
    LineageTransformation,
    NoemaKernel,
    PolicyBinding,
    PrincipalSnapshot,
    RetentionPolicy,
)

START = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
ID_DERIVER = HmacOpaqueInformationIdDeriver(
    b"0123456789abcdef0123456789abcdef"
)
PROTECTED_TEXT = "private message body that must never enter attention telemetry"


class _FixtureDispositionProvider:
    def __init__(self, information_id: str) -> None:
        self.information_id = information_id
        self.calls: list[str] = []
        self.fail_once_for: str | None = None

    async def decide(
        self, opportunity: AttentionOpportunity
    ) -> AttentionDispositionDecision:
        event = opportunity.source_event
        self.calls.append(event.id)
        if self.fail_once_for == event.id:
            self.fail_once_for = None
            raise RuntimeError("synthetic provider interruption")
        features = {
            name: event.payload[name]
            for name in ("deep_work", "requires_user_decision", "urgency")
            if name in event.payload
        }
        assert event.sequence is not None
        return AttentionDispositionDecision(
            disposition=AttentionDisposition(str(event.payload["actual_disposition"])),
            features=features,
            situation_causal_cursor=event.sequence,
            decision_mechanism_id="fixture-baseline-adviser",
            decision_mechanism_version="1",
            decision_configuration_ref="fixture-config:v1",
            decision_refs=("intent-current",),
            governing_intent_refs=("intent-current",),
            authority_ceiling=AttentionAuthorityCeiling.INTERNAL_ATTENTION_ONLY,
            governed_information_ids=(self.information_id,),
            valid_at=event.timestamp,
            known_at=event.timestamp,
            decided_at=event.timestamp,
            costs=AttentionCostSnapshot(
                model_call_count=None,
                input_tokens=None,
                output_tokens=None,
                wall_time_seconds=0.02,
                human_attention_units=0.0,
                deliberative_compute_units=1.0,
            ),
        )


class DeliberativeAttentionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.kernel = NoemaKernel()
        await self.kernel.start()
        self.information_ref = GovernedInformationRef.create(
            namespace="attention-test",
            stable_key="policy-safe-source",
            deriver=ID_DERIVER,
        )
        self.policy = InformationPolicy.create(
            version=2,
            origin_domains=("user-owned",),
            classification=Classification.CONFIDENTIAL,
            allowed_purposes=("attention-telemetry",),
            allowed_recipients=("companion",),
            allowed_trust_domains=("local",),
            allowed_localities=("local",),
            allowed_providers=(),
            cross_agent_sharing=False,
            retention=RetentionPolicy(),
            disclosure_forms=(DisclosureForm.REDACTED,),
            declassification_authorities=(),
            recorded_at=START,
            allowed_secondary_uses=(
                InformationOperation.LEARN,
                InformationOperation.EVALUATE,
            ),
        )
        lineage = InformationLineage.create(
            information_id=self.information_ref.information_id,
            source_information_ids=(),
            transformation=LineageTransformation.SOURCE,
            recorded_at=START,
        )
        binding = PolicyBinding.create(
            information_id=self.information_ref.information_id,
            lineage_id=lineage.lineage_id,
            policy_ids=(self.policy.policy_id,),
            bound_at=START,
        )
        await self.kernel.emit_many(
            (
                self.policy.to_event(source="test:governance"),
                lineage.to_event(source="test:governance"),
                binding.to_event(source="test:governance"),
            )
        )
        self.schema = AttentionFeatureSchemaSnapshot.create(
            version="deep-work-v1",
            features=(
                AttentionFeatureDefinition(
                    name="deep_work",
                    value_type=AttentionFeatureType.BOOLEAN,
                    required=True,
                    policy_safe=True,
                    missingness=FeatureMissingness.REQUIRED_EXPOSURE_INCOMPLETE,
                ),
                AttentionFeatureDefinition(
                    name="requires_user_decision",
                    value_type=AttentionFeatureType.BOOLEAN,
                    required=True,
                    policy_safe=True,
                    missingness=FeatureMissingness.REQUIRED_EXPOSURE_INCOMPLETE,
                ),
                AttentionFeatureDefinition(
                    name="urgency",
                    value_type=AttentionFeatureType.NUMBER,
                    required=True,
                    policy_safe=True,
                    missingness=FeatureMissingness.REQUIRED_EXPOSURE_INCOMPLETE,
                    minimum=0.0,
                    maximum=1.0,
                ),
            ),
            recorded_at=START + timedelta(seconds=1),
        )
        self.source_policy = AttentionSourcePolicySnapshot.create(
            version="companion-attention-v1",
            feature_schema_id=self.schema.schema_id,
            source_event_types=("companion.attention_opportunity",),
            source_prefixes=("companion:",),
            required_payload_fields=("kind",),
            scope="synthetic-companion",
            recorded_at=START + timedelta(seconds=2),
        )
        self.recorder = DeliberativeAttentionRecorder(
            self.kernel,
            derived_information_id_deriver=ID_DERIVER,
        )
        await self.recorder.register_contracts(
            feature_schema=self.schema,
            source_policy=self.source_policy,
        )
        await self.kernel.emit(
            Event(
                id="intent-current",
                type="test.current_intent",
                source="test:intent",
                subject="goal:deep-work",
                timestamp=START + timedelta(seconds=3),
            )
        )
        self.context = AttentionTelemetryContext(
            principal=PrincipalSnapshot.create(
                principal_id="companion",
                roles=(),
                groups=(),
                trust_domains=("local",),
                captured_at=START,
            ),
            actor_id="agent:companion",
            purpose="attention-telemetry",
            source_trust_domain="local",
            locality="local",
        )
        self.provider = _FixtureDispositionProvider(self.information_ref.information_id)

    async def asyncTearDown(self) -> None:
        await self.kernel.stop()

    def _worker(
        self,
        *,
        after_disposition: object | None = None,
        consumer_id: str = "attention-test-worker",
    ) -> DeliberativeAttentionWorker:
        return DeliberativeAttentionWorker(
            self.recorder,
            feature_schema=self.schema,
            source_policy=self.source_policy,
            provider=self.provider,
            telemetry_context=self.context,
            consumer_id=consumer_id,
            after_disposition=after_disposition,  # type: ignore[arg-type]
        )

    async def _opportunity(
        self,
        index: int,
        *,
        disposition: AttentionDisposition,
        include_urgency: bool = True,
    ) -> Event:
        payload: dict[str, object] = {
            "kind": "message",
            "deep_work": index % 2 == 0,
            "requires_user_decision": index % 3 == 0,
            "actual_disposition": disposition.value,
            "protected_text": PROTECTED_TEXT,
        }
        if include_urgency:
            payload["urgency"] = round((index % 10) / 10, 2)
        return await self.kernel.emit(
            Event(
                id=f"attention-source-{index}",
                type="companion.attention_opportunity",
                source="companion:fixture",
                subject=f"opportunity:{index}",
                timestamp=START + timedelta(minutes=index + 1),
                payload=payload,  # type: ignore[arg-type]
            )
        )

    async def test_flagship_denominator_outcomes_feedback_and_replay(self) -> None:
        labels = (
            AttentionDisposition.REMEMBER,
            AttentionDisposition.WAKE,
            AttentionDisposition.DEFER,
            AttentionDisposition.SUPPRESS,
        )
        for index in range(12):
            await self._opportunity(index, disposition=labels[index % len(labels)])

        before = await self.recorder.current_projection()
        before_audit = before.audit(
            source_policy_id=self.source_policy.policy_id,
            feature_schema_id=self.schema.schema_id,
        )
        self.assertEqual(len(before_audit.recognized_opportunities), 12)
        self.assertEqual(len(before_audit.missing_dispositions), 12)
        self.assertFalse(before_audit.denominator_complete)

        records = await self._worker().process_available()
        self.assertEqual(len(records), 12)
        projection = await self.recorder.current_projection()
        audit = projection.audit(
            source_policy_id=self.source_policy.policy_id,
            feature_schema_id=self.schema.schema_id,
        )
        self.assertTrue(audit.denominator_complete)
        self.assertEqual(len(audit.disposition_records), 12)
        self.assertEqual(len(audit.feature_complete_ids), 12)

        outcome_events: list[Event] = []
        outcomes = (
            AttentionOutcome.HANDLED_WITHIN_WINDOW,
            AttentionOutcome.FALSE_WAKE,
            AttentionOutcome.FALSE_SUPPRESSION,
            AttentionOutcome.UNKNOWN,
        )
        for index, outcome in enumerate(outcomes):
            event = await self.kernel.emit(
                Event(
                    id=f"outcome-source-{index}",
                    type="companion.outcome_observed",
                    source="companion:fixture",
                    timestamp=START + timedelta(hours=2, minutes=index),
                )
            )
            outcome_events.append(event)
            await self.recorder.link_outcome(
                disposition_id=records[index].disposition_id,
                outcome_event_id=event.id,
                outcome=outcome,
                observed_at=event.timestamp,
                recorded_at=event.timestamp,
                governed_information_ids=(),
                telemetry_context=self.context,
            )
        feedback_event = await self.kernel.emit(
            Event(
                id="feedback-source-accepted",
                type="companion.explicit_feedback",
                source="companion:user",
                timestamp=START + timedelta(hours=3),
            )
        )
        await self.recorder.record_feedback(
            disposition_id=records[0].disposition_id,
            feedback_event_id=feedback_event.id,
            feedback=AttentionFeedback.ACCEPTED,
            actor_id="user:carlos",
            actor_provenance_ref="session:authenticated-user",
            recorded_at=feedback_event.timestamp,
            governed_information_ids=(),
            telemetry_context=self.context,
        )
        correction_event = await self.kernel.emit(
            Event(
                id="feedback-source-correction",
                type="companion.explicit_feedback",
                source="companion:user",
                timestamp=START + timedelta(hours=3, minutes=1),
            )
        )
        await self.recorder.record_feedback(
            disposition_id=records[1].disposition_id,
            feedback_event_id=correction_event.id,
            feedback=AttentionFeedback.CORRECTED,
            actor_id="user:carlos",
            actor_provenance_ref="session:authenticated-user",
            recorded_at=correction_event.timestamp,
            governed_information_ids=(),
            telemetry_context=self.context,
        )

        final = await self.recorder.current_projection()
        final_audit = final.audit(
            source_policy_id=self.source_policy.policy_id,
            feature_schema_id=self.schema.schema_id,
        )
        self.assertEqual(len(final_audit.outcome_resolved_ids), 3)
        self.assertEqual(len(final_audit.outcome_censored_ids), 9)
        self.assertEqual(
            set(final_audit.feedback_observed_ids),
            {records[0].disposition_id, records[1].disposition_id},
        )
        raw_attention = [
            event.to_dict()
            for event in await self.kernel.history()
            if event.type.startswith("attention.")
        ]
        self.assertNotIn(PROTECTED_TEXT, json.dumps(raw_attention, sort_keys=True))
        self.assertFalse(
            {
                "action.intent_recorded",
                "work.order_recorded",
                "goal.revision_recorded",
                "commitment.recorded",
            }.intersection(event["type"] for event in raw_attention)
        )
        replayed = AttentionExposureProjection()
        replayed.rebuild(
            self.kernel.schemas.normalize(event) for event in await self.kernel.history()
        )
        self.assertEqual(replayed.semantic_snapshot(), final.semantic_snapshot())

    async def test_required_missing_feature_is_not_imputed(self) -> None:
        await self._opportunity(
            20,
            disposition=AttentionDisposition.REMEMBER,
            include_urgency=False,
        )
        records = await self._worker().process_available()
        audit = (await self.recorder.current_projection()).audit(
            source_policy_id=self.source_policy.policy_id,
            feature_schema_id=self.schema.schema_id,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(audit.feature_complete_ids, ())
        self.assertEqual(audit.feature_incomplete_ids, (records[0].disposition_id,))
        self.assertIsNone(records[0].decision.costs.model_call_count)
        self.assertIsNone(records[0].decision.costs.input_tokens)

    async def test_policy_activation_is_canonical_and_features_fail_closed(self) -> None:
        early = await self._opportunity(25, disposition=AttentionDisposition.REMEMBER)
        late_policy = AttentionSourcePolicySnapshot.create(
            version="late-policy-v1",
            feature_schema_id=self.schema.schema_id,
            source_event_types=("companion.attention_opportunity",),
            source_prefixes=("companion:",),
            required_payload_fields=("kind",),
            scope="late-only",
            recorded_at=early.timestamp + timedelta(seconds=1),
        )
        await self.kernel.emit(late_policy.to_event(source="attention:test"))
        projection = await self.recorder.current_projection()
        late_audit = projection.audit(
            source_policy_id=late_policy.policy_id,
            feature_schema_id=self.schema.schema_id,
        )
        self.assertEqual(late_audit.recognized_opportunities, ())

        unsafe_schema = AttentionFeatureSchemaSnapshot.create(
            version="unsafe-v1",
            features=(
                AttentionFeatureDefinition(
                    name="raw_content",
                    value_type=AttentionFeatureType.STRING,
                    required=True,
                    policy_safe=False,
                    missingness=FeatureMissingness.REQUIRED_EXPOSURE_INCOMPLETE,
                    allowed_values=("secret",),
                ),
            ),
            recorded_at=early.timestamp,
        )
        with self.assertRaisesRegex(ValueError, "not policy-safe"):
            unsafe_schema.validate_snapshot({"raw_content": "secret"})

    async def test_provider_failure_and_post_append_crash_recover_exactly_once(self) -> None:
        source = await self._opportunity(30, disposition=AttentionDisposition.DEFER)
        self.provider.fail_once_for = source.id
        worker = self._worker(consumer_id="attention-crash-before")
        with self.assertRaisesRegex(RuntimeError, "synthetic provider interruption"):
            await worker.process_available()
        projection = await self.recorder.current_projection()
        self.assertIsNone(
            projection.disposition_for(
                source_event_id=source.id,
                source_policy_id=self.source_policy.policy_id,
                feature_schema_id=self.schema.schema_id,
            )
        )
        records = await worker.process_available()
        self.assertEqual(len(records), 1)

        second = await self._opportunity(31, disposition=AttentionDisposition.REMEMBER)
        crashed = False

        async def crash_after_append(record: object) -> None:
            nonlocal crashed
            if not crashed:
                crashed = True
                raise RuntimeError("crash after durable disposition")

        recovery_worker = self._worker(
            after_disposition=crash_after_append,
            consumer_id="attention-crash-after",
        )
        with self.assertRaisesRegex(RuntimeError, "crash after durable disposition"):
            await recovery_worker.process_available()
        calls_before = self.provider.calls.count(second.id)
        recovered = await self._worker(
            consumer_id="attention-crash-after"
        ).process_available()
        self.assertEqual(self.provider.calls.count(second.id), calls_before)
        self.assertIn(second.id, {value.source_event_id for value in recovered})
        checkpoints = ConsumerCheckpointProjection()
        checkpoints.rebuild(
            self.kernel.schemas.normalize(event) for event in await self.kernel.history()
        )
        checkpoint = checkpoints.get("attention-crash-after")
        assert checkpoint is not None
        self.assertGreaterEqual(checkpoint.last_completed_sequence, second.sequence or 0)

    async def test_concurrent_equal_observations_converge_and_conflicts_fail_closed(self) -> None:
        source = await self._opportunity(40, disposition=AttentionDisposition.WAKE)
        opportunity = AttentionOpportunity(source, self.source_policy, self.schema)
        decision = await self.provider.decide(opportunity)
        first = DeliberativeAttentionRecorder(
            self.kernel,
            derived_information_id_deriver=ID_DERIVER,
            source="attention:distributed-fixture",
        )
        second = DeliberativeAttentionRecorder(
            self.kernel,
            derived_information_id_deriver=ID_DERIVER,
            source="attention:distributed-fixture",
        )
        equal = await asyncio.gather(
            first.record_disposition(
                source_event_id=source.id,
                source_policy_id=self.source_policy.policy_id,
                decision=decision,
                telemetry_context=self.context,
            ),
            second.record_disposition(
                source_event_id=source.id,
                source_policy_id=self.source_policy.policy_id,
                decision=decision,
                telemetry_context=self.context,
            ),
        )
        self.assertEqual(equal[0], equal[1])

        conflict_source = await self._opportunity(41, disposition=AttentionDisposition.DEFER)
        conflict_opportunity = AttentionOpportunity(
            conflict_source, self.source_policy, self.schema
        )
        base = await self.provider.decide(conflict_opportunity)
        results = await asyncio.gather(
            first.record_disposition(
                source_event_id=conflict_source.id,
                source_policy_id=self.source_policy.policy_id,
                decision=base,
                telemetry_context=self.context,
            ),
            second.record_disposition(
                source_event_id=conflict_source.id,
                source_policy_id=self.source_policy.policy_id,
                decision=replace(base, disposition=AttentionDisposition.SUPPRESS),
                telemetry_context=self.context,
            ),
            return_exceptions=True,
        )
        self.assertEqual(sum(not isinstance(value, BaseException) for value in results), 1)
        self.assertEqual(
            sum(isinstance(value, AttentionSemanticConflictError) for value in results),
            1,
        )

    async def test_outcome_and_feedback_links_are_idempotent_and_causal(self) -> None:
        source = await self._opportunity(50, disposition=AttentionDisposition.REMEMBER)
        record = (await self._worker().process_available())[0]
        outcome_event = await self.kernel.emit(
            Event(
                id="outcome-idempotent",
                type="companion.outcome_observed",
                source="companion:fixture",
                timestamp=source.timestamp + timedelta(minutes=1),
            )
        )
        first = await self.recorder.link_outcome(
            disposition_id=record.disposition_id,
            outcome_event_id=outcome_event.id,
            outcome=AttentionOutcome.UNKNOWN,
            observed_at=outcome_event.timestamp,
            recorded_at=outcome_event.timestamp,
            governed_information_ids=(),
            telemetry_context=self.context,
        )
        second = await self.recorder.link_outcome(
            disposition_id=record.disposition_id,
            outcome_event_id=outcome_event.id,
            outcome=AttentionOutcome.UNKNOWN,
            observed_at=outcome_event.timestamp,
            recorded_at=outcome_event.timestamp,
            governed_information_ids=(),
            telemetry_context=self.context,
        )
        self.assertEqual(first, second)
        with self.assertRaises(AttentionSemanticConflictError):
            await self.recorder.link_outcome(
                disposition_id=record.disposition_id,
                outcome_event_id=outcome_event.id,
                outcome=AttentionOutcome.FALSE_SUPPRESSION,
                observed_at=outcome_event.timestamp,
                recorded_at=outcome_event.timestamp,
                governed_information_ids=(),
                telemetry_context=self.context,
            )

        feedback_event = await self.kernel.emit(
            Event(
                id="feedback-idempotent",
                type="companion.explicit_feedback",
                source="companion:user",
                timestamp=outcome_event.timestamp + timedelta(minutes=1),
            )
        )
        feedback = await self.recorder.record_feedback(
            disposition_id=record.disposition_id,
            feedback_event_id=feedback_event.id,
            feedback=AttentionFeedback.TEMPORARY_OVERRIDE,
            actor_id="user:carlos",
            actor_provenance_ref="session:authenticated-user",
            recorded_at=feedback_event.timestamp,
            governed_information_ids=(),
            telemetry_context=self.context,
        )
        repeated = await self.recorder.record_feedback(
            disposition_id=record.disposition_id,
            feedback_event_id=feedback_event.id,
            feedback=AttentionFeedback.TEMPORARY_OVERRIDE,
            actor_id="user:carlos",
            actor_provenance_ref="session:authenticated-user",
            recorded_at=feedback_event.timestamp,
            governed_information_ids=(),
            telemetry_context=self.context,
        )
        self.assertEqual(feedback, repeated)
        with self.assertRaisesRegex(ValueError, "unknown disposition"):
            await self.recorder.record_feedback(
                disposition_id="attention-disposition:missing",
                feedback_event_id=feedback_event.id,
                feedback=AttentionFeedback.ACCEPTED,
                actor_id="user:carlos",
                actor_provenance_ref="session:authenticated-user",
                recorded_at=feedback_event.timestamp,
                governed_information_ids=(),
                telemetry_context=self.context,
            )

        causal_source = await self._opportunity(
            51, disposition=AttentionDisposition.SUPPRESS
        )
        causal_decision = await self.provider.decide(
            AttentionOpportunity(causal_source, self.source_policy, self.schema)
        )
        causal_record = await self.recorder.record_disposition(
            source_event_id=causal_source.id,
            source_policy_id=self.source_policy.policy_id,
            decision=causal_decision,
            telemetry_context=self.context,
        )
        with self.assertRaisesRegex(ValueError, "causally follow"):
            await self.recorder.link_outcome(
                disposition_id=causal_record.disposition_id,
                outcome_event_id="intent-current",
                outcome=AttentionOutcome.HANDLED_WITHIN_WINDOW,
                observed_at=outcome_event.timestamp,
                recorded_at=outcome_event.timestamp,
                governed_information_ids=(),
                telemetry_context=self.context,
            )
