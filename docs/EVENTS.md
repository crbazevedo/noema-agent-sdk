# Event semantics

## Envelope

Every event includes:

- `id`: globally unique event identity;
- `type`: hierarchical topic;
- `source`: actor or system producing it;
- `subject`: optional affected entity;
- `timestamp`: timezone-aware UTC time;
- `sequence`: durable store order;
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
decision.denied
decision.deferred
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

Events are persisted before publication. The local bus provides at-least-once-compatible semantics; consumers should use event IDs and action idempotency keys when external effects require deduplication.

Distributed exactly-once effects require an outbox/inbox adapter and capability-side idempotency. Those are deliberately not faked by the in-process core.
