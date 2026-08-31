# Noema Agent SDK

**Local-first, event-sourced infrastructure for portable durable agents.**

Noema is not a persona framework and does not encode one preferred cognitive style. It provides general primitives from which sophisticated agent instances can be composed:

- durable events rather than chat turns;
- a queryable situation graph rather than one oversized prompt;
- replaceable reasoning and metacontrol;
- typed executable capabilities;
- finite attention and portfolio-level opportunity cost;
- policy-bounded but human-independent autonomy;
- event-driven scheduling, sensing, action, recovery, and reflection;
- multi-agent operation over a shared world model.

The [Autonomic Fabric](docs/AUTONOMIC_FABRIC.md) adds a signal-first control
plane beneath deliberation: accumulated experience can become cheap, typed,
replayable micro-policies, while novelty and uncertainty are promoted to the
aware workspace. Its first observational worker continuously evaluates the
canonical event stream with predicate, temporal, and scoring rules. Rulesets
are content-addressed, evaluation epochs are pinned to event-log sequence, and
hard inhibition is distinct from graded modulation. The worker durably records
what would have signaled, woken, or been suppressed, but cannot wake cognition
or invoke capabilities. A generic, event-sourced `ConsumerCheckpoint` makes
partially completed triggers replayable after a crash without duplicating their
deterministic shadow outputs. Active behavior remains governed by the same
event, policy, authority, and capability boundaries.

The [Persistent Cognitive Memory](docs/PERSISTENT_COGNITIVE_MEMORY.md) layer
reconstructs episodic history, evidence links, immutable semantic assertions,
bitemporal belief state, hypotheses, and preserved contradictions from the
same canonical log. Retrieval combines relevance with time, goals, evidence,
freshness, and conflict penalties. Lexical and future vector indexes remain
disposable accelerators rather than memory authority. Its projector reuses
`ConsumerCheckpoint` to close partial-write crash windows deterministically.

The [Situated Continuity](docs/SITUATED_CONTINUITY.md) foundation makes wake a
selective epistemic reconstruction rather than a prompt resume. It separates
durable source facts from per-wake awareness demands, derives current freshness,
and plans from decision-relevant freshness/confidence gaps under an observation
budget. A deterministic fake ecology rebuilds continuity and memory from one
canonical cut, inserts delayed observations by valid time, and produces
orientation reports without connectors, models, or effects. Its orientation
barrier is shadow-only.

[Durable Work Coordination](docs/DURABLE_WORK_COORDINATION.md) adds the minimum
v0.5 work control plane. `FakePlanner` proposes dependency structure;
`PlanValidator` admits a durable graph; `ReadyFrontier` derives legal work;
`WorkerMatcher` combines availability, declared capability, and seeded
competence evidence; and fenced leases recover after worker loss. Planning,
matching, and work ownership remain distinct from `ActionIntent`, authority,
and capability execution.

The [Endogenous Drive Ecology](docs/ENDOGENOUS_DRIVE_ECOLOGY.md) records the
accepted mid-term architecture for bounded inquiry, calibration, consolidation,
and intrinsic agenda formation. It is deliberately staged behind observational
evidence from the shadow worker; its schedulers, HabitForge, and SkillForge are
not part of the current runtime.

The embedded core has **no runtime dependencies outside Python 3.11+**.
PostgreSQL, NATS, OpenAI, and OpenTelemetry integrations are optional adapters.

## What is implemented

```text
environment / agents / timers
             │
             ▼
       versioned append-only events
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
- **Epistemic:** memory distinguishes events, evidence, beliefs, simulation,
  world-valid time, and knowledge time without overwriting contradictions.
- **Situated:** wake epochs assess mutable source freshness and reconstruct
  sufficient decision context before reasoning or consequential action.
- **Portable:** the same agent application runs embedded with SQLite or distributed with PostgreSQL, a transactional outbox/inbox, and NATS JetStream.
- **Provider-agnostic:** `Reasoner` can be deterministic, LLM-backed, search-based, learned, symbolic, or an ensemble; model SDKs remain adapters.
- **Recoverable:** durable action lifecycle events restore completed idempotency keys and unfinished authorized work after a crash.
- **Observable:** causal events remain canonical while provider-neutral spans can be exported through OpenTelemetry.
- **Governed:** autonomy is explicit and configurable; “fully autonomous” means no mandatory human interaction, not invisible or unlimited authority.
- **Cognitively sparse:** shadow rules cheaply test which observations should be suppressed, retained, or promoted before expensive deliberation is involved.

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

Install all runtime adapters with:

```bash
pip install -e '.[all]'
```

## Run the autonomous example

```bash
MODE=embedded NOEMA_SQLITE_PATH=:memory: make demo
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

