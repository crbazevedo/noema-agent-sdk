# Architecture

> **Current revision:** 2026-08-31
>
> **Implemented through:** v0.5.1 deterministic Intent & Outcome Stewardship
>
> **Accepted architecture direction; implementation staged:** Information
> Governance and Confidential Context

This document is the current architectural synthesis. It distinguishes shipped
contracts from accepted but unimplemented target architecture so that a design
name never implies implementation. ADRs preserve decision history; later-dated
accepted ADRs supersede earlier conflicting decisions.

## Purpose and name

Noema provides infrastructure for agents that maintain a coherent relationship
with a changing world.

`Noema` is not an acronym. The name refers to the philosophical idea of
something as apprehended or understood from a situated perspective. The name is
architecturally apt without making any claim about machine consciousness: an
agent never acts on “the world itself.” It acts on an evolving,
evidence-bearing, temporally qualified model of its situation.

```text
WORLD → OBSERVATION → EVIDENCE → BELIEF → SITUATION → DECISION
```

The representation is not the world:

```text
agent situation at time t = f(observations, evidence, memory,
                              goals, perspective, time)
```

Two agents may inhabit the same environment yet hold different evidence,
knowledge times, goals, capabilities, and beliefs. Noema preserves those
differences and makes them inspectable rather than collapsing them into one
prompt or one last-write-wins truth.

The system thesis is:

> Durable autonomous agency should be a systems property, not an emergent side
> effect of a long-running LLM loop.

## Design objective

Noema is a general substrate for long-running autonomous systems. It separates:

- world state from model context;
- observations from evidence and beliefs;
- memory from currently trustworthy knowledge;
- goals from roadmaps, commitments, work, plans, and effects;
- outcome ownership from decision ownership, execution, and verification;
- external workstreams from Noema-owned work graphs;
- cognition from effectful capabilities;
- action proposals from authorization;
- capability from competence, information access, and authority;
- individual task value from portfolio opportunity cost;
- source reputation from proposition truth;
- autonomy from opacity;
- agent identity from the cognitive policies it instantiates.

The most important type boundary for the next architecture slice is:

```text
Goal/GoalRevision != Roadmap/RoadmapRevision != Commitment
                  != WorkOrder != PlanProposal
                  != WorkGraph/WorkNode != ActionIntent

IntentAuthority != EffectAuthority
```

An agent's ability to perform a task does not imply that the agent should own
the outcome. A roadmap's presence does not imply that its nodes are commitments.
A lease does not authorize an external effect.

## Two complementary architectural views

Noema has two orthogonal decompositions. The cognitive planes describe how the
agent maintains and uses a situated understanding. The control horizons
describe how user value becomes bounded work and governed effect. Neither view
replaces the other.

### Cognitive planes

```text
PERCEPTION / SUBSTRATE       What is happening and what can be sensed?
            ↓
SITUATION / MEMORY           What is currently believed about reality?
            ↓
AUTONOMIC                    What can be regulated cheaply?
            ↓
AWARE / DELIBERATIVE        What actually deserves thought?
            ↓
GOVERNED EFFECT             What may be done?
            ↓
DEVELOPMENT / METACOGNITIVE How should competence improve over time?
```

These are responsibility and authority boundaries, not required deployment
processes. The Endogenous Drive Ecology crosses the autonomic, aware, and
development planes; it is not a seventh peer plane.

### Control horizons

```text
CONSTITUTIONAL / USER INTENT AND EXTERNAL WORLDS
             │
             ▼
┌──────────────── STRATEGIC / INTENT ─────────────────┐
│ User Outcome Stewardship                            │
│   ownership · assistance · goal coverage            │
│                     ↓                               │
│ Intent & Portfolio Stewardship                      │
│   Goal → GoalRevision → RoadmapRevision → Commitment│
└────────────────────────┬────────────────────────────┘
                         ▼
┌──────────────── TACTICAL / WORK ────────────────────┐
│ WorkOrder → PlanProposal → WorkGraph                │
│ ReadyFrontier → WorkerMatcher → WorkLease           │
└────────────────────────┬────────────────────────────┘
                         ▼
┌─────────────── OPERATIONAL / EFFECT ────────────────┐
│ ActionIntent → policy / authority → typed capability│
└─────────────────────────────────────────────────────┘

INFORMATION GOVERNANCE crosses every box:
lineage · composition · internal access · retention · disclosure
```

The horizons operate at different rates. A user goal may last years, a roadmap
months and change weekly, a commitment days or weeks, a work graph hours, and an
action seconds. Conflating them makes either strategy too volatile or execution
too rigid.

