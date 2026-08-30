"""A complete autonomous, multi-step, event-driven recovery episode."""

from __future__ import annotations

import asyncio

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
    NoemaSystem,
    OpportunityCostCritic,
    PolicyEngine,
    RuleBasedReasoner,
    deployment_from_env,
)


async def main() -> None:
    deployment = await deployment_from_env()
    kernel = deployment.kernel
    capabilities = CapabilityRegistry()
    simulated_services = {"api": "degraded"}

    async def inspect_service(arguments, context):
        service = str(arguments["service"])
        health = simulated_services[service]
        await asyncio.sleep(0.02)
        return CapabilityResult.ok(
            {"service": service, "health": health},
            facts={f"service.{service}.health": health},
        )

    async def restart_service(arguments, context):
        service = str(arguments["service"])
        await asyncio.sleep(0.02)
        simulated_services[service] = "healthy"
        return CapabilityResult.ok(
            {"service": service, "restarted": True},
            facts={f"service.{service}.health": "healthy"},
        )

    capabilities.register_function(
        CapabilitySpec(
            "inspect_service",
            "Inspect current service health",
            idempotent=True,
        ),
        inspect_service,
    )
    capabilities.register_function(
        CapabilitySpec(
            "restart_service",
            "Restart a degraded service",
            idempotent=True,
        ),
        restart_service,
    )

    def reliability_policy(request):
        trigger = request.trigger
        if trigger.type == "external.metric" and float(trigger.payload["error_rate"]) > 0.2:
            service = str(trigger.payload["service"])
            return ActionIntent(
                "inspect_service",
                {"service": service},
                rationale="error rate crossed the investigation threshold",
                expected_value=8,
                information_value=6,
                attention_cost=1,
                confidence=0.95,
                alternatives=("ignore as transient", "inspect logs manually"),
                falsifiers=("a fresh health observation reports healthy",),
                idempotency_key=f"inspect:{service}:{trigger.id}",
            )

        if trigger.type == "fact.observed" and trigger.payload.get("value") == "degraded":
            key = str(trigger.payload["key"])
            if key.startswith("service.") and key.endswith(".health"):
                service = key.split(".")[1]
                return ActionIntent(
                    "restart_service",
                    {"service": service},
                    rationale="direct inspection confirmed service degradation",
                    expected_value=20,
                    risk_reduction=12,
                    attention_cost=2,
                    confidence=0.98,
                    alternatives=("rollback", "page a human"),
                    falsifiers=("restart is known unsafe for the current deployment",),
                    idempotency_key=f"restart:{service}:{trigger.id}",
                )
        return None

    controller = CognitiveController(
        RuleBasedReasoner([reliability_policy]),
        critics=[CapabilityExistenceCritic(), OpportunityCostCritic()],
    )
    agent = AutonomousAgent(
        config=AutonomousAgentConfig(agent_id="reliability-agent"),
        kernel=kernel,
        controller=controller,
        capabilities=capabilities,
        policy=PolicyEngine(),
    )
    system = NoemaSystem(
        kernel=kernel,
        agents=[agent],
        services=deployment.services,
    )

    async with system:
        await system.emit(
            Event(
                type="external.metric",
                source="monitoring",
                subject="service:api",
                priority=10,
                payload={"service": "api", "error_rate": 0.35},
            )
        )
        await system.wait_until_idle()

        snapshot = await kernel.snapshot()
        history = await kernel.history()
        print(f"Final API health: {snapshot.fact('service.api.health')}")
        print("\nCausal event trace:")
        for event in history:
            print(
                f"{event.sequence:02d}  {event.type:22s} "
                f"source={event.source:18s} cause={event.causation_id or '-'}"
            )


if __name__ == "__main__":
    asyncio.run(main())
