"""Deterministic replay, readiness, matching, and lease control."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Protocol, cast

from ..continuity import AwarenessCoverage, OrientationBarrier
from ..events import Event
from ..information.admission import InformationGovernanceAdmission
from ..information.models import (
    DISCLOSURE_DECIDED_EVENT,
    INFORMATION_ACCESS_DECIDED_EVENT,
    DisclosureDecision,
    InformationAccessDecision,
    InformationOperation,
)
from ..information.projection import InformationGovernanceProjection
from ..kernel import NoemaKernel
from ..store import ConcurrentAppendError
from ..types import parse_datetime, utc_now
from .models import (
    AGENT_PRESENCE_RECORDED_EVENT,
    CAPABILITY_MANIFEST_RECORDED_EVENT,
    COMPETENCE_ESTIMATE_RECORDED_EVENT,
    PLAN_PROPOSED_EVENT,
    WORK_GRAPH_ACCEPTED_EVENT,
    WORK_LEASE_EXPIRED_EVENT,
    WORK_LEASE_GRANTED_EVENT,
    WORK_NODE_COMPLETED_EVENT,
    WORK_ORDER_RECORDED_EVENT,
    WORK_PLAN_INVALIDATED_EVENT,
    AgentPresence,
    CapabilityManifest,
    CompetenceBasis,
    CompetenceEstimate,
    PlanProposal,
    PresenceStatus,
    WorkGraph,
    WorkLease,
    WorkNode,
    WorkNodeKind,
    WorkOrder,
    plan_invalidation_event,
)
from .planning import Planner, PlanValidator


@dataclass(frozen=True, slots=True)
class NodeCompletion:
    graph_id: str
    node_id: str
    agent_id: str
    lease_id: str
    fencing_token: int
    accepted_at: datetime
    reported_finished_at: datetime | None
    artifact_refs: tuple[str, ...]
    verification_passed: bool | None


@dataclass(frozen=True, slots=True)
class PlanInvalidation:
    graph_id: str
    trigger_event_id: str
    trigger_event_sequence: int
    invalidated_at: datetime
    reason: str


class WorkProjection:
    """Rebuild every durable work-control fact from canonical event history."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._events: dict[str, Event] = {}
        self._last_sequence = 0
        self._orders: dict[str, WorkOrder] = {}
        self._proposals: dict[str, PlanProposal] = {}
        self._graphs: dict[str, WorkGraph] = {}
        self._latest_graph_by_order: dict[str, str] = {}
        self._invalidations: dict[str, PlanInvalidation] = {}
        self._presence: dict[str, AgentPresence] = {}
        self._manifests: dict[str, CapabilityManifest] = {}
        self._competence: dict[tuple[str, str], CompetenceEstimate] = {}
        self._leases: dict[str, WorkLease] = {}
        self._lease_outcomes: dict[str, str] = {}
        self._completions: dict[tuple[str, str], NodeCompletion] = {}
        self._highest_fencing_token: dict[tuple[str, str], int] = {}

    @property
    def orders(self) -> tuple[WorkOrder, ...]:
        return tuple(self._orders[key] for key in sorted(self._orders))

    @property
    def event_cursor(self) -> int:
        """Canonical cut through which every projected planning input is known."""

        return self._last_sequence

    @property
    def proposals(self) -> tuple[PlanProposal, ...]:
        return tuple(self._proposals[key] for key in sorted(self._proposals))

    @property
    def graphs(self) -> tuple[WorkGraph, ...]:
        return tuple(
            sorted(
                self._graphs.values(),
                key=lambda value: (value.work_order_id, value.version, value.graph_id),
            )
        )

    @property
    def presences(self) -> tuple[AgentPresence, ...]:
        return tuple(self._presence[key] for key in sorted(self._presence))

    @property
    def manifests(self) -> tuple[CapabilityManifest, ...]:
        return tuple(self._manifests[key] for key in sorted(self._manifests))

    @property
    def competence_estimates(self) -> tuple[CompetenceEstimate, ...]:
        return tuple(self._competence[key] for key in sorted(self._competence))

    @property
    def leases(self) -> tuple[WorkLease, ...]:
        return tuple(
            sorted(
                self._leases.values(),
                key=lambda value: (
                    value.graph_id,
                    value.node_id,
                    value.fencing_token,
                ),
            )
        )

    @property
    def active_leases(self) -> tuple[WorkLease, ...]:
        return tuple(
            value for value in self.leases if self._lease_outcomes[value.lease_id] == "active"
        )

    @property
    def completions(self) -> tuple[NodeCompletion, ...]:
        return tuple(
            self._completions[key]
            for key in sorted(self._completions, key=lambda value: (value[0], value[1]))
        )

    @property
    def invalidations(self) -> tuple[PlanInvalidation, ...]:
        return tuple(self._invalidations[key] for key in sorted(self._invalidations))

    def order(self, work_order_id: str) -> WorkOrder | None:
        return self._orders.get(work_order_id)

    def graph(self, graph_id: str) -> WorkGraph | None:
        return self._graphs.get(graph_id)

    def latest_graph(self, work_order_id: str) -> WorkGraph | None:
        graph_id = self._latest_graph_by_order.get(work_order_id)
        return self._graphs.get(graph_id) if graph_id is not None else None

    def graph_is_active(self, graph_id: str) -> bool:
        graph = self._graphs.get(graph_id)
        return (
            graph is not None
            and graph_id not in self._invalidations
            and self._latest_graph_by_order.get(graph.work_order_id) == graph_id
        )

    def presence(self, agent_id: str) -> AgentPresence | None:
        return self._presence.get(agent_id)

    def manifest(self, agent_id: str) -> CapabilityManifest | None:
        return self._manifests.get(agent_id)

    def competence(self, agent_id: str, capability: str) -> CompetenceEstimate | None:
        return self._competence.get((agent_id, capability))

    def active_lease_for_node(self, graph_id: str, node_id: str) -> WorkLease | None:
        return next(
            (
                value
                for value in self.active_leases
                if value.graph_id == graph_id and value.node_id == node_id
            ),
            None,
        )

    def active_lease(self, lease_id: str) -> WorkLease | None:
        value = self._leases.get(lease_id)
        if value is None or self._lease_outcomes[value.lease_id] != "active":
            return None
        return value

    def completed(self, graph_id: str, node_id: str) -> bool:
        return (graph_id, node_id) in self._completions

    def completion(self, graph_id: str, node_id: str) -> NodeCompletion | None:
        return self._completions.get((graph_id, node_id))

    def worker_for_node(self, graph_id: str, node_id: str) -> str | None:
        completion = self.completion(graph_id, node_id)
        return completion.agent_id if completion is not None else None

    def next_fencing_token(self, graph_id: str, node_id: str) -> int:
        return self._highest_fencing_token.get((graph_id, node_id), 0) + 1

    def active_lease_count(self, agent_id: str) -> int:
        return sum(value.agent_id == agent_id for value in self.active_leases)

    def available_capability_types(
        self,
        *,
        through_sequence: int | None = None,
    ) -> tuple[str, ...]:
        if through_sequence is None:
            manifests = self._manifests.values()
        else:
            manifests_by_agent: dict[str, CapabilityManifest] = {}
            for event in self._events.values():
                if (
                    event.type == CAPABILITY_MANIFEST_RECORDED_EVENT
                    and (event.sequence or 0) <= through_sequence
                ):
                    manifest = CapabilityManifest.from_event(event)
                    manifests_by_agent[manifest.agent_id] = manifest
            manifests = manifests_by_agent.values()
        return tuple(
            sorted({capability for value in manifests for capability in value.capabilities})
        )

    def events_after(
        self,
        sequence: int,
        *,
        through_sequence: int | None = None,
    ) -> tuple[Event, ...]:
        return tuple(
            event
            for event in self._events.values()
            if (event.sequence or 0) > sequence
            and (
                through_sequence is None
                or (event.sequence or 0) <= through_sequence
            )
        )

    def apply(self, event: Event) -> bool:
        existing = self._events.get(event.id)
        if existing is not None:
            if existing != event:
                raise ValueError(f"conflicting canonical work event identity: {event.id}")
            return False
        if event.sequence is None:
            raise ValueError("work projection requires canonical sequenced events")
        if event.sequence <= self._last_sequence:
            raise ValueError("work projection events must be applied in canonical sequence order")

        handled = False
        if event.type == WORK_ORDER_RECORDED_EVENT:
            order = WorkOrder.from_event(event)
            existing_order = self._orders.get(order.work_order_id)
            if existing_order is not None and existing_order != order:
                raise ValueError(f"work order changed: {order.work_order_id}")
            self._orders[order.work_order_id] = order
            handled = True
        elif event.type == PLAN_PROPOSED_EVENT:
            proposal = PlanProposal.from_event(event)
            if proposal.work_order_id not in self._orders:
                raise ValueError("plan proposal references an unknown work order")
            if event.causation_id != f"work-order-recorded:{proposal.work_order_id}":
                raise ValueError("plan proposal causation is inconsistent")
            existing_proposal = self._proposals.get(proposal.proposal_id)
            if existing_proposal is not None and existing_proposal != proposal:
                raise ValueError(f"plan proposal changed: {proposal.proposal_id}")
            self._proposals[proposal.proposal_id] = proposal
            handled = True
        elif event.type == WORK_GRAPH_ACCEPTED_EVENT:
            graph = WorkGraph.from_event(event)
            graph_proposal = self._proposals.get(graph.proposal_id)
            if graph_proposal is None or graph.work_order_id not in self._orders:
                raise ValueError("work graph references unknown planning state")
            if event.causation_id != f"plan-proposed:{graph.proposal_id}":
                raise ValueError("work graph causation is inconsistent")
            current_graph = self.latest_graph(graph.work_order_id)
            current_version = current_graph.version if current_graph is not None else 0
            expected = PlanValidator(validator_id=graph.validator_id).validate(
                graph_proposal,
                self._orders[graph.work_order_id],
                causal_event_cursor=graph_proposal.based_on_event_cursor,
                acceptance_event_cursor=self.event_cursor,
                current_graph_version=current_version,
                available_capability_types=self.available_capability_types(
                    through_sequence=graph_proposal.based_on_event_cursor
                ),
                intervening_events=self.events_after(
                    graph_proposal.based_on_event_cursor,
                    through_sequence=event.sequence - 1,
                ),
                accepted_at=graph.accepted_at,
            )
            if graph != expected:
                raise ValueError("accepted work graph differs from deterministic validation")
            self._graphs[graph.graph_id] = graph
            self._latest_graph_by_order[graph.work_order_id] = graph.graph_id
            handled = True
        elif event.type == AGENT_PRESENCE_RECORDED_EVENT:
            presence = AgentPresence.from_event(event)
            current_presence = self._presence.get(presence.agent_id)
            if (
                current_presence is not None
                and presence.observed_at < current_presence.observed_at
            ):
                raise ValueError(f"agent presence regressed: {presence.agent_id}")
            self._presence[presence.agent_id] = presence
            handled = True
        elif event.type == CAPABILITY_MANIFEST_RECORDED_EVENT:
            manifest = CapabilityManifest.from_event(event)
            current_manifest = self._manifests.get(manifest.agent_id)
            if (
                current_manifest is not None
                and manifest.recorded_at < current_manifest.recorded_at
            ):
                raise ValueError(f"capability manifest regressed: {manifest.agent_id}")
            self._manifests[manifest.agent_id] = manifest
            handled = True
        elif event.type == COMPETENCE_ESTIMATE_RECORDED_EVENT:
            estimate = CompetenceEstimate.from_event(event)
            if estimate.basis is not CompetenceBasis.SEEDED:
                raise ValueError(
                    "evidence-based competence is non-operational in v0.5"
                )
            key = (estimate.agent_id, estimate.capability)
            current_estimate = self._competence.get(key)
            if (
                current_estimate is not None
                and estimate.estimated_at < current_estimate.estimated_at
            ):
                raise ValueError(f"competence estimate regressed: {key}")
            self._competence[key] = estimate
            handled = True
        elif event.type == WORK_LEASE_GRANTED_EVENT:
            lease = WorkLease.from_event(event)
            if event.causation_id != f"work-graph-accepted:{lease.graph_id}":
                raise ValueError("work lease causation is inconsistent")
            self._validate_lease_grant(lease)
            self._leases[lease.lease_id] = lease
            self._lease_outcomes[lease.lease_id] = "active"
            self._highest_fencing_token[(lease.graph_id, lease.node_id)] = lease.fencing_token
            handled = True
        elif event.type == WORK_LEASE_EXPIRED_EVENT:
            self._apply_lease_expiration(event)
            handled = True
        elif event.type == WORK_NODE_COMPLETED_EVENT:
            self._apply_completion(event)
            handled = True
        elif event.type == WORK_PLAN_INVALIDATED_EVENT:
            self._apply_invalidation(event)
            handled = True

        self._events[event.id] = event
        self._last_sequence = event.sequence
        return handled

    def rebuild(
        self,
        events: Iterable[Event],
        *,
        through_sequence: int | None = None,
    ) -> None:
        self._reset()
        for event in events:
            if through_sequence is not None and (event.sequence or 0) > through_sequence:
                continue
            self.apply(event)

    def _validate_lease_grant(self, lease: WorkLease) -> None:
        graph = self._graphs.get(lease.graph_id)
        if graph is None or not self.graph_is_active(lease.graph_id):
            raise ValueError("work lease requires an active work graph")
        node = graph.node(lease.node_id)
        if self.completed(graph.graph_id, node.node_id):
            raise ValueError("completed work cannot receive another lease")
        if self.active_lease_for_node(graph.graph_id, node.node_id) is not None:
            raise ValueError("work node already has an active lease")
        if any(
            not self.completed(graph.graph_id, predecessor_id)
            for predecessor_id in graph.predecessors(node.node_id)
        ):
            raise ValueError("work node dependencies are not complete")
        expected_token = self.next_fencing_token(graph.graph_id, node.node_id)
        if lease.fencing_token != expected_token:
            raise ValueError("work lease fencing token is not the next token")

        presence = self._presence.get(lease.agent_id)
        if (
            presence is None
            or presence.status is not PresenceStatus.AVAILABLE
            or not presence.is_valid_at(lease.granted_at)
        ):
            raise ValueError("work lease requires an available agent")
        if self.active_lease_count(lease.agent_id) >= presence.max_concurrency:
            raise ValueError("work lease exceeds agent concurrency capacity")
        manifest = self._manifests.get(lease.agent_id)
        if manifest is None or not set(node.required_capabilities).issubset(
            manifest.capabilities
        ):
            raise ValueError("work lease agent lacks a declared capability")
        estimates = tuple(
            self._competence.get((lease.agent_id, capability))
            for capability in node.required_capabilities
        )
        if any(value is None for value in estimates):
            raise ValueError("work lease requires competence estimates for every capability")
        typed_estimates = cast(tuple[CompetenceEstimate, ...], estimates)
        if any(value.basis is not CompetenceBasis.SEEDED for value in typed_estimates):
            raise ValueError("v0.5 work leases require seeded competence estimates")
        expected_refs = tuple(value.estimate_id for value in typed_estimates)
        if lease.competence_estimate_refs != expected_refs:
            raise ValueError("work lease competence evidence is not the current estimate set")
        expected_score = min(
            value.score * value.evidence_confidence for value in typed_estimates
        )
        if not math.isclose(lease.match_score, expected_score):
            raise ValueError("work lease match score is inconsistent with competence evidence")
        excluded_workers = {
            worker
            for target_id in node.verification_of
            if (worker := self.worker_for_node(graph.graph_id, target_id)) is not None
        }
        if lease.agent_id in excluded_workers:
            raise ValueError("verification work must use a worker independent of its target")
        self._validate_information_access(lease, node)

    def _validate_information_access(self, lease: WorkLease, node: WorkNode) -> None:
        if not node.governed_information_refs:
            if (
                lease.information_access_decision_refs
                or lease.information_disclosure_decision_refs
            ):
                raise ValueError("ungoverned work cannot cite information decisions")
            return
        if len(lease.information_access_decision_refs) != len(node.governed_information_refs):
            raise ValueError("work lease lacks complete information access evidence")
        decisions: list[InformationAccessDecision] = []
        decision_events: list[Event] = []
        for decision_id in lease.information_access_decision_refs:
            event = self._events.get(f"information-access-decided:{decision_id}")
            if event is None:
                raise ValueError("work lease cites a non-canonical access decision")
            decision_events.append(event)
            decision = InformationAccessDecision.from_event(event)
            if event.sequence != decision.causal_event_cursor + 1:
                raise ValueError("work lease access decision lacks exact-head admission")
            decisions.append(decision)
        if {value.request.information_ref.information_id for value in decisions} != set(
            node.governed_information_refs
        ):
            raise ValueError("work lease access evidence covers different information")
        if any(
            not value.allowed
            or value.request.context.operation is not InformationOperation.WORK_ASSIGN
            or value.request.context.principal.principal_id != lease.agent_id
            or value.request.context.recipient != lease.agent_id
            or value.decided_at != lease.granted_at
            for value in decisions
        ):
            raise ValueError("work lease information access evidence is inapplicable")
        crossing_ids = {
            value.request.information_ref.information_id
            for value in decisions
            if value.request.context.destination_trust_domain
            != value.request.context.source_trust_domain
        }
        if len(lease.information_disclosure_decision_refs) != len(crossing_ids):
            raise ValueError("work lease lacks required cross-domain disclosure evidence")
        disclosure_decisions: list[DisclosureDecision] = []
        for decision_id in lease.information_disclosure_decision_refs:
            event = self._events.get(f"information-disclosure-decided:{decision_id}")
            if event is None:
                raise ValueError("work lease cites a non-canonical disclosure decision")
            decision_events.append(event)
            disclosure_decision = DisclosureDecision.from_event(event)
            if event.sequence != disclosure_decision.causal_event_cursor + 1:
                raise ValueError("work lease disclosure decision lacks exact-head admission")
            disclosure_decisions.append(disclosure_decision)
        if {
            value.request.information_ref.information_id
            for value in disclosure_decisions
        } != crossing_ids:
            raise ValueError("work lease disclosure evidence covers different information")
        if any(
            not value.allowed
            or value.request.context.operation is not InformationOperation.WORK_ASSIGN
            or value.request.context.principal.principal_id != lease.agent_id
            or value.request.context.recipient != lease.agent_id
            or value.request.context.destination_trust_domain
            == value.request.context.source_trust_domain
            or value.decided_at != lease.granted_at
            for value in disclosure_decisions
        ):
            raise ValueError("work lease disclosure evidence is inapplicable")
        decision_cut = min(event.sequence or 0 for event in decision_events)
        if any(
            (event.sequence or 0) > decision_cut
            and event.type
            not in {INFORMATION_ACCESS_DECIDED_EVENT, DISCLOSURE_DECIDED_EVENT}
            for event in self._events.values()
        ):
            raise ValueError(
                "work lease access evidence is stale across an intervening canonical event"
            )

    def _apply_lease_expiration(self, event: Event) -> None:
        lease_id = str(event.payload["lease_id"])
        lease = self._leases.get(lease_id)
        if lease is None or self._lease_outcomes.get(lease_id) != "active":
            raise ValueError("lease expiration references a non-active lease")
        for key, expected in lease.to_dict().items():
            if event.payload.get(key) != expected:
                raise ValueError("lease expiration payload differs from the granted lease")
        expired_at = parse_datetime(cast(str | None, event.payload.get("expired_at")))
        if expired_at is None or event.timestamp != expired_at or expired_at < lease.expires_at:
            raise ValueError("lease expiration time is inconsistent")
        if event.id != f"work-lease-terminal:{lease.lease_id}":
            raise ValueError("lease expiration event id is inconsistent")
        if event.subject != lease.node_id:
            raise ValueError("lease expiration event subject is inconsistent")
        expected_cause = (
            f"work-lease-granted:{lease.graph_id}:{lease.node_id}:{lease.fencing_token}"
        )
        if event.causation_id != expected_cause:
            raise ValueError("lease expiration event causation is inconsistent")
        if not str(event.payload.get("reason", "")).strip():
            raise ValueError("lease expiration requires a reason")
        self._lease_outcomes[lease_id] = "expired"

    def _apply_completion(self, event: Event) -> None:
        lease_id = str(event.payload["lease_id"])
        lease = self._leases.get(lease_id)
        if lease is None or self._lease_outcomes.get(lease_id) != "active":
            raise ValueError("work completion requires an active lease")
        if not self.graph_is_active(lease.graph_id):
            raise ValueError("work completion cannot advance an invalidated graph")
        if event.id != f"work-lease-terminal:{lease.lease_id}":
            raise ValueError("work completion event id is inconsistent")
        if event.subject != lease.node_id:
            raise ValueError("work completion event subject is inconsistent")
        expected_cause = (
            f"work-lease-granted:{lease.graph_id}:{lease.node_id}:{lease.fencing_token}"
        )
        if event.causation_id != expected_cause:
            raise ValueError("work completion event causation is inconsistent")
        for key in ("graph_id", "node_id", "agent_id", "fencing_token"):
            if event.payload.get(key) != lease.to_dict()[key]:
                raise ValueError("work completion does not match its fenced lease")
        accepted_at = parse_datetime(cast(str | None, event.payload.get("accepted_at")))
        if (
            accepted_at is None
            or event.timestamp != accepted_at
            or accepted_at < lease.granted_at
            or accepted_at >= lease.expires_at
        ):
            raise ValueError("work completion acceptance time is outside the active lease")
        reported_finished_at = parse_datetime(
            cast(str | None, event.payload.get("reported_finished_at"))
        )
        artifact_values = cast(
            list[object] | tuple[object, ...],
            event.payload.get("artifact_refs", ()),
        )
        artifact_refs = tuple(str(value) for value in artifact_values)
        if (
            not artifact_refs
            or any(not value.strip() for value in artifact_refs)
            or len(set(artifact_refs)) != len(artifact_refs)
        ):
            raise ValueError("work completion requires unique non-empty artifact refs")
        verification_value = event.payload.get("verification_passed")
        verification_passed = (
            bool(verification_value) if verification_value is not None else None
        )
        node = cast(WorkGraph, self._graphs.get(lease.graph_id)).node(lease.node_id)
        if node.kind is WorkNodeKind.VERIFY and verification_passed is not True:
            raise ValueError("verification work completes only with an explicit passing result")
        if node.kind is not WorkNodeKind.VERIFY and verification_passed is not None:
            raise ValueError("non-verification work cannot claim a verification result")
        completion = NodeCompletion(
            graph_id=lease.graph_id,
            node_id=lease.node_id,
            agent_id=lease.agent_id,
            lease_id=lease.lease_id,
            fencing_token=lease.fencing_token,
            accepted_at=accepted_at,
            reported_finished_at=reported_finished_at,
            artifact_refs=artifact_refs,
            verification_passed=verification_passed,
        )
        self._completions[(lease.graph_id, lease.node_id)] = completion
        self._lease_outcomes[lease_id] = "completed"

    def _apply_invalidation(self, event: Event) -> None:
        graph_id = str(event.payload["graph_id"])
        graph = self._graphs.get(graph_id)
        if graph is None or not self.graph_is_active(graph_id):
            raise ValueError("plan invalidation requires an active graph")
        trigger_event_id = str(event.payload["trigger_event_id"])
        trigger = self._events.get(trigger_event_id)
        if trigger is None or trigger.sequence is None:
            raise ValueError("plan invalidation references an unknown canonical trigger")
        trigger_sequence = int(cast(int, event.payload["trigger_event_sequence"]))
        if trigger.sequence != trigger_sequence or trigger.type != str(
            event.payload["trigger_event_type"]
        ):
            raise ValueError("plan invalidation trigger identity is inconsistent")
        if trigger_sequence <= graph.based_on_event_cursor:
            raise ValueError("plan invalidation trigger does not follow the plan causal cut")
        if trigger.type not in graph.replan_event_types:
            raise ValueError("plan invalidation trigger is not a replan condition")
        invalidated_at = parse_datetime(cast(str | None, event.payload.get("invalidated_at")))
        if (
            invalidated_at is None
            or event.timestamp != invalidated_at
            or invalidated_at < trigger.timestamp
        ):
            raise ValueError("plan invalidation time is inconsistent")
        reason = str(event.payload["reason"])
        if not reason.strip():
            raise ValueError("plan invalidation requires a reason")
        expected_id = f"work-plan-invalidated:{graph.graph_id}:{trigger.id}"
        if event.id != expected_id or event.causation_id != trigger.id:
            raise ValueError("plan invalidation event identity is inconsistent")
        self._invalidations[graph_id] = PlanInvalidation(
            graph_id=graph_id,
            trigger_event_id=trigger.id,
            trigger_event_sequence=trigger_sequence,
            invalidated_at=invalidated_at,
            reason=reason,
        )


