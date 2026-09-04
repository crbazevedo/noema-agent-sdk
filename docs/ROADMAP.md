# Noema roadmap: increasing agency

> **Roadmap ID:** `noema-core`
>
> **Current revision:** 2026-09-04
>
> **Status:** `main` implements v0.1 through the deterministic v0.6.2 Dormant
> Cognition Discovery foundation and Information Governance; ADR 0012 is an
> accepted direction, and the current feature branch contains a v0.6.3
> learning-grade attention-telemetry implementation candidate. A qualifying
> real corpus does not yet exist, so runtime Habit Learning remains blocked.

Noema is infrastructure for agents that maintain a coherent relationship with
a changing world. Its releases should therefore tell a story of increasing
agency, not merely group engineering features.

The project thesis is:

> Useful long-lived agency emerges not from keeping a reasoning model running,
> but from giving intelligence a durable architecture for memory, situation,
> attention, intent, work, authority, and development.

The program is now explicitly aimed at **durable developmental agency**:

> **Run my work. Improve my decisions. Help me improve.**

Sentinel, chief-of-staff, thought-partner, technical-mentor,
development-coach, and epistemic-steward behavior are application functions,
not SDK personas. Noema supplies the general mechanisms applications need to:

- build a persistent agent and reconstruct its current world;
- start bounded background cognition while preserving current intent;
- represent governed advisory and developmental interventions;
- connect real environments without moving policy into connectors;
- learn repetitive cognition without authority inflation;
- evaluate model, prompt, tool, retrieval, and policy configurations
  reproducibly;
- recover under crash and distribution; and
- build application-specific companions without contaminating core semantics.

## How to read this roadmap

Release nodes are **outcome thresholds**, not task queues. They describe what
Noema must become able to do. Only an explicit project commitment authorizes
the creation of implementation work.

```text
project goal → roadmap revision → project commitment → implementation work
```

The future runtime architecture will make that distinction a domain invariant:

```text
Goal/GoalRevision != Roadmap/RoadmapRevision != Commitment
                  != WorkOrder != WorkGraph != ActionIntent
```

Until that event-sourced roadmap machinery exists, this file is the current
human-readable projection and Git history preserves its earlier revisions.
Later runtime revisions must be immutable and explicitly supersede their
predecessors rather than mutating history.

Status terms in this document mean:

- **Implemented:** present in the repository and covered by acceptance tests;
- **Accepted direction; implementation staged:** approved architecture and
  dependency order whose runtime contracts are not implemented yet;
- **Planned:** an outcome and acceptance direction whose contracts may still
  change;
- **Beyond v1.0:** intentionally excluded from the stable core milestone.

The v0.6.3, v0.6.4, and v0.7.x labels below express the proposed dependency
sequence. Their exact numbering remains provisional until their respective
architecture decisions are accepted.

Security, observability, deterministic replay, and local operation are
cross-cutting release gates, not a final wave.

## The version story

| Release | Outcome | Voice | Status |
|---|---|---|---|
| **v0.1 — Agency Kernel** | An autonomous agent can have a causal life beyond one model invocation. | **I can act.** | Implemented |
| **v0.2 — Durable Runtime** | Agency survives processes, providers, and machines without changing semantics. | **I survive.** | Implemented |
| **v0.3 — Persistent Cognition** | The agent remembers what happened, what it believes, and why. | **I remember.** | Implemented |
| **v0.4 — Situated Continuity** | The agent knows when memory is no longer sufficient and reconstructs orientation. | **I wake and know what I no longer know.** | Implemented |
| **v0.5 — Durable Work Coordination** | Goals can become dependency-aware, recoverable, verified work. | **I organize work.** | Implemented |
| **v0.5.x — Intent & Outcome Stewardship** | Work remains connected to revisable commitments and the user's actual outcomes. | **I know what I owe, whom it serves, and what should remain human.** | Deterministic slice implemented in v0.5.1 |
| **v0.6 — Endogenous Cognition** | Useful cognition can begin without an external prompt. | **I know what is worth thinking about.** | Deterministic shadow slice implemented |
| **v0.6.1 — Deterministic Cognitive Reconsideration** | Historical inquiries can be revalidated under current intent or an explicit mandate and compete for scarce cognitive slack without blind resumption. | **I know what may deserve thought again.** | Deterministic shadow foundation implemented; learned allocation staged |
| **v0.6.2 — Dormant Cognition Discovery & Evidence Qualification** | Durable history can nominate target-specific historical inquiries for governed reconsideration without manual seed assembly. | **I know which dormant thoughts deserve reconsideration.** | Deterministic shadow slice implemented |
| **v0.6.3 — Learning-Grade Attention Telemetry** *(proposed number)* | Real attention opportunities, actual dispositions, outcomes, explicit feedback, and cost form a denominator-complete governed learning corpus. | **I can observe what deserved attention and what happened next.** | Implementation candidate on the current feature branch; real qualifying corpus pending |
| **v0.6.4 — Developmental Intervention Foundation** *(proposed number)* | Applications can represent an intervention aimed at an immediate user outcome and/or long-term agency without taking ownership of terminal values. | **I can help improve a decision without owning it.** | Proposed in ADR 0013; not implemented |
| **v0.7 — Habit Learning** | Repeated reasoning compiles into cheaper governed behavior. | **I learn what no longer needs thought.** | Architecture accepted in ADR 0012; runtime NO-GO pending qualifying real corpus |
| **v0.7.x — Private Cognitive Ecology** *(proposed number)* | Multiple bounded background loops maintain situation, hazards, scenarios, stakeholder effects, epistemic challenges, and developmental hypotheses through one scarce-cognition portfolio. | **I can keep a bounded private watch over what may matter.** | Proposed; not implemented |
| **v0.8 — Situated Presence** | The abstract agent inhabits a real environment through governed perception. | **I live somewhere.** | Planned |
| **v0.9 — Integrated Autonomous Runtime** | All cognitive systems operate together continuously under faults and budgets. | **I can keep going without being babysat.** | Planned |
| **v1.0 — Durable Cognitive Agency** | Developers can build production long-lived agents without inventing another agent operating system around Noema. | **I persist, orient, steward, coordinate, act, and improve over time.** | Planned |

