# ADR 0008: Intent and outcome stewardship

- Status: Accepted — deterministic v0.5.x slice implemented in v0.5.1
- Date: 2026-08-31
- Scope: goal revision and intent authority, roadmap and commitment semantics,
  outcome roles, assistance, external workstreams, coverage, and portfolio
  observability

## Synthesis provenance

This proposal consolidates the 2026-08-31 design notes on increasing agency,
user-outcome stewardship, and durable roadmap semantics, plus the subsequent
architecture review. Information flow was deliberately separated into
[ADR 0009](0009-information-governance-and-confidential-context.md).

## Context

Durable Work Coordination answers what bounded work exists, which dependencies
are ready, who can perform it, and how ownership recovers. It deliberately does
not answer why the work remains valuable, who owns the real-world outcome,
whether a roadmap still serves current goals, or what must remain human.

Noema already has first-class `Goal` and `Commitment` situation objects. The
current `GoalStatus` values are `PROPOSED`, `ACTIVE`, `BLOCKED`, `COMPLETED`,
`FAILED`, and `CANCELLED`; current `CommitmentStatus` values are `OPEN`,
`IN_PROGRESS`, `COMPLETED`, `FAILED`, and `CANCELLED`. The built-in projection
handles `goal.updated`, `commitment.updated`, and commitment terminal events as
current values. Adding durable strategic history is therefore a versioned
evolution of existing contracts, not permission to create conflicting parallel
meanings.

The next layer must preserve intentional continuity and increase user leverage
without turning roadmaps into work graphs, treating technical capability as
outcome ownership, or maximizing agent activity.

## Quality-attribute scenarios

1. A user changes a governing goal. Noema records a new immutable goal revision,
   marks dependent roadmap assumptions for review, and preserves the prior goal
   and roadmap history.
2. A model proposes reprioritizing or retiring a user-authored goal. Validation
   rejects the change without sufficient `IntentAuthority`, even if the model
   or agent has effect authority.
3. A roadmap node exists but has no accepted commitment. It creates no
   roadmap-derived `WorkOrder`.
4. An immediate user instruction, incident, maintenance requirement, external
   obligation, or endogenous inquiry legitimately creates a `WorkOrder` without
   manufacturing a roadmap or strategic commitment.
5. A suspended roadmap direction becomes relevant six months later. The system
   re-evaluates goals, assumptions, dependencies, completed work, capabilities,
   and external conditions before a new revision and reactivation.
6. A promotion outcome requires a user-owned interview, an employer-owned
   decision, and agent-executable preparation. Noema preserves independent
   outcome, decision, execution, and verification roles while its assistance
   envelope constrains intervention without duplicating ownership.
7. An externally governed milestone changes. Noema records a fresh epistemic
   observation and may revise internal support work, but never claims its work
   graph is the external source of truth.
8. Legacy goal and commitment histories replay through deterministic upcasters
   into the same v2 strategic projection as equivalent native v2 events.
9. Thirteen nodes are feasible but verification is the bottleneck. Initial WIP
   policy starts only a deterministic bounded set and records the quantities
   needed for later portfolio research; it does not claim an optimal allocator.
10. A goal, roadmap, or commitment transition validates through canonical head
    `H`, then a concurrent append changes relevant strategic state. The
    expected-head append rejects the stale transition; Noema reloads and
    revalidates before anything becomes canonical.

## Decision

1. Extend the identity boundary:

   ```text
   Goal/GoalRevision != Roadmap/RoadmapRevision != Commitment
                     != WorkOrder != PlanProposal
                     != WorkGraph/WorkNode != ActionIntent
   ```

2. Evolve the existing `Goal` contract rather than adding a parallel strategic
   goal type. `Goal` retains stable identity and `GoalRevision` is the semantic
   contract. Each immutable revision preserves description, priority, utility,
   success criteria, owner, status, governing authority, causal cursor, author,
   revision reason, authenticated origin/provenance, and a `GoalKind` such as
   `CONSTITUTIONAL`, `USER_AUTHORED`, `DELEGATED`, `INSTRUMENTAL`, `EPISTEMIC`,
   `MAINTENANCE`, or `EXPLORATORY`. A versioned canonical event durably
   represents each admitted revision; the event is not an alternative goal
   ontology. The current goal is a projection. An agent-generated revision
   cannot claim `USER_AUTHORED` or `CONSTITUTIONAL` origin without authenticated
   provenance establishing that origin.
