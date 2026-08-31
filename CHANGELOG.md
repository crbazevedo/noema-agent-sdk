# Changelog

## Unreleased

## 0.5.0 — 2026-08-31

- added immutable `WorkOrder`, `WorkNode`, `WorkDependency`, and validated
  `WorkGraph` contracts without conflating goals, plans, work, or actions;
- added the provider-neutral `Planner` protocol, deterministic `FakePlanner`,
  causal/version-pinned `PlanProposal`, and a fail-closed DAG `PlanValidator`;
- added durable `AgentPresence`, `CapabilityManifest`, and seeded/evidence-ready
  `CompetenceEstimate` facts while keeping capability, competence, and
  authority separate;
- added derived `ReadyFrontier`, deterministic capability/competence-aware
  `WorkerMatcher`, and structurally independent verification work;
- added fenced `WorkLease` grants, mutually exclusive terminal completion or
  expiry, stale-token rejection, replay recovery, and safe reassignment;
- integrated Situated Continuity source prerequisites into work readiness and
  added causal-state plan invalidation without erasing completed artifacts;
- added canonical `WorkProjection` replay and a coordinator that rebuilds from
  history before each lifecycle transition rather than owning a second store;
- demonstrated dependency waves, worker loss, independent verification, stale
  release knowledge, fresh readiness, and causal invalidation in one
  deterministic model-free, connector-free, effect-free acceptance scenario;
- recorded the boundaries, tradeoffs, explicit deferrals, and structural gates
  in ADR 0007;
- hardened graph admission against causal changes during planning and made
  replay reconstruct capability inputs through the exact planning cut;
- made agent presence expire, kept unresolved evidence-based competence out of
  v0.5 routing, and based lease completion legality on control-plane acceptance
  time rather than a worker-reported finish time;
- added atomic expected-head event append across embedded and PostgreSQL stores,
  preserved transactional outbox semantics, and closed the final graph
  validate-to-append race with deterministic revalidation.

## 0.4.0 — 2026-08-30

- promoted Situated Continuity ahead of agent society in dependency order and
  implemented the deterministic, connector-free foundation;
- added `TemporalService` with explicit restart-safe wall time, monotonic local
  durations, time zones, deadlines, and sleep intervals;
- added durable `AwakeEpoch` and provider-neutral `SourceState` event contracts
  plus exponential domain-sensitive freshness decay;
- separated durable `SourceState` facts from per-wake `AwarenessDemand` goal,
  relevance, sensitivity, and sufficiency requirements;
- added decision-relevant `AwarenessCoverage`, effect-free `RefreshRequest`
  proposals, explicit observation budgets, and a pure selective
  `WakeReconciler`;
- added a shadow-only `OrientationBarrier` that exposes insufficient
  freshness/confidence prerequisites without reaching models, authority,
  agents, capabilities, reasoning, dispatch, or execution;
- added deterministic cursor-driven `FakeSource` adapters and an effect-free
  `SituatedContinuityWorker` that reuses the canonical event store, memory
  projection, generic consumer checkpoints, and optional autonomic evaluation
  epoch identity;
- preserved the existing event envelope for delayed observations: observation
  time remains `Event.timestamp`, source world time is `payload.occurred_at`,
  and memory maps those to assertion knowledge and valid time;
- inserted late observations through unambiguous valid-time predecessor and
  successor boundaries instead of latest recording time, preserving ambiguous
  histories without synthetic supersession;
- made refresh priority depend on current freshness/confidence gaps and demand
  importance, without applying sleep elapsed time or change hazard twice;
- rebuilt continuity and memory from the same captured canonical history cut on
  every wake, independent of external projector lag;
- added canonical orientation reports for semantic efficiency, sources
  considered/refreshed, fetched events, updated beliefs, retained staleness,
  cost, unnecessary refreshes, and missed changes;
- kept monotonic runtime latency exclusively in telemetry so equivalent
  semantic outcomes retain the same content-addressed report identity;
- demonstrated the 65-hour selective wake, silent no-change wake, delayed
  knowledge, unavailable critical source, and four-of-one-hundred selective
  freshness acceptances with no consequential effect;