## Dependency arcs

```text
Arc I — coherent existence
Agency Kernel → Durable Runtime → Persistent Cognition → Situated Continuity

Arc II — durable goal pursuit
Situated Continuity → Durable Work Coordination
                     → Intent & Outcome Stewardship
                     → Endogenous Cognition

Cross-cutting before restricted real-world context
Information Governance and Confidential Context

Arc III — cognitive self-regulation and learning
Endogenous Cognition → Cognitive Reconsideration & Allocation
                      → Dormant Cognition Discovery
                      → Learning-Grade Attention Telemetry
                      → Habit Learning → Situated Presence

Arc IV — proof
Situated Presence → Integrated Autonomous Runtime → Durable Cognitive Agency

Arc V — Developmental Partnership (cross-cutting)
Intent & Outcome Stewardship + Persistent Cognition
    → Developmental Intervention Foundation
    → bounded private cognitive ecology
    → application-level advise / challenge / teach / coach / prepare / silence
```

The dependency order is architectural. Calendar versions or parallel research
may overlap, but a later capability cannot bypass an earlier invariant.
Arc III governs cognitive self-regulation and learning: what deserves thought,
what can be reconsidered, and what repeated cognition may safely compress.
Arc V uses those foundations to improve current user outcomes and durable user
agency. It does not grant the SDK a persona, a second user-development control
plane, or ownership of user values.

## Implemented foundations

### v0.1 — Agency Kernel

Question: **Can a system have a causal life beyond one LLM invocation?**

```text
Event → Situation → Deliberation → Intent → Authority
      → Capability → Result → Event
```

Implemented: asynchronous durable events, a queryable situation graph, typed
capabilities, attention-aware deliberation, critics, policy-bounded autonomy,
scheduling, and multi-agent operation.

### v0.2 — Durable Runtime

Question: **Can the same agency survive crashes, scale-out, and provider
substitution?**

```text
single process → durable events → idempotency → crash recovery
               → distributed transport → fenced leases
               → provider-neutral models → observability → deployment parity
```

Implemented: PostgreSQL, transactional outbox/inbox, NATS JetStream, durable
leases and fencing, event upcasting, provider-neutral model and tracing
contracts, replay fixtures, and embedded/distributed parity.

Decisive invariant: **deployment topology does not change cognitive semantics.**

### v0.3 — Persistent Cognition

Question: **Can the agent accumulate a defensible epistemic history?**

```text
occurrence → evidence → assertion → bitemporal belief → contradiction
           → decision-relevant retrieval
```

Implemented: episodic projection, immutable assertions, first-class evidence,
independent valid and knowledge time, preserved contradictions, deterministic
checkpointed projection, disposable lexical retrieval, and the observational
Autonomic Shadow Kernel.

See [Persistent Cognitive Memory](PERSISTENT_COGNITIVE_MEMORY.md),
[Autonomic Fabric](AUTONOMIC_FABRIC.md),
[ADR 0002](adr/0002-autonomic-fabric.md), and
[ADR 0005](adr/0005-persistent-cognitive-memory.md).

### v0.4 — Situated Continuity

Question: **Can the agent safely return to a world that changed while it was
absent?**

```text
sleep → wake → estimate staleness → identify awareness gaps
      → selective sensing → reconcile → orient
```

Implemented: explicit clock semantics, durable awake epochs and source state,
per-wake awareness demand, hazard-based freshness, selective refresh under an
observation budget, bitemporal reconciliation, and a shadow-only orientation
barrier isolated from effects.

Acceptance: after a simulated 65-hour absence, Noema refreshes only four
decision-relevant changed domains, identifies the highest-value issue, remains
explicit when a critical source is unavailable, and performs no consequential
effect. A no-change wake stays silent.

See [Situated Continuity](SITUATED_CONTINUITY.md) and
[ADR 0006](adr/0006-situated-continuity-foundation.md).

### v0.5 — Durable Work Coordination

Question: **Can goals become durable coordinated work without making a model
the runtime control loop?**

