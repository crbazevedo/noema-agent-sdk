"""Rebuildable exposure denominator and attention-observation projection."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar

from ..events import Event
from ..information import (
    DecisionDisposition,
    GovernedInformationRef,
    InformationGovernanceEngine,
    InformationGovernanceProjection,
    InformationOperation,
    LineageTransformation,
)
from ..types import JSONObject, JSONScalar
from .models import (
    DELIBERATIVE_ATTENTION_EVENT_TYPES,
    DISPOSITION_FEEDBACK_RECORDED_EVENT,
    DISPOSITION_OUTCOME_LINKED_EVENT,
    DISPOSITION_RECORDED_EVENT,
    FEATURE_SCHEMA_RECORDED_EVENT,
    SOURCE_POLICY_RECORDED_EVENT,
    AttentionDenominatorAudit,
    AttentionDispositionFeedbackRecord,
    AttentionDispositionOutcomeLink,
    AttentionDispositionRecord,
    AttentionFeatureSchemaSnapshot,
    AttentionSourcePolicySnapshot,
    OutcomeEvidenceClass,
    RecognizedAttentionOpportunity,
)

ValueT = TypeVar("ValueT")


@dataclass(frozen=True, slots=True)
class _EventReference:
    event_id: str
    event_type: str
    sequence: int
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class _RecognizedSourceFacts:
    features: dict[str, JSONScalar]
    governed_information_ids: tuple[str, ...]


class AttentionExposureProjection:
    """Canonical denominator, dispositions, outcomes, and explicit feedback.

    The projection stores only lightweight references for unrelated canonical
    events. The append-only event store remains the durable source of truth.
    """

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._last_event_id: str | None = None
        self._last_sequence = 0
        self._events: dict[str, _EventReference] = {}
        self._information = InformationGovernanceProjection()
        self._schemas: dict[str, AttentionFeatureSchemaSnapshot] = {}
        self._policies: dict[str, AttentionSourcePolicySnapshot] = {}
        self._policy_sequences: dict[str, int] = {}
        self._recognized: dict[
            tuple[str, str, str], RecognizedAttentionOpportunity
        ] = {}
        self._recognized_source_facts: dict[
            tuple[str, str, str], _RecognizedSourceFacts
        ] = {}
        self._dispositions: dict[str, AttentionDispositionRecord] = {}
        self._dispositions_by_key: dict[
            tuple[str, str, str], AttentionDispositionRecord
        ] = {}
        self._disposition_sequences: dict[str, int] = {}
        self._feature_complete: dict[str, bool] = {}
        self._outcomes: dict[str, AttentionDispositionOutcomeLink] = {}
        self._feedback: dict[str, AttentionDispositionFeedbackRecord] = {}

    @property
    def event_cursor(self) -> int:
        return self._last_sequence

    @property
    def information(self) -> InformationGovernanceProjection:
        return self._information

    @property
    def schemas(self) -> tuple[AttentionFeatureSchemaSnapshot, ...]:
        return tuple(self._schemas[key] for key in sorted(self._schemas))

    @property
    def policies(self) -> tuple[AttentionSourcePolicySnapshot, ...]:
        return tuple(self._policies[key] for key in sorted(self._policies))

    @property
    def recognized_opportunities(self) -> tuple[RecognizedAttentionOpportunity, ...]:
        return tuple(
            sorted(
                self._recognized.values(),
                key=lambda value: (
                    value.source_event_sequence,
                    value.source_policy_id,
                    value.feature_schema_id,
                ),
            )
        )

    @property
    def dispositions(self) -> tuple[AttentionDispositionRecord, ...]:
        return tuple(self._dispositions[key] for key in sorted(self._dispositions))

    @property
    def outcomes(self) -> tuple[AttentionDispositionOutcomeLink, ...]:
        return tuple(self._outcomes[key] for key in sorted(self._outcomes))

    @property
    def feedback(self) -> tuple[AttentionDispositionFeedbackRecord, ...]:
        return tuple(self._feedback[key] for key in sorted(self._feedback))

    def schema(self, schema_id: str) -> AttentionFeatureSchemaSnapshot | None:
        return self._schemas.get(schema_id)

    def policy(self, policy_id: str) -> AttentionSourcePolicySnapshot | None:
        return self._policies.get(policy_id)

    def policy_sequence(self, policy_id: str) -> int | None:
        return self._policy_sequences.get(policy_id)

    def disposition(self, disposition_id: str) -> AttentionDispositionRecord | None:
        return self._dispositions.get(disposition_id)

    def disposition_for(
        self,
        *,
        source_event_id: str,
        source_policy_id: str,
        feature_schema_id: str,
    ) -> AttentionDispositionRecord | None:
        return self._dispositions_by_key.get(
            (source_event_id, source_policy_id, feature_schema_id)
        )

    def recognized_opportunity(
        self,
        *,
        source_event_id: str,
        source_policy_id: str,
        feature_schema_id: str,
    ) -> RecognizedAttentionOpportunity | None:
        return self._recognized.get(
            (source_event_id, source_policy_id, feature_schema_id)
        )

    def outcome_for(self, disposition_id: str) -> AttentionDispositionOutcomeLink | None:
        return self._outcomes.get(disposition_id)

    def feedback_for(
        self, disposition_id: str
    ) -> tuple[AttentionDispositionFeedbackRecord, ...]:
        return tuple(
            sorted(
                (
                    value
                    for value in self._feedback.values()
                    if value.disposition_id == disposition_id
                ),
                key=lambda value: value.feedback_id,
            )
        )

    def event_reference(self, event_id: str) -> tuple[str, int, datetime] | None:
        value = self._events.get(event_id)
        if value is None:
            return None
        return (value.event_type, value.sequence, value.timestamp)

    def apply(self, event: Event) -> bool:
        if event.sequence is None:
            raise ValueError("attention projection requires canonical sequenced events")
        if event.sequence <= self._last_sequence:
            if event.sequence == self._last_sequence and event.id == self._last_event_id:
                return False
            raise ValueError("attention events must be applied in canonical order")
        if event.id in self._events:
            raise ValueError("canonical event id appears at more than one sequence")

        preceding_head = self._last_sequence
        self._information.apply(event)
        handled = False
        if event.type == FEATURE_SCHEMA_RECORDED_EVENT:
            schema = AttentionFeatureSchemaSnapshot.from_event(event)
            self._put_immutable(self._schemas, schema.schema_id, schema, "feature schema")
            handled = True
        elif event.type == SOURCE_POLICY_RECORDED_EVENT:
            policy = AttentionSourcePolicySnapshot.from_event(event)
            if policy.feature_schema_id not in self._schemas:
                raise ValueError("attention source policy references an unknown feature schema")
            schema = self._schemas[policy.feature_schema_id]
            if {value.name for value in schema.features}.intersection(
                policy.information_id_payload_fields
            ):
                raise ValueError(
                    "attention feature fields and information-id fields must be disjoint"
                )
            self._put_immutable(self._policies, policy.policy_id, policy, "source policy")
            self._policy_sequences[policy.policy_id] = event.sequence
            handled = True
        elif event.type == DISPOSITION_RECORDED_EVENT:
            record = AttentionDispositionRecord.from_event(event)
            self._validate_disposition(record, preceding_head=preceding_head)
            key = (
                record.source_event_id,
                record.source_policy_id,
                record.feature_schema_id,
            )
            existing = self._dispositions_by_key.get(key)
            if existing is not None and existing != record:
                raise ValueError("conflicting attention dispositions for one opportunity")
            self._put_immutable(
                self._dispositions,
                record.disposition_id,
                record,
                "attention disposition",
            )
            self._dispositions_by_key[key] = record
            self._disposition_sequences[record.disposition_id] = event.sequence
            schema = self._schemas[record.feature_schema_id]
            self._feature_complete[record.disposition_id] = schema.validate_snapshot(
                record.decision.features
            )
            handled = True
        elif event.type == DISPOSITION_OUTCOME_LINKED_EVENT:
            link = AttentionDispositionOutcomeLink.from_event(event)
            self._validate_outcome(link, preceding_head=preceding_head)
            self._put_immutable(
                self._outcomes,
                link.disposition_id,
                link,
                "attention outcome",
            )
            handled = True
        elif event.type == DISPOSITION_FEEDBACK_RECORDED_EVENT:
            feedback = AttentionDispositionFeedbackRecord.from_event(event)
            self._validate_feedback(feedback, preceding_head=preceding_head)
            self._put_immutable(
                self._feedback,
                feedback.feedback_id,
                feedback,
                "attention feedback",
            )
            handled = True

        self._recognize(event)
        self._events[event.id] = _EventReference(
            event_id=event.id,
            event_type=event.type,
            sequence=event.sequence,
            timestamp=event.timestamp,
        )
        self._last_event_id = event.id
        self._last_sequence = event.sequence
        return handled

    def rebuild(self, events: Iterable[Event]) -> None:
        self._reset()
        for event in events:
            self.apply(event)

    def audit(
        self,
        *,
        source_policy_id: str,
        feature_schema_id: str,
        start_sequence: int = 1,
        end_sequence: int | None = None,
    ) -> AttentionDenominatorAudit:
        if start_sequence <= 0:
            raise ValueError("attention audit start sequence must be positive")
        end = self.event_cursor if end_sequence is None else end_sequence
        if end < start_sequence:
            raise ValueError("attention audit end sequence cannot precede start")
        recognized = tuple(
            value
            for value in self.recognized_opportunities
            if value.source_policy_id == source_policy_id
            and value.feature_schema_id == feature_schema_id
            and start_sequence <= value.source_event_sequence <= end
        )
        records = tuple(
            value
            for value in (
                self._dispositions_by_key.get(opportunity.key) for opportunity in recognized
            )
            if value is not None
        )
        record_keys = {
            (value.source_event_id, value.source_policy_id, value.feature_schema_id)
            for value in records
        }
        missing = tuple(value for value in recognized if value.key not in record_keys)
        complete = tuple(
            value.disposition_id
            for value in records
            if self._feature_complete[value.disposition_id]
        )
        incomplete = tuple(
            value.disposition_id
            for value in records
            if not self._feature_complete[value.disposition_id]
        )
        resolved = tuple(
            value.disposition_id
            for value in records
            if (
                outcome := self._outcomes.get(value.disposition_id)
            ) is not None
            and outcome.evidence_class is not OutcomeEvidenceClass.CENSORED
        )
        censored = tuple(
            value.disposition_id
            for value in records
            if (
                (outcome := self._outcomes.get(value.disposition_id)) is None
                or outcome.evidence_class is OutcomeEvidenceClass.CENSORED
            )
        )
        feedback_observed = tuple(
            value.disposition_id
            for value in records
            if any(
                item.disposition_id == value.disposition_id
                for item in self._feedback.values()
            )
        )
        return AttentionDenominatorAudit(
            source_policy_id=source_policy_id,
            feature_schema_id=feature_schema_id,
            start_sequence=start_sequence,
            end_sequence=end,
            recognized_opportunities=recognized,
            disposition_records=records,
            missing_dispositions=missing,
            duplicate_disposition_keys=(),
            feature_complete_ids=complete,
            feature_incomplete_ids=incomplete,
            outcome_resolved_ids=resolved,
            outcome_censored_ids=censored,
            feedback_observed_ids=feedback_observed,
        )

    def semantic_snapshot(self) -> JSONObject:
        return {
            "event_cursor": self.event_cursor,
            "schemas": [value.to_dict() for value in self.schemas],
            "policies": [value.to_dict() for value in self.policies],
            "recognized": [
                {
                    "source_event_id": value.source_event_id,
                    "source_event_sequence": value.source_event_sequence,
                    "source_policy_id": value.source_policy_id,
                    "feature_schema_id": value.feature_schema_id,
                }
                for value in self.recognized_opportunities
            ],
            "dispositions": [value.to_dict() for value in self.dispositions],
            "outcomes": [value.to_dict() for value in self.outcomes],
            "feedback": [value.to_dict() for value in self.feedback],
        }

    def _recognize(self, event: Event) -> None:
        if event.type in DELIBERATIVE_ATTENTION_EVENT_TYPES:
            return
        for policy_id, policy in self._policies.items():
            activated = self._policy_sequences[policy_id]
            if policy.recognizes(event, activated_at_sequence=activated):
                schema = self._schemas[policy.feature_schema_id]
                opportunity = RecognizedAttentionOpportunity(
                    source_event_id=event.id,
                    source_event_sequence=event.sequence or 0,
                    source_policy_id=policy.policy_id,
                    feature_schema_id=policy.feature_schema_id,
                )
                self._recognized[opportunity.key] = opportunity
                self._recognized_source_facts[opportunity.key] = _RecognizedSourceFacts(
                    features=schema.extract_snapshot(event.payload),
                    governed_information_ids=policy.extract_governed_information_ids(
                        event.payload
                    ),
                )

    def _validate_disposition(
        self,
        record: AttentionDispositionRecord,
        *,
        preceding_head: int,
    ) -> None:
        if record.admitted_predecessor_head != preceding_head:
            raise ValueError("attention disposition does not cite the exact preceding head")
        key = (
            record.source_event_id,
            record.source_policy_id,
            record.feature_schema_id,
        )
        opportunity = self._recognized.get(key)
        if opportunity is None:
            raise ValueError("attention disposition lacks a label-blind recognized opportunity")
        if opportunity.source_event_sequence != record.source_event_sequence:
            raise ValueError("attention disposition source sequence is inconsistent")
        schema = self._schemas.get(record.feature_schema_id)
        if schema is None:
            raise ValueError("attention disposition references an unknown feature schema")
        schema.validate_snapshot(record.decision.features)
        source_facts = self._recognized_source_facts[key]
        if dict(record.decision.features) != source_facts.features:
            raise ValueError(
                "attention disposition features differ from its canonical source"
            )
        if (
            record.decision.governed_information_ids
            != source_facts.governed_information_ids
        ):
            raise ValueError(
                "attention disposition lineage differs from its canonical source declaration"
            )
        source = self._events[record.source_event_id]
        if source.timestamp > record.decision.decided_at:
            raise ValueError("attention disposition predates its source event")
        self._require_actual_cut(record.decision.situation_causal_cursor)
        for reference in (
            *record.decision.decision_refs,
            *record.decision.governing_intent_refs,
        ):
            cited = self._events.get(reference)
            if cited is None or cited.sequence > record.decision.situation_causal_cursor:
                raise ValueError("attention decision reference was unavailable at its causal cut")
        self._validate_source_access(
            governed_information_ids=source_facts.governed_information_ids,
            information_access_decision_ids=(
                record.source_information_access_decision_ids
            ),
            situation_causal_cursor=record.decision.situation_causal_cursor,
        )
        self._validate_governance(
            governed_information_ids=record.decision.governed_information_ids,
            derived_information_id=record.derived_information_id,
            information_policy_ids=record.information_policy_ids,
            information_access_decision_ids=(
                record.derived_information_access_decision_ids
            ),
        )

    def _validate_outcome(
        self,
        link: AttentionDispositionOutcomeLink,
        *,
        preceding_head: int,
    ) -> None:
        if link.admitted_predecessor_head != preceding_head:
            raise ValueError("attention outcome does not cite the exact preceding head")
        disposition = self._dispositions.get(link.disposition_id)
        if disposition is None:
            raise ValueError("attention outcome references an unknown disposition")
        source = self._events.get(link.outcome_event_id)
        disposition_sequence = self._disposition_sequences[link.disposition_id]
        if source is None or source.sequence <= disposition_sequence:
            raise ValueError("attention outcome must causally follow its disposition")
        if source.timestamp < disposition.decision.decided_at:
            raise ValueError("attention outcome event time predates its disposition")
        if link.observed_at < source.timestamp:
            raise ValueError("attention outcome observation predates its source event")
        if disposition.derived_information_id not in link.governed_information_ids:
            raise ValueError("attention outcome does not inherit disposition information policy")
        self._validate_governance(
            governed_information_ids=link.governed_information_ids,
            derived_information_id=link.derived_information_id,
            information_policy_ids=link.information_policy_ids,
            information_access_decision_ids=link.information_access_decision_ids,
        )

    def _validate_feedback(
        self,
        feedback: AttentionDispositionFeedbackRecord,
        *,
        preceding_head: int,
    ) -> None:
        if feedback.admitted_predecessor_head != preceding_head:
            raise ValueError("attention feedback does not cite the exact preceding head")
        disposition = self._dispositions.get(feedback.disposition_id)
        if disposition is None:
            raise ValueError("attention feedback references an unknown disposition")
        source = self._events.get(feedback.feedback_event_id)
        disposition_sequence = self._disposition_sequences[feedback.disposition_id]
        if source is None or source.sequence <= disposition_sequence:
            raise ValueError("attention feedback must causally follow its disposition")
        if source.timestamp < disposition.decision.decided_at:
            raise ValueError("attention feedback event time predates its disposition")
        if feedback.recorded_at < source.timestamp:
            raise ValueError("attention feedback record predates explicit feedback")
        if disposition.derived_information_id not in feedback.governed_information_ids:
            raise ValueError("attention feedback does not inherit disposition information policy")
        self._validate_governance(
            governed_information_ids=feedback.governed_information_ids,
            derived_information_id=feedback.derived_information_id,
            information_policy_ids=feedback.information_policy_ids,
            information_access_decision_ids=feedback.information_access_decision_ids,
        )

    def _validate_governance(
        self,
        *,
        governed_information_ids: tuple[str, ...],
        derived_information_id: str,
        information_policy_ids: tuple[str, ...],
        information_access_decision_ids: tuple[str, ...],
    ) -> None:
        lineage = self._information.lineage(derived_information_id)
        binding = self._information.binding(derived_information_id)
        if (
            lineage is None
            or lineage.transformation is not LineageTransformation.DERIVATION
            or lineage.source_information_ids != tuple(sorted(governed_information_ids))
        ):
            raise ValueError("attention record requires exact derived information lineage")
        if (
            binding is None
            or binding.lineage_id != lineage.lineage_id
            or binding.policy_ids != tuple(sorted(information_policy_ids))
        ):
            raise ValueError("attention record requires exact composed policy binding")
        composition = InformationGovernanceEngine(self._information).composition_for(
            GovernedInformationRef(derived_information_id)
        )
        if composition.source_policy_ids != tuple(sorted(information_policy_ids)):
            raise ValueError("attention policy refs differ from canonical composition")
        accessed: set[str] = set()
        for decision_id in information_access_decision_ids:
            decision = self._information.access_decision(decision_id)
            if (
                decision is None
                or decision.policy_decision.disposition is not DecisionDisposition.ALLOW
                or decision.request.context.operation is not InformationOperation.TELEMETRY
            ):
                raise ValueError("attention record requires allowed telemetry access decisions")
            accessed.add(decision.request.information_ref.information_id)
        if accessed != {derived_information_id}:
            raise ValueError("attention telemetry access does not cover its derived artifact")

    def _validate_source_access(
        self,
        *,
        governed_information_ids: tuple[str, ...],
        information_access_decision_ids: tuple[str, ...],
        situation_causal_cursor: int,
    ) -> None:
        if len(information_access_decision_ids) != len(governed_information_ids):
            raise ValueError(
                "attention source access receipts do not exactly cover source information"
            )
        accessed: set[str] = set()
        for decision_id in information_access_decision_ids:
            decision = self._information.access_decision(decision_id)
            event = self._events.get(f"information-access-decided:{decision_id}")
            if (
                decision is None
                or event is None
                or event.sequence > situation_causal_cursor
                or decision.policy_decision.disposition is not DecisionDisposition.ALLOW
                or decision.request.context.operation is not InformationOperation.TELEMETRY
            ):
                raise ValueError(
                    "attention source requires prior allowed telemetry access decisions"
                )
            accessed.add(decision.request.information_ref.information_id)
        if accessed != set(governed_information_ids):
            raise ValueError(
                "attention source access receipts do not exactly cover source information"
            )

    def _require_actual_cut(self, sequence: int) -> None:
        if sequence != 0 and not any(
            value.sequence == sequence for value in self._events.values()
        ):
            raise ValueError("attention situation cursor is not an actual canonical head")

    @staticmethod
    def _put_immutable(
        mapping: dict[str, ValueT], key: str, value: ValueT, name: str
    ) -> None:
        existing = mapping.get(key)
        if existing is not None and existing != value:
            raise ValueError(f"conflicting {name} identity: {key}")
        mapping[key] = value
