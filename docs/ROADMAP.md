# Engineering roadmap

Noema's responsibility is persistent autonomous agency. Deployment, model,
tool, and interoperability choices remain adapters around the same semantics.

Security, observability, deterministic replay, and local operation are
cross-cutting release gates rather than a final wave.

## Cross-cutting track — Autonomic Fabric

The [Autonomic Fabric](AUTONOMIC_FABRIC.md) spans the cognitive roadmap. It is
not a monolithic rules release:

- v0.3 adds signals, immutable rule versions, pinned rulesets and evaluation
  epochs, deterministic predicate/temporal/scoring evaluation, firing
  telemetry/replay, hard and graded inhibition, shadow-only cells, salience
  resolution, and a continuous observational worker;
- v0.4 links optional evaluation epochs to durable awake epochs and adds
  deterministic freshness/orientation projections without active wake control;
- v0.5 exposes protocol-neutral work, lease, and ecology events to observational
  cells while keeping coordination in the work control plane;
- v0.6 adds candidate mining, counterfactual replay, fitness, meta-rule
  proposals, and governed lifecycle transitions;
- later work adds durable timer workers, richer opportunity patterns,
  sensing-request signals, active wake control, and salience-based continuity.

Rules emit signals by default. Learned policies never execute arbitrary code or
bypass the existing policy/capability boundary. Automatic reflex canaries wait
until durable evidence, replay, temporal semantics, and metacontrol exist.

## Cross-cutting track — Endogenous Drive Ecology

The [Endogenous Drive Ecology](ENDOGENOUS_DRIVE_ECOLOGY.md) adds governed
internal questions, maintenance, simulation, preparedness, and peer calibration
as a second source of cognitive demand. It does not create terminal values or a
new effect path:

- v0.3 collects real shadow evaluations and hypothetical decisions; no
  HabitForge, SkillForge, or intrinsic scheduler is implemented;
- v0.4 adds no endogenous scheduler; wake orientation remains effect-free;
- v0.5 adds no endogenous scheduler or intrinsic-work generator;
- v0.6 introduces first-class inquiry and peer-calibration event contracts,
  budgeted value-of-cognition experiments, and a shadow
  `IntrinsicAgenda`, then evaluates HabitForge candidates from the accumulated
  corpus;
- later work links SLEEP/DREAM/AWAKE scheduling, cognitive slack, and foreground
  preemption to the implemented awake-epoch substrate;
- SkillForge remains later work requiring independent sandbox, supply-chain,
  capability-registration, and authority governance.

Intrinsic activities remain subordinate to constitutional, user, mission, and
commitment goals. Background cognition is explicitly budgeted and produces
questions and candidates more readily than actions.

With shadow reliability hardened, the dependency order is:

```text
✓ persistent memory → ✓ situated continuity → ✓ durable work coordination
  → endogenous agenda → HabitForge → SkillForge
```

Autonomic feature expansion remains paused. Persistent memory, situated
continuity, and the deterministic durable-work slice are implemented;
endogenous agenda formation is the next dependency.

## v0.2 — Portable Durable Agent

Implemented:

- PostgreSQL `EventStore`;
- transactional outbox and durable inbox with fencing-token leases;
- NATS JetStream and deterministic in-memory broker adapters;
- event schema versioning and projection-time upcasting;
- action lifecycle, durable idempotency restoration, and crash recovery;
- model-provider/context/router contracts;
- OpenAI Responses and OpenAI-compatible local adapters;
- structured `ActionIntent` boundary validation;
- OpenTelemetry tracing port and OTLP adapter;
- replayable JSONL model fixtures;
- embedded/distributed deployment profiles and Docker Compose topology.

Acceptance: the autonomous incident application contains no mode-specific
policy branch and runs with both `MODE=embedded` and `MODE=distributed`.

## v0.3 — Persistent Cognitive Agent

- typed `Signal`, immutable `AutonomicRule` versions, `RulesetSnapshot`, and
  `EvaluationEpoch` (implemented shadow-kernel foundation);
- effect-free shadow evaluation with predicate/temporal/scoring encodings,
  complete rule traces, deterministic replay, and a `SalienceResolver`
  (implemented shadow-kernel foundation);
- sequence-correct content-addressed rulesets, hard/graded inhibition, and the
  continuously running observational `AutonomicShadowWorker` (implemented);
- generic durable `ConsumerCheckpoint` recovery, crash-window idempotency, and
  shadow processing-lag/phase telemetry (implemented);
- episodic projection over canonical event history (implemented);
- immutable semantic assertions and first-class evidence links (implemented);
- hypotheses, preserved contradictions, validity/freshness, and independent
  valid/knowledge-time queries (implemented);
- deterministic memory projection using generic durable checkpoints
  (implemented);
- decision-relevant lexical retrieval with a disposable rebuildable index
  (implemented);
