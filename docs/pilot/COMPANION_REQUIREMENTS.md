# Companion pilot requirements

This document is normative for the first Companion attention-telemetry pilot.
“Must” and “shall” indicate acceptance requirements. The requirements preserve a
general SDK boundary: product behavior stays in the Companion; durable safety
and evidence contracts stay in Noema.

## Baseline and manifest

**CP-BASE-01.** The pilot manifest shall record the exact SDK and Companion Git
commits, not only branch names or package versions.

**CP-BASE-02.** The SDK commit shall descend from
`42fd3c4ea656eff0dce011b36452a131c802fd9a`, whose accepted architecture base is
`52c1695cfce1de4680b7343fe3fc0c8a03b4c7d5`.

**CP-BASE-03.** The audited Companion C0 baseline is
`671ef7ed6b468226a6c6c1f21d74e7207e6cece1`. A later pilot commit shall name that
commit as its base and document every intervening change. C0 is deterministic
baseline evidence, not evidence that the P0 integration is complete.

## Product and authority boundary

**CP-PROD-01.** The Companion may implement sentinel, chief-of-staff,
thought-partner, mentor, coach, and epistemic-steward functions. It shall not
encode those functions as SDK personas or use them as authority grants.

**CP-PROD-02.** An attention disposition controls internal attention only. It
shall not create an action intent, work order, goal revision, commitment,
capability grant, or external effect.

**CP-PROD-03.** The application shall preserve current user intent and shall not
infer terminal values from repeated behavior, attention outcomes, or feedback.

**CP-PROD-04.** P0 shall not mine, generate, register, canary, shadow, or activate
learned policy. The pilot is observation and evaluation only.

## Opportunity and feature capture

**CP-ATT-01.** The Companion shall define one versioned, label-blind eligibility
policy for the first cohort. Source selection may inspect event type, source,
subject prefix, and required field presence; it shall not inspect actual
disposition, outcome, feedback, or later user behavior.

**CP-ATT-02.** The application shall record an `AttentionSourcePolicySnapshot`
and matching `AttentionFeatureSchemaSnapshot` before any evaluated source event.
Events that precede canonical policy activation shall not enter the cohort.

**CP-ATT-03.** Every feature shall be a policy-safe boolean, bounded number,
bounded integer, or explicitly enumerated string. Required and optional
missingness shall be declared. Raw content, free text, credentials, personal
identifiers, and hidden reasoning transcripts shall not be features.

**CP-ATT-04.** Missing required features shall remain feature-incomplete. The
Companion shall not fill them with zero, false, an empty string, a population
mean, or a model guess.

**CP-ATT-05.** Opportunity event IDs shall be stable across retries and derived
without embedding protected or low-entropy personal content. Product-specific
source extraction and feature computation remain application-local.

**CP-ATT-06.** The source policy shall declare every payload field containing an
opaque governed-information ID. Before invoking the disposition provider, the
worker shall resolve those canonical lineages and record allowed source
`TELEMETRY` access. Missing, denied, or undeclared lineage shall fail before the
provider call.

## Actual disposition

**CP-DSP-01.** The application shall adapt its real attention decision point to
`AttentionDispositionProvider`. The provider shall return the actual disposition
that controlled behavior: `WAKE`, `REMEMBER`, `DEFER`, or `SUPPRESS`.

The provider input shall contain only opaque canonical source references,
schema-approved typed features, declared governed-information IDs, prior source
access references, and the admitted causal cut. It shall not contain the raw
event, source, subject, payload, or protected content.

**CP-DSP-02.** A disposition shall never be inferred from whether a surface was
displayed, whether the user responded, whether later work occurred, or whether
the application remained silent. Delivery failure is later evidence; it does
not relabel the original decision.

**CP-DSP-03.** Each decision shall cite mechanism ID/version, immutable
configuration reference, causal situation cursor, governing-intent references,
governed-information references, temporal coordinates, and observable costs.
Unknown costs shall remain `null`, not zero.

**CP-DSP-04.** The application shall use the
`INTERNAL_ATTENTION_ONLY` authority ceiling. A product adapter shall reject any
attempt to treat a disposition record as effect authorization.

**CP-DSP-05.** For one source event, source policy, and feature schema, exactly
one semantic disposition shall become canonical. Equal concurrent writers shall
converge; conflicting writers shall fail closed and become operationally
visible.

**CP-DSP-06.** Disposition admission shall require returned features,
governed-information IDs, and causal cut to match the prepared opportunity
exactly. Replay shall verify that source-access receipts cover every declared
source ID and that separate derived-artifact receipts cover the disposition
artifact.

## Outcome and feedback

**CP-OUT-01.** A later outcome shall first exist as a canonical source event and
shall causally and temporally follow the disposition before
`link_outcome` is called.

**CP-OUT-02.** The Companion shall use the smallest supported outcome vocabulary.
When the observation window cannot resolve the result, it shall use `UNKNOWN`.
Unknown or absent outcomes are censored and shall not be counted as negative.

**CP-OUT-03.** One disposition has at most one immutable outcome link. A changed
interpretation shall be new evidence under a future contract, not mutation of
the existing link.

**CP-FBK-01.** Feedback shall be recorded only from an explicit authenticated
statement and shall include actor and provenance. Absence of interaction is not
acceptance, rejection, or preference.

**CP-FBK-02.** Correction, temporary override, contextual exception, preference
revision, explicit rejection, and permanent prohibition shall remain distinct.
A temporary event shall not silently become a durable preference.

## Information governance and personal data

**CP-IG-01.** Every source and derived information reference shall have canonical
lineage and immutable policy binding. Missing governance evidence shall fail
closed.

