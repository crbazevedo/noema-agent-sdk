# Architecture

## Design objective

Noema provides a general substrate for long-running autonomous systems. It intentionally separates:

- **world state** from model context;
- **cognition** from effectful capabilities;
- **action proposals** from authorization;
- **individual task value** from portfolio opportunity cost;
- **source reputation** from proposition truth;
- **autonomy** from opacity;
- **agent identity** from the cognitive policies it instantiates.

## Six planes

Noema's major responsibilities form six governed planes:

```text
PERCEPTION / SUBSTRATE       What is happening and what can be sensed?
            ↓
SITUATION / MEMORY           What is currently believed about reality?
            ↓
AUTONOMIC                   What can be regulated cheaply?
            ↓
AWARE / DELIBERATIVE        What actually deserves thought?
            ↓
GOVERNED EFFECT             What may be done?
            ↓
DEVELOPMENT / METACOGNITIVE How should competence improve over time?
```

These are responsibility and authority boundaries, not required deployment
processes. The Endogenous Drive Ecology crosses the autonomic, aware, and
development planes; it is not a seventh peer plane.

## Event-sourced kernel

The event log is canonical. Every event is persisted before it is projected or delivered.

```text
emit(event)
  1. append to store
  2. assign sequence
  3. project into situation
  4. publish to subscribers
```

This order gives deterministic replay and lets agents deliberate over a situation that already contains the triggering observation.

Every envelope carries a schema version. Deterministic upcasters adapt old
payloads at read/projection time without rewriting canonical history.

Durable consumers record progress through generic `ConsumerCheckpoint` events.
The checkpoint is written only after required derived observations. A restart
replays later canonical triggers, while deterministic output IDs make partial
prior attempts idempotent. Checkpoint projections expose event-stream lag; they
do not replace the event log with a second offset store.

## Persistent cognitive memory

The event log records occurrences; it is not itself a belief table. Persistent
memory derives three separate layers from it:

```text
event → evidence relation → semantic assertion → bitemporal belief query
```

`SemanticAssertion` versions are immutable. They carry explicit epistemic
provenance, source/derivation anchors, valid-world time, recorded-knowledge
time, freshness, confidence, and hypothesis/active status. `EvidenceLink` is
the sole graph describing how resolved evidence bears on a claim. Supersession
and validity closure are later events, never row updates. Conflicting visible
assertions remain present and make the projected belief uncertain.

The [memory architecture](PERSISTENT_COGNITIVE_MEMORY.md) uses the same generic
checkpoint contract as other durable consumers. Required deterministic derived
events precede checkpoint advancement. Local lexical and future FTS/vector
indexes are projections that can be removed and rebuilt; canonical assertions
and their evidence remain the source of truth. A same-process write failure
also rebuilds speculative state through the last durable checkpoint before
retry.

## Situated continuity

Memory reconstruction does not prove that a mutable world remained unchanged
while the process was inactive. The v0.4
[Situated Continuity](SITUATED_CONTINUITY.md) foundation therefore treats every
wake as an epistemic reconstruction:

```text
canonical replay → freshness decay → awareness gaps → budgeted refresh
                 → bitemporal reconciliation → orientation report
```

`AwakeEpoch` records the sleep interval, canonical cursors, and orientation
status. Provider-neutral `SourceState` values expose durable source cursor,
hazard, confidence, and observation cost. Per-wake `AwarenessDemand` values
carry governing goals, relevance, decision sensitivity, and required
freshness/confidence. `WakeReconciler` is a pure planner over current requirement
gaps; `FakeSource` is the only v0.4 observation adapter. The orientation barrier
is shadow-only and cannot reach models, authority, capabilities, or effects.

Delayed observations retain the existing event-envelope contract: the event
timestamp is when Noema observed the report, while `payload.occurred_at` is the
source-reported world time. Memory maps them to assertion knowledge time and
valid time. Late observations use valid-time neighbors rather than latest
recording time. Each wake rebuilds continuity and memory from one canonical
history cut, independently of external projector lag. Source states, wake
epochs, observations, assertions, and reports are canonical events; freshness,
coverage, plans, and barrier decisions are rebuildable projections. Runtime
latency is telemetry, not canonical report identity. See
[ADR 0006](adr/0006-situated-continuity-foundation.md).