3. Introduce explicit `IntentAuthority` and keep it independent from
   `EffectAuthority`:

   ```text
   IntentAuthority != EffectAuthority
   ```

   Constitutional and user-authored goals cannot be rewritten, reprioritized,
   or retired by an agent merely because it may perform effects. Agents may
   propose instrumental, epistemic, maintenance, and exploratory goals only
   beneath governing constitutional/user goals and within delegated intent
   scope.
4. Treat `Roadmap` as stable identity and `RoadmapRevision` as an immutable,
   causally pinned hypothesis graph of outcome nodes, assumptions, confidence,
   approximate dependencies, success criteria, and resource envelope. Revisions
   supersede but never rewrite earlier revisions. A roadmap is not executable
   state.
5. Evolve the existing `Commitment` contract deliberately through event schema
   v2, deterministic upcasters, and projection migration. Separate lifecycle
   from closure semantics:

   ```text
   state:
       PROPOSED → ACCEPTED → ACTIVE ↔ SUSPENDED → CLOSED

   closure_reason:
       FULFILLED | CANCELLED | SUPERSEDED | FAILED | BREACHED
   ```

   The proposed compatibility mapping is `OPEN → ACCEPTED`,
   `IN_PROGRESS → ACTIVE`, `COMPLETED → CLOSED/FULFILLED`,
   `FAILED → CLOSED/FAILED`, and `CANCELLED → CLOSED/CANCELLED`. Failure means
   the outcome was not fulfilled; breach makes the stronger claim that an
   obligation was violated. Legacy history does not invent that stronger claim.
   The legacy `commitment.completed`, `commitment.failed`, and
   `commitment.cancelled` events upcast to explicit transitions. Implementation
   must validate this mapping against existing application meaning before schema
   v2 is accepted.
6. Make `Commitment` the only **roadmap-derived** object that creates durable
   obligation. It is not the universal source of work. Legitimate work origins
   remain explicit and provenance-bearing:

   ```text
   RoadmapNode → Commitment ───────────┐
   Immediate User Instruction ────────┤
   Existing External Obligation ──────┤
   Incident / Maintenance Requirement ┤→ WorkOrder
   Endogenous Inquiry ────────────────┘
   ```

7. Derive `CommitmentCoverage` for both accepted and active strategic
   commitments while keeping obligation separate from execution timing:

   ```text
   ACCEPTED ⇒ obligation exists
   ACTIVE   ⇒ currently eligible for execution
   ```

   Automatic `WorkOrderProposal` generation requires an `ACTIVE` commitment,
   an `activation_due` condition, or evidence that prerequisite lead time
   requires work now. A proposal created for the latter two conditions must
   obtain an authorized transition to `ACTIVE` before commitment-derived work
   is admitted for execution. A future accepted commitment can therefore remain
   covered and visible without creating executable work prematurely. Other work
   origins use their own durable provenance and admission policy.
8. Model outcome owner, decision owner, executor, and verifier as independent
   first-class role assignments. None is inferred from capability, competence,
   information access, effect authority, or another role.
9. Make `AssistanceEnvelope` reference the canonical outcome-role assignment
   rather than repeat ownership fields. It constrains maximum delegation,
   identity/physical/relationship/institutional limits, user-development value,
   permitted agent support, required human work, checkpoints, reversibility,
   privacy, risk, and attention.
10. Use `GoalCoverage` to identify valuable gaps across the user, Noema, and
    external participants. Select the least intrusive intervention that reaches
    sufficient expected coverage. Task count, utilization, token volume, and
    automation rate are not top-level objectives.
