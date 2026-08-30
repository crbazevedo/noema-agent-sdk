# ADR 0004: Durable event-consumer checkpoints

- Status: accepted
- Date: 2026-08-30
- Scope: all durable consumers of the canonical event log

## Context

A continuous consumer can crash after reading a canonical trigger but before
all derived observations are durable. Restarting from the event-store head
would silently omit that trigger from its corpus. A private watermark table
would recover progress but create a second source of truth and a separate
embedded/distributed consistency problem.

The immediate case is the autonomic shadow worker, but memory projections,
telemetry reducers, maintenance loops, agent-ecology projections, and future
HabitForge miners need the same primitive.

## Decision

1. Represent consumer progress as a canonical
   `runtime.consumer_checkpoint_advanced` event and rebuild it through a
   `ConsumerCheckpointProjection`.
2. Identify progress by a stable `consumer_id`, `last_completed_sequence`, the
   event-log head observed when processing began, and an optional epoch ID.
3. Write every required derived observation before advancing the checkpoint.
   On restart, replay canonical triggers after the last completed sequence.
4. Give derived outputs deterministic causal identities. If a crash leaves a
   prefix of the outputs durable without a checkpoint, replay reuses those
   outputs and completes the missing suffix before advancing.
5. Reject checkpoint regression in both the runtime and the rebuildable
   projection. The checkpoint event's own sequence remains distinct from the
   input sequence it declares complete.
6. Expose processing lag as both checkpoint state and provider-neutral
   telemetry. Measure full-history events replayed per trigger, situation
   rebuild time, rule evaluation time, salience resolution time, and shadow
   event write time before optimizing reconstruction.

## Consequences

- A checkpoint means all required shadow observations for its completed trigger
  were durable first.
- Outputs may be durable while a checkpoint is not; this is intentional
  at-least-once recovery state, resolved by deterministic replay.
- No checkpoint database, broker offset, or worker-local file becomes a second
  authority.
- The current correctness-first situation reconstruction remains approximately
  quadratic over a growing history. Telemetry determines when an incremental
  snapshot plus small-delta replay becomes justified.
- Multiple active writers for one consumer ID will eventually require leasing
  or compare-and-advance storage semantics. This milestone assumes one logical
  writer and makes checkpoint regression visible rather than silently accepting
  it.

## Rejected alternatives

- **Restart from the current event-store head:** loses triggers read immediately
  before a crash.
- **Private worker offset storage:** creates a second truth source and weakens
  local/distributed parity.
- **Require one transaction spanning the trigger and all derived events:**
  over-couples consumers to a particular event-store implementation and is not
  needed while deterministic idempotent replay closes partial-write windows.
- **Optimize the situation projection now:** changes the proof substrate before
  measurements show where the bottleneck lies.

## Fitness functions

- crash before trace persistence replays the trigger;
- crash after trace but before decision reuses the trace and writes the decision;
- crash after all outputs but before checkpoint produces no duplicate outputs;
- checkpoint projections reject unsequenced or regressing records;
- phase and processing-lag metrics are emitted for completed attempts.

This decision extends [ADR 0001](0001-portable-durable-agent.md) and hardens the
continuous worker introduced by [ADR 0002](0002-autonomic-fabric.md).
