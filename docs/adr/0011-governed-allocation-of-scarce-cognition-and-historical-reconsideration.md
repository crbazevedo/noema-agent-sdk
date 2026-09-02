# ADR 0011: Governed allocation of scarce cognition and historical reconsideration

- Status: Accepted — deterministic v0.6.1 shadow foundation implemented;
  learned allocation remains staged
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
    --current-basis/current-world revalidation-->
new cognition
```

This is reconsideration, not resumption. It treats history as evidence and a
source of candidates while requiring a fresh authorized current basis for every
new cognitive allocation. That basis may come from live governing intent or a
separately explicit standing mandate for bounded reconsideration.

Cognition is also scarce. The limiting resources include compute, wall time,
money, user attention, interruption, privacy exposure, and the opportunity cost
of displacing other thought. A future learned allocator may improve estimates
of outcomes and costs, but it must not infer sovereign values, manufacture
intent, or weaken hard constraints.

The deterministic v0.6.1 contracts, allocator, events, projection, and shadow
worker described below are implemented. Learned estimators, exploration,
training, and active allocation remain staged.

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

A historical item may seed new cognition only after revalidation against the
current canonical world, current cognitive basis, current information policy,
and current cognitive budget. The v0.6.1 implementation creates a distinct
`ReconsiderationCandidate` and shadow proposal with a new causal cut and
allocation decision; it does not generalize or resume the stored v0.6 inquiry.
The historical item remains immutable provenance.

Fulfilled, cancelled, and failed goals cannot re-authorize cognition merely
because they once governed it. Their evidence may contribute to new cognition
only when independently relevant to a separately current cognitive basis.

### Require a current cognitive basis

The v0.6.1 foundation permits two—and only two—sources of cognitive basis:

```text
CurrentCognitiveBasis
    = LiveGoverningIntent
      OR ExplicitReconsiderationMandate

ReconsiderationMandate
    != Goal
    != Commitment
    != WorkOrder
    != EffectAuthority
```

`LiveGoverningIntent` means current `ACTIVE` intent or legitimate recovery-
oriented `BLOCKED` intent. `ExplicitReconsiderationMandate` is user- or
constitutionally authorized permission for bounded meta-cognition when no live
goal independently supplies the basis. It carries at least:

- scope;
- permitted candidate classes and domains;
- a multidimensional budget;
- cadence or trigger conditions;
- expiry;
- maximum interruption;
- surfacing policy; and
- information-use policy.

Within those bounds, a mandate may authorize historical inspection, current-
world revalidation, reconsideration-value estimation, candidate formation, and
preparation of a question or proposal. It cannot reactivate an old goal,
manufacture a terminal goal, accept a commitment, dispatch work, or execute an
effect.

```text
historical cognition regains cognitive eligibility
    iff live governing intent
        OR an explicit standing reconsideration mandate
```

The historical goal never supplies that authority. A mandate only permits
bounded cognition and surfacing; every goal, commitment, work, and effect
transition remains separately admitted.

The implemented v0.6 rule remains unchanged: endogenous inquiries require an
exact current `ACTIVE` or `BLOCKED` governing goal revision. The mandate is an
accepted v0.6.x architecture boundary, not a claim about current runtime
behavior.

### Preserve semantic and authority boundaries

```text
UserValue
    != ValueAlignmentEstimate
    != ExpectedOutcomeValue

Preference
    != MotivationEstimate
    != Intent
    != Commitment

MotivationEstimate != authority

MotivationEstimate != Commitment

Epistemic contradiction != goal conflict

ReconsiderationCandidate
    != Inquiry
    != Goal
    != WorkOrder
    != ActionIntent
```

`UserValue` is comparatively durable evidence of which outcomes or principles
matter. `ValueAlignmentEstimate` evaluates how strongly a candidate aligns
with that evidence. `ExpectedOutcomeValue` estimates the contribution of
cognition to a particular outcome. None is a scalar sovereign utility, and none
may silently substitute for another.

`Preference` is a scoped comparative tendency. `MotivationEstimate` is dynamic
evidence of current activation toward an outcome. It carries evidence,
confidence, provenance, and valid/fresh intervals. Its evidentiary standing is:

```text
Explicit
    > VoluntaryReengagement
    > RepeatedInterest
    > Inferred
```

This ordering is not authority. Low motivation may suppress discretionary
resurfacing but cannot cancel an obligation. Intent identifies an outcome the
user or another authorized principal currently governs. Commitment makes a
bounded obligation durable. Motivation is neither.

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

### Make future allocation evidence identifiable

A future implementation records an architectural `CognitiveAllocationTrace`
for every candidate reaching allocation. This is a staged evidence contract,
not an implemented runtime class. It preserves:

- the candidate and immutable historical provenance;
- the complete feature snapshot;
- every hard-gate outcome;
- policy and estimator identities and versions;
- the budget snapshot;
- one allocation label and its causal reason or binding constraint; and
- selection probability or other behavior-policy evidence when applicable.

The allocation label is exactly one of:

```text
SELECTED
DEFERRED_BY_CONSTRAINT
SUPPRESSED
EXPLICITLY_REJECTED
```

Subsequent evidence is linked without rewriting the allocation decision. It may
include user response, voluntary revisit, decision change, goal or commitment
conversion, completion, correction, interruption cost, regret, or missed
opportunity.

```text
learned causal ranking requires identifiable selection data
```

A future learner may rely on logged behavior-policy propensities, separately
authorized bounded experimentation, or another defensible counterfactual
design. It may never train on the shortcut “selected = good, unselected = bad.”
Active exploration for high-stakes, identity-bound, or relationship-sensitive
resurfacing is prohibited unless separately authorized. This ADR selects no
bandit, reinforcement-learning, or exploration algorithm.

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
available. Its evaluation must use identifiable `CognitiveAllocationTrace`
evidence rather than naive selected/unselected labels. Shadow disagreement is
evidence, not authority to self-promote.

### Preserve the four distinct developmental questions

```text
Endogenous Cognition:
    what deserves thought now?

