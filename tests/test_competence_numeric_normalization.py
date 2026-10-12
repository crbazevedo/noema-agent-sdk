import unittest
from datetime import UTC, datetime

from noema import CompetenceBasis, CompetenceEstimate


class CompetenceNumericNormalizationTests(unittest.TestCase):
    def test_integer_numeric_inputs_round_trip_canonical_identity(self):
        estimate = CompetenceEstimate.create(
            agent_id="worker",
            capability="inspect",
            score=1,
            evidence_confidence=1,
            basis=CompetenceBasis.SEEDED,
            evidence_refs=(),
            estimated_at=datetime(2026, 10, 12, tzinfo=UTC),
        )
        replayed = CompetenceEstimate.from_event(estimate.to_event(source="test"))
        self.assertEqual(estimate, replayed)
        self.assertEqual(estimate.estimate_id, replayed.estimate_id)
