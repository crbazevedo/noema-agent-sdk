# Architecture principles

These rules are release invariants, not aspirations. ADRs must identify any
principle they change.

| Principle | Enforced consequence |
|---|---|
| Core is provider-neutral | Model, broker, database, and cloud SDK imports stay in adapters. |
| Local is first-class | Embedded operation requires no network or external service. |
| Events are canonical | Situation state, recovery state, and transport messages derive from the event log. |
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
| Planners propose structure | A planner cannot admit a graph, select a worker, grant a lease, authorize, or execute. |
| Graphs own dependency progress | Ready frontiers derive from accepted dependencies, canonical completions, leases, orientation, and invalidation. |
| Capability, competence, and authority differ | Declarations establish feasibility, evidence estimates quality, and policy alone grants authority. |
| Work ownership is fenced | Every reassignment increments a node fencing token; stale workers cannot complete newer attempts. |
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
| Competence does not grant authority | A future SkillForge may propose a capability; capability registration and authority remain independent gates. |

Structural enforcement lives in `tests/test_architecture.py`, schema/replay
tests, and distributed fault tests. Documentation alone is not considered an
enforcement mechanism.
