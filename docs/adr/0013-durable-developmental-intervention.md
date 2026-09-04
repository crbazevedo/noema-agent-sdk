# ADR 0013: Durable developmental intervention

- Status: Accepted — architecture direction; runtime implementation staged
- Date: 2026-09-04
- Scope: material advisory intervention, intervention-mode permission,
  outcome and assistance provenance, later evidence, and the boundary from
  private cognition to user-facing developmental support

## Context

Noema already preserves current user intent, immutable goal and roadmap
revisions, outcome roles, bounded assistance, durable work, and proposal-only
background cognition. Those contracts can say why work exists, who owns the
outcome and decision, who may execute, and how intrusive assistance may be.
They cannot yet represent a durable, inspectable claim that a particular piece
of advice, challenge, teaching, coaching, or preparation is expected to improve
an immediate user outcome.

That missing concept matters. A persistent agent may notice a faulty
assumption, an avoidable decision error, or an opportunity for the user to gain
capability. Merely recording another `Inquiry` loses the user-facing
intervention and its expected impact. Creating a `WorkOrder` confuses advice
with executable work. Mutating a `GoalRevision` lets developmental judgment
become authority over the user's purpose.

The architecture therefore needs a narrow advisory boundary, but it does not
need a second intent system, a coaching product ontology, or named SDK
personas. Sentinel, chief-of-staff, thought-partner, mentor, coach, and
epistemic-steward behavior remain application functions assembled from general
contracts.

The load-bearing distinctions are:

```text
challenge authority != decision authority
challenge authority != intent authority
challenge authority != effect authority

developmental advice != user-goal mutation
past behavior != current intent
personalization != terminal values
observation != truth

AdvisoryIntervention != WorkOrder != ActionIntent
later outcome != feedback
silence != acceptance
CognitivePriority != InterventionPriority
```

## Existing substrate and demonstrated gap

The new semantics extend Intent & Outcome Stewardship rather than sit beside
it:

| Existing contract | Reuse | Remaining gap |
|---|---|---|
| `GoalRevision` | Exact current governing intent and success criteria | It is not a developmental recommendation and cannot be mutated by one. |
| `RoadmapRevision` outcome node | Exact current strategic outcome where one exists | Not every immediate instruction or decision has a roadmap. |
| `OutcomeRoleAssignment` | Independent outcome owner, decision owner, executor, and verifier | It does not describe an advisory mode or expected improvement. |
| `AssistanceEnvelope` | Maximum intervention, permitted support, human work, checkpoints, risk, privacy, reversibility, attention, and user-development value | Current envelopes do not grant typed advice, challenge, teaching, or coaching modes. |
| `WorkOrder` | Durable executable work | Advice is not executable work, and an intervention cannot manufacture work. |
| `ActionIntent` | Proposed external effect | An advisory proposal carries no effect authority. |
| `Inquiry` and proposal-only cognition | Evidence-bearing question under current intent | An inquiry does not establish permission to interrupt or influence the user. |
| Memory and Information Governance | Evidence provenance, policy, lineage, and secondary-use boundaries | Evidence availability cannot grant intervention or intent authority. |

The gap is therefore one durable, outcome-scoped advisory object plus its
admission and evidence semantics. It is not a parallel goal, workflow, user
model, or agent persona.

## Quality-attribute scenarios

1. **Current intent and safety.** A background assessment proposes challenging
   an assumption. Before admission, the governing `GoalRevision` is cancelled.
   Admission rejects the stale proposal and records no intervention against the
   terminal intent.
2. **Authority isolation.** An agent may prepare material and is permitted to
   advise, but the user owns the decision. The intervention can be admitted in
   the permitted advisory mode; it cannot change the goal, decide for the user,
   create work, or perform an effect.
3. **Identity continuity.** A roadmap-backed proposal names the exact current
   user outcome, `GoalRevision`, roadmap revision and outcome node,
   `OutcomeRoleAssignment`, and `AssistanceEnvelope`. Reactivation onto a newer
   roadmap revision invalidates the old proposal until it is reassessed and
   remapped.
