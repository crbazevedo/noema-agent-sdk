# Situated Partner integration contract

Status: **SDK contract candidate — synthetic conformance only.** The Companion
owns product scope and the shared schedule. The SDK owns the reusable semantic
boundaries, this sanitized mirror, and its conformance gate.

Program: `noema-companion-p0`

Requirement revision: `situated-partner-2026-09-05-v1`

Source requirements digest:
`sha256:ce7cc401f1d4452c491acf438828dea801b5fc7e104a0a09cc6970cde1e6e587`

The exact consumable SDK source commit and the digests of the mirror, schema,
fixture, and conformance example are recorded in the lock-only child commit at
`docs/pilot/situated-partner.lock.json`. A consumer must pin that source commit,
not this branch or moving `main`. Existing Companion IPC/event v2 meanings and
its historical SDK dependency pin remain unchanged. A future Companion v3 may
carry this envelope additively after its own consumer tests.

The committed Project Meridian fixture is fictional and runs on a fictional
Linux workstation. It contains no private user material and proves only a
deterministic SDK integration boundary—not live voice, real source access,
field effectiveness, uninterrupted background monitoring, protected storage,
or a qualifying learning corpus.

## Normative separations

The pilot must preserve these independent decisions:

```text
source acquisition priority
    != cognitive priority
    != intervention priority
    != effect authority
```

```text
Observation
  -> CognitiveDemand
  -> CognitiveAllocation
  -> Assessment
  -> InterventionOpportunity
  -> InterventionAllocation
  -> silence / remember / defer / wake
```

The existing scarce-cognition machinery remains the eventual shared substrate.
This contract does not implement a mixed portfolio or ADR 0013 runtime. A
`WorkOrder` may prepare a proposal, but only a separately admitted
`ActionIntent` may authorize an effect. Retrieved content is inert evidence: it
cannot create a permission, revise intent, dispatch work, or execute an effect.

Likewise:

```text
scheduled event != confirmed outcome
historical evidence != current intent
generated != received != displayed != played
played != acknowledged != understood != acted on
task execution state != evidence freshness != intervention readiness
```

## Shared envelope v1

The provider-neutral schema is
[`situated-partner-envelope-v1.schema.json`](contracts/situated-partner-envelope-v1.schema.json).
It is a versioned projection/exchange boundary over canonical SDK records, not
a new event family, memory store, UI queue, or scheduler.

Every envelope carries:

- `context_id` and `situation_id` as distinct opaque references;
- a positive `context_revision` and the actual nonnegative canonical head in
  `causal_cut`; no consumer may infer contiguous event sequences;
- session, turn, topic, and request correlation with explicit `null` when not
  applicable;
- the governing goal revision, outcome, and artifact IDs/versions;
- task state, deadline, next check, finite budgets, and measured or unknown
  usage;
- explicit information, lineage, binding, policy, access-decision, and
  cross-domain disclosure-decision references in the SDK's opaque identifier
  format;
- cancellation, supersession, and validity references; and
- optional source-request, source-result, or material-output data selected by
  `message_kind`.

Unknown schema versions fail closed. `source_requirements_digest` identifies
the approved source ledger; it is not the digest of the schema itself. File
digests live in the external lock because a file cannot contain its own digest
without self-reference.

The published Draft 2020-12 schema encodes `message_kind` discrimination:
request, result, and material-output bodies are mutually exclusive, and a
presentation-ready material output must name its revalidation basis. Consumers
must use a validator that implements those standard conditionals. The example
validator additionally enforces relational rules JSON Schema cannot express,
including finite usage not exceeding budgets, valid playback intervals, and
matching cross-domain disclosure fingerprints.

Source content is inert, untrusted input. It cannot grant access or disclosure,
alter intent, create authority, or execute an effect. A trust-domain crossing
requires opaque admitted access and disclosure decisions, an admitted
disclosure-view reference, and equality between caller-keyed fingerprints of
the admitted form and the transmitted payload. Content is never placed in
correlation fields or ordinary telemetry.

### Source request and result

A request pins the context basis, target fact, reason, source scope/account,
match policy, deadline, and finite query/read/model/time/cost limits. A result
links the request and its original context basis, while the envelope causal cut
records the actual head at which the result is considered. Its status is
exactly one of:

```text
FOUND
NO_MATCH_IN_SCOPE
NOT_YET_AVAILABLE
SOURCE_UNAVAILABLE
ACCESS_DENIED
AMBIGUOUS_MATCH
FACT_NOT_ESTABLISHED
CONTRADICTED
```