The cognitive path and control horizons intersect at explicit contracts:
situation and memory inform goal and roadmap health; orientation gates work and
effects; attention and endogenous inquiry decide what deserves cognition; work
produces action proposals; all derived context remains subject to information
policy.

## Implemented foundation: User Outcome Stewardship

v0.5.1 implements independent outcome roles, role-referencing assistance
envelopes, epistemic external-workstream observations, and deterministic
commitment coverage. Richer goal-coverage intervention policy remains a later
extension over these contracts.

Noema optimizes for user goal achievement, not for the amount of work performed
by agents. Every meaningful outcome or commitment carries four independent
roles:

| Role | Responsibility |
|---|---|
| Outcome owner | Ultimately accountable for the outcome |
| Decision owner | Holds the legitimate authority or judgment to decide |
| Executor | Performs some or all of the work |
| Verifier | Determines whether the success criteria were met |

The roles may be held by the user, Noema, another human, an external system, or
a combination. They must not be inferred from one another.

### Execution locus and assistance envelope

`ExecutionLocus` distinguishes `USER`, `AGENT`, `SHARED`, `EXTERNAL_HUMAN`, and
`EXTERNAL_SYSTEM`. `SHARED` alone is too vague, so an `AssistanceEnvelope`
references the canonical outcome-role assignment and constrains:

- maximum intervention: prepare, propose, co-execute, or act;
- identity-bound, physical-presence, relationship, institutional, and
  user-development constraints;
- permitted agent work and required user work;
- required checkpoints and verification;
- reversibility, risk, privacy, and attention budgets.

Non-delegable does not mean non-assistable. Noema may research, prepare,
simulate, remind, draft, retrieve, and analyze around a human-owned interview,
negotiation, attestation, relationship, or physical act without pretending to
perform or own it.

### Goal coverage and intervention policy

`GoalCoverage` projects how valuable required work is covered by the user,
Noema, and external participants and identifies the uncovered gap. The
selection question is:

> What important part of the user's goals is insufficiently covered, and what
> is the least intrusive effective intervention?

Candidate interventions include act, co-execute, prepare, propose, ask one
high-value question, surface a human decision, defer, or do nothing. A baseline
objective is incremental expected goal value minus user attention, privacy,
risk, financial, resource, coordination, and dependency costs, subject to hard
policy and ownership constraints.

This intentionally rejects “automation rate,” agent utilization, token volume,
and task count as top-level objectives.

## Implemented: Intent & Portfolio Stewardship

This layer preserves **intentional continuity** above the implemented Work
Control Plane:

> What was being pursued, why was it committed, how was it expected to succeed,
> and do current goals and evidence still justify it?

### Existing contracts and intent authority

This architecture evolves the existing `Goal` and `Commitment` situation
contracts; it does not introduce parallel meanings. `Goal` retains stable
identity while immutable `GoalRevision` values are the semantic contract for
user intent history; canonical events durably represent admitted revisions.
Each revision carries authenticated origin/provenance and a `GoalKind`. An agent
cannot label its own generated goal `USER_AUTHORED` or `CONSTITUTIONAL` without
authenticated provenance establishing that origin. Legacy `goal.updated` and
`commitment.*` histories require schema-v2 upcasters and compatibility fixtures.

`IntentAuthority` is independent from `EffectAuthority`. Constitutional and
user-authored goals cannot be rewritten, reprioritized, or retired by an agent
merely because the agent may perform effects. Agent-proposed instrumental,
epistemic, maintenance, and exploratory goals remain subordinate to governing
constitutional/user intent.

### Roadmaps are hypothesis graphs

A `Roadmap` has a stable identity and immutable `RoadmapRevision` values. Each
revision contains outcome nodes, governing goal references, approximate
dependencies, success criteria, assumptions, confidence, resource envelope,
planning horizon, causal cursor, author, and revision reason.

A roadmap is a durable, revisable hypothesis about how goals might be achieved.
It is not a work graph:

| Roadmap | Work graph |
|---|---|
| Outcome and capability thresholds | Concrete bounded work |
| Approximate strategic dependencies | Admitted executable dependencies |
| Assumptions and confidence | Readiness prerequisites and leases |
| Revised when strategy changes | Replanned as execution changes |
| Creates no obligation | Exists because a `WorkOrder` was admitted |

Revisions supersede; they never rewrite or erase prior hypotheses. The current
roadmap, its history, goal-scoped views, and health are projections of canonical
events, not a separate project-management database.

### Roadmap is not commitment

