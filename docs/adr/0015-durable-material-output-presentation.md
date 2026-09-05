# ADR 0015: Durable Material Output and Presentation Truth

Status: **Proposed — architecture review required; no runtime implementation is authorized**

## Context

Noema can durably record model responses, work completion artifact references,
attention dispositions/outcomes/feedback, broker delivery, and action
lifecycles. None proves that a particular user-facing artifact was received,
displayed, played through a known boundary, acknowledged, understood, or acted
on. Broker outbox/inbox completion only proves transport handling. An attention
delivery flag and a successful model response are also insufficient.

The situated-partner pilot needs barge-in, stale-result rejection, artifact
version continuity, and honest evaluation. Without a generic boundary, a late
response can be presented against superseded intent, unplayed speech can enter
dialogue history, and silence can become false comprehension evidence.

The v1 situated-partner envelope defines a projection shape and a synthetic
guard. New durable semantics require review before implementation.

## Proposed decision

If accepted, add the smallest generic lifecycle that preserves independent
evidence rather than one overloaded status:

1. **Material output.** A content-addressed record identifies artifact/content
   digest, media kind, producing request/model/work reference, context revision,
   generation causal cut, information lineage, and validity/supersession rules.
   Protected bytes remain in governed application storage.
2. **Presentation offer.** An offer identifies the intended recipient/surface,
   artifact version/selection, current context basis, delivery constraints, and
   expiry. It carries no effect authority.
3. **Exact-head revalidation.** Before a material offer is admitted, rebuild
   current intent, context, evidence, artifact version, policy, cancellation,
   and supersession state. Compare-and-append against the actual predecessor
   head; retry only by rebuilding. An unrelated head advance may be revalidated
   without changing semantic identity.
4. **Independent receipts.** Record separate immutable evidence for:

   - transport received;
   - visual content/version/selection displayed;
   - exact audio/media ranges played;
   - explicit user acknowledgement;
   - explicit or separately supported understanding report; and
   - a later attributable user action or separately authorized capability
     execution.

5. **Interruption and supersession.** Barge-in closes the last known played
   range, cancels the unplayed suffix, and excludes that suffix from shared
   dialogue assumptions. Context/intent/artifact changes supersede stale offers
   without deleting their historical evidence.
6. **Outcome and feedback.** Later outcome, explicit feedback, acknowledgement,
   understanding, and action remain different observations. Silence is censored.

The lifecycle uses existing canonical events, exact-head admission,
Information Governance, and checkpoints. It does not replace model/provider
protocols, broker delivery, work completion, action authorization, or
application playback/rendering code.

## Required invariants

```text
generated != transport received != displayed != played
played != acknowledged != understood != acted on != outcome
model response != user delivery
broker delivery != presentation
intervention admission != effect authority
old context result != current answer
```

- Receipt evidence names exact artifact version and, where applicable, exact
  visual selection or played range.
- Unknown understanding, action, or outcome remains unknown.
- A stale/cancelled/superseded offer cannot surface or execute.
- Cross-domain presentation requires both access and disclosure whose admitted
  form matches the presented bytes.
- Source/tool/model content cannot grant authority or initiate effects.
- Realtime provider state and UI animation remain disposable.

## Quality-attribute scenarios

| Scenario | Required response |
|---|---|
| A 30-second brief is interrupted after eight seconds | Persist only the known played range, cancel the suffix, and omit unplayed content from shared dialogue history. |
| A lookup for topic A completes after the user switches to B | Preserve it under A, reject current presentation, and surface later only after explicit relevance revalidation. |
| A confidential brief loses its authorized audio route | Stop or fall back only to a separately authorized nonconfidential surface. |
| Playback completes with no response | Record playback only; understanding, agreement, action, and outcome remain unknown. |
| Context changes between validation and append | CAS fails, reloads, and revalidates; no stale offer becomes canonical. |
| PostgreSQL consumes sequence values in a rolled-back transaction | Replay validates the actual predecessor head, not `new_sequence - 1`. |

## Compatibility and migration

- `ModelResponse`, work completion `artifact_refs`, attention outcomes/feedback,
  action events, and delivery outbox/inbox semantics remain unchanged and do not
  gain new implied meanings.
- Existing two-state application delivery records remain historical partial
  evidence. “Presented” may map only when the exact artifact/version/surface is
  known; “not delivered” does not explain why and cannot be expanded into other
  receipt states.
- Existing Companion IPC/event v2 stays immutable. A future v3 may carry the
  situated envelope and new receipt references additively after consumer tests.
- Unknown event/schema versions fail closed. Any accepted implementation needs
  explicit upcasters that never fabricate played, acknowledged, understood, or
  acted-on evidence.

## Consequences and risks

This boundary enables honest multi-surface context, barge-in, stale result
suppression, and evaluation without treating a UI or provider session as
canonical truth. It also creates potentially high-volume receipts and timing
metadata that may itself be sensitive. Payload minimization, bounded disposable
views, retention, and opaque governed references are mandatory.

Client attestations can be wrong or delayed. A receipt proves what a named
client reported, not objective perception or comprehension. User-visible claims
must retain that evidence qualification.

## Rejected alternatives

- **Reuse broker delivery receipts.** Transport acknowledgement is not display
  or playback.
- **Infer delivery from model completion.** Generation occurs before any user
  surface.
- **Use one presentation enum.** Independent dimensions can coexist and arrive
  at different times.
- **Infer understanding from playback or sentiment.** This creates labels from
  absence and conflates delivery with cognition.
- **Store realtime session state as canonical context.** Provider sessions are
  disposable and provider-specific.
- **Let a stale response silently bind to current context.** This destroys
  causal meaning and can bypass current intent.

## Fitness functions before acceptance

- exact-head concurrency and PostgreSQL sequence-gap tests;
- crash recovery before/after each output, offer, and receipt boundary;
- barge-in tests for played-range closure and unplayed-suffix exclusion;
- stale topic/context/intent/artifact/policy rejection tests;
- privacy tests proving no protected content appears in IDs, telemetry, errors,
  or unrestricted receipts;
- replay tests that never infer missing receipt dimensions;
- bounded projection tests for high-volume playback updates;
- embedded/PostgreSQL/NATS parity; and
- structural tests keeping presentation separate from work, intervention,
  authority, and effects.

## Deferred

This ADR does not authorize runtime code, a voice provider, a UI, media storage,
audio-route policy, ADR 0013 runtime, the mixed portfolio, learned interruption,
HabitForge, workflow learning, or real external connectors. Presentation and
playback adapters remain application-local even after a generic record family
is accepted.
