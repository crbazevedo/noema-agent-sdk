# Deterministic Cognitive Reconsideration

Noema v0.6.1 implements the smallest replay-safe path by which one historical
`Inquiry` may become worth thinking about again. It preserves the v0.6 rule
that canonical `Inquiry` and `IntrinsicActivity` require exact current
`ACTIVE` or `BLOCKED` goal revisions. Mandate-based reconsideration uses a
separate shadow path and does not manufacture a goal-bound inquiry.

The normative architecture is [ADR 0011](adr/0011-governed-allocation-of-scarce-cognition-and-historical-reconsideration.md).

## Boundary

```text
historical Inquiry
    + CurrentCognitiveBasis
        ├── exact live governing intent
        └── explicit ReconsiderationMandate
    + current-world evidence
    + current Information Governance permission
        ↓
ReconsiderationCandidate
        ↓
deterministic scarce-cognition allocation
        ↓
CognitiveAllocationTrace
        ↓
shadow question proposal
```

These contracts cannot substitute for one another:

```text
ReconsiderationCandidate
    != Inquiry
    != Goal
    != Commitment
    != WorkOrder
    != ActionIntent
```

The reconsideration core and worker cannot import strategic mutation, durable
work, capability, authorization, model, or effect paths. Architecture tests
make that boundary structural.

## Conservative compatibility choice

v0.6.1 does not replace `GoverningIntentRef` in stored v0.6 events. Existing
inquiry identity, schema, fixtures, replay, and selector semantics are
unchanged. A mandate-based selection emits only reconsideration events and a
`ReconsiderationShadowProposal`. A future schema-versioned migration may
generalize the type hierarchy, but this milestone does not require it.

Live-intent reconsideration supports only a deterministic same-stable-goal
lineage relation. It does not infer relevance from prose or semantic
similarity. Mandate scope supplies cognitive eligibility, not outcome ownership
or authority to act.

## Mandate lifecycle

An immutable `ReconsiderationMandate` revision records an authenticated user or
constitutional issuer, canonical authorization evidence, candidate class and
domain scope, a multidimensional budget, cadence and triggers, issuance and
expiry, interruption ceiling, shadow surfacing policy, and information-use
purpose and policy lineage. Revocation is a separate canonical event.

An active mandate must be current, canonical, unrevoked, unexpired, within
cadence and trigger bounds, scope-matching, interruption-safe, and supported by
current allowed Information Governance decisions. It can authorize historical
inspection, revalidation, feature/cost estimation, allocation, and a shadow
question. It cannot create or reactivate a goal, accept a commitment, dispatch
work, create an action intent, invoke a capability, or grant effect authority.

Mandate admission uses an injected authentication port and exact-head compare-
and-append. Replay checks the durable authority receipt and the actual preceding
canonical head; it does not assume sequence numbers are contiguous.

## Historical provenance and idempotence

The first and only source class is historical `Inquiry`. Each candidate cites:

- the immutable inquiry, DREAM epoch, original causal cut, governing intent,
  and evidence;
- governed information identities and their current allowed `REASON`
  decisions;
- a fresh scan causal cut and explicit current-world evidence; and
- the current live-intent or mandate basis.

The old inquiry and goal never return to current state. Candidate identity is
derived from historical provenance, current basis, domain, current evidence,
features, and costs—not elapsed time. An unchanged rescan reuses the existing
candidate and allocation. Changed evidence or basis can form a new candidate.

## Features, costs, and deterministic allocation

Mechanical features include unresolvedness, freshness, new evidence,
opportunity-window value, and current-basis validity. Value alignment,
expected outcome value, and motivation remain separate optional estimates.
Every present estimate carries evidence kind, confidence, provenance, and a
valid interval. Unknown critical estimates fail closed as `SUPPRESSED` rather
than receiving fabricated scores.

The v0.6.1 budget is separate from the stored v0.6 resource vector and covers:

```text
compute, wall time, money, attention, context switching, intrusion, interruption,
privacy exposure, opportunity cost, and revalidation
```

The version-pinned `stable-greedy-reconsideration` v1 policy calculates
explicit expected benefit and cost terms, orders candidates with a stable
tie-break, and admits only a subset that fits every hard dimension. Positive
NetVOC means eligible, not mandatory. Foreground demand defers otherwise
positive candidates.

Each decision uses exactly one label:

```text
SELECTED
DEFERRED_BY_CONSTRAINT
SUPPRESSED
EXPLICITLY_REJECTED
```

The deterministic worker does not synthesize `EXPLICITLY_REJECTED` or behavior-
policy probabilities. Those remain explicit future evidence, not inferred
counterfactual labels.

## Trace, replay, and recovery

Every allocated candidate receives an immutable `CognitiveAllocationTrace`
containing provenance, basis, features, costs, hard gates, policy and estimator
versions, budget, label, causal reason, and binding constraint. Later outcome
evidence is appended as `CognitiveAllocationOutcomeLink`; it never rewrites the
original trace.

All durable state rebuilds from the canonical event log. Scan inputs include
the information decisions, evidence, features, and costs needed for recovery.
Content-addressed outputs and the generic `ConsumerCheckpoint` make replay
idempotent after partial writes. No private cursor or scheduler is introduced.

## Deliberate deferrals

v0.6.1 does not implement learned allocation, model-based relevance, LLM
reflection, contextual bandits, reinforcement learning, exploration,
propensity estimation, counterfactual training, a feature store, a training
pipeline, generated habits or skills, automatic goal creation, arbitrary
historical-object reconsideration, notification UX, durable work, or effects.
