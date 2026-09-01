# Endogenous Cognition

Noema v0.6 implements the smallest deterministic, shadow-first mechanism by
which useful cognition can begin without an external prompt. It discovers
grounded questions, prices them under an explicit policy, selects a feasible
background agenda, and preserves the result for replay. It does not perform the
selected cognition as durable work and cannot produce an external effect.

The normative decision is [ADR 0010](adr/0010-endogenous-cognition.md). The
longer-term design remains in
[Endogenous Drive Ecology](ENDOGENOUS_DRIVE_ECOLOGY.md).

## Boundary

```text
Signal != Inquiry != IntrinsicActivity != WorkOrder != ActionIntent

governing intent → bounded cognitive demand → shadow agenda
                                         no dispatch ─┘
                                         no effects  ─┘
```

- `Signal` says a rule cell noticed something.
- `Inquiry` asks a provenance-bearing question.
- `IntrinsicActivity` estimates a bounded way to think about that question.
- `WorkOrder` is admitted durable execution, which v0.6 never creates.
- `ActionIntent` is an effect proposal, which v0.6 never creates.

Every inquiry and activity names exact current governing goal revisions.
`ACTIVE` and `BLOCKED` intent may justify cognition; `COMPLETED`, `FAILED`, and
`CANCELLED` intent cannot.

## Deterministic lifecycle

```text
EndogenousPolicySnapshot
        +
CognitionScanRequest at canonical cursor H
        ↓
DreamEpoch(consumer, H, policy, selector, budget, expiry, DREAM_PROPOSAL_ONLY)
        ↓
deterministic producers
        ↓
Inquiry → IntrinsicActivity → ValueOfCognitionEstimate
        ↓
IntrinsicAgendaSelection
        ├── selected: positive and fits the budget
        ├── deferred: positive but does not fit
        └── suppressed: expired or non-positive
        ↓
preempted by foreground work or expired by pinned time
```

All durable state derives from canonical events. Content-addressed identities,
exact-head conditional append, replay-time validation, and a shared
`ConsumerCheckpoint` make partial-write recovery idempotent.

## Candidate producers

The deterministic detector emits candidates only from defended state:

| Source | Candidate |
|---|---|
| Current `RoadmapHealth` requires review | goal/roadmap maintenance |
| Active `CommitmentCoverage` is uncovered | goal/roadmap maintenance |
| Current-strategy belief is stale or contradictory | belief maintenance |
| Active autonomic novelty signal | inquiry, with no automatic novelty premium |
| Recorded peer confidence differs materially | peer calibration |

Belief relevance is intentionally exact in v0.6. An assertion subject must
identify a current goal, roadmap, roadmap revision, or commitment. Similarity
and natural-language guesses are not admission evidence.

## Value of Cognition and finite budget

The pinned policy computes:

```text
NetVOC = improvement
       - compute - delay - attention - opportunity - privacy/risk
```

The event records the unweighted inputs, applied weights, resulting terms, and
net value. Selection uses a stable ordering and a multidimensional resource
vector: activity slots, compute units, wall time, attention, and privacy/risk.
The first feasible positive candidates are selected greedily. This is a
deterministic reference policy, not a learned estimate or optimization claim.

Exactly one `IntrinsicAgendaSelection` may exist per DREAM epoch. Unused budget
remains explicit; exhausted dimensions defer later positive candidates. A
consumer may own at most one active epoch, so repeated scans cannot multiply
aggregate cognitive slack. While that epoch remains active, a later scan
deterministically reuses its selection or does no additional work.

The policy and epoch pin `stable-greedy-multidimensional` version 1. Replay
dispatches through that immutable algorithm identity; unknown versions fail
closed instead of being interpreted by whatever selector happens to be current.

## Calibration without consensus collapse

`CalibrationExchange` preserves the local and peer confidences, evidence sets,
assumptions, peer identity, protocol version, and request/response provenance.
Disagreement creates a candidate inquiry; it does not average beliefs, assign
truth by vote, or transfer authority.

## Failure and preemption semantics

- a crash before the scan checkpoint causes replay from the canonical scan;
- already recorded inquiries, activities, estimates, and selection are reused;
- foreground `WorkOrder` or decision demand preempts active DREAM epochs;
- the running worker observes configured foreground events through the existing
  event bus; no manual preemption call or new scheduler is required;
- only foreground events causally after the epoch cut may preempt it;
- preemption, expiry, and intent-loss abandonment are durable terminal states;
- terminal epochs cannot consume more cognition;
- terminal partial scans advance the generic checkpoint and cannot become
  poison scans during recovery;
- unchanged evidence and intent do not renew an unresolved inquiry or allocate
  another activity, and expired inquiries cannot be silently reopened;
- old DREAM evidence remains inspectable after preemption;
- a goal becoming terminal prevents later admission against that intent.

## What remains deferred

v0.6 does not implement LLM generation, learned value weights, RDDL/MDP/RL or
solver scheduling, adaptive oversight, runtime information-gain estimation,
generated habits or skills, endogenous work dispatch, a generalized workflow
language, real external connectors, or a self-triggering scheduler.

The milestone proves that durable machinery can own cognitive initiative while
models, work coordination, and effect authority remain replaceable downstream
concerns.
