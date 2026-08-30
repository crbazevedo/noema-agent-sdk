from __future__ import annotations

import unittest

from noema import (
    ActionIntent,
    AutonomousAgent,
    AutonomousAgentConfig,
    CapabilityExistenceCritic,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    CognitiveController,
    Event,
    NoemaKernel,
    OpportunityCostCritic,
    PolicyEngine,
    RuleBasedReasoner,
)
from noema.testing import EventCollector, wait_for


class AutonomousAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_performs_multi_step_event_driven_recovery(self) -> None:
        kernel = NoemaKernel()
        registry = CapabilityRegistry()
        calls: list[str] = []

        async def inspect(arguments, context):
            calls.append("inspect")
            return CapabilityResult.ok(
                {"service": arguments["service"]},
                facts={f"service.{arguments['service']}.health": "degraded"},
            )

        async def restart(arguments, context):
            calls.append("restart")
            return CapabilityResult.ok(
                {"service": arguments["service"], "restarted": True},
                facts={f"service.{arguments['service']}.health": "healthy"},
            )

        registry.register_function(
            CapabilitySpec("inspect_service", "Inspect a service"), inspect
        )
        registry.register_function(
            CapabilitySpec("restart_service", "Restart a service"), restart
        )

        def rule(request):
            if request.trigger.type == "external.metric" and float(
                request.trigger.payload["error_rate"]
            ) > 0.2:
                return ActionIntent(
                    "inspect_service",
                    {"service": request.trigger.payload["service"]},
                    rationale="error rate is above threshold",
                    expected_value=10,
                    information_value=5,
                    attention_cost=1,
                    confidence=0.9,
                    idempotency_key=f"inspect:{request.trigger.id}",
                )
            if (
                request.trigger.type == "fact.observed"
                and request.trigger.payload.get("value") == "degraded"
            ):
                service = str(request.trigger.payload["key"]).split(".")[1]
                return ActionIntent(
                    "restart_service",
                    {"service": service},
                    rationale="inspection confirmed degradation",
                    expected_value=20,
                    risk_reduction=10,
                    attention_cost=2,
                    confidence=0.95,
                    idempotency_key=f"restart:{service}:{request.trigger.id}",
                )
            return None

        controller = CognitiveController(
            RuleBasedReasoner([rule]),
            critics=[CapabilityExistenceCritic(), OpportunityCostCritic()],
        )
        agent = AutonomousAgent(
            config=AutonomousAgentConfig(agent_id="reliability-agent"),
            kernel=kernel,
            controller=controller,
            capabilities=registry,
            policy=PolicyEngine(),
        )
        await kernel.start()
        collector = await EventCollector(kernel).start()
        await agent.start()
        await kernel.emit(
            Event(
                "external.metric",
                "monitor",
                {"service": "api", "error_rate": 0.35},
                priority=10,
            )
        )
        await wait_for(lambda: calls == ["inspect", "restart"], timeout=2)
        await agent.wait_until_idle(timeout=2)
        snapshot = await kernel.snapshot()
        self.assertEqual(snapshot.fact("service.api.health"), "healthy")
        self.assertEqual(len(collector.of_type("action.succeeded")), 2)
        await agent.stop()
        await collector.stop()
        await kernel.stop()