The result also identifies source version/cursor, observation time, evidence,
coverage, limitations, retry eligibility, and expiry. Acquisition coverage is
not `AwarenessCoverage`: the former says what a bounded source operation
covered; the latter is a derived epistemic freshness/confidence view.

The envelope is usable by a synthetic or application-local adapter now.
Canonical, reusable source-acquisition and observation-scope lifecycle events
remain a proposed architecture lane in
[ADR 0014](../adr/0014-durable-situation-watch-and-source-acquisition.md).

### Task and Observatory state

Execution state is limited to:

```text
queued / running / awaiting_source / blocked / completed / cancelled / expired / unknown
```

Evidence freshness is separately `current`, `stale`, or `unknown`. Applications
must not map a lease directly to “running,” an invalidated plan directly to
“cancelled,” elapsed time to progress, or a model call to thought. The optional
Observatory is a disposable application read model rebuilt at one canonical
cut. It may attach an explicitly stale or unavailable runtime telemetry overlay,
but OpenTelemetry is never its source of truth and never changes authority.

Hide, pause, and stop-monitoring remain different product commands. Durable
pause, expiry, revocation, catch-up scheduling, and work-start/cancel semantics
are not made real by this schema.

### Material-output and presentation truth

A material output records its generation basis and, before presentation, the
context revision and causal cut at which it was revalidated. Transport receipt,
display, exact played ranges, explicit user acknowledgement, understanding
evidence, and later action evidence remain separate fields. Empty evidence
means unknown—not false and not silently inferred.

Broker outbox/inbox delivery does not establish user delivery. The missing
generic durable offer/presentation/playback/supersession lifecycle is proposed
for review in
[ADR 0015](../adr/0015-durable-material-output-presentation.md). Until accepted
and implemented, Companion receipts remain application events and synthetic
tests must not claim the generic runtime gap is closed.

## G1 conformance composition

The executable
[`situated_partner_conformance.py`](../../examples/situated_partner_conformance.py)
and [Project Meridian fixture](fixtures/project-meridian-g1.json) use existing
public APIs:

1. `GoalRevision`, `IntentAuthority`, and `OutcomeNode` express an explicit
   current user-authored outcome.
2. `SemanticAssertion`, `EpistemicType`, and `AssertionStatus` keep an observed
   schedule distinct from a simulated forecast and preserve unknown outcomes.
3. `SourceState`, `AwarenessDemand`, `AwarenessCoverage`, and
   `ObservationBudget` expose decision-relevant staleness and finite evidence
   work.
4. `WorkOrder.deadline` and `opportunity_window_end` carry the decision window,
   while the fixture explicitly cancels the old request after a reschedule.
5. `IntentStewardCoordinator` plus `NoemaKernel.emit_if_head` admits real goal
   revisions at their exact predecessor heads; every envelope uses the same
   exact-head boundary.
6. `StrategicProjection`, `WorkProjection`, and a pure
   `PilotObserverProjection` independently rebuild the referentially closed
   canonical history, with no OTel dependency.
7. `WorkOrder.authority_ceiling=PROPOSE` remains distinct from an
   `ActionIntent`; `PolicyEngine` denies the effect under a proposal-only
   profile.
8. The application-side stale-result guard compares situation, context,
   goal/outcome, evidence, artifact, policy, topic, freshness, cancellation,
   supersession, and material revalidation before output may surface.

The test harness intentionally exposes the current limits. `AsyncScheduler` is
in-memory; WorkOrder deadlines are descriptive rather than a ReadyFrontier
gate; goal revision does not automatically cancel already admitted work; and
the generic agent effect path has no universal final presentation revalidation.
G1 applications must explicitly compose invalidation and current-context checks
without calling those gaps implemented runtime semantics.

## Readiness map

`IMPLEMENTED` below means implemented SDK substrate coverage, never completion
of the whole user requirement. Every program requirement remains
`USER_APPROVED_REQUIREMENT` until the Companion-owned evidence stage changes it.
The machine-readable source of this table is
[`situated-partner-contract-v1.json`](situated-partner-contract-v1.json).

<a id="req-01-through-req-06--stewardship-inquiry-and-bounded-runtime"></a>

### REQ-01 through REQ-06 — stewardship, inquiry, and bounded runtime

