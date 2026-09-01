# ADR 0009: Information governance and confidential context

- Status: Accepted architecture direction — implementation staged
- Date: 2026-08-31
- Scope: information policy, provenance and composition, internal access,
  artifact retention, declassification, disclosure, and protected derived data

## Context

Noema's canonical log, epistemic memory, model context, agent ecology, tracing,
and future real-world adapters will process information from different security
domains and purposes. A single confidentiality bit cannot represent origin,
purpose, recipient, locality, retention, or declassification constraints.

Information governance intersects
[Intent and Outcome Stewardship](0008-intent-and-outcome-stewardship.md), but it
is separate cross-cutting infrastructure. It must protect memory retrieval,
internal worker visibility, models, tools, telemetry, indexes, connectors, and
outputs regardless of whether the information belongs to a roadmap or
commitment.

## Quality-attribute scenarios

1. A user ingests a possibly confidential artifact whose governing policy is
   unknown. Noema quarantines it, permits only local or otherwise policy-safe
   classification, and prevents external models, connectors, cross-domain
   agents, shared indexes, and content-bearing telemetry from seeing it.
2. A protected artifact produces an observation, assertion, summary, roadmap
   proposal, and work context. Every derivative retains a deterministically
   composed policy and resolvable lineage.
3. Two sources allow disjoint purposes or recipients. Composition exposes an
   incompatible permission and the affected operation fails closed rather than
   inventing permission.
4. A user requests declassification of employer-controlled material but lacks
   authority under its source policy. The user may tighten treatment but cannot
   loosen it.
5. Redaction or abstraction removes visible identifiers. The resulting
   `DisclosureView` remains protected until an explicit authorized
   `DeclassificationDecision` grants a less restrictive disclosure policy.
6. A competent worker lacks access to a source security domain. Internal
   retrieval and context assembly deny the content before assignment or model
   invocation, even if no external egress occurs.
7. A retention policy requests deletion while a valid legal hold requires
   preservation. The composed policy denies deletion, but does not deny an
   independently permitted read for legal review merely because the retention
   dimensions conflict.
8. Raw transcript bytes expire. Canonical history preserves an opaque reference,
   protected digest, classification, lineage, policy, and tombstone without
   leaking content through either the event payload or envelope.
9. A trace, exception, cache, embedding index, replay fixture, or evaluation
   artifact would contain protected data. The same access/disclosure policy
   prevents or transforms the sink write.
10. A trusted local model and a remote provider receive equivalent requests.
    Both require internal access; only the request that crosses a trust-domain
    boundary requires a disclosure decision.
11. Replay through the same event cursor, policy versions, and immutable
    principal/access snapshot reproduces the same effective policies, internal
    access decisions, and disclosure decisions even if current group membership
    or provider posture has changed.

## Decision

1. Make `InformationPolicy` multidimensional and versioned. It represents at
   least origin/security domain, sensitivity/classification, allowed purposes,
   permitted recipients and trust domains, processing locality/providers,
   cross-agent sharing, retention bounds and holds, disclosure forms, and
   declassification authorities.
2. Define a typed `PolicyComposition` operation with field-specific semantics,
   not one generic ordering:

   - sensitivity takes the least-permissive value in a declared classification
     lattice;
   - allowed purposes, recipients, trust domains, providers/localities, and
     sharing scopes intersect;
   - an empty required permission intersection is incompatible and denies the
     affected operation;
   - retention composes minimum/maximum retention windows, deletion duties, and
     legal holds into effective constraints plus explicit conflicts; each
     `PolicyDecision(operation)` evaluates whether a conflict affects that
     operation, so a legal hold can deny deletion without automatically denying
     a separately permitted legal-review read;
   - declassification requires authority acceptable to every governing source
     policy;
   - missing, unknown, or incomparable permissions relevant to the requested
     operation fail closed.

   ```text
   PolicyComposition
       → effective constraints + explicit conflicts

   PolicyDecision(operation)
       → evaluate the constraints and conflicts relevant to that operation
   ```

   `PolicyDecision(operation)` is the common evaluation performed within
   `InformationAccessDecision` and `DisclosureDecision`, not a third persisted
   decision type.

3. Default unresolved policy to quarantine rather than permissive inference:

   ```text
   RAW INGEST
       → QUARANTINED
       → local / policy-safe classification
       → InformationPolicy resolved
       → normal ingestion / derivation
   ```

   Until policy is resolved, the artifact has no external-model or
   external-connector access, no inter-agent cross-domain sharing, no insertion
   into shared embedding or lexical indexes, and no telemetry containing its
   content. Classification itself must run in a locality and trust domain
   permitted by the quarantine policy; otherwise human review is required.
4. Make lineage first-class across:

   ```text
   Artifact → Observation → Evidence → Assertion → Summary
            → Goal/Roadmap/Plan → Work Context → Output
   ```

   Every derivative computes its effective policy from resolved sources and
   policy versions. A transformation never breaks lineage.