```text
WorkOrder → Planner → PlanProposal → PlanValidator → WorkGraph
          → ReadyFrontier → WorkerMatcher → WorkLease
          → completion / verification / invalidation / replanning
```

Implemented: distinct work contracts, deterministic `FakePlanner`, causal-cut
and graph-version pinning, fail-closed plan validation, dependency readiness,
provider-neutral agent presence and capability manifests, conservative
competence-aware matching, independent verification as work, fenced leases,
crash recovery, source-level orientation prerequisites, and causal plan
invalidation.

Acceptance: the deterministic release graph advances through dependency waves,
matches feasible workers, recovers a crashed lease, uses an independent
verifier, blocks release on stale deployment knowledge, and invalidates after a
causal change without invoking a model or effect.

See [Durable Work Coordination](DURABLE_WORK_COORDINATION.md) and
[ADR 0007](adr/0007-durable-work-coordination.md).

## Implemented — v0.5.x Intent & Outcome Stewardship

Question: **What important part of the user's goals is insufficiently covered,
who legitimately owns it, and what is the least intrusive effective
intervention?**

v0.5.1 implements the bounded deterministic strategic layer above work
coordination. Information governance remains a separate accepted cross-cutting
milestone rather than part of this slice.

### Intent & Portfolio Stewardship

This layer preserves intentional continuity:

> What was the system trying to accomplish, why was it committed, how did it
> expect to get there, and is that still worth pursuing?

The minimum slice is:

```text
Goal → immutable GoalRevision
  → immutable RoadmapRevision / OutcomeNode
  → explicit Commitment
  → CommitmentCoverage
  → bounded WorkOrder proposals
  → RoadmapHealth / deterministic review
```

Required semantics:

- roadmaps are revisable hypothesis graphs of outcomes, assumptions, and
  approximate dependencies—not large `WorkGraph` values;
- the existing `Goal` keeps stable identity while immutable `GoalRevision`
  values form the semantic contract for user intent history; authenticated
  provenance establishes constitutional and user-authored origin, deadlines are
  revisioned, and derived goals name their governing goal lineage;
- `IntentAuthority` remains independent from effect authority, and agent goals
  stay subordinate to governing constitutional/user goals;
- roadmap identity persists while revisions are immutable and superseding;
- a roadmap node creates no obligation until an explicit commitment is accepted;
  `ACCEPTED` means the obligation exists, while `ACTIVE` means execution is
  currently eligible;
- the existing `Commitment` evolves through schema v2/upcasting; lifecycle is
  `PROPOSED → ACCEPTED → ACTIVE ↔ SUSPENDED → CLOSED`, while closure reason is
  `FULFILLED`, `CANCELLED`, `SUPERSEDED`, `FAILED`, or `BREACHED`; legacy failure
  maps to `CLOSED/FAILED` rather than asserting breach;
- automatic commitment-derived work proposals require `ACTIVE`, activation due,
  or prerequisite lead-time evidence, current goal/roadmap provenance, and a
  typed intervention/support declaration within canonical assistance; execution
  requires activation;
- reactivation is reorientation, not blind resume: goals, assumptions,
  dependencies, capabilities, external state, and prior work are reassessed,
  then current revision-scoped roles and assistance are remapped explicitly;
- `RoadmapHealth` derives goal alignment, assumption validity, dependency
  validity, feasibility, capacity fit, progress consistency, and opportunity;
- models may propose revisions, but deterministic validation, intent authority,
  and policy admit them through expected-head compare-and-append at the cursor
  against which they validated;
- current, goal-scoped, commitment, health, and history views are rebuildable
  projections of canonical events;
- initial portfolio work makes scheduling factors observable and applies
  deterministic review/WIP policies; optimization waits for calibrated data.

### User Outcome Stewardship

This layer prevents “more agent work” from becoming the objective. Every
material outcome distinguishes:

| Dimension | Question |
|---|---|
| Outcome owner | Who is ultimately accountable for the result? |
| Decision owner | Who has legitimate authority or judgment to decide? |
| Executor | Who can perform the work? |
| Verifier | Who determines whether it succeeded? |

It also introduces an explicit execution locus (`USER`, `AGENT`, `SHARED`,
`EXTERNAL_HUMAN`, or `EXTERNAL_SYSTEM`) and an `AssistanceEnvelope` that
references the canonical outcome roles while constraining maximum intervention,
identity/physical/institutional limits, user-development value, permitted agent
work, required human work, checkpoints, privacy, risk, and attention.

v0.5.1 stops at deterministic `CommitmentCoverage`. The generalized
`GoalCoverage` intervention policy below remains an accepted follow-on: it
identifies valuable uncovered work across user, Noema, and
external participants. `ExternalWorkstream` represents observations and beliefs
about employer, institutional, or other outside roadmaps without pretending
that Noema owns their source of truth. External milestones may generate Noema
support work; they do not become Noema work graphs by observation alone.
`CommitmentCoverage` itself is criterion-based: required, covered, and uncovered
outcome criteria remain visible until admitted work covers the full obligation.

### Strategic commitments are not the only work origin