| ID | Owner | SDK readiness | SDK coverage status | Acceptance | Slice |
|---|---|---|---|---|---|
| REQ-01 proactive situation stewardship | Companion lead | NEEDS_ARCHITECTURE_REVIEW | PROPOSED_DESIGN | T01, T08, T34 | G1, G3 |
| REQ-02 temporal uncertainty and coverage | Companion lead | REUSE_EXISTING | IMPLEMENTED | T02, T35 | G1, G3 |
| REQ-03 instrumental active inquiry | Companion lead | COMPANION_LOCAL | DEFERRED | T06, T07 | G1, G3 |
| REQ-04 intentional source acquisition | Companion lead | NEEDS_ARCHITECTURE_REVIEW | PROPOSED_DESIGN | T01, T03–T05, T34 | G1, G3 |
| REQ-05 independent resource decisions | Joint contract | REUSE_EXISTING | IMPLEMENTED | T08, T33 | G1, G5 |
| REQ-06 bounded effort and availability | Joint contract | NEEDS_ARCHITECTURE_REVIEW | PROPOSED_DESIGN | T09–T11 | G1, G3, G6 |

REQ-01 reuses intent, continuity, work, checkpoints, and explicit invalidation,
but durable no-prompt watches/cancellation still need ADR 0014. REQ-03's
ask/retrieve/wait/prepare/abstain branch table is product policy. It must ask
only when plausible answers change action, timing, owner, scope, safety, or
verification; question count is not an objective. REQ-05 is already protected
by distinct cognition, attention, work, and effect authority. REQ-06 reuses
finite budgets and wake reconstruction but does not yet have durable quiet
windows or general catch-up scheduling.

<a id="req-07-and-req-08--optional-truthful-observatory"></a>

### REQ-07 and REQ-08 — optional truthful Observatory

| ID | Owner | SDK readiness | SDK coverage status | Acceptance | Slice |
|---|---|---|---|---|---|
| REQ-07 Situation Observatory | Companion lead | COMPANION_LOCAL | DEFERRED | T12, T33 | G1, G3 |
| REQ-08 truthful observability/control | Companion lead | NEEDS_ARCHITECTURE_REVIEW | PROPOSED_DESIGN | T12, T13 | G1, G3 |

The interface, list/timeline design, accessibility, and ten-second comprehension
goal are Companion-local. Canonical projections supply evidence; actual runtime
measurements are a non-authorizing overlay. Durable stop-monitoring depends on
the observation-scope review rather than a UI state mutation.

<a id="req-09-through-req-12--one-context-dialogue-and-presentation-truth"></a>

### REQ-09 through REQ-12 — one context, dialogue, and presentation truth

| ID | Owner | SDK readiness | SDK coverage status | Acceptance | Slice |
|---|---|---|---|---|---|
| REQ-09 context across surfaces | Companion lead | ACCEPTED_GENERIC_GAP | PROPOSED_DESIGN | T14, T21 | G1, G2 |
| REQ-10 situated live dialogue | Companion lead | COMPANION_LOCAL | DEFERRED | T14, T17, T34 | G2 |
| REQ-11 playback/presentation truth | Companion lead | NEEDS_ARCHITECTURE_REVIEW | PROPOSED_DESIGN | T15, T20, T36 | G1, G2 |
| REQ-12 concurrent context updates | Companion lead | NEEDS_ARCHITECTURE_REVIEW | PROPOSED_DESIGN | T16, T18 | G1, G2 |

The v1 envelope closes the typed projection/consumer-contract gap for REQ-09;
it does not make context another canonical database. Dialogue, pronoun
resolution, provider selection, voice UX, and rehearsal remain Companion-local.
Material presentation CAS and durable playback receipts wait for ADR 0015.

<a id="req-13-and-req-14--readiness-now-recurring-cause-later"></a>

### REQ-13 and REQ-14 — readiness now, recurring cause later

| ID | Owner | SDK readiness | SDK coverage status | Acceptance | Slice |
|---|---|---|---|---|---|
| REQ-13 Meeting Readiness | Companion lead | COMPANION_LOCAL | DEFERRED | T19, T22, T34 | G1–G3 |
| REQ-14 immediate help versus recurring cause | Companion lead | ACCEPTED_GENERIC_GAP | ACCEPTED_ARCHITECTURE | T22, T23 | G2, G4 |

Meeting-specific detection, cards, brief duration, joining behavior, and scenario
support are application semantics. A readiness gap is a missing supported
prerequisite, not a trait judgment. Recurrent-cause developmental intervention
is accepted in ADR 0013 but its runtime remains staged.

