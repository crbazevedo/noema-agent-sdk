# Non-functional requirements

This document defines measurable quality requirements for Noema and for the
first continuous Companion pilot. It does not convert a proposed target into an
implemented guarantee.

## Status vocabulary

- **Implemented evidence** means a runtime contract and an automated test exist
  in the current SDK ancestry.
- **Proposed pilot target** means the measurement and pass condition are defined,
  but acceptance evidence has not yet been collected.
- **Blocker** means the pilot must remain bounded or disabled until the missing
  mechanism or evidence exists.

The canonical event store is the source of truth. Checkpoints, projections,
metrics, traces, broker state, dashboards, and evaluation reports are derived
views. None may create authority or repair canonical history silently.

## Current evidence baseline

| Concern | Current evidence | Limit of the evidence |
|---|---|---|
| Deterministic replay | Projections rebuild from canonical events; attention tests compare semantic snapshots after replay. | No long-duration or large-history replay benchmark has been accepted. |
| PostgreSQL sequence gaps | Governance and attention tests inject real `BIGSERIAL` gaps and validate exact-predecessor-head replay. | The evidence covers the tested admission families, not every future event family. |
| Local/distributed operation | In-memory, SQLite, PostgreSQL, transactional outbox/inbox, and NATS acceptance paths exist. | A byte-for-byte semantic parity run over one identical pilot corpus is still required. |
| Crash and concurrency recovery | Attention tests cover provider failure, crash after durable disposition, idempotent recovery, equal-writer convergence, and conflicting-writer rejection. | A complete fault-injection matrix and long-running process-restart campaign are not yet present. |
| Checkpoint recovery | `ConsumerCheckpoint` is canonical and monotonic; workers advance it only after required outputs are durable. | Production backlog objectives and alerting thresholds are deployment-local and not yet pinned. |
| Bounded cognition | Existing cognitive policies expose finite budgets, and attention reuses an existing disposition after recovery. | The attention worker has no accepted continuous-pilot quota or throughput envelope. |
| Delivery | Transactional outbox/inbox, leases, fencing, idempotent event IDs, and retry backoff are implemented. | There is no retry ceiling, poison-event quarantine, or dead-letter workflow. |
| Information governance | Unknown information fails closed; policy composition, lineage, disclosure, telemetry, `LEARN`, and `EVALUATE` checks exist. The attention provider receives only a schema-approved safe view after source access admission. | Production protected-byte storage, key management, physical retention enforcement, and complete interception are deferred. |
| Retention | Retention and hold semantics exist in policy composition. | Canonical-log and artifact deletion/archival execution is not implemented. |
| Transport security | Deployment adapters accept deployment-supplied endpoints; OTLP can be configured securely. | The SDK does not currently enforce authenticated encrypted PostgreSQL, NATS, or OTLP transport. |
| Observability | A provider-neutral tracer protocol, null tracer, optional OpenTelemetry adapter, OTLP exporter, and scalar span attributes exist. | A centrally enforced safe-attribute allowlist and redaction verification gate do not yet exist. |
| Configuration reproducibility | Attention records mechanism, version, configuration reference, source policy, feature schema, evidence, and costs. | `ExperimentFingerprintV1` and a canonical evaluation-run contract are staged, not implemented. |

## Reliability and semantic integrity

### NFR-REL-01 — deterministic replay

For a fixed canonical history and schema registry, every supported projection
must produce the same semantic snapshot regardless of process restart.

**Proposed pilot target:** 100 consecutive clean-process rebuilds of the frozen
pilot corpus produce byte-identical canonicalized semantic snapshots and zero
normalization errors. The test records corpus head, event count, schema versions,
wall time, and peak resident memory.

### NFR-REL-02 — sequence-gap safety

No correctness check may assume `stored_sequence == predecessor_head + 1`.
State-dependent admission must prove that the recorded causal cursor was the
actual canonical head presented to compare-and-append and that the stored event
follows that head.

**Implemented evidence:** real PostgreSQL sequence-gap regressions exist for
governance and deliberative-attention admission.

**Proposed pilot target:** zero admission or replay failures across 100 runs that
combine rolled-back sequence consumption with two competing writers.

### NFR-REL-03 — local/distributed semantic parity

The same ordered inputs, policy snapshots, configuration, and actual disposition
provider outputs must yield the same semantic state in embedded and distributed
modes. Broker delivery order and retries may differ; canonical meaning may not.

**Proposed pilot target:** canonicalized projections are identical at the same
logical corpus cuts for 100% of the acceptance fixture. Event-store-specific
sequence values and transport metadata are excluded only when the projection
contract explicitly classifies them as non-semantic.

### NFR-REL-04 — crash recovery and idempotence

A crash before a required output must leave the source opportunity incomplete.
A crash after a required output but before its checkpoint must reuse the durable
output and complete only the missing suffix. Concurrent equal observations must
converge; incompatible observations must fail closed.

**Proposed pilot target:** inject failure before and after every durable boundary
in the opportunity → disposition → outcome → feedback → checkpoint flow. After
one successful recovery pass, every recognized opportunity has exactly one
semantic disposition, no output is lost, no checkpoint regresses, and the
provider is not called again for an already durable disposition.

## Bounded operation

### NFR-BOU-01 — finite cognition

Every continuous cognitive loop must have a finite, versioned application
configuration for per-cycle work, daily provider calls, compute/cost, and human
attention. Call these limits `B_cycle`, `B_provider`, `B_compute`, and
`B_human`; their numeric values are application-local and must not become SDK
defaults.

