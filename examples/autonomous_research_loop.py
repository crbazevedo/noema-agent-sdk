"""Three autonomous agents coordinate a falsifiable research loop via events."""

from __future__ import annotations

import asyncio

from noema import (
    ActionIntent,
    AutonomousAgent,
    AutonomousAgentConfig,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    CognitiveController,
    Event,
    NoemaKernel,
    NoemaSystem,
    PolicyEngine,
    RuleBasedReasoner,
)


def make_agent(agent_id, kernel, registry, rule):
    return AutonomousAgent(
        config=AutonomousAgentConfig(agent_id=agent_id),
        kernel=kernel,
        controller=CognitiveController(RuleBasedReasoner([rule])),
        capabilities=registry,
        policy=PolicyEngine(),
    )


async def main() -> None:
    kernel = NoemaKernel()
    conclusions: list[str] = []

    explorer_capabilities = CapabilityRegistry()

    async def formulate(arguments, context):
        question = str(arguments["question"])
        hypothesis = "Explicit opportunity cost reduces unnecessary agent branches"
        return CapabilityResult.ok(
            {"question": question, "hypothesis": hypothesis},
            facts={"research.hypothesis": hypothesis},
        )

    explorer_capabilities.register_function(
        CapabilitySpec("formulate_hypothesis", "Formulate a falsifiable hypothesis"),
        formulate,
    )

    def explorer_rule(request):
        if request.trigger.type != "external.research_question":
            return None
        return ActionIntent(
            "formulate_hypothesis",
            {"question": request.trigger.payload["question"]},
            rationale="convert the question into a testable claim",
            expected_value=8,
            information_value=7,
            attention_cost=2,
            confidence=0.8,
            falsifiers=("branch count does not decrease under matched task quality",),
        )

    critic_capabilities = CapabilityRegistry()

    async def run_probe(arguments, context):
        hypothesis = str(arguments["hypothesis"])
        # Deterministic toy result: a real adapter would execute a benchmark.
        control_branches = 12
        treatment_branches = 5
        supported = treatment_branches < control_branches
        return CapabilityResult.ok(
            {
                "supported": supported,
                "control_branches": control_branches,
                "treatment_branches": treatment_branches,
            },
            facts={
                "research.evidence": {
                    "hypothesis": hypothesis,
                    "supported": supported,
                    "control_branches": control_branches,
                    "treatment_branches": treatment_branches,
                }
            },
        )

    critic_capabilities.register_function(
        CapabilitySpec("run_branching_probe", "Run a matched branching experiment"),
        run_probe,
    )

    def critic_rule(request):
        if (
            request.trigger.type == "fact.observed"
            and request.trigger.payload.get("key") == "research.hypothesis"
        ):
            return ActionIntent(
                "run_branching_probe",
                {"hypothesis": request.trigger.payload["value"]},
                rationale="seek evidence capable of falsifying the claim",
                expected_value=10,
                information_value=10,
                attention_cost=3,
                confidence=0.9,
                alternatives=("simulation", "historical trace analysis"),
                falsifiers=("treatment branch count is not lower than control",),
            )
        return None

    synthesizer_capabilities = CapabilityRegistry()

    async def synthesize(arguments, context):
        evidence = dict(arguments["evidence"])
        conclusion = (
            "Provisionally supported"
            if evidence["supported"]
            else "Not supported"
        )
        conclusions.append(conclusion)
        return CapabilityResult.ok({"conclusion": conclusion})

    synthesizer_capabilities.register_function(
        CapabilitySpec("synthesize_result", "Synthesize evidence conservatively"),
        synthesize,
    )

    def synthesizer_rule(request):
        if (
            request.trigger.type == "fact.observed"
            and request.trigger.payload.get("key") == "research.evidence"
        ):
            return ActionIntent(
                "synthesize_result",
                {"evidence": request.trigger.payload["value"]},
                rationale="update the conclusion from observed evidence",
                expected_value=7,
                attention_cost=1,
                confidence=0.85,
            )
        return None

    system = NoemaSystem(
        kernel=kernel,
        agents=[
            make_agent("explorer", kernel, explorer_capabilities, explorer_rule),
            make_agent("critic", kernel, critic_capabilities, critic_rule),
            make_agent("synthesizer", kernel, synthesizer_capabilities, synthesizer_rule),
        ],
    )

    async with system:
        await system.emit(
            Event(
                "external.research_question",
                "researcher",
                {"question": "Does explicit opportunity cost improve agent efficiency?"},
            )
        )
        await system.wait_until_idle()
        print(conclusions[-1])
        print(f"Persisted events: {len(await kernel.history())}")


if __name__ == "__main__":
    asyncio.run(main())