5. Separate transformation from declassification:

   ```text
   protected sources
       → composed inherited policy
       → redaction / abstraction
       → DisclosureView (still protected)
       → explicit DeclassificationDecision
       → possibly less restrictive disclosure policy
   ```

   Redaction and abstraction alone never loosen policy. A user can always
   request stricter handling; loosening requires authority recognized by every
   governing source, which may exclude the user for employer, legal, or
   institutional material.
6. Keep raw documents, audio, images, transcripts, and other opaque bytes in a
   policy-governed encrypted `ArtifactStore`. Canonical events retain artifact
   references, digests, classification, provenance, policy/version references,
   semantic claims where appropriate, and retention/tombstone transitions.
   Credentials appear only as secret references. Protection applies to the
   entire canonical event envelope, not only its payload: protected content must
   not appear in event IDs, subjects, correlation identifiers, metadata, tags,
   filenames, exception text, or other indexing fields unless that field is
   itself policy-governed and access-controlled. Use opaque stable identifiers
   by default. Ordinary document integrity may use content digests; small or
   low-entropy protected values use keyed digests or another construction that
   resists dictionary recovery.
7. Distinguish two mandatory decisions by trust boundary, not object type:

   - `InformationAccessDecision` asks whether an actor or process may access the
     information in its current trust domain. It controls internal retrieval,
     event/projection views, context assembly, worker visibility, model/tool
     input, and index/cache reads;
   - `DisclosureDecision` asks whether the information may cross from trust
     domain A to trust domain B. It controls cross-domain models, tools,
     connectors, inter-agent messages, and user/external outputs.

   A trusted local model or parser may require only access; a remote model
   provider or SaaS tool requires both access and disclosure. Every recorded
   decision references an immutable `AccessContext` containing a
   `PrincipalSnapshot`, actor/principal, role and group membership, source and
   destination trust domains, purpose, requested operation, recipient, decision
   time, policy versions, source lineage, and relevant provider/security posture.
   Direct event-store access is a privileged infrastructure boundary, not
   ordinary worker visibility.
8. Apply governance to every material sink: canonical semantic event views,
   memory retrieval, prompts and model responses, work contexts, telemetry,
   traces, logs, error reports, caches, embeddings/vector and lexical indexes,
   replay fixtures, evaluation artifacts, artifacts, connectors, tools,
   inter-agent protocols, and final outputs.
9. Permit confidential semantic claims in canonical events only when their
   policy and lineage are explicit and ordinary consumers use access-controlled
   projections/read ports. Raw protected bytes remain outside event payloads.
10. Add information access as a worker-feasibility dimension:

   ```text
   eligible = capability ∧ competence ∧ availability ∧ information access
   ```

   Information access does not imply intent authority or effect authority.
11. Use provenance-bearing `SituationCapsule` or equivalent context views as the
    normal reasoning unit. Full, redacted, abstracted, and denied views share
    lineage and record their access/disclosure decisions.
12. Separate canonical security semantics from high-volume security audit
    receipts:

    ```text
    CANONICAL SECURITY SEMANTICS
    policy versions | lineage | declassification | artifact lifecycle
    durable grants/revocations | material/exceptional disclosure decisions
    material denials

    SECURITY AUDIT RECEIPTS
    individual retrieval checks | routine permitted disclosures
    individual remote-model/tool transfers | cache/index reads
    routine allowed decisions
    ```

    Both records are append-only and auditable, and may share the same physical
    event infrastructure, but routine receipts remain outside ordinary situation
    projection and do not become a second authorization source of truth.
    Durable security meaning is canonical; high-volume enforcement occurrences
    are audit receipts. For example, a durable grant allowing a provider to
    receive a classification for a purpose is canonical, while each routine
    transfer under that unchanged grant is normally a receipt unless that
    disclosure is itself material or exceptional.
    Effective policy, recipient-specific views, and indexes are rebuildable
    projections. The privileged enforcement boundary has an explicit bootstrap
    path for reading policy and writing its receipt without recursively requiring
    another receipt-producing decision; bootstrap use is itself bounded and
    auditable.
13. Implement and test this architecture before real confidential employer or
    similarly restricted context enters production Noema. It is not a side
    feature of portfolio stewardship and can be delivered independently.

## Consequences and tradeoffs

- Internal least privilege becomes enforceable before external egress, closing
  the global-event-log leakage path.
- Quarantine makes unknown inputs safe by default, but useful processing may
  wait for a trusted local classifier or human policy assignment.
- Field-specific composition is more complex than a scalar label but exposes
  real incompatibilities rather than silently broadening access. Evaluating
  conflicts per operation preserves unrelated legitimate access at the cost of
  a larger decision matrix.
