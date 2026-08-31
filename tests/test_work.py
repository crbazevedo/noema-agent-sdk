from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from noema import (
    AuthorityLevel,
    CapabilityManifest,
    CompetenceBasis,
    CompetenceEstimate,
    FakePlanner,
    PlanProposal,
    PlanValidator,
    WorkDependency,
    WorkLease,
    WorkNode,
    WorkNodeKind,
    WorkOrder,
)

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def order() -> WorkOrder:
    return WorkOrder.create(
        purpose="prepare a release",
        governing_goal_refs=("goal:release",),
        created_from=("signal:release-requested",),
        priority=0.8,
        desired_outcome="release is ready",
        success_criteria=("release is ready",),
        created_at=NOW,
    )


class WorkContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_lease_completion_and_expiry_share_one_terminal_identity(self) -> None:
        lease = WorkLease.create(
            graph_id="graph:release",
            node_id="D",
            agent_id="agent-beta",
            fencing_token=1,
            granted_at=NOW,
            lease_duration=timedelta(minutes=10),
            match_score=0.8,
            competence_estimate_refs=("estimate:coding",),
        )

        completion = lease.completion_event(
            source="test",
            accepted_at=NOW + timedelta(minutes=1),
            artifact_refs=("artifact:implementation",),
            reported_finished_at=NOW + timedelta(seconds=30),
        )
        expiration = lease.expiration_event(
            source="test",
            expired_at=NOW + timedelta(minutes=10),
            reason="worker disappeared",
        )

        self.assertEqual(completion.id, expiration.id)
        self.assertNotEqual(completion.type, expiration.type)

    async def test_capability_competence_and_authority_are_distinct_contracts(self) -> None:
        manifest = CapabilityManifest.create(
            agent_id="agent-alpha",
            capabilities=("repo-analysis",),
            recorded_at=NOW,
        )
        estimate = CompetenceEstimate.create(
            agent_id="agent-alpha",
            capability="repo-analysis",
            score=0.9,
            evidence_confidence=0.8,
            basis=CompetenceBasis.EVIDENCE,
            evidence_refs=("work-result:inspection-17",),
            estimated_at=NOW,
        )
        work_order = WorkOrder.create(
            purpose="inspect a release",
            governing_goal_refs=("goal:release",),
            created_from=("signal:review",),
            priority=0.7,
            desired_outcome="inspection complete",
            success_criteria=("inspection complete",),
            authority_ceiling=AuthorityLevel.PROPOSE,
            created_at=NOW,
        )

        self.assertNotIn("score", manifest.to_dict())
        self.assertNotIn("authority_ceiling", estimate.to_dict())
        self.assertEqual(work_order.authority_ceiling, AuthorityLevel.PROPOSE)
        self.assertEqual(
            CompetenceEstimate.from_event(estimate.to_event(source="test")),
            estimate,
        )

    async def test_fake_planner_proposes_structure_without_worker_or_action_identity(self) -> None:
        work_node = WorkNode(
            node_id="A",
            kind=WorkNodeKind.ANALYZE,
            description="inspect the implementation",
            required_capabilities=("repo-analysis",),
            completion_criteria=("inspection artifact exists",),
        )
        planner = FakePlanner(
            nodes=(work_node,),
            dependencies=(),
            assumptions=(),
            done_conditions=("release is ready",),
            replan_event_types=("situation.release_constraints_changed",),
            clock=lambda: NOW,
        )

        proposal = await planner.propose(
            order(),
            based_on_event_cursor=12,
            based_on_graph_version=0,
            available_capability_types=("repo-analysis",),
        )

        self.assertIsInstance(proposal, PlanProposal)
        self.assertNotIn("agent_id", proposal.to_dict())
        self.assertNotIn("action", work_node.to_dict())
        graph = PlanValidator().validate(
            proposal,
            order(),
            causal_event_cursor=12,
            acceptance_event_cursor=12,
            current_graph_version=0,
            available_capability_types=("repo-analysis",),
            intervening_events=(),
            accepted_at=NOW,
        )
        self.assertNotEqual(proposal.proposal_id, graph.graph_id)
        self.assertNotEqual(order().work_order_id, graph.graph_id)

    async def test_plan_validator_rejects_cycles_and_unavailable_capabilities(self) -> None:
        nodes = (
            WorkNode(
                node_id="A",
                kind=WorkNodeKind.ANALYZE,
                description="inspect",
                required_capabilities=("repo-analysis",),
                completion_criteria=("inspection exists",),
            ),
            WorkNode(
                node_id="B",
                kind=WorkNodeKind.PREPARE,
                description="prepare",
                required_capabilities=("architecture",),
                completion_criteria=("design exists",),
            ),
        )
        planner = FakePlanner(
            nodes=nodes,
            dependencies=(WorkDependency("A", "B"), WorkDependency("B", "A")),
            assumptions=(),
            done_conditions=("release is ready",),
            replan_event_types=("situation.release_constraints_changed",),
            clock=lambda: NOW,
        )
        proposal = await planner.propose(
            order(),
            based_on_event_cursor=3,
            based_on_graph_version=0,
            available_capability_types=("repo-analysis", "architecture"),
        )

        with self.assertRaisesRegex(ValueError, "directed acyclic"):
            PlanValidator().validate(
                proposal,
                order(),
                causal_event_cursor=3,
                acceptance_event_cursor=3,
                current_graph_version=0,
                available_capability_types=("repo-analysis", "architecture"),
                intervening_events=(),
                accepted_at=NOW,
            )
        with self.assertRaisesRegex(ValueError, "unavailable capability"):
            PlanValidator().validate(
                proposal,
                order(),
                causal_event_cursor=3,
                acceptance_event_cursor=3,
                current_graph_version=0,
                available_capability_types=("repo-analysis",),
                intervening_events=(),
                accepted_at=NOW,
            )


if __name__ == "__main__":
    unittest.main()
