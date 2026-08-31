# ADR 0005: Persistent cognitive memory is an epistemic event projection

- Status: accepted
- Date: 2026-08-30
- Scope: episodic memory, evidence, semantic assertions, contradictions, and retrieval

## Context

A durable agent needs to know more than which text resembles a query. It must
distinguish what happened from what bears on a proposition and from what it
currently estimates to be true. It must also explain when a claim held, when it
learned the claim, why it believes it, whether it is stale, and what disagrees.

Treating an embedding store, transcript, or mutable fact table as memory loses
at least one of those distinctions. It also creates a second authority beside
the canonical event log and makes retrospective decision evaluation unreliable.

## Decision

1. Keep events, evidence links, and semantic assertions as separate contracts.
   All durable memory state remains reconstructible from canonical events.
2. Record immutable `SemanticAssertion` versions with structured semantic keys,
   epistemic type, confidence, valid time, knowledge time, freshness, source
   anchors, derivation, status, and supersession provenance.
3. Treat assertion `source_refs` as minimum admission anchors and
   `EvidenceLink` as the sole semantic evidence graph. One fail-closed resolver
   validates both paths against existing canonical events, assertions, or
   explicitly typed simulation artifacts. Unknown namespaces and identities
   are rejected.
4. Type provenance as observed, inferred, reported, assumed, or simulated.
   Non-assumptions require evidence or derivation, inferences require explicit
   derivations, and simulated evidence cannot become positive evidence for an
   observed fact through serialization or linking.
5. Use bitemporal queries. `valid_from`/`valid_to` describe the world;
   `recorded_at` and transition timestamps describe agent knowledge.
6. Never mutate a belief in place. Supersession, validity closure,
   contradiction detection, and contradiction resolution are append-only
   canonical events. Belief state is a projection.
7. Preserve competing assertions. The initial deterministic contradiction
   detector covers different values for one subject/predicate over overlapping
   intervals. Richer semantic contradiction detectors may emit the same event
   contracts later.
8. Name aggregate query confidence `max_assertion_confidence`. An uncertain
   belief has no selected value, so the strongest alternative's confidence must
   not look like confidence in a selected conclusion.
9. Rank retrieval by lexical relevance, time, goals, evidence, freshness, and
   contradiction/staleness. Full-text and vector indexes are disposable
   accelerators, never semantic authority.
10. Reuse `ConsumerCheckpoint`. The memory projector persists deterministic
   derived events before checkpoint advancement and closes partial-write crash
   windows by replay and ID-based idempotency. Any same-process processing
   failure first rebuilds speculative projection state through the last durable
   checkpoint.
11. Defer autonomous consolidation and promotion. Future pattern extraction must
   begin in observational shadow mode.

## Consequences

- Noema can independently ask what was true at a world time and what it knew at
  a knowledge time.
- Contradictions become inspectable uncertainty rather than last-write-wins
  corruption.
- A missing evidence identity, unsupported namespace, or provenance mismatch
  cannot affect retrieval scores or semantic state.
- Same-process retries have the same projection semantics as process restarts.
- Mutable-world claims require an explicit freshness or validity boundary.
- Deleting lexical or vector indexes cannot delete memory.
- The initial value domain is deliberately scalar. Rich structured values can
  be added with a canonical immutable encoding rather than mutable nested maps.
- Generic semantic contradiction remains incomplete. Domain-specific relations
  require typed detectors and cannot be guessed from prose.
- The projector currently favors correctness and replay transparency over
  incremental snapshot optimization.

## Rejected alternatives

- **Vector database as memory:** similarity has neither epistemic provenance nor
  bitemporal truth semantics and cannot be canonical.
- **Mutable belief rows:** destroys the evidence trail and prevents faithful
  historical reconstruction.
- **One timestamp:** conflates when a claim held with when the agent learned it.
- **Last-write-wins conflict handling:** hides uncertainty and discards evidence.
- **A private projector cursor:** duplicates recovery authority already supplied
  by canonical consumer checkpoints.
- **Immediate model-driven consolidation:** promotes an unmeasured lossy process
  into the truth path before replay and evaluation exist.

## Fitness functions

- late knowledge returns different correct answers for valid-time and
  knowledge-time queries;
- conflicting assertions remain present and yield an unresolved uncertain
  belief;
- a crash after evidence persistence but before checkpoint replays to identical
  assertion, evidence, and contradiction identities without duplicates;
- failed contradiction and supersession writes roll back speculative state and
  succeed exactly once when retried by the same worker;
- one fresh evidence-bearing contradiction outranks one hundred stale similar
  assertions;
- simulation provenance survives serialization and cannot support an observed
  fact through either source anchors or graph links;
- memory core code cannot import providers, adapters, effects, or the event bus;
- clearing the lexical index leaves retrieval and semantic state unchanged.

This decision builds on [ADR 0001](0001-portable-durable-agent.md) and reuses the
recovery contract from [ADR 0004](0004-durable-consumer-checkpoints.md).
