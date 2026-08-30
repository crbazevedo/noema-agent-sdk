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
[ADR 0001](adr/0001-portable-durable-agent.md), and the
[engineering roadmap](ROADMAP.md).
