# ADR 0007: Models propose plans; durable machinery owns work

- Status: accepted
- Date: 2026-08-31
- Scope: work identity, plan admission, dependency readiness, worker
  feasibility, verification independence, leases, and causal invalidation

## Context

Situated Continuity determines whether current knowledge is sufficient before
reasoning or consequence. It does not represent bounded work, dependency
progress, or recoverable ownership. Moving directly from goals or model output
to dispatch would conflate desire, planning, work, and effects. Likewise,
treating a declared capability as evidence of competence or permission would
create unsafe routing and authority shortcuts.

The next layer must prove its control semantics without relying on a model,
external connector, optimizer, learned score, or second state store.

## Quality-attribute scenarios

1. Given a deterministic release plan, independent roots run first, joins wait
   for every predecessor, and later waves emerge solely from canonical
   completions.
2. Given multiple available agents, matching rejects missing capabilities and
   chooses the highest seeded competence weighted by evidence confidence with a
   deterministic tie-break.
3. A verification node cannot be leased to the worker whose completed artifact
   it verifies.
4. After a worker disappears mid-node, a replacement coordinator rebuilds from
   history, expires the lease, rejects its stale fencing token, preserves prior
   artifacts, and grants the next attempt.
5. A release node with insufficient deployment freshness/confidence remains
   outside the ready frontier; fresh coverage makes it ready without executing
   an effect.
6. When a declared causal assumption changes after a proposal's event cut, the
   accepted graph is invalidated and cannot advance further.
7. Replaying the same canonical history reconstructs byte-equivalent durable
   work state and performs no model, authorization, capability, or effect call.

## Decision

1. Freeze the type boundaries:

   ```text
   Goal != WorkOrder != PlanProposal != WorkGraph/WorkNode != ActionIntent
   Capability != Competence != Authority
   ```

2. Make `WorkOrder` the durable record that bounded work deserves to exist. It
   carries goal/provenance references, outcome and success criteria, priority,
   temporal bounds, authority ceiling, and optional epistemic prerequisites.
3. Treat `Planner` as an asynchronous compiler protocol. It receives a work
   order, canonical causal cursor, current graph version, and capability types,
   but no agent identities, competence estimates, credentials, load, or
   authority policy. Implement only deterministic `FakePlanner` in v0.5.
4. Make `PlanProposal` immutable and content-addressed. Pin it to
   `based_on_event_cursor` and `based_on_graph_version`; proposed structure
   cannot mutate accepted state.
5. Give `PlanValidator` exclusive admission authority for `WorkGraph`. It
   validates identity, work-order success coverage, known capability types,
   dependency references, DAG acyclicity, monotonic graph version, and
   verification ancestry. It does not optimize or execute.
6. Derive `ReadyFrontier` from the accepted graph plus canonical lifecycle
   projection and current awareness coverage. Dependency waves are projections,
   never planner instructions or stored counters.
7. Keep legality separate from optimization. v0.5 enumerates the feasible
   frontier in deterministic node order; it implements no scheduling objective,
   makespan solver, MDP, or oversight allocator.
8. Represent ecology through durable `AgentPresence`, `CapabilityManifest`, and
   `CompetenceEstimate` facts. Seeded estimates are explicit; evidence-backed
   estimates require evidence references. Matching uses declared capability,
   availability/capacity, competence, and evidence confidence only.
9. Keep authority outside `WorkerMatcher`. A lease means responsibility for a
   work node, not permission to execute an external effect. Any later effect
   still requires `ActionIntent`, policy authorization, and a typed capability.
10. Represent verification as ordinary work. Verification nodes must be
    downstream of their targets, and matching excludes the workers recorded as
    completing those targets.
11. Use immutable fenced `WorkLease` grants. Fencing tokens increase per graph
    node. Completion requires the active token and a time within the lease.
    Completion and expiry share one terminal event identity so canonical event
    uniqueness admits only one terminal outcome.
12. Invalidate an active graph when a declared replan event occurs after its
    proposal causal cut. Preserve completed artifacts but expose no further
    ready nodes until a later graph version is validated.
13. Keep the canonical event log as the only durable authority. `WorkProjection`
    rebuilds orders, proposals, graphs, ecology, leases, completions, and
    invalidations. `DurableWorkCoordinator` rebuilds before every transition
    and owns no private state store.
14. Reuse Situated Continuity source prerequisites for work readiness. This
    control-plane gate does not replace the effect plane's final epistemic and
    authority checks.

## Consequences and tradeoffs

- Planner replacement is low-coupling: a future model implementation must
  produce the same proposal contract and pass the same validator and acceptance
  suite.
- Dependency progress, assignment reasons, verification independence, lease
  recovery, and invalidation are auditable from one log.
- The seeded score is intentionally conservative and simple. It is a stable
  feasibility heuristic, not a learned routing policy or calibrated objective.
- Rebuilding before commands favors clarity and recovery correctness over
  throughput. Disposable snapshots may accelerate this only if they preserve a
  single canonical cut.
- The slice assumes serialized work-control commands. Stable lease claim IDs and
  shared terminal IDs close the demonstrated claim/terminal races, but a
  distributed multi-writer compare-and-append transaction remains deferred.
- Presence is an observed lease-feasibility fact, not a liveness guarantee.
- Source-level orientation prerequisites are supported. Belief-level
  confidence prerequisites remain a later perception/work-control hardening
  decision.
- There is no generalized node-state machine, workflow language, lease renewal,
  cancellation, compensation, partial artifact protocol, or plan-diff model.

## Rejected alternatives

- **Dispatch directly from a goal:** loses bounded work identity, acceptance,
  dependency, and recovery semantics.
- **Let the planner mutate or dispatch the graph:** makes model behavior the
  control plane and destroys deterministic recovery.
- **Ask the planner to name workers or waves:** couples cognition to transient
  ecology and asks it to babysit state the runtime can derive.
- **Treat capability as competence:** turns a declaration into unsupported
  quality evidence.
- **Treat competence as authority:** bypasses explicit policy and capability
  governance.
- **Last-write-wins work ownership:** permits stale workers to complete after
  reassignment.
- **Store ready/wave state separately:** creates a second source of truth that
  can diverge from graph dependencies and completions.
- **Add an optimizer now:** there is no measured objective or demonstrated
  baseline gap; deterministic feasibility is sufficient for this milestone.
- **Use model-backed planning first:** prevents falsifying whether the durable
  control plane works independently of proposal intelligence.

## Fitness functions

- the planner module references no presence, competence, or matcher type;
- the work package cannot import model, reasoning, agent, capability-execution,
  scheduler, delivery, or external-adapter modules and cannot call effect-plane
  operations;
- validation rejects dependency cycles, unknown capability types, stale causal
  cuts/graph versions, and verification nodes not downstream of their targets;
- the flagship produces `A,B → C → D,E → F`, with independent verification;
- an expired lease rejects its stale token and reassigns with the next token
  after coordinator reconstruction;
- stale deployment coverage blocks `G`, fresh coverage exposes `G`, and a later
  declared causal change invalidates the graph before lease;
- canonical replay reproduces ecology, graph, leases, completions, workers, and
  invalidation while emitting no action or capability event;
- repository architecture gates keep deferred long-term mechanisms absent from
  the v0.5 work package.

This decision builds on [ADR 0004](0004-durable-consumer-checkpoints.md),
[ADR 0005](0005-persistent-cognitive-memory.md), and
[ADR 0006](0006-situated-continuity-foundation.md).