`Commitment` is the only **roadmap-derived** source of obligation, not the only
legitimate reason work exists:

```text
RoadmapNode → Commitment ───────────┐
Immediate User Instruction ────────┤
Existing External Obligation ──────┤
Incident / Maintenance Requirement ┤→ WorkOrder
Endogenous Inquiry ────────────────┘
```

### Delivery order and exit criterion

```text
GoalRevision + IntentAuthority
→ roadmap/commitment schema-v2 events and upcasters
→ deterministic projections, proposal validators, and expected-head admission
→ outcome roles + AssistanceEnvelope references
→ commitment coverage + direct-work compatibility
→ external-workstream support derivation
→ deterministic WIP/review policies + roadmap-health shadow evaluation
```

Exit criterion:

> Changing a user goal creates immutable strategic revisions; a roadmap node
> cannot produce work until committed; direct user, incident, maintenance,
> external-obligation, and inquiry work remain possible without a roadmap;
> suspended work reorients before reactivation; external roadmaps retain their
> authority; models cannot change user intent without intent authority; and
> active or activation-due commitment coverage produces bounded `WorkOrder`
> proposals for the implemented v0.5 control plane, with execution gated on
> activation.

The implementation is described in
[Intent & Outcome Stewardship](INTENT_OUTCOME_STEWARDSHIP.md), and its normative
architecture is recorded in
[ADR 0008](adr/0008-intent-and-outcome-stewardship.md).

## v0.6 — Endogenous Cognition

Question: **What should the agent think about when nobody asked it anything?**

The central object is an `Inquiry`, not an unbounded reflection loop. Candidate
questions include stale important beliefs, uncovered commitments, contradicted
roadmap assumptions, stalled goals, upcoming risk, valuable uncertainty,
peer disagreement, repeated expensive work, and useful simulation.

The deterministic v0.6 slice evaluates expected decision improvement against
compute, delay, attention, opportunity, and privacy/risk cost. It implements
durable inquiry and peer-calibration contracts, explicit multidimensional
background cognitive budgets, policy-pinned Value-of-Cognition estimates, a
shadow `IntrinsicAgenda`, endogenous roadmap-health/coverage review, exact
strategic-revision binding, canonical replay, crash recovery, expiry, and
foreground preemption. It does not create terminal values or a new effect path.

The implemented control path is:

```text
canonical scan → pinned DREAM epoch → deterministic candidates
               → explicit Value of Cognition → finite shadow agenda
               → foreground preemption or expiry
```

Novelty can seed an inquiry but receives no automatic value. Belief maintenance
uses exact goal/roadmap/revision/commitment identity until a generic durable
relevance relation exists. Selected activities do not automatically become
`WorkOrder` values.

Acceptance is implemented: identical captured inputs reproduce semantic agenda
selection; background cognition is bounded, single-spend, preemptible,
subordinate to live governing goals, and structurally unable to dispatch work
or effects.

See [Endogenous Drive Ecology](ENDOGENOUS_DRIVE_ECOLOGY.md) and
[ADR 0003](adr/0003-endogenous-drive-ecology.md). The implemented slice is
described in [Endogenous Cognition](ENDOGENOUS_COGNITION.md) and normatively
bounded by [ADR 0010](adr/0010-endogenous-cognition.md).

## v0.6.1 — Deterministic Cognitive Reconsideration

Question: **What from the agent's history may deserve thought again now?**

Outcome:

> Historical cognition can be revalidated under current intent and compete for
> scarce cognitive slack without blind resumption.

Voice: **I know what may deserve thought again.**

Status: **Deterministic shadow foundation implemented; learned allocation staged.**

Historical cognition keeps informational value but loses its former authority.
Reconsideration creates new cognition under a current cognitive basis, current
world state, current Information Governance, and a new causal cut:

```text
historical cognition
    → current-basis/current-world revalidation
    → new reconsideration-candidate eligibility
    → deterministic scarce-budget allocation
```

`RECONSIDER != RESUME`. Fulfilled, cancelled, and failed goals cannot revive old
cognition. Their evidence may seed a new candidate only under current live
intent or an explicit standing `ReconsiderationMandate`. The mandate is user or
constitutional authorization for bounded meta-cognition. It pins scope,
candidate classes/domains, budget, cadence or triggers, expiry, interruption
ceiling, surfacing policy, and information-use policy. It may inspect,
revalidate, estimate, form a candidate, and prepare a question or proposal; it
cannot reactivate a goal, invent terminal values, create obligations, dispatch
work, or execute effects. A reconsideration candidate remains distinct from an
`Inquiry`, `Goal`, `Commitment`, `WorkOrder`, and `ActionIntent`.

This does not change implemented v0.6: current endogenous inquiries still
require exact `ACTIVE` or recovery-oriented `BLOCKED` governing intent. A
mandate is executable only through the separate reconsideration candidate and
shadow-proposal path.

