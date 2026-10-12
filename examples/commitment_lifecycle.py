"""Run an evidence-brief commitment through the real embedded Noema SDK.

Synthetic provider, deterministic application reasoning, real event-sourced runtime.
Run: PYTHONPATH=src:examples python examples/commitment_lifecycle.py --output results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from commitment_lifecycle_domain import (
    Scenario,
    World,
    choose_action,
    deny_action,
    evaluate,
    public_scenarios,
)

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

COMMITMENT_ID = "evidence-brief"


def observed(snapshot):
    return {key: fact.value for key, fact in snapshot.facts.items()}


def commitment_status(snapshot):
    return snapshot.commitments[COMMITMENT_ID].status.value


async def run_scenario(
    scenario: Scenario,
    *,
    policy_enabled: bool = True,
    replay_enabled: bool = True,
    artifact_dir: Path | None = None,
    domain_module=None,
) -> dict[str, Any]:
    world_class = domain_module.World if domain_module else World
    planner = domain_module.choose_action if domain_module else choose_action
    policy_rule = domain_module.deny_action if domain_module else deny_action
    evaluator = domain_module.evaluate if domain_module else evaluate
    world = world_class()
    wakes = 0
    restarts = 0
    decisions = 0
    before_effect: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="noema-lifecycle-") as temporary:
        database = Path(temporary) / "events.sqlite"

        async def open_runtime():
            kernel = NoemaKernel(store=SQLiteEventStore(database))
            await kernel.start(replay=replay_enabled)
            registry = CapabilityRegistry()

            for name in ("prepare_brief", "deliver_brief", "verify_receipt"):
                # Bind names in closures; trigger events remain genuine timer wakes.
                async def invoke(arguments, context, operation=name):
                    result = world.invoke(operation, dict(arguments))
                    if not result["success"]:
                        return CapabilityResult.fail(result["error"])
                    events = []
                    if result.get("close"):
                        events.append(
                            Event(
                                "commitment.updated",
                                "receipt-verifier",
                                {
                                    "id": COMMITMENT_ID,
                                    "status": "closed",
                                    "closure_reason": "fulfilled",
                                },
                            )
                        )
                    return CapabilityResult.ok(facts=result["facts"], events=events)

                registry.register_function(CapabilitySpec(name, name, idempotent=True), invoke)

            async def rule(request):
                nonlocal decisions, before_effect
                decisions += 1
                if COMMITMENT_ID not in request.situation.commitments:
                    return None
                selected = planner(
                    observed(request.situation), commitment_status(request.situation)
                )
                if selected is None:
                    return None
                name, arguments = selected
                if before_effect:
                    world.update(before_effect)
                    for key, value in before_effect.items():
                        await kernel.emit(
                            Event(
                                "fact.observed",
                                "concurrent-source",
                                {
                                    "key": key,
                                    "value": value,
                                },
                            )
                        )
                    before_effect = {}
                return ActionIntent(
                    name,
                    arguments,
                    expected_value=10,
                    confidence=1,
                    rationale="advance current evidence-backed commitment",
                    attention_cost=1,
                )

            def guard(intent, capability, snapshot):
                del capability
                if not policy_enabled:
                    return None
                return policy_rule(
                    intent.capability,
                    dict(intent.arguments),
                    observed(snapshot),
                    commitment_status(snapshot),
                )

            agent = AutonomousAgent(
                config=AutonomousAgentConfig(
                    agent_id="brief-steward", trigger_patterns=("timer.commitment_wake",)
                ),
                kernel=kernel,
                controller=CognitiveController(RuleBasedReasoner([rule])),
                capabilities=registry,
                policy=PolicyEngine(rules=(guard,)),
            )
            await agent.start()
            return kernel, agent, AsyncScheduler(kernel)

        kernel, agent, scheduler = await open_runtime()
        try:
            await kernel.emit(
                Event(
                    "commitment.created",
                    "owner",
                    {
                        "id": COMMITMENT_ID,
                        "description": "Deliver and verify a current evidence brief",
                        "owner": "brief-steward",
                        "status": "active",
                    },
                )
            )
            for key, value in world.facts.items():
                await kernel.emit(Event("fact.observed", "source", {"key": key, "value": value}))
            for command in scenario.commands:
                if command["op"] == "update":
                    world.update(command["facts"])
                    for key, value in command["facts"].items():
                        await kernel.emit(
                            Event(
                                "fact.observed",
                                "source",
                                {
                                    "key": key,
                                    "value": value,
                                },
                            )
                        )
                elif command["op"] == "wake":
                    wakes += 1
                    before_effect = dict(command.get("before_effect", {}))
                    handle = scheduler.at(
                        datetime.now(UTC),
                        lambda count=wakes: Event(
                            "timer.commitment_wake", "scheduler", {"wake": count}
                        ),
                    )
                    await handle.task
                    await agent.wait_until_idle()
                elif command["op"] == "restart":
                    restarts += 1
                    await scheduler.stop()
                    await agent.stop()
                    await kernel.stop()
                    world.dump(Path(temporary) / "provider.json")
                    world = world_class.load(Path(temporary) / "provider.json")
                    kernel, agent, scheduler = await open_runtime()
                else:
                    raise ValueError(f"unknown command: {command['op']}")
            snapshot = await kernel.snapshot()
            facts = observed(snapshot)
            status = (
                commitment_status(snapshot) if COMMITMENT_ID in snapshot.commitments else "missing"
            )
            history = await kernel.history()
            result = {
                "scenario": scenario.name,
                "system": "noema-sdk",
                "metrics": {
                    **evaluator(world, facts, status, scenario.expected_revision),
                    "wakes": wakes,
                    "restarts": restarts,
                    "decisions": decisions,
                    "policy_denials": sum(
                        e.type in {"decision.denied", "action.abandoned"} for e in history
                    ),
                    "persisted_events": len(history),
                },
                "facts": facts,
                "status": status,
                "ledger": world.ledger,
                "invocations": world.invocations,
                "events": [e.to_dict() for e in history],
            }
        except Exception as error:
            if artifact_dir is not None:
                await asyncio.to_thread(artifact_dir.mkdir, parents=True, exist_ok=True)
                partial = {
                    "scenario": scenario.name,
                    "error": repr(error),
                    "commands": scenario.commands,
                    "world": world.facts,
                    "ledger": world.ledger,
                    "invocations": world.invocations,
                    "events": [e.to_dict() for e in await kernel.history()],
                }
                (artifact_dir / f"{scenario.name}-failure.json").write_text(
                    json.dumps(partial, indent=2) + "\n"
                )
            raise
        finally:
            await scheduler.stop()
            await agent.stop()
            await kernel.stop()
        return result


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = []
    report = {
        "scope": "synthetic deterministic mechanics; no model or real-world effectiveness",
        "results": results,
    }
    for scenario in public_scenarios():
        result = await run_scenario(
            scenario, artifact_dir=args.output.parent if args.output else Path.cwd()
        )
        results.append(result)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            [{"scenario": result["scenario"], **result["metrics"]} for result in results], indent=2
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