Only an explicit `Commitment` turns a roadmap possibility into a durable
roadmap-derived obligation. The existing contract evolves through schema v2;
its lifecycle position is distinct from why it closed:

```text
state:
    PROPOSED → ACCEPTED → ACTIVE ↔ SUSPENDED → CLOSED

closure_reason:
    FULFILLED | CANCELLED | SUPERSEDED | FAILED | BREACHED
```

The proposed legacy mapping is `OPEN → ACCEPTED`, `IN_PROGRESS → ACTIVE`,
`COMPLETED → CLOSED/FULFILLED`, `FAILED → CLOSED/FAILED`, and
`CANCELLED → CLOSED/CANCELLED`. Failure does not assert the stronger breach
claim. Every transition is durable and upcastable. Closure removes an item from
the active portfolio but never erases its history.

An `ACCEPTED` strategic commitment creates an obligation; `ACTIVE` means that
execution is currently eligible. `CommitmentCoverage` measures both without
starting future work prematurely. Automatic `WorkOrderProposal` generation
requires an active commitment, an activation-due condition, or prerequisite
lead-time evidence; commitment-derived execution still requires an authorized
transition to active. An uncommitted roadmap node may not produce work.

This is not a universal work chain. Immediate user instructions, incidents,
maintenance requirements, existing external obligations, and endogenous
inquiries may create provenance-bearing `WorkOrder` values without inventing a
roadmap commitment:

```text
RoadmapNode → Commitment ───────────┐
Immediate User Instruction ────────┤
Existing External Obligation ──────┤
Incident / Maintenance Requirement ┤→ WorkOrder
Endogenous Inquiry ────────────────┘
```

### Roadmap health and reactivation

`RoadmapHealth` derives at least goal alignment, assumption validity,
dependency validity, schedule feasibility, capacity fit, progress consistency,
and opportunity validity. Goal change, contradicted assumptions, new evidence,
large variance, external change, or a new opportunity normally moves a roadmap
to `NEEDS_REVIEW`, not deletion.

The continuity rule is:

```text
REACTIVATE != RESUME
```

Reactivating a suspended direction re-evaluates current goals, assumptions,
dependencies, completed work, capabilities, deadlines, and external conditions,
then creates a new revision and renewed commitment if warranted. The old path
becomes evidence for the new one.

Models may emit `GoalRevisionProposal` and `RoadmapRevisionProposal` values.
Deterministic validation plus `IntentAuthority` and policy check goal
references, graph legality, sourced priority changes, commitment preservation,
history preservation, assumptions, and resource bounds before admission. Every
causally validated strategic transition captures canonical head `H`, validates
through `H`, and uses `append_if_head(..., H)`; a concurrent append forces reload
and revalidation rather than admitting a stale transition.

### External workstreams

An employer, institution, person, or third-party system may own its roadmap.
Noema represents that through an `ExternalWorkstream` containing source-of-truth
identity, user and Noema roles, observed roadmap reference, provenance,
confidence, and freshness.

```text
external roadmap / milestone (observed belief)
                   ↓ support gap
Noema Commitment → WorkOrder → WorkGraph (Noema-owned work)
```

`ExternalRoadmap != NoemaWorkGraph`. An external executive review may cause
Noema to prepare research, options, or notes; the meeting and external decision
remain outside Noema unless authority is explicitly transferred.

### Portfolio observability before optimization

The first slice makes goal value, commitment strength, urgency, critical-path
pressure, success estimates, coordination cost, context affinity, verification
capacity, WIP, scarce competence, and information-access requirements
representable and observable. It implements deterministic review and WIP
policies only. Portfolio optimization remains a separate research program until
real trajectories calibrate its objective.

## Accepted architecture direction: Information governance and confidential context

Information governance is separate cross-cutting infrastructure specified in
[ADR 0009](adr/0009-information-governance-and-confidential-context.md), not a
subsystem of portfolio stewardship. An `InformationPolicy` separates:

- origin and security domain;
- sensitivity/classification;
- allowed purposes;
- local and remote processing policy;
- permitted recipients and disclosure forms;
- cross-agent sharing;
- retention and deletion requirements;
- declassification authority.

Two items with the same sensitivity may have different origin, purpose,
retention, access, and disclosure constraints. `PolicyComposition` applies
field-specific semantics: classification takes the least-permissive lattice
value; purposes, recipients, localities/providers, and sharing scopes intersect;
retention produces effective constraints plus explicit conflicts that are
evaluated for the requested operation. A legal hold can deny deletion without
automatically denying a separately permitted legal-review read. Unknown or
incompatible permissions relevant to an operation fail that operation closed.