The identical application can run through the distributed adapters:

```bash
cp .env.example .env
docker compose up -d --wait
set -a; source .env; set +a
python examples/autonomous_incident_agent.py
docker compose down
```

PostgreSQL is exposed on host port `55432` to avoid colliding with a common
local PostgreSQL installation. NATS uses `4222` and its monitor uses `8222`.

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

Events also carry a schema version. Registered deterministic upcasters evolve
payloads without rewriting history.

### `NoemaKernel`

Atomically coordinates the event store, situation projection, and event bus.

In distributed mode, event append and outbox enqueue are one PostgreSQL
transaction; durable inbox claims and fencing tokens govern broker delivery.

### `SituationSnapshot`

Read-only current world model containing facts, graph entities/relations, goals, commitments, risks, opportunities, and resources.

### `Reasoner` and `CognitiveController`

`Reasoner` proposes actions. `CognitiveController` makes the path inspectable and applies independent critics before policy authorization.

`StructuredModelReasoner` adds a provider-neutral context and structured-output
boundary. OpenAI Responses and OpenAI-compatible local endpoints are supplied
as optional adapters, with deterministic recording/replay fixtures for tests.

### `ActionIntent`

A proposal containing expected value, information value, risk reduction, attention cost, risk, reversibility, confidence, alternatives, falsifiers, and idempotency.

### `CapabilityRegistry`

Typed boundary between cognition and effects. Capabilities declare risk,
reversibility, authority, timeout, retries, and idempotency. Idempotency is
opt-in; unfinished non-idempotent work is never replayed after a crash.

### `PolicyEngine`

Determines whether an action may execute under the current autonomy profile and situation.

### `AttentionAllocator`

Selects a portfolio of actions under finite attention rather than evaluating every action in isolation.

### `TrustLedger`

Maintains evidence-weighted reliability estimates for dynamic delegation. Source credibility remains separate from proposition truth.

### `DetectorEngine`

Turns low-level observations and situation state into higher-level signals. The included deadline detector promotes weak temporal signals into explicit risk events.

### Autonomic Shadow Kernel

`AutonomicRule`, `RuleRegistry`, `RulesetSnapshot`, and `EvaluationEpoch` define
immutable, event-rebuildable policy snapshots. Ruleset identity is derived from
content; each epoch records the event-log cursor that bounds the rule versions
it may use. `RuleCell` evaluates only three typed rule families—predicate,
temporal, and scoring—and returns `RuleEvaluationTrace` records containing
hypothetical `Signal` values. `SalienceResolver` deterministically aggregates
those signals, applying explicit hard vetoes or confidence-weighted graded
modulation, into shadow `WAKE`, `REMEMBER`, `REFLEX_PROPOSAL`, `SUPPRESS`, or
`DEFER` decisions.

`AutonomicShadowWorker` runs that path continuously over the real event
substrate and persists its evaluations and decisions for retrospective analysis.
It advances its durable checkpoint only after required shadow observations are
stored, then replays from the prior checkpoint after interruption. It performs
no external effect and has no dependency on models, authority, agents, or
capabilities.

### `ConsumerCheckpoint`

A generic canonical processing watermark for durable event consumers. Its
projection exposes last completed sequence, observed event-log head, processing
lag, and optional epoch identity. Memory projections, telemetry reducers,
maintenance loops, and future learning workers can reuse the same contract.

### Persistent Cognitive Memory

`SemanticAssertion` records an immutable, evidence-bearing proposition with
explicit observed, inferred, reported, assumed, or simulated provenance.
`MemoryProjection` reconstructs held beliefs and hypotheses at independent
valid and knowledge times, preserves contradictory claims, and excludes known
stale state by default. `MemoryRetriever` ranks canonical assertions while its
`LexicalMemoryIndex` can be deleted without semantic-state loss.

Assertions carry minimum `source_refs`; `EvidenceLink` remains the authoritative
graph for how a resolved event or assertion supports, contradicts, refines,
supersedes, or derives a claim. Missing references, unknown namespaces, and
simulation-to-observation laundering fail closed.

