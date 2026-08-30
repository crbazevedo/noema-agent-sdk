from __future__ import annotations

import unittest
from datetime import UTC, datetime

from noema import ConsumerCheckpoint, ConsumerCheckpointProjection

START = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


class ConsumerCheckpointTests(unittest.TestCase):
    def test_projection_rebuilds_generic_monotonic_watermarks(self) -> None:
        first = ConsumerCheckpoint("memory-index", 10, 12, "epoch:1")
        second = ConsumerCheckpoint("memory-index", 10, 15, "epoch:2")
        projection = ConsumerCheckpointProjection()
        projection.rebuild(
            (
                first.to_event(source="test", timestamp=START).with_sequence(20),
                second.to_event(source="test", timestamp=START).with_sequence(21),
            )
        )

        restored = projection.get("memory-index")
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.epoch_id, "epoch:2")
        self.assertEqual(restored.processing_lag, 5)
        self.assertEqual(restored.event_sequence, 21)

        regressing = ConsumerCheckpoint("memory-index", 9, 15, "epoch:2")
        with self.assertRaisesRegex(ValueError, "regressed"):
            projection.apply(
                regressing.to_event(source="test", timestamp=START).with_sequence(22)
            )

        stale_head = ConsumerCheckpoint("memory-index", 10, 14, "epoch:2")
        with self.assertRaisesRegex(ValueError, "observed head regressed"):
            projection.apply(
                stale_head.to_event(source="test", timestamp=START).with_sequence(23)
            )

    def test_checkpoint_projection_requires_canonical_events(self) -> None:
        checkpoint = ConsumerCheckpoint("habit-miner", 4, 4)
        with self.assertRaisesRegex(ValueError, "canonical event"):
            ConsumerCheckpointProjection().apply(
                checkpoint.to_event(source="test", timestamp=START)
            )
