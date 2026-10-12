"""A real SDK work-graph reference with independent review and local packaging.

Deterministic planner and synthetic stimuli; actual public work-control APIs,
agent policy/capabilities, SQLite events and local file effects. No deployment.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import sys
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from noema import (
    ActionIntent,
    ActionPrerequisite,
    AgentPresence,
    AuthorityLevel,
    AutonomousAgent,
    AutonomousAgentConfig,
    AwarenessCoverage,
    AwarenessDemand,
    CapabilityManifest,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    CognitiveController,
    CompetenceBasis,
    CompetenceEstimate,
    DurableWorkCoordinator,
    Event,
    FakePlanner,
    NoemaKernel,
    OrientationBarrier,
    PolicyEngine,
    PresenceStatus,
    RuleBasedReasoner,
    SourceState,
    SQLiteEventStore,
    WorkDependency,
    WorkNode,
    WorkNodeKind,
    WorkOrder,
    WorkProjection,
)

START = datetime(2026, 10, 12, 12, tzinfo=UTC)


class ReleaseSteward:
    def __init__(
        self,
        root: Path,
        *,
        independent_verifier=True,
        factor="1",
        source_csv="id,amount\n a ,1.25\nb,-2.00\n",
    ):
        self.root = root
        self.now = START
        self.independent_verifier = independent_verifier
        self.revision = 1
        self.features = ["trim identifiers", "scale decimal amounts"]
        self.factor = str(factor)
        if not Decimal(self.factor).is_finite():
            raise ValueError("factor must be finite")
        self.source_csv = source_csv
        self.freshness = 1.0
        self.old_lease = None
        self.effects = []
        self.decisions = []
        self.stale_rejections = 0
        self.presence_occurrence = 0
        self.kernel = NoemaKernel(store=SQLiteEventStore(root / "events.sqlite"))
        self.agents = {}
        self.coordinator = self.make_coordinator()

    def make_coordinator(self):
        nodes = (
            WorkNode(
                "prepare",
                WorkNodeKind.PREPARE,
                "prepare current release inputs",
                ("prepare",),
                ("current prepared input exists",),
            ),
            WorkNode(
                "verify",
                WorkNodeKind.VERIFY,
                "independently inspect prepared input",
                ("verify",),
                ("independent input verification passes",),
                verification_of=("prepare",),
            ),
            WorkNode(
                "package",
                WorkNodeKind.RELEASE,
                "build local release archive",
                ("package",),
                ("local release package exists",),
                epistemic_prerequisites=(ActionPrerequisite("release-source", 0.9, 0.9),),
            ),
        )
        planner = FakePlanner(
            nodes=nodes,
            dependencies=(WorkDependency("prepare", "verify"), WorkDependency("verify", "package")),
            assumptions=("release source revision and constraints remain current",),
            done_conditions=("current local package independently read back",),
            replan_event_types=("situation.release_constraints_changed",),
            clock=lambda: self.now,
        )
        return DurableWorkCoordinator(
            self.kernel,
            planner=planner,
            lease_duration=timedelta(minutes=1),
            clock=lambda: self.now,
        )

    def coverage(self):
        return AwarenessCoverage.from_inputs(
            (
                SourceState(
                    source_id="release-source",
                    domain="release",
                    last_observed_at=self.now,
                    last_cursor=f"revision-{self.revision}",
                    change_hazard=1,
                    confidence=1,
                    refresh_cost=1,
                    captured_at=self.now,
                ),
            ),
            (
                AwarenessDemand(
                    source_id="release-source",
                    governing_goal_refs=("release-goal",),
                    relevance=1,
                    decision_sensitivity=1,
                    required_freshness=0.9,
                    required_confidence=0.9,
                ),
            ),
            freshness_by_source={"release-source": self.freshness},
        )

    async def emit(self, kind, payload):
        return await self.kernel.emit(Event(kind, "release-reference", payload, timestamp=self.now))

    async def start(self):
        await self.kernel.start()
        await self.emit(
            "goal.created", {"id": "release-goal", "description": "Build current local package"}
        )
        await self.emit(
            "commitment.created",
            {
                "id": "release-commitment",
                "owner": "release-steward",
                "description": "Prepare, independently inspect and read back a local release",
                "status": "active",
            },
        )
        await self.emit("fact.observed", {"key": "release.revision", "value": self.revision})
        await self.emit("fact.observed", {"key": "release.effect_allowed", "value": True})
        await self.emit(
            "fact.observed",
            {
                "key": "release.requirements",
                "value": {
                    "features": self.features,
                    "factor": self.factor,
                    "source_sha256": hashlib.sha256(self.source_csv.encode()).hexdigest(),
                },
            },
        )
        self.order = WorkOrder.create(
            purpose="Prepare a verified local release package",
            governing_goal_refs=("release-goal",),
            created_from=("local-owner-request",),
            priority=0.9,
            desired_outcome="current local package independently read back",
            success_criteria=("current local package independently read back",),
            created_at=self.now,
            deadline=self.now + timedelta(hours=1),
            authority_ceiling=AuthorityLevel.ACT_REVERSIBLE,
        )
        await self.coordinator.record_work_order(self.order)
        workers = {
            "builder": {"prepare": 0.95, "verify": 0.99},
            "replacement": {"prepare": 0.8},
            "reviewer": {"verify": 0.95},
            "packager": {"package": 0.95},
        }
        for worker, skills in workers.items():
            status = PresenceStatus.AVAILABLE
            if worker == "reviewer" and not self.independent_verifier:
                status = PresenceStatus.OFFLINE
            await self.presence(worker, status)
            await self.coordinator.record_manifest(
                CapabilityManifest.create(
                    agent_id=worker, capabilities=tuple(skills), recorded_at=self.now
                )
            )
            for capability, score in skills.items():
                await self.coordinator.record_competence(
                    CompetenceEstimate.create(
                        agent_id=worker,
                        capability=capability,
                        score=score,
                        evidence_confidence=1,
                        basis=CompetenceBasis.SEEDED,
                        evidence_refs=(),
                        estimated_at=self.now,
                    )
                )
            registry = CapabilityRegistry()
            for capability in skills:

                async def invoke(arguments, context, operation=capability):
                    return await self.execute(operation, arguments, context.agent_id)

                registry.register_function(
                    CapabilitySpec(capability, capability, idempotent=True), invoke
                )

            def rule(request, identity=worker):
                if request.trigger.payload.get("worker") != identity:
                    return None
                return ActionIntent(
                    request.trigger.payload["operation"],
                    request.trigger.payload["arguments"],
                    expected_value=10,
                    confidence=1,
                    rationale="execute a currently leased work node under separate effect policy",
                )

            def gate(intent, spec, snapshot, identity=worker):
                del spec
                args = intent.arguments
                lease = self.coordinator.projection.active_lease(args["lease_id"])
                if (
                    lease is None
                    or lease.agent_id != identity
                    or lease.expires_at <= self.now
                    or lease.fencing_token != args["token"]
                    or not self.coordinator.projection.graph_is_active(lease.graph_id)
                ):
                    return "current active fenced work ownership required"
                if snapshot.fact("release.revision") != args["revision"]:
                    return "release revision changed"
                if not snapshot.fact("release.effect_allowed"):
                    return "local effect permission revoked"
                return None

            agent = AutonomousAgent(
                config=AutonomousAgentConfig(
                    agent_id=worker, trigger_patterns=("external.release_work",)
                ),
                kernel=self.kernel,
                controller=CognitiveController(RuleBasedReasoner([rule])),
                capabilities=registry,
                policy=PolicyEngine(rules=(gate,)),
            )
            self.agents[worker] = agent
            await agent.start()

    async def presence(self, worker, status, *, seconds=3600, observation_id=None):
        self.presence_occurrence += 1
        await self.coordinator.record_presence(
            AgentPresence(
                worker,
                status,
                1,
                self.now,
                self.now + timedelta(seconds=seconds),
                observation_id=observation_id or f"{worker}:observation:{self.presence_occurrence}",
            )
        )

    def predecessor_path(self, graph_id, node):
        completion = self.coordinator.projection.completion(graph_id, node)
        return Path(completion.artifact_refs[0])

    async def effect_is_current(self, arguments, worker):
        await self.coordinator.frontier(self.order.work_order_id, coverage=self.coverage())
        lease = self.coordinator.projection.active_lease(arguments["lease_id"])
        snapshot = await self.kernel.snapshot()
        if lease:
            graph = self.coordinator.projection.graph(lease.graph_id)
            node = next(node for node in graph.nodes if node.node_id == lease.node_id)
            if (
                OrientationBarrier()
                .evaluate(node.node_id, node.epistemic_prerequisites, self.coverage())
                .would_block
            ):
                return False
        return bool(
            lease
            and lease.agent_id == worker
            and lease.expires_at > self.now
            and lease.fencing_token == arguments["token"]
            and self.coordinator.projection.graph_is_active(lease.graph_id)
            and snapshot.fact("release.revision") == arguments["revision"]
            and snapshot.fact("release.effect_allowed")
        )

    async def execute(self, operation, arguments, worker):
        revision, graph_id = arguments["revision"], arguments["graph_id"]
        basename = f"v{revision}-g{arguments['graph_version']}-{arguments['token']}"
        extra_facts = {}
        if operation == "prepare":
            payload = {
                "revision": revision,
                "features": self.features,
                "source_sha256": hashlib.sha256(json.dumps(self.features).encode()).hexdigest(),
            }
            payload["factor"] = self.factor
            module = (
                "import csv, io, json, sys\nfrom decimal import Decimal\n"
                + f"FACTOR = {self.factor!r}\n"
                + "def transform(text):\n"
                + "    return [{'id': row['id'].strip(),\n"
                + "             'amount': str(Decimal(row['amount']) * Decimal(FACTOR))}\n"
                + "            for row in csv.DictReader(io.StringIO(text))]\n"
                + "if __name__ == '__main__':\n"
                + "    print(json.dumps(transform(sys.stdin.read()), sort_keys=True))\n"
            )
            software = {
                "transform.py": module,
                "fixture.csv": self.source_csv,
                "spec.json": json.dumps(
                    {
                        "revision": revision,
                        "factor": self.factor,
                        "input_columns": ["id", "amount"],
                        "output_fields": ["id", "amount"],
                    }
                ),
            }
            payload["software"] = {}
            for name, text in software.items():
                if not await self.effect_is_current(arguments, worker):
                    return CapabilityResult.fail("work authority changed before source write")
                artifact = self.root / f"{basename}-{name}"
                await asyncio.to_thread(artifact.write_text, text)
                payload["software"][name] = str(artifact)
            path = self.root / f"prepared-{basename}.json"
            if not await self.effect_is_current(arguments, worker):
                return CapabilityResult.fail("work authority changed before file write")
            await asyncio.to_thread(path.write_text, json.dumps(payload, sort_keys=True))
        elif operation == "verify":
            path_in = self.predecessor_path(graph_id, "prepare")
            prepared = json.loads(await asyncio.to_thread(path_in.read_text))
            executor = self.coordinator.projection.worker_for_node(graph_id, "prepare")
            passed = (
                worker != executor
                and prepared["revision"] == self.revision
                and prepared["features"] == self.features
            )
            if not passed:
                return CapabilityResult.fail("independent input inspection failed")
            software = prepared["software"]
            tested_bytes = {
                name: await asyncio.to_thread(Path(file).read_bytes)
                for name, file in software.items()
            }
            expected_spec = {
                "revision": revision,
                "factor": self.factor,
                "input_columns": ["id", "amount"],
                "output_fields": ["id", "amount"],
            }
            try:
                fixture = tested_bytes["fixture.csv"].decode("utf-8")
                spec = json.loads(tested_bytes["spec.json"])
            except (ValueError, UnicodeDecodeError, KeyError):
                return CapabilityResult.fail("prepared software contract is unreadable")
            if (
                fixture != self.source_csv
                or spec != expected_spec
                or prepared.get("factor") != self.factor
            ):
                return CapabilityResult.fail("prepared fixture/spec differs from accepted contract")
            tests = []
            probes = [fixture, "id,amount\n probe ,-0.50\nzero,0\n"]
            for probe in probes:
                expected_rows = [
                    {
                        "id": row["id"].strip(),
                        "amount": str(Decimal(row["amount"]) * Decimal(self.factor)),
                    }
                    for row in csv.DictReader(io.StringIO(probe))
                ]
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-I",
                    software["transform.py"],
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(probe.encode()), 3)
                except TimeoutError:
                    process.kill()
                    await process.wait()
                    return CapabilityResult.fail("transform subprocess timed out")
                try:
                    observed_rows = json.loads(stdout)
                except (ValueError, UnicodeDecodeError):
                    observed_rows = None
                correct = process.returncode == 0 and observed_rows == expected_rows
                tests.append(
                    {
                        "passed": correct,
                        "returncode": process.returncode,
                        "expected": expected_rows,
                        "observed": observed_rows,
                        "stderr": stderr.decode(errors="replace"),
                    }
                )
            if not all(test["passed"] for test in tests):
                await self.emit("reference.software_tests_failed", {"tests": tests})
                return CapabilityResult.fail("independent subprocess transform tests failed")
            for name, file in software.items():
                if await asyncio.to_thread(Path(file).read_bytes) != tested_bytes[name]:
                    return CapabilityResult.fail("software bytes changed during verification")
            path = self.root / f"verification-{basename}.json"
            receipt = {
                "passed": passed,
                "verifier": worker,
                "executor": executor,
                "revision": revision,
                "input_sha256": hashlib.sha256(path_in.read_bytes()).hexdigest(),
                "tests": tests,
                "software_sha256": {
                    name: hashlib.sha256(data).hexdigest() for name, data in tested_bytes.items()
                },
            }
            if not await self.effect_is_current(arguments, worker):
                return CapabilityResult.fail("work authority changed before verification write")
            await asyncio.to_thread(path.write_text, json.dumps(receipt, sort_keys=True))
            extra_facts["release.software_test_report"] = receipt
        else:
            source = self.predecessor_path(graph_id, "prepare")
            receipt_path = self.predecessor_path(graph_id, "verify")
            prepared = json.loads(await asyncio.to_thread(source.read_text))
            receipt = json.loads(await asyncio.to_thread(receipt_path.read_text))
            if (
                prepared["revision"] != revision
                or not receipt["passed"]
                or receipt["input_sha256"] != hashlib.sha256(source.read_bytes()).hexdigest()
            ):
                return CapabilityResult.fail(
                    "package inputs no longer match independent inspection"
                )
            members = {
                "prepared.json": source.read_bytes(),
                "verification.json": receipt_path.read_bytes(),
                "README.txt": b"Run locally: python transform.py < fixture.csv\n",
            }
            for name, file in prepared["software"].items():
                data = await asyncio.to_thread(Path(file).read_bytes)
                if hashlib.sha256(data).hexdigest() != receipt["software_sha256"][name]:
                    return CapabilityResult.fail("tested source bytes changed before packaging")
                members[name] = data
            package_manifest = {
                "revision": revision,
                "graph_id": graph_id,
                "graph_version": arguments["graph_version"],
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in members.items()},
            }
            members["manifest.json"] = json.dumps(package_manifest, sort_keys=True).encode()
            path = self.root / f"release-{basename}.zip"

            def package():
                with zipfile.ZipFile(path, "w") as archive:
                    for name, data in members.items():
                        archive.writestr(name, data)

            if not await self.effect_is_current(arguments, worker):
                return CapabilityResult.fail("work authority changed before package write")
            await asyncio.to_thread(package)
            extra_facts["release.package_manifest"] = package_manifest
        self.effects.append(
            {
                "operation": operation,
                "path": str(path),
                "worker": worker,
                "revision": revision,
                "graph_id": graph_id,
                "lease_id": arguments["lease_id"],
                "token": arguments["token"],
            }
        )
        return CapabilityResult.ok(
            {"path": str(path)},
            facts={f"release.result.{arguments['lease_id']}": str(path), **extra_facts},
        )

    async def step(self, *, lease_only=False):
        frontier = await self.coordinator.frontier(
            self.order.work_order_id, coverage=self.coverage()
        )
        await self.emit(
            "reference.work_frontier",
            {
                "graph_id": frontier.graph_id,
                "ready": [n.node_id for n in frontier.ready],
                "invalidated": frontier.invalidated,
                "dependency_blocked": list(frontier.dependency_blocked),
                "epistemic_blocked": list(frontier.epistemic_blocked),
            },
        )
        leases = await self.coordinator.assign_ready(
            self.order.work_order_id, coverage=self.coverage()
        )
        if lease_only:
            self.old_lease = leases[0] if leases else None
            return
        if not leases:
            await self.emit(
                "reference.dispatch_blocked", {"reason": "no eligible work or current worker"}
            )
        for lease in leases:
            graph = self.coordinator.projection.graph(lease.graph_id)
            await self.emit(
                "external.release_work",
                {
                    "worker": lease.agent_id,
                    "operation": lease.node_id,
                    "arguments": {
                        "lease_id": lease.lease_id,
                        "token": lease.fencing_token,
                        "graph_id": lease.graph_id,
                        "graph_version": graph.version,
                        "revision": self.revision,
                    },
                },
            )
            for agent in self.agents.values():
                await agent.wait_until_idle()
            snapshot = await self.kernel.snapshot()
            artifact = snapshot.fact(f"release.result.{lease.lease_id}")
            if artifact:
                await self.coordinator.complete(
                    lease.lease_id,
                    fencing_token=lease.fencing_token,
                    artifact_refs=(str(artifact),),
                    verification_passed=True if lease.node_id == "verify" else None,
                )
                if lease.node_id == "package":
                    with zipfile.ZipFile(str(artifact)) as archive:
                        input_bytes = archive.read("prepared.json")
                        prepared = json.loads(input_bytes)
                        verification = json.loads(archive.read("verification.json"))
                        manifest = json.loads(archive.read("manifest.json"))
                        package_hashes_valid = all(
                            hashlib.sha256(archive.read(name)).hexdigest() == digest
                            for name, digest in manifest["files"].items()
                        )
                    executor = self.coordinator.projection.worker_for_node(
                        lease.graph_id, "prepare"
                    )
                    verifier = self.coordinator.projection.worker_for_node(lease.graph_id, "verify")
                    passed = (
                        prepared["features"] == self.features
                        and prepared["revision"] == self.revision
                        and manifest["revision"] == self.revision
                        and manifest["graph_id"] == lease.graph_id
                        and manifest["graph_version"] == graph.version
                        and verification["executor"] == executor
                        and verification["verifier"] == verifier
                        and verifier != executor
                        and verification["revision"] == self.revision
                        and verification["passed"]
                        and package_hashes_valid
                        and all(test["passed"] for test in verification["tests"])
                        and verification["input_sha256"] == hashlib.sha256(input_bytes).hexdigest()
                    )
                    await self.emit(
                        "reference.package_readback",
                        {
                            "passed": passed,
                            "path": artifact,
                            "revision": manifest["revision"],
                            "sha256": hashlib.sha256(
                                await asyncio.to_thread(Path(str(artifact)).read_bytes)
                            ).hexdigest(),
                        },
                    )
                    if passed:
                        await self.emit(
                            "commitment.updated",
                            {
                                "id": "release-commitment",
                                "status": "closed",
                                "closure_reason": "fulfilled",
                            },
                        )

    async def command(self, command):
        op = command["op"]
        if op == "plan":
            await self.coordinator.plan(self.order.work_order_id)
        elif op in {"step", "lease"}:
            await self.step(lease_only=op == "lease")
        elif op == "advance":
            self.now += timedelta(seconds=command["seconds"])
        elif op == "presence":
            await self.presence(
                command["worker"],
                PresenceStatus(command["status"]),
                seconds=command.get("seconds", 3600),
                observation_id=command.get("observation_id"),
            )
        elif op == "recover":
            self.coordinator = self.make_coordinator()
            await self.coordinator.recover_expired(at=self.now)
        elif op == "stale_dispatch":
            lease = self.old_lease
            graph = self.coordinator.projection.graph(lease.graph_id)
            await self.emit(
                "external.release_work",
                {
                    "worker": lease.agent_id,
                    "operation": lease.node_id,
                    "arguments": {
                        "lease_id": lease.lease_id,
                        "token": lease.fencing_token,
                        "graph_id": lease.graph_id,
                        "graph_version": graph.version,
                        "revision": self.revision,
                    },
                },
            )
            for agent in self.agents.values():
                await agent.wait_until_idle()
        elif op == "stale_complete":
            try:
                await self.coordinator.complete(
                    self.old_lease.lease_id,
                    fencing_token=self.old_lease.fencing_token,
                    artifact_refs=("stale-output",),
                )
            except ValueError as error:
                self.stale_rejections += 1
                await self.emit(
                    "reference.stale_completion_rejected",
                    {
                        "reason": str(error),
                        "lease_id": self.old_lease.lease_id,
                        "token": self.old_lease.fencing_token,
                    },
                )
        elif op == "constraint":
            self.revision = command["revision"]
            self.features = command["features"]
            self.factor = str(command.get("factor", self.factor))
            if not Decimal(self.factor).is_finite():
                raise ValueError("factor must be finite")
            self.source_csv = command.get("source_csv", self.source_csv)
            await self.emit("fact.observed", {"key": "release.revision", "value": self.revision})
            await self.emit(
                "fact.observed",
                {
                    "key": "release.requirements",
                    "value": {
                        "features": self.features,
                        "factor": self.factor,
                        "source_sha256": hashlib.sha256(self.source_csv.encode()).hexdigest(),
                    },
                },
            )
            trigger = await self.emit(
                "situation.release_constraints_changed",
                {
                    "revision": self.revision,
                    "features": self.features,
                    "factor": self.factor,
                    "source_sha256": hashlib.sha256(self.source_csv.encode()).hexdigest(),
                },
            )
            await self.coordinator.invalidate_for(
                trigger, reason="declared release constraint changed"
            )
        elif op == "freshness":
            self.freshness = command["value"]
            await self.emit("reference.source_coverage", {"freshness": self.freshness})
        elif op == "permission":
            await self.emit(
                "fact.observed", {"key": "release.effect_allowed", "value": command["allowed"]}
            )
        else:
            raise ValueError(f"unsupported stimulus: {op}")

    async def finish(self):
        for agent in self.agents.values():
            await agent.stop()
        history = await self.kernel.history()
        replay = WorkProjection()
        replay.rebuild(history)
        snapshot = await self.kernel.snapshot()
        result = {
            "agent": "Release Steward",
            "controller": "deterministic FakePlanner + SDK work frontier",
            "scope": "local synthetic package; no deployment or endogenous cognition",
            "manifest": {
                "reference_source_sha256": hashlib.sha256(
                    await asyncio.to_thread(Path(__file__).read_bytes)
                ).hexdigest(),
                "work_models_sha256": hashlib.sha256(
                    await asyncio.to_thread(
                        lambda: (
                            Path(__file__).resolve().parents[2] / "src/noema/work/models.py"
                        ).read_bytes()
                    )
                ).hexdigest(),
                "clock": "synthetic logical clock",
                "planner": "FakePlanner deterministic",
                "competence": "SEEDED, not learned",
                "effects": "isolated local files only",
                "restart": "coordinator reconstructed from canonical history, not process crash",
            },
            "artifact_root": str(self.root),
            "revision": self.revision,
            "features": self.features,
            "factor": self.factor,
            "source_csv": self.source_csv,
            "status": snapshot.commitments["release-commitment"].status.value,
            "effects": self.effects,
            "stale_rejections": self.stale_rejections,
            "graphs": [g.to_dict() for g in replay.graphs],
            "events": [event.to_dict() for event in history],
            "replay_equal": replay.completions == self.coordinator.projection.completions,
        }
        await self.kernel.stop()
        return result


async def run_scenario(scenario, output_root=None):
    root = Path(output_root) if output_root else Path(tempfile.mkdtemp(prefix="noema-release-"))
    if root.exists() and any(root.iterdir()):
        raise ValueError("reference output directory must be empty to preserve prior evidence")
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
    app = ReleaseSteward(
        root,
        independent_verifier=scenario.get("independent_verifier", True),
        factor=scenario.get("factor", "1"),
        source_csv=scenario.get("source_csv", "id,amount\n a ,1.25\nb,-2.00\n"),
    )
    try:
        await app.start()
        for command in scenario["commands"]:
            await app.command(command)
        result = await app.finish()
    except Exception as error:
        history = await app.kernel.history() if app.kernel.started else []
        await asyncio.to_thread(
            (root / "failure.json").write_text,
            json.dumps(
                {
                    "scenario": scenario,
                    "error": repr(error),
                    "effects": app.effects,
                    "events": [event.to_dict() for event in history],
                },
                indent=2,
            ),
        )
        for agent in app.agents.values():
            await agent.stop()
        if app.kernel.started:
            await app.kernel.stop()
        raise
    result["scenario"] = scenario["name"]
    return result


def public_scenarios():
    plan, step = {"op": "plan"}, {"op": "step"}
    return [
        {"name": "R1_nominal", "commands": [plan, step, step, step]},
        {
            "name": "R2_fenced_recovery",
            "commands": [
                plan,
                {"op": "lease"},
                {"op": "presence", "worker": "builder", "status": "offline"},
                {"op": "advance", "seconds": 61},
                {"op": "recover"},
                {"op": "stale_complete"},
                {"op": "stale_dispatch"},
                step,
                step,
                step,
            ],
        },
        {
            "name": "R3_constraint_replan",
            "commands": [
                plan,
                step,
                {
                    "op": "constraint",
                    "revision": 2,
                    "features": ["scaled values", "verified package"],
                    "factor": "2",
                },
                step,
                plan,
                step,
                step,
                step,
            ],
        },
        {
            "name": "R4_freshness_gate",
            "commands": [
                plan,
                step,
                {"op": "presence", "worker": "reviewer", "status": "available", "seconds": 5},
                {"op": "advance", "seconds": 6},
                step,
                {"op": "presence", "worker": "reviewer", "status": "available"},
                step,
                {"op": "freshness", "value": 0.2},
                step,
                {"op": "freshness", "value": 1.0},
                step,
            ],
        },
        {
            "name": "R5_no_independent_verifier",
            "independent_verifier": False,
            "commands": [plan, step, step, step],
        },
    ]


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--artifacts", type=Path, help="optional new directory holding physical outputs by scenario"
    )
    args = parser.parse_args()
    results = []
    for scenario in public_scenarios():
        result = await run_scenario(
            scenario, output_root=args.artifacts / scenario["name"] if args.artifacts else None
        )
        results.append(result)
        args.output.write_text(json.dumps(results, indent=2) + "\n")
        print(result["scenario"], result["status"], len(result["effects"]), result["replay_equal"])


if __name__ == "__main__":
    asyncio.run(main())
