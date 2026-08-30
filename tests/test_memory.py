from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

from noema import (
    AssertionStatus,
    BeliefDisposition,
    EpistemicType,
    Event,
    EvidenceLink,
    EvidenceRelation,
    MemoryProjection,
    MemoryQuery,
    MemoryRetriever,
    SemanticAssertion,
)

FRIDAY = datetime(2026, 8, 28, 10, 0, tzinfo=UTC)
MONDAY = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)


def observed_assertion(
    *,
    subject: str,
    predicate: str,
    value: str,
    valid_from: datetime,
    recorded_at: datetime,
    evidence_ref: str,
    fresh_until: datetime,
    supersedes: str | None = None,
) -> SemanticAssertion:
    return SemanticAssertion.create(
        subject=subject,
        predicate=predicate,
        value=value,
        epistemic_type=EpistemicType.OBSERVED,
        confidence=0.99,
        valid_from=valid_from,
        recorded_at=recorded_at,
        fresh_until=fresh_until,
        evidence_refs=(evidence_ref,),
        supersedes=supersedes,
        mutable_world=True,
    )


class PersistentCognitiveMemoryTests(unittest.TestCase):
    def test_late_knowledge_answers_valid_and_knowledge_time_independently(self) -> None:
        projection = MemoryProjection()
        open_evidence = Event(
            "github.pull_request_observed",
            "test",
            {"status": "open"},
            id="pr-open-event",
            subject="pr:42",
            timestamp=FRIDAY,
        )
        projection.apply(open_evidence)
        open_assertion = observed_assertion(
            subject="pr:42",
            predicate="status",
            value="open",
            valid_from=FRIDAY,
            recorded_at=FRIDAY,
            evidence_ref=f"event:{open_evidence.id}",
            fresh_until=MONDAY + timedelta(days=2),
        )
        projection.apply(open_assertion.to_event(source="test"))

        merge_evidence = Event(
            "github.pull_request_observed",
            "test",
            {"status": "merged", "merged_at": "2026-08-28T18:00:00+00:00"},
            id="pr-merge-event",
            subject="pr:42",
            timestamp=MONDAY,
        )
        projection.apply(merge_evidence)
        merged = observed_assertion(
            subject="pr:42",
            predicate="status",
            value="merged",
            valid_from=FRIDAY + timedelta(hours=8),
            recorded_at=MONDAY,
            evidence_ref=f"event:{merge_evidence.id}",
            fresh_until=MONDAY + timedelta(days=2),
            supersedes=open_assertion.assertion_id,
        )
        outputs = projection.apply(
            merged.to_event(source="test"),
            derived_source="memory:test-projector",
        )
        self.assertEqual([event.type for event in outputs], ["memory.assertion_superseded"])
        projection.apply(outputs[0])

        true_now = projection.belief(
            "pr:42",
            "status",
            valid_at=MONDAY + timedelta(hours=1),
            known_at=MONDAY + timedelta(hours=1),
        )
        true_friday = projection.belief(
            "pr:42",
            "status",
            valid_at=FRIDAY + timedelta(hours=9),
            known_at=MONDAY + timedelta(hours=1),
        )
        known_friday = projection.belief(
            "pr:42",
            "status",
            valid_at=FRIDAY + timedelta(hours=9),
            known_at=FRIDAY + timedelta(hours=10),
        )

        self.assertEqual(true_now.value, "merged")
        self.assertEqual(true_friday.value, "merged")
        self.assertEqual(known_friday.value, "open")
        self.assertEqual(true_now.disposition, BeliefDisposition.HELD)

    def test_contradictory_assertions_are_preserved_and_exposed_as_uncertain(self) -> None:
        projection = MemoryProjection()
        first_event = Event(
            "deployment.reported",
            "source-a",
            {"state": "complete"},
            id="deployment-source-a",
            timestamp=MONDAY,
        )
        second_event = Event(
            "deployment.reported",
            "source-b",
            {"state": "failed"},
            id="deployment-source-b",
            timestamp=MONDAY + timedelta(minutes=1),
        )
        projection.apply(first_event)
        projection.apply(second_event)
        complete = observed_assertion(
            subject="deployment:production",
            predicate="state",
            value="complete",
            valid_from=MONDAY,
            recorded_at=MONDAY,
            evidence_ref=f"event:{first_event.id}",
            fresh_until=MONDAY + timedelta(hours=2),
        )
        failed = observed_assertion(
            subject="deployment:production",
            predicate="state",
            value="failed",
            valid_from=MONDAY,
            recorded_at=MONDAY + timedelta(minutes=1),
            evidence_ref=f"event:{second_event.id}",
            fresh_until=MONDAY + timedelta(hours=2),
        )
        projection.apply(complete.to_event(source="test"))
        outputs = projection.apply(
            failed.to_event(source="test"),
            derived_source="memory:test-projector",
        )
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0].type, "memory.contradiction_detected")
        projection.apply(outputs[0])

        belief = projection.belief(
            "deployment:production",
            "state",
            valid_at=MONDAY + timedelta(minutes=2),
            known_at=MONDAY + timedelta(minutes=2),
        )
        self.assertEqual(belief.disposition, BeliefDisposition.UNCERTAIN)
        self.assertIsNone(belief.value)
        self.assertEqual(len(belief.assertions), 2)
        self.assertEqual(len(belief.contradictions), 1)
        self.assertEqual(len(projection.assertions), 2)
        self.assertEqual(
            len(projection.unresolved_contradictions(known_at=MONDAY + timedelta(minutes=2))),
            1,
        )

    def test_epistemic_invariants_and_simulation_provenance_survive_round_trip(self) -> None:
        simulated = SemanticAssertion.create(
            subject="deployment:production",
            predicate="failure_plausible",
            value=True,
            epistemic_type=EpistemicType.SIMULATED,
            confidence=0.62,
            valid_from=MONDAY,
            recorded_at=MONDAY,
            evidence_refs=("simulation:rollout-17",),
            fresh_until=MONDAY + timedelta(hours=1),
            mutable_world=True,
            status=AssertionStatus.HYPOTHESIS,
        )
        restored = SemanticAssertion.from_dict(simulated.to_dict())
        self.assertEqual(restored, simulated)
        self.assertEqual(restored.epistemic_type, EpistemicType.SIMULATED)
        self.assertEqual(restored.status, AssertionStatus.HYPOTHESIS)
        with self.assertRaises(FrozenInstanceError):
            restored.confidence = 1.0  # type: ignore[misc]
        with self.assertRaisesRegex(ValueError, "derivation"):
            SemanticAssertion.create(
                subject="service:api",
                predicate="risk",
                value="high",
                epistemic_type=EpistemicType.INFERRED,
                confidence=0.8,
                valid_from=MONDAY,
                recorded_at=MONDAY,
                evidence_refs=("event:metric-spike",),
            )
        with self.assertRaisesRegex(ValueError, "mutable-world"):
            SemanticAssertion.create(
                subject="service:api",
                predicate="state",
                value="healthy",
                epistemic_type=EpistemicType.OBSERVED,
                confidence=0.9,
                valid_from=MONDAY,
                recorded_at=MONDAY,
                evidence_refs=("event:health-check",),
                mutable_world=True,
            )
        with self.assertRaisesRegex(ValueError, "simulated evidence"):
            SemanticAssertion.create(
                subject="deployment:production",
                predicate="state",
                value="failed",
                epistemic_type=EpistemicType.OBSERVED,
                confidence=0.8,
                valid_from=MONDAY,
                recorded_at=MONDAY,
                evidence_refs=("simulation:rollout-17",),
            )

        projection = MemoryProjection()
        observed = observed_assertion(
            subject="service:api",
            predicate="state",
            value="healthy",
            valid_from=MONDAY,
            recorded_at=MONDAY,
            evidence_ref="event:health-check",
            fresh_until=MONDAY + timedelta(hours=1),
        )
        projection.apply(
            Event(
                "service.health_observed",
                "test",
                {},
                id="health-check",
                timestamp=MONDAY,
            )
        )
        projection.apply(observed.to_event(source="test"))
        laundering_link = EvidenceLink.create(
            evidence_ref=simulated.assertion_id,
            assertion_ref=observed.assertion_id,
            relation=EvidenceRelation.SUPPORTS,
            strength=0.9,
            evidence_type=EpistemicType.SIMULATED,
            recorded_at=MONDAY + timedelta(minutes=1),
        )
        with self.assertRaisesRegex(ValueError, "simulated evidence"):
            projection.apply(laundering_link.to_event(source="test"))

    def test_fresh_evidence_beats_one_hundred_old_similar_memories(self) -> None:
        projection = MemoryProjection()
        old_time = MONDAY - timedelta(days=365)
        old_ids: set[str] = set()
        for index in range(100):
            projection.apply(
                Event(
                    "service.health_observed",
                    "test",
                    {"state": "healthy"},
                    id=f"old-health-{index}",
                    subject="service:api",
                    timestamp=old_time + timedelta(minutes=index),
                )
            )
            assertion = observed_assertion(
                subject="service:api",
                predicate="status",
                value="healthy",
                valid_from=old_time,
                recorded_at=old_time + timedelta(minutes=index),
                evidence_ref=f"event:old-health-{index}",
                fresh_until=old_time + timedelta(days=1),
            )
            old_ids.add(assertion.assertion_id)
            projection.apply(assertion.to_event(source="test"))

        fresh = observed_assertion(
            subject="service:api",
            predicate="status",
            value="failed",
            valid_from=MONDAY,
            recorded_at=MONDAY,
            evidence_ref="event:fresh-failure",
            fresh_until=MONDAY + timedelta(hours=1),
        )
        projection.apply(
            Event(
                "service.health_observed",
                "test",
                {"state": "failed"},
                id="fresh-failure",
                subject="service:api",
                timestamp=MONDAY,
            )
        )
        outputs = projection.apply(
            fresh.to_event(source="test"),
            derived_source="memory:test-projector",
        )
        for output in outputs:
            projection.apply(output)

        retriever = MemoryRetriever(projection)
        retriever.rebuild_index()
        query = MemoryQuery(
            text="service api status healthy",
            valid_at=MONDAY + timedelta(minutes=1),
            known_at=MONDAY + timedelta(minutes=1),
            include_stale=True,
            limit=101,
        )
        indexed = retriever.retrieve(query)
        self.assertEqual(indexed[0].assertion.assertion_id, fresh.assertion_id)
        self.assertTrue(old_ids.issubset({item.assertion.assertion_id for item in indexed}))

        semantic_state = projection.assertions
        retriever.drop_index()
        rebuilt_without_index = retriever.retrieve(query)
        self.assertEqual(rebuilt_without_index, indexed)
        self.assertEqual(projection.assertions, semantic_state)

        current_only = retriever.retrieve(
            MemoryQuery(
                text="service api status",
                valid_at=MONDAY + timedelta(minutes=1),
                known_at=MONDAY + timedelta(minutes=1),
            )
        )
        self.assertEqual(
            [item.assertion.assertion_id for item in current_only], [fresh.assertion_id]
        )


if __name__ == "__main__":
    unittest.main()