- optional PostgreSQL/pgvector and local SQLite/FTS acceleration adapters;
- integration of memory retrieval into bounded model context assembly;
- maintenance debt and commitment recovery.

Acceptance: after a multi-day restart, an agent reconstructs relevant world
and cognitive state without replaying its full transcript into a model; late
knowledge remains bitemporally queryable, contradictions stay visible, indexes
are disposable, and partial projection writes replay without duplicates.

## v0.4 — Situated Continuity Foundation

Implemented:

- explicit wall, monotonic, world/occurrence, and knowledge-time distinctions;
- durable `AwakeEpoch` records with canonical cursors and optional evaluation
  epoch identity;
- provider-neutral durable source state, per-wake awareness demand,
  hazard-based freshness, awareness coverage, refresh requests, and observation
  budgets;
- a pure selective `WakeReconciler` and shadow-only orientation barrier;
- deterministic fake-source ecology and effect-free wake worker;
- single-cut continuity/memory reconstruction and valid-time insertion of
  delayed observations without changing `Event.timestamp`;
- canonical orientation reports, generic consumer checkpoints, and orientation
  efficiency/quality metrics, with runtime latency kept in telemetry;
- structural isolation from model, authority, capability, reasoning, and effect
  paths.

Acceptance: after a simulated 65-hour absence, Noema refreshes only four
decision-relevant changed domains, updates bitemporal memory, identifies the
highest-value issue, remains explicit when a critical source is unavailable,
and performs no consequential effect. A no-change wake stays silent, and four
relevant sources out of one hundred produce four refresh requests.

See [`SITUATED_CONTINUITY.md`](SITUATED_CONTINUITY.md) and
[ADR 0006](adr/0006-situated-continuity-foundation.md).

## v0.5 — Durable Work Coordination

Implemented:

- distinct durable `WorkOrder`, proposed plan, accepted `WorkGraph`,
  `WorkNode`, and later `ActionIntent` boundaries;
- provider-neutral `Planner`, deterministic `FakePlanner`, causal/version-pinned
  `PlanProposal`, and fail-closed `PlanValidator`;
- provider-neutral presence and capability manifests plus seeded/evidence-ready
  competence estimates, kept separate from authority, with expiring presence
  and seeded-only v0.5 routing;
- derived dependency frontiers and deterministic feasibility matching;
- ordinary independent verification work;
- fenced lease grant, completion, expiry, stale-token rejection, recovery, and
  reassignment;
- source-level orientation prerequisites and causal plan invalidation;
- exact-cut planning replay and stale planning-window admission rejection;
- control-plane-owned completion acceptance time;
- canonical replay of the complete implemented work lifecycle;
- structural isolation from models, effects, external connectors, endogenous
  scheduling, and generalized workflow languages.

Acceptance: the deterministic release graph advances through dependency waves,
matches feasible workers, recovers a crashed lease, uses an independent
verifier, blocks release on stale deployment knowledge, and invalidates after a
causal-state change without invoking a model or effect.

See [`DURABLE_WORK_COORDINATION.md`](DURABLE_WORK_COORDINATION.md) and
[ADR 0007](adr/0007-durable-work-coordination.md).

## v0.6 — Reflective Autonomous System

- governed HabitForge candidate mining from corrections and repeated trajectories;
- rule fitness, collision analysis, meta-rule proposals, and lifecycle gates;
- explicit value-of-computation policies;
- wall-clock, call, cost, branch, action, and recursion ceilings;
- adaptive reasoning depth and strategy selection;
- shadow-mode bandit/learned controllers;
- counterfactual policy replay and experiment comparison;
- explicit background cognitive budgets, NetVOC experiments, and a shadow
  `IntrinsicAgenda` over maintenance, inquiry, and simulation candidates.

Acceptance: learned control cannot execute before deterministic shadow
evaluation, and identical captured inputs reproduce the same semantic trace.

## Later — Situated Presence and Adaptive Perception

- durable timer workers, advanced opportunity patterns, and active
  salience-driven wake control;
- sensing-request signals governed by perception policy;
- substrate/sensor contracts and adaptive perception;
- provenance-bearing situation capsules and artifact retention;
- user, workflow, and agent ecology models;
- richer delegation protocols, lease renewal/cancellation, and opportunity
  windows;
- macOS reference sidecar and real-environment sleep/wake acceptances;
- governed SLEEP/DREAM/AWAKE linkage with foreground preemption and cognitive
  slack; dream outputs remain observational or proposals by default.

These capabilities extend the implemented v0.4 continuity substrate. They may
not introduce connector-owned temporal, cursor, freshness, or memory truth.

## Ongoing production ratchet

- poison-message quarantine and operator repair tools;
- sandbox adapters and secret-reference resolution;
- tenant isolation and policy-as-code adapters;
- performance/fault benchmarks at 1M+ events and 100-agent clusters;
- optional Temporal durable-execution adapter;
- Kafka/Redpanda transport adapter without changing core semantics.
