"""Rebuildable strategic history, coverage, and health projections."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime
from typing import TypeVar, cast

from ..events import Event
from ..situation import Commitment, CommitmentClosureReason, CommitmentStatus, GoalStatus
from ..work.models import WORK_GRAPH_ACCEPTED_EVENT, WORK_ORDER_RECORDED_EVENT, WorkGraph, WorkOrder
from .models import (
    ASSISTANCE_ENVELOPE_RECORDED_EVENT,
    COMMITMENT_RECORDED_EVENT,
    COMMITMENT_TRANSITIONED_EVENT,
    EXTERNAL_WORKSTREAM_OBSERVED_EVENT,
    GOAL_REVISION_RECORDED_EVENT,
    OUTCOME_ROLES_RECORDED_EVENT,
    ROADMAP_REVISION_RECORDED_EVENT,
    WORK_ORDER_PROPOSED_EVENT,
    AssistanceEnvelope,
    CommitmentCoverage,
    CommitmentTransition,
    CoverageDisposition,
    ExternalWorkstream,
    GoalKind,
    GoalRevision,
    HealthSignal,
    IntentAuthority,
    OriginProvenance,
    OutcomeRoleAssignment,
    Roadmap,
    RoadmapHealth,
    RoadmapRevision,
    WorkOrderProposal,
    commitment_from_dict,
)
from .schemas import is_legacy_intent_event, legacy_context

T = TypeVar("T")


class StrategicProjection:
    """Project immutable strategic history from one canonical event cut."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._events: dict[str, Event] = {}
        self._last_sequence = 0
        self._goal_revisions: dict[str, GoalRevision] = {}
        self._goal_history: dict[str, list[str]] = {}
        self._current_goal_revision: dict[str, str] = {}
        self._roadmap_revisions: dict[str, RoadmapRevision] = {}
        self._roadmap_history: dict[str, list[str]] = {}
        self._current_roadmap_revision: dict[str, str] = {}
        self._commitments: dict[str, Commitment] = {}
        self._commitment_versions: dict[str, list[Commitment]] = {}
        self._commitment_transitions: dict[str, list[CommitmentTransition]] = {}
        self._roles: dict[str, OutcomeRoleAssignment] = {}
        self._assistance: dict[str, AssistanceEnvelope] = {}
        self._external_history: dict[str, list[ExternalWorkstream]] = {}
        self._external_current: dict[str, ExternalWorkstream] = {}
        self._work_proposals: dict[str, WorkOrderProposal] = {}
        self._admitted_work_orders: dict[str, WorkOrder] = {}
        self._work_graph_ids: set[str] = set()

    @property
    def event_cursor(self) -> int:
        return self._last_sequence

    @property
    def goal_revisions(self) -> tuple[GoalRevision, ...]:
        return tuple(
            self._goal_revisions[key]
            for key in sorted(
                self._goal_revisions,
                key=lambda value: (
                    self._goal_revisions[value].goal_id,
                    self._goal_revisions[value].version,
                    value,
                ),
            )
        )

    @property
    def roadmap_revisions(self) -> tuple[RoadmapRevision, ...]:
        return tuple(
            self._roadmap_revisions[key]
            for key in sorted(
                self._roadmap_revisions,
                key=lambda value: (
                    self._roadmap_revisions[value].roadmap_id,
                    self._roadmap_revisions[value].version,
                    value,
                ),
            )
        )

    @property
    def commitments(self) -> tuple[Commitment, ...]:
        return tuple(self._commitments[key] for key in sorted(self._commitments))

    @property
    def work_proposals(self) -> tuple[WorkOrderProposal, ...]:
        return tuple(self._work_proposals[key] for key in sorted(self._work_proposals))

    @property
    def external_workstreams(self) -> tuple[ExternalWorkstream, ...]:
        return tuple(self._external_current[key] for key in sorted(self._external_current))

    @property
    def work_graph_ids(self) -> frozenset[str]:
        return frozenset(self._work_graph_ids)

    def current_goal_revision(self, goal_id: str) -> GoalRevision | None:
        revision_id = self._current_goal_revision.get(goal_id)
        return self._goal_revisions.get(revision_id) if revision_id else None

    def goal_revision(self, revision_id: str) -> GoalRevision | None:
        return self._goal_revisions.get(revision_id)

    def goal_history(self, goal_id: str) -> tuple[GoalRevision, ...]:
        return tuple(self._goal_revisions[value] for value in self._goal_history.get(goal_id, ()))

    def roadmap_revision(self, revision_id: str) -> RoadmapRevision | None:
        return self._roadmap_revisions.get(revision_id)

    def current_roadmap_revision(self, roadmap_id: str) -> RoadmapRevision | None:
        revision_id = self._current_roadmap_revision.get(roadmap_id)
        return self._roadmap_revisions.get(revision_id) if revision_id else None

    def roadmap(self, roadmap_id: str) -> Roadmap | None:
        revision = self.current_roadmap_revision(roadmap_id)
        if revision is None:
            return None
        return Roadmap(roadmap_id, revision.revision_id, revision.version)

    def roadmap_history(self, roadmap_id: str) -> tuple[RoadmapRevision, ...]:
        return tuple(
            self._roadmap_revisions[value] for value in self._roadmap_history.get(roadmap_id, ())
        )

    def commitment(self, commitment_id: str) -> Commitment | None:
        return self._commitments.get(commitment_id)

    def commitment_history(self, commitment_id: str) -> tuple[Commitment, ...]:
        return tuple(self._commitment_versions.get(commitment_id, ()))

    def commitment_transitions(self, commitment_id: str) -> tuple[CommitmentTransition, ...]:
        return tuple(self._commitment_transitions.get(commitment_id, ()))

    def role_assignment(self, assignment_id: str) -> OutcomeRoleAssignment | None:
        return self._roles.get(assignment_id)

    def assistance_envelope(self, envelope_id: str) -> AssistanceEnvelope | None:
        return self._assistance.get(envelope_id)

    def work_proposal(self, proposal_id: str) -> WorkOrderProposal | None:
        return self._work_proposals.get(proposal_id)

    def admitted_work_order(self, work_order_id: str) -> WorkOrder | None:
        return self._admitted_work_orders.get(work_order_id)

    def external_history(self, workstream_id: str) -> tuple[ExternalWorkstream, ...]:
        return tuple(self._external_history.get(workstream_id, ()))

    def apply(self, event: Event) -> bool:
        existing = self._events.get(event.id)
        if existing is not None:
            if existing != event:
                raise ValueError(f"conflicting canonical strategic event identity: {event.id}")
            return False
        if event.sequence is None:
            raise ValueError("strategic projection requires canonical sequenced events")
        if event.sequence <= self._last_sequence:
            raise ValueError("strategic events must be applied in canonical sequence order")

        handled = self._apply_event(event)
        self._events[event.id] = event
        self._last_sequence = event.sequence
        return handled

    def rebuild(self, events: Iterable[Event]) -> None:
        self._reset()
        for event in events:
            self.apply(event)

    def _apply_event(self, event: Event) -> bool:
        if is_legacy_intent_event(event):
            return self._apply_legacy(event)
        if event.type == GOAL_REVISION_RECORDED_EVENT:
            goal_revision = GoalRevision.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=f"goal-revision-recorded:{goal_revision.revision_id}",
                subject=goal_revision.goal_id,
                timestamp=goal_revision.recorded_at,
                based_on_event_cursor=goal_revision.based_on_event_cursor,
            )
            self._record_goal_revision(goal_revision, event)
            return True
        if event.type == ROADMAP_REVISION_RECORDED_EVENT:
            roadmap_revision = RoadmapRevision.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=(f"roadmap-revision-recorded:{roadmap_revision.revision_id}"),
                subject=roadmap_revision.roadmap_id,
                timestamp=roadmap_revision.recorded_at,
                based_on_event_cursor=roadmap_revision.based_on_event_cursor,
            )
            self._record_roadmap_revision(roadmap_revision, event)
            return True
        if event.type == COMMITMENT_RECORDED_EVENT:
            commitment = commitment_from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=f"commitment-recorded:{commitment.id}",
                subject=commitment.id,
                timestamp=commitment.created_at,
            )
            self._record_commitment(commitment, event)
            return True
        if event.type == COMMITMENT_TRANSITIONED_EVENT:
            transition = CommitmentTransition.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=f"commitment-transitioned:{transition.transition_id}",
                subject=transition.commitment_id,
                timestamp=transition.transitioned_at,
                based_on_event_cursor=transition.based_on_event_cursor,
            )
            self._record_transition(transition, event)
            return True
        if event.type == OUTCOME_ROLES_RECORDED_EVENT:
            roles = OutcomeRoleAssignment.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=f"outcome-roles-recorded:{roles.assignment_id}",
                subject=roles.outcome_ref,
                timestamp=roles.recorded_at,
            )
            self._record_immutable(self._roles, roles.assignment_id, roles, "outcome roles")
            return True
        if event.type == ASSISTANCE_ENVELOPE_RECORDED_EVENT:
            envelope = AssistanceEnvelope.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=f"assistance-envelope-recorded:{envelope.envelope_id}",
                subject=envelope.role_assignment_id,
                timestamp=envelope.recorded_at,
            )
            if envelope.role_assignment_id not in self._roles:
                raise ValueError("assistance envelope references unknown outcome roles")
            self._record_immutable(self._assistance, envelope.envelope_id, envelope, "assistance")
            return True
        if event.type == EXTERNAL_WORKSTREAM_OBSERVED_EVENT:
            observation = ExternalWorkstream.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=(f"external-workstream-observed:{observation.observation_id}"),
                subject=observation.workstream_id,
                timestamp=observation.recorded_at,
            )
            if (
                observation.observed_roadmap_ref.startswith("work-graph:")
                or observation.observed_roadmap_ref in self._work_graph_ids
            ):
                raise ValueError("external roadmap id cannot be a Noema work graph id")
            history = self._external_history.setdefault(observation.workstream_id, [])
            if history and observation.recorded_at < history[-1].recorded_at:
                raise ValueError("external workstream knowledge time cannot regress")
            if any(item.observation_id == observation.observation_id for item in history):
                raise ValueError("external observation id changed")
            history.append(observation)
            self._external_current[observation.workstream_id] = observation
            return True
        if event.type == WORK_ORDER_PROPOSED_EVENT:
            proposal = WorkOrderProposal.from_dict(event.payload)
            self._validate_native_envelope(
                event,
                expected_id=f"work-order-proposed:{proposal.proposal_id}",
                subject=proposal.commitment_id,
                timestamp=proposal.proposed_at,
                based_on_event_cursor=proposal.based_on_event_cursor,
            )
            self._record_immutable(
                self._work_proposals,
                proposal.proposal_id,
                proposal,
                "work order proposal",
            )
            return True
        if event.type == WORK_ORDER_RECORDED_EVENT:
            order = WorkOrder.from_event(event)
            self._record_immutable(
                self._admitted_work_orders, order.work_order_id, order, "work order"
            )
            return True
        if event.type == WORK_GRAPH_ACCEPTED_EVENT:
            self._work_graph_ids.add(WorkGraph.from_event(event).graph_id)
            return True
        return False

    @staticmethod
    def _record_immutable(values: dict[str, T], key: str, value: T, label: str) -> None:
        existing = values.get(key)
        if existing is not None and existing != value:
            raise ValueError(f"{label} changed in place: {key}")
        values[key] = value

    def _validate_native_envelope(
        self,
        event: Event,
        *,
        expected_id: str,
        subject: str,
        timestamp: datetime,
        based_on_event_cursor: int | None = None,
    ) -> None:
        if event.id != expected_id or event.subject != subject or event.timestamp != timestamp:
            raise ValueError("strategic event envelope is inconsistent")
        validated_cursor = event.metadata.get("validated_at_event_cursor")
        # Durable store sequences may contain gaps after rolled-back inserts.
        # The exact causal cut is the preceding canonical head we projected,
        # not an arithmetic assumption about the next sequence value.
        expected_cursor = self._last_sequence
        if validated_cursor != expected_cursor:
            raise ValueError("strategic event lacks exact-head admission evidence")
        if based_on_event_cursor is not None and validated_cursor != based_on_event_cursor:
            raise ValueError("strategic event cursor differs from admitted content")

    def _record_goal_revision(self, revision: GoalRevision, event: Event) -> None:
        subject_matches = event.subject == revision.goal_id or (
            is_legacy_intent_event(event) and event.subject is None
        )
        if not subject_matches or event.timestamp != revision.recorded_at:
            raise ValueError("goal revision event envelope is inconsistent")
        current = self.current_goal_revision(revision.goal_id)
        expected_version = current.version + 1 if current else 1
        expected_supersedes = current.revision_id if current else None
        if (
            revision.version != expected_version
            or revision.supersedes_revision_id != expected_supersedes
        ):
            raise ValueError("goal revision does not extend immutable history")
        if revision.based_on_event_cursor >= cast(int, event.sequence):
            raise ValueError("goal revision cursor must precede its canonical event")
        self._record_immutable(
            self._goal_revisions, revision.revision_id, revision, "goal revision"
        )
        self._goal_history.setdefault(revision.goal_id, []).append(revision.revision_id)
        self._current_goal_revision[revision.goal_id] = revision.revision_id

    def _record_roadmap_revision(self, revision: RoadmapRevision, event: Event) -> None:
        if event.subject != revision.roadmap_id or event.timestamp != revision.recorded_at:
            raise ValueError("roadmap revision event envelope is inconsistent")
        current = self.current_roadmap_revision(revision.roadmap_id)
        expected_version = current.version + 1 if current else 1
        expected_supersedes = current.revision_id if current else None
        if (
            revision.version != expected_version
            or revision.supersedes_revision_id != expected_supersedes
        ):
            raise ValueError("roadmap revision does not extend immutable history")
        if revision.based_on_event_cursor >= cast(int, event.sequence):
            raise ValueError("roadmap revision cursor must precede its canonical event")
        self._record_immutable(
            self._roadmap_revisions, revision.revision_id, revision, "roadmap revision"
        )
        self._roadmap_history.setdefault(revision.roadmap_id, []).append(revision.revision_id)
        self._current_roadmap_revision[revision.roadmap_id] = revision.revision_id

    def _record_commitment(self, value: Commitment, event: Event) -> None:
        if event.subject != value.id or event.timestamp != value.created_at:
            raise ValueError("commitment event envelope is inconsistent")
        existing = self._commitments.get(value.id)
        if existing is not None and existing != value:
            raise ValueError(f"commitment identity changed: {value.id}")
        self._commitments[value.id] = value
        self._commitment_versions.setdefault(value.id, []).append(value)

    def _record_transition(self, transition: CommitmentTransition, event: Event) -> None:
        current = self._commitments.get(transition.commitment_id)
        if current is None:
            raise ValueError("commitment transition references unknown commitment")
        if event.subject != current.id or event.timestamp != transition.transitioned_at:
            raise ValueError("commitment transition event envelope is inconsistent")
        if current.status != transition.from_state:
            raise ValueError("commitment transition does not start at current state")
        updated = replace(
            current,
            status=transition.to_state,
            closure_reason=transition.closure_reason,
            roadmap_revision_id=(
                transition.reactivation_roadmap_revision_id or current.roadmap_revision_id
            ),
            updated_at=transition.transitioned_at,
        )
        self._commitments[current.id] = updated
        self._commitment_versions.setdefault(current.id, []).append(updated)
        self._commitment_transitions.setdefault(current.id, []).append(transition)

    def _apply_legacy(self, event: Event) -> bool:
        context = legacy_context(event)
        operation = str(context["operation"])
        if event.type.startswith("goal."):
            return self._apply_legacy_goal(event, operation, context)
        if event.type.startswith("commitment."):
            return self._apply_legacy_commitment(event, operation)
        return False

    def _apply_legacy_goal(
        self, event: Event, operation: str, context: Mapping[str, object]
    ) -> bool:
        goal_id = str(event.payload.get("id") or event.subject or event.id)
        current = self.current_goal_revision(goal_id)
        if operation == "patch" and current is None:
            return False
        origin = (
            current.origin
            if current
            else OriginProvenance.from_dict(cast(Mapping[str, object], context["origin"]))
        )
        authority = (
            current.intent_authority
            if current
            else IntentAuthority.from_dict(cast(Mapping[str, object], context["intent_authority"]))
        )
        payload = event.payload
        revision = GoalRevision.create(
            goal_id=goal_id,
            version=current.version + 1 if current else 1,
            description=str(payload.get("description", current.description if current else "")),
            priority=_float_value(payload.get("priority", current.priority if current else 0.5)),
            utility=_float_value(payload.get("utility", current.utility if current else 1.0)),
            success_criteria=_string_values(
                payload.get("success_criteria", current.success_criteria if current else ())
            ),
            owner=str(payload.get("owner", current.owner if current else event.source)),
            status=GoalStatus(str(payload.get("status", current.status if current else "active"))),
            kind=current.kind if current else GoalKind.LEGACY_UNCLASSIFIED,
            origin=origin,
            intent_authority=authority,
            based_on_event_cursor=max(0, cast(int, event.sequence) - 1),
            author=event.source,
            revision_reason=f"deterministic migration of {event.type}",
            recorded_at=event.timestamp,
            supersedes_revision_id=current.revision_id if current else None,
        )
        self._record_goal_revision(revision, event)
        return True

    def _apply_legacy_commitment(self, event: Event, operation: str) -> bool:
        commitment_id = str(event.payload.get("id") or event.subject or event.id)
        current = self._commitments.get(commitment_id)
        if operation != "create" and current is None:
            return False
        if current is None:
            data: dict[str, object] = dict(event.payload)
            data.update(
                {
                    "id": commitment_id,
                    "created_at": event.timestamp,
                    "updated_at": event.timestamp,
                }
            )
            value = commitment_from_dict(data)
            self._commitments[value.id] = value
            self._commitment_versions.setdefault(value.id, []).append(value)
            return True
        status = CommitmentStatus(str(event.payload.get("status", current.status)))
        closure_value = event.payload.get("closure_reason", current.closure_reason)
        closure = (
            closure_value
            if isinstance(closure_value, CommitmentClosureReason)
            else CommitmentClosureReason(str(closure_value))
            if closure_value is not None
            else None
        )
        updated = replace(
            current,
            description=str(event.payload.get("description", current.description)),
            owner=str(event.payload.get("owner", current.owner)),
            priority=_float_value(event.payload.get("priority", current.priority)),
            status=status,
            deadline=(
                current.deadline
                if "deadline" not in event.payload
                else _parse_optional_datetime(event.payload["deadline"])
            ),
            terminal=bool(event.payload.get("terminal", current.terminal)),
            attention_cost=_float_value(
                event.payload.get("attention_cost", current.attention_cost)
            ),
            social_cost_of_failure=_float_value(
                event.payload.get("social_cost_of_failure", current.social_cost_of_failure)
            ),
            closure_reason=closure,
            updated_at=event.timestamp,
        )
        self._commitments[commitment_id] = updated
        self._commitment_versions.setdefault(commitment_id, []).append(updated)
        if status != current.status:
            transition = CommitmentTransition.create(
                commitment_id=commitment_id,
                from_state=current.status,
                to_state=status,
                closure_reason=closure,
                based_on_event_cursor=max(0, cast(int, event.sequence) - 1),
                author=event.source,
                reason=f"deterministic migration of {event.type}",
                transitioned_at=event.timestamp,
            )
            self._commitment_transitions.setdefault(commitment_id, []).append(transition)
        return True

    def coverage(self, commitment_id: str, *, at: datetime) -> CommitmentCoverage:
        commitment = self._commitments.get(commitment_id)
        if commitment is None:
            raise KeyError(f"unknown commitment: {commitment_id}")
        proposals = tuple(
            sorted(
                value.proposal_id
                for value in self._work_proposals.values()
                if value.commitment_id == commitment_id
            )
        )
        admitted = tuple(
            sorted(
                value.work_order.work_order_id
                for value in self._work_proposals.values()
                if value.commitment_id == commitment_id
                and value.work_order.work_order_id in self._admitted_work_orders
            )
        )
        external_support = any(
            value.support_required
            and commitment_id in value.support_commitment_refs
            and value.freshness_expires_at > at
            for value in self._external_current.values()
        )
        eligible = commitment.status is CommitmentStatus.ACTIVE or (
            commitment.status is CommitmentStatus.ACCEPTED
            and (
                commitment.activation_due_at is not None
                and commitment.activation_due_at <= at
                or bool(commitment.lead_time_evidence_refs)
            )
        )
        if admitted:
            disposition = CoverageDisposition.COVERED
        elif proposals:
            disposition = CoverageDisposition.PROPOSED
        elif eligible:
            disposition = CoverageDisposition.UNCOVERED
        else:
            disposition = CoverageDisposition.INACTIVE
        return CommitmentCoverage(
            commitment_id=commitment_id,
            disposition=disposition,
            work_proposal_ids=proposals,
            admitted_work_order_ids=admitted,
            external_support_required=external_support,
        )

    def roadmap_health(self, roadmap_id: str, *, at: datetime, wip_limit: int = 4) -> RoadmapHealth:
        revision = self.current_roadmap_revision(roadmap_id)
        if revision is None:
            raise KeyError(f"unknown roadmap: {roadmap_id}")
        aligned = all(
            (goal := self._goal_revisions.get(revision_id)) is not None
            and self._current_goal_revision.get(goal.goal_id) == revision_id
            for revision_id in revision.governing_goal_revision_ids
        )
        linked = tuple(
            value
            for value in self._commitments.values()
            if value.roadmap_revision_id == revision.revision_id
        )
        failed = any(
            value.status is CommitmentStatus.CLOSED
            and value.closure_reason
            in {CommitmentClosureReason.FAILED, CommitmentClosureReason.BREACHED}
            for value in linked
        )
        late = any(
            value.status in {CommitmentStatus.ACCEPTED, CommitmentStatus.ACTIVE}
            and value.deadline is not None
            and value.deadline < at
            for value in linked
        )
        linked_commitment_ids = {item.id for item in linked}
        wip = sum(
            value.commitment_id in linked_commitment_ids
            and value.work_order.work_order_id not in self._admitted_work_orders
            for value in self._work_proposals.values()
        )
        external_change = any(
            value.support_required
            and value.freshness_expires_at > at
            and any(ref in {item.id for item in linked} for ref in value.support_commitment_refs)
            for value in self._external_current.values()
        )
        signals = {
            "goal alignment": HealthSignal.SATISFIED if aligned else HealthSignal.NEEDS_REVIEW,
            "assumption validity": (
                HealthSignal.UNKNOWN if revision.assumptions else HealthSignal.SATISFIED
            ),
            "dependency validity": HealthSignal.SATISFIED,
            "progress consistency": (
                HealthSignal.NEEDS_REVIEW if failed else HealthSignal.SATISFIED
            ),
            "schedule feasibility": (HealthSignal.NEEDS_REVIEW if late else HealthSignal.SATISFIED),
            "capacity fit": (
                HealthSignal.NEEDS_REVIEW if wip > wip_limit else HealthSignal.SATISFIED
            ),
            "opportunity validity": (
                HealthSignal.NEEDS_REVIEW if external_change else HealthSignal.SATISFIED
            ),
        }
        reasons = tuple(
            key for key, value in signals.items() if value is not HealthSignal.SATISFIED
        )
        return RoadmapHealth(
            roadmap_id=roadmap_id,
            revision_id=revision.revision_id,
            goal_alignment=signals["goal alignment"],
            assumption_validity=signals["assumption validity"],
            dependency_validity=signals["dependency validity"],
            progress_consistency=signals["progress consistency"],
            schedule_feasibility=signals["schedule feasibility"],
            capacity_fit=signals["capacity fit"],
            opportunity_validity=signals["opportunity validity"],
            review_reasons=reasons,
        )


def _parse_optional_datetime(value: object) -> datetime | None:
    from ..types import parse_datetime

    return parse_datetime(cast(str | datetime | None, value))


def _float_value(value: object) -> float:
    return float(cast(str | int | float, value))


def _string_values(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in cast(tuple[object, ...] | list[object], value))
