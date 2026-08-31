# ADR 0006: Every wake is a selective epistemic reconstruction

- Status: accepted
- Date: 2026-08-30
- Scope: temporal semantics, source freshness, wake reconciliation, and
  pre-action orientation

## Context

A durable agent can reconstruct memory after restart and still act incorrectly.
External sources continue changing while the process is inactive, so replaying
the last prompt or restoring the last belief projection does not establish that
those beliefs remain trustworthy. Refreshing every source is also wrong: it is
expensive, invasive, slow, and ignores the decision the agent actually faces.

The architecture therefore needs an explicit boundary between waking and
reasoning or acting. It must preserve delayed world time versus knowledge time,
estimate source-specific staleness, select minimum sufficient observations,
and remain honest when a prerequisite cannot be refreshed.

## Quality-attribute scenarios

1. After a simulated 65-hour absence with four relevant changes and two
   irrelevant/stable domains, orientation refreshes the four relevant sources,
   updates bitemporal memory, names the highest-value issue, and emits no
   consequential effect.
2. After an eight-hour no-change absence, orientation performs no source
   refresh, deliberation, or effect.
3. When a Friday occurrence is learned Monday, a historical query distinguishes
   what was true from what Noema knew Friday.
4. When a critical source is unavailable, freshness remains degraded,
   uncertainty is explicit, and the dependent action is shadow-blocked.
5. With one hundred sources and four decision-relevant stale prerequisites,
   the planner requests four refreshes under the observation budget.
6. Given the same event history, clock values, source deltas, and budget,
   projections and decisions are deterministic.
7. When Friday `open` and Saturday `closed` are already known and Friday
   `merged` arrives Monday, valid-time queries return `open`, then `merged`, then
   `closed`; recording order does not erase the Saturday state.
8. Under a one-source budget, a very stale source outranks a mildly stale one;
   high freshness with insufficient confidence can still require refresh.
9. A wake reconstructs continuity and memory from the same canonical cut even
   when an external memory projector is behind that cut.
10. Identical semantic outcomes produce the same canonical report identity
    despite different monotonic execution durations.

## Decision

1. Treat `WAKE != RESUME`. An `AwakeEpoch` is the durable unit of wake-time
   reconstruction and records wall-time absence, canonical cursors, optional
   autonomic epoch identity, and orientation status.
2. Keep `Event.timestamp` semantics unchanged in this milestone. Delayed
   observations use the observation/record time in the envelope and carry
   source-reported `occurred_at` in the payload. Memory maps those values to
   `recorded_at` and `valid_from`, respectively.
3. Centralize wall time, monotonic time, time zones, durations, deadlines, and
   sleep intervals in `TemporalService`. Never use monotonic time as world or
   durable event time.
4. Represent mutable external domains through provider-neutral `SourceState`
   contracts containing durable source properties only. Represent current goal
   references, relevance, decision sensitivity, and required
   freshness/confidence separately as per-wake `AwarenessDemand`. Connector API
   types cannot enter the reconciliation core.
5. Derive point-in-time source freshness by exponential hazard decay from the
   durable observation time and hazard. Do not persist the resulting freshness
   snapshot in `SourceState`.
6. Project `AwarenessCoverage` for decision-relevant domains. Completeness is a
   sufficiency claim for current decisions, not a claim of omniscience.
7. Make `WakeReconciler` a pure planner over current freshness/confidence gaps
   and demand importance. Combine normalized gaps as
   `importance × [1 - (1 - freshness_gap)(1 - confidence_gap)]`, rank against
   observation cost, and apply an explicit source/cost budget. Hazard and
   elapsed time affect freshness before planning and are not applied twice.
8. Represent proposed observations as effect-free `RefreshRequest` values.
   Unavailable refreshes become `MARK_UNCERTAIN`; they never become evidence of
   no change.
9. Keep `OrientationBarrier` shadow-only. It reports whether action
   prerequisites would be blocked but has no import or call path to models,
   authority, capabilities, deliberation, dispatch, or execution.
10. Build the first ecology exclusively from deterministic `FakeSource`
    adapters. External connectors and active sensing wait until the mechanism
    passes temporal, failure, selectivity, and silence acceptances.
11. Reuse the canonical event store, `MemoryProjection`, generic
    `ConsumerCheckpoint`, and optional autonomic evaluation-epoch reference.
    At wake, capture one canonical history cut `N` and rebuild both
    `ContinuityProjection` and `MemoryProjection` through `N`; never depend on
    the progress of an external projector. Do not create private cursor, belief,
    or wake databases.
