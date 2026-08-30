# ADR 0002: Signal-first autonomic fabric

- Status: accepted
- Date: 2026-08-30
- Scope: v0.3–v0.6 cross-cutting track

## Context

Noema's durable event loop can wake a deliberative agent for every material
event. That is correct for an initial substrate but inefficient and cognitively
flat for an always-on personal agent. Routine perception, temporal monitoring,
salience, coordination, and homeostasis do not justify repeated foundation-model
calls. Repeatedly successful deliberation should be eligible to become cheaper
behavior, without creating an ungoverned second action path.

The central risk is dual control: if learned rules hold private state, execute
code, invoke capabilities, or mutate themselves outside the event and authority
systems, Noema can no longer reconstruct or govern its behavior.

## Decision

1. Add a signal-first Autonomic Fabric beneath deliberation. Rules emit typed
   signals by default; a bounded reflex may only propose an `ActionIntent`.
2. Keep the event store canonical. Registry, rulesets, cell state, signals,
   firings, fitness, and Forge datasets are rebuildable projections.
3. Store immutable, provenance-bearing rule versions. Pin a ruleset per fabric
   evaluation epoch; awake epochs reference it so activation is reproducible
   both while cognition sleeps and after it wakes.
4. Represent learned rules in sanctioned typed encodings. Generated or stored
   arbitrary executable code is forbidden.
5. Keep probabilistic evidence and scoring, but make evaluation and conflict
   resolution deterministic for identical pinned inputs.
6. Use semi-decentralized `RuleCell` workers for locality. Cells communicate
   only through events, cannot invoke capabilities, and share a governed agenda.
7. Resolve conflict through invariant levels, explicit precedence, inhibition,
   and utility—not execution order.
8. Preserve natural-language user intent as evidence and compile it first into
   an `IntentFrame`. A model proposes typed candidates; deterministic evidence,
   replay, impact, collision, and lifecycle gates decide advancement.
9. Make every firing and lifecycle transition observable. Meta-rules may
   propose throttling, quarantine, revision, or retirement but cannot silently
   mutate active policy.
10. Implement the fabric incrementally across v0.3–v0.6. Begin with effect-free
    shadow rules; defer automatic canary reflexes and RETE optimization until
    evidence and profiling justify them.

## Consequences

- Deliberative load, latency, and model cost can fall as demonstrated routines
  compile downward.
- Situated continuity gains a cheap attention membrane and continuous temporal
  monitoring without continuous rich sensing or inference.
- Personalization becomes testable and reversible, but calibration, drift, and
  privacy inference become first-class operational concerns.
- The event log grows with firing telemetry. Retention and derived metrics must
  prevent auditability from becoming unbounded hot-path storage.
- Pinning rulesets improves replay but delays ordinary rule changes until the
  next epoch. L0 emergency inhibition is the explicit exception.
- Semi-decentralized cells improve locality and failure isolation while making
  event partitioning and duplicate suppression sensitivity points.
- A small typed rule IR limits expressiveness initially. This is deliberate;
  new encodings require evidence rather than arbitrary-code escape hatches.

## Rejected alternatives

- **Call a model for every event:** too expensive, slow, and difficult to keep
  continuously available.
- **Let learned rules execute tools directly:** bypasses Noema's authority,
  idempotency, policy, and causal action trace.
- **Store generated Python:** expands the security and verification problem into
  arbitrary program synthesis.
- **One monolithic evaluator:** couples unrelated domains and local temporal
  state, weakening failure isolation and deployability.
- **Random runtime firing:** prevents exact replay and makes calibration harder
  to diagnose.
- **Full RETE immediately:** adds a large optimization framework before scale
  measurements establish a need.

## Fitness functions

- Architecture tests reject dynamic execution and adapter imports in future
  autonomic/Forge core modules.
- Rule-schema tests will reject unknown operations, undeclared dependencies,
  authority escalation, and mutable versions.
- Replay tests will compare firing semantics under a pinned ruleset.
- Shadow-mode tests will prove the absence of deliberative signals and effects.
- Agenda tests will permute evaluation order and require identical conflict
  resolution.
- Embedded/distributed acceptance will run the same personal-workflow cell.

This ADR extends [ADR 0001](0001-portable-durable-agent.md); it does not change
the canonical event, adapter, or capability-boundary decisions.