The staged deterministic policy keeps comparatively durable `UserValue`,
candidate `ValueAlignmentEstimate`, and `ExpectedOutcomeValue` distinct. A
scoped `Preference` differs from a temporally volatile `MotivationEstimate`,
which carries evidence, confidence, provenance, and valid/fresh intervals and is
neither authority nor commitment. Explicit motivation evidence has stronger
standing than voluntary reengagement, repeated interest, or inference; low
motivation may suppress discretionary resurfacing but cannot cancel an
obligation.

Allocation also exposes portfolio coherence, clarity, resolvability,
feasibility, meaningful new evidence, regret of silence, opportunity-window
value, and residual unresolvedness. It prices compute, revalidation, attention,
context switching, intrusion, privacy/risk, and opportunity cost against a
budget that also treats wall time, monetary cost, and interruption as scarce.
Positive `NetVOC` means eligible, not mandatory; non-selection and constraint
deferral are not negative evidence.

Future estimators produce an explicit vector of outcome and cost estimates, not
a learned scalar user utility. Hard intent, authority, information-access,
safety, and user-agency constraints run before learned ranking. Operational use
of governed information does not automatically permit training or evaluation
use.

The implemented `CognitiveAllocationTrace` makes future learning identifiable by pinning
candidate provenance, features, hard gates, estimator/policy versions, budget,
one of `SELECTED`, `DEFERRED_BY_CONSTRAINT`, `SUPPRESSED`, or
`EXPLICITLY_REJECTED`, its causal reason, applicable behavior-policy evidence,
and later user/outcome evidence. Counterfactual learning cannot equate selection
with value or non-selection with failure. High-stakes, identity-bound, or
relationship-sensitive exploration requires separate authorization; no
bandit/RL algorithm is chosen here.

The bounded implementation is described in
[Deterministic Cognitive Reconsideration](COGNITIVE_RECONSIDERATION.md) and
normatively governed by
[ADR 0011](adr/0011-governed-allocation-of-scarce-cognition-and-historical-reconsideration.md).
Learned allocation, exploration, and wider historical sources remain staged.

## v0.6.2 — Dormant Cognition Discovery & Evidence Qualification

Question: **Which dormant historical cognition deserves to enter
reconsideration?**

Outcome:

> Durable history can deterministically nominate a historical `Inquiry`,
> qualify current evidence, and assemble the existing reconsideration seed
> without restoring historical authority or manufacturing subjective value.

Voice: **I know which dormant thoughts deserve reconsideration.**

Status: **Deterministic shadow slice implemented.**

```text
historical Inquiry corpus
    → projection-only dormancy
    → target-specific relevance and qualified evidence
    → immutable ReconsiderationOpportunity
    → deterministic ReconsiderationSeed
    → existing v0.6.1 allocation
```

Dormancy is exactly the complement of current v0.6 Inquiry eligibility and is
never a canonical state transition. Agenda slack permits inspection but does
not supply relevance. The initial detector recognizes explicit user or
relevance evidence, opportunity windows, same-goal-lineage reactivation,
target-specific qualified persistent values, and material context changes for
previously constraint-deferred candidates. It does not use elapsed time,
generic values, prose matching, signal salience, NetVOC, models, or learned
scores.

Current evidence remains ordinary `SemanticAssertion` memory. Thin
qualification bindings classify assertions as current revalidation, durable
value, preference, motivation, opportunity, or expected outcome value without
duplicating confidence, bitemporal validity, freshness, provenance, or
contradiction semantics. The discovery worker cannot create the subjective
qualifications that justify its own nominations.

Evaluation is pinned to the canonical trigger sequence; exact-head admission
records and rechecks the actual current predecessor. Scope, qualification, and
opportunity artifacts inherit Information Governance lineage and policy.
Constraint-deferred candidates reuse their identity and seed only after a
material allocation-context change. All outputs remain proposal-only.

The bounded implementation is described in
[Dormant Cognition Discovery](DORMANT_COGNITION_DISCOVERY.md). ADR 0011 remains
the accepted governing allocation decision. Learned allocation, broader
historical sources, automatic subjective inference, and Habit Learning remain
staged.

## v0.6.3 — Learning-Grade Attention Telemetry *(proposed number)*

Question: **Can actual attention behavior become a governed, denominator-
complete source of learning evidence?**

Outcome:

> Every recognized opportunity in an approved source family records an explicit
> actual disposition, with typed features and observable cost, before later
> outcome and explicit feedback are linked causally.

Status: **Implementation candidate on the current feature branch. The mechanics
are implemented there; a qualifying real operating corpus is not.**

```text
label-blind source policy + feature schema
    → every recognized opportunity
    → explicit WAKE / REMEMBER / DEFER / SUPPRESS disposition
    → causally later outcome + explicit feedback
    → denominator audit under LEARN / EVALUATE policy
```

The `deliberative_attention_v1` candidate keeps opportunity recognition
independent of later labels, never infers disposition from model calls or
actions, treats unknown outcome and absent feedback as censored, records
unknown cost components as unknown rather than zero, and inherits Information
Governance lineage into every derived view. Source policies declare the opaque
information-ID fields; source access is admitted before the provider receives a
schema-only safe view, and admission rejects any returned feature, lineage, or
causal-cut mismatch. Exact-head admission is safe across PostgreSQL sequence
gaps; deterministic replay, concurrency convergence, and `ConsumerCheckpoint`
recovery protect the denominator.

