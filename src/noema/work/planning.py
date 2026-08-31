"""Planner boundary and deterministic plan validation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol, cast

from ..events import Event
from ..types import utc_now
from .models import (
    PlanProposal,
    WorkDependency,
    WorkGraph,
    WorkNode,
    WorkOrder,
)


class Planner(Protocol):
    """Compile a work order into proposed structure without dispatching it."""

    planner_id: str

    async def propose(
        self,
        work_order: WorkOrder,
        *,
        based_on_event_cursor: int,
        based_on_graph_version: int,
        available_capability_types: tuple[str, ...],
    ) -> PlanProposal: ...


class FakePlanner:
    """Deterministic planner fixture used to prove the control plane."""

    def __init__(
        self,
        *,
        nodes: tuple[WorkNode, ...],
        dependencies: tuple[WorkDependency, ...],
        assumptions: tuple[str, ...],
        done_conditions: tuple[str, ...],
        replan_event_types: tuple[str, ...],
        clock: Callable[[], datetime] = utc_now,
        planner_id: str = "planner:fake",
    ) -> None:
        if not planner_id.strip():
            raise ValueError("fake planner id must be non-empty")
        self.nodes = nodes
        self.dependencies = dependencies
        self.assumptions = assumptions
        self.done_conditions = done_conditions
        self.replan_event_types = replan_event_types
        self.clock = clock
        self.planner_id = planner_id

    async def propose(
        self,
        work_order: WorkOrder,
        *,
        based_on_event_cursor: int,
        based_on_graph_version: int,
        available_capability_types: tuple[str, ...],
    ) -> PlanProposal:
        # The fake deliberately receives capability TYPES only. Agent identity,
        # competence, load, and authority never enter planning.
        del available_capability_types
        return PlanProposal.create(
            planner_id=self.planner_id,
            work_order_id=work_order.work_order_id,
            based_on_event_cursor=based_on_event_cursor,
            based_on_graph_version=based_on_graph_version,
            nodes=self.nodes,
            dependencies=self.dependencies,
            assumptions=self.assumptions,
            done_conditions=self.done_conditions,
            replan_event_types=self.replan_event_types,
            proposed_at=self.clock(),
        )


class PlanValidator:
    """Validate graph legality; it does not optimize or execute the plan."""

    def __init__(self, *, validator_id: str = "plan-validator:v1") -> None:
        if not validator_id.strip():
            raise ValueError("plan validator id must be non-empty")
        self.validator_id = validator_id

    def validate(
        self,
        proposal: PlanProposal,
        work_order: WorkOrder,
        *,
        causal_event_cursor: int,
        acceptance_event_cursor: int,
        current_graph_version: int,
        available_capability_types: tuple[str, ...],
        intervening_events: tuple[Event, ...],
        accepted_at: datetime,
    ) -> WorkGraph:
        if accepted_at.tzinfo is None:
            raise ValueError("plan acceptance time must be timezone-aware")
        if proposal.work_order_id != work_order.work_order_id:
            raise ValueError("plan proposal targets a different work order")
        if proposal.proposed_at < work_order.created_at:
            raise ValueError("plan proposal cannot precede its work order")
        if accepted_at < proposal.proposed_at:
            raise ValueError("plan acceptance cannot precede its proposal")
        if proposal.based_on_event_cursor != causal_event_cursor:
            raise ValueError("plan proposal does not match the captured causal event cursor")
        if acceptance_event_cursor < causal_event_cursor:
            raise ValueError("plan acceptance head cannot precede the planning cut")
        intervening_sequences = tuple(event.sequence for event in intervening_events)
        if any(sequence is None for sequence in intervening_sequences):
            raise ValueError("plan admission requires canonical intervening events")
        canonical_sequences = tuple(cast(int, sequence) for sequence in intervening_sequences)
        if canonical_sequences != tuple(sorted(set(canonical_sequences))):
            raise ValueError("plan admission events must be unique and canonically ordered")
        if any(
            sequence <= causal_event_cursor or sequence > acceptance_event_cursor
            for sequence in canonical_sequences
        ):
            raise ValueError("plan admission events fall outside the planning window")
        observed_head = (
            canonical_sequences[-1] if canonical_sequences else causal_event_cursor
        )
        if observed_head != acceptance_event_cursor:
            raise ValueError("plan admission events do not reach the acceptance head")
        if proposal.based_on_graph_version != current_graph_version:
            raise ValueError("plan proposal does not match the current graph version")
        stale_events = tuple(
            event
            for event in intervening_events
            if event.type in proposal.replan_event_types
            and int(event.sequence or 0) > proposal.based_on_event_cursor
        )
        if stale_events:
            raise ValueError(
                "plan proposal is stale at admission due to intervening events: "
                f"{[event.id for event in stale_events]}"
            )
        if not set(work_order.success_criteria).issubset(proposal.done_conditions):
            raise ValueError("plan done conditions do not cover work-order success criteria")

        nodes_by_id = {node.node_id: node for node in proposal.nodes}
        if len(nodes_by_id) != len(proposal.nodes):
            raise ValueError("plan node ids must be unique")
        dependency_keys = {
            (dependency.predecessor_id, dependency.successor_id)
            for dependency in proposal.dependencies
        }
        if len(dependency_keys) != len(proposal.dependencies):
            raise ValueError("plan dependencies must be unique")
        unknown_dependencies = {
            node_id
            for dependency in proposal.dependencies
            for node_id in (dependency.predecessor_id, dependency.successor_id)
            if node_id not in nodes_by_id
        }
        if unknown_dependencies:
            raise ValueError(
                f"plan dependencies reference unknown nodes: {sorted(unknown_dependencies)}"
            )

        available = set(available_capability_types)
        unknown_capabilities = {
            capability
            for node in proposal.nodes
            for capability in node.required_capabilities
            if capability not in available
        }
        if unknown_capabilities:
            raise ValueError(
                "plan requires unavailable capability types: "
                f"{sorted(unknown_capabilities)}"
            )

        predecessors = {node_id: set[str]() for node_id in nodes_by_id}
        successors = {node_id: set[str]() for node_id in nodes_by_id}
        for dependency in proposal.dependencies:
            predecessors[dependency.successor_id].add(dependency.predecessor_id)
            successors[dependency.predecessor_id].add(dependency.successor_id)
        ready = sorted(node_id for node_id, values in predecessors.items() if not values)
        visited: list[str] = []
        remaining = {node_id: set(values) for node_id, values in predecessors.items()}
        while ready:
            node_id = ready.pop(0)
            visited.append(node_id)
            for successor_id in sorted(successors[node_id]):
                remaining[successor_id].discard(node_id)
                if not remaining[successor_id] and successor_id not in visited:
                    if successor_id not in ready:
                        ready.append(successor_id)
                        ready.sort()
        if len(visited) != len(nodes_by_id):
            raise ValueError("plan dependencies must form a directed acyclic graph")

        ancestors = {node_id: set[str]() for node_id in nodes_by_id}
        for node_id in visited:
            for predecessor_id in predecessors[node_id]:
                ancestors[node_id].add(predecessor_id)
                ancestors[node_id].update(ancestors[predecessor_id])
        for node in proposal.nodes:
            missing_targets = set(node.verification_of) - ancestors[node.node_id]
            if missing_targets:
                raise ValueError(
                    f"verification node {node.node_id} must depend on its targets: "
                    f"{sorted(missing_targets)}"
                )

        return WorkGraph.create(
            proposal=proposal,
            version=current_graph_version + 1,
            validator_id=self.validator_id,
            accepted_at=accepted_at,
        )
