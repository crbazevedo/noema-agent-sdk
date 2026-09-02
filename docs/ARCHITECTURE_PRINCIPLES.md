# Architecture principles

These rules are release invariants, not aspirations. ADRs must identify any
principle they change.

| Principle | Enforced consequence |
|---|---|
| Core is provider-neutral | Model, broker, database, and cloud SDK imports stay in adapters. |
| Local is first-class | Embedded operation requires no network or external service. |
| Events are canonical | Situation state, recovery state, and transport messages derive from the event log. |
| Causal admission is atomic | State validated through head `H` becomes canonical only through an expected-head conditional append at `H`. |
| Consumer progress is canonical | Durable workers checkpoint only after required outputs; restart replays later triggers idempotently. |
| The broker is transport | Broker retention is never treated as system history. |
| Effects are explicit | Cognition proposes `ActionIntent`; policy authorizes a typed capability. |
| At-least-once is assumed | External effects receive idempotency keys and must tolerate retry. |
| Schemas evolve | Every event carries a positive schema version; upcasters preserve identity and ordering. |
| Situation is not a prompt | The world model exists independently of model context. |
| Events, evidence, and beliefs differ | An occurrence, its bearing on a proposition, and current belief state use separate contracts. |
| Beliefs are append-only projections | Assertion changes create versions and transition events; no belief mutates in place. |
| Memory is bitemporal | World-valid time and recorded knowledge time remain independently queryable. |
| Wake is reconstruction | Restarting or resuming cognition never implies mutable external beliefs remain trustworthy. |
| Clocks are distinct | Durable wall time, local monotonic duration, and source-reported world time cannot substitute for one another. |
| Orientation precedes consequence | Action prerequisites expose minimum freshness and confidence before the effect path. |
| Work identity is layered | `Goal`, `WorkOrder`, `PlanProposal`, `WorkGraph`, `WorkNode`, and `ActionIntent` cannot substitute for one another. |
| Strategic identity is layered | `GoalRevision`, `RoadmapRevision`, `Commitment`, and `WorkOrder` are distinct immutable contracts. |
| Intent authority differs from effect authority | Permission to act cannot rewrite, reprioritize, or retire governing user intent. |
| Roadmaps are hypotheses | Outcome nodes create neither obligations nor executable work; only an admitted commitment can bridge roadmap-derived work. |
| Obligation differs from activation | `ACCEPTED` means owed; only `ACTIVE` permits commitment-derived work admission. |
| Reactivation is reorientation | A suspended commitment requires a newer roadmap revision and current evidence before returning to active. |
| Outcome roles are independent | Outcome owner, decision owner, executor, and verifier cannot be inferred from each other or duplicated in assistance policy. |
| External work remains external truth | External observations may create support demand but cannot become a Noema work graph or authoritative roadmap copy. |
| Strategic execution requires a current cut | New roadmaps, commitments, proposals, admission, and reactivation cannot rely on known-stale goal or roadmap revisions. |
| Assistance bounds agent work | Non-agent execution requires canonical roles and assistance; declared intervention/support cannot exceed that envelope. |
| Coverage means criterion sufficiency | An obligation is covered only when admitted work covers every required outcome criterion. |
| Replay defends strategic legality | Deterministic cross-object invariants are checked during reconstruction, not only at the command facade. |
| Planners propose structure | A planner cannot admit a graph, select a worker, grant a lease, authorize, or execute. |
| Graphs own dependency progress | Ready frontiers derive from accepted dependencies, canonical completions, leases, orientation, and invalidation. |
| Planning cuts are causal snapshots | Admission and replay use capability inputs through the proposal cursor and reject declared changes during planning. |
| Capability, competence, and authority differ | Declarations establish feasibility, evidence estimates quality, and policy alone grants authority. |
| Availability expires | An `AVAILABLE` observation cannot outlive its explicit presence validity horizon. |
| Work ownership is fenced | Every reassignment increments a node fencing token; stale workers cannot complete newer attempts. |
| Completion time is control-plane time | Worker-reported finish time is evidence; only coordinator acceptance time determines lease legality. |
| Epistemic provenance is durable | Observed, inferred, reported, assumed, and simulated claims remain explicitly typed through replay. |
| Evidence references fail closed | One resolver admits only existing canonical events, assertions, or typed simulation artifacts. |
| Evidence has one semantic graph | Assertion source anchors establish provenance; only `EvidenceLink` describes how evidence bears on a claim. |
| Contradictions are preserved | Competing evidence produces inspectable uncertainty rather than last-write-wins replacement. |
| Indexes are not memory | Lexical, full-text, and vector indexes may disappear without semantic-state loss. |
| Retrieval is decision-relevant | Similarity competes with time, goals, evidence, freshness, and contradiction penalties. |
| Authority is explicit | Capability, permission, authority, reversibility, and risk remain separate. |
| Autonomy is observable | Trigger, proposal, authorization, dispatch, execution, and result share causal provenance. |
| Cancellation and backpressure are real | Async boundaries have timeouts, bounded queues, and graceful shutdown. |
| Failure is data | Failed decisions, deliveries, retries, actions, and compensation enter durable state. |
| External protocols stay at boundaries | NATS, MCP, A2A, provider APIs, and cloud services do not become domain models. |
| Research uses the production path | Replay fixtures and traces wrap the same runtime interfaces used in deployment. |
| Sensing is minimal and sufficient | Refresh planning is decision-relevant and budgeted; future adapters escalate sensing by value, privacy, and cost. |
| Competence compiles downward by proof | Repeated deliberation may forge a candidate micro-policy, but only evidence and lifecycle gates can advance it. |
| Rules are signal-first | Autonomic rules emit typed signals by default and can only propose, never execute, an external effect. |
| Learned policy is data | Rule versions use sanctioned typed encodings; arbitrary generated code and in-place mutation are forbidden. |
| Uncertainty is replayable | Evidence may be probabilistic, but pinned activation and conflict resolution are deterministic. |
| Modulation is explicit | Global context that changes rule thresholds is provenance-bearing situation state, not a hidden mutable global. |
| Invariants are not learnable | L0 security, privacy, sandbox, and authority constraints cannot be weakened by rules or meta-rules. |
| Policy time is sequence-based | Rule eligibility is pinned by canonical event cursor; a later registration cannot leak into historical evaluation. |
| Ruleset identity is content identity | Time and event cursor belong to evaluation epochs, not the content-addressed ruleset artifact. |
| Inhibition strength is typed | Hard equal-or-higher-precedence vetoes and probabilistic graded modulation are distinct encodings. |
| Observation precedes learning | Continuous shadow telemetry must ground HabitForge fitness before learned policy can advance. |
| Intrinsic goals are subordinate | Future endogenous processes may propose instrumental, epistemic, maintenance, and exploratory goals, never terminal values. |
| Background cognition is leased | Future dream/maintenance work consumes explicit preemptible budgets and cannot silently act externally. |
| Cognitive demand is layered | `Signal`, `Inquiry`, `IntrinsicActivity`, `WorkOrder`, and `ActionIntent` cannot substitute for one another. |
| Curiosity is not novelty | Novelty may seed a candidate inquiry but does not establish positive Value of Cognition. |
| Endogenous intent is subordinate | New inquiries require exact current `ACTIVE` or `BLOCKED` governing goal revisions; terminal intent admits none. |
| Value of Cognition is explicit | Improvement and compute, delay, attention, opportunity, and privacy/risk costs remain separately replayable under a pinned policy. |
| DREAM is not effect authority | A DREAM epoch may select cognitive proposals only; it cannot dispatch work, authorize effects, or invoke capabilities. |
| Background budget is single-spend | One consumer owns at most one active DREAM epoch, each epoch records at most one deterministic agenda, and terminal epochs consume no further cognition. |
| Background yields causally | A configured foreground event preempts DREAM only when it follows the epoch's pinned event cut. |
| Inquiry renewal is explicit | Unchanged evidence and intent cannot allocate a new activity for an unresolved or expired inquiry. |
| Cognitive policy pins code semantics | Policy and DREAM state identify an immutable agenda-selector implementation; unknown versions fail closed. |
| Competence does not grant authority | A future SkillForge may propose a capability; capability registration and authority remain independent gates. |

