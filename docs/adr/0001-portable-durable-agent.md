# ADR 0001: Portable durable agent

- Status: accepted
- Date: 2026-08-30
- Milestone: v0.2

## Context

Noema v0.1 proved the autonomous event loop in one Python process. The next
version must preserve those semantics on a laptop and across workers without
creating a local edition and a separate distributed edition.

The main failure risk is dual truth: if the broker, projection, model context,
or idempotency cache becomes independently authoritative, recovery can no
longer explain or deterministically rebuild agent behavior.

## Quality-attribute scenarios

| Attribute | Scenario and response |
|---|---|
| Portability | On a disconnected macOS/Linux host, `MODE=embedded` runs with Python and SQLite only. |
| Reliability | If publication fails after an event commits, the leased outbox retries it; no committed event is lost. |
| Crash recovery | If an agent stops after authorization, restart reconstructs the unfinished intent and reuses the business idempotency key. |
| Auditability | Given an action result, correlation and causation identifiers lead back through dispatch, authorization, proposal, and trigger. |
| Modifiability | Replacing NATS, PostgreSQL, OpenAI, or OTLP changes an adapter, not agent policy or the incident application. |
| Security | A model can return structured proposals but receives no capability credentials and cannot bypass policy. |
| Testability | A deterministic broker, static model, fixture replay, fencing tests, and the real Compose topology exercise the same ports. |
| Performance | Embedded commits avoid network I/O; distributed dispatch adds an explicit outbox polling sensitivity point. |

## Decision

1. The `EventStore` is the only canonical history. Situation state, action
   recovery, model fixtures, and broker messages are projections.
2. Distributed commits use an event-store transaction that inserts both the
   event and one outbox row. A leased publisher sends it to a portable
   `EventBroker`.
3. Delivery is at least once. Durable inbox claims use expiring leases and
   monotonically increasing fencing tokens. Event IDs deduplicate observations;
   idempotency keys cross the capability boundary for business effects.
4. PostgreSQL and NATS JetStream are default distributed adapters. SQLite and
   the in-process bus remain the embedded profile. Core imports neither driver.
5. Model cognition depends on `ModelProvider`, `ModelRequest`,
   `ModelResponse`, `ContextAssembler`, and `Reasoner`. Provider responses are
   schema-validated before becoming `ActionIntent` objects.
6. OpenTelemetry implements the core `Tracer` port. The event log remains the
   canonical causal record; traces are an operational projection.
7. `deployment_from_env()` selects topology. Application policies and
   capability code do not branch on deployment mode.
8. Situated Continuity remains a plane above these primitives. Its v0.4
   foundation reuses canonical events without redefining the envelope; sensing
   and ecology semantics remain outside the v0.2 delivery machinery.

## Consequences and tradeoffs

- Outbox polling is simpler and portable, but its interval directly affects
  dispatch latency and database load.
- A shared PostgreSQL log makes causality and replay straightforward, but it is
  a scaling sensitivity point. Partitioning must preserve global or scoped
  ordering semantics explicitly.
- Fencing prevents stale workers from committing delivery state; it cannot
  make a non-idempotent external API safe. Capability adapters must honor the
  supplied key or disable automatic retry.
- JetStream duplicate suppression is useful but insufficient; the durable
  inbox is still required because broker windows expire.
- Upcasters make old events readable without rewriting history. They must be
  deterministic and preserve event ID and sequence.
- Structured output improves boundary validity, but model proposals remain
  untrusted until critics and policy approve them.
- One repository and optional extras reduce ecosystem fragmentation at the
  cost of a larger adapter test matrix.

## Fitness functions

- `tests/test_architecture.py` rejects provider SDK imports outside adapters and
  mode-specific branches in the incident application.
- `tests/test_delivery.py` injects broker failure, duplicate and out-of-order
  delivery, expired leases, stale fencing tokens, and action recovery;
  `tests/test_postgres.py` exercises cross-connection append and inbox races.
- `tests/test_events.py` checks version round-trip and deterministic upcasting.
- `tests/test_models.py` checks schema-constrained model requests and exact
  fixture replay.
- CI runs tests, Ruff, strict mypy, build verification, and the same incident
  demo against the Compose PostgreSQL/NATS topology.
