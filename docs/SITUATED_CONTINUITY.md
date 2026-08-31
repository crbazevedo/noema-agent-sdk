# Situated Continuity

Situated Continuity is the v0.4 foundation for agents that explicitly
reconstruct context after intermittent execution:

> An agent is a temporally discontinuous process that reconstructs sufficient
> situational continuity whenever it becomes active.

It is not an always-conscious process and not a prompt-resume mechanism.

```text
SLEEP → WAKE → REPLAY → ASSESS FRESHNESS → SELECTIVE REFRESH → RECONCILE → ORIENTED
```

The governing invariant is `WAKE != RESUME`. Every wake is an epistemic
reconstruction. The successful result may be action, deliberation, silence, or
another sleep interval; v0.4 performs only the reconstruction and records what
the orientation barrier would block.

## Implemented foundation

The foundation is deterministic and connector-free:

- `TemporalService` separates restart-safe wall time, local monotonic duration
  time, time zones, deadlines, and sleep intervals. Source-reported world time
  remains a separate value.
- `AwakeEpoch` durably records prior activity, elapsed wall time, canonical log
  cursors, an optional autonomic evaluation-epoch pin, and terminal orientation
  status.
- `SourceState` records durable source facts: domain, observation time, cursor,
  change hazard, confidence, and refresh cost. It does not retain wake-specific
  goal policy or a decayed freshness snapshot.
- `AwarenessDemand` supplies the per-wake goal references, relevance, decision
  sensitivity, and required freshness/confidence for one source.
- `FreshnessModel` applies domain-sensitive exponential decay,
  `exp(-hazard * elapsed)`.
- `AwarenessCoverage` projects whether decision-relevant domains have enough
  confidence and freshness. It asks whether Noema knows enough for the next
  important decision, not whether every possible source was refreshed.
- `RefreshRequest` is an effect-free perception proposal.
- `WakeReconciler` is a pure, observation-budgeted planner. It emits refresh,
  accept-existing, mark-uncertain, or defer decisions without importing a
  connector or effect path.
- `OrientationBarrier` is shadow-only. It exposes stale or missing epistemic
  prerequisites but cannot authorize, deliberate, dispatch, or execute.
- `FakeSource` supplies deterministic cursor deltas and failure behavior for
  executable sleep/wake scenarios.
- `SituatedContinuityWorker` captures one canonical history cut `N`, rebuilds
  both continuity and memory through that same cut, performs the plan over fake
  sources, updates bitemporal memory, emits an `OrientationReport`, and advances
  a generic `ConsumerCheckpoint`. A lagging external memory projector is never
  wake-time truth.

The canonical event log remains the only durable authority. Source states,
awake epochs, refresh requests/results, observations, semantic assertions, and
orientation reports are events. Freshness, coverage, refresh plans, and barrier
decisions are deterministic projections over those records.

## Temporal semantics

v0.4 deliberately does not redefine `Event.timestamp`. For delayed external
observations:

```text
Event.timestamp       = when Noema observed/recorded the report
payload.occurred_at   = source-reported world time

assertion.valid_from  = occurred_at
assertion.recorded_at = Event.timestamp
```

This preserves the distinction between what was true at a world time and what
Noema knew at a knowledge time without an event-envelope migration. A future
schema version may promote additional temporal coordinates through deterministic
upcasting.

Late observations are inserted by valid time, not recording order.
`MemoryProjection.temporal_neighbors()` finds the uniquely determined assertion
valid immediately before the occurrence and the earliest assertion after it.
The new assertion supersedes only a unique predecessor and ends at the
successor's `valid_from`. Ambiguous history is preserved without inventing a
supersession.

Wall and monotonic time are also separate. Wall time survives a restart and
governs deadlines; monotonic time measures local orientation latency without
being corrupted by wall-clock adjustment. Runtime latency is operational
telemetry only and cannot alter canonical report identity.