@dataclass(frozen=True, slots=True)
class ReadyFrontier:
    graph_id: str
    ready: tuple[WorkNode, ...]
    dependency_blocked: tuple[str, ...]
    epistemic_blocked: tuple[str, ...]
    leased: tuple[str, ...]
    completed: tuple[str, ...]
    invalidated: bool

    @classmethod
    def derive(
        cls,
        graph: WorkGraph,
        projection: WorkProjection,
        *,
        coverage: AwarenessCoverage | None = None,
    ) -> ReadyFrontier:
        if not projection.graph_is_active(graph.graph_id):
            return cls(
                graph_id=graph.graph_id,
                ready=(),
                dependency_blocked=(),
                epistemic_blocked=(),
                leased=(),
                completed=tuple(
                    node.node_id
                    for node in graph.nodes
                    if projection.completed(graph.graph_id, node.node_id)
                ),
                invalidated=True,
            )
        ready: list[WorkNode] = []
        dependency_blocked: list[str] = []
        epistemic_blocked: list[str] = []
        leased: list[str] = []
        completed: list[str] = []
        barrier = OrientationBarrier()
        order = projection.order(graph.work_order_id)
        if order is None:
            raise ValueError("ready frontier requires the graph work order")
        for node in graph.nodes:
            if projection.completed(graph.graph_id, node.node_id):
                completed.append(node.node_id)
                continue
            if projection.active_lease_for_node(graph.graph_id, node.node_id) is not None:
                leased.append(node.node_id)
                continue
            if any(
                not projection.completed(graph.graph_id, predecessor_id)
                for predecessor_id in graph.predecessors(node.node_id)
            ):
                dependency_blocked.append(node.node_id)
                continue
            requirements_by_source = {
                value.source_id: value for value in order.epistemic_prerequisites
            }
            for value in node.epistemic_prerequisites:
                current = requirements_by_source.get(value.source_id)
                if current is None:
                    requirements_by_source[value.source_id] = value
                else:
                    requirements_by_source[value.source_id] = type(value)(
                        source_id=value.source_id,
                        minimum_freshness=max(
                            current.minimum_freshness,
                            value.minimum_freshness,
                        ),
                        minimum_confidence=max(
                            current.minimum_confidence,
                            value.minimum_confidence,
                        ),
                    )
            epistemic_prerequisites = tuple(
                requirements_by_source[key] for key in sorted(requirements_by_source)
            )
            if epistemic_prerequisites:
                if coverage is None or barrier.evaluate(
                    node.node_id,
                    epistemic_prerequisites,
                    coverage,
                ).would_block:
                    epistemic_blocked.append(node.node_id)
                    continue
            ready.append(node)
        return cls(
            graph_id=graph.graph_id,
            ready=tuple(ready),
            dependency_blocked=tuple(dependency_blocked),
            epistemic_blocked=tuple(epistemic_blocked),
            leased=tuple(leased),
            completed=tuple(completed),
            invalidated=False,
        )