**CP-IG-02.** Attention recording requires allowed `TELEMETRY`. Evaluation
requires allowed `EVALUATE`. Any fitting, adaptation, example selection, mining,
or policy compilation requires allowed `LEARN`. These permissions are
independent and do not imply disclosure or action authority.

**CP-IG-03.** The evaluated corpus shall be frozen by policy/schema IDs and an
inclusive canonical sequence interval. Access shall be re-evaluated against the
exact current governing state when the corpus is consumed.

**CP-IG-04.** Protected source content shall remain in application-owned governed
storage. Attention events may contain opaque references and approved features,
but shall not copy source text into payloads, envelopes, metadata, traces,
exceptions, snapshots, or evaluation exports.

**CP-IG-05.** Cross-trust-domain model context, telemetry export, or evaluation
export shall require both access and disclosure. A local permission shall not be
treated as permission to export.

**CP-IG-06.** Provider credentials, secret rotation, prompts, few-shot sets,
personal datasets, protected-content storage, and product retention choices are
Companion/deployment responsibilities. Only immutable opaque references or
digests cross into SDK records.

## Recovery and continuous operation

**CP-OPS-01.** The application shall use a stable logical attention consumer ID.
A checkpoint may advance only after the required disposition for a recognized
source is durable.

**CP-OPS-02.** A crash before disposition shall retry the source. A crash after
disposition but before checkpoint shall reuse the disposition without another
provider call. Process restart shall rebuild from canonical history rather than
an application-private watermark.

**CP-OPS-03.** The application shall pin finite per-cycle, daily provider,
compute/cost, human-attention, backlog-warning, and backlog-stop limits. Their
numeric values remain application-local and shall be included in the pilot
manifest.

**CP-OPS-04.** When a cognitive or backlog limit is reached, nonessential
processing shall defer without invoking a model. “Always on” means continuously
recoverable observation, not continuous generation.

**CP-OPS-05.** Continuous collection shall remain bounded until poison-event
quarantine, physical retention enforcement, secure transport enforcement, and
the soak criteria in `docs/NFRS.md` pass. A repeated deterministic failure shall
not be hidden by checkpoint advancement.

## Evaluation and observability

**CP-EVAL-01.** Every report shall include recognized, disposition-complete,
feature-complete, outcome-resolved, outcome-censored, and feedback-observed
counts before derived rates.

**CP-EVAL-02.** Outcomes shall be stratified by actual disposition. Censored
records remain in exposure counts and are excluded from resolved-outcome quality
rates. Undefined rates shall not be reported as zero.

**CP-EVAL-03.** Comparative claims shall wait for the staged
`ExperimentFingerprintV1` runtime. An interim application manifest may record
the proposed dimensions, but it is not a canonical fingerprint and does not
make a run reproducible by assertion.

**CP-EVAL-04.** A later fingerprint shall pin SDK/application commits, model
provider and ID, model parameters, reasoning settings, prompt bundle, few-shot
set, tool schema, retrieval policy, embedding model, index snapshot, metadata
filters, information-policy snapshots, attention feature/source policies, and
ruleset digest.

**CP-OBS-01.** The Companion may export provider-neutral OpenTelemetry data. It
shall use a versioned scalar-attribute allowlist and redactor. Protected content
export is opt-in under `TELEMETRY` and disclosure policy; it is never a debugging
default.

**CP-OBS-02.** The pilot shall scan events, logs, traces, metrics, and error paths
with protected sentinel values and demonstrate zero leakage before real personal
content is enabled.

## Application-local requirements

The following shall remain application-local rather than being added to Noema's
core vocabulary or defaults:

| Concern | Required application artifact |
|---|---|
| Provider credentials | Secret-store reference and rotation procedure; never a fingerprint field. |
| Prompts and examples | Versioned bundle/set in governed storage plus content digest. |
| Personal datasets | Governed lineage, policy, retention, and corpus-cut reference. |
| Product surfaces | Interaction specification and accessibility tests. |
| Voice and tone | Product policy and prompt/configuration reference. |
| Connectors | Adapter contract, credentials, source schemas, rate limits, and failure handling. |
| Thresholds and schedules | Versioned product configuration containing budgets, quiet periods, backlog limits, and rollout cohort. |
| Experimental hypotheses | Evaluation plan naming baseline, candidate, metrics, minimum evidence, and stopping rule. |

The SDK may provide general protocols and durable references for these concerns.
It shall not absorb their product-specific values.

## Acceptance checklist

The P0 integration is acceptable only if all of the following are evidenced:

- [ ] exact build commits and all application-local configurations are pinned;
- [ ] source eligibility is label-blind and activated canonically;
- [ ] every recognized opportunity has exactly one actual disposition;
- [ ] incomplete features, censored outcomes, and absent feedback remain distinct;
- [ ] outcome and feedback evidence is causal, explicit, immutable, and governed;
- [ ] crash, restart, equal-writer, conflict, and PostgreSQL-gap scenarios pass;
- [ ] embedded and distributed semantic projections match for the same fixture;
- [ ] cognition, checkpoint lag, event growth, and storage remain within the
      manifest's finite limits;
- [ ] poison-event, retention, transport-security, soak, and redaction gates in
      `docs/NFRS.md` pass or the pilot is explicitly constrained around the
      unresolved blocker;
- [ ] evaluation access is allowed without assuming learning permission; and
- [ ] no observation record mutates intent, creates agency, or activates learned
      behavior.

Passing this checklist establishes a trustworthy observation corpus. It does
not establish that the Companion improved the user, that a learned policy is
safe, or that the system may choose the user's values.