## Accepted staged principles

These principles govern the accepted v0.6.x architecture direction. They are
normative for a future implementation but do not claim that reconsideration or
learned allocation runtime contracts exist yet.

| Principle | Required future consequence |
|---|---|
| Historical cognition loses authority, not value | Prior cognition remains immutable evidence, but old goals, selections, priorities, and authority cannot directly govern a new allocation. |
| Reconsideration is not resumption | Historical cognition returns only as newly admitted cognition after current-intent/current-world revalidation and a fresh causal cut. |
| Closed intent cannot self-revive | Fulfilled, failed, and cancelled goals may supply historical evidence but cannot authorize a new inquiry without independently live current intent. |
| Cognitive identity is layered | A reconsideration candidate, inquiry, goal, work order, and action intent cannot substitute for one another. |
| Value semantics remain distinct | Value, preference, motivation, intent, and commitment require separate evidence and cannot be inferred from one another. |
| Motivation is not authority | A strong reason to think cannot create intent, grant permission, or authorize work or effects. |
| Epistemic and strategic conflict differ | Contradictory evidence may motivate inquiry but cannot establish goal conflict without an explicit strategic relation. |
| Scarce cognition is multidimensional | Compute, wall time, money, user attention, interruption, privacy exposure, and opportunity cost remain hard, inspectable budget dimensions. |
| Positive NetVOC is eligibility | A positive estimate permits portfolio consideration; it does not mandate selection or bypass any gate. |
| Selection absence is censored evidence | Non-selection, constraint deferral, rejection, and negative outcome remain distinct labels for evaluation and learning. |
| Learned estimation is not sovereign utility | Estimators emit versioned outcome and cost vectors; they cannot learn or replace terminal user values. |
| Hard gates precede learned scores | Current intent, authority, safety, information access, and user agency constrain the candidate set before learned ranking. |
| Learning use is separately governed | Permission to use information for current cognition never automatically permits training, calibration, evaluation, or benchmarking reuse. |
| Learning stages earn authority | Deterministic allocation precedes traces, calibrated estimation, counterfactual evaluation, shadow allocation, and only then bounded active allocation. |

Structural enforcement lives in `tests/test_architecture.py`, schema/replay
tests, and distributed fault tests. Documentation alone is not considered an
enforcement mechanism.
