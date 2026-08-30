from __future__ import annotations

import unittest

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
from noema.testing import wait_for


class MultiAgentSystemTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_startup_rolls_back_runtime_services(self) -> None:
        class FailingService:
            stopped = False

            async def start(self) -> None:
                raise RuntimeError("injected startup failure")

            async def stop(self) -> None:
                self.stopped = True

        kernel = NoemaKernel()
        service = FailingService()
        system = NoemaSystem(kernel=kernel, services=[service])
        with self.assertRaisesRegex(RuntimeError, "injected startup failure"):
            await system.start()
        self.assertTrue(service.stopped)
        self.assertFalse(kernel.started)

    async def test_agents_coordinate_through_shared_situation_events(self) -> None:
        kernel = NoemaKernel()
        calls: list[str] = []

        analysis_capabilities = CapabilityRegistry()

        async def analyze(arguments, context):
            calls.append("analyze")
            return CapabilityResult.ok(
                {"topic": arguments["topic"]},
                facts={"analysis.ready": str(arguments["topic"])},
            )

        analysis_capabilities.register_function(
            CapabilitySpec("analyze", "Analyze a topic"), analyze
        )

        def analysis_rule(request):
            if request.trigger.type != "external.research_requested":
                return None
            return ActionIntent(
                "analyze",
                {"topic": request.trigger.payload["topic"]},
                expected_value=5,
                attention_cost=1,
                confidence=0.9,
            )

        publication_capabilities = CapabilityRegistry()

        async def publish(arguments, context):
            calls.append("publish")
            return CapabilityResult.ok({"published": arguments["topic"]})

        publication_capabilities.register_function(
            CapabilitySpec("publish", "Publish completed analysis"), publish
        )

        def publication_rule(request):
            if (
                request.trigger.type == "fact.observed"
                and request.trigger.payload.get("key") == "analysis.ready"
            ):
                return ActionIntent(
                    "publish",
                    {"topic": request.trigger.payload["value"]},
                    expected_value=5,
                    attention_cost=1,
                    confidence=0.9,
                )
            return None

        analyst = AutonomousAgent(
            config=AutonomousAgentConfig(agent_id="analyst"),
            kernel=kernel,
            controller=CognitiveController(RuleBasedReasoner([analysis_rule])),
            capabilities=analysis_capabilities,
            policy=PolicyEngine(),
        )
        publisher = AutonomousAgent(
            config=AutonomousAgentConfig(agent_id="publisher"),
            kernel=kernel,
            controller=CognitiveController(RuleBasedReasoner([publication_rule])),
            capabilities=publication_capabilities,
            policy=PolicyEngine(),
        )
        system = NoemaSystem(kernel=kernel, agents=[analyst, publisher])
        async with system:
            await system.emit(
                Event(
                    "external.research_requested",
                    "user",
                    {"topic": "adaptive agency"},
                )
            )
            await wait_for(lambda: calls == ["analyze", "publish"], timeout=2)
            await system.wait_until_idle(timeout=2)
        self.assertEqual(calls, ["analyze", "publish"])
