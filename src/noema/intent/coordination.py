"""CAS-backed command facade for deterministic strategic stewardship."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime

from ..events import Event
from ..kernel import NoemaKernel
from ..situation import Commitment, CommitmentClosureReason, CommitmentStatus, GoalStatus
from ..store import ConcurrentAppendError
from ..types import JSONValue, utc_now
from ..work.models import WorkOrder
from .models import (
    AssistanceEnvelope,
    CommitmentCoverage,
    CommitmentTransition,
    ExternalWorkstream,
    GoalKind,
    GoalRevision,
    IntentAuthority,
    InterventionLevel,
    OriginProvenance,
    OutcomeNode,
    OutcomeRoleAssignment,
    PortfolioSignals,
    RoadmapHealth,
    RoadmapRevision,
    WorkOrderProposal,
    commitment_recorded_event,
)
from .projection import StrategicProjection
from .validation import StrategicValidator

EventFactory = Callable[[StrategicProjection, int], Event]


class IntentStewardCoordinator:
    """Rebuild, validate, and compare-and-append every strategic transition."""

    def __init__(
        self,
        kernel: NoemaKernel,
        *,
        validator: StrategicValidator,
        clock: Callable[[], datetime] = utc_now,
        source: str = "intent:coordinator",
    ) -> None:
        if not source.strip():
            raise ValueError("intent coordinator source must be non-empty")
        self.kernel = kernel
        self.validator = validator
        self.clock = clock
        self.source = source
        self.projection = StrategicProjection()

    async def record_goal_revision(
        self,
        *,
        goal_id: str,
        description: str,
        priority: float,
        utility: float,
        success_criteria: tuple[str, ...],
        owner: str,
        status: GoalStatus,
        deadline: datetime | None,
        kind: GoalKind,
        governing_goal_refs: tuple[str, ...],
        origin: OriginProvenance,
        intent_authority: IntentAuthority,
        author: str,
        revision_reason: str,
    ) -> GoalRevision:
        await self._reload()
        captured = self.projection.current_goal_revision(goal_id)
        expected_current_id = captured.revision_id if captured else None
        recorded_at = self.clock()

        def factory(projection: StrategicProjection, head: int) -> Event:
            current = projection.current_goal_revision(goal_id)
            revision = GoalRevision.create(
                goal_id=goal_id,
                version=current.version + 1 if current else 1,
                description=description,
                priority=priority,
                utility=utility,
                success_criteria=success_criteria,
                owner=owner,
                status=status,
                deadline=deadline,
                kind=kind,
                governing_goal_refs=governing_goal_refs,
                origin=origin,
                intent_authority=intent_authority,
                based_on_event_cursor=head,
                author=author,
                revision_reason=revision_reason,
                recorded_at=recorded_at,
                supersedes_revision_id=current.revision_id if current else None,
            )
            self.validator.validate_goal_revision(
                revision,
                projection,
                expected_current_revision_id=expected_current_id,
            )
            return revision.to_event(source=self.source)

        event = await self._admit(factory)
        return GoalRevision.from_dict(event.payload)

    async def record_roadmap_revision(
        self,
        *,
        roadmap_id: str,
        governing_goal_revision_ids: tuple[str, ...],
        outcome_nodes: tuple[OutcomeNode, ...],
        assumptions: tuple[str, ...],
        confidence: float,
        success_criteria: tuple[str, ...],
        resource_envelope: Mapping[str, float],
        intent_authority: IntentAuthority,
        author: str,
        revision_reason: str,
    ) -> RoadmapRevision:
        await self._reload()
        captured = self.projection.current_roadmap_revision(roadmap_id)
        expected_current_id = captured.revision_id if captured else None
        recorded_at = self.clock()

        def factory(projection: StrategicProjection, head: int) -> Event:
            current = projection.current_roadmap_revision(roadmap_id)
            revision = RoadmapRevision.create(
                roadmap_id=roadmap_id,
                version=current.version + 1 if current else 1,
                governing_goal_revision_ids=governing_goal_revision_ids,
                outcome_nodes=outcome_nodes,
                assumptions=assumptions,
                confidence=confidence,
                success_criteria=success_criteria,
                resource_envelope=resource_envelope,
                intent_authority=intent_authority,
                based_on_event_cursor=head,
                author=author,
                revision_reason=revision_reason,
                recorded_at=recorded_at,
                supersedes_revision_id=current.revision_id if current else None,
            )
            self.validator.validate_roadmap_revision(
                revision,
                projection,
                expected_current_revision_id=expected_current_id,
            )
            return revision.to_event(source=self.source)

        event = await self._admit(factory)
        return RoadmapRevision.from_dict(event.payload)

    async def record_outcome_roles(
        self, assignment: OutcomeRoleAssignment
    ) -> OutcomeRoleAssignment:
        def factory(projection: StrategicProjection, head: int) -> Event:
            del head
            self.validator.validate_roles(assignment, projection)
            return assignment.to_event(source=self.source)

        event = await self._admit(factory)
        return OutcomeRoleAssignment.from_dict(event.payload)

    async def record_assistance_envelope(self, envelope: AssistanceEnvelope) -> AssistanceEnvelope:
        def factory(projection: StrategicProjection, head: int) -> Event:
            del head
            self.validator.validate_assistance(envelope, projection)
            return envelope.to_event(source=self.source)

        event = await self._admit(factory)
        return AssistanceEnvelope.from_dict(event.payload)

    async def record_commitment(
        self,
        commitment: Commitment,
        *,
        intent_authority: IntentAuthority,
    ) -> Commitment:
        def factory(projection: StrategicProjection, head: int) -> Event:
            del head
            self.validator.validate_commitment(
                commitment,
                projection,
                authority=intent_authority,
            )
            event = commitment_recorded_event(commitment, source=self.source)
            return replace(
                event,
                metadata={"intent_authority": intent_authority.to_dict()},
            )

        event = await self._admit(factory)
        from .models import commitment_from_dict

        return commitment_from_dict(event.payload)

    async def transition_commitment(
        self,
        commitment_id: str,
        *,
        to_state: CommitmentStatus,
        closure_reason: CommitmentClosureReason | None,
        intent_authority: IntentAuthority,
        author: str,
        reason: str,
        reactivation_roadmap_revision_id: str | None = None,
        reactivation_role_assignment_id: str | None = None,
        reactivation_assistance_envelope_id: str | None = None,
        reorientation_evidence_refs: tuple[str, ...] = (),
    ) -> CommitmentTransition:
        await self._reload()
        captured = self.projection.commitment(commitment_id)
        if captured is None:
            raise KeyError(f"unknown commitment: {commitment_id}")
        expected_state = captured.status
        transitioned_at = self.clock()

        def factory(projection: StrategicProjection, head: int) -> Event:
            current = projection.commitment(commitment_id)
            if current is None or current.status is not expected_state:
                raise ValueError("commitment changed after transition command was captured")
            transition = CommitmentTransition.create(
                commitment_id=commitment_id,
                from_state=current.status,
                to_state=to_state,
                closure_reason=closure_reason,
                based_on_event_cursor=head,
                author=author,
                reason=reason,
                transitioned_at=transitioned_at,
                reactivation_roadmap_revision_id=reactivation_roadmap_revision_id,
                reactivation_role_assignment_id=reactivation_role_assignment_id,
                reactivation_assistance_envelope_id=(reactivation_assistance_envelope_id),
                reorientation_evidence_refs=reorientation_evidence_refs,
            )
            self.validator.validate_transition(
                transition,
                projection,
                authority=intent_authority,
            )
            event = transition.to_event(source=self.source)
            return replace(
                event,
                metadata={"intent_authority": intent_authority.to_dict()},
            )

        event = await self._admit(factory)
        return CommitmentTransition.from_dict(event.payload)

    async def observe_external_workstream(
        self, observation: ExternalWorkstream
    ) -> ExternalWorkstream:
        def factory(projection: StrategicProjection, head: int) -> Event:
            del head
            self.validator.validate_external(observation, projection)
            return observation.to_event(source=self.source)

        event = await self._admit(factory)
        return ExternalWorkstream.from_dict(event.payload)

    async def propose_work_for_commitment(
        self,
        commitment_id: str,
        *,
        purpose: str,
        desired_outcome: str,
        success_criteria: tuple[str, ...],
        intervention: InterventionLevel,
        declared_agent_support: tuple[str, ...],
        portfolio_signals: PortfolioSignals,
        additional_provenance: tuple[str, ...] = (),
    ) -> WorkOrderProposal:
        proposed_at = self.clock()

        def factory(projection: StrategicProjection, head: int) -> Event:
            commitment = projection.commitment(commitment_id)
            if commitment is None:
                raise KeyError(f"unknown commitment: {commitment_id}")
            if commitment.roadmap_revision_id is None or commitment.outcome_node_id is None:
                raise ValueError("commitment lacks roadmap outcome provenance")
            eligibility = self.validator.work_eligibility(commitment, at=proposed_at)
            if eligibility is None:
                raise ValueError("accepted future commitment is not yet eligible for work")
            order = WorkOrder.create(
                purpose=purpose,
                governing_goal_refs=commitment.governing_goal_refs,
                created_from=(
                    f"commitment:{commitment.id}",
                    f"roadmap-revision:{commitment.roadmap_revision_id}",
                    f"outcome-node:{commitment.outcome_node_id}",
                    *additional_provenance,
                ),
                priority=commitment.priority,
                desired_outcome=desired_outcome,
                success_criteria=success_criteria,
                deadline=commitment.deadline,
                created_at=proposed_at,
            )
            proposal = WorkOrderProposal.create(
                commitment_id=commitment.id,
                roadmap_revision_id=commitment.roadmap_revision_id,
                outcome_node_id=commitment.outcome_node_id,
                work_order=order,
                intervention=intervention,
                declared_agent_support=declared_agent_support,
                eligibility=eligibility,
                portfolio_signals=portfolio_signals,
                wip_limit=self.validator.wip_limit,
                based_on_event_cursor=head,
                proposed_at=proposed_at,
                validator_id=self.validator.validator_id,
            )
            self.validator.validate_work_proposal(proposal, projection, at=proposed_at)
            return proposal.to_event(source=self.source)

        event = await self._admit(factory)
        return WorkOrderProposal.from_dict(event.payload)

    async def admit_work_order(self, proposal_id: str) -> WorkOrder:
        await self._reload()
        known = self.projection.work_proposal(proposal_id)
        if known is None:
            raise KeyError(f"unknown work proposal: {proposal_id}")
        already = self.projection.admitted_work_order(known.work_order.work_order_id)
        if already is not None:
            return already

        def factory(projection: StrategicProjection, head: int) -> Event:
            del head
            proposal = projection.work_proposal(proposal_id)
            if proposal is None:
                raise KeyError(f"unknown work proposal: {proposal_id}")
            self.validator.validate_work_admission(proposal, projection)
            return proposal.work_order.to_event(source=self.source)

        event = await self._admit(factory)
        return WorkOrder.from_event(event)

    async def coverage(
        self, commitment_id: str, *, at: datetime | None = None
    ) -> CommitmentCoverage:
        await self._reload()
        return self.projection.coverage(commitment_id, at=at or self.clock())

    async def roadmap_health(self, roadmap_id: str, *, at: datetime | None = None) -> RoadmapHealth:
        await self._reload()
        return self.projection.roadmap_health(
            roadmap_id,
            at=at or self.clock(),
            wip_limit=self.validator.wip_limit,
        )

    async def _reload(self) -> None:
        history = await self.kernel.history()
        self.projection.rebuild(self.kernel.schemas.normalize(event) for event in history)

    async def _admit(self, factory: EventFactory) -> Event:
        while True:
            await self._reload()
            head = self.projection.event_cursor
            event = factory(self.projection, head)
            metadata: dict[str, JSONValue] = dict(event.metadata)
            metadata["validated_at_event_cursor"] = head
            event = replace(event, metadata=metadata)
            try:
                stored = await self.kernel.emit_if_head(
                    event,
                    expected_head_sequence=head,
                )
            except ConcurrentAppendError:
                continue
            if replace(stored, sequence=None) != event:
                raise ValueError(f"canonical event id conflict: {event.id}")
            projected = self.kernel.schemas.normalize(stored)
            self.projection.apply(projected)
            return projected
