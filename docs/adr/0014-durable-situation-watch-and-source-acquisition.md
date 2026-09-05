# ADR 0014: Durable Situation Watch and Source Acquisition

Status: **Proposed — architecture review required; no runtime implementation is authorized**

## Context

The situated-partner G1 rehearsal can compose current intent, bitemporal memory,
awareness coverage, finite budgets, work, checkpoints, and explicit plan
invalidation. It cannot yet make these broader claims:

- a selected situation remains durably scheduled across process loss;
- rescheduling or terminal intent automatically cancels obsolete checks;
- quiet windows, next-check time, expiry, and catch-up are canonical;
- a bounded acquisition result distinguishes found, absent-in-scope, delayed,
  unavailable, denied, ambiguous, not established, and contradicted; or
- an opted-in observation scope can be durably paused, expired, or revoked.

`AsyncScheduler` is an in-memory convenience. `WorkOrder.deadline` and
`opportunity_window_end` are immutable planning data but do not gate
`ReadyFrontier`. `RefreshRequest` expresses desired epistemic refresh, not a
complete connector operation or result. Information Governance decides whether
information may be used; it does not say that a source is continuously in
scope. Treating any of those objects as the missing lifecycle would make a
false durability or authority claim.

The P0 product can use explicit application events and the situated-partner v1
projection contract synthetically. A reusable canonical runtime requires a
reviewed decision first.

## Proposed decision

If accepted, add one small generic lifecycle family around existing primitives:

1. **Observation scope.** An immutable activation records actor, purpose,
   source/account/workspace scope, allowed granularity/operations, cadence or
   event trigger, validity, quiet constraints, information-policy references,
   and authenticated authority. Transitions pause, resume, expire, revoke, or
   supersede it. No source content is stored in the scope.
2. **Situation watch.** A content-addressed watch binds one current intent or
   explicit mandate, semantic cause, situation/context revision, decision
   deadline, next check, expiry/cancellation condition, finite budget reference,
   and observation-scope reference. It is durable demand for the shared runtime,
   not a new scheduler or worker queue.
3. **Acquisition request.** A request cites the watch/context causal cut, target
   fact, reason, source scope/account, match policy, deadline, and finite
   query/read/model/time/cost limits. Information access and required disclosure
   are admitted separately at the exact current head.
4. **Acquisition result.** A result links the request and carries source
   version/cursor, observation time, evidence refs, coverage/limitations, retry
   eligibility, expiry, actual resource use, policy lineage, and exactly one of:

   ```text
   FOUND
   NO_MATCH_IN_SCOPE
   NOT_YET_AVAILABLE
   SOURCE_UNAVAILABLE
   ACCESS_DENIED
   AMBIGUOUS_MATCH
   FACT_NOT_ESTABLISHED
   CONTRADICTED
   ```

5. **Admission and recovery.** Every state-dependent transition rebuilds the
   current scope, intent, context, policy, deadline, and cancellation state,
   then uses compare-and-append at the actual predecessor head. Replay never
   assumes contiguous sequences. Checkpoints advance only after the required
   result or explicit terminal disposition is durable.
6. **Cancellation.** Terminal intent, revoked scope, superseded context,
   expired opportunity, or explicit stop causally terminates future checks and
   presentation eligibility. Acquired evidence remains immutable under its
   retention policy; it does not retain current authority.

Adapters may implement wall-clock wakeups, OS scheduling, push delivery, or
polling. They materialize due durable demand into the existing event/work
substrate and cannot own a second clock, event log, freshness model, authority
path, or connector-private watermark.

## Required invariants

```text
calendar time elapsed != outcome confirmed
scope activated != unrestricted collection
source permission != disclosure != learning != effect authority
acquisition result != instruction
deadline recorded != deadline enforced
old evidence != current intent
```

- Only authenticated scope transitions change collection permission.
- Source content cannot revise intent, expand scope, create work, or authorize
  an effect.
- Request identity is derived from semantic cause and pinned inputs, not timer
  tick count.
- An asleep/offline local deployment reports a coverage gap and catches up; it
  never claims continuous observation.
