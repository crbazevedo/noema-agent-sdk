# ADR 0011: Governed allocation of scarce cognition and historical reconsideration

- Status: Accepted architecture direction; implementation staged
- Date: 2026-09-01
- Scope: historical reconsideration, scarce-cognition allocation, learned
  outcome estimation, information-use governance, and authority boundaries

## Context

The deterministic v0.6 Endogenous Cognition slice can answer a bounded version
of “what deserves thought now?” from current goals, commitments, beliefs,
signals, and peer evidence. It deliberately does not decide whether old
cognition should return, learn a user's terminal utility, or allocate active
cognition with a learned policy.

Long-lived agents accumulate unresolved inquiries, abandoned simulations,
superseded plans, negative findings, deferred questions, and cognition produced
under goals that later complete, fail, or are cancelled. Erasing that history
wastes information. Resuming it blindly lets obsolete intent recover authority.
The architecture needs a third path:

```text
historical cognition
    --current-intent/current-world revalidation-->
new cognition
```

This is reconsideration, not resumption. It treats history as evidence and a
source of candidates while requiring a fresh causal basis for every new
cognitive allocation.

Cognition is also scarce. The limiting resources include compute, wall time,
money, user attention, interruption, privacy exposure, and the opportunity cost
of displacing other thought. A future learned allocator may improve estimates
of outcomes and costs, but it must not infer sovereign values, manufacture
intent, or weaken hard constraints.

The names in this ADR describe architectural roles and boundaries. They are not
claims that runtime models, classes, allocators, or events are implemented.

## Decision

### Historical cognition loses authority, not informational value

Historical cognition remains durable evidence. Its former governing goal,
priority, selection, commitment, or DREAM allocation is not current authority.

```text
RECONSIDER != RESUME

old selection != current selection
old intent basis != current intent basis
old authority != current authority
```

A historical item may seed a new inquiry only after revalidation against the
current canonical world, current live intent, current information policy, and
current cognitive budget. The new inquiry receives a new causal cut and a new
allocation decision. The historical item remains immutable provenance.

Fulfilled, cancelled, and failed goals cannot re-authorize cognition merely
because they once governed it. Their evidence may contribute to a new inquiry
only when independently relevant to current `ACTIVE` or legitimate recovery-
oriented `BLOCKED` intent.

### Preserve semantic and authority boundaries

```text
Value != Preference != Motivation != Intent != Commitment

Motivation != authority

Epistemic contradiction != goal conflict

ReconsiderationCandidate
    != Inquiry
    != Goal
    != WorkOrder
    != ActionIntent
```

Value describes an evaluated contribution to an outcome. Preference describes
a user's observed or declared comparative tendency. Motivation describes a
reason cognition may be worth considering. Intent identifies an outcome the
user or an authorized principal currently governs. Commitment makes a bounded
obligation durable. None can be inferred merely from the presence of another.

An epistemic contradiction is competing evidence about a proposition. A goal
conflict is incompatibility among desired outcomes or constraints. The former
may motivate inquiry, but it does not prove the latter or authorize a change in
intent.

A reconsideration candidate is only a proposal to inspect historical cognition
under current conditions. It is not yet a current inquiry, goal, work order, or
action proposal. Each downstream transition remains separately governed.

### Allocate one layered cognitive demand under explicit scarcity

Future allocation observes one demand portfolio:

```text
cognitive demand
    = foreground demand
    + current endogenous demand
    + reconsideration demand
```

Foreground demand remains preemptive where current runtime policy grants it.
Current endogenous demand is grounded in the present situation. Reconsideration
demand begins with historical evidence but must earn a fresh current basis.

The scarce cognitive budget includes at least:

- compute;
- wall time;
- monetary cost;
- user attention;
- interruption;
- privacy exposure; and
- opportunity cost.

These dimensions are not interchangeable by default. A low-compute item can
still be too intrusive, privacy-expensive, or costly in displaced attention.

### Start with deterministic reconsideration

Before learned active allocation, a deterministic policy must expose and record
the features and costs that make reconsideration eligible. Candidate features
include:

- value alignment;
- preference fit;
- motivation;
- portfolio coherence;
- clarity;
- resolvability;
- feasibility;
- meaningful new evidence;
- regret of silence;
- opportunity-window value; and
- residual unresolvedness.

Explicit costs include:

- compute;
- revalidation;
- attention;
- context switching;
- intrusion;
- privacy/risk; and
- opportunity cost.

The deterministic policy pins feature definitions, weights, thresholds,
budget, information policy, causal cursor, and evaluation time. Positive
`NetVOC` means eligible, not mandatory. Eligibility does not bypass portfolio
constraints, preemption, information governance, user-agency boundaries, or
later admission gates.

Selection labels retain their causal meaning:

```text
not selected != negative evidence

deferred by constraint != rejected
```

Budget exhaustion, a higher-value portfolio, an unavailable prerequisite, or a
privacy gate says nothing by itself about the candidate's underlying merit.
Training and evaluation data must preserve those distinctions.

### Learn outcome vectors, not sovereign terminal utility

Learned estimators may estimate observable outcomes and costs. They do not
learn, replace, or optimize a scalar sovereign user utility. The future learned
output is an inspectable outcome vector such as:

```text
P(still matters)
P(changes decision)
E[delta goal value]
P(resolvable)
P(user wants resurfacing)
E[attention cost]
E[revalidation cost]
E[intrusion cost]
E[regret if ignored]
```

Policy combines this vector only after current hard constraints are satisfied.
Hard intent, authority, information-access, safety, and user-agency constraints
precede learned scores. A learned estimate cannot create a goal, revive intent,
grant authority, authorize disclosure, or turn competence into permission.

### Govern allocation features and learning corpora independently

Information Governance applies both when cognition is allocated and when its
traces are reused for training, calibration, counterfactual evaluation, or
benchmarking.

```text
permitted for current cognition
    != automatically permitted for learning
```

Every feature, label, historical trace, model input, model output, evaluation
artifact, and derived corpus retains policy lineage. Current access or
disclosure permission for an operational decision does not silently authorize
secondary learning use. Declassification, retention, deletion, purpose,
locality, provider, and cross-agent constraints remain independently enforced.

Learned allocation therefore consumes only explicitly permitted projections of
canonical traces. The event store remains the durable source of truth; training
sets, feature stores, indexes, and estimator artifacts are governed derived
views, never a second authority.

### Stage learning behind deterministic evidence

The research and delivery order is:

```text
deterministic allocation
    → allocation/outcome traces
    → calibrated estimators
    → counterfactual evaluation
    → shadow learned allocation
    → bounded active allocation
```

Active learned allocation requires evidence that calibration holds under
distribution shift, protected groups and purposes remain governed, resource
budgets remain hard, and deterministic fallback/replay semantics remain
available. Shadow disagreement is evidence, not authority to self-promote.

### Preserve the three-way developmental duality

```text
Endogenous Cognition:
    what deserves thought now?

Reconsideration:
    what deserves thought again?

Habit Learning:
    what no longer deserves deliberation?
```

Together these form the longer-term Governed / Learned Allocation of Scarce
Cognition architecture. Reconsideration prevents useful history from being
forgotten; Habit Learning prevents proven repetition from consuming needless
deliberation; Endogenous Cognition keeps current unmet cognitive demand visible.

## Consequences and tradeoffs

- Historical work remains useful without recovering obsolete authority.
- Revalidation adds compute and latency before historical cognition can compete,
  but that cost is the mechanism that prevents blind resumption.
- A vector of outcome estimates is more complex than one learned score, but
  preserves inspectability and prevents accidental claims of learned sovereign
  utility.
- Deterministic features may initially miss subtle relevance. The accepted
  bias is toward false negatives and silence until traces support calibrated
  estimators.
- Separate information-use permission for learning reduces available training
  data, but prevents operational access from becoming an unlimited secondary-
  use license.
- Portfolio non-selection is censored evidence. Counterfactual evaluation must
  account for it rather than treating absent outcomes as failures.

## Rejected alternatives

- **Resume every unresolved historical inquiry:** revives stale intent and
  confuses prior selection with current authority.
- **Discard historical cognition when its goal closes:** destroys useful
  evidence and makes repeated thought more expensive.
- **Learn one scalar user utility:** collapses value, preference, motivation,
  intent, and authority into an opaque optimization target.
- **Let learned scores precede hard gates:** permits optimization pressure to
  erode intent, privacy, safety, authority, and user agency.
- **Treat non-selection as negative feedback:** mislabels budget and constraint
  effects as evidence about value.
- **Reuse all operational traces for learning:** violates purpose limitation
  and creates a second, weakly governed information path.

## Deferred decisions

The v0.6.x implementation substrate is not authorized by this ADR. Deferred
work includes event and projection contracts, candidate generation, outcome
instrumentation, counterfactual estimators, model selection, exploration
policy, active-learning strategy, calibration thresholds, training pipelines,
feature stores, learned allocator deployment, and user-facing resurfacing UX.

This ADR does not authorize RDDL/MDP/RL scheduling, HabitForge, SkillForge,
endogenous work dispatch, new effect paths, external connectors, or production
training on governed information.

## Required fitness functions for a future implementation

- terminal historical goals cannot authorize new cognition;
- every reconsidered item cites immutable historical provenance and a fresh
  current causal cut;
- `RECONSIDER` creates new cognition and never mutates or resumes old lifecycle
  state;
- epistemic contradiction cannot be interpreted as goal conflict without an
  explicit strategic relation;
- all selected cognition fits every hard resource dimension;
- positive `NetVOC` establishes eligibility only;
- non-selection, constraint deferral, rejection, and negative outcome remain
  distinct labels;
- learned estimators emit a versioned outcome vector, not a terminal utility;
- current intent, authority, safety, information access, and user-agency gates
  run before learned ranking;
- operational-use permission cannot authorize learning use;
- training and evaluation artifacts retain policy and lineage through deletion,
  declassification, provider, locality, and purpose changes;
- shadow learned allocation cannot promote itself to active control; and
- canonical replay reconstructs the same deterministic candidate and allocation
  state from the same policy, causal cut, and evidence.

Delivery order and milestone status are recorded in the
[roadmap](../ROADMAP.md). The architectural synthesis and staged principles are
recorded in [Architecture](../ARCHITECTURE.md) and
[Architecture principles](../ARCHITECTURE_PRINCIPLES.md).