Synthetic acceptance fixtures prove these mechanics only. Exit requires real
operation to produce a policy-approved corpus with complete eligible exposure,
actual disposition, causally linkable outcomes, corrections, and representative
counterexamples. Until then, the telemetry layer is observation infrastructure,
not evidence that Habit Learning is safe.

## v0.6.4 — Developmental Intervention Foundation *(proposed number)*

Question: **How can an application improve a user's present decision and
long-term agency without claiming the right to choose for them?**

Outcome:

> A material advisory intervention names the current user outcome it expects to
> improve, its mode, costs, assumptions, affected parties, authority boundary,
> and later feedback/outcome; developmental effects remain secondary evidence.

Status: **Proposed in
[ADR 0013](adr/0013-durable-developmental-intervention.md); not implemented.**

The smallest contract should extend, not replace, existing outcome roles,
`AssistanceEnvelope`, current intent, Information Governance, and evidence
links. Candidate modes may include advise, challenge, teach, coach, prepare,
and ask. Defer and silence are presentation/admission dispositions, not
intervention modes. The architecture audit must still prove which new
object—if any—is necessary before adding an intervention ontology.

Required boundaries are:

```text
challenge authority != decision authority
developmental advice != user-goal mutation
past behavior != current intent
personalization != terminal values
```

This release creates neither effect authority nor a parallel development
control plane. Applications choose how to embody mentor, coach, or thought-
partner functions; the SDK records general outcome, evidence, policy, and
authority semantics.

## v0.7 — Habit Learning

Question: **Which cognition has the agent earned the right not to perform?**

```text
canonical deliberative-attention telemetry
    → episode/exposure projection
    → governed evidence bundle
    → bounded predicate candidate
    → temporal holdout + fitness + collision analysis
    → governed SHADOW rule
```

Status: **Architecture accepted in ADR 0012; runtime HabitForge remains a NO-GO
until actual operation supplies a qualifying, denominator-complete corpus. The
telemetry mechanics exist only as an implementation candidate on the current
feature branch until reviewed and merged.**

Repository inspection found no current canonical family that combines a typed
attention situation, a complete eligible-exposure denominator, the actual
deliberative disposition, current intent and authority, Information Governance
lineage, downstream outcome, correction semantics, and cognition/attention
cost. `decision.proposed` and action events are incomplete; autonomic traces are
counterfactual; cognitive-allocation traces describe whether thought was
selected rather than whether its eventual attention decision was correct.

The v0.6.3 implementation candidate supplies one narrow
`deliberative_attention_v1` source family that records every recognized
attention disposition plus causally later outcome and typed feedback links.
Explicit `LEARN` and `EVALUATE` information operations are independently
governed and source policies establish the denominator before labels. Silence
or absence of correction is censored, never positive evidence. Synthetic
acceptance fixtures demonstrate mechanics, not a production-ready learning
corpus.

Once unblocked, the first HabitForge slice remains model-free and
`RuleFamily.PREDICATE`-only. It derives `HabitEpisode` as a projection, creates
content-addressed evidence/policy/candidate/fitness/collision artifacts, uses
causal train/holdout cuts, compiles into the existing typed rule IR, and advances
through a separate lifecycle projection only as far as SHADOW. Registration
does not imply ruleset membership, authority, CANARY, ACTIVE, live wake
suppression, an `ActionIntent`, or an effect.

Acceptance: repeated situations require progressively less deliberate
cognition while outcome quality remains stable and regret does not increase.
The first runtime acceptance is earlier and stricter: the naive
`deep_work → REMEMBER` rule must fail on urgent or user-decision counterexamples,
while a bounded refined conjunction may enter SHADOW only after denominator,
governance, holdout, regret, compression, novelty-escape, authority, privacy,
and exact-ruleset collision gates all pass.

The proposed architecture, readiness audit, prerequisite, object/event map, and
explicit deferrals are recorded in
[ADR 0012](adr/0012-governed-habit-learning-and-cognitive-compilation.md).

## v0.7.x — Private Cognitive Ecology *(proposed number)*

Question: **Can several always-on cognitive concerns remain useful and bounded
without becoming several schedulers or an endless private monologue?**

Outcome:

> Situation continuity, goal coherence, hazards, scenarios, stakeholder impact,
> epistemic health, developmental hypotheses, reconsideration, and cognitive
> compilation all propose demand into one governed scarce-cognition portfolio.

Status: **Proposed; not implemented.**

```text
detectors + typed evidence
    → Inquiry proposals
    → one common scarce-cognition allocator
    → bounded cognition
    → typed internal assessments
    → governed intervention candidate
    → silence / advise / challenge / teach / coach / prepare
```

This track must reuse `Signal`, `Inquiry`, `IntrinsicActivity`, existing
cognitive-allocation traces and budgets, DREAM epochs, autonomic rules, and
`ConsumerCheckpoint`. A future shared `CognitiveAllocation` portfolio is a
missing integration boundary, not an implemented class today. There is one
shared cognitive portfolio, no bespoke scheduler per concern, and no second
effect path. Always-on means cheap detectors and bounded, preemptible
cognition—not continuous large-model invocation. Durable state contains typed
claims, evidence, assessments, and decisions; a model's private scratchpad or
hidden reasoning transcript is never persisted as durable truth.

