"""Deterministic endogenous candidate producers over defended Noema state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..autonomic.models import Signal
from ..events import Event
from ..intent.models import CoverageDisposition
from ..intent.projection import StrategicProjection
from ..memory.models import ASSERTION_RECORDED_EVENT, SemanticAssertion
from ..memory.projection import MemoryProjection
from ..situation import Commitment, CommitmentStatus, GoalStatus
from .models import (
    CalibrationExchange,
    CognitiveResourceVector,
    EndogenousDrive,
    GoverningIntentRef,
    Inquiry,
    IntrinsicActivity,
    IntrinsicActivityKind,
    ValueOfCognitionInputs,
)


@dataclass(frozen=True, slots=True)
class DetectedCandidate:
    inquiry: Inquiry
    activity: IntrinsicActivity


class DeterministicEndogenousDetector:
    """Produce bounded candidates without models, similarity, or inferred relevance."""

    producer_id = "deterministic-endogenous-detectors-v1"

    def detect(
        self,
        *,
        history: tuple[Event, ...],
        strategy: StrategicProjection,
        memory: MemoryProjection,
        calibrations: tuple[CalibrationExchange, ...],
        at: datetime,
        causal_cursor: int,
    ) -> tuple[DetectedCandidate, ...]:
        if at.tzinfo is None:
            raise ValueError("endogenous detection time must be timezone-aware")
        event_by_id = {event.id: event for event in history}
        candidates = [
            *self._roadmap_health_candidates(
                strategy=strategy,
                at=at,
                causal_cursor=causal_cursor,
                history=history,
            ),
            *self._commitment_gap_candidates(
                strategy=strategy,
                at=at,
                causal_cursor=causal_cursor,
                history=history,
            ),
            *self._belief_hygiene_candidates(
                strategy=strategy,
                memory=memory,
                at=at,
                causal_cursor=causal_cursor,
                history=history,
            ),
            *self._novelty_candidates(
                strategy=strategy,
                at=at,
                causal_cursor=causal_cursor,
                history=history,
                event_by_id=event_by_id,
            ),
            *self._calibration_candidates(
                strategy=strategy,
                calibrations=calibrations,
                at=at,
                causal_cursor=causal_cursor,
            ),
        ]
        unique: dict[str, DetectedCandidate] = {}
        for candidate in candidates:
            existing = unique.get(candidate.activity.activity_id)
            if existing is not None and existing != candidate:
                raise ValueError(
                    f"conflicting deterministic activity identity: {candidate.activity.activity_id}"
                )
            unique[candidate.activity.activity_id] = candidate
        return tuple(unique[key] for key in sorted(unique))

    def _roadmap_health_candidates(
        self,
        *,
        strategy: StrategicProjection,
        at: datetime,
        causal_cursor: int,
        history: tuple[Event, ...],
    ) -> tuple[DetectedCandidate, ...]:
        values: list[DetectedCandidate] = []
        for revision in strategy.roadmap_revisions:
            if strategy.current_roadmap_revision(revision.roadmap_id) != revision:
                continue
            intents = self._intent_refs_for_revision_ids(
                strategy,
                revision.governing_goal_revision_ids,
            )
            if not intents:
                continue
            health = strategy.roadmap_health(revision.roadmap_id, at=at)
            if not health.review_required:
                continue
            priority = self._priority(strategy, intents)
            evidence = self._roadmap_health_evidence(
                strategy=strategy,
                roadmap_id=revision.roadmap_id,
                revision_id=revision.revision_id,
                governing_goal_ids=tuple(ref.goal_id for ref in intents),
                history=history,
            )
            values.append(
                self._candidate(
                    question=(
                        f"Which current evidence would resolve roadmap {revision.roadmap_id} "
                        f"review needs: {', '.join(health.review_reasons)}?"
                    ),
                    origin=EndogenousDrive.GOAL_MAINTENANCE,
                    kind=IntrinsicActivityKind.GOAL_OR_ROADMAP_MAINTENANCE,
                    intents=intents,
                    evidence=evidence,
                    targets=(
                        f"roadmap:{revision.roadmap_id}",
                        f"roadmap-revision:{revision.revision_id}",
                    ),
                    decision_relevance=priority,
                    information_value=0.8,
                    uncertainty=0.7,
                    expected_improvement=round(priority * 0.85, 12),
                    urgency=0.65,
                    confidence=max(0.1, revision.confidence),
                    cost_bases=(0.05, 0.02, 0.04, 0.03, 0.01),
                    resources=(0.8, 60.0, 0.10, 0.01),
                    at=at,
                    causal_cursor=causal_cursor,
                )
            )
        return tuple(values)

    @staticmethod
    def _roadmap_health_evidence(
        *,
        strategy: StrategicProjection,
        roadmap_id: str,
        revision_id: str,
        governing_goal_ids: tuple[str, ...],
        history: tuple[Event, ...],
    ) -> tuple[str, ...]:
        linked_commitment_ids = {
            value.id for value in strategy.commitments if value.roadmap_revision_id == revision_id
        }
        related_event_ids = {
            f"work-order-proposed:{proposal.proposal_id}"
            for proposal in strategy.work_proposals
            if proposal.roadmap_revision_id == revision_id
        }
        related_event_ids.update(
            f"external-workstream-observed:{workstream.observation_id}"
            for workstream in strategy.external_workstreams
            if linked_commitment_ids.intersection(workstream.support_commitment_refs)
        )
        related_subjects = {
            roadmap_id,
            *governing_goal_ids,
            *linked_commitment_ids,
        }
        evidence = {
            f"event:{event.id}"
            for event in history
            if event.id in related_event_ids
            or (event.subject in related_subjects and event.type.startswith("intent."))
        }
        evidence.add(f"event:roadmap-revision-recorded:{revision_id}")
        return tuple(sorted(evidence))

    def _commitment_gap_candidates(
        self,
        *,
        strategy: StrategicProjection,
        at: datetime,
        causal_cursor: int,
        history: tuple[Event, ...],
    ) -> tuple[DetectedCandidate, ...]:
        values: list[DetectedCandidate] = []
        for commitment in strategy.commitments:
            if commitment.status is not CommitmentStatus.ACTIVE:
                continue
            intents = self._intent_refs_for_goal_ids(
                strategy,
                commitment.governing_goal_refs,
            )
            if not intents:
                continue
            coverage = strategy.coverage(commitment.id, at=at)
            if coverage.disposition is not CoverageDisposition.UNCOVERED:
                continue
            related = tuple(
                event
                for event in history
                if event.subject == commitment.id
                and event.type
                in {
                    "intent.commitment_recorded",
                    "intent.commitment_transitioned",
                }
            )
            evidence_ids = {f"event:{event.id}" for event in related}
            if commitment.roadmap_revision_id is not None:
                evidence_ids.add(
                    f"event:roadmap-revision-recorded:{commitment.roadmap_revision_id}"
                )
            values.append(
                self._candidate(
                    question=(
                        f"What bounded support would close commitment {commitment.id} "
                        f"criteria: {', '.join(coverage.uncovered_criteria)}?"
                    ),
                    origin=EndogenousDrive.GOAL_MAINTENANCE,
                    kind=IntrinsicActivityKind.GOAL_OR_ROADMAP_MAINTENANCE,
                    intents=intents,
                    evidence=tuple(sorted(evidence_ids)),
                    targets=(
                        f"commitment:{commitment.id}",
                        f"roadmap-revision:{commitment.roadmap_revision_id}",
                        f"outcome-node:{commitment.outcome_node_id}",
                    ),
                    decision_relevance=commitment.priority,
                    information_value=0.9,
                    uncertainty=min(1.0, 0.4 + 0.1 * len(coverage.uncovered_criteria)),
                    expected_improvement=round(commitment.priority * 0.95, 12),
                    urgency=0.8,
                    confidence=0.9,
                    cost_bases=(0.04, 0.01, 0.03, 0.02, 0.01),
                    resources=(0.7, 45.0, 0.08, 0.01),
                    at=at,
                    causal_cursor=causal_cursor,
                    deadline=self._future_deadline(commitment, at),
                )
            )
        return tuple(values)

    def _belief_hygiene_candidates(
        self,
        *,
        strategy: StrategicProjection,
        memory: MemoryProjection,
        at: datetime,
        causal_cursor: int,
        history: tuple[Event, ...],
    ) -> tuple[DetectedCandidate, ...]:
        grouped: dict[tuple[str, str], list[SemanticAssertion]] = {}
        for assertion in memory.assertions:
            stale = assertion.fresh_until is not None and assertion.fresh_until <= at
            contradicted = memory.is_contradicted(
                assertion.assertion_id,
                valid_at=at,
                known_at=at,
                include_stale=True,
            )
            if stale or contradicted:
                grouped.setdefault((assertion.subject, assertion.predicate), []).append(assertion)

        values: list[DetectedCandidate] = []
        for (subject, predicate), assertions in sorted(grouped.items()):
            intents = self._intent_refs_for_subject(strategy, subject)
            if not intents:
                continue
            assertion_ids = {value.assertion_id for value in assertions}
            evidence_ids = {
                f"event:{event.id}"
                for event in history
                if self._event_mentions_assertion(event, assertion_ids)
            }
            if not evidence_ids:
                continue
            priority = self._priority(strategy, intents)
            contradiction = any(
                memory.is_contradicted(
                    value.assertion_id,
                    valid_at=at,
                    known_at=at,
                    include_stale=True,
                )
                for value in assertions
            )
            confidence = max(value.confidence for value in assertions)
            condition = "contradictory" if contradiction else "stale"
            values.append(
                self._candidate(
                    question=(
                        f"What current evidence resolves the {condition} belief "
                        f"{subject} / {predicate}?"
                    ),
                    origin=EndogenousDrive.COHERENCE,
                    kind=IntrinsicActivityKind.BELIEF_MAINTENANCE,
                    intents=intents,
                    evidence=tuple(sorted(evidence_ids)),
                    targets=tuple(
                        sorted(
                            {f"assertion:{value.assertion_id}" for value in assertions}
                            | {f"subject:{subject}", f"predicate:{predicate}"}
                        )
                    ),
                    decision_relevance=priority,
                    information_value=0.9 if contradiction else 0.75,
                    uncertainty=0.95 if contradiction else 0.7,
                    expected_improvement=round(priority * (0.9 if contradiction else 0.78), 12),
                    urgency=0.75 if contradiction else 0.55,
                    confidence=confidence,
                    cost_bases=(0.04, 0.01, 0.02, 0.02, 0.0),
                    resources=(0.6, 40.0, 0.06, 0.0),
                    at=at,
                    causal_cursor=causal_cursor,
                )
            )
        return tuple(values)

    def _novelty_candidates(
        self,
        *,
        strategy: StrategicProjection,
        at: datetime,
        causal_cursor: int,
        history: tuple[Event, ...],
        event_by_id: dict[str, Event],
    ) -> tuple[DetectedCandidate, ...]:
        values: list[DetectedCandidate] = []
        for event in history:
            if event.type != "rule.evaluation_traced":
                continue
            raw_signal = event.payload.get("signal_would_emit")
            if not isinstance(raw_signal, dict):
                continue
            signal = Signal.from_dict(raw_signal)
            if signal.kind not in {"novelty", "fact.novelty", "self.novelty"}:
                continue
            if not signal.active_at(at):
                continue
            intents = self._intent_refs_for_subject(strategy, signal.subject)
            if not intents:
                continue
            evidence = {f"event:{event.id}"}
            evidence.update(
                f"event:{event_id}"
                for event_id in signal.evidence_event_ids
                if event_id in event_by_id
            )
            priority = self._priority(strategy, intents)
            values.append(
                self._candidate(
                    question=f"Could novel signal {signal.signal_id} change a current decision?",
                    origin=EndogenousDrive.CURIOSITY,
                    kind=IntrinsicActivityKind.INQUIRY,
                    intents=intents,
                    evidence=tuple(sorted(evidence)),
                    targets=(signal.signal_id, f"subject:{signal.subject}"),
                    decision_relevance=min(1.0, signal.salience),
                    information_value=min(1.0, signal.expected_value),
                    uncertainty=round(1.0 - signal.confidence, 12),
                    expected_improvement=round(
                        priority * signal.expected_value * signal.salience,
                        12,
                    ),
                    urgency=signal.urgency,
                    confidence=signal.confidence,
                    cost_bases=(0.04, 0.01, 0.02, 0.03, 0.01),
                    resources=(0.5, 30.0, 0.05, 0.01),
                    at=at,
                    causal_cursor=causal_cursor,
                )
            )
        return tuple(values)

    def _calibration_candidates(
        self,
        *,
        strategy: StrategicProjection,
        calibrations: tuple[CalibrationExchange, ...],
        at: datetime,
        causal_cursor: int,
    ) -> tuple[DetectedCandidate, ...]:
        values: list[DetectedCandidate] = []
        for exchange in calibrations:
            if abs(exchange.local_confidence - exchange.peer_confidence) <= 0.1:
                continue
            if not self._intent_refs_are_current(strategy, exchange.governing_intent_refs):
                continue
            evidence = tuple(
                sorted(
                    {
                        *exchange.local_evidence_refs,
                        *exchange.peer_evidence_refs,
                        exchange.request_provenance_ref,
                        exchange.response_provenance_ref,
                        f"event:calibration-exchange-recorded:{exchange.exchange_id}",
                    }
                )
            )
            priority = self._priority(strategy, exchange.governing_intent_refs)
            disagreement = abs(exchange.local_confidence - exchange.peer_confidence)
            values.append(
                self._candidate(
                    question=(
                        f"Why do local and peer confidence differ for: {exchange.proposition}?"
                    ),
                    origin=EndogenousDrive.SOCIAL_CALIBRATION,
                    kind=IntrinsicActivityKind.PEER_CALIBRATION,
                    intents=exchange.governing_intent_refs,
                    evidence=evidence,
                    targets=(
                        f"calibration-exchange:{exchange.exchange_id}",
                        f"peer:{exchange.peer_id}",
                    ),
                    decision_relevance=priority,
                    information_value=disagreement,
                    uncertainty=disagreement,
                    expected_improvement=round(priority * 0.65 * disagreement, 12),
                    urgency=0.5,
                    confidence=max(exchange.local_confidence, exchange.peer_confidence),
                    cost_bases=(0.04, 0.01, 0.03, 0.02, 0.0),
                    resources=(0.5, 35.0, 0.08, 0.0),
                    at=at,
                    causal_cursor=causal_cursor,
                )
            )
        return tuple(values)

    def _candidate(
        self,
        *,
        question: str,
        origin: EndogenousDrive,
        kind: IntrinsicActivityKind,
        intents: tuple[GoverningIntentRef, ...],
        evidence: tuple[str, ...],
        targets: tuple[str, ...],
        decision_relevance: float,
        information_value: float,
        uncertainty: float,
        expected_improvement: float,
        urgency: float,
        confidence: float,
        cost_bases: tuple[float, float, float, float, float],
        resources: tuple[float, float, float, float],
        at: datetime,
        causal_cursor: int,
        deadline: datetime | None = None,
    ) -> DetectedCandidate:
        expires_at = at + timedelta(hours=6)
        inquiry = Inquiry.create(
            question=question,
            origin=origin,
            governing_intent_refs=intents,
            evidence_refs=evidence,
            target_refs=targets,
            decision_relevance=decision_relevance,
            expected_information_value=information_value,
            uncertainty=uncertainty,
            possible_methods=("inspect current evidence", "prepare a bounded proposal"),
            estimated_cognitive_cost=sum(cost_bases[:4]),
            privacy_risk_cost=cost_bases[4],
            deadline=deadline,
            expires_at=expires_at,
            causal_cursor=causal_cursor,
            created_at=at,
            producer_id=self.producer_id,
        )
        activity = IntrinsicActivity.create(
            kind=kind,
            inquiry_id=inquiry.inquiry_id,
            governing_intent_refs=intents,
            evidence_refs=evidence,
            target_refs=targets,
            voc_inputs=ValueOfCognitionInputs(
                expected_decision_improvement=expected_improvement,
                compute_cost_basis=cost_bases[0],
                delay_cost_basis=cost_bases[1],
                attention_cost_basis=cost_bases[2],
                opportunity_cost_basis=cost_bases[3],
                privacy_risk_cost_basis=cost_bases[4],
            ),
            urgency=urgency,
            confidence=confidence,
            interruptible=True,
            expires_at=expires_at,
            resources=CognitiveResourceVector(
                activities=1,
                compute_units=resources[0],
                wall_time_seconds=resources[1],
                attention_units=resources[2],
                privacy_risk_units=resources[3],
            ),
            causal_cursor=causal_cursor,
            producer_id=self.producer_id,
        )
        return DetectedCandidate(inquiry, activity)

    @staticmethod
    def _future_deadline(commitment: Commitment, at: datetime) -> datetime | None:
        if commitment.deadline is not None and commitment.deadline >= at:
            return commitment.deadline
        return None

    @staticmethod
    def _event_mentions_assertion(event: Event, assertion_ids: set[str]) -> bool:
        if event.type == ASSERTION_RECORDED_EVENT:
            return str(event.payload.get("assertion_id")) in assertion_ids
        if event.type != "memory.contradiction_detected":
            return False
        refs = event.payload.get("assertion_refs")
        if not isinstance(refs, list):
            return False
        return any(str(value) in assertion_ids for value in refs)

    @staticmethod
    def _priority(
        strategy: StrategicProjection,
        refs: tuple[GoverningIntentRef, ...],
    ) -> float:
        values = [
            revision.priority
            for ref in refs
            if (revision := strategy.goal_revision(ref.goal_revision_id)) is not None
        ]
        return max(values, default=0.0)

    def _intent_refs_for_subject(
        self,
        strategy: StrategicProjection,
        subject: str,
    ) -> tuple[GoverningIntentRef, ...]:
        goal = strategy.current_goal_revision(subject)
        if goal is not None:
            return self._intent_refs_for_revision_ids(strategy, (goal.revision_id,))
        roadmap = strategy.current_roadmap_revision(subject)
        if roadmap is not None:
            return self._intent_refs_for_revision_ids(
                strategy,
                roadmap.governing_goal_revision_ids,
            )
        for revision in strategy.roadmap_revisions:
            if (
                revision.revision_id == subject
                and strategy.current_roadmap_revision(revision.roadmap_id) == revision
            ):
                return self._intent_refs_for_revision_ids(
                    strategy,
                    revision.governing_goal_revision_ids,
                )
        commitment = strategy.commitment(subject)
        if commitment is not None:
            return self._intent_refs_for_goal_ids(
                strategy,
                commitment.governing_goal_refs,
            )
        return ()

    def _intent_refs_for_goal_ids(
        self,
        strategy: StrategicProjection,
        goal_ids: tuple[str, ...],
    ) -> tuple[GoverningIntentRef, ...]:
        revisions = tuple(
            revision.revision_id
            for goal_id in goal_ids
            if (revision := strategy.current_goal_revision(goal_id)) is not None
        )
        return self._intent_refs_for_revision_ids(strategy, revisions)

    @staticmethod
    def _intent_refs_for_revision_ids(
        strategy: StrategicProjection,
        revision_ids: tuple[str, ...],
    ) -> tuple[GoverningIntentRef, ...]:
        refs: list[GoverningIntentRef] = []
        for revision_id in revision_ids:
            revision = strategy.goal_revision(revision_id)
            if revision is None:
                return ()
            if strategy.current_goal_revision(revision.goal_id) != revision:
                return ()
            if revision.status not in {GoalStatus.ACTIVE, GoalStatus.BLOCKED}:
                return ()
            refs.append(GoverningIntentRef(revision.goal_id, revision.revision_id))
        return tuple(sorted(set(refs)))

    @staticmethod
    def _intent_refs_are_current(
        strategy: StrategicProjection,
        refs: tuple[GoverningIntentRef, ...],
    ) -> bool:
        return bool(refs) and all(
            (revision := strategy.goal_revision(ref.goal_revision_id)) is not None
            and revision.goal_id == ref.goal_id
            and strategy.current_goal_revision(ref.goal_id) == revision
            and revision.status in {GoalStatus.ACTIVE, GoalStatus.BLOCKED}
            for ref in refs
        )