4. **Direct outcomes.** A user asks for help with a one-off decision that has no
   roadmap. A material intervention can name the current direct user outcome
   and current role/assistance records without manufacturing a goal or
   commitment.
5. **Development without paternalism.** A proposal estimates both immediate
   decision improvement and a possible long-term capability effect. Admission
   evaluates the immediate outcome first; the capability estimate remains
   uncertain secondary evidence and cannot redefine terminal user values.
6. **Evidence integrity.** A later real-world outcome is linked to an admitted
   intervention, but the user supplies no feedback. The outcome and missing
   feedback remain distinct; silence is censored rather than counted as
   acceptance.
7. **Crash and concurrency.** Two workers derive the same candidate at the same
   causal cut. Exact-head admission plus semantic identity produces one
   canonical intervention or an explicit conflict. Replay reaches the same
   result even when durable event sequences contain gaps.
8. **Bounded background cognition.** Multiple detectors identify developmental
   questions. They propose `Inquiry` values into one finite scarce-cognition
   portfolio. No detector owns a scheduler, creates an effect, or persists a
   model scratchpad.
9. **Privacy and learning isolation.** Protected observations may support an
   assessment only under Information Governance. Reuse of an intervention,
   feedback, or outcome for learning or evaluation requires the corresponding
   explicit secondary-use decision.
10. **Adoptability.** An application can implement mentor-like or coaching-like
    behavior through the same outcome, mode, assistance, and evidence
    contracts without the SDK defining those product roles.

## Decision

### Extend Intent & Outcome Stewardship

Every material advisory intervention must reference:

1. the exact current user outcome it expects to improve;
2. the current `GoalRevision` and roadmap revision/outcome node when the
   outcome is roadmap-governed;
3. the current `OutcomeRoleAssignment` for that outcome; and
4. the current `AssistanceEnvelope` that permits the proposed intervention
   mode.

The roadmap references are conditional because immediate user instructions and
other legitimate direct outcomes do not require a roadmap. The current user
outcome, role assignment, and assistance envelope are not conditional for a
material intervention.

```text
current user outcome
  + current governing intent where available
  + current outcome roles
  + current assistance envelope
  + evidence-bearing assessment
  -> advisory intervention proposal
  -> deterministic admission
  -> advisory intervention record
```

The canonical goal, roadmap, roles, and assistance records remain the source of
truth. An intervention retains exact references; it does not copy or override
their semantics. A projection may derive current intervention status and
evidence views from canonical events, but it is never a second writable
developmental profile.

### Add intervention mode as an independent permission

`InterventionMode` expresses how the application proposes to influence the
user's deliberation. The initial contract should support only a small typed
vocabulary sufficient to distinguish advice, challenge, teaching, coaching,
and preparation. Silence is an admission or presentation disposition, not an
intervention mode.

Mode permission is a new axis of `AssistanceEnvelope`; it is not inferred from
`maximum_intervention`, `permitted_agent_support`, user-development value,
decision ownership, execution locus, capability, or any other authority:

```text
InterventionModePermission
!= DecisionAuthority
!= IntentAuthority
!= EffectAuthority
!= ExecutionLocus
```

All constraints apply conjunctively. A permitted challenge mode does not allow
the agent to decide, execute, mutate intent, or exceed privacy, risk,
reversibility, human-work, checkpoint, institutional, relationship, identity,
or attention bounds. Existing assistance envelopes deterministically grant no
intervention modes. A schema evolution must not infer new permission from
legacy support strings or maximum intervention levels.

### Keep immediate outcome primary

An intervention's primary claim is the expected improvement to the named
current user outcome. A proposed `ImpactEstimate` may represent:

- expected decision or outcome improvement;
- expected reduction in user effort;
- affected stakeholder references and plausible externalities;
- assumptions, counterevidence, and tradeoffs;
- intervention, attention, privacy, and delay costs;
- confidence, validity horizon, and evidence references; and
- an expected long-term agency or capability effect.

