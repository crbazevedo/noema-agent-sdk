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
- v0.4 adds protocol-neutral coordination cells over delegations and leases;
- v0.5 adds candidate mining, counterfactual replay, fitness, meta-rule
  proposals, and governed lifecycle transitions;
- v0.6 adds durable timer workers, richer opportunity patterns,
  sensing-request signals, evaluation/awake-epoch linkage, active wake control,
  and salience-based continuity.

Rules emit signals by default. Learned policies never execute arbitrary code or
bypass the existing policy/capability boundary. Automatic reflex canaries wait
until durable evidence, replay, temporal semantics, and metacontrol exist.

## Cross-cutting track — Endogenous Drive Ecology

The [Endogenous Drive Ecology](ENDOGENOUS_DRIVE_ECOLOGY.md) adds governed
internal questions, maintenance, simulation, preparedness, and peer calibration
as a second source of cognitive demand. It does not create terminal values or a
new effect path:

- v0.3 collects real shadow evaluations and hypothetical decisions; no Forge or
  intrinsic scheduler is implemented;
- v0.4 introduces first-class inquiry and peer-calibration event contracts;
- v0.5 introduces budgeted value-of-cognition experiments and a shadow
  `IntrinsicAgenda`, then evaluates HabitForge candidates from the accumulated
  corpus;
- v0.6 links SLEEP/DREAM/AWAKE epochs, cognitive slack, foreground preemption,
  and situated continuity;
- SkillForge remains later work requiring independent sandbox, supply-chain,
  capability-registration, and authority governance.

Intrinsic activities remain subordinate to constitutional, user, mission, and
commitment goals. Background cognition is explicitly budgeted and produces
questions and candidates more readily than actions.

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
- episodic indexes over event history;
- semantic assertions linked to evidence;
- hypotheses, contradictions, and validity intervals;
- PostgreSQL/pgvector and local SQLite/FTS projections;
- context assembly by relevance, evidence, freshness, and confidence;
- maintenance debt and commitment recovery.

Acceptance: after a multi-day restart, an agent reconstructs relevant world
and cognitive state without replaying its full transcript into a model; pinned
shadow rules replay deterministically without producing an effect.

## v0.4 — Agent Society

- coordination cells for delegation, lease, and presence signals;
- MCP capability adapter and A2A agent adapter;
- capability manifests and discovery;
- typed task offers, bids, awards, progress, result, failure, cancellation;
- domain-specific trust, authority, rehabilitation, and exploration;
- durable multi-agent cancellation and contracting;
- first-class `Inquiry`, `CalibrationRequest`, and `CalibrationResponse` event
  contracts with evidence-preserving disagreement.

Acceptance: a Noema agent delegates to a non-Noema A2A agent and consumes an
MCP server without exposing Noema's internal memory or runtime protocol.

## v0.5 — Reflective Autonomous System

- governed Rule Forge candidate mining from corrections and repeated trajectories;
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

## v0.6 — Situated Continuity

- durable timer workers, advanced opportunity patterns, and active
  salience-driven wake control;
- sensing-request signals governed by perception policy;
- temporal semantics, source cursors, freshness, and awake epochs;
- wake reconciliation and an orientation barrier;
- substrate/sensor contracts and adaptive perception;
- provenance-bearing situation capsules and artifact retention;
- user, workflow, and agent ecology models;
- durable delegations, work leases, and opportunity windows;
- macOS reference sidecar and simulated sleep/wake flagship demo;
- governed SLEEP/DREAM/AWAKE linkage with foreground preemption and cognitive
  slack; dream outputs remain observational or proposals by default.

See [`SITUATED_CONTINUITY.md`](SITUATED_CONTINUITY.md) for its invariants and
dependency sequence.

## Ongoing production ratchet

- poison-message quarantine and operator repair tools;
- sandbox adapters and secret-reference resolution;
- tenant isolation and policy-as-code adapters;
- performance/fault benchmarks at 1M+ events and 100-agent clusters;
- optional Temporal durable-execution adapter;
- Kafka/Redpanda transport adapter without changing core semantics.