<a id="req-15-through-req-18--activity-and-workflow-intelligence-remain-application-local"></a>

### REQ-15 through REQ-18 — activity and workflow intelligence remain application-local

| ID | Owner | SDK readiness | SDK coverage status | Acceptance | Slice |
|---|---|---|---|---|---|
| REQ-15 governed activity observation | Companion lead | NEEDS_ARCHITECTURE_REVIEW | PROPOSED_DESIGN | T24, T25 | G3, G4 |
| REQ-16 activity episodes/workflow bank | Companion lead | COMPANION_LOCAL | DEFERRED | T24 | G4 |
| REQ-17 improve rather than imitate | Companion lead | COMPANION_LOCAL | DEFERRED | T26 | G4 |
| REQ-18 selective technology/practice research | Companion lead | COMPANION_LOCAL | DEFERRED | T27 | G4 |

Narrow authorized observation may precede Habit Learning and later supply a
candidate corpus. It must not wait for broad v0.8 Situated Presence, and it must
not bypass `LEARN`. Observation scope needs ADR 0014. Episode segmentation,
workflow hypotheses, process experiments, research criteria, and tool choices
stay application-local and evidence-bearing.

<a id="req-19-and-req-20--artifact-quality-and-developmental-restraint"></a>

### REQ-19 and REQ-20 — artifact quality and developmental restraint

| ID | Owner | SDK readiness | SDK coverage status | Acceptance | Slice |
|---|---|---|---|---|---|
| REQ-19 artifact quality/contextual fit | Companion lead | COMPANION_LOCAL | DEFERRED | T28 | G1, G2, G4 |
| REQ-20 capability growth without paternalism | Companion lead | ACCEPTED_GENERIC_GAP | ACCEPTED_ARCHITECTURE | T23, T29 | G2, G4 |

Work verification and evidence links support named checks, but the artifact
rubric is product policy. Explicit delegation remains legitimate; applications
must not turn “do it” into compulsory practice. ADR 0013 preserves current
outcome and decision ownership while keeping later capability effects secondary.

<a id="req-21-and-req-22--information-governance-and-private-storage"></a>

### REQ-21 and REQ-22 — Information Governance and private storage

| ID | Owner | SDK readiness | SDK coverage status | Acceptance | Slice |
|---|---|---|---|---|---|
| REQ-21 privacy/source integrity | Joint contract | REUSE_EXISTING | IMPLEMENTED | T04, T20, T21, T25, T31 | G1–G5 |
| REQ-22 private storage/packaging gates | Joint contract | ACCEPTED_GENERIC_GAP | ACCEPTED_ARCHITECTURE | T31 | G3, G5 |

Information Governance already supplies immutable lineage/bindings, purpose-
and-operation-specific access, disclosure, declassification, and separate
`TELEMETRY`, `EVALUATE`, and `LEARN` use. Any remote provider call requires both
access and an explicit cross-trust-domain disclosure decision whose admitted
form matches the bytes sent. Current application adapters must close that
consumer gap before live remote context.

ADR 0009 accepts protected-artifact architecture, but encrypted bytes, key
management, physical retention/deletion, backup behavior, secure transport, and
signed native packaging remain unproven. File permissions are not encryption.

<a id="req-23-through-req-26--evaluation-learning-history-and-program-truth"></a>

### REQ-23 through REQ-26 — evaluation, learning, history, and program truth

| ID | Owner | SDK readiness | SDK coverage status | Acceptance | Slice |
|---|---|---|---|---|---|
| REQ-23 evidence-grade evaluation | Companion lead | ACCEPTED_GENERIC_GAP | PROPOSED_DESIGN | T30, T32, T36 | G3, G5 |
| REQ-24 HabitForge boundary | Companion lead | REUSE_EXISTING | BLOCKED | T30 | G5 |
| REQ-25 developmental personal model | Companion lead | REUSE_EXISTING | IMPLEMENTED | T18, T35 | G1, G2, G4 |
| REQ-26 pilot scope/milestones | Companion lead | COMPANION_LOCAL | SYNTHETICALLY_VERIFIED | T37 | G0–REVIEW |

