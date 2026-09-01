# ADR 0010: Deterministic endogenous cognition

- Status: Proposed — deterministic v0.6 implementation candidate awaiting acceptance
- Date: 2026-09-01
- Scope: endogenous inquiry, value-of-cognition evaluation, finite background
  budgets, deterministic agenda selection, calibration, replay, and preemption

## Context

Noema can already preserve beliefs, reconstruct orientation, steward intent,
and coordinate durable work. Those layers still depend on an external event or
operator deciding what deserves cognition. A durable agent also needs a bounded
way to notice unresolved questions while nobody is prompting it.

The accepted Endogenous Drive Ecology describes that direction, but most of its
long-term mechanisms remain deliberately speculative. The first implementation
must prove the control semantics without relying on an LLM, learned policy,
optimizer, generated skill, new scheduler, or effect path.

## Readiness synthesis

The implemented substrate is sufficient for a small vertical slice:

1. the canonical event log supplies one replay and recovery authority;
2. `ConsumerCheckpoint` supplies durable, idempotent worker progress;
3. `StrategicProjection` supplies current goal revisions and terminal-intent
   barriers;
4. `RoadmapHealth` and `CommitmentCoverage` supply grounded maintenance demand;
5. `MemoryProjection` supplies stale and contradictory belief evidence;
6. autonomic shadow traces supply novelty candidates without granting them
   value merely because they are novel;
7. expected-head append supplies atomic admission against the state that was
   validated;
8. a finite resource vector can express background cognition limits without
   claiming a calibrated global optimizer; and
9. the existing work and action layers can remain entirely downstream and
   untouched.

One integration gap remains intentionally conservative: memory does not yet
carry a generic, authoritative goal-relevance edge. The v0.6 belief detector
therefore accepts only assertion subjects that exactly identify a current goal,
roadmap, roadmap revision, or commitment. It does not infer relevance from
similarity or prose.

## Decision

### Preserve the identity and authority boundaries

```text
Signal != Inquiry != IntrinsicActivity != WorkOrder != ActionIntent

Capability != Competence != Authority

DREAM authority != effect authority
```

An `Inquiry` is an evidence-bearing question. An `IntrinsicActivity` is a
candidate allocation of finite cognition toward that question. Neither is
durable work or permission to act. Endogenous cognition may serve current
`ACTIVE` or `BLOCKED` governing intent; it cannot choose terminal values or
revive `COMPLETED`, `FAILED`, or `CANCELLED` goals.

### Use one deterministic shadow pipeline

```text
canonical scan request at cursor H
  → deterministic candidate producers through H
  → Inquiry + IntrinsicActivity
  → explicit ValueOfCognition terms under a pinned policy
  → deterministic finite-budget IntrinsicAgenda
  → replayable shadow state
```

The first producers are intentionally bounded:

- current roadmap-health review needs;
- uncovered criteria on active commitments;
- stale or contradictory beliefs with exact strategic identity binding;
- active autonomic novelty signals; and
- evidence-preserving peer disagreement.

Novelty is only a source of a candidate question. It receives no intrinsic
priority bonus and may have non-positive value of cognition.

### Make Value of Cognition explicit and inspectable

For policy snapshot `P`, the deterministic estimate is:

```text
NetVOC = expected decision improvement
       - weighted compute cost
       - weighted delay cost
       - weighted attention cost
       - weighted opportunity cost
       - weighted privacy/risk cost
```

Every term, weight, policy identity, causal cursor, and evaluation time is
recorded. v0.6 uses fixed seeded inputs; these are a testable policy, not a
claim of learned calibration.

Candidates are ordered by descending `NetVOC`, urgency, confidence, and then
stable activity identity. Only strictly positive candidates that fit every
dimension of the pinned `BackgroundCognitiveBudget` are selected. The greedy
selector is deterministic and auditable; it is explicitly not an optimal
scheduler or solver.

### Bound cognition with a DREAM epoch

A `DreamEpoch` pins its consumer, scan trigger, event-log cursor, policy
snapshot, agenda selector identity/version, finite resource budget, start,
expiry, and `DREAM_PROPOSAL_ONLY` authority ceiling. Each consumer may own at
most one active epoch, and each epoch may record at most one agenda selection.
Foreground work that is causally later than the pinned cut preempts active
epochs through the existing event bus. Historical foreground cannot preempt a
new epoch. Expiry, preemption, and explicit abandonment are terminal and accept
no further cognitive output.

