# Architecture principles

These rules are release invariants, not aspirations. ADRs must identify any
principle they change.

| Principle | Enforced consequence |
|---|---|
| Core is provider-neutral | Model, broker, database, and cloud SDK imports stay in adapters. |
| Local is first-class | Embedded operation requires no network or external service. |
| Events are canonical | Situation state, recovery state, and transport messages derive from the event log. |
| The broker is transport | Broker retention is never treated as system history. |
| Effects are explicit | Cognition proposes `ActionIntent`; policy authorizes a typed capability. |
| At-least-once is assumed | External effects receive idempotency keys and must tolerate retry. |
| Schemas evolve | Every event carries a positive schema version; upcasters preserve identity and ordering. |
| Situation is not a prompt | The world model exists independently of model context. |
| Authority is explicit | Capability, permission, authority, reversibility, and risk remain separate. |
| Autonomy is observable | Trigger, proposal, authorization, dispatch, execution, and result share causal provenance. |
| Cancellation and backpressure are real | Async boundaries have timeouts, bounded queues, and graceful shutdown. |
| Failure is data | Failed decisions, deliveries, retries, actions, and compensation enter durable state. |
| External protocols stay at boundaries | NATS, MCP, A2A, provider APIs, and cloud services do not become domain models. |
| Research uses the production path | Replay fixtures and traces wrap the same runtime interfaces used in deployment. |
| Sensing is minimal and sufficient | Future situated-continuity adapters escalate sensing by value, privacy, and cost. |
| Competence compiles downward by proof | Repeated deliberation may forge a candidate micro-policy, but only evidence and lifecycle gates can advance it. |
| Rules are signal-first | Autonomic rules emit typed signals by default and can only propose, never execute, an external effect. |
| Learned policy is data | Rule versions use sanctioned typed encodings; arbitrary generated code and in-place mutation are forbidden. |
| Uncertainty is replayable | Evidence may be probabilistic, but pinned activation and conflict resolution are deterministic. |
| Modulation is explicit | Global context that changes rule thresholds is provenance-bearing situation state, not a hidden mutable global. |
| Invariants are not learnable | L0 security, privacy, sandbox, and authority constraints cannot be weakened by rules or meta-rules. |

Structural enforcement lives in `tests/test_architecture.py`, schema/replay
tests, and distributed fault tests. Documentation alone is not considered an
enforcement mechanism.
