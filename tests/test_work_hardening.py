from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta

from noema import (
    AgentPresence,
    CapabilityManifest,
    CompetenceBasis,
    CompetenceEstimate,
    DurableWorkCoordinator,
    Event,
    FakePlanner,
    NoemaKernel,
    PlanProposal,
    PresenceStatus,
    WorkGraph,
    WorkNode,
    WorkNodeKind,
    WorkOrder,
    WorkProjection,
)

NOW = datetime(2026, 8, 31, 15, 0, tzinfo=UTC)


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def work_order() -> WorkOrder:
    return WorkOrder.create(
        purpose="inspect a release",
        governing_goal_refs=("goal:release",),
        created_from=("signal:review",),
        priority=0.8,
        desired_outcome="inspection complete",
        success_criteria=("inspection complete",),
        created_at=NOW,
    )


def fake_planner(clock: MutableClock) -> FakePlanner:
    return FakePlanner(
        nodes=(
            WorkNode(
                node_id="A",
                kind=WorkNodeKind.ANALYZE,
                description="inspect the release",
                required_capabilities=("repo-analysis",),
                completion_criteria=("inspection exists",),
            ),
        ),
        dependencies=(),
        assumptions=("release constraints remain stable",),
        done_conditions=("inspection complete",),
        replan_event_types=("situation.release_constraints_changed",),
        clock=clock,
    )


class BlockingPlanner:
    planner_id = "planner:blocking-test"

    def __init__(self, delegate: FakePlanner) -> None:
        self.delegate = delegate
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def propose(
        self,
        order: WorkOrder,
        *,
        based_on_event_cursor: int,
        based_on_graph_version: int,
        available_capability_types: tuple[str, ...],
    ) -> PlanProposal:
        self.started.set()
        await self.release.wait()
        return await self.delegate.propose(
            order,
            based_on_event_cursor=based_on_event_cursor,
            based_on_graph_version=based_on_graph_version,
            available_capability_types=available_capability_types,
        )


async def record_capability(
    coordinator: DurableWorkCoordinator,
    *,
    presence_valid_until: datetime,
    basis: CompetenceBasis,
) -> None:
    await coordinator.record_presence(
        AgentPresence(
            agent_id="agent-alpha",
            status=PresenceStatus.AVAILABLE,
            max_concurrency=1,
            observed_at=NOW,
            valid_until=presence_valid_until,
        )
    )
    await coordinator.record_manifest(
        CapabilityManifest.create(
            agent_id="agent-alpha",
            capabilities=("repo-analysis",),
            recorded_at=NOW,
        )
    )
    await coordinator.record_competence(
        CompetenceEstimate.create(
            agent_id="agent-alpha",
            capability="repo-analysis",
            score=0.9,
            evidence_confidence=0.8,
            basis=basis,
            evidence_refs=("work-result:claimed",)
            if basis is CompetenceBasis.EVIDENCE
            else (),
            estimated_at=NOW,
        )
    )


class DurableWorkHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_admission_rejects_replan_event_during_planning(self) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        clock = MutableClock(NOW)
        planner = BlockingPlanner(fake_planner(clock))
        coordinator = DurableWorkCoordinator(kernel, planner=planner, clock=clock)
        order = work_order()
        await coordinator.record_work_order(order)
        await coordinator.record_manifest(
            CapabilityManifest.create(
                agent_id="agent-alpha",
                capabilities=("repo-analysis",),
                recorded_at=NOW,
            )
        )

        planning = asyncio.create_task(coordinator.plan(order.work_order_id))
        await planner.started.wait()
        await kernel.emit(
            Event(
                id="release-constraints-during-planning",
                type="situation.release_constraints_changed",
                source="test:world",
                timestamp=NOW + timedelta(minutes=1),
            )
        )
        clock.value = NOW + timedelta(minutes=2)
        planner.release.set()

        with self.assertRaisesRegex(ValueError, "stale at admission"):
            await planning
        self.assertFalse(
            any(event.type == "work.graph_accepted" for event in await kernel.history())
        )
        await kernel.stop()

    async def test_replay_validates_capabilities_from_exact_planning_cut(self) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        clock = MutableClock(NOW)
        planner = BlockingPlanner(fake_planner(clock))
        coordinator = DurableWorkCoordinator(kernel, planner=planner, clock=clock)
        order = work_order()
        await coordinator.record_work_order(order)
        await coordinator.record_manifest(
            CapabilityManifest.create(
                agent_id="agent-alpha",
                capabilities=("repo-analysis",),
                recorded_at=NOW,
            )
        )

        planning = asyncio.create_task(coordinator.plan(order.work_order_id))
        await planner.started.wait()
        changed_manifest = CapabilityManifest.create(
            agent_id="agent-alpha",
            capabilities=("release-analysis",),
            recorded_at=NOW + timedelta(minutes=1),
        )
        await kernel.emit(changed_manifest.to_event(source="test:ecology"))
        clock.value = NOW + timedelta(minutes=2)
        planner.release.set()
        graph = await planning

        replayed = WorkProjection()
        replayed.rebuild(await kernel.history())
        proposal = replayed.proposals[0]
        self.assertEqual(
            replayed.available_capability_types(
                through_sequence=proposal.based_on_event_cursor
            ),
            ("repo-analysis",),
        )
        self.assertEqual(replayed.available_capability_types(), ("release-analysis",))
        self.assertEqual(replayed.graph(graph.graph_id), graph)
        await kernel.stop()

    async def test_expired_presence_cannot_receive_a_lease(self) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        clock = MutableClock(NOW)
        coordinator = DurableWorkCoordinator(
            kernel,
            planner=fake_planner(clock),
            clock=clock,
        )
        order = work_order()
        await coordinator.record_work_order(order)
        await record_capability(
            coordinator,
            presence_valid_until=NOW + timedelta(minutes=1),
            basis=CompetenceBasis.SEEDED,
        )
        await coordinator.plan(order.work_order_id)

        clock.value = NOW + timedelta(minutes=2)
        self.assertEqual(await coordinator.assign_ready(order.work_order_id), ())
        await coordinator.record_presence(
            AgentPresence(
                agent_id="agent-alpha",
                status=PresenceStatus.AVAILABLE,
                max_concurrency=1,
                observed_at=clock.value,
                valid_until=clock.value + timedelta(minutes=5),
            )
        )
        leases = await coordinator.assign_ready(order.work_order_id)
        self.assertEqual(tuple(lease.agent_id for lease in leases), ("agent-alpha",))
        await kernel.stop()

    async def test_reported_finish_cannot_backdate_completion_acceptance(self) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        clock = MutableClock(NOW)
        coordinator = DurableWorkCoordinator(
            kernel,
            planner=fake_planner(clock),
            lease_duration=timedelta(minutes=10),
            clock=clock,
        )
        order = work_order()
        await coordinator.record_work_order(order)
        await record_capability(
            coordinator,
            presence_valid_until=NOW + timedelta(days=1),
            basis=CompetenceBasis.SEEDED,
        )
        await coordinator.plan(order.work_order_id)
        lease = (await coordinator.assign_ready(order.work_order_id))[0]

        clock.value = NOW + timedelta(minutes=20)
        with self.assertRaisesRegex(ValueError, "accepted during its active lease"):
            await coordinator.complete(
                lease.lease_id,
                fencing_token=lease.fencing_token,
                artifact_refs=("artifact:late",),
                reported_finished_at=NOW + timedelta(minutes=5),
            )
        self.assertIsNone(coordinator.projection.completion(graph_id=lease.graph_id, node_id="A"))
        await kernel.stop()

    async def test_evidence_based_competence_is_non_operational_in_v05(self) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        clock = MutableClock(NOW)
        coordinator = DurableWorkCoordinator(
            kernel,
            planner=fake_planner(clock),
            clock=clock,
        )
        order = work_order()
        await coordinator.record_work_order(order)
        await coordinator.record_presence(
            AgentPresence(
                agent_id="agent-alpha",
                status=PresenceStatus.AVAILABLE,
                max_concurrency=1,
                observed_at=NOW,
                valid_until=NOW + timedelta(days=1),
            )
        )
        await coordinator.record_manifest(
            CapabilityManifest.create(
                agent_id="agent-alpha",
                capabilities=("repo-analysis",),
                recorded_at=NOW,
            )
        )
        evidence_estimate = CompetenceEstimate.create(
            agent_id="agent-alpha",
            capability="repo-analysis",
            score=0.99,
            evidence_confidence=0.99,
            basis=CompetenceBasis.EVIDENCE,
            evidence_refs=("unresolved:claim",),
            estimated_at=NOW,
        )
        with self.assertRaisesRegex(ValueError, "non-operational in v0.5"):
            await coordinator.record_competence(evidence_estimate)
        with self.assertRaisesRegex(ValueError, "non-operational in v0.5"):
            WorkProjection().rebuild(
                [evidence_estimate.to_event(source="test").with_sequence(1)]
            )
        graph: WorkGraph = await coordinator.plan(order.work_order_id)

        self.assertEqual(await coordinator.assign_ready(order.work_order_id), ())
        await coordinator.record_competence(
            CompetenceEstimate.create(
                agent_id="agent-alpha",
                capability="repo-analysis",
                score=0.7,
                evidence_confidence=0.6,
                basis=CompetenceBasis.SEEDED,
                evidence_refs=(),
                estimated_at=NOW + timedelta(minutes=1),
            )
        )
        clock.value = NOW + timedelta(minutes=1)
        leases = await coordinator.assign_ready(order.work_order_id)
        self.assertEqual(tuple(lease.graph_id for lease in leases), (graph.graph_id,))
        await kernel.stop()


if __name__ == "__main__":
    unittest.main()