@dataclass(frozen=True, slots=True)
class WorkerMatch:
    node_id: str
    agent_id: str
    score: float
    competence_estimate_refs: tuple[str, ...]
    information_access_decisions: tuple[InformationAccessDecision, ...] = ()
    information_disclosure_decisions: tuple[DisclosureDecision, ...] = ()


class WorkerAccessEvaluator(Protocol):
    """Evaluate governed inputs before a worker becomes assignment-feasible."""

    def evaluate(
        self,
        graph: WorkGraph,
        node: WorkNode,
        agent_id: str,
        *,
        at: datetime,
    ) -> tuple[InformationAccessDecision | DisclosureDecision, ...]: ...


class WorkerMatcher:
    """Choose a feasible seeded worker; it does not authorize execution."""

    def __init__(self, access_evaluator: WorkerAccessEvaluator | None = None) -> None:
        self.access_evaluator = access_evaluator

    def match(
        self,
        graph: WorkGraph,
        node: WorkNode,
        projection: WorkProjection,
        *,
        at: datetime,
    ) -> WorkerMatch | None:
        match, _ = self.match_with_access_evidence(
            graph,
            node,
            projection,
            at=at,
        )
        return match

    def match_with_access_evidence(
        self,
        graph: WorkGraph,
        node: WorkNode,
        projection: WorkProjection,
        *,
        at: datetime,
    ) -> tuple[
        WorkerMatch | None,
        tuple[InformationAccessDecision | DisclosureDecision, ...],
    ]:
        if at.tzinfo is None:
            raise ValueError("worker matching time must be timezone-aware")
        candidates: list[WorkerMatch] = []
        access_evidence: list[InformationAccessDecision | DisclosureDecision] = []
        excluded_workers = {
            worker
            for target_id in node.verification_of
            if (worker := projection.worker_for_node(graph.graph_id, target_id)) is not None
        }
        for presence in projection.presences:
            if (
                presence.status is not PresenceStatus.AVAILABLE
                or not presence.is_valid_at(at)
            ):
                continue
            if presence.agent_id in excluded_workers:
                continue
            if projection.active_lease_count(presence.agent_id) >= presence.max_concurrency:
                continue
            manifest = projection.manifest(presence.agent_id)
            if manifest is None or not set(node.required_capabilities).issubset(
                manifest.capabilities
            ):
                continue
            estimates = tuple(
                projection.competence(presence.agent_id, capability)
                for capability in node.required_capabilities
            )
            if any(value is None for value in estimates):
                continue
            typed_estimates = cast(tuple[CompetenceEstimate, ...], estimates)
            if any(value.basis is not CompetenceBasis.SEEDED for value in typed_estimates):
                continue
            access_decisions: tuple[InformationAccessDecision, ...] = ()
            disclosure_decisions: tuple[DisclosureDecision, ...] = ()
            if node.governed_information_refs:
                if self.access_evaluator is None:
                    continue
                evaluated = self.access_evaluator.evaluate(
                    graph,
                    node,
                    presence.agent_id,
                    at=at,
                )
                access_evidence.extend(evaluated)
                access_decisions = tuple(
                    value for value in evaluated if isinstance(value, InformationAccessDecision)
                )
                disclosure_decisions = tuple(
                    value for value in evaluated if isinstance(value, DisclosureDecision)
                )
                if not self._access_is_feasible(
                    node,
                    presence.agent_id,
                    at,
                    access_decisions,
                    disclosure_decisions,
                ):
                    continue
            candidates.append(
                WorkerMatch(
                    node_id=node.node_id,
                    agent_id=presence.agent_id,
                    score=min(
                        value.score * value.evidence_confidence
                        for value in typed_estimates
                    ),
                    competence_estimate_refs=tuple(
                        value.estimate_id for value in typed_estimates
                    ),
                    information_access_decisions=access_decisions,
                    information_disclosure_decisions=disclosure_decisions,
                )
            )
        if not candidates:
            return None, tuple(access_evidence)
        candidates.sort(key=lambda value: (-value.score, value.agent_id))
        return candidates[0], tuple(access_evidence)

    @staticmethod
    def _access_is_feasible(
        node: WorkNode,
        agent_id: str,
        at: datetime,
        access_decisions: tuple[InformationAccessDecision, ...],
        disclosure_decisions: tuple[DisclosureDecision, ...],
    ) -> bool:
        governed_ids = set(node.governed_information_refs)
        if (
            len(access_decisions) != len(governed_ids)
            or {value.request.information_ref.information_id for value in access_decisions}
            != governed_ids
            or not all(
                value.allowed
                and value.request.context.operation is InformationOperation.WORK_ASSIGN
                and value.request.context.principal.principal_id == agent_id
                and value.request.context.recipient == agent_id
                and value.decided_at == at
                for value in access_decisions
            )
        ):
            return False
        crossing_ids = {
            value.request.information_ref.information_id
            for value in access_decisions
            if value.request.context.destination_trust_domain
            != value.request.context.source_trust_domain
        }
        return (
            len(disclosure_decisions) == len(crossing_ids)
            and {
                value.request.information_ref.information_id
                for value in disclosure_decisions
            }
            == crossing_ids
            and all(
                value.allowed
                and value.request.context.operation is InformationOperation.WORK_ASSIGN
                and value.request.context.principal.principal_id == agent_id
                and value.request.context.recipient == agent_id
                and value.request.context.destination_trust_domain
                != value.request.context.source_trust_domain
                and value.decided_at == at
                for value in disclosure_decisions
            )
        )


