# Persistent Cognitive Memory

Noema memory is an epistemic projection of canonical history. It answers five
questions without treating a transcript, summary, full-text index, or embedding
as truth:

1. What does the agent currently believe?
2. What evidence bears on that proposition?
3. When was the proposition valid in the world?
4. When did the agent learn it?
5. What unresolved evidence contradicts it?

## Layers and boundaries

```text
canonical events
      │
      ▼
episodic memory ── what happened
      │
      ▼
evidence graph ─── supports / contradicts / refines / supersedes / derives
      │
      ▼
semantic projection
      ├── held assertions
      ├── hypotheses
      ├── contradictions
      └── validity and freshness
              │
              ▼
decision-relevant retrieval
```

An event is something that happened. Evidence is a typed relationship showing
how an event or assertion bears on a proposition. A belief is the current query
result derived from assertions, evidence, validity transitions, supersession,
and contradictions. These concepts are deliberately not interchangeable.

## Assertions and provenance

`SemanticAssertion` is immutable and content-addressed when created through its
factory. It records a structured subject, predicate, scalar value, confidence,
status, source and derivation references, optional supersession, and one of five
epistemic types:

- `OBSERVED`
- `INFERRED`
- `REPORTED`
- `ASSUMED`
- `SIMULATED`

Every non-assumption has a provenance source or derivation reference. Every
inference has an explicit derivation. A mutable-world assertion must declare either
`fresh_until` or `valid_to`. Simulated provenance survives serialization and
cannot be linked as positive evidence for an observed fact.

`source_refs` are the minimum provenance anchors needed to admit an assertion.
They do not encode how evidence bears on the claim. `EvidenceLink` is the one
canonical graph for `SUPPORTS`, `CONTRADICTS`, `REFINES`, `SUPERSEDES`, and
`DERIVED_FROM` relations, including relation strength and typed provenance.

`MemoryProjection.resolve_evidence_ref()` is the single fail-closed resolver for
both inline anchors and evidence-graph edges:

```text
event:<id>       → existing canonical event
assertion:<id>   → existing semantic assertion
simulation:<id>  → canonical event explicitly typed as simulated
```

Unknown namespaces and missing identities are rejected. An observed assertion
cannot use a simulated assertion indirectly through `source_refs`, so inline
anchors cannot bypass the evidence-link provenance gate.

Hypotheses reuse the same assertion contract with `status=HYPOTHESIS`; they are
not silently mixed into the default held-belief projection.

## Bitemporal queries

Memory distinguishes:

- **valid time**: when the proposition held in the world;
- **knowledge time**: when Noema had recorded it.

`MemoryProjection.belief(..., valid_at=..., known_at=...)` therefore supports
both retrospective truth and retrospective knowledge. A late report may say a
pull request merged Friday while being recorded Monday. Monday's query about
Friday can return `merged`; Friday's own knowledge-time query still returns
`open`.

Validity closure and supersession are separate immutable events. No assertion
row is edited. A current belief is always a projection over the versions visible
at the requested pair of times. Known-expired or stale mutable assertions are
excluded by default.

## Contradictions

The first detector is intentionally narrow and deterministic: simultaneous
assertions with the same subject and predicate but different scalar values are
in conflict unless one directly supersedes the other. Both assertions and their
evidence remain available. The query returns `UNCERTAIN`, a null selected value,
the competing assertions, and the unresolved contradiction record.

`BeliefState` names the aggregate field `max_assertion_confidence`; it is not
the confidence of a selected value when the disposition is uncertain.

Cross-predicate and domain-semantic contradiction rules belong in later typed
detectors. They must produce the same canonical contradiction events instead of
silently overwriting either claim.

## Retrieval

`MemoryRetriever` ranks visible assertions using lexical relevance, temporal
relevance, current-goal overlap, evidence strength, freshness, and a
contradiction/staleness penalty. The initial lexical implementation is local,
deterministic, and dependency-free.

`LexicalMemoryIndex` is disposable. Clearing it does not alter semantic state or
query correctness because the retriever falls back to canonical assertions.
SQLite FTS, embeddings, PostgreSQL full-text search, and pgvector may later
accelerate candidate generation behind the same rule:

> An index can be deleted and rebuilt. It is not memory.

## Recovery

`MemoryProjector` consumes the canonical event log and reuses the generic
`ConsumerCheckpoint`. It writes deterministic supersession, contradiction, and
resolution outputs before advancing its checkpoint. On restart it rebuilds
through the checkpoint event, replays every later eligible input, reuses any
partial outputs by ID, and completes the checkpoint. There is no private memory
offset store.

The same rule applies without a process restart. Any processing exception
immediately discards speculative projection state and rebuilds through the last
durable checkpoint before the input may be retried. A live worker therefore
cannot remember an assertion while silently omitting its failed derived event.

The checkpoint's processing lag remains a canonical sequence gap. It includes
system and derived events and is not necessarily the count of useful memory
inputs waiting.

## Event vocabulary

```text
memory.assertion_recorded
memory.assertion_superseded
memory.evidence_linked
memory.validity_closed
memory.contradiction_detected
memory.contradiction_resolved
```

Autonomous consolidation is deliberately deferred. Episodes, patterns, and
semantic abstractions may later be evaluated in shadow mode, but no model can
currently rewrite or promote memory on its own.

See [ADR 0005](adr/0005-persistent-cognitive-memory.md) for the decision and
tradeoffs.
