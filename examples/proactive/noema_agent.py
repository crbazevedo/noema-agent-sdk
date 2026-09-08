"""One SDK-native agent reused by all three lessons; no new SDK facade."""

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
    SQLiteEventStore,
)

from .domain import Proposal, admissible, initial_world, observe, proposals


class NoemaLesson:
    def __init__(self, level, tools, database=None):
        self.level, self.tools = level, tools
        self.kernel = NoemaKernel(store=SQLiteEventStore(database)) if database else NoemaKernel()
        registry = CapabilityRegistry()

        def execute(arguments, context):
            proposal = Proposal(**arguments)
            world = context.situation.fact("world")
            updated = tools.invoke(proposal, world)
            return CapabilityResult.ok({"tool": proposal.tool}, facts={"world": updated})

        for name in ("read_note", "prepare_brief", "notify"):
            registry.register_function(CapabilitySpec(name, name.replace("_", " ")), execute)

        def reason(request):
            world = request.situation.fact("world")
            if world is None:
                return []
            return [
                ActionIntent(
                    candidate.tool,
                    candidate.payload(),
                    rationale=candidate.reason,
                    expected_value=candidate.value,
                    confidence=1.0,
                    attention_cost=1,
                    idempotency_key=candidate.key
                    if candidate.tool != "read_note"
                    else f"{candidate.key}:t{world['now']}",
                    falsifiers=("The meeting is cancelled, rescheduled or no longer useful",),
                )
                for candidate in proposals(world)
            ]

        def deny_stale(intent, capability, situation):
            return (
                None
                if admissible(Proposal(**intent.arguments), situation.fact("world"))
                else "The meeting or standing instruction is no longer current"
            )

        agent = AutonomousAgent(
            config=AutonomousAgentConfig(
                agent_id="meeting-preparation",
                trigger_patterns=("fact.observed",),
                workers=1,
                max_concurrent_actions=1,
                max_actions_per_cycle=1,
                attention_budget_per_cycle=1,
            ),
            kernel=self.kernel,
            capabilities=registry,
            controller=CognitiveController(RuleBasedReasoner([reason])),
            policy=PolicyEngine(rules=(deny_stale,)),
        )
        self.system = NoemaSystem(kernel=self.kernel, agents=[agent])

    async def start(self):
        await self.system.start()
        if (await self.kernel.snapshot()).fact("world") is None:
            await self._publish(initial_world(self.level))
        return self

    async def _publish(self, world):
        await self.system.emit(
            Event(
                "fact.observed",
                "synthetic-source",
                {"key": "world", "value": world},
            )
        )
        await self.system.wait_until_idle()

    async def tick(self, **update):
        await self._publish(observe(await self.world(), **update))
        return await self.world()

    async def world(self):
        return (await self.kernel.snapshot()).fact("world")

    async def trace(self):
        return [event.to_dict() for event in await self.kernel.history()]

    async def close(self):
        await self.system.stop()