## Durable work coordination

v0.5 adds the minimum durable control plane between goals and effects:

```text
Goal → WorkOrder → FakePlanner → PlanProposal → PlanValidator → WorkGraph
                                                      ↓
                               completions → ReadyFrontier → WorkerMatcher
                                                      ↓
                                                 WorkLease
```

These contracts are deliberately distinct. A goal is not a work order; a work
order is not a plan; a proposed plan is not an accepted graph; a work node is
not an `ActionIntent`. The planner receives capability types but no agent
identity, competence, load, credentials, or authority policy. It proposes
structure only. `PlanValidator` owns DAG legality and graph admission, while
dependency waves emerge from canonical completions.

Agent ecology is similarly separated. `CapabilityManifest` records declared
capability types. `AgentPresence` expires explicitly. `CompetenceEstimate`
records seeded or evidence-ready quality estimates, but only seeded estimates
are operational in v0.5. `AuthorityLevel` remains a separate governance ceiling
and is never inferred by `WorkerMatcher`. Independent verification is ordinary
work whose matcher excludes the worker recorded as completing its target.

`WorkLease` grants carry monotonically increasing fencing tokens. Grant,
completion, expiration, and plan invalidation are canonical events;
`WorkProjection` is rebuildable. Completion and expiration share a terminal
event identity per lease, preventing two terminal outcomes under event-ID
uniqueness. Completion legality uses the coordinator's acceptance time; worker
finish time is informational. Planning capability inputs replay through the
proposal's exact causal cut, and a declared change during planning rejects graph
admission. A later declared causal-state change invalidates the active graph
without erasing completed artifacts.

`ReadyFrontier` also evaluates source freshness/confidence prerequisites through
Situated Continuity coverage. This controls work readiness but does not
authorize effects: actual effects still require `ActionIntent`, policy, and a
typed capability. See [Durable Work Coordination](DURABLE_WORK_COORDINATION.md)
and [ADR 0007](adr/0007-durable-work-coordination.md).

## Portable durability

Noema has one semantic runtime with two deployment profiles:

```text
embedded                         distributed
SQLite event store               PostgreSQL event store
in-process event bus              transactional outbox → NATS JetStream
single runtime                    durable inbox → one or more runtimes
```

In distributed mode, committing an event and its outbox record is one database
transaction. The publisher and consumer use renewable leases with fencing
tokens. Delivery is intentionally at least once: event IDs deduplicate runtime
observations, while a stable idempotency key crosses the capability boundary
for external effects. A broker transports events; it is never canonical history.

The same application policy and capability code runs in either profile.
If concurrent publishers deliver store sequences out of order, the receiving
kernel rebuilds its situation projection from canonical database order before
notifying local subscribers about the late event. Broker history already
present at runtime startup is not treated as a new stimulus.

## Autonomic, endogenous, and deliberative regimes

Noema has implemented the effect-free foundation of a signal-first
[Autonomic Fabric](AUTONOMIC_FABRIC.md) beneath its deliberative agents. Cheap
semi-independent rule cells observe narrow event and situation slices, record
deterministic activations, and produce hypothetical expiring signals. A
continuous observational worker now runs those cells through the canonical
event substrate and persists would-have-signaled/woken/suppressed telemetry
without enacting the decision.

The fabric does not create a second effect path. A bounded reflex can propose an
`ActionIntent`, but critics, policy, authorization, idempotency, and typed
capabilities remain mandatory. Rules, rulesets, firings, signals, and fitness
are projections of canonical events. Learned policies are immutable typed data,
never arbitrary executable code.

The mid-term [Endogenous Drive Ecology](ENDOGENOUS_DRIVE_ECOLOGY.md) adds a
second, governed source of cognitive demand: questions, belief/goal maintenance,
calibration, preparedness, and bounded simulation generated when no external
event currently warrants thought. Exogenous signals and endogenous activities
compete for one finite aware workspace. Internal initiative remains subordinate
to constitutional, user, mission, and commitment goals and creates proposals
more readily than actions.

## Situation graph

The built-in projection supports:

- facts with confidence and expiry;
- entities and typed relations;
- goals and status;
- commitments, deadlines, terminality, attention cost, and social cost;
- risks with expected-loss structure;
- opportunities with expected value, uncertainty, expiry, and attention cost;
- named resources.