12. Persist source states, awake epochs, refresh requests/results,
    observations, assertions, and orientation reports as canonical events.
    Freshness, coverage, refresh plans, and barrier decisions remain
    deterministic projections.
13. Insert delayed observations by valid time. A new assertion supersedes only
    the unique predecessor valid immediately before its occurrence and closes
    at the earliest unique successor. Ambiguous history creates no synthetic
    supersession and remains available for contradiction handling.
14. Keep runtime measurements out of content-addressed semantic records.
    Canonical reports contain semantic outcomes; monotonic orientation latency
    is emitted only through `TelemetrySink`.

## Consequences and tradeoffs

- Noema gains a formal, inspectable reason not to act from stale context.
- Selective sensing reduces latency, cost, privacy exposure, and irrelevant
  observation while retaining explicit missed-change metrics.
- A no-change wake can be a successful silent outcome.
- Source hazards and awareness demands require later calibration; the initial
  deterministic freshness and gap formulas are intentionally simple.
- Global orientation can be sufficient while a particular future action still
  lacks a prerequisite. The action-specific barrier is the final check.
- The worker currently rebuilds small projections from canonical history for
  clarity and causal-cut correctness. Snapshot acceleration may be added only
  as a disposable projection that preserves the same cut.
- `FakeSource` proves semantics, not connector behavior, authentication,
  privacy policy, or real-world reliability.
- The event envelope temporarily carries two temporal coordinates in different
  places. This avoids migration risk but requires disciplined mapping until a
  future schema version.
- The barrier records counterfactual blocking only. Enforcing it in the effect
  path is deferred until shadow evidence establishes thresholds and failure
  behavior.

## Rejected alternatives

- **Resume the last prompt or transcript:** restores text, not trustworthy
  situational state.
- **Refresh every source:** violates minimum-sufficient sensing and scales cost
  with the universe rather than the decision.
- **Assume unchanged after refresh failure:** converts missing evidence into a
  false observation.
- **Put connector logic in the planner:** couples epistemic policy to vendors
  and prevents deterministic testing.
- **Redefine `Event.timestamp` in place:** silently changes existing event
  semantics and introduces migration ambiguity.
- **Allow the orientation barrier to execute refreshes or actions:** creates a
  parallel effect path around existing governance.
- **Use a private wake cursor store:** creates a second recovery authority
  beside canonical checkpoints and events.
- **Use an LLM to choose initial refreshes:** obscures the policy before its
  inputs, costs, and failure modes are measurable.
- **Select the latest assertion by recording time:** corrupts valid-time order
  when delayed evidence arrives after a later world state.
- **Reuse a live external memory projection during wake:** couples orientation
  correctness to another consumer's lag and breaks single-cut reconstruction.
- **Include runtime latency in report identity:** makes equal semantic outcomes
  canonically different because of scheduler or machine speed.

## Fitness functions

- the flagship 65-hour wake refreshes repository, calendar, delegation, and
  dependency state but not irrelevant documents or stable preferences;
- delayed observations retain distinct event observation time and payload
  occurrence time, producing correct bitemporal memory queries;
- unavailable critical sources yield incomplete coverage and a shadow-blocked
  dependent action;
- one hundred sources with four relevant stale sources produce four requests;
- current freshness/confidence gaps produce non-zero first-wake priorities,
  rank very stale above mildly stale under one budget slot, and refresh a
  high-freshness/low-confidence source;
- a delayed Friday observation is inserted between its Friday predecessor and
  Saturday successor, while ambiguous predecessors remain unsuperseded;
- a wake produces correct memory while the external projector is deliberately
  lagging because continuity and memory rebuild from the same canonical cut;
- equal semantic fixtures with different monotonic durations have identical
  orientation report IDs and distinct latency telemetry;
- no-change wakes emit zero observation, belief-update, deliberation, and
  effect events;
- canonical orientation reports record semantic efficiency, consideration,
  refresh, fetched events, belief updates, retained staleness, cost,
  unnecessary refreshes, and missed changes; telemetry additionally records
  runtime latency;
- architecture tests reject effect-plane imports and effect operations from the
  continuity core and worker;
- all continuity state can be reconstructed from canonical event history and
  generic checkpoints.

This decision builds on [ADR 0004](0004-durable-consumer-checkpoints.md) and
[ADR 0005](0005-persistent-cognitive-memory.md).