- A result for a cancelled or superseded request may remain evidence but cannot
  automatically surface or act.
- Acquisition coverage and `AwarenessCoverage` stay separate.
- No new acquisition-specific scheduler, memory store, or event transport is
  introduced.

## Quality-attribute scenarios

| Scenario | Required response |
|---|---|
| A selected event is rescheduled before a check | Cancel/supersede the old watch/request, recompute from current intent, and preserve an independent business cutoff. |
| The host sleeps across a due check | Record the coverage gap, discard expired work, and perform only bounded still-relevant catch-up after wake. |
| Intent becomes terminal while a connector is running | Preserve the governed evidence result, terminate future work, and deny stale presentation/effect. |
| A source is delayed, unavailable, denied, or ambiguous | Record the exact status and retry eligibility; never collapse it into an empty result. |
| Observation is paused or a source is excluded | Admit no new observations for that scope after the transition head; existing evidence follows retention policy. |
| Two workers race to complete one request across a PostgreSQL gap | Equal semantic results converge, incompatible results fail closed, and replay validates the actual predecessor head. |

## Compatibility and migration

- Existing `SourceState`, `RefreshRequest`, `AwarenessCoverage`, `WorkOrder`,
  `ConsumerCheckpoint`, Information Governance, and scheduler events remain
  unchanged.
- The situated-partner envelope stays a projection/consumer contract. Its
  synthetic result objects do not become canonical merely because this ADR is
  proposed.
- Existing Companion application events may be adapted as historical evidence
  only when their scope, intent, policy, timing, and status are explicit. Missing
  fields fail closed; they are not inferred from a successful connector call.
- Any future event family requires schema registration, upcasters, embedded and
  PostgreSQL sequence-gap tests, crash recovery, and distributed parity before
  an implementation status changes.

## Consequences and risks

The proposal closes one coherent control boundary: authorized observation
creates bounded durable watch demand, which may create a typed acquisition
attempt and result. It makes stop/pause/reschedule meaningful across restarts
without turning connectors into autonomous control planes.

It also adds canonical volume and lifecycle complexity. Continuous scopes can
become surveillance; aggressive catch-up can overload sources; and stale
results can be mistaken for current truth. Scope minimization, finite budgets,
expiry, poison isolation, retention enforcement, and explicit coverage are
therefore release gates rather than defaults.

## Rejected alternatives

- **Treat `AsyncScheduler` as durable.** Its handles and tasks are process-local.
- **Use `WorkOrder.deadline` as enforcement.** Current frontier logic does not
  enforce it, and work is broader than evidence acquisition.
- **Turn every source into its own scheduler/store.** This creates conflicting
  truth, clocks, budgets, and recovery.
- **Use `FOUND | EMPTY | ERROR`.** It destroys epistemic and permission meaning.
- **Fold observation scope into Information Policy.** Permission to use known
  information is not authorization to collect continuously.
- **Infer completion from elapsed calendar time.** Time passing is not evidence
  of attendance, agreement, or outcome.

## Fitness functions before acceptance

- structural test: source/acquisition modules cannot import effect execution or
  strategic mutation;
- replay test: every transition validates the actual preceding canonical head,
  including PostgreSQL sequence gaps;
- cancellation test: terminal intent, reschedule, revocation, and expiry leave
  no surfaceable old request;
- budget test: query/read/model/time/cost use cannot exceed the pinned request;
- sleep test: coverage gaps and bounded catch-up are explicit;
- privacy test: excluded scopes emit no observation and alternate-source copies
  cannot launder denial;
- recovery test: every crash boundary completes exactly the missing suffix;
- parity test: embedded/PostgreSQL/NATS projections agree semantically; and
- architecture test: no second scheduler, event log, authority path, or
  connector-owned freshness truth exists.

## Deferred

This ADR does not authorize runtime code, real connectors, protected ingestion,
learned source selection, workflow induction, the mixed cognitive/intervention
portfolio, ADR 0013 runtime, HabitForge, SkillForge, or general Situated
Presence. Numeric schedules, budgets, source adapters, and OS behavior remain
deployment/application choices.
