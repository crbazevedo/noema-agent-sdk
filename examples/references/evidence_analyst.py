"""Real Noema memory/intent/endogenous scan, plus an explicit local preparation bridge.

SDK scans remain shadow-only. The reference application owns timer scheduling,
permission/budget admission, a narrow bridge, and deterministic CSV computation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

from evidence_analyst_domain import reconcile, render_note, sha

from noema import (
    ActionIntent,
    AsyncScheduler,
    AutonomousAgent,
    AutonomousAgentConfig,
    BackgroundCognitiveBudget,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    CognitiveController,
    CognitiveResourceVector,
    Commitment,
    CommitmentClosureReason,
    CommitmentStatus,
    EndogenousShadowWorker,
    Event,
    ExecutionLocus,
    GoalKind,
    GoalStatus,
    IntentAuthority,
    IntentAuthorityScope,
    IntentStewardCoordinator,
    IntrinsicActivityKind,
    MemoryProjector,
    NoemaKernel,
    OriginKind,
    OriginProvenance,
    OutcomeActor,
    OutcomeNode,
    OutcomeRoleAssignment,
    PolicyEngine,
    RuleBasedReasoner,
    SemanticAssertion,
    SQLiteEventStore,
    StaticStrategicTrust,
    StrategicProjection,
    StrategicValidator,
)
from noema.memory import EpistemicType

GOAL = "goal:evidence-review"
COMMITMENT = "commitment:evidence-review"
SDK_COMMIT = "cd4ecde33659f0403d8920e96f1c17837c45c5ea"


def now():
    return datetime.now(UTC)


class ReferencePreparationBridge:
    """Allow only selected belief maintenance -> one locally authorized preparation."""

    def __init__(self, app):
        self.app = app
        self.reservations = {}
        self.keys = set()

    async def accept(self, selection, activity):
        app = self.app
        snapshot = await app.kernel.snapshot()
        goal = snapshot.goals.get(GOAL)
        refs = [r for r in activity.governing_intent_refs if r.goal_id == GOAL]
        current = await app.current_goal()
        reasons = []
        if activity.kind != IntrinsicActivityKind.BELIEF_MAINTENANCE:
            reasons.append("activity kind is outside local preparation allowlist")
        if activity.activity_id not in selection.selected_activity_ids:
            reasons.append("activity not selected")
        if not goal or goal.status != GoalStatus.ACTIVE:
            reasons.append("goal not active")
        if not refs or not current or refs[0].goal_revision_id != current.revision_id:
            reasons.append("governing goal revision changed")
        if not app.authorized:
            reasons.append("local preparation permission absent")
        key = sha(
            json.dumps(
                {
                    "revision": refs[0].goal_revision_id if refs else None,
                    "sources": app.claimed_hashes,
                    "scope": app.scope,
                },
                sort_keys=True,
            ).encode()
        )
        if key in self.keys:
            reasons.append("identical preparation already reserved")
        if app.metrics["preparations_reserved"] >= app.preparation_budget:
            reasons.append("lifetime preparation ceiling exhausted")
        if app.read_budget - app.metrics["source_reads_reserved"] < 4:
            reasons.append("need four reserved source reads for analysis and hash revalidation")
        if reasons:
            await app.emit(
                "reference.bridge_rejected",
                {
                    "selection_id": selection.selection_id,
                    "activity_id": activity.activity_id,
                    "reasons": reasons,
                    "idempotency_key": key,
                },
            )
            return
        # Admission captures the selection cut. A later SDK foreground event may
        # preempt its shadow epoch; it does not turn the shadow worker into an executor.
        app.metrics["preparations_reserved"] += 1
        app.metrics["source_reads_reserved"] += 4
        self.keys.add(key)
        args = {
            "selection_id": selection.selection_id,
            "activity_id": activity.activity_id,
            "inquiry_id": activity.inquiry_id,
            "goal_revision": current.revision_id,
            "goal_updated_at": goal.updated_at.isoformat(),
            "idempotency_key": key,
            "evidence_generation": app.evidence_generation,
        }
        self.reservations[key] = args
        await app.emit(
            "reference.bridge_admitted",
            {
                **args,
                "source_reads_reserved": 4,
                "scope": dict(app.scope),
                "evidence_refs": list(activity.evidence_refs),
                "execution_owner": "application_bridge",
            },
        )
        await app.emit("reference.preparation_requested", args)


class EvidenceAnalyst:
    def __init__(self, scenario, directory):
        if (
            not scenario.get("name")
            or Path(scenario["name"]).name != scenario["name"]
            or scenario["name"] in {".", ".."}
        ):
            raise ValueError("scenario name must be a basename")
        if (
            sum(
                op.get("op") == "revise_and_reauthorize" for op in scenario.get("interventions", [])
            )
            > 1
        ):
            raise ValueError("at most one explicit supported-revision request per scenario")
        self.scenario = deepcopy(scenario)
        self.claims = deepcopy(scenario["claims"])
        self.evidence_generation = 0
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.inputs = self.directory / "inputs"
        self.inputs.mkdir()
        self.output = self.directory / "artifacts"
        self.output.mkdir()
        files = scenario["files"]
        if len(files) != 2 or any(
            Path(name).name != name or not name.endswith(".csv") for name in files
        ):
            raise ValueError("exactly two basename-only local CSV filenames are required")
        self.paths = {name: self.inputs / name for name in sorted(files)}
        for name, text in files.items():
            self.paths[name].write_bytes(text.encode())
        self.claimed_hashes = {name: sha(text.encode()) for name, text in files.items()}
        self.scope = {k: scenario[k] for k in ["window_start", "window_end", "region"]}
        self.authorized = bool(scenario.get("authorized", True))
        self.read_budget = int(scenario.get("source_read_budget", 4))
        self.activity_remaining = int(scenario.get("activity_budget", 1))
        self.preparation_budget = int(scenario.get("preparation_budget", 1))
        self.wake_handles = []
        self.commitment_id = COMMITMENT
        self.grant_revision = None
        self.goal_deadline = now() + timedelta(hours=1)
        self.fail_after_stage = False
        self.metrics = {
            "source_reads_reserved": 0,
            "source_reads_used": 0,
            "source_bytes_read": 0,
            "preparations_reserved": 0,
            "capability_invocations": 0,
            "output_write_calls": 0,
            "output_bytes_written": 0,
            "output_verifier_reads": 0,
            "output_verifier_bytes": 0,
            "scans": 0,
            "sdk_selected_activities": 0,
            "current_publications": 0,
        }
        self.kernel = NoemaKernel(store=SQLiteEventStore(self.directory / "events.sqlite"))
        self.bridge = ReferencePreparationBridge(self)
        self.sources_read = asyncio.Event()
        self.scan_queued = asyncio.Event()
        self.selections = []
        self.failure = None
        self.started_monotonic = time.monotonic()
        self.wake_monotonic = None
        self.last_external_monotonic = None

    async def emit(self, event_type, payload, source="reference:evidence-bridge"):
        return await self.kernel.emit(Event(event_type, source, payload, subject=GOAL))

    async def current_goal(self):
        projection = StrategicProjection()
        projection.rebuild(await self.kernel.history())
        return projection.current_goal_revision(GOAL)

    async def record_goal(
        self, status=GoalStatus.ACTIVE, reason="initial local preparation request"
    ):
        self.goal = await self.steward.record_goal_revision(
            goal_id=GOAL,
            description="Reconcile supplied reports for "
            + str(self.scope["region"] or "all regions"),
            priority=0.9,
            utility=1.0,
            success_criteria=(
                "produce a source-cited, hash-verified note or explicitly partial finding",
            ),
            owner="fixture:user",
            status=status,
            deadline=self.goal_deadline,
            kind=GoalKind.USER_AUTHORED,
            governing_goal_refs=(),
            origin=self.origin,
            intent_authority=self.authority,
            author="fixture:user",
            revision_reason=reason,
        )
        return self.goal

    async def record_plan(self):
        roadmap = await self.steward.record_roadmap_revision(
            roadmap_id="roadmap:evidence-review",
            governing_goal_revision_ids=(self.goal.revision_id,),
            outcome_nodes=(
                OutcomeNode(
                    "reconciled-note",
                    "Prepare a factual comparison",
                    ("sources and arithmetic are independently checked",),
                ),
            ),
            assumptions=("supplied reports may use different time bases",),
            confidence=0.95,
            success_criteria=("a current factual note exists",),
            resource_envelope={
                "source_reads": float(self.read_budget),
                "preparations": float(self.preparation_budget),
            },
            intent_authority=self.authority,
            author="fixture:user",
            revision_reason="bounded local inquiry plan",
        )
        roles = OutcomeRoleAssignment.create(
            outcome_ref=roadmap.revision_id + "#reconciled-note",
            outcome_owner=OutcomeActor("fixture:user", ExecutionLocus.USER),
            decision_owner=OutcomeActor("fixture:user", ExecutionLocus.USER),
            executor=OutcomeActor("agent:evidence-analyst", ExecutionLocus.AGENT),
            verifier=OutcomeActor("verifier:local-readback", ExecutionLocus.AGENT),
            recorded_at=now(),
        )
        await self.steward.record_outcome_roles(roles)
        await self.steward.record_commitment(
            Commitment(
                id=self.commitment_id,
                description="Prepare and verify a source-cited local note",
                owner="fixture:user",
                priority=0.9,
                status=CommitmentStatus.ACTIVE,
                deadline=self.goal_deadline,
                governing_goal_refs=(GOAL,),
                roadmap_revision_id=roadmap.revision_id,
                outcome_node_id="reconciled-note",
                role_assignment_id=roles.assignment_id,
            ),
            intent_authority=self.authority,
        )

    async def setup(self):
        await self.kernel.start()
        self.origin = OriginProvenance(
            provenance_id="origin:local-fixture",
            kind=OriginKind.USER,
            principal_id="fixture:user",
            authentication_ref="fixture-authentication:no-real-account",
        )
        self.authority = IntentAuthority(
            authority_id="authority:local-preparation",
            principal_id="fixture:user",
            scope=IntentAuthorityScope.USER,
            allowed_goal_kinds=(GoalKind.USER_AUTHORED,),
            goal_refs=(),
            provenance_ref=self.origin.provenance_id,
        )
        trust = StaticStrategicTrust((self.origin,), (self.authority,))
        self.steward = IntentStewardCoordinator(self.kernel, validator=StrategicValidator(trust))
        await self.record_goal()
        await self.record_plan()
        self.grant_revision = self.goal.revision_id
        self.memory = MemoryProjector(self.kernel)
        await self.memory.start()
        for filename in self.paths:
            claim = self.claims[filename]
            event = await self.emit(
                "reference.source_claim",
                {
                    "file": filename,
                    "claimed_sha256": self.claimed_hashes[filename],
                    "claims": claim,
                    "epistemic_status": "reported, not verified from bytes",
                },
                source="fixture:prior-report",
            )
            for predicate in ["period_amount", "period_population"]:
                assertion = SemanticAssertion.create(
                    subject=GOAL,
                    predicate=predicate,
                    value=(
                        json.dumps(claim[predicate], sort_keys=True)
                        if isinstance(claim[predicate], (list, dict))
                        else claim[predicate]
                    ),
                    epistemic_type=EpistemicType.REPORTED,
                    confidence=0.8,
                    valid_from=now(),
                    recorded_at=now(),
                    fresh_until=now() + timedelta(hours=1),
                    source_refs=("event:" + event.id,),
                    mutable_world=True,
                )
                await self.kernel.emit(assertion.to_event(source="reference:reported-memory"))
        await self.kernel.bus.drain()
        await self.memory.stop()
        await self.emit(
            "reference.memory_projection_quiesced",
            {
                "reason": "initial reports projected; avoid derived checkpoint writes racing strict scan causal-cut admission"  # noqa: E501 - preserve frozen fixture/event text
            },
        )
        self.worker = EndogenousShadowWorker(self.kernel)
        await self.worker.start()
        registry = CapabilityRegistry()
        registry.register_function(
            CapabilitySpec(
                "reconcile_local_reports",
                "Read two allowed CSVs, reconcile and prepare local artifacts",
                input_schema={
                    "type": "object",
                    "required": ["goal_revision", "idempotency_key", "selection_id"],
                },
                idempotent=True,
                max_retries=0,
            ),
            self.analyze,
        )

        async def rule(request):
            return ActionIntent(
                "reconcile_local_reports",
                dict(request.trigger.payload),
                expected_value=1,
                confidence=1,
                attention_cost=0.1,
                rationale="explicit application bridge admits selected belief maintenance",
            )

        def guard(intent, capability, snapshot):
            del capability
            return self.admission_reason(dict(intent.arguments), snapshot)

        self.agent = AutonomousAgent(
            config=AutonomousAgentConfig(
                agent_id="evidence-analyst-reference",
                trigger_patterns=("reference.preparation_requested",),
            ),
            kernel=self.kernel,
            controller=CognitiveController(RuleBasedReasoner([rule])),
            capabilities=registry,
            policy=PolicyEngine(rules=(guard,)),
        )
        await self.agent.start()
        self.scheduler = AsyncScheduler(self.kernel)
        self.subscription = await self.kernel.bus.subscribe("reference.timer_fired", self.on_wake)
        await self.emit(
            "reference.local_grant",
            {
                "authorized": self.authorized,
                "source_read_budget": self.read_budget,
                "preparation_ceiling": self.preparation_budget,
                "activity_budget": self.activity_remaining,
                "allowed_files": list(self.paths),
                "output_directory": "artifacts",
                "scope": self.scope,
                "goal_revision": self.goal.revision_id,
            },
            source="fixture:request",
        )
        self.last_external_monotonic = time.monotonic()

    def admission_reason(self, args, snapshot):
        goal = snapshot.goals.get(GOAL)
        if not goal or goal.status != GoalStatus.ACTIVE:
            return "goal is not active"
        if self.goal.revision_id != args.get("goal_revision"):
            return "exact goal revision changed"
        if goal.updated_at.isoformat() != args.get("goal_updated_at"):
            return "goal revision changed"
        if self.evidence_generation != args.get("evidence_generation"):
            return "relevant reported evidence changed"
        if not self.authorized or self.grant_revision != args.get("goal_revision"):
            return "local preparation permission absent for exact revision"
        if now() >= self.goal_deadline:
            return "preparation deadline expired"
        if args.get("idempotency_key") not in self.bridge.reservations:
            return "no admitted application reservation"
        if self.metrics["source_reads_used"] > self.read_budget:
            return "source read budget exceeded"
        return None

    async def on_wake(self, event):
        if self.wake_monotonic is None:
            self.wake_monotonic = time.monotonic()
        current = await self.current_goal()
        if (
            not current
            or current.status != GoalStatus.ACTIVE
            or current.revision_id != event.payload["goal_revision"]
        ):
            await self.emit(
                "reference.wake_suppressed",
                {
                    "wake_id": event.payload["wake_id"],
                    "reason": "goal cancelled or superseded",
                },
            )
            return
        if self.activity_remaining <= 0:
            await self.emit(
                "reference.scan_suppressed",
                {
                    "wake_id": event.payload["wake_id"],
                    "reason": "total activity grant exhausted; no new SDK budget minted",
                },
            )
            return
        self.metrics["scans"] += 1
        self.scan_queued.set()
        budget = BackgroundCognitiveBudget.create(
            ceiling=CognitiveResourceVector(
                activities=1,
                compute_units=1.0,
                wall_time_seconds=60.0,
                attention_units=0.2,
                privacy_risk_units=0.0,
            )
        )
        selection = await self.worker.run_scan(budget=budget)
        if selection is None:
            await self.emit(
                "reference.scan_no_selection",
                {
                    "reason": "no admitted agenda: no current candidate or strict causal-cut admission lost"  # noqa: E501 - preserve frozen fixture/event text
                },
            )
            return
        self.selections.append(selection.to_dict())
        used = selection.consumed.activities
        self.activity_remaining = max(0, self.activity_remaining - used)
        self.metrics["sdk_selected_activities"] += used
        projection = await self.worker.current_projection()
        activities = {a.activity_id: a for a in projection.activities_for_epoch(selection.epoch_id)}
        await self.emit(
            "reference.selection_observed",
            {
                "selection_id": selection.selection_id,
                "selected": list(selection.selected_activity_ids),
                "deferred": list(selection.deferred_activity_ids),
                "sdk_estimated_consumption": selection.consumed.to_dict(),
                "remaining_activity_grant": self.activity_remaining,
                "not_measured_cpu_or_reads": True,
            },
        )
        for activity_id in selection.selected_activity_ids:
            await self.bridge.accept(selection, activities[activity_id])

    async def read_source(self, name, phase):
        if self.metrics["source_reads_used"] >= self.read_budget:
            raise ValueError("source read budget exhausted")
        self.metrics["source_reads_used"] += 1
        data = self.paths[name].read_bytes()
        self.metrics["source_bytes_read"] += len(data)
        await self.emit(
            "reference.source_read",
            {
                "file": name,
                "phase": phase,
                "sha256": sha(data),
                "bytes": len(data),
                "read_number": self.metrics["source_reads_used"],
            },
        )
        return data

    async def analyze(self, arguments, context):
        args = dict(arguments)
        self.metrics["capability_invocations"] += 1
        await self.emit(
            "reference.analysis_started",
            {**args, "capability": "reconcile_local_reports"},
        )
        try:
            contents = {name: await self.read_source(name, "analysis") for name in self.paths}
            self.sources_read.set()
            result = reconcile(
                contents,
                **self.scope,
                bases={name: self.claims[name]["basis"] for name in self.paths},
            )
            computed = await self.emit(
                "reference.analysis_computed",
                {
                    "goal_revision": args["goal_revision"],
                    "status": result["status"],
                    "metrics": result["metrics"],
                },
            )
            await asyncio.sleep(float(self.scenario.get("analysis_delay_seconds", 0.06)))
            current_goal = await self.current_goal()
            denial = (
                "exact canonical goal revision changed"
                if not current_goal or current_goal.revision_id != args["goal_revision"]
                else self.admission_reason(args, await self.kernel.snapshot())
            )
            if denial:
                await self.emit(
                    "reference.preparation_discarded",
                    {"goal_revision": args["goal_revision"], "reason": denial},
                )
                return CapabilityResult.fail(denial)
            current = {
                name: await self.read_source(name, "prepublication_revalidation")
                for name in self.paths
            }
            if any(sha(current[name]) != sha(contents[name]) for name in self.paths):
                await self.emit(
                    "reference.preparation_discarded",
                    {
                        "goal_revision": args["goal_revision"],
                        "reason": "source bytes changed after analysis",
                    },
                )
                return CapabilityResult.fail("source bytes changed after analysis")
            result["goal_revision"] = args["goal_revision"]
            result["idempotency_key"] = args["idempotency_key"]
            staging = self.output / "staging" / args["idempotency_key"]
            staging.mkdir(parents=True, exist_ok=True)
            payloads = {
                "note.md": render_note(result, args["goal_revision"]),
                "derived.csv": result.pop("derived_csv").encode(),
                "result.json": json.dumps(result, indent=2, sort_keys=True).encode(),
            }
            for name, data in payloads.items():
                (staging / name).write_bytes(data)
                self.metrics["output_write_calls"] += 1
                self.metrics["output_bytes_written"] += len(data)
            await self.emit(
                "reference.artifacts_staged",
                {
                    "goal_revision": args["goal_revision"],
                    "artifacts": [
                        {
                            "path": str((staging / name).relative_to(self.directory)),
                            "sha256": sha(data),
                            "bytes": len(data),
                        }
                        for name, data in payloads.items()
                    ],
                },
            )
            if self.fail_after_stage:
                await self.emit(
                    "reference.preparation_discarded",
                    {"reason": "injected failure after staged writes; no current publication"},
                )
                return CapabilityResult.fail("injected failure after staging")
            verification = []
            for name, data in payloads.items():
                actual = (staging / name).read_bytes()
                self.metrics["output_verifier_reads"] += 1
                self.metrics["output_verifier_bytes"] += len(actual)
                if actual != data:
                    raise ValueError("output readback differs")
                verification.append(
                    {
                        "path": str((staging / name).relative_to(self.directory)),
                        "sha256": sha(actual),
                        "bytes": len(actual),
                    }
                )
            verified = await self.emit(
                "reference.artifact_readback_verified",
                {
                    "goal_revision": args["goal_revision"],
                    "artifacts": verification,
                    "verifier": "local-readback",
                    "separate_external_oracle_required": True,
                },
            )
            current_goal = await self.current_goal()
            denial = (
                "exact canonical goal revision changed"
                if not current_goal or current_goal.revision_id != args["goal_revision"]
                else self.admission_reason(args, await self.kernel.snapshot())
            )
            if denial:
                return CapabilityResult.fail(denial)
            marker = {
                "status": result["status"],
                "goal_revision": args["goal_revision"],
                "artifacts": verification,
                "source_hashes": {name: sha(data) for name, data in contents.items()},
                "metrics": result["metrics"],
                "scope": result["scope"],
                "selection_id": args["selection_id"],
                "inquiry_id": args["inquiry_id"],
                "goal_fulfilled": result["status"] == "reconciled",
            }
            marker_bytes = json.dumps(marker, indent=2, sort_keys=True).encode()
            temporary = self.output / "current.partial"
            temporary.write_bytes(marker_bytes)
            os.replace(temporary, self.output / "current.json")
            self.metrics["output_write_calls"] += 1
            self.metrics["output_bytes_written"] += len(marker_bytes)
            self.metrics["current_publications"] += 1
            published = await self.emit("reference.current_artifact_published", marker)
            assertion = SemanticAssertion.create(
                subject=GOAL,
                predicate="reconciliation_status",
                value=result["status"],
                epistemic_type=EpistemicType.INFERRED,
                confidence=1.0,
                valid_from=now(),
                recorded_at=now(),
                source_refs=("event:" + published.id,),
                derivation_refs=("event:" + computed.id, "event:" + verified.id),
                fresh_until=now() + timedelta(hours=1),
                mutable_world=True,
            )
            events = [assertion.to_event(source="reference:verified-analysis")]
            if result["status"] == "reconciled":
                events.append(
                    Event(
                        "commitment.updated",
                        "reference:verified-analysis",
                        {
                            "id": self.commitment_id,
                            "status": "closed",
                            "closure_reason": "fulfilled",
                        },
                    )
                )
            return CapabilityResult.ok(
                {
                    "artifact_status": result["status"],
                    "current_marker": "artifacts/current.json",
                },
                facts={"evidence_note_status": result["status"]},
                events=events,
            )
        except (ValueError, OSError) as error:
            await self.emit(
                "reference.preparation_failed",
                {"error": str(error), "goal_revision": args.get("goal_revision")},
            )
            return CapabilityResult.fail(str(error))

    async def revise_and_reauthorize(self, operation):
        # Only the explicit local fixture request grants authority; a revision alone does not.
        scope = operation.get("scope")
        claims = operation.get("claims")
        from evidence_analyst_domain import instant

        try:
            valid = (
                isinstance(scope, dict)
                and set(scope) == {"region", "window_start", "window_end"}
                and (scope["region"] is None or isinstance(scope["region"], str))
                and isinstance(scope["window_start"], str)
                and isinstance(scope["window_end"], str)
                and instant(scope["window_end"]) > instant(scope["window_start"])
                and isinstance(claims, dict)
                and set(claims) == set(self.paths)
                and all(
                    isinstance(claims[n], dict)
                    and set(claims[n]) >= {"basis", "period_amount", "period_population"}
                    and isinstance(claims[n]["period_amount"], str)
                    and isinstance(claims[n]["period_population"], list)
                    and all(isinstance(i, str) for i in claims[n]["period_population"])
                    for n in self.paths
                )
                and sorted(claims[n]["basis"] for n in self.paths) == ["ingested_at", "occurred_at"]
                and operation.get("revision_kind") == "report_scope"
                and isinstance(operation.get("wake_delay_seconds"), (int, float))
                and not isinstance(operation.get("wake_delay_seconds"), bool)
                and isinstance(operation.get("deadline_seconds"), (int, float))
                and not isinstance(operation.get("deadline_seconds"), bool)
                and math.isfinite(operation["wake_delay_seconds"])
                and math.isfinite(operation["deadline_seconds"])
                and 0 < operation["wake_delay_seconds"] < operation["deadline_seconds"]
            )
        except (ValueError, TypeError, KeyError, OverflowError):
            valid = False
        self.authorized = False
        self.grant_revision = None
        for handle in self.wake_handles:
            if not handle.task.done():
                handle.cancel()
        await self.emit(
            "reference.obsolete_wakes_cancelled",
            {"old_goal_revision": self.goal.revision_id},
        )
        if not valid:
            await self.record_goal(
                GoalStatus.CANCELLED, "unsupported revision requires clarification"
            )
            await self.emit(
                "reference.revision_escalated",
                {"reason": "unsupported scope or missing updated reported claims"},
            )
            return
        from evidence_analyst_domain import instant

        start, end = instant(scope["window_start"]), instant(scope["window_end"])
        if end <= start:
            raise ValueError("invalid revised window")
        self.scope = deepcopy(scope)
        self.claims = deepcopy(claims)
        self.evidence_generation += 1
        self.goal_deadline = now() + timedelta(seconds=float(operation["deadline_seconds"]))
        await self.steward.transition_commitment(
            self.commitment_id,
            to_state=CommitmentStatus.CLOSED,
            closure_reason=CommitmentClosureReason.SUPERSEDED,
            intent_authority=self.authority,
            author="fixture:user",
            reason="explicit supported goal scope supersedes old preparation",
        )
        await self.record_goal(reason="supported factual scope revision with a new bounded wake")
        self.commitment_id = COMMITMENT + ":" + self.goal.revision_id
        await self.record_plan()
        # Old capability finishes before reprojecting; exact revision fence discards it.
        await self.agent.wait_until_idle()
        await self.kernel.bus.drain()
        await self.memory.start()
        for name in self.paths:
            event = await self.emit(
                "reference.source_claim",
                {
                    "file": name,
                    "claims": self.claims[name],
                    "scope": self.scope,
                    "goal_revision": self.goal.revision_id,
                    "epistemic_status": "reported, not verified",
                },
            )
            for predicate in ["period_amount", "period_population"]:
                value = self.claims[name][predicate]
                assertion = SemanticAssertion.create(
                    subject=GOAL,
                    predicate=predicate,
                    value=json.dumps(value, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else value,
                    epistemic_type=EpistemicType.REPORTED,
                    confidence=0.8,
                    valid_from=now(),
                    recorded_at=now(),
                    fresh_until=now() + timedelta(hours=1),
                    source_refs=("event:" + event.id,),
                    mutable_world=True,
                )
                await self.kernel.emit(
                    assertion.to_event(source="reference:revised-reported-memory")
                )
        await self.kernel.bus.drain()
        await self.memory.stop()
        await self.emit(
            "reference.memory_projection_quiesced",
            {"reason": "revised report claims projected; strict scan admission boundary"},
        )
        self.authorized = operation.get("renew_authorization") is True
        if self.authorized:
            self.grant_revision = self.goal.revision_id
        due = now() + timedelta(seconds=float(operation["wake_delay_seconds"]))
        await self.emit(
            "reference.revision_grant",
            {
                "authorized": self.authorized,
                "goal_revision": self.goal.revision_id,
                "scope": self.scope,
                "allowed_files": list(self.paths),
                "output_directory": "artifacts",
                "due_at": due.isoformat(),
                "deadline": self.goal_deadline.isoformat(),
                "source_reads_reserved": self.metrics["source_reads_reserved"],
                "source_reads_used": self.metrics["source_reads_used"],
                "lifetime_read_ceiling": self.read_budget,
                "lifetime_preparation_ceiling": self.preparation_budget,
                "remaining_activity_grant": self.activity_remaining,
                "refund": 0,
            },
        )
        if not self.authorized:
            await self.emit("reference.revision_escalated", {"reason": "renewed permission absent"})
            return
        revision = self.goal.revision_id
        wake_id = "wake:revised:" + str(len(self.wake_handles))
        await self.emit(
            "reference.wake_scheduled",
            {
                "wake_id": wake_id,
                "goal_revision": revision,
                "due_at": due.isoformat(),
                "scheduler_kind": "process_local_asyncio",
            },
        )
        self.wake_handles.append(
            self.scheduler.at(
                due,
                lambda: Event(
                    "reference.timer_fired",
                    "scheduler:actual-asyncio",
                    {"wake_id": wake_id, "goal_revision": revision},
                    subject=GOAL,
                ),
            )
        )

    async def intervene(self, operation):
        phase = operation["phase"]
        if phase == "before_wake":
            await asyncio.sleep(float(self.scenario.get("wake_delay_seconds", 0.06)) / 2)
        elif phase == "after_source_reads":
            await asyncio.wait_for(self.sources_read.wait(), 2)
        elif phase == "while_scan_queued":
            await asyncio.wait_for(self.scan_queued.wait(), 2)
        else:
            raise ValueError("unsupported intervention phase")
        op = operation["op"]
        if op == "revise_and_reauthorize":
            await self.revise_and_reauthorize(operation)
        elif op == "cancel":
            await self.record_goal(GoalStatus.CANCELLED, "explicit synthetic cancellation")
        elif op == "revise":
            self.scope["region"] = operation.get("region")
            await self.record_goal(reason="explicit synthetic scope revision")
        elif op == "revoke":
            self.authorized = False
        elif op == "replace_file":
            name = operation["file"]
            if name not in self.paths:
                raise ValueError("replacement outside allowed fixture files")
            self.paths[name].write_bytes(operation["text"].encode())
        elif op == "new_source_claim":
            name = operation["file"]
            if name not in self.paths:
                raise ValueError("claim outside allowed sources")
            self.claims[name].update(operation["claims"])
            self.evidence_generation += 1
            event = await self.emit(
                "reference.source_claim",
                {
                    "file": name,
                    "claims": self.claims[name],
                    "generation": self.evidence_generation,
                    "epistemic_status": "reported, not verified from bytes",
                },
                source="fixture:new-report",
            )
            for predicate in ["period_amount", "period_population"]:
                value = self.claims[name][predicate]
                assertion = SemanticAssertion.create(
                    subject=GOAL,
                    predicate=predicate,
                    value=json.dumps(value, sort_keys=True)
                    if isinstance(value, (list, dict))
                    else value,
                    epistemic_type=EpistemicType.REPORTED,
                    confidence=0.8,
                    valid_from=now(),
                    recorded_at=now(),
                    fresh_until=now() + timedelta(hours=1),
                    source_refs=("event:" + event.id,),
                    mutable_world=True,
                )
                await self.kernel.emit(assertion.to_event(source="reference:new-reported-memory"))
        elif op == "unrelated_event":
            await self.emit(
                "reference.unrelated_observation",
                {"value": operation.get("value", "non-governing fixture observation")},
                source="fixture:unrelated",
            )
        elif op == "fail_after_stage":
            self.fail_after_stage = True
        else:
            raise ValueError("unsupported intervention")
        await self.emit(
            "reference.external_intervention",
            operation,
            source="fixture:external-change",
        )

    async def run(self):
        await self.setup()
        wake_id = "wake:initial"
        captured = self.goal.revision_id
        due = now() + timedelta(seconds=float(self.scenario.get("wake_delay_seconds", 0.06)))
        await self.emit(
            "reference.wake_scheduled",
            {
                "wake_id": wake_id,
                "goal_revision": captured,
                "due_at": due.isoformat(),
                "scheduler_kind": "process_local_asyncio",
                "restart_timer_recovery": "unsupported",
                "reason": "inspect existing relevant memory contradictions",
            },
        )
        scheduled_monotonic = time.monotonic()
        handle = self.scheduler.at(
            due,
            lambda: Event(
                "reference.timer_fired",
                "scheduler:actual-asyncio",
                {"wake_id": wake_id, "goal_revision": captured},
                subject=GOAL,
            ),
        )
        self.wake_handles.append(handle)
        changes = [
            asyncio.create_task(self.intervene(op)) for op in self.scenario.get("interventions", [])
        ]
        try:
            if changes:
                await asyncio.gather(*changes)
            await asyncio.gather(*(h.task for h in self.wake_handles), return_exceptions=True)
            await self.kernel.bus.drain()
            await self.agent.wait_until_idle()
            await self.kernel.bus.drain()
            if self.scenario.get("repeat_scan"):
                repeated = self.scheduler.at(
                    now() + timedelta(seconds=0.01),
                    lambda: Event(
                        "reference.timer_fired",
                        "scheduler:actual-asyncio",
                        {"wake_id": "wake:repeat", "goal_revision": captured},
                        subject=GOAL,
                    ),
                )
                await repeated.task
                await self.kernel.bus.drain()
                await self.agent.wait_until_idle()
                await self.kernel.bus.drain()
            history = await self.kernel.history()
            snapshot = await self.kernel.snapshot()
            current = await self.current_goal()
            marker = self.output / "current.json"
            report = {
                "scenario": self.scenario["name"],
                "original_frozen_sdk_commit": SDK_COMMIT,
                "sdk_source": "installed/repository noema import; record checkout separately",
                "reference": "evidence-analyst",
                "mechanisms": [
                    "IntentStewardCoordinator",
                    "MemoryProjector",
                    "SemanticAssertion",
                    "EndogenousShadowWorker",
                    "AsyncScheduler",
                    "AutonomousAgent",
                    "CapabilityRegistry",
                    "SQLiteEventStore",
                ],
                "application_bridge": "ReferencePreparationBridge; SDK endogenous worker remains shadow-only",  # noqa: E501 - preserve frozen fixture/event text
                "scheduler_kind": "process_local_asyncio",
                "restart_timer_recovery": "unsupported",
                "reasoner_kind": "deterministic_rule_based_no_model",
                "bus_errors": [
                    {"event": event.type, "error": repr(error)}
                    for event, error in self.kernel.bus.errors
                ],
                "metrics": self.metrics,
                "scope": self.scope,
                "current_goal_revision": current.revision_id if current else None,
                "current_goal_status": current.status.value if current else None,
                "selections": self.selections,
                "real_wake_delay_seconds": None
                if self.wake_monotonic is None
                else self.wake_monotonic - scheduled_monotonic,
                "source_read_budget": self.read_budget,
                "events": [e.to_dict() for e in history],
                "current_artifact": json.loads(marker.read_text()) if marker.exists() else None,
                "commitment_status": snapshot.commitments.get(self.commitment_id).status.value,
                "elapsed_seconds": time.monotonic() - self.started_monotonic,
            }
            (self.directory / "trace.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n"
            )
            (self.directory / "scenario.json").write_text(
                json.dumps(self.scenario, indent=2, sort_keys=True) + "\n"
            )
            return report
        finally:
            for task in changes:
                if not task.done():
                    task.cancel()
            await self.scheduler.stop()
            await self.agent.stop()
            await self.worker.stop()
            await self.memory.stop()
            await self.kernel.stop()


async def run_scenario(scenario, directory):
    app = EvidenceAnalyst(scenario, directory)
    try:
        return await app.run()
    except Exception as error:
        try:
            history = [e.to_dict() for e in await app.kernel.history()]
        except Exception:
            history = []
        (app.directory / "failure_trace.json").write_text(
            json.dumps(
                {
                    "scenario": scenario,
                    "error": repr(error),
                    "metrics": app.metrics,
                    "events": history,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        if app.kernel.started:
            await app.kernel.stop()
        raise


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-all", action="store_true")
    args = parser.parse_args()
    from evidence_analyst_fixtures import public_scenario, public_scenarios

    cases = (
        json.loads(args.scenarios.read_text())
        if args.scenarios
        else (public_scenarios() if args.public_all else [public_scenario()])
    )
    results = []
    args.output.mkdir(parents=True, exist_ok=True)
    for case in cases:
        try:
            report = await run_scenario(case, args.output / case["name"])
            results.append(
                {
                    "scenario": case["name"],
                    "metrics": report["metrics"],
                    "current_status": report["current_artifact"]["status"]
                    if report["current_artifact"]
                    else None,
                    "trace": case["name"] + "/trace.json",
                }
            )
        except Exception as error:
            results.append({"scenario": case["name"], "failed": True, "error": repr(error)})
        finally:
            (args.output / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