- Explicit declassification preserves useful redaction and abstraction while
  preventing those transformations from laundering protected information.
- Storing raw bytes outside the event log preserves retention and erasure
  control at the cost of a second storage substrate. It is not a second semantic
  authority: canonical events govern artifact identity, policy, lineage, and
  lifecycle; the store owns encrypted byte availability.
- Access-controlled projections and sink enforcement add latency and operational
  complexity. Policy decisions require caching that remains keyed by actor,
  purpose, source lineage, policy version, and immutable access context.
- Opaque envelope identifiers reduce accidental leakage but make raw operational
  inspection less descriptive; authorized projections must supply safe labels.
- Separating canonical security semantics from audit receipts bounds cognitive
  log growth and avoids recursive audit events, while requiring joined audit
  tooling across the two logical streams.
- Conservative failure may reduce usefulness, but an explicit review or
  declassification path is safer than implicit permission.

## Rejected alternatives

- **One `confidential` flag:** cannot express purpose, locality, retention,
  recipient, holds, sharing, or declassification authority.
- **One generic policy maximum:** these dimensions do not share a total order.
- **Ingest first and classify later under ordinary permissions:** exposes unknown
  data to providers, indexes, or telemetry before its constraints are known.
- **Treat redaction as declassification:** removed identifiers do not prove a
  disclosure is permitted or non-identifying.
- **Assume user approval can always loosen policy:** source owners, employers,
  contracts, or law may reserve that authority.
- **Check only external egress:** unauthorized internal retrieval is already a
  disclosure within the system.
- **Let each adapter decide:** produces inconsistent enforcement and an
  untraceable policy boundary.
- **Write raw protected bytes to immutable events:** makes retention, erasure,
  secret rotation, and least privilege structurally unsafe.
- **Protect only event payloads:** subjects, identifiers, tags, filenames, and
  exception metadata can disclose the same protected facts.
- **Classify models and tools as disclosure by object type:** a local trusted
  process and a remote SaaS provider have different trust-boundary behavior.
- **Exclude observability and indexes:** traces, logs, fixtures, caches, and
  embeddings are common disclosure paths, not harmless implementation details.
- **Record every access check as an ordinary situation event:** bloats semantic
  projection and creates recursive access-decision logging.

## Fitness functions for implementation

- policy composition has table-driven tests for every field, incompatibility,
  unknown value, deletion bound, and legal hold, including proof that a hold
  denies deletion without automatically denying a permitted legal-review read;
- unresolved policy at ingestion enters quarantine, and tests prove quarantined
  content cannot reach external models/connectors, cross-domain agents, shared
  indexes, or content-bearing telemetry;
- unresolved lineage, policy versions, or permissions relevant to an operation
  fail that operation closed;
- a derived artifact cannot have a less restrictive policy without a valid
  `DeclassificationDecision` authorized under every source policy;
- redaction and abstraction tests prove their output initially retains the
  composed source policy;
- an unauthorized worker cannot read protected canonical claims through event,
  projection, retrieval, context, cache, or index APIs;
- every model/tool access passes `InformationAccessDecision`; every model, tool,
  connector, inter-agent, or output path that crosses a trust domain also passes
  `DisclosureDecision`;
- equivalent local-trusted and remote-provider tests prove that disclosure is
  determined by trust-domain crossing rather than adapter or object type;
- telemetry, trace, log, error, cache, embedding/index, replay-fixture, and
  evaluation sinks have structural policy gates and leakage tests;
- schema and architecture tests reject raw artifact bytes, credentials, and
  ungoverned protected content from every canonical envelope field, including
  IDs, subjects, correlation metadata, tags, filenames, and exception text;
- digest tests require a keyed or equivalently dictionary-resistant construction
  for small or low-entropy protected values;
- matcher feasibility rejects missing information access independently of
  competence and authority;
- artifact tombstoning removes raw bytes while preserving canonical lifecycle
  and lineage metadata;
- every recorded decision pins an immutable `AccessContext` and
  `PrincipalSnapshot`; replay does not consult current roles, memberships, trust
  domains, time, recipient state, or provider posture;
- routine allowed retrieval/cache/index checks and permitted cross-domain
  transfers write bounded security audit receipts outside ordinary situation
  projection, while durable disclosure grants, material disclosures, material
  denials, and other durable security semantics remain canonical;
- bootstrap enforcement can read policy and append one bounded receipt without
  recursively producing another decision, and unauthorized bootstrap use fails;
- identical canonical history, policy versions, and access-context snapshots
  reproduce byte-equivalent effective policies and decision projections.

This proposal extends [ADR 0005](0005-persistent-cognitive-memory.md),
[ADR 0007](0007-durable-work-coordination.md), and
[ADR 0008](0008-intent-and-outcome-stewardship.md). Its delivery dependency is
recorded in the [roadmap](../ROADMAP.md).
