# Companion P0 pilot

## Purpose

The product promise is:

> Run my work. Improve my decisions. Help me improve.

The Companion may present application functions such as sentinel, chief of
staff, thought partner, technical mentor, development coach, and epistemic
steward. These are product functions—not SDK personas, authorities, schedulers,
or new core ontologies.

P0 is the first empirical slice of the “improve my decisions” part of that
promise. It records a governed, denominator-complete account of which real
opportunities were eligible for attention, what the Companion actually decided,
what happened later, and what the user explicitly said. It does not learn or
activate policy, mutate user goals, or execute effects.

## Exact evidence pins

The architecture and integration plan were prepared against:

| Repository role | Exact commit | Meaning |
|---|---|---|
| Accepted SDK main | `52c1695cfce1de4680b7343fe3fc0c8a03b4c7d5` | Accepted ADR 0012 architecture baseline. |
| SDK telemetry prerequisite | `42fd3c4ea656eff0dce011b36452a131c802fd9a` | Documentation-accepted attention-telemetry implementation; must remain in the pilot SDK ancestry. |
| Companion main | `671ef7ed6b468226a6c6c1f21d74e7207e6cece1` | Audited deterministic C0 application baseline; not proof of P0 telemetry integration. |

Every pilot artifact must record the exact SDK and Companion commits actually
run. Verify the pins before building a corpus:

```bash
git -C <sdk-repository> merge-base --is-ancestor \
  42fd3c4ea656eff0dce011b36452a131c802fd9a HEAD
git -C <sdk-repository> rev-parse HEAD
git -C <companion-repository> rev-parse HEAD
```

The first command must succeed. The latter two outputs must be copied into the
pilot manifest; do not substitute a branch name or package version for a commit.
If the Companion is intended to remain at the audited baseline, its output must
equal `671ef7ed6b468226a6c6c1f21d74e7207e6cece1`.

## Scope

P0 observes one narrow decision seam:

```text
application situation
    -> label-blind opportunity event
    -> canonical attention source policy
    -> actual Companion attention decision
    -> explicit AttentionDispositionDecision
    -> canonical disposition
    -> later real outcome event and link
    -> optional explicit user feedback event and record
    -> denominator audit / governed evaluation
```

The P0 corpus uses the SDK's implemented `deliberative_attention_v1` contracts.
No inferred label is acceptable. The disposition provider reports the decision
that actually controlled the Companion's behavior; it does not reconstruct that
decision from a displayed surface, later user activity, or silence.

## Integration seam

| Step | Companion responsibility | SDK contract |
|---|---|---|
| 1. Define eligibility | Choose a general opportunity event family and label-blind fields. Keep product-specific source extraction local. | `AttentionSourcePolicySnapshot` records event types, scope, source/subject prefixes, required fields, version, and feature schema. Recognition starts only after the policy is canonical. |
| 2. Define observable features | Supply only typed, bounded or enumerated, policy-safe values. Missing required values stay missing. | `AttentionFeatureSchemaSnapshot` and `AttentionFeatureDefinition` validate feature type, bounds/enums, classification, and missingness. |
| 3. Govern source information | Bind source and derived information to immutable lineage and composed policies. Declare the opaque information-ID payload fields in the source policy and allow source telemetry before provider invocation. | Information Governance lineage, policy binding, material access admission, `AttentionSourcePolicySnapshot.information_id_payload_fields`, and `AttentionTelemetryContext`. |
| 4. Record the actual choice | Implement `AttentionDispositionProvider.decide(opportunity)` as an adapter around the Companion's real decision point. Consume only the prepared schema-approved safe view; return one of `WAKE`, `REMEMBER`, `DEFER`, or `SUPPRESS`, plus matching feature/lineage/cut and decision provenance. | `AttentionOpportunity`, `AttentionDispositionDecision`, `DeliberativeAttentionRecorder`, and `DeliberativeAttentionWorker`. |
| 5. Recover safely | Use a stable logical consumer ID and stable opportunity event ID across retries. Do not call the provider again when the semantic disposition is already canonical. | Content-addressed dispositions, exact-head admission, semantic conflict detection, and `ConsumerCheckpoint`. |
| 6. Link outcomes | Emit the actual later outcome as its own canonical event, then link it causally. Use `UNKNOWN` when observation cannot resolve the outcome. | `DeliberativeAttentionRecorder.link_outcome` and `AttentionOutcome`. |
| 7. Record feedback | Capture only an explicit authenticated statement, with actor and provenance. No response is not acceptance. | `DeliberativeAttentionRecorder.record_feedback` and `AttentionFeedback`. |
| 8. Audit the corpus | Freeze a policy/schema/sequence interval and inspect missing, incomplete, resolved, censored, and feedback-observed sets. | `AttentionExposureProjection.audit`; `denominator_complete` requires a nonempty denominator and no missing or duplicate disposition. |

