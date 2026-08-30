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

## Async semantics

- Per-subscription FIFO delivery is guaranteed.
- Subscribers execute independently.
- One failing subscriber does not crash the bus.
- Agent workers consume a priority queue.
- Actions are concurrency-limited independently from deliberation workers.
- Capability timeouts and retries are explicit.
- Idempotency is opt-in through an action key.
- Scheduled events create autonomous internal stimuli.

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
| Telemetry | `TelemetrySink` |
| Projection | custom `SituationModel` projector |

## Non-goals of the core

The core does not choose:

- a model provider;
- a vector database;
- a prompt format;
- a particular personality;
- a fixed reasoning loop;
- a distributed broker;
- a cloud platform;
- a human-approval UI.

Those choices belong in adapters and deployments.