### Quarantine before classification

Unknown policy never implies ordinary processing permission:

```text
RAW INGEST → QUARANTINED → local/policy-safe classification
           → InformationPolicy resolved → normal derivation
```

Until policy is resolved, content cannot reach external models or connectors,
cross-domain agents, shared indexes, or content-bearing telemetry. Classification
runs only within the default quarantine locality/trust policy or requires human
review.

### Restriction inheritance

Derived knowledge inherits the composed source policy:

```text
Artifact → Observation → Evidence → Assertion → Summary
         → Roadmap/Plan → Work Context → Output
```

Redaction and abstraction are provenance-bearing transformations, not
declassification. They first produce a `DisclosureView` under the composed
source policy. Only an explicit `DeclassificationDecision`, authorized under
every governing source policy, may grant a less restrictive disclosure policy.
A user may always tighten treatment but may lack authority to loosen employer,
contractual, institutional, or legal restrictions.

### Raw artifacts and canonical events

The event log remains canonical for causal and semantic history, but it must not
become an immutable secret dump. Raw documents, audio, images, transcripts, and
credentials live in a policy-governed encrypted `ArtifactStore`. Canonical
events contain artifact references, digests, classifications, provenance,
retention/tombstone state, and appropriate semantic claims. Credentials appear
only as secret references. Protection covers the entire event envelope: IDs,
subjects, correlation identifiers, metadata, tags, filenames, exception text,
and other indexing fields use opaque identifiers by default or are themselves
policy-governed and access-controlled. Small or low-entropy protected values use
keyed or otherwise dictionary-resistant digests.

This boundary reconciles event immutability with retention and erasure duties:
events preserve that an artifact existed and what governed transformations were
performed; the artifact store controls access and recoverability of raw bytes.

### Internal access, capsules, and disclosure

A target ingestion path is:

```text
user drop → quarantine → policy-safe classification → InformationPolicy
          → raw artifact store → policy-allowed extraction
          → observations/evidence → semantic memory → SituationCapsule views
```

Extraction does not silently create commitments. A transcript statement is a
reported candidate with provenance until commitment policy admits it.

`SituationCapsule` is the normal reasoning unit: claims, decisions, candidate
commitments, changed priorities, risks, questions, entity and evidence
references, valid and knowledge time, plus effective information policy.
Full, redacted, and abstracted views can share lineage.

Governance has two mandatory boundaries. `InformationAccessDecision` controls
internal event/projection views, retrieval, context assembly, worker visibility,
and index/cache reads. `DisclosureDecision` controls movement across a trust
boundary through models, tools, connectors, inter-agent messages, or outputs.
The distinction follows trust domains, not object type: a trusted local model or
parser may need access only, while a remote model or SaaS tool needs both access
and disclosure. Every recorded decision pins an immutable `AccessContext` and
`PrincipalSnapshot`, including actor, roles/groups, purpose, operation,
recipient, time, policy versions, lineage, trust domains, and relevant provider
posture. Direct event-store access is privileged infrastructure, not ordinary
worker visibility.

Both boundaries cover semantic events, memory retrieval, prompts and responses,
work contexts, telemetry, traces, logs, error reporting, caches, embeddings,
vector and lexical indexes, replay fixtures, evaluation artifacts, artifact
stores, connectors, tools, protocols, and outputs.

Durable security meaning—policy versions, lineage, declassification, artifact
lifecycle, durable grants/revocations, material disclosures, and material
denials—belongs in canonical semantic history. High-volume enforcement
occurrences—routine retrieval checks, cache/index reads, permitted disclosures,
and individual remote-model/tool transfers—produce bounded security audit
receipts outside ordinary situation projection. The receipts may share physical
event infrastructure but are never a second authorization source of truth.

Worker eligibility therefore requires all of:

```text
capability ∧ competence ∧ fresh availability ∧ information access
```

Information access remains separate from authority. A trusted local worker may
act as a privacy intermediary: abstract a protected problem, send only the
authorized disclosure view to an external specialist, then privately
recontextualize the generic result.

## Implemented: Event-sourced kernel

The event log is canonical. Every event is persisted before it is projected or
delivered.

```text
emit(event)
  1. append to store
  2. assign sequence
  3. project into situation
  4. publish to subscribers
```

This order gives deterministic replay and lets agents deliberate over a
situation that already contains the triggering observation. Every envelope
carries a schema version. Deterministic upcasters adapt old payloads at
read/projection time without rewriting canonical history.

