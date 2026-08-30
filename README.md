# Noema Agent SDK

**Async, event-sourced, situation-aware infrastructure for fully autonomous agent systems.**

Noema is not a persona framework and does not encode one preferred cognitive style. It provides general primitives from which sophisticated agent instances can be composed:

- durable events rather than chat turns;
- a queryable situation graph rather than one oversized prompt;
- replaceable reasoning and metacontrol;
- typed executable capabilities;
- finite attention and portfolio-level opportunity cost;
- policy-bounded but human-independent autonomy;
- event-driven scheduling, sensing, action, recovery, and reflection;
- multi-agent operation over a shared world model.

The core package has **no runtime dependencies outside Python 3.11+**.

## What is implemented

```text
environment / agents / timers
             │
             ▼
       append-only events
             │
      ┌──────┴──────┐
      ▼             ▼
 event store    async event bus
      │             │
      ▼             ├───────────────┐
 situation graph    ▼               ▼
      │         detectors      autonomous agents
      │             │               │
      └─────────────┴──────┬────────┘
                           ▼
                 deliberation + critics
                           │
                 attention allocation
                           │
                    policy/authority
                           │
                  capability execution
                           │
                 observations + events
                           └───────► loop
```

### Runtime properties

- **Asynchronous:** event delivery, reasoning, scheduling, capability calls, persistence, and multi-agent execution use `asyncio` contracts.
- **Situation-aware:** facts, entities, relations, goals, commitments, risks, opportunities, and resources are continuously projected from events.
- **Event-driven:** agents respond to material events and may emit new events that trigger other agents or later phases of their own policy.
- **Autonomous:** after startup, agents can sense, deliberate, prioritize, authorize, act, retry, compensate, reflect, and self-trigger without another human prompt.
- **Durable:** SQLite can reconstruct the exact situation and causal trace after restart.
- **Provider-agnostic:** `Reasoner` can be deterministic, LLM-backed, search-based, learned, symbolic, or an ensemble.
- **Governed:** autonomy is explicit and configurable; “fully autonomous” means no mandatory human interaction, not invisible or unlimited authority.

## Install locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The core runs without optional dependencies. Development tools are available through:

```bash
pip install -e '.[dev]'
```

## Run the autonomous example

```bash
make demo
```

The example receives one external service metric. From there the agent autonomously:

1. interprets the event in the current situation;
2. proposes an inspection;
3. passes the proposal through critics and policy;
4. executes the capability;
5. projects the resulting degraded-health fact;
6. treats that fact as a new situation event;
7. decides to restart the service;
8. verifies the resulting healthy state.

## Minimal API

```python
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
    PolicyEngine,
    RuleBasedReasoner,
)


async def main() -> None:
    kernel = NoemaKernel()
    capabilities = CapabilityRegistry()

    async def notify(arguments, context):
        print(arguments["message"])
        return CapabilityResult.ok()

    capabilities.register_function(
        CapabilitySpec("notify", "Emit an operational notification"),
        notify,
    )

    def rule(request):
        if request.trigger.type != "external.alert":
            return None
        return ActionIntent(
            "notify",
            {"message": request.trigger.payload["message"]},
            expected_value=5,
            attention_cost=1,
            confidence=0.9,
        )

    agent = AutonomousAgent(
        config=AutonomousAgentConfig(agent_id="operator"),
        kernel=kernel,
        controller=CognitiveController(RuleBasedReasoner([rule])),
        capabilities=capabilities,
        policy=PolicyEngine(),
    )

    await agent.start()
    await kernel.emit(
        Event("external.alert", "monitor", {"message": "API latency is high"})
    )
    await agent.wait_until_idle()
    await agent.stop()
    await kernel.stop()


asyncio.run(main())
```

## Core abstractions

### `Event`

Immutable causal record with type, source, payload, subject, timestamp, sequence, correlation ID, and causation ID.

### `NoemaKernel`

Atomically coordinates the event store, situation projection, and event bus.

### `SituationSnapshot`

Read-only current world model containing facts, graph entities/relations, goals, commitments, risks, opportunities, and resources.

### `Reasoner` and `CognitiveController`

`Reasoner` proposes actions. `CognitiveController` makes the path inspectable and applies independent critics before policy authorization.

### `ActionIntent`

A proposal containing expected value, information value, risk reduction, attention cost, risk, reversibility, confidence, alternatives, falsifiers, and idempotency.

### `CapabilityRegistry`

Typed boundary between cognition and effects. Capabilities declare risk, reversibility, authority, timeout, retries, and idempotency.

### `PolicyEngine`

Determines whether an action may execute under the current autonomy profile and situation.

### `AttentionAllocator`

Selects a portfolio of actions under finite attention rather than evaluating every action in isolation.

### `TrustLedger`

Maintains evidence-weighted reliability estimates for dynamic delegation. Source credibility remains separate from proposition truth.

### `DetectorEngine`

Turns low-level observations and situation state into higher-level signals. The included deadline detector promotes weak temporal signals into explicit risk events.

### `NoemaSystem`

Runs multiple autonomous agents, detectors, scheduling, persistence, and a shared situation model.

## Cognitive modes are optional policies, not a fixed personality

Noema names several useful modes:

```text
observe, expand, structure, formalize, falsify,
operationalize, govern, reopen, restore
```

An agent may use all, some, none, or learned replacements. The SDK records modes so their marginal value can later be measured.

## Fully autonomous operation

For unrestricted human-independent execution, use a sovereign profile deliberately:

```python
from noema import AutonomyProfile, PolicyEngine

policy = PolicyEngine(AutonomyProfile.sovereign())
```

This still leaves every action visible, typed, causally linked, and subject to custom policy rules. Production deployments should grant the minimum authority consistent with the environment's risk model.

## Tests

```bash
make test
```

The test suite covers:

- ordered wildcard event delivery;
- subscriber failure isolation;
- in-memory and SQLite event persistence;
- situation graph projection;
- attention portfolio selection;
- dynamic trust/authority;
- autonomous scheduling;
- deadline signal detection;
- multi-step autonomous incident recovery.

## Next engineering layers

The current version is a functioning substrate. The next layers should be built on top rather than folded into the core prematurely:

1. durable distributed bus adapters;
2. model-provider adapters and structured-output reasoners;
3. distributed leases and exactly-once action execution;
4. long-term semantic/episodic memory;
5. learned metacontrol and adaptive attention;
6. capability discovery and agent-to-agent contracting;
7. sandboxed execution and secret isolation;
8. distributed situation projections;
9. experiment and replay harnesses;
10. production observability adapters.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/AUTONOMY.md`](docs/AUTONOMY.md), [`docs/EVENTS.md`](docs/EVENTS.md), and [`docs/ROADMAP.md`](docs/ROADMAP.md).