11. Represent external roadmaps and milestones as `ExternalWorkstream`
    observations/beliefs with source-of-truth identity, provenance, valid and
    knowledge time, confidence, freshness, user role, and Noema role. External
    observations may justify internal support work but cannot become a Noema
    `WorkGraph` directly.
12. Derive `RoadmapHealth` from goal alignment, assumption validity, dependency
    validity, schedule feasibility, capacity fit, progress consistency, and
    opportunity validity. Goal or assumption changes create review demand
    rather than destructive edits.
13. Apply Situated Continuity to strategy: reactivation is reorientation, not
    resume. A reactivated direction requires a current assessment, new roadmap
    revision, and explicit commitment transition.
14. Let models propose `GoalRevisionProposal`, `RoadmapRevisionProposal`, and
    intervention candidates. Deterministic validation plus `IntentAuthority`
    and policy alone admit goal, roadmap, and commitment transitions. Existing
    work and effect gates remain independently mandatory. Every causally
    validated strategic transition uses the expected-head compare-and-append
    primitive already established by Durable Work Coordination:

    ```text
    capture H
       → validate Goal/Roadmap/Commitment transition through H
       → append_if_head(..., H)
           ├── success
           └── ConcurrentAppend → reload → revalidate
    ```

    A transition becomes canonical only at the head against which it validated;
    no separate strategic transaction mechanism is introduced.
15. Keep the event log canonical. Goal, roadmap, commitment, outcome-role,
    assistance, external-workstream, coverage, and health views are rebuildable
    projections, not a separate writable project-management store.
16. Keep portfolio optimization outside the first implementation. v0.5.x makes
    goal value, commitment strength, urgency, critical-path pressure, success
    estimates, coordination cost, context affinity, verification capacity, WIP,
    scarce competence, and information-access requirements representable and
    observable. It implements deterministic review and WIP policies, collects
    trajectories, and defers optimization until calibration evidence exists.

## Consequences and tradeoffs

- Noema can preserve why work exists and stop executing a strategy whose reason
  disappeared without weakening reactive, maintenance, or inquiry-driven work.
- Existing Goal and Commitment users face an explicit schema migration instead
  of a silent semantic collision. Upcasters add complexity but make replay and
  compatibility testable.
- Expected-head admission may force strategic proposals to be recomputed under
  contention, but prevents a valid-at-an-old-head transition from corrupting
  current intent or obligation state.
- Intent authority prevents effect permissions from becoming permission to
  redefine user purpose; deployments must now model a second authority axis.
- Human-owned, shared, and externally owned outcomes become assistable without
  being falsely delegated or duplicated inside an assistance contract.
- Roadmap revisions, closures, and negative outcomes become evidence for later
  planning calibration rather than discarded plans.
- Deterministic coverage and WIP policies are less ambitious than immediate
  optimization, but they create a trustworthy dataset before objective weights
  become operational.
- Additional strategic contracts risk architecture sprawl. The first slice is
  deliberately narrower than a project-management or workflow framework.

## Rejected alternatives

- **Create `OutcomeCommitment` beside the existing `Commitment`:** leaves two
  overlapping meanings and forces every consumer to choose between them.
- **Reuse current statuses without versioning:** makes old and new histories
  semantically ambiguous.
- **Treat fulfilled, cancelled, superseded, failed, breached, and suspended as
  sibling states:** conflates lifecycle position with closure reason.
- **Treat every accepted commitment as immediately executable:** confuses the
  existence of a durable obligation with current activation and starts
  long-horizon work prematurely.
- **Use effect policy for intent changes:** lets permission to act become
  permission to choose or erase user purpose.
- **Make a roadmap a large `WorkGraph`:** forces strategy to churn at execution
  speed and turns hypotheses into dispatch state.
- **Let roadmap nodes create work automatically:** turns possibility into
  obligation and bypasses commitment authority.
- **Require every `WorkOrder` to have a roadmap commitment:** breaks direct user,
  incident, maintenance, external-obligation, and endogenous work.
- **Duplicate ownership in `AssistanceEnvelope`:** permits canonical outcome
  roles and intervention constraints to diverge.