Durable consumers record progress through generic `ConsumerCheckpoint` events.
The checkpoint is written only after required derived observations. Restart
replays later canonical triggers, while deterministic output IDs make partial
prior attempts idempotent. Checkpoint projections expose event-stream lag; they
do not replace the event log with a second offset store.

## Implemented: Persistent cognitive memory

The event log records occurrences; it is not itself a belief table. Persistent
memory derives three separate layers:

```text
event → evidence relation → semantic assertion → bitemporal belief query
```

`SemanticAssertion` versions are immutable. They carry epistemic provenance,
source/derivation anchors, valid-world time, recorded-knowledge time, freshness,
confidence, and hypothesis/active status. `EvidenceLink` is the sole graph
describing how resolved evidence bears on a claim. Supersession and validity
closure are later events, never row updates. Conflicting visible assertions
remain present and make the projected belief uncertain.

The [memory architecture](PERSISTENT_COGNITIVE_MEMORY.md) uses the same generic
checkpoint contract as other durable consumers. Local lexical and future
FTS/vector indexes are rebuildable accelerators; canonical assertions and
evidence remain authoritative. A same-process write failure rebuilds
speculative state through the last durable checkpoint before retry.

## Implemented: Situated continuity

Memory reconstruction does not prove that a mutable world remained unchanged
while the process was inactive. Every wake is an epistemic reconstruction:

```text
canonical replay → freshness decay → awareness gaps → budgeted refresh
                 → bitemporal reconciliation → orientation report
```

`AwakeEpoch` records the sleep interval, canonical cursors, and orientation
status. Provider-neutral `SourceState` values expose durable source cursor,
hazard, confidence, and observation cost. Per-wake `AwarenessDemand` values
carry governing goals, relevance, decision sensitivity, and required
freshness/confidence. `WakeReconciler` is a pure planner over requirement gaps;
`FakeSource` is the only v0.4 observation adapter. The orientation barrier is
shadow-only and cannot reach models, authority, capabilities, or effects.

Delayed observations retain the event-envelope contract: `Event.timestamp` is
when Noema observed the report, while `payload.occurred_at` is source-reported
world time. Memory maps them to knowledge and valid time. Each wake rebuilds
continuity and memory from one canonical history cut. Source states, wake
epochs, observations, assertions, and reports are canonical events; freshness,
coverage, plans, and barrier decisions are projections. Runtime latency is
telemetry, not canonical report identity.

See [Situated Continuity](SITUATED_CONTINUITY.md) and
[ADR 0006](adr/0006-situated-continuity-foundation.md).

## Implemented: Durable work coordination

v0.5 adds the minimum durable control plane between goals and effects:

```text
Goal → WorkOrder → FakePlanner → PlanProposal → PlanValidator → WorkGraph
                                                      ↓
                               completions → ReadyFrontier → WorkerMatcher
                                                      ↓
                                                 WorkLease
```

A goal is not a work order; a work order is not a plan; a proposed plan is not
an accepted graph; a work node is not an `ActionIntent`. The planner receives
capability types but no agent identity, competence, load, credentials, or
authority policy. It proposes structure only. `PlanValidator` owns DAG legality
and graph admission; dependency waves derive from canonical completions.

`CapabilityManifest` records declarations, `AgentPresence` expires explicitly,
and `CompetenceEstimate` records seeded or evidence-ready estimates. Only seeded
estimates are operational in v0.5. `AuthorityLevel` remains a separate ceiling.
Independent verification is ordinary downstream work whose matcher excludes
the worker recorded as completing its target.

`WorkLease` grants carry increasing fencing tokens. Grant, completion, expiry,
and invalidation are canonical events; `WorkProjection` is rebuildable.
Completion and expiry share a terminal event identity per lease. Completion
legality uses coordinator acceptance time, not claimed worker finish time.
Planning capability inputs replay through the proposal's exact causal cut. A
later declared causal-state change invalidates the active graph without erasing
completed artifacts.

`ReadyFrontier` evaluates source freshness/confidence prerequisites through
Situated Continuity. This controls work readiness but does not authorize
effects; effects still require `ActionIntent`, policy, and a typed capability.

See [Durable Work Coordination](DURABLE_WORK_COORDINATION.md) and
[ADR 0007](adr/0007-durable-work-coordination.md).

## Implemented: Portable durability

Noema has one semantic runtime with two deployment profiles:

```text
embedded                         distributed
SQLite event store               PostgreSQL event store
in-process event bus             transactional outbox → NATS JetStream
single runtime                   durable inbox → one or more runtimes
```

