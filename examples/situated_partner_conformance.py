"""Deterministic situated-partner G1 contract rehearsal.

This example composes existing public Noema APIs around a fictional fixture. It
does not add canonical SDK semantics for source acquisition, observation scope,
dialogue, or presentation delivery, and it does not claim live pilot evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import cast

from noema import (
    ActionIntent,
    AssertionStatus,
    AuthorityLevel,
    AutonomyProfile,
    AwarenessCoverage,
    AwarenessDemand,
    CapabilitySpec,
    EpistemicType,
    Event,
    GoalKind,
    GoalRevision,
    GoalStatus,
    IntentAuthority,
    IntentAuthorityScope,
    IntentStewardCoordinator,
    NoemaKernel,
    ObservationBudget,
    OriginKind,
    OriginProvenance,
    OutcomeNode,
    PolicyEngine,
    SemanticAssertion,
    SituationSnapshot,
    SourceState,
    StaticStrategicTrust,
    StrategicProjection,
    StrategicValidator,
    WorkOrder,
    WorkProjection,
    validate_opaque_governance_id,
)
from noema.schema import validate_json_schema
from noema.types import JSONObject, JSONValue

REPOSITORY = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPOSITORY
    / "docs"
    / "pilot"
    / "contracts"
    / "situated-partner-envelope-v1.schema.json"
)
FIXTURE_PATH = (
    REPOSITORY / "docs" / "pilot" / "fixtures" / "project-meridian-g1.json"
)
REQUIRED_CASES = (
    "T01",
    "T02",
    "T09",
    "T10",
    "T11",
    "T13",
    "T16",
    "T25",
    "T30",
    "T31",
    "T34",
    "T35",
)
SYNTHETICALLY_VERIFIED_CASES = (
    "T02",
    "T10",
    "T11",
    "T13",
    "T16",
    "T34",
    "T35",
)
SPECIFIED_ONLY_CASES = tuple(
    case_id for case_id in REQUIRED_CASES if case_id not in SYNTHETICALLY_VERIFIED_CASES
)


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be an object")
    return cast(Mapping[str, object], value)


def _items(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise TypeError(f"{name} must be an array")
    return value


def _load_json(path: Path) -> JSONObject:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return cast(JSONObject, _mapping(loaded, str(path)))


def load_fixture(path: Path = FIXTURE_PATH) -> JSONObject:
    return _load_json(path)


def load_schema(path: Path = SCHEMA_PATH) -> JSONObject:
    return _load_json(path)


def validate_envelope(envelope: Mapping[str, object], schema: Mapping[str, object]) -> None:
    """Validate the published shape plus semantics expressible without ``oneOf``."""

    validate_json_schema(envelope, schema)
    kind = str(envelope["message_kind"])
    correlation = _mapping(envelope["correlation"], "correlation")
    request = envelope["source_request"]
    result = envelope["source_result"]
    if kind == "source_acquisition_request":
        if not isinstance(request, Mapping) or result is not None:
            raise ValueError("source request envelopes require request data and no result")
        if request["acquisition_request_id"] != correlation["request_id"]:
            raise ValueError("source request identity must match correlation request_id")
    elif kind == "source_acquisition_result":
        if request is not None or not isinstance(result, Mapping):
            raise ValueError("source result envelopes require result data and no request")
        if result["acquisition_request_id"] != correlation["request_id"]:
            raise ValueError("source result identity must match correlation request_id")
    elif request is not None or result is not None:
        raise ValueError("only source acquisition envelopes may carry source data")

    task = envelope["task"]
    if isinstance(task, Mapping):
        budget = _mapping(task["budget"], "task budget")
        usage = _mapping(task["usage"], "task usage")
        for stem in ("query_calls", "content_reads", "model_calls"):
            maximum = int(cast(int, budget[f"max_{stem}"]))
            actual = int(cast(int, usage[stem]))
            if actual > maximum:
                raise ValueError(f"task usage exceeds {stem} budget")
        actual_cost = usage["cost"]
        if actual_cost is not None and float(cast(float, actual_cost)) > float(
            cast(float, budget["max_cost"])
        ):
            raise ValueError("task usage exceeds cost budget")

    output = envelope["material_output"]
    if isinstance(output, Mapping):
        for played in _items(output["played_ranges"], "played ranges"):
            item = _mapping(played, "played range")
            if int(cast(int, item["end_ms"])) < int(cast(int, item["start_ms"])):
                raise ValueError("played range cannot end before it starts")
        if not bool(output["requires_revalidation"]):
            revision = output["revalidated_context_revision"]
            causal_cut = output["revalidated_at_causal_cut"]
            if revision is None or causal_cut is None:
                raise ValueError("presentation-ready output requires explicit revalidation")

    governance = _mapping(envelope["governance"], "governance")
    for field in (
        "information_refs",
        "lineage_refs",
        "policy_binding_refs",
        "policy_snapshot_refs",
        "access_decision_refs",
        "disclosure_decision_refs",
    ):
        for reference in _items(governance[field], field):
            validate_opaque_governance_id(str(reference), field)
    disclosure_view_ref = governance["disclosure_view_ref"]
    if disclosure_view_ref is not None:
        validate_opaque_governance_id(str(disclosure_view_ref), "disclosure_view_ref")
    if governance["source_trust_domain"] != governance["target_trust_domain"]:
        if not _items(governance["access_decision_refs"], "access decisions"):
            raise ValueError("cross-domain payload requires an access decision")
        if not _items(governance["disclosure_decision_refs"], "disclosure decisions"):
            raise ValueError("cross-domain payload requires a disclosure decision")
        if disclosure_view_ref is None:
            raise ValueError("cross-domain payload requires an admitted disclosure view")
        if (
            governance["payload_fingerprint"] is None
            or governance["admitted_payload_fingerprint"] is None
            or governance["payload_fingerprint"]
            != governance["admitted_payload_fingerprint"]
        ):
            raise ValueError("payload does not match the admitted disclosure form")


def envelope_by_id(fixture: Mapping[str, object], envelope_id: str) -> Mapping[str, object]:
    for value in _items(fixture["envelopes"], "fixture envelopes"):
        envelope = _mapping(value, "envelope")
        if envelope["envelope_id"] == envelope_id:
            return envelope
    raise KeyError(envelope_id)


def is_surface_eligible(
    candidate: Mapping[str, object],
    current_context: Mapping[str, object],
    *,
    current_goal_status: GoalStatus,
) -> bool:
    """Application-side stale-result guard for the frozen boundary contract."""

    candidate_context = _mapping(candidate["context"], "candidate context")
    current = _mapping(current_context["context"], "current context")
    candidate_correlation = _mapping(candidate["correlation"], "candidate correlation")
    current_correlation = _mapping(current_context["correlation"], "current correlation")
    lifecycle = _mapping(candidate["lifecycle"], "candidate lifecycle")
    freshness = _mapping(candidate["freshness"], "candidate freshness")
    candidate_governance = _mapping(candidate["governance"], "candidate governance")
    current_governance = _mapping(current_context["governance"], "current governance")
    context_basis_fields = (
        "context_id",
        "situation_id",
        "context_revision",
        "goal_revision_id",
        "outcome_id",
        "immediate_intent_ref",
        "supported_assertion_refs",
        "unresolved_assertion_refs",
        "artifact_versions",
    )
    correlation_basis_fields = ("session_id", "turn_id", "topic_id", "request_id")
    governance_basis_fields = (
        "purpose",
        "principal_id",
        "information_refs",
        "lineage_refs",
        "policy_binding_refs",
        "policy_snapshot_refs",
        "access_decision_refs",
        "disclosure_decision_refs",
        "source_trust_domain",
        "target_trust_domain",
        "disclosure_view_ref",
        "payload_fingerprint",
        "admitted_payload_fingerprint",
    )
    eligible = (
        current_goal_status not in {GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.CANCELLED}
        and all(candidate_context[field] == current[field] for field in context_basis_fields)
        and all(
            candidate_correlation[field] == current_correlation[field]
            for field in correlation_basis_fields
        )
        and all(
            candidate_governance[field] == current_governance[field]
            for field in governance_basis_fields
        )
        and lifecycle["cancelled_by_event_id"] is None
        and lifecycle["superseded_by_envelope_id"] is None
        and freshness["state"] == "current"
    )
    output = candidate["material_output"]
    if not eligible or not isinstance(output, Mapping):
        return eligible
    artifacts = {
        (
            str(_mapping(value, "artifact")["artifact_id"]),
            int(_mapping(value, "artifact")["version"]),
        )
        for value in _items(current["artifact_versions"], "artifact versions")
    }
    return (
        output["requires_revalidation"] is False
        and output["revalidated_context_revision"] == current["context_revision"]
        and int(cast(int, output["revalidated_at_causal_cut"]))
        <= int(cast(int, current["causal_cut"]))
        and (str(output["artifact_id"]), int(cast(int, output["artifact_version"])))
        in artifacts
    )


class PilotObserverProjection:
    """Disposable, OTel-independent view over canonical example events."""

    def __init__(self) -> None:
        self.event_cursor = 0
        self.refreshed_at: str | None = None
        self.task_states: dict[tuple[str | None, str | None], str] = {}

    def apply(self, event: Event) -> None:
        if event.sequence is not None:
            self.event_cursor = max(self.event_cursor, event.sequence)
        if not event.type.startswith("companion.situated_partner."):
            return
        envelope = _mapping(event.payload, "canonical envelope")
        self.refreshed_at = str(envelope["recorded_at"])
        task = envelope["task"]
        if isinstance(task, Mapping):
            work_order_id = cast(str | None, task["work_order_id"])
            work_node_id = cast(str | None, task["work_node_id"])
            self.task_states[(work_order_id, work_node_id)] = str(task["state"])

    def rebuild(self, events: Sequence[Event]) -> None:
        self.event_cursor = 0
        self.refreshed_at = None
        self.task_states.clear()
        for event in events:
            self.apply(event)


@dataclass(frozen=True, slots=True)
class ExistingApiEvidence:
    goal: GoalRevision
    cancelled_goal: GoalRevision
    current_goal: GoalRevision
    outcome: OutcomeNode
    current_outcome: OutcomeNode
    order: WorkOrder
    coverage: AwarenessCoverage
    fact: SemanticAssertion
    owner_unknown: SemanticAssertion
    rescheduled_fact: SemanticAssertion
    owner_fact: SemanticAssertion
    forecast: SemanticAssertion
    action: ActionIntent
    action_allowed: bool
    observation_budget: ObservationBudget


def existing_api_evidence() -> ExistingApiEvidence:
    """Build the G1 evidence using existing SDK records, not pilot dataclasses."""

    observed_at = datetime(2031, 5, 14, 14, 0, tzinfo=UTC)
    deadline = datetime(2031, 5, 14, 18, 30, tzinfo=UTC)
    origin = OriginProvenance(
        provenance_id="origin:fictional-user",
        kind=OriginKind.USER,
        principal_id="principal:fictional-user",
        authentication_ref="authentication:fictional-session",
    )
    authority = IntentAuthority(
        authority_id="intent-authority:fictional-user",
        principal_id="principal:fictional-user",
        scope=IntentAuthorityScope.USER,
        allowed_goal_kinds=(GoalKind.USER_AUTHORED,),
        goal_refs=(),
        provenance_ref=origin.provenance_id,
    )
    goal = GoalRevision.create(
        goal_id="goal:prepare-project-meridian-review",
        version=1,
        description="Prepare the fictional Project Meridian decision review",
        priority=0.9,
        utility=1.0,
        success_criteria=("decision prerequisites are explicitly supported or unresolved",),
        owner="principal:fictional-user",
        status=GoalStatus.ACTIVE,
        deadline=deadline,
        kind=GoalKind.USER_AUTHORED,
        governing_goal_refs=(),
        origin=origin,
        intent_authority=authority,
        based_on_event_cursor=0,
        author="principal:fictional-user",
        revision_reason="fictional G1 contract rehearsal",
        recorded_at=observed_at,
    )
    outcome = OutcomeNode(
        node_id="outcome:decision-ready-review",
        description="The review has supported decision inputs and named unknowns",
        success_criteria=("supported inputs and unknowns are visible before the cutoff",),
    )
    order = WorkOrder.create(
        purpose="prepare bounded evidence for the Project Meridian review",
        governing_goal_refs=(goal.revision_id,),
        created_from=("event:fictional-review-selected",),
        priority=0.9,
        desired_outcome=outcome.description,
        success_criteria=outcome.success_criteria,
        created_at=observed_at,
        deadline=deadline,
        opportunity_window_end=deadline,
        authority_ceiling=AuthorityLevel.PROPOSE,
    )
    source = SourceState(
        source_id="source:calendar:selected-review",
        domain="fictional-calendar",
        last_observed_at=observed_at - timedelta(hours=2),
        last_cursor="cursor:calendar:15",
        change_hazard=1.0,
        confidence=0.9,
        refresh_cost=1.0,
        captured_at=observed_at,
    )
    demand = AwarenessDemand(
        source_id=source.source_id,
        governing_goal_refs=(goal.revision_id,),
        relevance=1.0,
        decision_sensitivity=1.0,
        required_freshness=0.9,
        required_confidence=0.9,
    )
    coverage = AwarenessCoverage.from_inputs(
        (source,),
        (demand,),
        freshness_by_source={source.source_id: 0.4},
    )
    fact = SemanticAssertion.create(
        subject="situation:project-meridian-review",
        predicate="scheduled_start",
        value="2031-05-14T16:00:00+00:00",
        epistemic_type=EpistemicType.OBSERVED,
        confidence=0.99,
        valid_from=observed_at,
        recorded_at=observed_at,
        fresh_until=deadline,
        source_refs=("event:fictional-review-selected",),
        mutable_world=True,
    )
    forecast = SemanticAssertion.create(
        subject="situation:project-meridian-review",
        predicate="decision_will_be_confirmed",
        value=True,
        epistemic_type=EpistemicType.SIMULATED,
        confidence=0.5,
        valid_from=deadline,
        recorded_at=observed_at,
        fresh_until=deadline + timedelta(hours=1),
        source_refs=("simulation:fictional-decision-branch",),
        status=AssertionStatus.HYPOTHESIS,
        mutable_world=True,
    )
    owner_unknown = SemanticAssertion.create(
        subject="situation:project-meridian-review",
        predicate="decision_owner",
        value=None,
        epistemic_type=EpistemicType.ASSUMED,
        confidence=0.0,
        valid_from=observed_at,
        recorded_at=observed_at,
        fresh_until=deadline,
        source_refs=(),
        status=AssertionStatus.HYPOTHESIS,
        mutable_world=True,
    )
    rescheduled_fact = SemanticAssertion.create(
        subject="situation:project-meridian-review",
        predicate="scheduled_start",
        value="2031-05-14T17:00:00+00:00",
        epistemic_type=EpistemicType.OBSERVED,
        confidence=0.99,
        valid_from=observed_at + timedelta(hours=4),
        recorded_at=observed_at + timedelta(minutes=2, seconds=10),
        fresh_until=deadline,
        source_refs=("event:calendar-rescheduled",),
        supersedes=fact.assertion_id,
        mutable_world=True,
    )
    owner_fact = SemanticAssertion.create(
        subject="situation:project-meridian-review",
        predicate="decision_owner",
        value="role:fictional-review-owner",
        epistemic_type=EpistemicType.OBSERVED,
        confidence=0.95,
        valid_from=observed_at,
        recorded_at=observed_at + timedelta(minutes=5, seconds=10),
        fresh_until=deadline,
        source_refs=("event:envelope:meridian:notes-result:2",),
        mutable_world=True,
    )
    cancelled_goal = GoalRevision.create(
        goal_id=goal.goal_id,
        version=2,
        description=goal.description,
        priority=goal.priority,
        utility=goal.utility,
        success_criteria=goal.success_criteria,
        owner=goal.owner,
        status=GoalStatus.CANCELLED,
        deadline=deadline,
        kind=goal.kind,
        governing_goal_refs=goal.governing_goal_refs,
        origin=origin,
        intent_authority=authority,
        based_on_event_cursor=15,
        author="principal:fictional-user",
        revision_reason="fictional user switched the active topic",
        recorded_at=observed_at + timedelta(minutes=6, seconds=15),
        supersedes_revision_id=goal.revision_id,
    )
    current_goal = GoalRevision.create(
        goal_id="goal:plan-project-river",
        version=1,
        description="Plan the fictional Project River",
        priority=0.8,
        utility=1.0,
        success_criteria=("next planning decision is explicit",),
        owner="principal:fictional-user",
        status=GoalStatus.ACTIVE,
        deadline=None,
        kind=GoalKind.USER_AUTHORED,
        governing_goal_refs=(),
        origin=origin,
        intent_authority=authority,
        based_on_event_cursor=17,
        author="principal:fictional-user",
        revision_reason="fictional current topic",
        recorded_at=observed_at + timedelta(minutes=6, seconds=45),
    )
    current_outcome = OutcomeNode(
        node_id="outcome:river-plan",
        description="The next Project River planning decision is explicit",
        success_criteria=("next decision is explicit",),
    )
    action = ActionIntent(
        capability="publish-decision-card",
        arguments={"artifact_ref": "artifact:meridian-decision-card"},
        rationale="Only a separately authorized effect may publish the prepared artifact",
        required_authority=AuthorityLevel.ACT_REVERSIBLE,
        confidence=0.9,
    )
    capability = CapabilitySpec(
        name="publish-decision-card",
        description="Fictional external publication effect",
        required_authority=AuthorityLevel.ACT_REVERSIBLE,
    )
    empty_snapshot = SituationSnapshot(
        version=0,
        observed_at=observed_at,
        facts=MappingProxyType({}),
        entities=MappingProxyType({}),
        relations=MappingProxyType({}),
        goals=MappingProxyType({}),
        commitments=MappingProxyType({}),
        risks=MappingProxyType({}),
        opportunities=MappingProxyType({}),
        resources=MappingProxyType({}),
    )
    decision = PolicyEngine(
        AutonomyProfile(authority_ceiling=AuthorityLevel.PROPOSE)
    ).authorize(action, capability, empty_snapshot)
    return ExistingApiEvidence(
        goal=goal,
        cancelled_goal=cancelled_goal,
        current_goal=current_goal,
        outcome=outcome,
        current_outcome=current_outcome,
        order=order,
        coverage=coverage,
        fact=fact,
        owner_unknown=owner_unknown,
        rescheduled_fact=rescheduled_fact,
        owner_fact=owner_fact,
        forecast=forecast,
        action=action,
        action_allowed=decision.allowed,
        observation_budget=ObservationBudget(max_cost=3.0, max_sources=2),
    )


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    fixture_id: str
    canonical_event_count: int
    replay_cursor: int
    evaluated_cases: tuple[str, ...]
    synthetically_verified_cases: tuple[str, ...]
    specified_only_cases: tuple[str, ...]
    blocked_runtime_lanes: tuple[str, ...]

    def to_dict(self) -> JSONObject:
        return {
            "fixture_id": self.fixture_id,
            "canonical_event_count": self.canonical_event_count,
            "replay_cursor": self.replay_cursor,
            "evaluated_cases": list(self.evaluated_cases),
            "synthetically_verified_cases": list(self.synthetically_verified_cases),
            "specified_only_cases": list(self.specified_only_cases),
            "blocked_runtime_lanes": list(self.blocked_runtime_lanes),
            "evidence_level": "MIXED_SYNTHETIC_AND_SPECIFIED",
        }


async def run_conformance(path: Path = FIXTURE_PATH) -> ConformanceReport:
    """Run the fictional G1 boundary rehearsal against an embedded canonical log."""

    fixture = load_fixture(path)
    schema = load_schema()
    if fixture["fictional"] is not True or fixture["platform"] != "fictional-linux-workstation":
        raise ValueError("the committed G1 fixture must remain fictional and non-macOS")
    envelopes = tuple(
        _mapping(value, "envelope") for value in _items(fixture["envelopes"], "envelopes")
    )
    for envelope in envelopes:
        validate_envelope(envelope, schema)

    requests_by_id: dict[str, Mapping[str, object]] = {}
    for envelope in envelopes:
        if isinstance(envelope["source_request"], Mapping):
            request = _mapping(envelope["source_request"], "source request")
            requests_by_id[str(request["acquisition_request_id"])] = envelope
    for envelope in envelopes:
        if not isinstance(envelope["source_result"], Mapping):
            continue
        result = _mapping(envelope["source_result"], "source result")
        request = requests_by_id[str(result["acquisition_request_id"])]
        request_context = _mapping(request["context"], "request context")
        if (
            result["request_context_id"] != request_context["context_id"]
            or result["request_context_revision"] != request_context["context_revision"]
            or result["request_causal_cut"] != request_context["causal_cut"]
        ):
            raise AssertionError("source result does not preserve its request context basis")

    api = existing_api_evidence()
    if (
        api.goal.status is not GoalStatus.ACTIVE
        or api.order.authority_ceiling is not AuthorityLevel.PROPOSE
    ):
        raise AssertionError("G1 must retain explicit current intent and proposal-only work")
    if api.action_allowed:
        raise AssertionError("proposal-only work must not authorize an external effect")
    if api.fact.epistemic_type is api.forecast.epistemic_type:
        raise AssertionError("observed fact and simulated forecast must remain distinct")
    if api.forecast.status is not AssertionStatus.HYPOTHESIS:
        raise AssertionError("forecast must remain a hypothesis")

    envelope_events: dict[str, Event] = {}
    for envelope in envelopes:
        context = _mapping(envelope["context"], "context")
        correlation = _mapping(envelope["correlation"], "correlation")
        event = Event(
            id=f"event:{envelope['envelope_id']}",
            type=f"companion.situated_partner.{envelope['message_kind']}",
            source="fixture:situated-partner-g1",
            subject=str(context["situation_id"]),
            timestamp=datetime.fromisoformat(str(envelope["recorded_at"])),
            correlation_id=cast(str | None, correlation["session_id"]),
            causation_id=cast(str | None, correlation["causation_event_id"]),
            payload=cast(Mapping[str, JSONValue], envelope),
        )
        envelope_events[event.id] = event
    external_events = {
        "event:fictional-review-selected": Event(
            id="event:fictional-review-selected",
            type="companion.fixture.situation_selected",
            source="fixture:situated-partner-g1",
            subject="situation:project-meridian-review",
            timestamp=datetime(2031, 5, 14, 13, 59, tzinfo=UTC),
            payload={"fictional": True},
        ),
        "event:calendar-rescheduled": Event(
            id="event:calendar-rescheduled",
            type="companion.fixture.source_changed",
            source="fixture:situated-partner-g1",
            subject="situation:project-meridian-review",
            timestamp=datetime(2031, 5, 14, 14, 2, tzinfo=UTC),
            causation_id="event:envelope:meridian:calendar-request:1",
            payload={"fictional": True, "change": "scheduled_start"},
        ),
        "event:topic-switched": Event(
            id="event:topic-switched",
            type="companion.fixture.topic_switched",
            source="fixture:situated-partner-g1",
            subject="situation:project-river-plan",
            timestamp=datetime(2031, 5, 14, 14, 6, 30, tzinfo=UTC),
            causation_id=f"goal-revision-recorded:{api.cancelled_goal.revision_id}",
            payload={"fictional": True, "topic_id": "topic:river-plan"},
        ),
    }
    goal_events = {
        f"goal-revision-recorded:{revision.revision_id}": revision
        for revision in (api.goal, api.cancelled_goal, api.current_goal)
    }
    api_events = {
        event.id: event
        for event in (
            api.goal.to_event(source="fixture:intent"),
            api.fact.to_event(source="fixture:memory"),
            api.owner_unknown.to_event(source="fixture:memory"),
            api.forecast.to_event(source="fixture:memory"),
            api.order.to_event(source="fixture:work"),
            api.rescheduled_fact.to_event(source="fixture:memory"),
            api.owner_fact.to_event(source="fixture:memory"),
            api.cancelled_goal.to_event(source="fixture:intent"),
            api.current_goal.to_event(source="fixture:intent"),
        )
    }
    event_by_id = {**external_events, **api_events, **envelope_events}
    timeline = tuple(str(value) for value in _items(fixture["canonical_timeline"], "timeline"))
    if set(timeline) != set(event_by_id) or len(timeline) != len(event_by_id):
        raise AssertionError("fixture timeline and constructed canonical events differ")

    assertion_ids = {
        api.fact.assertion_id,
        api.owner_unknown.assertion_id,
        api.rescheduled_fact.assertion_id,
        api.owner_fact.assertion_id,
    }
    outcome_by_goal = {
        api.goal.revision_id: api.outcome.node_id,
        api.current_goal.revision_id: api.current_outcome.node_id,
    }
    for envelope in envelopes:
        context = _mapping(envelope["context"], "context")
        if not set(_items(context["supported_assertion_refs"], "supported refs")) <= assertion_ids:
            raise AssertionError("context cites an unknown supported assertion")
        unresolved_refs = set(
            _items(context["unresolved_assertion_refs"], "unresolved refs")
        )
        if not unresolved_refs <= assertion_ids:
            raise AssertionError("context cites an unknown unresolved assertion")
        if context["goal_revision_id"] not in {api.goal.revision_id, api.current_goal.revision_id}:
            raise AssertionError("context cites a goal outside the composed SDK records")
        if outcome_by_goal[str(context["goal_revision_id"])] != context["outcome_id"]:
            raise AssertionError("context outcome is inconsistent with its governing goal")
        task = envelope["task"]
        if isinstance(task, Mapping) and task["work_order_id"] != api.order.work_order_id:
            raise AssertionError("task cites a work order outside the composed SDK record")

    observer = PilotObserverProjection()
    async with NoemaKernel() as kernel:
        emitted_ids: set[str] = set()
        for expected_head, event_id in enumerate(timeline):
            actual_head = await kernel.store.latest_sequence()
            if expected_head != actual_head:
                raise AssertionError(
                    f"timeline head {expected_head} != canonical head {actual_head}"
                )
            event = event_by_id[event_id]
            if event.causation_id is not None and event.causation_id not in emitted_ids:
                raise AssertionError(f"{event.id} has a non-preceding causation reference")
            if event.id in envelope_events:
                envelope = _mapping(event.payload, "envelope")
                context = _mapping(envelope["context"], "context")
                if int(cast(int, context["causal_cut"])) != actual_head:
                    raise AssertionError(
                        f"{envelope['envelope_id']} causal cut does not match canonical head"
                    )
            goal_template = goal_events.get(event_id)
            if goal_template is None:
                stored = await kernel.emit_if_head(event, expected_head_sequence=expected_head)
            else:
                coordinator = IntentStewardCoordinator(
                    kernel,
                    validator=StrategicValidator(
                        StaticStrategicTrust(
                            origins=(goal_template.origin,),
                            authorities=(goal_template.intent_authority,),
                        )
                    ),
                    clock=lambda template=goal_template: template.recorded_at,
                    source="fixture:intent",
                )
                recorded = await coordinator.record_goal_revision(
                    goal_id=goal_template.goal_id,
                    description=goal_template.description,
                    priority=goal_template.priority,
                    utility=goal_template.utility,
                    success_criteria=goal_template.success_criteria,
                    owner=goal_template.owner,
                    status=goal_template.status,
                    deadline=goal_template.deadline,
                    kind=goal_template.kind,
                    governing_goal_refs=goal_template.governing_goal_refs,
                    origin=goal_template.origin,
                    intent_authority=goal_template.intent_authority,
                    author=goal_template.author,
                    revision_reason=goal_template.revision_reason,
                )
                if recorded != goal_template:
                    raise AssertionError("admitted goal differs from the frozen SDK record")
                stored = (await kernel.history())[-1]
            observer.apply(stored)
            emitted_ids.add(stored.id)
        history = await kernel.history()
        replayed = PilotObserverProjection()
        replayed.rebuild(history)

    if tuple(event.id for event in history) != timeline:
        raise AssertionError("canonical history does not match the frozen fixture timeline")
    strategic = StrategicProjection()
    strategic.rebuild(history)
    if strategic.current_goal_revision(api.goal.goal_id) != api.cancelled_goal:
        raise AssertionError("strategic replay did not restore terminal historical intent")
    if strategic.current_goal_revision(api.current_goal.goal_id) != api.current_goal:
        raise AssertionError("strategic replay did not restore current intent")
    work = WorkProjection()
    work.rebuild(history)
    if work.order(api.order.work_order_id) != api.order:
        raise AssertionError("work replay did not restore the composed work order")

    if replayed.event_cursor != observer.event_cursor:
        raise AssertionError("observer replay did not reach the canonical cut")
    if replayed.task_states != observer.task_states:
        raise AssertionError("observer replay changed task state")

    old_request = envelope_by_id(fixture, "envelope:meridian:calendar-request:1")
    cancellation = envelope_by_id(fixture, "envelope:meridian:calendar-cancelled:1")
    old_lifecycle = _mapping(old_request["lifecycle"], "old request lifecycle")
    cancellation_lifecycle = _mapping(cancellation["lifecycle"], "cancellation lifecycle")
    cancellation_payload = _mapping(cancellation["payload"], "cancellation payload")
    if old_lifecycle["superseded_by_envelope_id"] is not None:
        raise AssertionError("an immutable request cannot point to a future supersession")
    if cancellation_lifecycle["supersedes_envelope_id"] != old_request["envelope_id"]:
        raise AssertionError("reschedule did not supersede the obsolete check")
    if cancellation_lifecycle["cancelled_by_event_id"] != "event:calendar-rescheduled":
        raise AssertionError("cancellation lacks causal evidence")
    if cancellation_payload["business_cutoff_unchanged"] is not True:
        raise AssertionError("reschedule must not move an independent business cutoff")

    output = envelope_by_id(fixture, "envelope:meridian:decision-card:1")
    material = _mapping(output["material_output"], "material output")
    if material["generated_against_context_revision"] != material["revalidated_context_revision"]:
        raise AssertionError("material output was not revalidated for its current context")
    if material["understanding_evidence_refs"] or material["action_evidence_refs"]:
        raise AssertionError("generation cannot imply understanding or action")
    if not is_surface_eligible(output, output, current_goal_status=api.goal.status):
        raise AssertionError("revalidated current material output was not surface eligible")

    current_context = envelope_by_id(fixture, "envelope:river:context:3")
    late_result = envelope_by_id(fixture, "envelope:meridian:calendar-result:late")
    if is_surface_eligible(
        late_result,
        current_context,
        current_goal_status=api.current_goal.status,
    ):
        raise AssertionError("a stale result became eligible for the current topic")

    cases = _mapping(fixture["case_inputs"], "case inputs")
    if _mapping(cases["T02"], "T02")["expected_belief"] != "unknown":
        raise AssertionError("elapsed schedule time cannot establish an outcome")
    if _mapping(cases["T09"], "T09")["coverage_claim"] != "awake_only":
        raise AssertionError("sleep coverage must remain truthful")
    if _mapping(cases["T10"], "T10")["surface_eligible"] is not False:
        raise AssertionError("terminal intent must suppress stale presentation")
    if int(cast(int, _mapping(cases["T11"], "T11")["additional_calls"])) != 0:
        raise AssertionError("exhausted budgets cannot authorize hidden calls")
    if _mapping(cases["T13"], "T13")["canonical_observer_available"] is not True:
        raise AssertionError("canonical observer incorrectly depends on OTel")
    if _items(_mapping(cases["T25"], "T25")["observations"], "T25 observations"):
        raise AssertionError("excluded source produced an observation")
    if _mapping(cases["T30"], "T30")["learning_eligible"] is not False:
        raise AssertionError("solicited-only evidence cannot qualify Habit Learning")
    if _mapping(cases["T31"], "T31")["access_disposition"] != "deny":
        raise AssertionError("restricted material bypassed the storage gate")
    t35 = _mapping(cases["T35"], "T35")
    if t35["current_goal_revision_id"] != t35["governing_revision_id"]:
        raise AssertionError("historical intent displaced current intent")

    return ConformanceReport(
        fixture_id=str(fixture["fixture_id"]),
        canonical_event_count=len(history),
        replay_cursor=replayed.event_cursor,
        evaluated_cases=REQUIRED_CASES,
        synthetically_verified_cases=SYNTHETICALLY_VERIFIED_CASES,
        specified_only_cases=SPECIFIED_ONLY_CASES,
        blocked_runtime_lanes=(
            "durable-situation-watch-and-source-acquisition",
            "durable-observation-scope",
            "material-output-presentation-receipts",
            "reproducible-experiment-identity",
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
    args = parser.parse_args()
    report = asyncio.run(run_conformance(args.fixture))
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
