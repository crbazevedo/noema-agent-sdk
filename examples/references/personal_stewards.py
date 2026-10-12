"""Real embedded Noema agents for three synthetic human situations.

SQLite replay, autonomous scheduled actions, live policy reauthorization, local
artifacts and readback. Fixture clock is accelerated; no external effects or LLM.
Run: PYTHONPATH=src python examples/references/personal_stewards.py --output out.json
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from personal_stewards_domain import DOMAINS, initial_facts, public_scenarios

from noema import (
    ActionIntent,
    AsyncScheduler,
    AutonomousAgent,
    AutonomousAgentConfig,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    CognitiveController,
    Event,
    NoemaKernel,
    PolicyEngine,
    RuleBasedReasoner,
    SQLiteEventStore,
)
from noema.store import ConcurrentAppendError

STATE_KEY = "personal_steward"


class PersonalSteward:
    def __init__(self, domain, root):
        self.domain = DOMAINS[domain]
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.handle = None
        self.before_effect = {}
        self.state_lock = asyncio.Lock()

    async def state(self):
        snapshot = await self.kernel.snapshot()
        return copy.deepcopy(snapshot.facts[STATE_KEY].value)

    async def save(self, state, source="steward"):
        return await self.kernel.emit(
            Event("fact.observed", source, {"key": STATE_KEY, "value": state})
        )

    async def open(self):
        self.kernel = NoemaKernel(store=SQLiteEventStore(self.root / "events.sqlite"))
        await self.kernel.start()
        registry = CapabilityRegistry()
        for name in ("inquire", "prepare", "verify"):

            async def invoke(arguments, context, operation=name):
                return await self.execute(operation, dict(arguments))

            registry.register_function(CapabilitySpec(name, name, idempotent=True), invoke)

        async def choose(request):
            state = copy.deepcopy(request.situation.facts[STATE_KEY].value)
            assessment = self.domain.assess(state)
            if state["closed"]:
                return None
            if state["inquired_revision"] != state["revision"]:
                operation = "inquire"
            elif not assessment.ready:
                await self.kernel.emit(
                    Event(
                        "reference.abstained",
                        "domain-policy",
                        {
                            "reason": "Required evidence is stale, absent or conflicting",
                            "uncertain": assessment.uncertain,
                            "revision": state["revision"],
                        },
                    )
                )
                return None
            elif state["prepared_revision"] != state["revision"]:
                operation = "prepare"
            elif state["approved_revision"] == state["revision"]:
                operation = "verify"
            else:
                return None
            if self.before_effect:
                facts, self.before_effect = self.before_effect, {}
                await self.observe(facts, why="Concurrent evidence invalidated the selected action")
            return ActionIntent(
                operation,
                {"revision": state["revision"]},
                expected_value=10,
                confidence=1,
                attention_cost=1,
                rationale="Advance only the current local planning commitment",
            )

        def guard(intent, capability, snapshot):
            state = snapshot.facts[STATE_KEY].value
            if not state["allowed"]:
                return "Human revoked planning permission"
            if intent.arguments["revision"] != state["revision"]:
                return "Selected input revision is stale"
            if intent.capability != "inquire" and not self.domain.assess(state).ready:
                return "Current required evidence is missing or conflicted"
            if intent.capability == "verify" and state["approved_revision"] != state["revision"]:
                return "Current human decision is missing"
            return None

        self.agent = AutonomousAgent(
            config=AutonomousAgentConfig(
                agent_id=f"{self.domain.id}-steward", trigger_patterns=("timer.personal_wake",)
            ),
            kernel=self.kernel,
            controller=CognitiveController(RuleBasedReasoner([choose])),
            capabilities=registry,
            policy=PolicyEngine(rules=(guard,)),
        )
        await self.agent.start()
        self.scheduler = AsyncScheduler(self.kernel)

    async def start(self):
        await self.open()
        await self.save(
            {
                "sources": {},
                "now": 0,
                "revision": 0,
                "allowed": True,
                "inquired_revision": -1,
                "prepared_revision": -1,
                "approved_revision": -1,
                "closed": False,
                "artifact": None,
                "next_wake": 5,
                "why_now": "Initial human planning request",
            }
        )
        await self.kernel.emit(
            Event(
                "commitment.created",
                "synthetic-human",
                {
                    "id": self.domain.id,
                    "description": self.domain.goal,
                    "owner": f"{self.domain.id}-steward",
                    "status": "active",
                },
            )
        )
        await self.observe(initial_facts(self.domain.id), why="Initial synthetic evidence")
        await self.card("Initial situation")

    async def observe(self, facts, source="fixture", due=None, why="New source evidence", ttl=120):
        if type(ttl) is not int or not 0 <= ttl <= 10**6:
            raise ValueError("ttl must be a bounded nonnegative integer")
        if due is not None and (type(due) is not int or not 0 <= due <= 10**9):
            raise ValueError("due must be a bounded nonnegative integer")
        async with self.state_lock:
            await self._observe(facts, source, due, why, ttl)

    async def _observe(self, facts, source, due, why, ttl):
        state = await self.state()
        event = await self.kernel.emit(
            Event(
                "reference.source_observed",
                source,
                {
                    "facts": facts,
                    "observed_minute": state["now"],
                    "valid_until": state["now"] + ttl,
                    "synthetic": True,
                    "why": why,
                },
            )
        )
        for key, value in facts.items():
            state["sources"].setdefault(key, {})[source] = {
                "value": value,
                "event_id": event.id,
                "observed_at": state["now"],
                "valid_until": state["now"] + ttl,
            }
        if state["closed"]:
            await self.kernel.emit(
                Event(
                    "commitment.updated",
                    "evidence-revision",
                    {"id": self.domain.id, "status": "active"},
                )
            )
        state["revision"] += 1
        state["approved_revision"] = -1
        state["closed"] = False
        state["why_now"] = why
        if due is not None:
            state["next_wake"] = max(state["now"], due)
        await self.save(state, source)
        await self.reschedule(why)

    async def reschedule(self, reason):
        if self.handle:
            await self.scheduler.cancel(self.handle.id)
            await self.kernel.emit(
                Event(
                    "reference.wake_cancelled",
                    "scheduler",
                    {"schedule_id": self.handle.id, "reason": reason},
                )
            )
        state = await self.state()
        if state["closed"]:
            self.handle = None
            return
        # Logical due time is persisted; wall-time pacing is deliberately accelerated by wake().
        due = state["next_wake"]
        self.handle = self.scheduler.at(
            datetime.now(UTC) + timedelta(hours=1),
            lambda: Event("timer.personal_wake", "scheduler", {"due": due}),
        )
        await self.kernel.emit(
            Event(
                "reference.wake_scheduled",
                "scheduler",
                {
                    "schedule_id": self.handle.id,
                    "due_minute": due,
                    "reason": reason,
                    "clock": "synthetic-minutes; explicit accelerated delivery",
                },
            )
        )

    async def execute(self, operation, arguments):
        snapshot = await self.kernel.snapshot()
        original = copy.deepcopy(snapshot.facts[STATE_KEY].value)
        state = copy.deepcopy(original)
        if not state["allowed"] or state["revision"] != arguments["revision"]:
            return CapabilityResult.fail("Revoked or stale input at effect boundary")
        assessment = self.domain.assess(state)
        pending = []
        if operation == "inquire":
            event = Event(
                "reference.inquiry_observed",
                "synthetic-read-adapter",
                {
                    "facts": self.domain.inquiry,
                    "revision": state["revision"],
                    "purpose": "Prepare useful independent work during human silence",
                    "budget": "one bounded fixture read per revision",
                    "synthetic": True,
                },
            )
            pending.append(event)
            for key, value in self.domain.inquiry.items():
                state["sources"].setdefault(key, {})["inquiry-fixture"] = {
                    "value": value,
                    "event_id": event.id,
                    "observed_at": state["now"],
                    "valid_until": state["now"] + 120,
                }
            state["inquired_revision"] = state["revision"]
        elif operation == "prepare":
            if not assessment.ready:
                return CapabilityResult.fail("Cannot prepare from stale required evidence")
            content = (
                json.dumps(
                    {
                        "domain": self.domain.id,
                        "revision": state["revision"],
                        "scope": "Synthetic local planning only; no external execution",
                        "goal": self.domain.goal,
                        **asdict(assessment),
                    },
                    indent=2,
                )
                + "\n"
            )
            relative = f"{self.domain.id}-review-v{state['revision']}.json"
            await asyncio.to_thread((self.root / relative).write_text, content)
            digest = hashlib.sha256(content.encode()).hexdigest()
            event = Event(
                "reference.artifact_prepared",
                "local-preparer",
                {
                    "path": relative,
                    "sha256": digest,
                    "revision": state["revision"],
                    "evidence_ids": assessment.evidence_ids,
                    "content": content,
                },
            )
            pending.append(event)
            state["artifact"] = {
                "path": relative,
                "sha256": digest,
                "content": content,
                "event_id": event.id,
                "readback_event_id": None,
            }
            state["prepared_revision"] = state["revision"]
        else:
            if (
                not assessment.ready
                or state["approved_revision"] != state["revision"]
                or state["prepared_revision"] != state["revision"]
            ):
                return CapabilityResult.fail("Current preparation and human decision required")
            artifact = state["artifact"]
            path = self.root / artifact["path"]
            raw = await asyncio.to_thread(path.read_bytes)
            # A second read catches replacement during the first read; proof is point-in-time,
            # not a claim that a user-writable file can never change again.
            raw_again = await asyncio.to_thread(path.read_bytes)
            if raw != raw_again or hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
                return CapabilityResult.fail("Independent readback hash mismatch")
            parsed = json.loads(raw)
            if (
                parsed["revision"] != state["revision"]
                or parsed["evidence_ids"] != assessment.evidence_ids
            ):
                return CapabilityResult.fail("Readback no longer matches current evidence")
            event = Event(
                "reference.artifact_verified",
                "local-readback-verifier",
                {
                    "path": artifact["path"],
                    "sha256": artifact["sha256"],
                    "revision": state["revision"],
                    "prepared_event_id": artifact["event_id"],
                    "human_decision_event_id": state["human_decision_event_id"],
                    "scope": "Local review verified; external outcome unverified",
                },
            )
            pending.extend(
                [
                    event,
                    Event(
                        "commitment.updated",
                        "local-readback-verifier",
                        {"id": self.domain.id, "status": "closed", "closure_reason": "fulfilled"},
                    ),
                ]
            )
            state["artifact"]["readback_event_id"] = event.id
            state["closed"] = True
        # The SDK applies CapabilityResult facts after invoke returns. Never hand it a stale
        # whole-state snapshot. Compare-and-append at the actual canonical commit boundary,
        # then publish proof while the application's state mutation lock is held.
        async with self.state_lock:
            if await self.state() != original:
                return CapabilityResult.fail("Concurrent state change; discard stale result")
            # Persist candidate/readback evidence before any state can claim it exists.
            # A crash here leaves an open commitment, never a proof-less closure.
            for event in pending:
                if event.type != "commitment.updated":
                    await self.kernel.emit(event)
            current = await self.kernel.snapshot()
            if current.facts[STATE_KEY].value != original:
                return CapabilityResult.fail("State changed while publishing evidence")
            try:
                await self.kernel.emit_if_head(
                    Event(
                        "fact.observed", "steward-atomic-commit", {"key": STATE_KEY, "value": state}
                    ),
                    expected_head_sequence=current.version,
                )
            except ConcurrentAppendError:
                return CapabilityResult.fail("Canonical head changed; discard stale result")
            for event in pending:
                if event.type == "commitment.updated":
                    await self.kernel.emit(event)
        return CapabilityResult.ok()

    async def wake(self, before_effect=None):
        if self.handle:
            await self.scheduler.cancel(self.handle.id)
            self.handle = None
        async with self.state_lock:
            state = await self.state()
            state["now"] = max(state["now"], state["next_wake"])
            state["why_now"] = "Scheduled check without a new human message"
            await self.save(state)
        self.before_effect = before_effect or {}
        handle = self.scheduler.at(
            datetime.now(UTC),
            lambda: Event(
                "timer.personal_wake",
                "scheduler",
                {"due_minute": state["now"], "accelerated": True},
            ),
        )
        await handle.task
        await self.agent.wait_until_idle()
        async with self.state_lock:
            state = await self.state()
            state["next_wake"] = state["now"] + 5
            await self.save(state)
        await self.reschedule("Check remaining work after wake")

    async def card(self, changed):
        async with self.state_lock:
            await self._card(changed)

    async def _card(self, changed):
        state = await self.state()
        assessment = self.domain.assess(state)
        current_review = (
            state["allowed"]
            and assessment.ready
            and state["prepared_revision"] == state["revision"]
        )
        if not state["allowed"]:
            status = "permission-revoked"
        elif not assessment.ready:
            status = "needs-current-evidence"
        elif state["closed"]:
            status = "closed-local-review"
        elif state["prepared_revision"] == state["revision"]:
            status = "needs-human-decision"
        else:
            status = "preparing"
        projection = {
            "title": self.domain.title,
            "version": state["revision"],
            "status": status,
            "changed": changed,
            "why_now": state["why_now"],
            "known": assessment.known,
            "uncertain": assessment.uncertain,
            "recommendation": assessment.recommendation,
            "options": assessment.options,
            "evidence_ids": assessment.evidence_ids,
            "next_wake": None
            if state["closed"]
            else {"due_minute": state["next_wake"], "clock": "synthetic-minutes"},
            "human_decision": "simulated-acceptance-current-local-review"
            if (state["approved_revision"] == state["revision"] and current_review)
            else "pending",
            "closure": "Verified local brief only; no external action or outcome"
            if state["closed"]
            else None,
            "artifact": state["artifact"] if current_review else None,
        }
        await self.kernel.emit(Event("reference.card", "human-projection", projection))

    async def command(self, command):
        op = command["op"]
        if op == "wake":
            await self.wake(command.get("before_effect"))
        elif op == "observe":
            await self.observe(
                command["facts"],
                source=command.get("source", "fixture"),
                due=command.get("due"),
                why=command.get("why", "New source evidence"),
                ttl=command.get("ttl", 120),
            )
        elif op in {"approve", "revoke", "advance"}:
            async with self.state_lock:
                await self.control(command)
        elif op == "restart":
            await self.stop()
            await self.open()
            await self.kernel.emit(
                Event(
                    "reference.restarted",
                    "runtime",
                    {"state": "SQLite replay", "timer": "reconstructed from persisted logical due"},
                )
            )
            await self.reschedule("Restore persisted next wake after interruption")
        else:
            raise ValueError(f"Unknown command {op}")
        await self.card(command.get("why", op))

    async def control(self, command):
        op = command["op"]
        state = await self.state()
        if op == "approve":
            revision = command.get("revision", state["revision"])
            if (
                type(revision) is not int
                or revision != state["prepared_revision"]
                or revision != state["revision"]
                or not state["allowed"]
                or not self.domain.assess(state).ready
            ):
                await self.kernel.emit(
                    Event(
                        "reference.human_decision_rejected",
                        "synthetic-human",
                        {
                            "revision": revision,
                            "reason": "No current authorized, evidence-backed prepared brief",
                        },
                    )
                )
            else:
                event = await self.kernel.emit(
                    Event(
                        "reference.human_decision",
                        "synthetic-human",
                        {
                            "revision": revision,
                            "decision": "accept-local-review",
                            "external_authority": False,
                            "simulated": True,
                        },
                    )
                )
                state["approved_revision"] = revision
                state["human_decision_event_id"] = event.id
        elif op == "revoke":
            state["allowed"] = False
            state["approved_revision"] = -1
            await self.kernel.emit(Event("reference.permission_revoked", "synthetic-human"))
        else:
            minutes = command["minutes"]
            if type(minutes) is not int or not 0 <= minutes <= 10**6:
                raise ValueError("Clock advance must be a bounded nonnegative integer")
            state["now"] += minutes
        await self.save(state)

    async def stop(self):
        await self.scheduler.stop()
        self.handle = None
        await self.agent.stop()
        await self.kernel.stop()

    async def result(self, scenario):
        state = await self.state()
        events = await self.kernel.history()
        cards = [
            {**dict(e.payload), "event_id": e.id, "sequence": e.sequence}
            for e in events
            if e.type == "reference.card"
        ]
        projection = copy.deepcopy((await self.kernel.snapshot()).facts[STATE_KEY].value)
        await self.stop()
        replay = NoemaKernel(store=SQLiteEventStore(self.root / "events.sqlite"))
        await replay.start()
        recovered = (await replay.snapshot()).facts[STATE_KEY].value
        replay_equal = recovered == projection
        await replay.stop()
        return {
            "scenario": scenario,
            "domain": self.domain.id,
            "title": self.domain.title,
            "goal": self.domain.goal,
            "stakes": self.domain.stakes,
            "status": cards[-1]["status"],
            "cards": cards,
            "events": [e.to_dict() for e in events],
            "artifact": state["artifact"],
            "replay_equal": replay_equal,
            "metrics": {
                "persisted_events": len(events),
                "cards": len(cards),
                "inquiries": sum(e.type == "reference.inquiry_observed" for e in events),
                "preparations": sum(e.type == "reference.artifact_prepared" for e in events),
                "policy_denials": sum(
                    e.type in {"decision.denied", "action.abandoned"} for e in events
                ),
                "external_effects": 0,
                "model_calls": 0,
            },
        }


async def run_scenario(scenario, root=None):
    root = Path(root) if root else Path(tempfile.mkdtemp(prefix="noema-personal-"))
    app = PersonalSteward(scenario["domain"], root)
    await app.start()
    try:
        for command in scenario["commands"]:
            await app.command(command)
        return await app.result(scenario["name"])
    except BaseException:
        await app.stop()
        raise


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--domain", choices=tuple(DOMAINS))
    args = parser.parse_args()
    root = args.artifact_root or Path(tempfile.mkdtemp(prefix="noema-personal-portfolio-"))
    scenarios = [s for s in public_scenarios() if not args.domain or s["domain"] == args.domain]
    results = [await run_scenario(s, root / s["name"]) for s in scenarios]
    report = {
        "schema_version": 1,
        "scope": "synthetic deterministic Noema runtime; no model calls",
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            [{k: r[k] for k in ("scenario", "status", "replay_equal", "metrics")} for r in results],
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
