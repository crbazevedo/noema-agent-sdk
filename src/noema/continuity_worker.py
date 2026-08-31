"""Deterministic wake reconciliation over canonical events and fake sources."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from .checkpoints import ConsumerCheckpoint, ConsumerCheckpointProjection
from .continuity import (
    SOURCE_REFRESH_FAILED_EVENT,
    SOURCE_REFRESHED_EVENT,
    AwakeEpoch,
    AwarenessCoverage,
    ContinuityProjection,
    FakeObservation,
    FakeSource,
    FreshnessModel,
    ObservationBudget,
    OrientationIssue,
    OrientationMetrics,
    OrientationReport,
    OrientationStatus,
    ReconciliationDecision,
    ReconciliationDisposition,
    SourceState,
    TemporalService,
    WakeReconciler,
)
from .events import Event
from .kernel import NoemaKernel
from .memory import EpistemicType, MemoryProjection, SemanticAssertion
from .telemetry import InMemoryTelemetry, Metric, TelemetrySink


class SituatedContinuityWorker:
    """Orient from stale source state without performing a consequential effect."""

    def __init__(
        self,
        kernel: NoemaKernel,
        memory: MemoryProjection,
        *,
        sources: Mapping[str, FakeSource],
        temporal: TemporalService | None = None,
        freshness: FreshnessModel | None = None,
        reconciler: WakeReconciler | None = None,
        telemetry: TelemetrySink | None = None,
        consumer_id: str = "situated-continuity",
        source: str = "continuity:wake-worker",
    ) -> None:
        if not consumer_id.strip() or not source.strip():
            raise ValueError("continuity worker consumer id and source must be non-empty")
        if len(set(sources)) != len(sources):
            raise ValueError("continuity fake source ids must be unique")
        self.kernel = kernel
        self.memory = memory
        self.sources = dict(sources)
        self.temporal = temporal or TemporalService()
        self.freshness = freshness or FreshnessModel()
        self.reconciler = reconciler or WakeReconciler()
        self.telemetry = telemetry or InMemoryTelemetry()
        self.consumer_id = consumer_id
        self.source = source

    async def record_source_state(self, state: SourceState) -> SourceState:
        """Persist the canonical source cursor/configuration snapshot."""

        adapter = self.sources.get(state.source_id)
        if adapter is not None:
            self._validate_adapter_state(adapter, state)
        stored = await self.kernel.emit(state.to_event(source=self.source))
        return SourceState.from_event(stored)

    async def wake(
        self,
        *,
        previous_active_at: datetime | None = None,
        budget: ObservationBudget | None = None,
        active_evaluation_epoch_id: str | None = None,
    ) -> OrientationReport:
        """Run one effect-free wake/orientation cycle against deterministic sources."""

        if not self.kernel.started:
            await self.kernel.start()
        started_monotonic = self.temporal.monotonic_now()
        woke_at = self.temporal.wall_now()
        history = await self.kernel.history()
        continuity = ContinuityProjection()
        continuity.rebuild(history)
        checkpoints = ConsumerCheckpointProjection()
        checkpoints.rebuild(history)
        checkpoint = checkpoints.get(self.consumer_id)
        cursor_before = checkpoint.last_completed_sequence if checkpoint else 0
        cursor_after_replay = await self.kernel.store.latest_sequence()
        previous = self._resolve_previous_active(
            previous_active_at,
            continuity=continuity,
            woke_at=woke_at,
        )
        epoch = AwakeEpoch.start(
            woke_at=woke_at,
            previous_active_at=previous,
            event_log_cursor_before=cursor_before,
            event_log_cursor_after=cursor_after_replay,
            active_evaluation_epoch_id=active_evaluation_epoch_id,
        )
        epoch_event = await self.kernel.emit(epoch.to_event(source=self.source))

        initial_states = continuity.source_states
        decayed_states = tuple(
            state.with_freshness(
                self.freshness.source_freshness(state, at=woke_at),
                captured_at=woke_at,
            )
            for state in initial_states
        )
        before_coverage = AwarenessCoverage.from_states(
            decayed_states,
            relevance_floor=self.reconciler.relevance_floor,
        )
        observation_budget = budget or ObservationBudget(
            max_cost=sum(state.refresh_cost for state in decayed_states),
            max_sources=len(decayed_states),
        )
        plan = self.reconciler.plan(
            decayed_states,
            elapsed_wall_time=epoch.elapsed_wall_time,
            budget=observation_budget,
            created_at=woke_at,
        )
        for request in plan.requests:
            await self.kernel.emit(
                request.to_event(source=self.source, causation_id=epoch_event.id)
            )

        states_by_id = {state.source_id: state for state in decayed_states}
        latest_assertions = self._latest_assertions()
        refreshed: list[str] = []
        changed: list[str] = []
        unavailable: list[str] = []
        issues: list[OrientationIssue] = []
        decisions: list[ReconciliationDecision] = []
        events_fetched = 0
        beliefs_updated = 0
        observation_cost = 0.0
        empty_refreshes = 0

        for decision in plan.decisions:
            if decision.disposition is not ReconciliationDisposition.REFRESH:
                decisions.append(decision)
                continue
            state = states_by_id[decision.source_id]
            adapter = self.sources.get(decision.source_id)
            if adapter is None:
                decisions.append(self.reconciler.mark_unavailable(decision))
                unavailable.append(decision.source_id)
                await self._emit_refresh_result(
                    event_type=SOURCE_REFRESH_FAILED_EVENT,
                    state=state,
                    request_id=decision.request.request_id if decision.request else "missing",
                    woke_at=woke_at,
                    epoch_event_id=epoch_event.id,
                    cursor=state.last_cursor,
                    observations=0,
                    reason="source adapter unavailable",
                )
                continue
            self._validate_adapter_state(adapter, state)
            result = adapter.refresh(after_cursor=state.last_cursor, observed_at=woke_at)
            observation_cost += result.cost
            if not result.available:
                decisions.append(self.reconciler.mark_unavailable(decision))
                unavailable.append(decision.source_id)
                await self._emit_refresh_result(
                    event_type=SOURCE_REFRESH_FAILED_EVENT,
                    state=state,
                    request_id=decision.request.request_id if decision.request else "missing",
                    woke_at=woke_at,
                    epoch_event_id=epoch_event.id,
                    cursor=state.last_cursor,
                    observations=0,
                    reason="source unavailable",
                )
                continue

            decisions.append(decision)
            refreshed.append(decision.source_id)
            if not result.observations:
                empty_refreshes += 1
            await self._emit_refresh_result(
                event_type=SOURCE_REFRESHED_EVENT,
                state=state,
                request_id=decision.request.request_id if decision.request else "missing",
                woke_at=woke_at,
                epoch_event_id=epoch_event.id,
                cursor=result.cursor,
                observations=len(result.observations),
                reason="refresh completed",
            )
            for observation in result.observations:
                changed.append(decision.source_id)
                source_event = await self._record_observation(
                    state,
                    observation,
                    woke_at=woke_at,
                    epoch_event_id=epoch_event.id,
                )
                key = (observation.subject, observation.predicate)
                previous_assertion = latest_assertions.get(key)
                assertion = SemanticAssertion.create(
                    subject=observation.subject,
                    predicate=observation.predicate,
                    value=observation.value,
                    epistemic_type=EpistemicType.OBSERVED,
                    confidence=observation.confidence,
                    valid_from=observation.occurred_at,
                    recorded_at=woke_at,
                    source_refs=(f"event:{source_event.id}",),
                    fresh_until=self.freshness.fresh_until(
                        observed_at=woke_at,
                        change_hazard=state.change_hazard,
                    ),
                    supersedes=(
                        previous_assertion.assertion_id if previous_assertion is not None else None
                    ),
                    mutable_world=True,
                )
                await self.kernel.emit(assertion.to_event(source=self.source))
                latest_assertions[key] = assertion
                events_fetched += 1
                beliefs_updated += 1
                if observation.issue_priority > 0.0:
                    issues.append(
                        OrientationIssue(
                            source_id=state.source_id,
                            summary=observation.impact_summary,
                            priority=observation.issue_priority,
                            affects_current_plan=observation.affects_current_plan,
                        )
                    )
            refreshed_state = state.refreshed(
                observed_at=woke_at,
                cursor=result.cursor,
            )
            states_by_id[state.source_id] = refreshed_state
            await self.kernel.emit(
                refreshed_state.to_event(
                    source=self.source,
                    causation_id=epoch_event.id,
                )
            )

        await self.kernel.bus.drain()
        final_states = tuple(states_by_id[key] for key in sorted(states_by_id))
        coverage = AwarenessCoverage.from_states(
            final_states,
            relevance_floor=self.reconciler.relevance_floor,
        )
        status = OrientationStatus.ORIENTED if coverage.sufficient else OrientationStatus.INCOMPLETE
        cursor_after_refresh = await self.kernel.store.latest_sequence()
        completed_epoch = epoch.complete(
            status=status,
            oriented_at=woke_at,
            event_log_cursor_after=cursor_after_refresh,
        )
        completed_event = await self.kernel.emit(completed_epoch.to_event(source=self.source))
        issues.sort(key=lambda issue: (-issue.priority, issue.source_id, issue.summary))
        highest_issue = issues[0] if issues else None
        relevant_unseen, relevant_changes = self._relevant_missed_changes(
            initial_states=decayed_states,
            refreshed_source_ids=set(refreshed),
            at=woke_at,
        )
        ended_monotonic = self.temporal.monotonic_now()
        latency = self.temporal.elapsed_monotonic(
            started_monotonic,
            ended=ended_monotonic,
        ).total_seconds()
        uncertainty_removed = max(
            0.0,
            before_coverage.weighted_uncertainty - coverage.weighted_uncertainty,
        )
        metrics = OrientationMetrics(
            sources_considered=len(initial_states),
            sources_refreshed=len(refreshed),
            events_fetched=events_fetched,
            beliefs_updated=beliefs_updated,
            stale_beliefs_retained=len(coverage.gaps),
            orientation_latency_seconds=latency,
            observation_cost=observation_cost,
            unnecessary_refresh_rate=(empty_refreshes / len(refreshed) if refreshed else 0.0),
            missed_change_rate=(relevant_unseen / relevant_changes if relevant_changes else 0.0),
            decision_relevant_uncertainty_removed=uncertainty_removed,
        )
        report = OrientationReport.create(
            epoch=completed_epoch,
            status=status,
            coverage=coverage,
            decisions=tuple(decisions),
            refreshed_source_ids=tuple(sorted(refreshed)),
            changed_source_ids=tuple(sorted(set(changed))),
            unavailable_source_ids=tuple(sorted(unavailable)),
            issues=tuple(issues),
            highest_value_issue=highest_issue,
            metrics=metrics,
            summary=self._summary(status, issues, unavailable),
        )
        await self.kernel.emit(report.to_event(source=self.source, causation_id=completed_event.id))
        await self._advance_checkpoint(
            completed_sequence=await self.kernel.store.latest_sequence(),
            epoch_id=epoch.epoch_id,
            causation_id=completed_event.id,
            timestamp=woke_at,
        )
        await self._record_metrics(report)
        return report

    async def _record_observation(
        self,
        state: SourceState,
        observation: FakeObservation,
        *,
        woke_at: datetime,
        epoch_event_id: str,
    ) -> Event:
        return await self.kernel.emit(
            Event(
                id=f"fake-observation:{state.source_id}:{observation.cursor}",
                type="external.source_observed",
                source=f"fake:{state.source_id}",
                subject=observation.subject,
                timestamp=woke_at,
                causation_id=epoch_event_id,
                payload={
                    "source_id": state.source_id,
                    "cursor": observation.cursor,
                    "occurred_at": observation.occurred_at.isoformat(),
                    "predicate": observation.predicate,
                    "value": observation.value,
                },
                metadata={"epistemic_type": EpistemicType.OBSERVED.value},
            )
        )

    async def _emit_refresh_result(
        self,
        *,
        event_type: str,
        state: SourceState,
        request_id: str,
        woke_at: datetime,
        epoch_event_id: str,
        cursor: str | None,
        observations: int,
        reason: str,
    ) -> None:
        await self.kernel.emit(
            Event(
                id=f"continuity-refresh-result:{request_id}:{event_type}",
                type=event_type,
                source=self.source,
                subject=state.source_id,
                timestamp=woke_at,
                causation_id=epoch_event_id,
                payload={
                    "request_id": request_id,
                    "source_id": state.source_id,
                    "cursor": cursor,
                    "observations": observations,
                    "reason": reason,
                },
            )
        )

    async def _advance_checkpoint(
        self,
        *,
        completed_sequence: int,
        epoch_id: str,
        causation_id: str,
        timestamp: datetime,
    ) -> ConsumerCheckpoint:
        candidate = ConsumerCheckpoint(
            consumer_id=self.consumer_id,
            last_completed_sequence=completed_sequence,
            observed_head_sequence=completed_sequence,
            epoch_id=epoch_id,
        )
        stored = await self.kernel.emit(
            candidate.to_event(
                source=self.source,
                timestamp=timestamp,
                causation_id=causation_id,
            )
        )
        return ConsumerCheckpoint.from_event(stored)

    async def _record_metrics(self, report: OrientationReport) -> None:
        values = report.metrics.to_dict()
        for name, value in values.items():
            if isinstance(value, (int, float)):
                await self.telemetry.record(
                    Metric(
                        f"continuity.{name}",
                        float(value),
                        {"epoch": report.epoch.epoch_id},
                    )
                )

    def _latest_assertions(self) -> dict[tuple[str, str], SemanticAssertion]:
        latest: dict[tuple[str, str], SemanticAssertion] = {}
        for assertion in self.memory.assertions:
            key = (assertion.subject, assertion.predicate)
            current = latest.get(key)
            if current is None or (
                assertion.recorded_at,
                assertion.assertion_id,
            ) > (current.recorded_at, current.assertion_id):
                latest[key] = assertion
        return latest

    def _relevant_missed_changes(
        self,
        *,
        initial_states: tuple[SourceState, ...],
        refreshed_source_ids: set[str],
        at: datetime,
    ) -> tuple[int, int]:
        missed = 0
        total = 0
        for state in initial_states:
            if state.goal_relevance * state.decision_sensitivity < self.reconciler.relevance_floor:
                continue
            adapter = self.sources.get(state.source_id)
            if adapter is None:
                continue
            unseen = adapter.unseen_changes(
                after_cursor=state.last_cursor,
                at=at,
            )
            total += unseen
            if state.source_id not in refreshed_source_ids:
                missed += unseen
        return missed, total

    @staticmethod
    def _validate_adapter_state(adapter: FakeSource, state: SourceState) -> None:
        if adapter.source_id != state.source_id:
            raise ValueError("fake source adapter identity differs from canonical source state")
        if adapter.hazard != state.change_hazard or adapter.refresh_cost != state.refresh_cost:
            raise ValueError(
                f"fake source configuration differs from canonical state: {state.source_id}"
            )

    @staticmethod
    def _resolve_previous_active(
        value: datetime | None,
        *,
        continuity: ContinuityProjection,
        woke_at: datetime,
    ) -> datetime:
        if value is not None:
            return value
        latest = continuity.latest_epoch
        if latest is not None:
            return latest.oriented_at or latest.woke_at
        return woke_at

    @staticmethod
    def _summary(
        status: OrientationStatus,
        issues: list[OrientationIssue],
        unavailable: list[str],
    ) -> str:
        if status is OrientationStatus.INCOMPLETE:
            sources = ", ".join(sorted(unavailable)) or "critical sources"
            return (
                f"Orientation incomplete: {sources} could not be refreshed; "
                "dependent actions remain shadow-blocked."
            )
        affecting = [issue.summary for issue in issues if issue.affects_current_plan]
        informational = [issue.summary for issue in issues if not issue.affects_current_plan]
        if not affecting and not informational:
            return "No decision-relevant change detected; no consequential action is warranted."
        parts: list[str] = []
        if affecting:
            parts.append(
                f"{len(affecting)} changes affect the current plan: " + "; ".join(affecting)
            )
        if informational:
            parts.append("Additional resolved changes: " + "; ".join(informational))
        return ". ".join(parts) + "."
