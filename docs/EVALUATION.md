# Provider-neutral evaluation

Noema evaluation must answer a narrow question: did one pinned configuration
produce better decisions over the same governed opportunity population? It must
not turn observation into truth, censored evidence into failure, or evaluation
permission into learning permission.

This document separates current runtime support from the next evaluation
contract. `ExperimentFingerprintV1`, evaluation-run events, and an evaluation
runner are **staged specifications**; they are not implemented SDK classes or
canonical event types today.

## Current substrate

The SDK currently provides:

- a provider-neutral `Tracer` protocol, a `NullTracer`, and an optional
  `OpenTelemetryTracer`/OTLP adapter;
- canonical attention source-policy and feature-schema snapshots;
- actual `WAKE`, `REMEMBER`, `DEFER`, and `SUPPRESS` disposition records with
  mechanism, version, configuration, evidence, intent, temporal, information,
  and observable-cost references;
- immutable later outcome links and explicit feedback records;
- a denominator audit that separates missing dispositions, incomplete features,
  resolved outcomes, censored outcomes, and observed feedback; and
- independent Information Governance operations for `EVALUATE`, `LEARN`, and
  `TELEMETRY`.

OpenTelemetry is an observability transport, not the canonical evaluation
record. A dashboard, trace backend, or exported file is always a projection of
canonical evidence and cannot authorize access, learning, or effects.

## Evaluation population and evidence semantics

The unit of exposure is a source event recognized by a source-policy snapshot
after that policy becomes canonical. Eligibility must be label-blind. Every
recognized opportunity in a declared canonical sequence interval belongs in the
denominator even when feature capture, disposition, outcome, or feedback is
missing.

The core evidence classes are:

| Evidence | Interpretation |
|---|---|
| Recognized opportunity | Denominator member. It says the policy recognized an opportunity, not that the opportunity was important. |
| Actual disposition | What the active decision mechanism selected. It is supplied explicitly, never inferred from later activity or silence. |
| Feature-complete disposition | All feature-schema fields marked required were observed. Missing values are not imputed. |
| Resolved positive outcome | `TIMELY_USER_DECISION` or `HANDLED_WITHIN_WINDOW`. |
| Resolved negative outcome | `MISSED_OPPORTUNITY`, `FALSE_WAKE`, or `FALSE_SUPPRESSION`. |
| Censored outcome | No outcome link or `UNKNOWN`; it is excluded from quality-rate denominators but retained in exposure and censoring reports. |
| Explicit feedback | A separately authenticated statement such as accepted, corrected, overridden, contextually exceptional, revised, rejected, or prohibited. Absence is no opinion. |

Outcome observation and explicit feedback answer different questions. A timely
result is not proof that the user endorsed the intervention; acceptance is not
proof that the result was good.

## `ExperimentFingerprintV1` — staged contract

Every reproducible run must pin all dimensions that can change behavior. The
proposed immutable value is content-addressed as:

```text
experiment-fingerprint:v1:<sha256(canonical-json-without-id)>
```

Canonical JSON uses UTF-8, sorted object keys, sorted set-like reference lists,
no insignificant whitespace, finite numeric values, and explicit `null` for an
observed unknown. Secret material and raw protected content are never inputs to
the identifier.

The proposed dimensions are:

| Group | Required dimensions |
|---|---|
| Build | exact SDK commit; exact application commit; fingerprint schema version |
| Model | logical provider ID; model ID and provider revision when exposed; canonical model parameters; reasoning settings |
| Prompting | prompt-bundle digest; few-shot-set digest |
| Tools | tool-schema digest; application tool-policy digest |
| Retrieval | retrieval-policy digest; embedding provider/model/version and dimensions; index snapshot ID; canonical metadata-filter digest |
| Governance | information-policy snapshot IDs; attention source-policy ID; feature-schema ID; access-purpose version |
| Control | active ruleset digest; decision mechanism ID/version/configuration reference |
| Corpus | governed corpus reference; inclusive canonical start/end sequence; event-schema registry digest; outcome observation cutoff |

An illustrative proposed representation is:

```json
{
  "schema": "ExperimentFingerprintV1",
  "sdk_sha": "<40-hex>",
  "application_sha": "<40-hex>",
  "model": {
    "provider_id": "<logical-id>",
    "model_id": "<model-id>",
    "provider_revision": null,
    "parameters": {},
    "reasoning_settings": {}
  },
  "prompt_bundle_digest": "sha256:<digest>",
  "few_shot_set_digest": "sha256:<digest>",
  "tool_schema_digest": "sha256:<digest>",
  "tool_policy_digest": "sha256:<digest>",
  "retrieval": {
    "policy_digest": "sha256:<digest>",
    "embedding_model": "<provider/model/version/dimensions>",
    "index_snapshot_id": "<immutable-id>",
    "metadata_filter_digest": "sha256:<digest>"
  },
  "governance": {
    "information_policy_ids": ["<opaque-id>"],
    "attention_source_policy_id": "<content-id>",
    "feature_schema_id": "<content-id>",
    "access_purpose_version": "<version>"
  },
  "control": {
    "ruleset_digest": "sha256:<digest>",
    "decision_mechanism_id": "<id>",
    "decision_mechanism_version": "<version>",
    "decision_configuration_ref": "<immutable-ref>"
  },
  "corpus": {
    "governed_ref": "<opaque-id>",
    "start_sequence": 1,
    "end_sequence": 1,
    "schema_registry_digest": "sha256:<digest>",
    "outcome_observation_cutoff": "<rfc3339>"
  }
}
```

