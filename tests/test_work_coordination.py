from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from noema import (
    ActionPrerequisite,
    AgentPresence,
    AuthorityLevel,
    AwarenessCoverage,
    AwarenessDemand,
    CapabilityManifest,
    CompetenceBasis,
    CompetenceEstimate,
    DurableWorkCoordinator,
    Event,
    FakePlanner,
    NoemaKernel,
    PresenceStatus,
    SourceState,
    WorkDependency,
    WorkNode,
    WorkNodeKind,
    WorkOrder,
    WorkProjection,
)

START = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def release_planner(clock: MutableClock) -> FakePlanner:
    nodes = (
        WorkNode(
            "A",
            WorkNodeKind.ANALYZE,
            "inspect implementation",
            ("repo-analysis",),
            ("implementation inspection exists",),
        ),
        WorkNode(
            "B",
            WorkNodeKind.ANALYZE,
            "inspect release constraints",
            ("release-analysis",),
            ("release constraints are recorded",),
        ),
        WorkNode(
            "C",
            WorkNodeKind.PREPARE,
            "produce release design",
            ("architecture",),
            ("release design is accepted",),
        ),
        WorkNode(
            "D",
            WorkNodeKind.EXECUTE,
            "implement release changes",
            ("coding",),
            ("implementation artifact exists",),
        ),
        WorkNode(
            "E",
            WorkNodeKind.PREPARE,
            "write release documentation",
            ("technical-writing",),
            ("documentation artifact exists",),
        ),
        WorkNode(
            "F",
            WorkNodeKind.VERIFY,
            "independently verify implementation",
            ("testing",),
            ("verification passes",),
            verification_of=("D",),
        ),
        WorkNode(
            "G",
            WorkNodeKind.RELEASE,
            "prepare the governed release handoff",
            ("release",),
            ("release handoff exists",),
            epistemic_prerequisites=(ActionPrerequisite("deployment", 0.95, 0.95),),
        ),
    )
    dependencies = (
        WorkDependency("A", "C"),
        WorkDependency("B", "C"),
        WorkDependency("C", "D"),
        WorkDependency("C", "E"),
        WorkDependency("D", "F"),
        WorkDependency("D", "G"),
        WorkDependency("E", "G"),
        WorkDependency("F", "G"),
    )
    return FakePlanner(
        nodes=nodes,
        dependencies=dependencies,
        assumptions=("release constraints are stable at the causal cut",),
        done_conditions=("production release is prepared",),
        replan_event_types=("situation.release_constraints_changed",),
        clock=clock,
    )


def deployment_coverage(freshness: float) -> AwarenessCoverage:
    state = SourceState(
        source_id="deployment",
        domain="deployment",
        last_observed_at=START,
        last_cursor="deployment-1",
        change_hazard=1.0,
        confidence=0.99,
        refresh_cost=1.0,
        captured_at=START,
    )
    demand = AwarenessDemand(
        source_id="deployment",
        governing_goal_refs=("goal:release",),
        relevance=1.0,
        decision_sensitivity=1.0,
        required_freshness=0.95,
        required_confidence=0.95,
    )
    return AwarenessCoverage.from_inputs(
        (state,),
        (demand,),
        freshness_by_source={"deployment": freshness},
    )


class DurableWorkCoordinationAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_flagship_dependency_waves_recovery_orientation_and_invalidation(
        self,
    ) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        clock = MutableClock(START)
        coordinator = DurableWorkCoordinator(
            kernel,
            planner=release_planner(clock),
            lease_duration=timedelta(minutes=10),
            clock=clock,
        )
        order = WorkOrder.create(
            purpose="prepare the Noema release for production",
            governing_goal_refs=("goal:release",),
            created_from=("signal:release-requested",),
            priority=0.9,
            desired_outcome="production release is prepared",
            success_criteria=("production release is prepared",),
            created_at=START,
            deadline=START + timedelta(days=1),
            authority_ceiling=AuthorityLevel.PROPOSE,
        )
        await coordinator.record_work_order(order)

        ecology = {
            "agent-alpha": {
                "repo-analysis": 0.95,
                "architecture": 0.82,
                "release": 0.74,
            },
            "agent-beta": {"coding": 0.88, "testing": 0.46},
            "agent-gamma": {"testing": 0.91, "architecture": 0.61},
            "agent-delta": {"technical-writing": 0.93},
            "agent-epsilon": {"release-analysis": 0.92, "coding": 0.80},
        }
        for agent_id, capabilities in ecology.items():
            await coordinator.record_presence(
                AgentPresence(
                    agent_id,
                    PresenceStatus.AVAILABLE,
                    1,
                    START,
                    START + timedelta(days=1),
                )
            )
            await coordinator.record_manifest(
                CapabilityManifest.create(
                    agent_id=agent_id,
                    capabilities=tuple(capabilities),
                    recorded_at=START,
                )
            )
            for capability, score in capabilities.items():
                await coordinator.record_competence(
                    CompetenceEstimate.create(
                        agent_id=agent_id,
                        capability=capability,
                        score=score,
                        evidence_confidence=0.9,
                        basis=CompetenceBasis.SEEDED,
                        evidence_refs=(),
                        estimated_at=START,
                    )
                )

        graph = await coordinator.plan(order.work_order_id)

        # Wave 1 emerges from dependencies and seeded feasibility.
        clock.value = START + timedelta(minutes=1)
        wave_1 = await coordinator.assign_ready(order.work_order_id)
        self.assertEqual(
            tuple((lease.node_id, lease.agent_id) for lease in wave_1),
            (("A", "agent-alpha"), ("B", "agent-epsilon")),
        )
        clock.value = START + timedelta(minutes=2)
        for lease in wave_1:
            await coordinator.complete(
                lease.lease_id,
                fencing_token=lease.fencing_token,
                artifact_refs=(f"artifact:{lease.node_id.lower()}",),
                reported_finished_at=START + timedelta(minutes=2),
            )

        # Wave 2 is the join node.
        clock.value = START + timedelta(minutes=3)
        wave_2 = await coordinator.assign_ready(order.work_order_id)
        self.assertEqual(
            tuple((lease.node_id, lease.agent_id) for lease in wave_2),
            (("C", "agent-alpha"),),
        )
        clock.value = START + timedelta(minutes=4)
        await coordinator.complete(
            wave_2[0].lease_id,
            fencing_token=wave_2[0].fencing_token,
            artifact_refs=("artifact:release-design",),
            reported_finished_at=START + timedelta(minutes=4),
        )

        # Wave 3 fans out. The best seeded coder crashes while holding D.
        clock.value = START + timedelta(minutes=5)
        wave_3 = await coordinator.assign_ready(order.work_order_id)
        self.assertEqual(
            tuple((lease.node_id, lease.agent_id) for lease in wave_3),
            (("D", "agent-beta"), ("E", "agent-delta")),
        )
        d_first = wave_3[0]
        clock.value = START + timedelta(minutes=6)
        await coordinator.complete(
            wave_3[1].lease_id,
            fencing_token=wave_3[1].fencing_token,
            artifact_refs=("artifact:documentation",),
            reported_finished_at=START + timedelta(minutes=6),
        )
        await coordinator.record_presence(
            AgentPresence(
                "agent-beta",
                PresenceStatus.OFFLINE,
                1,
                START + timedelta(minutes=6),
                START + timedelta(days=1),
            )
        )

        # A new coordinator recovers exclusively from canonical history.
        clock.value = START + timedelta(minutes=16)
        recovered = DurableWorkCoordinator(
            kernel,
            planner=release_planner(clock),
            lease_duration=timedelta(minutes=10),
            clock=clock,
        )
        expired = await recovered.recover_expired(at=clock.value)
        self.assertEqual(expired, (d_first,))
        with self.assertRaisesRegex(ValueError, "active lease"):
            await recovered.complete(
                d_first.lease_id,
                fencing_token=d_first.fencing_token,
                artifact_refs=("artifact:stale-completion",),
                reported_finished_at=START + timedelta(minutes=14),
            )
        d_retry = await recovered.assign_ready(order.work_order_id)
        self.assertEqual(
            tuple((lease.node_id, lease.agent_id, lease.fencing_token) for lease in d_retry),
            (("D", "agent-epsilon", 2),),
        )
        clock.value = START + timedelta(minutes=17)
        await recovered.complete(
            d_retry[0].lease_id,
            fencing_token=d_retry[0].fencing_token,
            artifact_refs=("artifact:implementation",),
            reported_finished_at=START + timedelta(minutes=17),
        )

        # Verification is ordinary work but cannot be assigned to D's worker.
        clock.value = START + timedelta(minutes=18)
        wave_4 = await recovered.assign_ready(order.work_order_id)
        self.assertEqual(
            tuple((lease.node_id, lease.agent_id) for lease in wave_4),
            (("F", "agent-gamma"),),
        )
        self.assertNotEqual(wave_4[0].agent_id, d_retry[0].agent_id)
        clock.value = START + timedelta(minutes=19)
        await recovered.complete(
            wave_4[0].lease_id,
            fencing_token=wave_4[0].fencing_token,
            artifact_refs=("artifact:independent-verification",),
            reported_finished_at=START + timedelta(minutes=19),
            verification_passed=True,
        )

        stale_frontier = await recovered.frontier(
            order.work_order_id,
            coverage=deployment_coverage(0.4),
        )
        self.assertEqual(stale_frontier.ready, ())
        self.assertEqual(stale_frontier.epistemic_blocked, ("G",))
        fresh_frontier = await recovered.frontier(
            order.work_order_id,
            coverage=deployment_coverage(0.99),
        )
        self.assertEqual(tuple(node.node_id for node in fresh_frontier.ready), ("G",))

        # A causal-state change invalidates the accepted plan before G is leased.
        clock.value = START + timedelta(minutes=20)
        causal_change = await kernel.emit(
            Event(
                id="release-constraints-v2",
                type="situation.release_constraints_changed",
                source="test:world",
                subject="release:production",
                timestamp=clock.value,
                payload={"constraint_version": 2},
            )
        )
        invalidated = await recovered.invalidate_for(
            causal_change,
            reason="release constraints changed after the plan causal cut",
            invalidated_at=clock.value,
        )
        self.assertEqual(invalidated, (graph,))
        invalid_frontier = await recovered.frontier(
            order.work_order_id,
            coverage=deployment_coverage(0.99),
        )
        self.assertTrue(invalid_frontier.invalidated)
        self.assertEqual(invalid_frontier.ready, ())

        history = await kernel.history()
        replayed = WorkProjection()
        replayed.rebuild(history)
        self.assertEqual(replayed.orders, recovered.projection.orders)
        self.assertEqual(replayed.graphs, recovered.projection.graphs)
        self.assertEqual(replayed.leases, recovered.projection.leases)
        self.assertEqual(replayed.completions, recovered.projection.completions)
        self.assertEqual(replayed.invalidations, recovered.projection.invalidations)
        self.assertEqual(replayed.worker_for_node(graph.graph_id, "D"), "agent-epsilon")
        self.assertEqual(replayed.worker_for_node(graph.graph_id, "F"), "agent-gamma")
        self.assertFalse(
            any(event.type.startswith(("action.", "capability.")) for event in history)
        )

        await kernel.stop()


if __name__ == "__main__":
    unittest.main()