In distributed mode, committing an event and outbox record is one database
transaction. Publisher and consumer use renewable fenced leases. Delivery is
at least once: event IDs deduplicate runtime observations, while a stable
idempotency key crosses the capability boundary for external effects. A broker
transports events; it is never canonical history.

The same application policy and capability code runs in either profile. If
concurrent publishers deliver sequences out of order, the receiving kernel
rebuilds its situation projection from canonical database order before
notifying local subscribers about the late event. Broker history present at
startup is not treated as a new stimulus.

## Autonomic, endogenous, and deliberative regimes

Noema has implemented the effect-free foundation of a signal-first
[Autonomic Fabric](AUTONOMIC_FABRIC.md). Cheap semi-independent rule cells
observe narrow event and situation slices, record deterministic activations,
and produce hypothetical expiring signals. A continuous observational worker
runs those cells through the canonical event substrate and records what would
have signaled, woken, or been suppressed without enacting the decision.

The fabric does not create a second effect path. A bounded reflex may propose
an `ActionIntent`, but critics, policy, authorization, idempotency, and typed
capabilities remain mandatory. Learned policies are immutable typed data,
never arbitrary executable code.

The planned [Endogenous Drive Ecology](ENDOGENOUS_DRIVE_ECOLOGY.md) adds a
second governed source of cognitive demand: questions, belief/goal/roadmap
maintenance, calibration, preparedness, and bounded simulation when no
external event warrants thought. Exogenous and endogenous demand compete for
one finite aware workspace. Internal initiative remains subordinate to
constitutional, user, mission, and commitment goals and creates proposals more
readily than actions.

## Situation graph and agent cycle

The built-in situation projection supports facts, entities, typed relations,
goals, commitments, risks, opportunities, and named resources. Applications
can register custom projectors without modifying the kernel.

```text
material event → snapshot → deliberate → critique / falsify
               → score action portfolio → authorize → execute capability
               → observe result → emit facts/events → reflect
```

Each transition is persisted. On restart, an agent rebuilds successful
idempotency keys and reconstructs authorized actions with no terminal outcome.
Only idempotent capabilities retry automatically; non-idempotent actions are
durably abandoned for explicit reconciliation and new authorization.

## Model boundary

Model providers implement a small provider-neutral request/response contract. A
context assembler selects a bounded situation view and, in the target
information architecture, applies an internal `InformationAccessDecision`
before dispatch and a `DisclosureDecision` when the provider crosses a trust
boundary. Structured model output is schema-validated into a proposal such as
`ActionIntent`, `GoalRevisionProposal`, or `RoadmapRevisionProposal`, then passes
through the same deterministic validation and governance as non-model proposals.
Models never receive capability credentials, intent authority, or canonical
mutation authority.

## Async and multi-agent semantics

- per-subscription FIFO delivery is guaranteed;
- subscribers execute independently and one failure does not crash the bus;
- agent workers consume bounded priority queues;
- actions are concurrency-limited independently from deliberation;
- capability timeouts, retries, and idempotency are explicit;
- scheduled events create autonomous internal stimuli;
- distributed delivery uses leases and fencing to reject stale acknowledgments;
- agents coordinate through events, not direct hidden calls;
- agents may differ in reasoners, critics, capabilities, authority, risk,
  attention, trigger filters, beliefs, and—in the target design—information
  access.

## Quality-attribute scenarios

| Attribute | Scenario and required response |
|---|---|
| Recoverability | Kill any runtime during projection, planning, leasing, or action recovery; canonical replay reconstructs one legal semantic state and does not duplicate an effect. |
| Epistemic integrity | Receive late and conflicting evidence; retain occurrence, provenance, valid time, knowledge time, contradiction, and current uncertainty. |
| Situational safety | Wake after a long absence with one unavailable critical source; expose insufficient orientation and block dependent consequence without pretending certainty. |
| Intentional integrity | Change a governing goal or refute a roadmap assumption; preserve the old goal/roadmap revisions, require intent authority, and suspend or supersede commitments explicitly. |
| Reactive compatibility | Admit a direct user, incident, maintenance, external-obligation, or inquiry `WorkOrder` without manufacturing a roadmap commitment. |
| Human agency | Give Noema a technically executable but identity-bound decision; preserve user ownership while preparing permitted support work inside the assistance envelope. |
| Confidentiality | Derive a summary and work plan from a protected artifact; typed policy composition blocks unauthorized internal retrieval and external disclosure, and redaction alone does not declassify it. |
| Modifiability | Replace a model, broker, store, planner, sensor, or optimizer; stable domain contracts and acceptance semantics remain unchanged. |
| Auditability | Reconstruct why the system believed, refreshed, prioritized, committed, delegated, authorized, disclosed, and acted from canonical history and policy versions. |
| Performance | Process a million-event life while keeping expensive cognition sparse and projections rebuildable; indexes and snapshots may accelerate but never become authority. |
| Adoptability | Run the same application locally without network services and distributed without application-level policy branches. |