The long-term developmental effect is secondary evidence. It cannot compensate
for expected harm to the immediate outcome, establish a terminal value, justify
an unpermitted mode, or authorize goal mutation. Absence of a credible
long-term effect does not make otherwise useful advice invalid; claimed
developmental benefit does not make intrusive advice valid.

Impact dimensions remain explicit rather than collapsed into an opaque scalar.
Any future deterministic admission policy may compare them, but this ADR does
not select weights or authorize an optimizer.

### Use a minimal proposed contract family

Implementation design may introduce the following narrow contracts after this
ADR is accepted:

- `AdvisoryInterventionProposal`: a non-authorizing, immutable proposal with
  exact causal cut, current outcome/intent/role/assistance references, mode,
  typed assessment and evidence, `ImpactEstimate`, provenance, governing
  information decisions, validity horizon, and configuration identity;
- `AdvisoryInterventionRecord`: the exact-head admission receipt for one
  validated proposal, retaining the validated predecessor head and admitted
  policy/authority evidence;
- `InterventionMode`: the typed manner of advisory support, governed by an
  explicit mode grant;
- `ImpactEstimate`: the versioned, evidence-bearing immediate and secondary
  impact vector described above;
- `InterventionOutcomeLink`: an immutable link to a causally later observed
  outcome; and
- `InterventionFeedbackRecord`: an immutable explicit user or authorized actor
  response with actor and provenance.

Names and payload shapes remain proposed until the implementation contract is
reviewed. The semantic boundaries in this ADR are normative.

The record does not mean the advice was correct, accepted, delivered, or acted
upon. If presentation or notification is an external effect in a deployment,
the normal effect policy and delivery contract remain separately mandatory.

### Admit against exact current state

Material intervention admission follows the established expected-head
boundary:

```text
capture canonical head H
-> rebuild Goal/Roadmap/roles/assistance/information state through H
-> verify current non-terminal intent, mode permission, evidence and limits
-> append_if_head(intervention, H)
    |-- success
    `-- ConcurrentAppend -> reload and fully revalidate
```

The proposal must identify the exact outcome and revisions on which its meaning
depends. `COMPLETED`, `FAILED`, and `CANCELLED` governing goals deny new
intervention. A current `BLOCKED` goal may admit a bounded intervention whose
purpose is recovery or unblocking. A stale goal revision, roadmap revision,
outcome node, role assignment, assistance envelope, information decision, or
validity horizon denies admission; it is never silently rebound to newer
intent.

PostgreSQL sequence gaps are valid. The causal invariant is that the recorded
predecessor head equals the actual canonical head used for validation and that
the stored event follows it, not that their numeric sequences are contiguous.

No intervention admission mutates a goal, roadmap, commitment, role,
assistance envelope, work order, or action intent. Any later user-authorized
intent change travels through the existing stewardship command and authority
path as a separate causal event.

### Separate intervention, outcome, and feedback

An admitted intervention is a historical advisory act or decision, not proof
of value. Later evidence is append-only:

```text
intervention record
  + causally later outcome link
  + zero or more explicit feedback records