Hazards, scenarios, tradeoffs, stakeholder impacts, and epistemic challenges
should initially compose existing assertion, evidence, inquiry, outcome, and
intervention semantics. New core types require repeated application evidence;
the SDK should not preemptively become a universal personal-development
ontology.

## v0.8 — Situated Presence

Question: **Can Noema inhabit a real environment rather than an idealized event
source?**

Planned: substrate and sensor contracts, perception policy, progressive sensing,
artifact and situation capsules, opportunity windows, active wake, retention
controls, and reference adapters for real environments.

Perception escalates by expected value of information:

```text
cheap metadata → APIs/events → structured UI → image/audio → richer sensing
```

Connectors remain adapters. They may not own temporal, cursor, freshness,
memory, privacy, or authority truth.

## v0.9 — Integrated Autonomous Runtime

Question: **Does the complete system continue to work when left alone?**

This is deliberately an integration, soak, evaluation, and hardening release,
not a major new cognitive abstraction. Multi-day reference workloads must
survive process loss, broker loss, delayed and duplicated observations, model
rotation, stale sources, plan invalidation, lease expiry, agent disagreement,
goal change, privacy boundaries, and exhausted budgets while retaining causal,
epistemic, intentional, and operational integrity.

The production ratchet becomes a release gate: poison-message quarantine,
operator repair, sandbox and secret resolution, tenant isolation, policy as
code, million-event and hundred-agent benchmarks, and alternative transport or
durable-execution adapters that preserve semantics.

## v1.0 — Durable Cognitive Agency

v1.0 does not mean every interesting mechanism exists. It means the core theory
is integrated, stable, and usable for real long-lived agents.

A v1.0 agent can:

```text
PERSIST     retain causal continuity across crashes and deployments
REMEMBER    maintain evidence-bearing, contradictory, bitemporal beliefs
ORIENT      test whether old knowledge is still sufficient
ATTEND      suppress routine noise and promote meaningful novelty
THINK       invoke expensive cognition selectively
STEWARD     keep goals, roadmaps, commitments, and human ownership aligned
ORGANIZE    turn commitments into durable dependency-aware work
COORDINATE  route work by capability, competence, context, access, and availability
ACT         perform effects through explicit authority and typed capabilities
REFLECT     generate bounded useful inquiries and maintenance
LEARN       compile proven repeated cognition into governed habits
INHABIT     operate against real changing environments
RECOVER     reconstruct every control horizon after failure
EXPLAIN     show why it believed, noticed, planned, delegated, and acted
```

Full SkillForge and learned metacontrol do not block v1.0. Creating executable
capabilities is a stronger supply-chain, sandbox, evaluation, registration, and
authority problem and remains v1.x work.

## Cross-cutting tracks

### Autonomic Fabric

The [Autonomic Fabric](AUTONOMIC_FABRIC.md) spans the roadmap. v0.3 implemented
signals, immutable rule versions, pinned rulesets and epochs, deterministic
evaluation and replay, inhibition, shadow cells, salience resolution, and a
continuous observational worker. Later releases may add richer opportunity
patterns, sensing-request signals, governed timer workers, and active wake.

Rules emit signals by default. Learned policies never execute arbitrary code or
bypass the existing event, policy, authority, and capability boundary.

### Endogenous Drive Ecology

The [Endogenous Drive Ecology](ENDOGENOUS_DRIVE_ECOLOGY.md) is the second source
of cognitive demand. v0.6 implements its first shadow contracts only after
memory, orientation, work, and intent stewardship provide something grounded
to maintain. Intrinsic activity remains subordinate, budgeted, preemptible,
single-spend per epoch, and proposal-only.

### Learned Allocation of Scarce Cognition

This cross-cutting research track connects Endogenous Cognition,
reconsideration, and Habit Learning without collapsing their meanings:

```text
deterministic allocation
    → allocation/outcome traces
    → calibrated estimators
    → counterfactual evaluation
    → shadow learned allocation
    → bounded active allocation
```

Endogenous Cognition asks what deserves thought now; Historical Reconsideration
asks what may deserve thought again; Governed Allocation asks which eligible
thought deserves scarce cognition now; Habit Learning asks what has earned the
right not to require deliberation anymore. Learned Allocation sits inside—not
above—Governed Allocation of Scarce Cognition. Learned estimators predict an
inspectable outcome vector and never learn sovereign terminal utility.
Information Governance separately gates live allocation features and every
future training or evaluation corpus. The implemented `CognitiveAllocationTrace`
retains allocation labels, binding constraints, behavior-policy evidence when
applicable, and later outcomes so counterfactual evaluation is identifiable.
Active exploration for high-stakes or identity-sensitive resurfacing remains
separately authorized.

### Developmental Partnership