## Risks, tradeoffs, and sensitivity points

| Area | Tradeoff or risk | Sensitivity point / mitigation |
|---|---|---|
| Strategic model size | Outcome, intent, and work separation adds events and projections. | Keep each contract narrow; reject a generalized workflow/portfolio language until repeated use justifies it. |
| Schema evolution | Existing Goal and Commitment meanings can diverge from accepted strategic semantics. | Explicit schema v2, deterministic upcasters, legacy fixtures, and separate commitment state/closure reason. |
| Intent authority | An effect-capable agent may attempt to redefine governing goals. | Independent `IntentAuthority`; constitutional/user goals require matching authority for revision. |
| Roadmap health | Poor weights can cause churn or strategic inertia. | Begin with transparent deterministic features and shadow evaluation; do not learn the objective before collecting outcomes. |
| Goal optimization | Proxy metrics can reward busyness or remove valuable human learning. | Hard ownership and assistance envelopes; optimize incremental goal value under explicit constraints, never task count alone. |
| Portfolio scheduling | Maximum concurrency can reduce throughput through coordination and review bottlenecks. | First implement deterministic WIP/review policies and observation; defer optimization until trajectories calibrate the objective. |
| External truth | Mirroring outside roadmaps can drift or falsely claim authority. | Explicit source of truth, observation time, confidence, freshness, and `ExternalRoadmap != NoemaWorkGraph`. |
| Information composition | Different policy dimensions have no shared total order. | Typed field-specific composition; incompatible, empty, unknown, or unresolved combinations fail closed. |
| Immutable history | Raw confidential bytes can conflict with retention or erasure. | Put raw bytes in a governed artifact store; canonical events hold references, lineage, classifications, and tombstones. |
| Abstraction | A supposedly safe abstraction may retain identifying structure. | Transformation retains source policy; only a separately authorized declassification decision may loosen it. |
| Rebuild cost | Event-only projections can become expensive at scale. | Disposable verified snapshots and indexes pinned to canonical cursors; never a second writable source of truth. |
| Learned habits | Compression can hide regret or bypass novelty. | Counterexamples, replay, collision analysis, shadow/canary stages, drift and novelty escape paths. |

The most sensitive future decisions are the algebra for policy inheritance, the
threshold for roadmap review, the intervention objective, declassification
authority, and portfolio resource allocation. They require real execution data
and adversarial acceptance scenarios before learned control is permitted.

## Fitness functions and structural gates

Implemented invariants are enforced in `tests/test_architecture.py`, schema and
replay tests, distributed fault tests, and subsystem acceptance tests.
Documentation alone is not enforcement.

The v0.5.1 stewardship implementation adds gates that prove:

- legacy Goal and Commitment histories upcast deterministically to equivalent
  schema-v2 projections;
- legacy commitment failure maps to `CLOSED/FAILED`, never to breach without
  separate evidence;
- every goal revision, roadmap revision, and commitment transition is admitted
  through `append_if_head` at its validated cursor;
- user/constitutional goal kind requires authenticated provenance;
- no roadmap node creates work directly; roadmap-derived work carries commitment
  provenance and execution requires an active commitment, while direct user,
  incident/maintenance, external-obligation, and endogenous work remain
  admissible without roadmaps;
- proposal code cannot admit goals, roadmaps, commitments, work graphs, or
  effects;
- user/constitutional goal changes fail without `IntentAuthority`, regardless
  of effect authority;
- prior goal/roadmap revisions and commitment transitions cannot be overwritten
  or silently omitted;
- commitment lifecycle state and closure reason validate independently;
- reactivation requires a new orientation/revision event;
- external roadmap observations cannot masquerade as Noema graph state;
- outcome owner, decision owner, executor, and verifier are independently
  represented and validated;
- assistance envelopes reference role assignments and cannot duplicate
  ownership;
- first-slice portfolio code contains no learned optimizer and records every WIP
  or review decision with its inputs.

The staged information-governance implementation must add gates that prove:

- every policy dimension has field-specific composition tests and incompatible
  or unresolved permissions fail the affected operation closed without denying
  unrelated permitted operations;