```

Outcome observations require source provenance, valid and knowledge time,
confidence, and a causal relationship sufficient for their stated use. They do
not imply that the user accepted the intervention. Explicit acceptance,
correction, contextual exception, temporary override, preference revision,
rejection, or prohibition must remain distinct feedback values. Missing
feedback and unresolved outcomes remain censored. Neither silence nor the mere
absence of correction is positive evidence.

Retrospective evaluation must preserve the immediate-outcome and long-term
agency dimensions separately, including adverse stakeholder impacts and
intervention costs. Learning and evaluation use the existing Information
Governance `LEARN` and `EVALUATE` decisions; operational readability alone is
insufficient.

### Reuse one private cognitive ecology

Developmental cognition begins as another bounded demand on the existing
cognitive substrate:

```text
Observation
-> CognitiveDemand
-> CognitiveAllocation
-> Assessment
-> InterventionOpportunity
-> InterventionAllocation
-> silence / remember / defer / wake
```

`CognitivePriority != InterventionPriority`. Private cognition may deserve
compute without deserving user interruption. `CognitiveAllocation` determines
whether bounded thought receives scarce compute. Only a later, outcome-scoped
`InterventionOpportunity` may compete in a separate `InterventionAllocation`
for user attention. The resulting presentation disposition does not itself
grant an intervention mode, delivery authority, or effect authority.

Situation continuity, goal coherence, hazard anticipation, scenario
evaluation, stakeholder impact, epistemic health, developmental stewardship,
opportunity reconsideration, and cognitive compilation may supply detectors or
typed assessments. They do not become bespoke schedulers. The eventual mixed
portfolio must reuse the existing scarce-cognition machinery to allocate one
finite foreground/background cognitive budget and preserve foreground
preemption, expiry, checkpoints, and deterministic recovery. It is not
implemented by this ADR acceptance.

Private cognition has no direct work, dispatch, action, notification, or effect
path. It records typed claims, evidence, uncertainty, counterevidence,
assumptions, alternatives, and provenance. Model scratchpads and hidden
reasoning transcripts are neither canonical truth nor a durable memory format.

## Consequences and tradeoffs

- Applications gain a general audited boundary for developmental advice
  without the SDK embedding a mentor, coach, or chief-of-staff persona.
- Requiring exact current outcome, role, and assistance references makes
  interventions safer and replayable, at the cost of more setup for
  applications and more stale-proposal rejections.
- A distinct mode grant prevents ordinary preparation authority from silently
  becoming permission to challenge or coach, but requires a fail-closed schema
  migration for assistance envelopes.
- Immediate-outcome primacy resists paternalistic optimization. It also means
  uncertain long-term developmental benefits cannot justify otherwise invalid
  interventions.
- Separate outcome and feedback events preserve evidential honesty, but useful
  evaluation data accumulates more slowly because silence remains censored.
- One shared cognitive portfolio avoids duplicated scheduling and uncontrolled
  background work. Diverse cognitive demands must nevertheless become
  comparable without collapsing their typed outcome vectors into a false
  universal utility.
- Canonical, typed assessments improve auditability and privacy control but
  intentionally exclude durable free-form model scratchpads.
- Exact-head admission can recompute or suppress advice under contention. This
  is preferable to presenting advice whose governing intent or assistance
  permission has changed.

### Risks and sensitivity points

- **Paternalism risk:** a long-term agency score could dominate current user
  purpose. Admission is sensitive to outcome primacy and must keep the
  developmental dimension secondary.
- **Authority inflation:** loose mapping from existing support strings to modes
  could silently grant challenge authority. Legacy grants no modes.
- **Interruption harm:** mode, timing, attention cost, false-alarm cost, and
  user context are sensitive inputs. The assistance attention budget remains a
  hard ceiling, not an optimization weight.
- **Outcome attribution:** later outcomes may be correlated rather than caused
  by an intervention. Links must retain uncertainty and must not upgrade
  observation into truth.
- **Ontology growth:** application-specific coaching stages, personality
  models, competencies, hazards, and scenarios could leak into core. New types
  require repeated cross-application evidence.
- **Scheduler duplication:** one loop per developmental concern would bypass
  scarce-cognition allocation. Structural import and worker gates must prevent
  it.
- **Privacy amplification:** developmental inference can be more sensitive than
  its sources. Derived information must preserve lineage and composed policy,
  including separate learning/evaluation permission.

## Rejected alternatives

- **Create a parallel developmental goal hierarchy:** duplicates `GoalRevision`
  and lets advice diverge from current user intent.
- **Treat an intervention as a `WorkOrder`:** turns influence on deliberation
  into executable work and can accidentally reach dispatch.
- **Treat an intervention as an `ActionIntent`:** conflates advisory meaning
  with external effect authority and loses the immediate-outcome claim.
- **Add developmental fields directly to every `Inquiry`:** mixes private
  questions with admitted user-facing interventions and cannot express mode
  permission.
- **Infer challenge permission from maximum intervention or support strings:**
  silently expands legacy authority.
- **Let long-term agency improvement override immediate outcomes:** gives the
  system authority to choose terminal user values.
- **Count later success or silence as acceptance:** conflates real-world outcome,
  feedback, and censoring.
- **Persist free-form inner monologue for continuity:** creates an unauditable,
  privacy-heavy second memory substrate. Durable cognition is typed evidence.
- **Create one scheduler for each cognitive loop:** duplicates allocation,
  budgets, recovery, and foreground-preemption semantics.
- **Define SDK personas or a comprehensive development ontology:** couples core
  to one product vocabulary before repeated application evidence exists.

## Fitness functions for a future implementation

- every material proposal names exactly one current user outcome, current
  `OutcomeRoleAssignment`, and current `AssistanceEnvelope`;
- roadmap-governed proposals name the exact current `GoalRevision`, roadmap
  revision, and outcome node; direct outcomes work without manufacturing them;
- `COMPLETED`, `FAILED`, and `CANCELLED` governing goals reject new
  interventions; current `BLOCKED` goals retain bounded recovery support;
- stale outcome, intent, role, assistance, governance, or validity references
  reject rather than rebind;
- legacy assistance envelopes grant no advisory modes after upcast;
- mode permission is necessary and cannot confer decision, intent, execution,
  work, or effect authority;
- admission cannot mutate Goal, Roadmap, Commitment, WorkOrder, or
  `ActionIntent`, and developmental packages cannot import work dispatch or the
  effect plane;
- every canonical admission records the actual validated predecessor head,
  uses expected-head compare-and-append, tolerates durable sequence gaps, and
  revalidates after a concurrent append;
- projections rebuild deterministically from canonical events and reject
  inconsistent cross-object references during replay;
- immediate outcome effects, long-term agency effects, stakeholder impacts,
  uncertainty, and costs remain separate typed dimensions;
- outcome links must be causally later and preserve observation provenance;
  they cannot imply feedback;
- feedback is explicit and attributable; absence of feedback or outcome remains
  censored and never becomes acceptance;
- intervention evidence used for learning or evaluation has explicit `LEARN`
  or `EVALUATE` decisions respectively, with derived-information lineage and
  composed policy;
- developmental detectors emit `Inquiry` proposals into the shared bounded
  cognitive portfolio and have no independent scheduling or effect path;
- canonical developmental outputs contain typed assessments and evidence, not
  hidden reasoning or durable scratchpads;
- structural tests prevent core product-persona classes and application-specific
  development taxonomies from entering the SDK without a later accepted ADR.

## Deferred decisions

This ADR does not authorize runtime implementation. Acceptance and a separate
implementation directive are required before contracts or events are added.
The following remain deferred:

- exact `InterventionMode` vocabulary and assistance-envelope schema version;
- event names, payload schemas, upcasters, projection APIs, and retention;
- provider protocols and deterministic admission-policy details;
- weights or thresholds for impact, interruption, externality, or regret;
- learned intervention selection, personalization, and adaptive timing;
- causal attribution of long-term agency effects;
- a mixed private-cognition portfolio across loop classes;
- generalized hazard, scenario, tradeoff, stakeholder, epistemic-challenge, or
  competency ontologies;
- presentation and delivery connectors, notifications, and all external
  effects;
- persona, relationship, curriculum, or product-level coaching abstractions;
- executable learned policy, HabitForge integration, and automated goal
  creation or revision.

The proposed conceptual overview is
[Durable Developmental Agency](../DEVELOPMENTAL_AGENCY.md). Existing intent,
role, and assistance semantics remain governed by
[ADR 0008](0008-intent-and-outcome-stewardship.md); information lineage and
secondary use remain governed by
[ADR 0009](0009-information-governance-and-confidential-context.md); bounded
proposal-only cognition remains governed by
[ADR 0010](0010-endogenous-cognition.md) and
[ADR 0011](0011-governed-allocation-of-scarce-cognition-and-historical-reconsideration.md).