- **Start with a learned or weighted portfolio optimizer:** there is no
  calibrated objective or representative execution corpus yet.

## Fitness functions for implementation

- v1 goal/commitment fixtures upcast deterministically to equivalent v2
  projections, and native v2 replay is byte-equivalent;
- legacy `FAILED` commitments upcast to `CLOSED/FAILED`; no migration infers
  `BREACHED` without separate evidence;
- no projection mutates a prior `GoalRevision`, `RoadmapRevision`, commitment
  transition, or terminal closure;
- every admitted goal revision, roadmap revision, and commitment transition uses
  `append_if_head` with the validated cursor; a concurrent append forces reload
  and full revalidation;
- goal and roadmap proposal code cannot import work dispatch, capability
  execution, or the effect plane;
- user/constitutional goal changes fail without sufficient `IntentAuthority`,
  regardless of effect authority;
- a goal's user/constitutional origin cannot be asserted without authenticated
  provenance, including by an otherwise authorized agent;
- delegated intent cannot change a governing goal's kind, origin, owner, or
  lineage in place; derived goals name current governing goal identities;
- a roadmap node cannot produce work directly; every roadmap-derived
  `WorkOrder` carries commitment provenance;
- automatic commitment-derived `WorkOrderProposal` generation requires
  `ACTIVE`, `activation_due`, or prerequisite-lead-time evidence, and execution
  admission requires the commitment to be `ACTIVE`;
- acceptance proves direct user, incident/maintenance, external-obligation, and
  endogenous work can create admitted `WorkOrder` values without roadmaps;
- commitment state and closure reason validate independently, and a closed
  commitment cannot reactivate in place;
- reactivation from suspension requires a new review/revision event;
- new roadmaps, commitments, proposals, admissions, and reactivations reject
  stale governing goal or roadmap revisions;
- new roadmap hypotheses reject terminal governing goals, while commitments,
  activation, and work require `ACTIVE` or `BLOCKED` governing goals so recovery
  work remains possible;
- external roadmap IDs cannot be accepted as Noema work-graph IDs;
- outcome-role assignments remain independent, and assistance envelopes contain
  references rather than duplicate ownership;
- human/external execution requires typed proposal intervention/support within
  the canonical assistance envelope; identity-bound `USER` or `SHARED`
  execution cannot be replaced by unilateral agent action;
- commitment coverage exposes required, covered, and uncovered criteria and is
  `COVERED` only when admitted work from the commitment's current roadmap
  revision and outcome covers every criterion;
- model proposals cannot admit goal, roadmap, commitment, work, or effects;
- initial portfolio code contains no learned optimizer and records every WIP or
  review decision with its inputs;
- all strategic projections rebuild through an explicit canonical cursor and
  reject deterministic cross-object illegality during replay.

Information access, policy composition, artifact retention, and disclosure are
specified separately in
[ADR 0009](0009-information-governance-and-confidential-context.md). Delivery
order and release acceptance are defined in the [roadmap](../ROADMAP.md).

## Implementation

v0.5.1 implements the deterministic contracts, schema-v2 migration, canonical
events, replay projections, intent-authority admission, expected-head CAS,
commitment coverage, roadmap health, external-workstream observations, and the
bounded `WorkOrderProposal` bridge described here. The flagship and structural
fitness functions live in `tests/test_intent.py`.

The merge hardening makes these boundaries structural: derived goals carry
explicit governing lineage and revisioned deadlines; current goal/roadmap cuts
gate new strategic execution; reactivation remaps current revision-scoped
roles and assistance; work proposals declare bounded intervention/support;
coverage is criterion-based; and replay reruns deterministic cross-object
legality independently of the command facade. Legacy synthetic cursors use the
actual preceding canonical head even when durable sequences contain gaps.
The final merge gate additionally excludes terminal-goal strategy, keeps
blocked-goal recovery live, scopes coverage to the current reactivated outcome,
and keys identity-bound action to the executor role.

Goal-coverage optimization, learned allocation, model proposal generation, and
the separate Information Governance runtime remain deferred.