class DurableWorkCoordinator:
    """Command facade that rebuilds from history before every state transition."""

    def __init__(
        self,
        kernel: NoemaKernel,
        *,
        planner: Planner,
        validator: PlanValidator | None = None,
        matcher: WorkerMatcher | None = None,
        information_projection: InformationGovernanceProjection | None = None,
        lease_duration: timedelta = timedelta(minutes=30),
        clock: Callable[[], datetime] = utc_now,
        source: str = "work:coordinator",
    ) -> None:
        if lease_duration.total_seconds() <= 0:
            raise ValueError("work lease duration must be positive")
        if not source.strip():
            raise ValueError("work coordinator source must be non-empty")
        self.kernel = kernel
        self.planner = planner
        self.validator = validator or PlanValidator()
        self.matcher = matcher or WorkerMatcher()
        if (
            self.matcher.access_evaluator is not None
            and information_projection is None
        ):
            raise ValueError(
                "governed worker matching requires a canonical governance projection"
            )
        evaluator_state = getattr(
            self.matcher.access_evaluator,
            "governance_state",
            information_projection,
        )
        if (
            information_projection is not None
            and evaluator_state is not information_projection
        ):
            raise ValueError(
                "worker access evaluator must share the coordinator governance projection"
            )
        self.information_projection = information_projection
        self.information_admission = (
            InformationGovernanceAdmission(
                kernel,
                information_projection,
                source=source,
            )
            if information_projection is not None
            else None
        )
        self.lease_duration = lease_duration
        self.clock = clock
        self.source = source
        self.projection = WorkProjection()

    async def record_work_order(self, order: WorkOrder) -> WorkOrder:
        await self._reload()
        stored = await self._emit(order.to_event(source=self.source))
        return WorkOrder.from_event(stored)

    async def record_presence(self, presence: AgentPresence) -> AgentPresence:
        await self._reload()
        stored = await self._emit(presence.to_event(source=self.source))
        return AgentPresence.from_event(stored)

    async def record_manifest(self, manifest: CapabilityManifest) -> CapabilityManifest:
        await self._reload()
        stored = await self._emit(manifest.to_event(source=self.source))
        return CapabilityManifest.from_event(stored)

    async def record_competence(
        self, estimate: CompetenceEstimate
    ) -> CompetenceEstimate:
        if estimate.basis is not CompetenceBasis.SEEDED:
            raise ValueError("evidence-based competence is non-operational in v0.5")
        await self._reload()
        stored = await self._emit(estimate.to_event(source=self.source))
        return CompetenceEstimate.from_event(stored)

    async def plan(self, work_order_id: str) -> WorkGraph:
        await self._reload()
        order = self.projection.order(work_order_id)
        if order is None:
            raise KeyError(f"unknown work order: {work_order_id}")
        current = self.projection.latest_graph(work_order_id)
        current_version = current.version if current is not None else 0
        causal_cursor = self.projection.event_cursor
        capability_types = self.projection.available_capability_types()
        proposal = await self.planner.propose(
            order,
            based_on_event_cursor=causal_cursor,
            based_on_graph_version=current_version,
            available_capability_types=capability_types,
        )
        await self._reload()
        proposal_event = await self._emit(
            proposal.to_event(
                source=self.source,
                causation_id=f"work-order-recorded:{order.work_order_id}",
            )
        )
        while True:
            await self._reload()
            current = self.projection.latest_graph(work_order_id)
            acceptance_version = current.version if current is not None else 0
            acceptance_cursor = self.projection.event_cursor
            graph = self.validator.validate(
                proposal,
                order,
                causal_event_cursor=causal_cursor,
                acceptance_event_cursor=acceptance_cursor,
                current_graph_version=acceptance_version,
                available_capability_types=self.projection.available_capability_types(
                    through_sequence=causal_cursor
                ),
                intervening_events=self.projection.events_after(causal_cursor),
                accepted_at=self.clock(),
            )
            try:
                graph_event = await self._append_graph_if_head(
                    graph.to_event(source=self.source, causation_id=proposal_event.id),
                    expected_head_sequence=acceptance_cursor,
                )
            except ConcurrentAppendError:
                continue
            return WorkGraph.from_event(graph_event)

    async def frontier(
        self,
        work_order_id: str,
        *,
        coverage: AwarenessCoverage | None = None,
    ) -> ReadyFrontier:
        await self._reload()
        graph = self.projection.latest_graph(work_order_id)
        if graph is None:
            raise KeyError(f"work order has no accepted graph: {work_order_id}")
        return ReadyFrontier.derive(graph, self.projection, coverage=coverage)

    async def assign_ready(
        self,
        work_order_id: str,
        *,
        coverage: AwarenessCoverage | None = None,
    ) -> tuple[WorkLease, ...]:
        await self._reload()
        graph = self.projection.latest_graph(work_order_id)
        if graph is None:
            raise KeyError(f"work order has no accepted graph: {work_order_id}")
        frontier = ReadyFrontier.derive(graph, self.projection, coverage=coverage)
        assigned: list[WorkLease] = []
        at = self.clock()
        for node in frontier.ready:
            match, access_evidence = self.matcher.match_with_access_evidence(
                graph,
                node,
                self.projection,
                at=at,
            )
            selected_decision_ids: set[str] = set()
            if match is not None:
                selected_decision_ids.update(
                    value.decision_id for value in match.information_access_decisions
                )
                selected_decision_ids.update(
                    value.decision_id for value in match.information_disclosure_decisions
                )
            material_decisions = tuple(
                value
                for value in access_evidence
                if not value.allowed or value.decision_id in selected_decision_ids
            )
            expected_head = self.projection.event_cursor
            admitted_access: list[InformationAccessDecision] = []
            admitted_disclosure: list[DisclosureDecision] = []
            for decision in material_decisions:
                if self.information_admission is None:
                    raise AssertionError("governed matching lost its admission facade")
                if isinstance(decision, InformationAccessDecision):
                    access_receipt = await self.information_admission.admit_access(
                        decision.request,
                        expected_disposition=decision.policy_decision.disposition,
                        expected_causal_cursor=expected_head,
                    )
                    admitted = access_receipt.record
                    if decision.decision_id in selected_decision_ids:
                        admitted_access.append(admitted)
                    canonical_event = access_receipt.canonical_event
                    canonical_sequence = access_receipt.canonical_sequence
                else:
                    disclosure_receipt = await self.information_admission.admit_disclosure(
                        decision.request,
                        expected_disposition=decision.policy_decision.disposition,
                        expected_causal_cursor=expected_head,
                    )
                    admitted_disclosure_record = disclosure_receipt.record
                    if decision.decision_id in selected_decision_ids:
                        admitted_disclosure.append(admitted_disclosure_record)
                    canonical_event = disclosure_receipt.canonical_event
                    canonical_sequence = disclosure_receipt.canonical_sequence
                self.projection.apply(canonical_event)
                expected_head = canonical_sequence
            if match is None:
                continue
            lease = WorkLease.create(
                graph_id=graph.graph_id,
                node_id=node.node_id,
                agent_id=match.agent_id,
                fencing_token=self.projection.next_fencing_token(graph.graph_id, node.node_id),
                granted_at=at,
                lease_duration=self.lease_duration,
                match_score=match.score,
                competence_estimate_refs=match.competence_estimate_refs,
                information_access_decision_refs=tuple(
                    value.decision_id for value in admitted_access
                ),
                information_disclosure_decision_refs=tuple(
                    value.decision_id for value in admitted_disclosure
                ),
            )
            lease_event = lease.to_event(
                source=self.source,
                causation_id=f"work-graph-accepted:{graph.graph_id}",
            )
            if material_decisions:
                stored = await self._emit_if_head(
                    lease_event,
                    expected_head_sequence=expected_head,
                )
            else:
                stored = await self._emit(lease_event)
            assigned.append(WorkLease.from_event(stored))
        return tuple(assigned)

    async def complete(
        self,
        lease_id: str,
        *,
        fencing_token: int,
        artifact_refs: tuple[str, ...],
        reported_finished_at: datetime | None = None,
        verification_passed: bool | None = None,
    ) -> NodeCompletion:
        await self._reload()
        lease = self.projection.active_lease(lease_id)
        if lease is None:
            raise ValueError("work completion requires an active lease")
        if lease.fencing_token != fencing_token:
            raise ValueError("stale work lease fencing token")
        stored = await self._emit(
            lease.completion_event(
                source=self.source,
                accepted_at=self.clock(),
                artifact_refs=artifact_refs,
                reported_finished_at=reported_finished_at,
                verification_passed=verification_passed,
            )
        )
        del stored
        completion = self.projection.completion(lease.graph_id, lease.node_id)
        if completion is None:
            raise AssertionError("canonical completion was not projected")
        return completion

    async def recover_expired(
        self,
        *,
        at: datetime | None = None,
    ) -> tuple[WorkLease, ...]:
        await self._reload()
        expired_at = at or self.clock()
        expired = tuple(
            value for value in self.projection.active_leases if value.expires_at <= expired_at
        )
        for lease in expired:
            await self._emit(
                lease.expiration_event(
                    source=self.source,
                    expired_at=expired_at,
                    reason="lease deadline elapsed without canonical completion",
                )
            )
        return expired

    async def invalidate_for(
        self,
        trigger: Event,
        *,
        reason: str,
        invalidated_at: datetime | None = None,
    ) -> tuple[WorkGraph, ...]:
        await self._reload()
        canonical = next(
            (event for event in await self.kernel.history() if event.id == trigger.id),
            None,
        )
        if canonical is None or canonical != trigger:
            raise ValueError("plan invalidation requires the canonical trigger event")
        invalidated: list[WorkGraph] = []
        at = invalidated_at or self.clock()
        for graph in self.projection.graphs:
            if (
                self.projection.graph_is_active(graph.graph_id)
                and trigger.type in graph.replan_event_types
                and (trigger.sequence or 0) > graph.based_on_event_cursor
            ):
                await self._emit(
                    plan_invalidation_event(
                        graph,
                        trigger,
                        source=self.source,
                        invalidated_at=at,
                        reason=reason,
                    )
                )
                invalidated.append(graph)
        return tuple(invalidated)

    async def _reload(self) -> None:
        history = await self.kernel.history()
        self.projection.rebuild(history)
        if self.information_projection is not None:
            self.information_projection.rebuild(history)

    async def _emit(self, event: Event) -> Event:
        stored = await self.kernel.emit(event)
        if replace(stored, sequence=None) != event:
            raise ValueError(f"canonical event id conflict: {event.id}")
        self.projection.apply(stored)
        if self.information_projection is not None:
            self.information_projection.apply(stored)
        return stored

    async def _emit_if_head(
        self,
        event: Event,
        *,
        expected_head_sequence: int,
    ) -> Event:
        stored = await self.kernel.emit_if_head(
            event,
            expected_head_sequence=expected_head_sequence,
        )
        if replace(stored, sequence=None) != event:
            raise ValueError(f"canonical event id conflict: {event.id}")
        self.projection.apply(stored)
        if self.information_projection is not None:
            self.information_projection.apply(stored)
        return stored

    async def _append_graph_if_head(
        self,
        event: Event,
        *,
        expected_head_sequence: int,
    ) -> Event:
        stored = await self.kernel.emit_if_head(
            event,
            expected_head_sequence=expected_head_sequence,
        )
        if replace(stored, sequence=None) != event:
            raise ValueError(f"canonical event id conflict: {event.id}")
        self.projection.apply(stored)
        if self.information_projection is not None:
            self.information_projection.apply(stored)
        return stored
