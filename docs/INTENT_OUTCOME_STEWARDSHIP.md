# Intent & Outcome Stewardship

v0.5.1 adds the smallest deterministic strategic layer above Durable Work
Coordination. It preserves why bounded work exists, who owns the real-world
outcome, and whether an obligation is merely accepted for the future or active
now.

The semantic chain is:

```text
Goal
  → GoalRevision
  → Roadmap / RoadmapRevision
  → Commitment
  → CommitmentCoverage
  → WorkOrderProposal / admitted WorkOrder
  → Durable Work Coordination
```

These contracts are not substitutable:

```text
Goal/GoalRevision
!= Roadmap/RoadmapRevision
!= Commitment
!= WorkOrder
!= PlanProposal
!= WorkGraph/WorkNode
!= ActionIntent

IntentAuthority != EffectAuthority
```

## Contracts

`Goal` remains the stable public identity and current situation view.
`GoalRevision` is immutable strategic history. A revision records description,
priority, utility, success criteria, owner, status, `GoalKind`, authenticated
origin provenance, governing `IntentAuthority`, causal cursor, author, and
revision reason.

`StrategicTrust` is the authentication boundary. The deterministic
`StaticStrategicTrust` fixture admits only exact preconfigured provenance and
authority values. Deployments can implement the same port with their own
authentication mechanism. A claimed user-authored or constitutional origin
does not become canonical merely because an agent serialized the right label.

`Roadmap` is a stable identity projected across immutable `RoadmapRevision`
values. A revision is a causally pinned hypothesis graph containing outcome
nodes, assumptions, confidence, approximate dependencies, success criteria,
and a resource envelope. It has no dispatch or effect operation.

The existing `Commitment` contract now separates lifecycle from closure:

```text
PROPOSED → ACCEPTED → ACTIVE ↔ SUSPENDED → CLOSED

FULFILLED | CANCELLED | SUPERSEDED | FAILED | BREACHED
```

`ACCEPTED` means an obligation exists. `ACTIVE` means commitment-derived work
may enter execution. An activation-due or prerequisite-lead-time commitment
may produce a `WorkOrderProposal`, but that proposal cannot be admitted as an
executable `WorkOrder` until an authorized transition makes the commitment
active.

`OutcomeRoleAssignment` stores outcome owner, decision owner, executor, and
verifier as four independent actor references. `AssistanceEnvelope` points to
that assignment instead of copying ownership and constrains the maximum
intervention, identity/physical/relationship/institutional boundaries, human
work, permitted support, checkpoints, reversibility, risk, privacy, attention,
and user-development value.

`ExternalWorkstream` is an immutable epistemic observation with explicit
source-of-truth identity, provenance, valid time, knowledge time, confidence,
freshness, user role, Noema role, and internal support demand. An external
roadmap ID cannot be accepted as a Noema work-graph ID.

`PortfolioSignals` records the inputs needed for later allocation research:
goal value, commitment strength, urgency, critical-path pressure, success
estimate, cost, coordination cost, context affinity, verification capacity,
WIP, scarce-competence pressure, and future information-access requirements.
v0.5.1 verifies canonical WIP and applies a transparent limit; it does not
optimize these signals.

## Canonical events and projections

| Canonical event | Durable meaning |
|---|---|
| `intent.goal_revision_recorded` | One admitted immutable goal revision |
| `intent.roadmap_revision_recorded` | One admitted immutable roadmap hypothesis |
| `intent.commitment_recorded` | One strategic obligation identity and initial lifecycle state |
| `intent.commitment_transitioned` | One authorized lifecycle or closure transition |
| `intent.outcome_roles_recorded` | Independent ownership, decision, execution, and verification roles |
| `intent.assistance_envelope_recorded` | Intervention constraints referencing canonical roles |
| `intent.external_workstream_observed` | One bitemporal observation of externally controlled work |
| `intent.work_order_proposed` | One bounded, provenance-bearing work proposal |
| `work.order_recorded` | Existing v0.5 admission of bounded work |

`StrategicProjection` rebuilds goal and roadmap histories, current commitment
state and transitions, role and assistance views, external observation history,
pending/admitted proposals, `CommitmentCoverage`, and `RoadmapHealth`. These are
not separately writable project-management records.

Every native strategic event records the exact validated head in its envelope.
Replay rejects missing or inconsistent admission evidence.

## Atomic admission

Every causally validated mutation uses the kernel's existing expected-head
primitive:

```text
capture H
→ rebuild and validate through H
→ append_if_head(event, H)
    ├── success
    └── ConcurrentAppend → reload → full revalidation
```

There is no separate strategic lock or transaction mechanism. A concurrent
relevant goal revision causes the losing command to fail after reload instead
of being silently rebased over newer user intent.

## Compatibility migration

Stored legacy events retain schema version 1. The default kernel registers pure
projection-time upcasters for `goal.created`, `goal.updated`,
`commitment.created`, `commitment.updated`, and the three legacy terminal
events. Stored identity and sequence never change.

Legacy commitments map deterministically:

```text
OPEN        → ACCEPTED
IN_PROGRESS → ACTIVE
COMPLETED   → CLOSED / FULFILLED
FAILED      → CLOSED / FAILED
CANCELLED   → CLOSED / CANCELLED
```

Legacy Goal history receives `LEGACY_UNCLASSIFIED` kind and
`LEGACY_UNVERIFIED` origin. Migration never upgrades an old source string into
authenticated user or constitutional provenance, and legacy failure never
becomes breach.

The built-in situation model continues to expose current Goal and Commitment
views for existing consumers. The strategic projection adds immutable history;
it does not create a second semantic source of truth.

## Work bridge and direct work

Only `IntentStewardCoordinator.propose_work_for_commitment()` creates
roadmap-derived proposals. Its resulting `WorkOrder.created_from` includes the
commitment, roadmap revision, and outcome node. Admission requires the
commitment to be active and emits the unchanged v0.5 `work.order_recorded`
event. `FakePlanner`, `PlanValidator`, `WorkGraph`, matching, leases, authority,
and effects remain unchanged.

Commitment is not the universal source of work. These origins remain valid
without manufacturing a roadmap:

```text
Immediate User Instruction ────────┐
Incident / Maintenance ────────────┤
External Obligation ───────────────┤→ WorkOrder
Endogenous Inquiry ────────────────┘
```

## Acceptance and deferrals

`tests/test_intent.py` proves immutable revisions, legacy replay, authenticated
origin rejection, hypothetical roadmap nodes, accepted future commitments,
activation-due proposal gating, active coverage, mixed human/agent/external
roles, assistance boundaries, external support changes, direct work origins,
goal reprioritization, reactivation through reorientation, v0.5 causal
invalidation, a post-validation CAS race, and deterministic replay.

This slice does not implement model-backed roadmap planning, learned goal
generation, portfolio optimization, RDDL/MDP scheduling, adaptive oversight,
habit or skill forging, Information Governance runtime, confidential ingestion,
external project-system connectors, a workflow DSL, or new effect semantics.

See [ADR 0008](adr/0008-intent-and-outcome-stewardship.md) for the normative
decision and [ADR 0009](adr/0009-information-governance-and-confidential-context.md)
for the separate information-governance dependency.