The actual prompt bundle, few-shot examples, retrieval corpus, and personal data
remain in application-owned governed storage. Their digests prove configuration
identity without exporting their contents.

## Governance protocol

An evaluation run should eventually follow this admission sequence:

1. Resolve the exact governed corpus lineage and composed policies at a pinned
   canonical head.
2. Require every source policy to allow `EVALUATE` for the actor, purpose,
   locality, provider, trust domain, and time in use.
3. Record material access decisions before consuming protected corpus data.
4. Freeze one fingerprint, source-policy/schema pair, sequence interval, and
   outcome observation cutoff.
5. Compute evaluation results without modifying the source corpus.
6. Export only safe aggregates through a separately allowed `TELEMETRY` use and,
   when a trust boundary is crossed, an allowed disclosure decision.

`LEARN` is a separate secondary use. A corpus allowed for evaluation cannot be
used for fitting, fine-tuning, habit mining, embedding training, prompt-example
selection, or other adaptation unless every composed policy also allows
`LEARN`. Conversely, `LEARN` does not imply permission to publish comparative
results. Neither operation grants action or decision authority.

Legacy policies allow neither secondary use. A repeated historical use does not
create consent.

## Comparability and drift

Every report must name a baseline fingerprint and candidate fingerprint.

- Equal fingerprints over equal corpus cuts are repeatability trials.
- A comparison intended to estimate one factor should change exactly that
  declared factor. Other changes invalidate single-factor attribution.
- A changed source policy, feature schema, ruleset, outcome cutoff, index
  snapshot, retrieval filter, or event-schema digest creates a new experimental
  cell; results must not be silently pooled.
- Provider aliases are insufficient. If the provider changes behavior without
  exposing a revision, the run records the observed date and is treated as
  potentially drifted.
- Baseline promotion requires a new immutable decision record in a future
  evaluation runtime; editing a dashboard label is not promotion.

The current SDK records many of these provenance dimensions on individual
attention decisions, but it does not yet assemble or admit a complete
fingerprint. Until that runtime exists, pilot results may be exploratory but
must not be described as reproducible configuration comparisons.

## Metrics

Report counts before rates. At minimum:

```text
denominator_coverage = dispositions / recognized_opportunities
feature_completeness = complete_feature_snapshots / dispositions
outcome_resolution = resolved_outcomes / dispositions
censoring_rate = censored_outcomes / dispositions
feedback_coverage = dispositions_with_feedback / dispositions
```

Outcome rates use only resolved evidence and are stratified by actual
disposition. In particular:

```text
false_wake_rate = FALSE_WAKE / resolved_WAKE_outcomes
false_suppression_rate = FALSE_SUPPRESSION / resolved_SUPPRESS_outcomes
handled_rate = (TIMELY_USER_DECISION + HANDLED_WITHIN_WINDOW) / resolved_outcomes
```

If a denominator is zero, the rate is undefined rather than zero. Reports also
show model calls, input/output tokens, wall time, human-attention units, and
deliberative-compute units by their metric version. Unknown cost values remain
unknown.

Small samples, high censoring, or selection changes must be shown explicitly.
They are not repaired with implicit labels or favorable imputation.

## OpenTelemetry contract

Core code depends only on the provider-neutral tracer protocol. A deployment may
export through OTLP to any compatible backend, retain traces locally, or use the
null tracer. No observability vendor is part of canonical semantics.

Default exported attributes should be allowlisted to:

- opaque run and fingerprint IDs;
- SDK/application commit IDs;
- event type and schema version;
- source-policy and feature-schema IDs;
- disposition and evidence-class enums;
- aggregate counts, finite costs, durations, retry counts, and checkpoint lag;
- deployment mode and non-secret component versions.

Default-denied attributes include source payloads, prompts, model responses,
retrieved text, tool arguments/results, personal identifiers, credentials,
connection strings, arbitrary exceptions, and governed information content.
Opaque governance IDs should remain local unless export is explicitly required;
linkability itself can be sensitive.

The scalar `TraceAttribute` type prevents complex payloads but is not a privacy
boundary. The application must apply a versioned allowlist/redactor before
export, and Information Governance must authorize `TELEMETRY` plus any required
disclosure. Protected-content export is opt-in, never a debugging default.

## Required implementation before accepted comparative evaluation

The following remain staged:

1. an immutable `ExperimentFingerprintV1` model and deterministic canonicalizer;
2. canonical experiment-registration and result contracts with exact-head
   admission;
3. governed corpus-cut materialization for `EVALUATE` without `LEARN` leakage;
4. a baseline/candidate evaluator that refuses incompatible fingerprints;
5. an OTel safe-attribute processor and redaction fitness test;
6. config-drift detection and provider-revision handling; and
7. embedded/distributed replay and fault tests for the evaluation path.

These contracts should be implemented without binding core semantics to a model,
trace, experiment-tracking, or storage vendor.