Attention telemetry already preserves eligible denominators, actual
dispositions, later outcomes, explicit feedback, unknowns, and censoring.
Reproducible experiment identity and canonical evaluation-run admission remain a
documented generic gap. Habit Learning remains blocked until a real, permitted,
representative, denominator-complete corpus exists. Synthetic rehearsal never
qualifies it. Bitemporal attributed memory may inform a current decision, but
the current goal revision governs and no personality database or universal
improvement score is permitted.

## Mandatory conformance disposition and truth ceiling

| Case | SDK status | Evidence or remaining boundary | What it does not prove |
|---|---|---|---|
| T01 | PROPOSED_DESIGN | The fixture specifies reschedule/supersession and preserves the independent business cutoff. | Durable autonomous scheduling runtime. |
| T02 | SYNTHETICALLY_VERIFIED | Real `SemanticAssertion` records keep observed schedule and simulated outcome distinct; absent outcome stays unknown. | A real event outcome. |
| T09 | PROPOSED_DESIGN | The fixture declares an awake-only interval and existing `AwarenessCoverage` shows incomplete evidence. | Durable sleep detection, catch-up scheduling, or uninterrupted monitoring. |
| T10 | SYNTHETICALLY_VERIFIED | A real terminal `GoalRevision` and the full basis guard reject stale presentation. | Automatic cancellation of every admitted work item. |
| T11 | SYNTHETICALLY_VERIFIED | The validator rejects usage above query/read/model/cost ceilings. | Production quota enforcement across every adapter. |
| T13 | SYNTHETICALLY_VERIFIED | Observer state replays from canonical events with OTel unavailable. | Isolation from every malformed custom tracer implementation. |
| T16 | SYNTHETICALLY_VERIFIED | Goal/outcome/situation/context/assertion/artifact/policy/lifecycle mismatch rejects stale output. | Accepted generic presentation lifecycle. |
| T25 | PROPOSED_DESIGN | The fixture specifies exclusion and zero observations; ADR 0014 owns durable scope semantics. | Durable pause/expiry/revocation observation scope. |
| T30 | PROPOSED_DESIGN | The fixture specifies a solicited-only corpus as ineligible; no qualifying corpus exists. | Any real Habit Learning corpus. |
| T31 | PROPOSED_DESIGN | Opaque governance references and fail-closed cross-domain envelope rules are executable; protected storage remains absent. | Restricted-byte storage, deletion, backup, or packaging. |
| T35 | SYNTHETICALLY_VERIFIED | Actual historical and current `GoalRevision` IDs prove the current revision governs. | Developmental effectiveness. |
| T34 | SYNTHETICALLY_VERIFIED | A 20-event referentially closed fictional timeline composes actual SDK goal, memory, work, authority, CAS, and replay records. | The actual Companion G1, live dialogue, or field effectiveness. |

The machine mirror is authoritative for every T01–T37 status. Cases not named
as synthetically verified remain `PROPOSED_DESIGN` until executable evidence
exists; T37 retains only the pack's structural synthetic validation. No case in
this branch is `LIVE_SUPERVISED` or `PILOT_VALIDATED`.

## Dependency and delivery contract

The mirrored 17-work-package graph is acyclic. `W01` still depends on the
Companion-owned `W00`; this SDK branch prepares the shared freeze but cannot
declare it complete until the Companion confirms consumption. `W02` is this
conformance-first SDK slice.

The pilot adds a cross-cutting dependency path without renumbering SDK releases:

```text
governed narrow observation
  -> source-grounded supervised operation
  -> learning-grade operational corpus
  -> conditional ADR 0012 corpus review
```

This path corresponds to `W09 -> W10 -> W11 -> W14`. Broad Situated Presence
remains v0.8; narrow authorized application observation does not wait for Habit
Learning, and observation alone never authorizes learning.

## Consumer checklist

Before a Companion v3 adapter consumes this contract:

1. Verify the source requirements digest and all lock-file content digests.
2. Pin the exact `sdk_contract_source_sha`; do not consume moving `main`.
3. Reject unknown envelope versions and keep IPC/event version domains separate.
4. Preserve context, topic, request, cancellation, and supersession references
   through provider/tool round trips.
5. Rebuild current intent/evidence/artifact state before material presentation
   or effect; reject a stale result rather than silently rebinding it.
6. Admit both access and disclosure before crossing a trust domain; ensure the
   admitted disclosure form matches the payload actually sent.
7. Keep source contents out of IDs, correlation metadata, ordinary telemetry,
   exceptions, and this repository.
8. Report application adapters and synthetic evidence honestly. Do not call the
   proposed ADR 0014/0015 runtime implemented.
