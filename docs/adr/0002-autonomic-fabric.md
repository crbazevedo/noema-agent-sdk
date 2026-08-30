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
   firings, fitness, and HabitForge datasets are rebuildable projections.
3. Store immutable, provenance-bearing rule versions from sequenced canonical
   registration events. A ruleset is a content-addressed policy artifact. An
   evaluation epoch pins that artifact with a start time and event-log cursor;
   awake epochs reference it so activation is reproducible both while cognition
   sleeps and after it wakes.
4. Represent learned rules in sanctioned typed encodings. Generated or stored
   arbitrary executable code is forbidden.
5. Keep probabilistic evidence and scoring, but make evaluation and conflict
   resolution deterministic for identical pinned inputs.
6. Use semi-decentralized `RuleCell` workers for locality. Cells communicate
   only through events, cannot invoke capabilities, and share a governed agenda.
7. Resolve conflict through invariant levels, explicit precedence, hard
   inhibition, graded modulation, and utility—not execution order. Hard
   inhibition ignores probabilistic strength; modulation attenuates activation.
8. Preserve natural-language user intent as evidence and compile it first into
   an `IntentFrame`. A model proposes typed candidates; deterministic evidence,
   replay, impact, collision, and lifecycle gates decide advancement.
9. Make every firing and lifecycle transition observable. Meta-rules may
   propose throttling, quarantine, revision, or retirement but cannot silently
   mutate active policy.
10. Implement the fabric incrementally across v0.3–v0.6. Begin with effect-free
    shadow rules; defer automatic canary reflexes and RETE optimization until
    evidence and profiling justify them.
11. Keep `RuleCell` state rebuildable from canonical evidence. The live signal
    workspace is a disposable projection; durable evaluation traces and shadow
    decisions retain the evidence and hypothetical outcomes needed for replay
    and learning.
12. Permit immediate modulation only when it preserves or reduces authority.
    Any increase in authority requires an explicit governed lifecycle transition.
13. Keep HabitForge outside the autonomic execution boundary. It may
    propose immutable candidates, but it cannot mutate a pinned ruleset.
14. Make rule telemetry, deterministic replay, temporal evaluation, and
    salience resolution part of v0.3, before HabitForge learns from the resulting
    evidence in v0.5.
15. Run the fabric continuously through an outer observational worker. It may
    persist content artifacts, epochs, evaluation traces, and hypothetical
    decisions, but cannot import or call the effect plane.
16. Bind continuous processing to the general event-sourced
    `ConsumerCheckpoint`. Required shadow observations are written before the
    checkpoint advances; restart replays later triggers with deterministic IDs.

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
- Sequence-based eligibility prevents a registry rebuilt in the future from
  leaking later rule versions into a historical epoch. Content identity remains
  separate from temporal instantiation.
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
  autonomic/HabitForge core modules.
- Rule-schema tests reject unknown families, mismatched typed encodings,
  mutable rule versions, mutable literal containers, and the removed ambiguous
  string-membership operator.
- Replay tests compare semantic trace content and hypothetical signals under a
  pinned ruleset byte-for-byte; measured wall-clock cost is excluded.
- Shadow-mode tests prove suppression and escalation decisions remain
  hypothetical and the autonomic package cannot import the effect plane.
- Continuous-worker tests prove later registrations wait for explicit epoch
  rotation, only shadow observation events are produced, and failures before a
  trace, before a decision, or before checkpoint advancement recover without
  duplicate logical outputs.
- Agenda tests will permute evaluation order and require identical conflict
  resolution.
- Embedded/distributed acceptance will run the same personal-workflow cell.

This ADR extends [ADR 0001](0001-portable-durable-agent.md); it does not change
the canonical event, adapter, or capability-boundary decisions. Governed
internally generated cognition is specified separately by
[ADR 0003](0003-endogenous-drive-ecology.md). Durable worker recovery is
specified by [ADR 0004](0004-durable-consumer-checkpoints.md).
