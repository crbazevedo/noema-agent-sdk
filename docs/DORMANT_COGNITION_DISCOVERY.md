# Dormant Cognition Discovery and Evidence Qualification

Noema v0.6.2 implements the smallest deterministic bridge from historical
`Inquiry` records to the v0.6.1 reconsideration allocator. It discovers only
historical inquiries, remains model-free, and can produce at most a shadow
proposal.

The normative allocation architecture remains
[ADR 0011](adr/0011-governed-allocation-of-scarce-cognition-and-historical-reconsideration.md).
This slice implements a staged dependency already anticipated there; it does
not reopen the accepted decision.

## Boundary

```text
canonical historical Inquiry
    -> derived DormantInquiryDescriptor
    -> deterministic relevance trigger
    -> immutable ReconsiderationOpportunity
    -> deterministic ReconsiderationSeed
    -> existing v0.6.1 allocator
    -> at most ReconsiderationShadowProposal
```

The stages are deliberately non-substitutable:

```text
DormantInquiry
    != ReconsiderationOpportunity
    != ReconsiderationSeed
    != ReconsiderationCandidate
    != Inquiry
    != Goal
    != WorkOrder
    != ActionIntent

Discovery != Revalidation != Allocation != Surfacing
```

Discovery says that enough current, deterministic reason exists to spend a
bounded revalidation cost. It does not establish positive value of cognition,
restore historical authority, allocate resources, or authorize an effect.

## Projection-only dormancy

`DormantInquiryIndex` is a disposable complement of
`EndogenousProjection.eligible_inquiries(at=t)`. It never emits a dormancy
event. Its descriptor explains stale or terminal governing intent, expiry, the
historical DREAM state, and the last reconsideration cut without redefining
v0.6 eligibility.

Dormancy supplies neither relevance nor authority. Agenda slack is only a hard
gate. The deterministic detector needs one target-specific reason:

- explicit user reengagement;
- an explicit relevance signal;
- an opened opportunity window;
- reactivation of the same stable goal lineage;
- a currently qualified persistent value; or
- a changed allocation context for a previously constraint-deferred candidate.

Cadence, elapsed time, an unrelated event, idle capacity, and a generic user
value create no opportunity. Structured trigger `target_refs` are identifiers;
the detector never infers targets or domains from prose.

Autonomic `rule.evaluation_traced` events may be evidence only when their typed
signal is active, target-specific, from the exact canonical rule/version, and
of a policy-permitted kind. Signal salience, urgency, and expected value never
become reconsideration features or allocation scores.

## Memory-owned evidence

Evidence remains ordinary persistent memory. A current `SemanticAssertion`
owns confidence, bitemporal validity, freshness, provenance, supersession, and
contradiction semantics. The thin `EvidenceQualificationBinding` adds only a
role, target, authenticated qualifier/version, governance lineage, and binding
time.

The supported roles are:

```text
CURRENT_REVALIDATION
DURABLE_VALUE
PREFERENCE
MOTIVATION
OPPORTUNITY
EXPECTED_OUTCOME_VALUE
```

`EXPECTED_OUTCOME_VALUE` is an ex ante estimate, not a realized outcome. A
durable value, value-alignment estimate, expected outcome value, preference,
and motivation remain separate concepts. Value alignment, motivation, and
expected outcome value require distinct assertions before a new seed can be
assembled. Missing or ambiguous qualification yields no seed; the discovery
worker cannot manufacture subjective evidence to justify its own nomination.

A current qualification assertion may derive from older durable evidence. The
old assertion retains its original timestamp and remains reachable through
provenance, while the new assertion and role binding prove current,
target-specific applicability. Volatile and ex ante roles require post-Inquiry
evidence and current validity.

## Scope and Information Governance

`InquiryReconsiderationScopeBinding` supplies the domain and governed-
information mapping absent from the historical inquiry schema. It is
authenticated and immutable. Exactly one intersection with the mandate's
allowed domains is required; zero is out of scope and multiple matches fail
closed. The worker never parses mandate scope or inquiry text.

Scope bindings, qualification bindings, and opportunities receive opaque
information identities, exact derived lineage, inherited policy bindings, and
current `REASON` access decisions. Permission for current cognition does not
grant later training or evaluation use.

## Two causal cuts

Every opportunity separates:

```text
evaluation_cut = canonical trigger sequence
admitted_at_head = actual predecessor accepted by exact-head CAS
```

Dormancy and reasons replay through the evaluation cut. At admission and
handoff, the worker rechecks current cognitive basis and mandate, exact scope,
foreground slack, candidate disposition, and information access. The durable
event requires only that its stored sequence is greater than the validated
predecessor, so PostgreSQL sequence gaps are legal. Opportunity identity uses
semantic causal inputs, not wall-clock delay or admission-head numbering.

## Seed handoff and reallocation

For `NEW_REVALIDATION`, a version-pinned assembler builds the existing v0.6.1
`ReconsiderationSeed` from the historical inquiry, opportunity, scope, current
qualified assertions, and governance state. It does not alter candidate or
scan identity and does not fabricate critical features.

For `REALLOCATE_EXISTING`, the candidate must never have been selected, its
latest disposition must be `DEFERRED_BY_CONSTRAINT`, its basis and feature
evidence must remain valid, and budget, interruption, foreground, or allocation
policy context must have materially changed. The same candidate and original
seed are reused.

## Replay, recovery, and outcomes

Discovery state consists of immutable policy, scope, qualification, and
opportunity events on the canonical log. Content-addressed identities,
exact-head admission, and the generic `ConsumerCheckpoint` make retries and
partial-boundary recovery converge exactly once. Checkpoints accelerate replay
but cannot hide incomplete material triggers.

`CognitiveAllocationOutcomeLink` now accepts a downstream outcome only when the
outcome event's canonical sequence follows the allocation trace and its
timestamps are causally coherent. Linking an old event later cannot transform
it into a subsequent outcome.

## Deliberate deferrals

v0.6.2 does not add learned allocation, LLM relevance, embeddings, automatic
subjective-value inference, bandits or reinforcement learning, propensity
estimation, generated habits or skills, generic profiles, non-Inquiry history,
automatic goals, notifications, effects, or a scheduler.
