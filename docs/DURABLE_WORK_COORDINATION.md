# Durable Work Coordination

Durable Work Coordination is the deterministic v0.5 control-plane slice for
answering:

> Given an outcome worth pursuing, what work exists, what is ready now, and
> which available agent is a feasible worker?

It freezes two boundaries before richer orchestration is introduced:

```text
Goal != WorkOrder != PlanProposal != WorkGraph/WorkNode != ActionIntent
Capability != Competence != Authority
```

A goal describes a desired world outcome. A `WorkOrder` makes bounded work
durable. A planner proposes structure. `PlanValidator` alone admits a
`WorkGraph`. A `WorkNode` may analyze, prepare, execute, verify, or prepare a
release handoff; it is not an effect request. Any later external effect still
requires a distinct `ActionIntent`, policy decision, and typed capability.

## Implemented vertical slice

```text
WorkOrder
    ↓
FakePlanner → PlanProposal(causal cursor, graph version)
    ↓
PlanValidator
    ↓
durable WorkGraph
    ↓
ReadyFrontier
    ↓
WorkerMatcher
    ↓
fenced WorkLease
    ↓
canonical completion / expiration
    ↓
next ReadyFrontier
```

The slice contains:

- immutable `WorkOrder`, `WorkNode`, `WorkDependency`, and `WorkGraph`
  contracts;
- an asynchronous provider-neutral `Planner` protocol and deterministic
  `FakePlanner`;
- `PlanProposal` values pinned to both a canonical planning snapshot and prior
  graph version;
- deterministic `PlanValidator` gates for identity, success coverage,
  capability-type availability, dependency references, acyclicity, and
  verification ancestry;
- expiring `AgentPresence` facts and durable `CapabilityManifest` facts;
- seeded or evidence-ready `CompetenceEstimate` values with separate evidence
  confidence; only seeded estimates participate in v0.5 matching;
- a derived `ReadyFrontier` over completed dependencies, active leases, graph
  validity, and orientation prerequisites;
- a deterministic `WorkerMatcher` that considers availability, capacity,
  declared capability, seeded competence, evidence confidence, and verifier
  independence;
- fenced `WorkLease` grants whose shared terminal event identity makes
  completion and expiry mutually exclusive under canonical event-ID
  uniqueness;
- `WorkProjection` and `DurableWorkCoordinator`, which rebuild from the
  canonical event log before every transition.

## Planner boundary

The planner is a compiler, not an orchestrator. Its input contains the work
order, causal cursor, current graph version, and available capability types.
It receives no preferred agent identities, competence estimates, load,
credentials, or authority policy. Its output is proposed data and cannot grant
a lease, mutate a graph, authorize an effect, or execute anything.

`FakePlanner` is intentionally the only implementation in v0.5. This proves
that dependency progress, recovery, routing legality, and audit do not depend
on model intelligence.

## Readiness and dependency waves

For an active graph, readiness is derived as:

```text
ready(node) =
    all predecessors completed
    and epistemic prerequisites sufficient
    and no active lease
    and node not completed
    and graph not invalidated
```

The runtime never stores a wave number. Waves emerge from repeated frontier
derivation after canonical completions. This slice deliberately performs no
makespan or resource optimization; deterministic lexical ordering is only an
audit-stable traversal of the feasible frontier.

## Matching boundaries

`CapabilityManifest` answers whether an agent declares a capability type.
`CompetenceEstimate` supplies a separate seeded/evidence-ready estimate. Only
`SEEDED` estimates are operational in v0.5. The type remains evidence-ready,
but the coordinator and projection reject `EVIDENCE` estimates until their
references can be resolved against calibrated outcome evidence. The initial
seeded match score is the minimum across required capabilities of:

```text
competence score × evidence confidence
```

The best feasible score wins with agent ID as a deterministic tie-break. An
`AVAILABLE` presence is eligible only from `observed_at` through its exclusive
`valid_until` horizon; silence therefore cannot preserve availability forever.
Matching never grants authority. Authority remains on the work-order ceiling
and, for an actual effect, in the existing policy/capability path.

Verification is ordinary work. A verification node names the completed nodes
it checks, must be downstream of them, and structurally excludes their
completion workers from matching.

## Lease and recovery semantics

A lease is a renewable ownership claim only in the conceptual architecture;
the first slice implements grant, successful completion, and deadline expiry.
Each node attempt receives a monotonically increasing fencing token. Completion
must reference the active lease and token. A worker may report
`reported_finished_at` as informational evidence, but legality depends only on
the coordinator clock's `accepted_at`, which must precede lease expiry. Expiry
and completion use one terminal event ID per lease, so only one terminal fact
can win canonical event-ID uniqueness.

The coordinator is a command facade, not a private database or long-running
scheduler. It rebuilds `WorkProjection` from history before each transition.
A replacement coordinator can therefore expire a crashed worker's lease,
preserve prior artifacts, and grant a new fenced attempt.

## Causal invalidation and orientation

Every proposal records `based_on_event_cursor` and declared replan event types.
The cut is a causal planning snapshot: capability types used for both original
admission and replay are reconstructed through that exact cursor. Before graph
admission, the validator inspects the canonical planning window; a declared
replan event after the cut rejects the proposal as stale rather than accepting
then invalidating it. Graph admission uses an atomic expected-head append, so an
event arriving after validation cannot create history that later replay rejects.
A changed head forces reload and revalidation: an unrelated event may admit the
same proposal at the new explicit head, while a declared replan event rejects
it. A later matching event invalidates an already active graph. Completed
artifacts remain present, but the frontier becomes empty until a later plan
version is accepted.

Work-node source prerequisites reuse Situated Continuity's
freshness/confidence requirements. Insufficient coverage keeps the node outside
the ready frontier. This is a work-readiness gate, not effect authorization;
the governed effect plane must still recheck prerequisites before action.

## Flagship acceptance

The deterministic release scenario proves:

- dependency waves `A,B → C → D,E → F → G` emerge from the graph;
- capability and seeded competence select the initial workers;
- the verifier differs from the implementation worker;
- a crashed implementation lease expires and a new coordinator reassigns it
  with the next fencing token;
- stale deployment knowledge blocks `G`, while fresh coverage makes it ready;
- a later release-constraint event invalidates the plan before `G` is leased;
- replay reconstructs orders, graph, ecology, leases, completions, workers, and
  invalidation without an action or capability event.

Focused hardening regressions additionally prove that a blocking planner cannot
admit a proposal after a declared causal change, replay uses capability inputs
from the exact planning cut, expired presence cannot receive a lease, a worker
cannot backdate completion acceptance, and unresolved evidence-based competence
cannot affect v0.5 routing. A final admission barrier proves that a causal event
between validation and append leaves no accepted graph, while an unrelated event
forces a successful revalidation and replayable conditional append.

## Explicit deferrals

v0.5 does not implement model-backed planning, RDDL/MDP planning, learned
competence routing, adaptive oversight allocation, endogenous scheduling,
generalized workflow languages, real connectors, or capability execution. It
also defers lease renewal/cancellation, distributed multi-writer graph
transactions, belief-level prerequisites, plan-diff semantics, empirical
pre-review/post-review competence learning, and richer failure/result
contracts.

See [ADR 0007](adr/0007-durable-work-coordination.md) for the decision,
tradeoffs, and fitness functions.