Historical Reconsideration:
    what may deserve thought again?

Governed Allocation:
    which eligible thought deserves scarce cognition now?

Habit Learning:
    what has earned the right not to require deliberation anymore?
```

Together these form the longer-term Governed Allocation of Scarce Cognition
architecture. Reconsideration prevents useful history from being forgotten;
Habit Learning prevents proven repetition from consuming needless deliberation;
Endogenous Cognition keeps current unmet cognitive demand visible; and Governed
Allocation decides which eligible demand fits current constraints and budget.

```text
Governed Allocation of Scarce Cognition
    ⊃ Learned Allocation of Scarce Cognition
```

Learning may improve estimation and ranking inside the governed envelope. It is
never the envelope itself.

## Consequences and tradeoffs

- Historical work remains useful without recovering obsolete authority.
- A standing mandate allows dormant possibilities to be reconsidered when the
  live agenda is empty, but its explicit scope, budget, expiry, interruption,
  surfacing, and information-use bounds prevent it from becoming ambient intent.
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
- Identifiable allocation traces increase telemetry and governance cost, but
  prevent a future learner from confusing policy selection with causal value.

## Rejected alternatives

- **Resume every unresolved historical inquiry:** revives stale intent and
  confuses prior selection with current authority.
- **Discard historical cognition when its goal closes:** destroys useful
  evidence and makes repeated thought more expensive.
- **Require live intent for every reconsideration:** prevents bounded discovery
  precisely when the active agenda is empty; an explicit mandate supplies only
  cognitive eligibility, never goal or effect authority.
- **Learn one scalar user utility:** collapses value, preference, motivation,
  intent, and authority into an opaque optimization target.
- **Let learned scores precede hard gates:** permits optimization pressure to
  erode intent, privacy, safety, authority, and user agency.
- **Treat non-selection as negative feedback:** mislabels budget and constraint
  effects as evidence about value.
- **Train only on selected examples:** confounds the behavior policy with
  outcome value and makes causal ranking unidentifiable.
- **Reuse all operational traces for learning:** violates purpose limitation
  and creates a second, weakly governed information path.

## Deferred decisions

The v0.6.x implementation substrate is not authorized by this ADR. Deferred
work includes event and projection contracts, candidate generation, outcome
instrumentation, counterfactual estimators, model selection, exploration
policy, active-learning strategy, calibration thresholds, training pipelines,
feature stores, learned allocator deployment, and user-facing resurfacing UX.

No bandit, reinforcement-learning, propensity-estimation, or experimentation
algorithm is selected. High-stakes, identity-bound, and relationship-sensitive
exploration remains prohibited unless a separate authority decision explicitly
permits it.

This ADR does not authorize RDDL/MDP/RL scheduling, HabitForge, SkillForge,
endogenous work dispatch, new effect paths, external connectors, or production
training on governed information.

## Required fitness functions

- terminal historical goals cannot authorize new cognition;
- every reconsideration cites either current live governing intent or an
  unexpired, scope-matching explicit reconsideration mandate;
- mandate-based cognition fails closed outside its candidate domain, budget,
  cadence/trigger, interruption, surfacing, or information-use bounds;
- a reconsideration mandate cannot create or reactivate goals, accept
  commitments, dispatch work, grant effect authority, or execute effects;
- user value, value alignment, expected outcome value, preference, motivation,
  intent, and commitment remain separately evidenced;
- motivation estimates retain confidence, provenance, and temporal validity;
  explicit evidence outranks weaker behavioral inference, and low motivation
  cannot cancel an obligation or grant authority;
- every reconsidered item cites immutable historical provenance and a fresh
  current causal cut;
- `RECONSIDER` creates new cognition and never mutates or resumes old lifecycle
  state;
- epistemic contradiction cannot be interpreted as goal conflict without an
  explicit strategic relation;
- all selected cognition fits every hard resource dimension;
- positive `NetVOC` establishes eligibility only;
- `SELECTED`, `DEFERRED_BY_CONSTRAINT`, `SUPPRESSED`, and
  `EXPLICITLY_REJECTED` remain distinct labels;
- each `CognitiveAllocationTrace` pins features, hard gates, policy and
  estimator versions, budget, causal reason, and applicable behavior-policy
  evidence;
- subsequent response and outcome evidence links to rather than mutates its
  allocation trace;
- causal learning rejects datasets without identifiable selection evidence;
- active exploration for high-stakes, identity-bound, or relationship-sensitive
  resurfacing fails closed without separate authorization;
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