- recorded the architecture in ADR 0006 and added a structural gate that keeps
  situated continuity isolated from the effect plane.

## 0.3.0 — 2026-08-30

- added immutable, content-addressed semantic assertions with observed,
  inferred, reported, assumed, and simulated epistemic provenance;
- separated canonical episodes, first-class evidence links, and projected
  beliefs with independent valid-world and recorded-knowledge time;
- added append-only supersession and validity closure plus preserved,
  deterministically detected and resolved contradictions;
- added decision-relevant retrieval over lexical similarity, time, goals,
  evidence, freshness, and conflict/staleness penalties;
- made the lexical index disposable and rebuildable without semantic-state
  loss, preserving the boundary for later FTS and vector adapters;
- added the crash-recoverable `MemoryProjector` using generic canonical
  `ConsumerCheckpoint` records and deterministic derived event IDs;
- hardened same-process retries by rebuilding speculative projection state from
  the durable checkpoint after derived-event write failures;
- centralized fail-closed evidence resolution, blocked missing references and
  inline simulation laundering, and separated assertion source anchors from the
  authoritative `EvidenceLink` graph;
- renamed projected belief confidence to `max_assertion_confidence` so an
  uncertain belief cannot imply confidence in a selected value;
- validated late knowledge, conflicting evidence, partial-write replay, and
  fresh-evidence-over-stale-similarity acceptance scenarios;
- recorded the persistent cognitive memory architecture in ADR 0005 and added
  structural provider/effect isolation gates for its pure core;
- accepted the signal-first Autonomic Fabric architecture;
- implemented the effect-free Autonomic Shadow Kernel with immutable rules,
  content-addressed rulesets and sequence-pinned evaluation epochs,
  predicate/temporal/scoring cells, complete evaluation traces, and
  deterministic salience resolution;
- added a continuous observational worker over the canonical event substrate
  that persists evaluations and would-have-signaled/woken/suppressed outcomes
  without invoking models, authority, agents, or capabilities;
- added generic event-sourced consumer checkpoints, crash-window replay,
  deterministic partial-output idempotency, and processing-lag/phase telemetry;
- distinguished precedence-based hard inhibition from confidence-weighted
  graded modulation and removed collection-membership predicates from the
  deliberately small rule language;
- demonstrated deep-work suppression, opportunity escalation, stale-delegation
  escalation, cheap resolution, and byte-equivalent replay;
- moved temporal evaluation plus rule telemetry/replay into the mandatory v0.3
  substrate, before HabitForge or active reflexes;
- staged governed HabitForge learning and active wake control behind additional
  shadow evidence and metacontrol;
- accepted the Endogenous Drive Ecology as a staged mid-term architecture for
  bounded inquiry, calibration, consolidation, and intrinsic agenda formation;
- added architecture gates for retired terminology, dynamic rule execution,
  adapter leakage, and imports from the effect plane.

## 0.2.0 — 2026-08-30

Portable durable agent milestone:

- PostgreSQL event store with transactional outbox and durable inbox;
- NATS JetStream transport behind a provider-neutral broker protocol;
- at-least-once delivery, expiring leases, fencing tokens, and crash recovery;
- versioned events with deterministic projection-time upcasting;
- structured model-provider contracts and `ActionIntent` validation;
- OpenAI Responses and OpenAI-compatible local model adapters;
- record/replay model fixtures and provider routing;
- provider-neutral tracing with an OpenTelemetry/OTLP adapter;
- embedded and distributed deployment profiles plus Docker Compose topology;
- architecture fitness functions and real distributed acceptance coverage.

## 0.1.0 — 2026-08-30

Initial working substrate:

- asynchronous event bus with ordered per-subscriber delivery;
- durable event stores for memory and SQLite;
- event-sourced situation graph;
- typed capability registry;
- attention-aware deliberation;
- policy-bounded autonomous execution;
- cognitive controller with critics and falsification hooks;
- scheduler, multi-agent system runtime, telemetry, and tests;
- runnable autonomous incident-response example.