Arc V is cross-cutting because developmental help draws on current intent,
outcome ownership, memory, evidence, cognition, work, and later evaluation. It
does not sit above them as a new sovereign planner. Proposed ADR 0013 defines
the first decision point: every material intervention must identify the current
user outcome it expects to improve, while any longer-term capability or agency
effect remains separately observed secondary evidence.

The same shared cognitive portfolio later admits situation, hazard, scenario,
stakeholder, epistemic, and developmental inquiries under finite budgets.
Detectors propose; the common allocator selects; typed assessments may propose
an intervention; existing policy, authority, work, and effect paths remain the
only paths to consequence. Application products decide whether that appears as
sentinel, coach, mentor, chief of staff, or thought partner behavior.

### User value

Outcome ownership, minimal intervention, user-development value, and restraint
constrain every later release. Neither high competence nor technical feasibility
grants outcome ownership, intent authority, or effect authority.

### Information Governance and Confidential Context

This is a separate accepted architecture direction whose deterministic
foundation is implemented, with later confidential-data slices staged, as
specified by
[ADR 0009](adr/0009-information-governance-and-confidential-context.md). It may
develop independently of v0.5.x but must be implemented before real confidential
employer or similarly restricted context enters production Noema.

The implemented foundation proves quarantine before policy resolution, typed
operation-specific policy composition, provenance inheritance, internal
`InformationAccessDecision`, trust-boundary `DisclosureDecision`, explicit
declassification after redaction/abstraction, safe governance-event envelopes,
immutable historical context, exact-head admission for material decisions,
effective immutable declassified views, and distinct canonical decisions versus
non-authorizing bounded audit receipts. It enforces explicitly governed memory
retrieval, model context, and access-plus-disclosure worker feasibility.
Production encrypted artifact retention, real restricted ingestion, global
event-envelope retrofitting, and exhaustive gates for model responses, tools,
agents, telemetry, traces, logs, caches, indexes, fixtures, errors, connectors,
and outputs remain staged.

## Measures of success

The north star is:

```text
valuable autonomous outcomes
────────────────────────────────────────────────────
deliberative compute + human attention + regret
```

subject to hard authority, privacy, safety, user-development, and outcome-quality
constraints.

Supporting measures include:

- **User leverage:** goal-relevant work completed per unit of user attention;
- **Goal-weighted throughput:** change in expected goal value per unit time,
  rather than tasks completed per day;
- **Commitment coverage:** valuable active obligations with sufficient current
  work coverage;
- **Cognitive sparsity:** material events handled without expensive reasoning;
- **Deliberative compression:** repeated situations requiring progressively
  less deliberate cognition without increased regret;
- **Decision improvement:** interventions improve an explicitly named current
  user outcome without taking decision ownership or mutating terminal values;
- **Developmental integrity:** later capability or agency evidence is visible
  without being used as a proxy that overrides current intent;
- **Epistemic integrity:** important beliefs retain provenance, time, conflict,
  and freshness;
- **recoverability:** replay reconstructs the same semantic state and duplicates
  no external effect;
- **restraint:** silence, sleep, deferment, and “do nothing” are common when
  correct.

Maximum throughput does not mean maximum concurrency. The first stewardship
slice records critical paths, coordination and context-switch cost, verification
capacity, scarce competence, context affinity, WIP, and future opportunity cost
while applying deterministic WIP/review policies. Optimizing those factors is a
later research program.

## Decisive v1.0 demonstrations

1. **Seven-day absence:** after thousands of intervening changes, refresh only
   what matters, reconstruct bitemporal truth, identify important changes, and
   remain silent if nothing deserves attention.
2. **Mixed-ownership multi-day goal:** pursue a goal with human decisions,
   agent support, external dependencies, verification, and confidential context
   without prompting merely to continue; explain any uncovered gap.
3. **Million-event life:** keep useful model calls sparse without losing a
   meaningful event.
4. **Repeated world:** deliberate initially, then graduate proven habits while
   quality remains stable and regret does not rise.
5. **Kill -9:** terminate runtimes, workers, connections, brokers, and agents;
   duplicate, delay, and retry events and effects; restart without producing a
   causally, epistemically, intentionally, or operationally impossible state.
6. **Developmental restraint:** present a consequential, identity-bound user
   decision; improve preparation and expose tradeoffs while preserving the
   user's decision authority, accepting correction, and learning nothing from
   protected evidence without explicit secondary-use permission.

The strongest long-term signal is behavioral: a mature Noema agent becomes
quieter, cheaper, safer, and more useful as experience accumulates.

## Beyond v1.0

- **SkillForge:** capability-gap mining, specification, sandboxed construction,
  evaluation, provenance, canarying, registration, and independent authority;
- **learned metacontrol:** improve reasoning depth, model choice, simulation,
  delegation, verification, and attention allocation from trajectories;
- **rich habitats:** desktop, mobile, server, device-transition, and cooperative
  local/cloud reference environments;
- **ecosystem:** SDK protocols, adapter registry, observability, benchmarks, and
  development tooling;
- **v2.0 — Cognitive Ecology:** persistent, independently situated agents with
  different beliefs, capabilities, and authority coordinating through
  contracts, negotiation, calibration, institutions, and non-collapsed memory.
