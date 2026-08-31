from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from noema import (
    CONSUMER_CHECKPOINT_EVENT,
    EpistemicType,
    Event,
    EvidenceLink,
    EvidenceRelation,
    InMemoryEventStore,
    MemoryProjector,
    NoemaKernel,
    SemanticAssertion,
)

START = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


class FailOnceMemoryStore(InMemoryEventStore):
    def __init__(self) -> None:
        super().__init__()
        self.fail_before_type: str | None = None

    async def append(self, event: Event) -> Event:
        if event.type == self.fail_before_type:
            self.fail_before_type = None
            raise RuntimeError(f"crash before {event.type}")
        return await super().append(event)


class MemoryProjectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_evidence_write_replays_from_generic_checkpoint(self) -> None:
        store = FailOnceMemoryStore()
        kernel = NoemaKernel(store=store)
        await kernel.start()
        worker = MemoryProjector(kernel, clock=lambda: START + timedelta(minutes=10))
        await worker.start()

        source_event = await kernel.emit(
            Event(
                "service.health_observed",
                "test",
                {"state": "failed"},
                id="health-failure-event",
                subject="service:api",
                timestamp=START,
            )
        )
        assertion = SemanticAssertion.create(
            subject="service:api",
            predicate="status",
            value="failed",
            epistemic_type=EpistemicType.OBSERVED,
            confidence=0.99,
            valid_from=START,
            recorded_at=START + timedelta(minutes=1),
            source_refs=(f"event:{source_event.id}",),
            fresh_until=START + timedelta(hours=1),
            mutable_world=True,
        )
        await kernel.emit(assertion.to_event(source="test"))
        healthy_event = await kernel.emit(
            Event(
                "service.health_observed",
                "test",
                {"state": "healthy"},
                id="health-success-event",
                subject="service:api",
                timestamp=START + timedelta(minutes=2),
            )
        )
        healthy = SemanticAssertion.create(
            subject="service:api",
            predicate="status",
            value="healthy",
            epistemic_type=EpistemicType.OBSERVED,
            confidence=0.95,
            valid_from=START,
            recorded_at=START + timedelta(minutes=3),
            source_refs=(f"event:{healthy_event.id}",),
            fresh_until=START + timedelta(hours=1),
            mutable_world=True,
        )
        await kernel.emit(healthy.to_event(source="test"))
        await kernel.bus.drain()
        baseline = worker.checkpoint
        assert baseline is not None
        self.assertEqual(
            len(worker.projection.unresolved_contradictions(known_at=START + timedelta(minutes=4))),
            1,
        )

        link = EvidenceLink.create(
            evidence_ref=f"event:{source_event.id}",
            assertion_ref=assertion.assertion_id,
            relation=EvidenceRelation.SUPPORTS,
            strength=0.99,
            evidence_type=EpistemicType.OBSERVED,
            recorded_at=START + timedelta(minutes=4),
        )
        store.fail_before_type = CONSUMER_CHECKPOINT_EVENT
        evidence_event = await kernel.emit(link.to_event(source="test"))
        await kernel.bus.drain()

        self.assertEqual(worker.checkpoint, baseline)
        self.assertEqual(worker.projection.evidence_links, ())
        self.assertTrue(
            any(
                event.id == evidence_event.id and CONSUMER_CHECKPOINT_EVENT in str(error)
                for event, error in kernel.bus.errors
            )
        )
        before_restart_assertions = worker.projection.assertions
        before_restart_contradictions = worker.projection.contradictions
        await worker.stop()

        recovered = MemoryProjector(
            kernel,
            clock=lambda: START + timedelta(minutes=11),
        )
        await recovered.start()
        await kernel.bus.drain()
        history = await kernel.history()

        self.assertEqual(recovered.projection.assertions, before_restart_assertions)
        self.assertEqual(recovered.projection.contradictions, before_restart_contradictions)
        self.assertEqual(recovered.projection.evidence_links, (link,))
        self.assertEqual(
            len([event for event in history if event.type == "memory.evidence_linked"]),
            1,
        )
        self.assertEqual(
            len([event for event in history if event.type == "memory.contradiction_detected"]),
            1,
        )
        assert recovered.checkpoint is not None
        self.assertGreaterEqual(
            recovered.checkpoint.last_completed_sequence,
            evidence_event.sequence or 0,
        )

        await recovered.stop()
        await kernel.stop()

    async def test_same_process_retry_restores_missing_contradiction_output(self) -> None:
        store = FailOnceMemoryStore()
        kernel = NoemaKernel(store=store)
        await kernel.start()
        worker = MemoryProjector(kernel, clock=lambda: START + timedelta(minutes=10))
        await worker.start()

        first_source = await kernel.emit(
            Event(
                "service.health_observed",
                "test",
                {"state": "healthy"},
                id="same-process-healthy-event",
                timestamp=START,
            )
        )
        healthy = SemanticAssertion.create(
            subject="service:api",
            predicate="status",
            value="healthy",
            epistemic_type=EpistemicType.OBSERVED,
            confidence=0.99,
            valid_from=START,
            recorded_at=START,
            source_refs=(f"event:{first_source.id}",),
            fresh_until=START + timedelta(hours=1),
            mutable_world=True,
        )
        await kernel.emit(healthy.to_event(source="test"))
        second_source = await kernel.emit(
            Event(
                "service.health_observed",
                "test",
                {"state": "failed"},
                id="same-process-failed-event",
                timestamp=START + timedelta(minutes=1),
            )
        )
        await kernel.bus.drain()

        failed = SemanticAssertion.create(
            subject="service:api",
            predicate="status",
            value="failed",
            epistemic_type=EpistemicType.OBSERVED,
            confidence=0.99,
            valid_from=START,
            recorded_at=START + timedelta(minutes=1),
            source_refs=(f"event:{second_source.id}",),
            fresh_until=START + timedelta(hours=1),
            mutable_world=True,
        )
        store.fail_before_type = "memory.contradiction_detected"
        failed_event = await kernel.emit(failed.to_event(source="test"))
        await kernel.bus.drain()

        self.assertIsNone(worker.projection.get_assertion(failed.assertion_id))
        self.assertEqual(
            len(
                [
                    event
                    for event in await kernel.history()
                    if event.type == "memory.contradiction_detected"
                ]
            ),
            0,
        )

        await kernel.bus.publish(failed_event)
        await kernel.bus.drain()
        history = await kernel.history()
        self.assertEqual(
            len([event for event in history if event.type == "memory.contradiction_detected"]),
            1,
        )
        self.assertIsNotNone(worker.projection.get_assertion(failed.assertion_id))
        self.assertEqual(
            len(worker.projection.unresolved_contradictions(known_at=START + timedelta(minutes=2))),
            1,
        )

        await worker.stop()
        await kernel.stop()

    async def test_same_process_retry_restores_missing_supersession_output(self) -> None:
        store = FailOnceMemoryStore()
        kernel = NoemaKernel(store=store)
        await kernel.start()
        worker = MemoryProjector(kernel, clock=lambda: START + timedelta(minutes=10))
        await worker.start()

        open_source = await kernel.emit(
            Event(
                "work.status_observed",
                "test",
                {"status": "open"},
                id="same-process-open-event",
                timestamp=START,
            )
        )
        open_assertion = SemanticAssertion.create(
            subject="work:42",
            predicate="status",
            value="open",
            epistemic_type=EpistemicType.OBSERVED,
            confidence=0.99,
            valid_from=START,
            recorded_at=START,
            source_refs=(f"event:{open_source.id}",),
            fresh_until=START + timedelta(hours=2),
            mutable_world=True,
        )
        await kernel.emit(open_assertion.to_event(source="test"))
        closed_source = await kernel.emit(
            Event(
                "work.status_observed",
                "test",
                {"status": "closed"},
                id="same-process-closed-event",
                timestamp=START + timedelta(minutes=1),
            )
        )
        await kernel.bus.drain()

        closed = SemanticAssertion.create(
            subject="work:42",
            predicate="status",
            value="closed",
            epistemic_type=EpistemicType.OBSERVED,
            confidence=0.99,
            valid_from=START + timedelta(minutes=1),
            recorded_at=START + timedelta(minutes=1),
            source_refs=(f"event:{closed_source.id}",),
            fresh_until=START + timedelta(hours=2),
            supersedes=open_assertion.assertion_id,
            mutable_world=True,
        )
        store.fail_before_type = "memory.assertion_superseded"
        closed_event = await kernel.emit(closed.to_event(source="test"))
        await kernel.bus.drain()

        self.assertIsNone(worker.projection.get_assertion(closed.assertion_id))
        self.assertEqual(len(worker.projection.supersessions), 0)

        await kernel.bus.publish(closed_event)
        await kernel.bus.drain()
        history = await kernel.history()
        self.assertEqual(
            len([event for event in history if event.type == "memory.assertion_superseded"]),
            1,
        )
        self.assertEqual(len(worker.projection.supersessions), 1)
        belief = worker.projection.belief(
            "work:42",
            "status",
            valid_at=START + timedelta(minutes=2),
            known_at=START + timedelta(minutes=2),
        )
        self.assertEqual(belief.value, "closed")

        await worker.stop()
        await kernel.stop()


if __name__ == "__main__":
    unittest.main()
