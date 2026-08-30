# Event semantics

## Envelope

Every event includes:

- `id`: globally unique event identity;
- `type`: hierarchical topic;
- `source`: actor or system producing it;
- `subject`: optional affected entity;
- `timestamp`: timezone-aware UTC time;
- `sequence`: durable store order;
- `schema_version`: positive version used by deterministic upcasters;
- `correlation_id`: shared transaction / episode;
- `causation_id`: immediate parent event;
- `priority`: delivery priority for agent queues;
- `payload`: event-specific JSON data;
- `metadata`: cross-cutting annotations.

## Built-in situation events

```text
fact.observed
fact.retracted
entity.upserted
entity.removed
relation.upserted
relation.removed
goal.created
goal.updated
commitment.created
commitment.updated
commitment.completed
commitment.failed
commitment.cancelled
risk.detected
risk.resolved
opportunity.detected
opportunity.closed
resource.updated
```

## Agent lifecycle events

```text
agent.started
agent.stopped
agent.cycle_failed
decision.proposed
decision.authorized
decision.reauthorized
decision.denied
decision.deferred
action.dispatched
action.started
action.succeeded
action.failed
action.skipped
action.compensated
action.compensation_failed
```

## Causal chain

A typical episode is reconstructable as:

```text
external.metric
  └─ decision.proposed
       └─ decision.authorized
            └─ action.started
                 └─ action.succeeded
                      └─ fact.observed
                           └─ next decision cycle
```

## Delivery and durability

Events are persisted before publication. The local bus provides
at-least-once-compatible semantics; consumers use event IDs and action
idempotency keys when external effects require deduplication.

In distributed mode the PostgreSQL transaction writes the event and outbox row
together. A leased publisher sends the event through the configured broker; a
durable inbox claims delivery before the kernel ingests it. Lease fencing
rejects stale completion after ownership changes.

This does not claim exactly-once effects. Network failure can occur after an
external system applies an effect and before Noema records success. A capability
that enables automatic retry must therefore honor the supplied business
idempotency key. Non-idempotent capabilities are never automatically retried.

## Schema evolution

`EventSchemaRegistry` registers one deterministic upcaster per adjacent schema
version. Normalization preserves event identity, ordering, correlation, and
causation. Stored events are immutable; evolution happens at the projection
boundary rather than through history rewrites.