The source event may refer to governed content but the attention records must not
copy protected text into payloads, identifiers, subjects, correlation fields,
metadata, traces, or errors. Opaque references and policy-safe features are the
integration boundary. The disposition provider receives neither the raw event
nor its source, subject, or payload.

## SDK versus Companion boundary

The SDK owns general, replayable safety primitives:

- canonical events, schema normalization, exact-head admission, checkpoints,
  projections, and embedded/distributed adapters;
- information policy, lineage, access/disclosure decisions, and independent
  `TELEMETRY`, `EVALUATE`, and `LEARN` operations;
- attention feature/source-policy contracts, disposition/outcome/feedback
  records, denominator auditing, and an observation-only authority ceiling;
- provider-neutral tracing and immutable provider/configuration references.

The Companion owns product and deployment choices:

- provider credentials and secret rotation;
- prompts, few-shot material, model parameters, and provider selection;
- personal datasets, local protected-content stores, and product retention
  choices;
- opportunity extraction, product-specific feature computation, and the actual
  disposition mechanism;
- user interface, voice, notification surfaces, and interaction design;
- connector selection, authentication, rate limits, and external schemas;
- product schedules, quiet hours, thresholds, budgets, rollout cohorts, and
  experimental hypotheses.

Application-owned choices may be referenced by immutable IDs or digests in SDK
events. Their content and business vocabulary do not become SDK concepts.

## P0 product behavior

P0 may support these bounded application behaviors:

- recognize a situation that is eligible for an attention decision;
- decide to wake, remember, defer, or suppress under current intent and policy;
- explain the decision using typed observable provenance without exposing hidden
  reasoning transcripts;
- observe whether the opportunity was handled, missed, or misclassified;
- accept explicit correction, override, exception, preference revision,
  rejection, or prohibition; and
- compare decision configurations only after the evaluation prerequisites are
  satisfied.

P0 must preserve:

```text
challenge authority != decision authority
past behavior != current intent
personalization != terminal values
developmental advice != user-goal mutation
always-on != continuous model invocation
observation != truth
capability != permission != authority
```

## Current blockers

The following are not proven by the pinned Companion baseline or current SDK:

1. The Companion has not yet demonstrated this real integration seam on its
   application decision path.
2. No qualifying real denominator-complete attention corpus exists. Synthetic
   fixtures prove mechanics only.
3. `ExperimentFingerprintV1`, canonical evaluation runs, drift detection, and
   baseline promotion are staged rather than implemented.
4. Continuous-pilot budgets, backlog thresholds, event/byte growth envelopes,
   and product-specific latency objectives have not been pinned.
5. Poison-message quarantine/dead-letter handling, physical retention
   enforcement, transport-security enforcement, and a long soak are missing.
6. Production protected-byte storage, key management, secret rotation, and
   complete observability/content interception remain application/deployment
   obligations or future SDK work.
7. Developmental-intervention semantics and habit learning are outside P0. No
   data from P0 may be learned from unless policy separately permits `LEARN`.

These blockers require a bounded pilot. They do not invalidate the deterministic
telemetry substrate.

## Exit criteria

P0 exits only when:

- exact SDK and Companion commits are recorded;
- one source-policy/feature-schema pair is canonical before the evaluated
  opportunities;
- eligibility is demonstrably label-blind and every recognized opportunity has
  exactly one actual disposition;
- missing features remain incomplete, unknown outcomes remain censored, and
  absent feedback remains absent;
- crash and concurrent-writer recovery preserve one semantic disposition;
- protected values are absent from events, traces, logs, and errors;
- `EVALUATE` is admitted for the frozen corpus while `LEARN` remains independently
  controlled;
- the application-local budgets and the acceptance evidence in `docs/NFRS.md`
  are satisfied; and
- no learned or generated policy is activated.

At exit, P0 proves an evaluation-grade observation corpus. It does not prove
developmental benefit, durable habit quality, or authority to act for the user.