`MemoryProjector` consumes canonical history continuously. Deterministic
supersession and contradiction events are durable before its generic checkpoint
advances, so restart repeats incomplete work without duplicate logical memory.
The worker also restores its last durable projection immediately after a live
processing failure, making same-process retry equivalent to restart recovery.

The acceptance scenarios cover deep-work suppression, expiring code-review
opportunities, stale delegation, and byte-equivalent replay:

```bash
PYTHONPATH=src python -m unittest tests.test_autonomic tests.test_shadow tests.test_memory tests.test_memory_worker -v
```

### Situated Continuity Foundation

`TemporalService`, `AwakeEpoch`, `SourceState`, `AwarenessDemand`,
`FreshnessModel`, `AwarenessCoverage`, and `WakeReconciler` form an effect-free
wake planner.
`SituatedContinuityWorker` rebuilds source state from canonical events, decays
freshness, requests only decision-relevant observations from deterministic
`FakeSource` adapters, updates semantic memory from the same canonical causal
cut, and emits an `OrientationReport` plus a generic durable checkpoint.

Delayed observations keep `Event.timestamp` as observation time and carry
source world time in `payload.occurred_at`; semantic assertions preserve the
distinction through `recorded_at` and `valid_from`. Late reports are inserted
between their valid-time neighbors. Runtime latency remains telemetry and does
not affect content-addressed report identity. `OrientationBarrier`
evaluates action-specific freshness/confidence prerequisites in shadow mode and
cannot authorize or execute an effect.

```bash
PYTHONPATH=src python -m unittest tests.test_continuity tests.test_continuity_worker -v
```

### Durable Work Coordination

`WorkOrder`, `PlanProposal`, `WorkGraph`, ecology facts, fenced `WorkLease`
transitions, completions, and invalidations are canonical events.
`WorkProjection` reconstructs them without a private work database.

The deterministic release acceptance proves dependency waves,
capability/competence-aware assignment, independent verification, lease-expiry
recovery, a stale orientation prerequisite, and causal plan invalidation without
a model, external connector, or effect.

```bash
PYTHONPATH=src python -m unittest tests.test_work tests.test_work_coordination -v
```

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
make check
```

The test suite covers:

- ordered wildcard event delivery;
- subscriber failure isolation;
- in-memory and SQLite event persistence;
- schema versioning and deterministic upcasting;
- transactional outbox retry, inbox deduplication, lease expiry, and fencing;
- structured model output validation and exact JSONL replay;
- action idempotency restoration and crash recovery;
- situation graph projection;
- attention portfolio selection;
- dynamic trust/authority;
- autonomous scheduling;
- deadline signal detection;
- bitemporal belief queries, contradiction preservation, and memory retrieval;
- memory-projector crash recovery without duplicate logical memories;
- selective wake reconciliation, delayed observations, unavailable sources,
  and shadow orientation prerequisites;
- validated work graphs, dependency frontiers, deterministic worker matching,
  fenced lease recovery, independent verification, and causal invalidation;
- multi-step autonomous incident recovery.

The CI acceptance suite also runs the incident application against real
PostgreSQL and NATS containers.

## Release sequence

v0.5 is the Durable Work Coordination milestone. The roadmap next layers richer
agent interoperability and endogenous agenda formation above the durable event,
governance, autonomic, memory, orientation, and work-control substrates.

See [Architecture](docs/ARCHITECTURE.md), [architecture principles](docs/ARCHITECTURE_PRINCIPLES.md),
[ADR 0001](docs/adr/0001-portable-durable-agent.md), [autonomy](docs/AUTONOMY.md),
[event semantics](docs/EVENTS.md), [roadmap](docs/ROADMAP.md), and
[Situated Continuity](docs/SITUATED_CONTINUITY.md), plus the
[Autonomic Fabric](docs/AUTONOMIC_FABRIC.md) and its
[architecture decision](docs/adr/0002-autonomic-fabric.md), and
[Persistent Cognitive Memory](docs/PERSISTENT_COGNITIVE_MEMORY.md) with
[ADR 0005](docs/adr/0005-persistent-cognitive-memory.md), and
[ADR 0006](docs/adr/0006-situated-continuity-foundation.md), and
[Durable Work Coordination](docs/DURABLE_WORK_COORDINATION.md) with
[ADR 0007](docs/adr/0007-durable-work-coordination.md).