**Proposed pilot target:** observed use never exceeds the active limits. Once a
limit is exhausted, new cognition is deferred without model invocation and the
condition is observable. Recovery of a durable disposition consumes no second
provider call.

### NFR-BOU-02 — bounded event and projection growth

The pilot must measure canonical events, serialized bytes, replay time, and peak
memory per recognized opportunity and per day. It must pin an application-local
daily event budget `G_day`, storage-retention horizon `R_days`, and maximum
rebuild envelope `M_replay` before continuous collection begins.

**Blocker:** the attention exposure projection currently derives over canonical
history and no accepted compaction/snapshot policy exists. Until measured bounds
and retention execution exist, a pilot must be time- and corpus-limited and must
stop ingestion before its pinned envelope is exceeded.

### NFR-BOU-03 — checkpoint lag and backlog

Processing lag is `observed_head_sequence - last_completed_sequence`. Each
deployment must pin warning and stop-admission thresholds `L_warn` and `L_stop`,
plus a recovery-time objective `T_catchup`.

**Proposed pilot target:** lag is exported without content, warnings fire at
`L_warn`, new nonessential cognition stops at `L_stop`, and backlog returns below
`L_warn` within `T_catchup` after the dependency recovers. Threshold values stay
application-local.

## Delivery and retention

### NFR-DEL-01 — poison-event isolation

Retryable transport failure and deterministic semantic rejection are different
conditions. A deployment must pin a finite retry ceiling `R_delivery`. At the
ceiling, the item must enter a durable quarantined/dead-letter state with event
ID, consumer ID, failure class, attempt count, and timestamps—but no protected
payload copy. A required source event may not be skipped by advancing its
checkpoint.

**Blocker:** current outbox/inbox delivery retries with backoff and fencing but
does not implement a retry ceiling or dead-letter path.

### NFR-RET-01 — retention and legal hold

Every protected artifact class and evaluation corpus must have a versioned
retention policy, deletion deadline, and legal-hold behavior. Deleting a derived
cache must not rewrite canonical meaning; deleting protected bytes must leave a
non-content tombstone sufficient to explain why the bytes are unavailable.

**Proposed pilot target:** 100% of governed pilot artifacts have an effective
retention decision. Deletion tests prove removal within the deployment's pinned
grace period while legal holds prevent deletion. Physical enforcement is a
blocker for production protected content.

## Security and privacy

### NFR-SEC-01 — privacy fails closed

Missing policy, lineage, purpose, recipient, locality, provider posture, or
secondary-use permission must deny the operation. Repeated use never grants
permission. `EVALUATE` never grants `LEARN`, and either permission remains
separate from effect authority.

**Proposed pilot target:** every governed corpus read has an allowed material
decision at the exact causal head. Negative tests cover each missing dimension,
legacy policies, cross-domain disclosure, and revoked policy. There are zero
unclassified personal-content fields in canonical attention events.

### NFR-SEC-02 — transport security

Non-loopback production transport must use authenticated encryption with peer
verification. Credentials must come from deployment secret storage and must not
appear in events, logs, traces, experiment fingerprints, or failure strings.

**Proposed pilot target:** deployment startup fails when production PostgreSQL,
broker, or OTLP endpoints lack the application-required secure configuration;
certificate and credential rotation are exercised without canonical data loss.

**Blocker:** this enforcement is not supplied by the current deployment facade.

### NFR-SEC-03 — observability redaction

Telemetry is a governed information use, not an exemption. Default spans and
metrics may contain only allowlisted scalar operational attributes. Content,
prompts, responses, personal identifiers, governed payloads, and credentials are
denied by default. Export across a trust boundary additionally requires allowed
disclosure.

**Proposed pilot target:** seeded sentinel scans over events, logs, metrics,
traces, and error paths find zero protected values; 100% of exported attributes
match the versioned allowlist.

## Evaluation and reproducibility

### NFR-EVAL-01 — configuration identity

Every result used to compare a model, prompt, retrieval, feature, policy, or
ruleset configuration must cite one content-addressed experiment fingerprint and
one immutable corpus cut. Changed dimensions form a new experimental cell.

**Blocker:** the fingerprint runtime is specified in `docs/EVALUATION.md` but is
not yet implemented.

### NFR-EVAL-02 — censored evidence

Unobserved outcome, `UNKNOWN` outcome, and absent feedback are censored—not
negative, accepted, or rejected. Denominator coverage and resolved-outcome rate
must be reported separately.

**Implemented evidence:** the attention projection reports recognized,
disposition-complete, feature-complete, resolved, censored, and feedback-observed
sets independently.

### NFR-MOD-01 — provider neutrality

Core semantics may depend on protocols and immutable provider/configuration
references, not a particular model or observability vendor. A provider swap may
change a fingerprint and results; it may not change event meaning, governance,
replay, or authority ceilings.

## Continuous-pilot acceptance

Before an always-on pilot is called operationally accepted, it must publish an
evidence bundle containing:

1. the exact SDK and application commits;
2. the pinned application-local budgets and backlog thresholds;
3. embedded/distributed parity results;
4. crash, contention, sequence-gap, poison-event, and recovery results;
5. replay time, peak memory, event/byte growth, and retention results;
6. secure-transport and redaction results;
7. a minimum 72-hour soak with no lost semantic disposition, checkpoint
   regression, unresolved poison-event loop, or monotonic memory growth after a
   steady workload begins; and
8. the experiment fingerprint and governed corpus cut for every quality claim.

The current repository proves important deterministic mechanics. It does not yet
provide this complete production evidence bundle.