### Keep admission and recovery canonical

The worker reconstructs strategy, memory, and endogenous state from the same
captured canonical cut. Every lifecycle transition that depends on current
state carries exact-head validation metadata and enters through conditional
append. Replay reruns current-intent, evidence, epoch, deterministic-policy,
budget, single-selection, preemption, and expiry legality.

The worker advances its generic `ConsumerCheckpoint` only after all required
outputs exist or the scan has a durable terminal explanation. A preempted or
expired partial epoch is complete processing even without a selection. Intent
loss records explicit abandonment before checkpoint advancement. A crash in
any of those windows replays the scan, recognizes its terminal epoch, and moves
past it rather than retrying an impossible scan forever.

An unchanged unresolved inquiry with unchanged evidence and governing-intent
basis cannot create a new activity in a later scan. The original inquiry's
causal cut and expiry remain authoritative; renewal requires an explicit new
basis, such as new evidence or a changed governing intent revision.

Agenda replay dispatches through the selector identity/version pinned in both
policy and epoch state. v0.6 registers only
`stable-greedy-multidimensional` version 1. Unknown selectors fail closed, and
later algorithms must be added beside—not mutate—the v1 implementation.

### Remain shadow-first

The v0.6 worker does not dispatch `WorkOrder`, create `ActionIntent`, call a
model or capability, mutate a goal, or own a scheduler. Its strongest output is
a selected cognitive proposal. Existing work, intent, authority, orientation,
policy, and effect boundaries remain independent.

## Consequences and tradeoffs

- Noema can now generate useful, durable cognitive demand without an external
  prompt while preserving the user's governing intent.
- Deterministic fixed weights are less adaptive than a learned policy, but make
  replay, audit, crash recovery, and negative-value silence testable first.
- Exact strategic identity binding misses some relevant beliefs. This false-
  negative bias is accepted until a provenance-bearing relevance relation is
  designed.
- A greedy multidimensional allocator may leave usable capacity. That is
  preferable to introducing an optimizer before resource and outcome data are
  calibrated.
- DREAM epochs remain active after agenda formation until preempted or expired,
  but a consumer cannot multiply slack by opening concurrent epochs. Later
  renewable background leases may replace this conservative limit without
  weakening the v0.6 authority ceiling.

## Rejected alternatives

- **Start with LLM-generated reflection:** would entangle control correctness
  with model behavior and make replay depend on provider output.
- **Treat novelty as curiosity value:** confuses surprise with usefulness and
  rewards irrelevant stimulation.
- **Dispatch selected activities as work:** collapses cognition into agency and
  bypasses work admission, orientation, authority, and effects.
- **Let competence grant initiative or authority:** confuses predicted quality
  with legitimate purpose and permission.
- **Use a learned or optimal allocator now:** lacks calibrated outcome and cost
  evidence and prematurely freezes the objective.
- **Add a private queue or cursor:** creates a second recovery authority beside
  the canonical event log and generic consumer checkpoint.

## Deferred decisions

The following are outside v0.6: LLM inquiry or planning, RDDL/MDP/RL and solver-
based allocation, learned weights, runtime information-gain estimation,
adaptive oversight, generated habits or skills, endogenous work dispatch,
general workflow languages, real connectors, and an endogenous scheduler.

## Fitness functions

- identical captured state produces an identical semantic agenda;
- a scan with no live governing goal records no inquiry or activity;
- terminal goals admit no new endogenous cognition while blocked goals remain
  eligible for recovery-oriented thought;
- non-positive `NetVOC` is suppressed;
- every selected subset fits every finite budget dimension;
- one epoch cannot record a second selection or output after preemption/expiry;
- one endogenous consumer cannot own multiple active epochs;
- foreground events at or before an epoch's causal cut cannot preempt it;
- preempted, expired, and intent-abandoned partial scans advance recovery past
  the canonical scan trigger;
- an unchanged or expired inquiry cannot mint a later-cut activity;
- replay uses the pinned agenda selector and rejects unknown versions;
- a crash before checkpoint advancement cannot duplicate logical outputs or
  spend budget twice;
- peer disagreement preserves both evidence sets and assumptions;
- foreground work durably preempts DREAM without erasing its evidence; and
- architecture tests prevent the endogenous core and worker from reaching
  models, work dispatch, capabilities, authorization, or effects.

The implementation is described in
[Endogenous Cognition](../ENDOGENOUS_COGNITION.md).