Applications can register custom projectors without modifying the kernel.

## Agent cycle

```text
material event
  → snapshot
  → deliberate
  → critique / falsify
  → score action portfolio
  → authorize
  → execute capability
  → observe result
  → emit facts/events
  → reflect
```

Each transition is persisted as an event.

On restart, an agent rebuilds successful idempotency keys and reconstructs
authorized actions that have no terminal outcome. Only idempotent capabilities
are retried automatically; non-idempotent actions are durably abandoned for
explicit reconciliation and a new authorization.

## Model boundary

Model providers implement a small, provider-neutral request/response contract.
A context assembler selects a bounded view from the situation model. Structured
model output is schema-validated into `ActionIntent` values, then goes through
the same critics, policy, authorization, and capability boundary as deterministic
reasoners. Models never receive capability credentials.

## Async semantics

- Per-subscription FIFO delivery is guaranteed.
- Subscribers execute independently.
- One failing subscriber does not crash the bus.
- Agent workers consume a priority queue.
- Actions are concurrency-limited independently from deliberation workers.
- Capability timeouts and retries are explicit.
- Idempotency is explicit through an action key supplied to the capability.
- Scheduled events create autonomous internal stimuli.
- Distributed delivery uses leases and fencing to reject stale acknowledgements.

## Multi-agent systems

Agents share a kernel and therefore a consistent event history and situation projection. They may use different:

- reasoners;
- critics;
- capabilities;
- authority ceilings;
- risk policies;
- attention policies;
- trigger filters.

Coordination occurs through events, not direct hidden calls.

## Extension points

| Concern | Interface |
|---|---|
| Reasoning | `Reasoner` |
| Independent review | `Critic` |
| Effects | `Capability` |
| Situation inference | `SituationDetector` |
| Authorization | `PolicyRule` / `PolicyEngine` |
| Persistence | `EventStore` |
| Distributed transport | `EventBroker` |
| Model inference | `ModelProvider` |
| Model context | `ContextAssembler` |
| Telemetry | `TelemetrySink` |
| Tracing | `Tracer` |
| Projection | custom `SituationModel` projector |
| Durable consumer progress | `ConsumerCheckpoint` / `ConsumerCheckpointProjection` |
| Observational autonomic runtime | `AutonomicShadowWorker` |
| Epistemic memory | `SemanticAssertion` / `EvidenceLink` / `MemoryProjection` |
| Decision-relevant retrieval | `MemoryRetriever` / disposable index adapters |
| Durable memory projection | `MemoryProjector` |
| Wake-time temporal semantics | `TemporalService` / `AwakeEpoch` |
| Selective source refresh | `SourceState` / `AwarenessDemand` / `WakeReconciler` / `RefreshRequest` |
| Situated orientation | `AwarenessCoverage` / `OrientationReport` / `OrientationBarrier` |
| Durable work identity and planning | `WorkOrder` / `PlanProposal` / `WorkGraph` / `PlanValidator` |
| Work readiness and assignment | `ReadyFrontier` / `WorkerMatcher` / `WorkLease` |
| Agent ecology | `AgentPresence` / `CapabilityManifest` / `CompetenceEstimate` |
| Endogenous cognition (planned) | durable `Inquiry` / `IntrinsicActivity` contracts |

## Non-goals of the core

The core does not choose:

- a model provider;
- a vector database;
- a prompt format;
- a particular personality;
- a fixed reasoning loop;
- a cloud platform;
- a human-approval UI.

Those choices belong in adapters and deployments.

See [Architecture principles](ARCHITECTURE_PRINCIPLES.md),
[ADR 0001](adr/0001-portable-durable-agent.md),
[ADR 0002](adr/0002-autonomic-fabric.md),
[ADR 0003](adr/0003-endogenous-drive-ecology.md),
[ADR 0004](adr/0004-durable-consumer-checkpoints.md),
[ADR 0005](adr/0005-persistent-cognitive-memory.md),
[ADR 0006](adr/0006-situated-continuity-foundation.md),
[ADR 0007](adr/0007-durable-work-coordination.md), and the
[engineering roadmap](ROADMAP.md).
