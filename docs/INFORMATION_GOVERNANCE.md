# Information Governance Foundation

The deterministic foundation proves one cross-cutting invariant:

```text
possession != access != disclosure != authority
```

It is an implemented subset of
[ADR 0009](adr/0009-information-governance-and-confidential-context.md), not the
complete confidential-data platform.

## Control flow

```text
policy versions + source lineage + immutable principal/access context
                              │
                              ▼
                    PolicyComposition
                              │
                 operation-specific conflicts
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
    internal access     boundary disclosure  declassification
              │               │                │
       retrieval/context/worker feasibility   only legal loosening
```

`InformationPolicy` keeps classification, purposes, recipients, trust domains,
localities, providers, sharing, retention/deletion, holds, disclosure forms,
and declassification authorities independent. `PolicyComposition` takes the
least-permissive classification, intersects permission sets, derives effective
retention bounds, and records conflicts against only the operations they affect.
Thus a legal hold can deny deletion without erasing a separately legal read.

Every material decision pins an immutable `PrincipalSnapshot` and
`AccessContext`. Replay recomputes decisions from the recorded actor, roles,
groups, purpose, operation, trust domains, recipient, time, exact policy
versions, lineage, locality, provider, and provider posture. Present-day role
lookups are not part of replay. Material decisions also cite the exact preceding
canonical head. `InformationGovernanceAdmission` reloads policy state,
re-evaluates the request, and uses conditional append; replay rejects a decision
whose cursor is not its immediate predecessor.

## Lineage, views, and quarantine

Every governed reference resolves through an explicit lineage and immutable
policy binding. Derived information composes all source restrictions. A
redacted or abstracted `DisclosureView` retains that inherited policy:

```text
transformation != declassification
```

Only a `DeclassificationDecision` whose authority is accepted by every source
policy may approve a less restrictive policy. An allowed decision can create a
separate immutable `DeclassifiedDisclosureView` governed by the approved policy.
The view preserves the original source, policy, and lineage references; it never
mutates the source binding, and replay rejects it without its canonical allowed
decision.

Unknown input is `QuarantinedInformationRef`, never implicitly public. The
foundation permits local classification under the quarantine policy and denies
remote-model context, external connectors, cross-agent sharing, shared indexes,
and content-bearing telemetry.

## Implemented enforcement ports

- `MemoryRetriever` can evaluate bound assertions before scoring. Denied
  assertions remain in canonical memory but are absent from results; decisions
  remain available to the caller for material recording or bounded audit.
- `GovernedContextAssembler` evaluates internal access for each explicitly
  governed item. When destination and source trust domains differ, disclosure
  must also allow before the item enters model context.
- `WorkerMatcher` treats access as a hard feasibility predicate after current
  presence/capability checks and alongside competence evidence. Governed leases
  cite canonical access-decision IDs and, for cross-domain workers, canonical
  disclosure-decision IDs. The worker destination must match its immutable
  principal snapshot and policy trust domains. The coordinator admits all
  material decisions and the lease against one uninterrupted canonical head.
  Material denials for otherwise feasible candidates remain replayable, so
  exclusion is explainable.

Historical unbound memory and work remain compatible. Once an information
reference is explicitly governed, missing policy, lineage, context, or access
evidence fails closed.

## Canonical meaning and bounded audit

Policies, lineage, bindings, quarantine, effective declassified views, material
disclosure, and material access outcomes are canonical governance facts. A
`SecurityAuditReceipt` is a non-authorizing summary of a routine access or
disclosure check; the decision need not first become canonical. Receipts remain
outside `InformationGovernanceProjection` and are consumed by the separate
size-bounded `SecurityAuditProjection`, which cannot authorize anything. The governance
projection reads its own policy and decision records through a bounded
privileged bootstrap path, preventing recursive decision-to-receipt loops.

New governance events use opaque subjects and keep protected content out of
IDs, subjects, correlation fields, and metadata. Information identifiers derived
from caller material require an explicit caller-owned HMAC key, including for
low-entropy values; production secret storage and rotation remain deferred. A
reusable validator tests protected values against envelope fields. Retrofitting
every historical Noema event is intentionally deferred.

## Deferred integration slices

This foundation does not implement production encrypted `ArtifactStore` bytes,
real confidential ingestion, KMS/HSM integration, key rotation, crypto-erasure,
production secrets, principal/role attestation, durable grant/revocation
workflows, cross-tenant isolation, arbitrary policy languages, learned
classification, automatic declassification, vector storage, or exhaustive
telemetry/log/error/cache/evaluation/model-response/tool/connector/output
interception. No real restricted information is used in its fixtures.

Those slices remain mandatory before production use of restricted real-world
context. Habit and skill learning also remain separate later milestones; neither
may infer information permission from repeated use.