- unresolved inputs remain quarantined from external providers, cross-domain
  agents, shared indexes, and content-bearing telemetry;
- worker matching cannot infer information access from competence or authority;
- derived objects cannot have a less restrictive effective policy without an
  authorized `DeclassificationDecision` satisfying every source policy;
- redaction and abstraction initially retain the composed source policy;
- event/projection access, retrieval, context assembly, workers, caches, and
  indexes pass through `InformationAccessDecision`;
- model/tool access passes through `InformationAccessDecision`, and every path
  that crosses a trust domain also passes through `DisclosureDecision`;
- telemetry, traces, logs, errors, caches, embeddings/indexes, replay fixtures,
  and evaluation artifacts have leakage gates;
- raw artifact bytes, credentials, and ungoverned protected content cannot enter
  any canonical event-envelope field;
- decisions pin immutable access/principal context for replay;
- routine permitted transfers produce bounded audit receipts while durable
  grants, material disclosures, and material denials remain canonical;
- every projection rebuilds from a declared canonical cursor and emits
  byte-equivalent semantic state for identical history.

See [Architecture principles](ARCHITECTURE_PRINCIPLES.md) for current release
invariants.

## Extension points

| Concern | Interface |
|---|---|
| Reasoning | `Reasoner` |
| Independent review | `Critic` |
| Effects | `Capability` |
| Situation inference | `SituationDetector` |
| Authorization | `PolicyRule` / `PolicyEngine` |
| Persistence | `EventStore` |
| Distributed transport | `EventBroker` |
| Model inference | `ModelProvider` |
| Model context | `ContextAssembler` |
| Telemetry and tracing | `TelemetrySink` / `Tracer` |
| Durable consumer progress | `ConsumerCheckpoint` / projection |
| Observational autonomic runtime | `AutonomicShadowWorker` |
| Epistemic memory | `SemanticAssertion` / `EvidenceLink` / `MemoryProjection` |
| Decision-relevant retrieval | `MemoryRetriever` / disposable index adapters |
| Wake-time temporal semantics | `TemporalService` / `AwakeEpoch` |
| Selective source refresh | `SourceState` / `AwarenessDemand` / `WakeReconciler` |
| Situated orientation | `AwarenessCoverage` / `OrientationReport` / `OrientationBarrier` |
| Durable work identity and planning | `WorkOrder` / `PlanProposal` / `WorkGraph` / `PlanValidator` |
| Work readiness and assignment | `ReadyFrontier` / `WorkerMatcher` / `WorkLease` |
| Agent ecology | `AgentPresence` / `CapabilityManifest` / `CompetenceEstimate` |
| Endogenous cognition (planned) | `Inquiry` / `IntrinsicActivity` |
| User outcomes | outcome roles / `ExecutionLocus` / `AssistanceEnvelope` / commitment coverage |
| Intent and portfolio | `GoalRevision` / `IntentAuthority` / `RoadmapRevision` / `Commitment` / coverage and health projections |
| External work | `ExternalWorkstream` / support-demand projection |
| Information governance (accepted; staged) | `InformationPolicy` / `PolicyComposition` / access and disclosure decisions / `ArtifactStore` |

## Non-goals of the core

The core does not choose a model provider, vector database, prompt format,
personality, fixed reasoning loop, cloud platform, project-management product,
or human-approval UI. It does not ingest every aspect of the user's world into
one global context, own an external institution's truth, maximize agent
activity, erase human responsibility, or infer permission from competence.

Those choices belong in adapters, deployments, applications, or explicit user
policy.

## Decision record

- [ADR 0001](adr/0001-portable-durable-agent.md): portable durable agent;
- [ADR 0002](adr/0002-autonomic-fabric.md): signal-first Autonomic Fabric;
- [ADR 0003](adr/0003-endogenous-drive-ecology.md): governed endogenous drive
  ecology;
- [ADR 0004](adr/0004-durable-consumer-checkpoints.md): canonical durable
  consumer checkpoints;
- [ADR 0005](adr/0005-persistent-cognitive-memory.md): persistent cognitive
  memory;
- [ADR 0006](adr/0006-situated-continuity-foundation.md): situated continuity;
- [ADR 0007](adr/0007-durable-work-coordination.md): durable work coordination;
- [ADR 0008](adr/0008-intent-and-outcome-stewardship.md): implemented
  deterministic intent, user outcomes, external work, and coverage foundation;
- [ADR 0009](adr/0009-information-governance-and-confidential-context.md):
  accepted, staged information governance and confidential context.

See the [roadmap](ROADMAP.md) for delivery order and release acceptances.