## Selective reconciliation

Freshness decay turns durable source state into the current wake's freshness.
The planner then measures current requirement gaps rather than applying sleep
elapsed time or hazard a second time:

```text
importance       = relevance × decision sensitivity
freshness_gap    = max(0, 1 - current_freshness / required_freshness)
confidence_gap   = max(0, 1 - confidence / required_confidence)
refresh_need     = importance × [1 - (1 - freshness_gap)(1 - confidence_gap)]
```

This lets accumulated staleness outrank mild staleness and lets a fresh but
low-confidence source request observation. The planner ranks useful uncertainty
reduction against refresh cost, applies the observation budget, and never
treats a failed refresh as evidence that the world is unchanged. Unavailable
critical sources retain degraded freshness, become explicit coverage gaps, and
leave dependent actions shadow-blocked.

The primary metric is:

```text
orientation efficiency = decision-relevant uncertainty removed / observation cost
```

Canonical reports also record sources considered/refreshed, events fetched,
beliefs updated, stale beliefs retained, observation cost, unnecessary
refreshes, and missed changes. Runtime latency is recorded separately through
`TelemetrySink`.

## Acceptance ecology

The deterministic flagship simulates a 65-hour absence. Repository, calendar,
delegation, and dependency facts change; irrelevant documents and stable
preferences do not warrant refresh. On wake, Noema refreshes only the four
decision-relevant domains, records delayed observations with distinct world and
knowledge times, updates semantic memory, identifies the highest-priority
dependency issue, produces an orientation report, and performs no effect.

Additional executable scenarios prove:

- an eight-hour no-change wake performs no refresh, deliberation, or action;
- delayed knowledge preserves what was true versus what was known;
- a critical unavailable source makes orientation explicitly incomplete;
- four relevant sources out of one hundred produce four refreshes, not one
  hundred;
- accumulated current staleness wins a one-source budget, while high freshness
  with low confidence still requests refresh;
- a Friday state learned Monday is inserted between the Friday predecessor and
  Saturday successor, even while the external memory projector is lagging;
- identical semantic wake outcomes retain the same report identity across
  different monotonic runtimes;
- the shadow orientation barrier exposes insufficient action prerequisites;
- structural fitness gates prevent the continuity core and worker from reaching
  agents, models, authority, capabilities, reasoning, or effect operations.

## Required state scopes

Future situated presence retains these conceptual scopes:

```text
WORLD
├── SUBSTRATE  execution environment, resources, permissions, sensors
├── ECOLOGY    people, applications, projects, services, and agents
├── USER       explicit goals, inferred preferences, attention, constraints
└── SELF       commitments, delegations, suspended work, assumptions
```

The agent receives a goal-relevant projection, not the raw universe.

## Invariants

- Capability, OS permission, and Noema authority are separate.
- Raw artifacts are evidence, not memory or truth.
- Mutable assertions carry distinct world-valid and recorded-knowledge time.
- Explicit goals outrank committed, revealed, and inferred goals.
- Consequential action requires sufficiently fresh epistemic prerequisites.
- Sensing escalates from stored knowledge to metadata and APIs before UI
  structure or targeted pixels/audio.
- Default raw screenshot/audio retention is zero beyond a future processing
  window.
- A wake cycle with no relevant change may successfully perform no action.

## Deferred work

v0.4 includes no GitHub, calendar, email, desktop, macOS, screenshot, audio, or
continuous-sensing connector; no LLM refresh planner; and no agent-society,
HabitForge, or SkillForge feature. Later milestones may add perception policy,
substrate/sensor adapters, provenance-bearing situation capsules, privacy and
retention controls, durable presence/delegation, active wake scheduling, and a
macOS reference sidecar. Those capabilities must reuse this temporal and
epistemic substrate rather than create connector-owned truth.

See [ADR 0006](adr/0006-situated-continuity-foundation.md) for the decision and
fitness functions.
