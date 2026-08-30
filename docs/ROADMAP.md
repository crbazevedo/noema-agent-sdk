# Engineering roadmap

Noema's responsibility is persistent autonomous agency. Deployment, model,
tool, and interoperability choices remain adapters around the same semantics.

Security, observability, deterministic replay, and local operation are
cross-cutting release gates rather than a final wave.

## v0.2 — Portable Durable Agent

Implemented:

- PostgreSQL `EventStore`;
- transactional outbox and durable inbox with fencing-token leases;
- NATS JetStream and deterministic in-memory broker adapters;
- event schema versioning and projection-time upcasting;
- action lifecycle, durable idempotency restoration, and crash recovery;
- model-provider/context/router contracts;
- OpenAI Responses and OpenAI-compatible local adapters;
- structured `ActionIntent` boundary validation;
- OpenTelemetry tracing port and OTLP adapter;
- replayable JSONL model fixtures;
- embedded/distributed deployment profiles and Docker Compose topology.

Acceptance: the autonomous incident application contains no mode-specific
policy branch and runs with both `MODE=embedded` and `MODE=distributed`.

## v0.3 — Persistent Cognitive Agent

- episodic indexes over event history;
- semantic assertions linked to evidence;
- hypotheses, contradictions, and validity intervals;
- PostgreSQL/pgvector and local SQLite/FTS projections;
- context assembly by relevance, evidence, freshness, and confidence;
- maintenance debt and commitment recovery.

Acceptance: after a multi-day restart, an agent reconstructs relevant world
and cognitive state without replaying its full transcript into a model.

## v0.4 — Agent Society

- MCP capability adapter and A2A agent adapter;
- capability manifests and discovery;
- typed task offers, bids, awards, progress, result, failure, cancellation;
- domain-specific trust, authority, rehabilitation, and exploration;
- durable multi-agent cancellation and contracting.

Acceptance: a Noema agent delegates to a non-Noema A2A agent and consumes an
MCP server without exposing Noema's internal memory or runtime protocol.

## v0.5 — Reflective Autonomous System

- explicit value-of-computation policies;
- wall-clock, call, cost, branch, action, and recursion ceilings;
- adaptive reasoning depth and strategy selection;
- shadow-mode bandit/learned controllers;
- counterfactual policy replay and experiment comparison.

Acceptance: learned control cannot execute before deterministic shadow
evaluation, and identical captured inputs reproduce the same semantic trace.

## v0.6 — Situated Continuity

- temporal semantics, source cursors, freshness, and awake epochs;
- wake reconciliation and an orientation barrier;
- substrate/sensor contracts and adaptive perception;
- provenance-bearing situation capsules and artifact retention;
- user, workflow, and agent ecology models;
- durable delegations, work leases, and opportunity windows;
- macOS reference sidecar and simulated sleep/wake flagship demo.

See [`SITUATED_CONTINUITY.md`](SITUATED_CONTINUITY.md) for its invariants and
dependency sequence.

## Ongoing production ratchet

- poison-message quarantine and operator repair tools;
- sandbox adapters and secret-reference resolution;
- tenant isolation and policy-as-code adapters;
- performance/fault benchmarks at 1M+ events and 100-agent clusters;
- optional Temporal durable-execution adapter;
- Kafka/Redpanda transport adapter without changing core semantics.
