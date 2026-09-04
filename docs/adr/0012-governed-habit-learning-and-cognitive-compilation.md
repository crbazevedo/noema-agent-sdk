# ADR 0012: Governed habit learning and cognitive compilation

- Status: Accepted architecture direction — HabitForge runtime blocked on a
  qualifying `deliberative_attention_v1` corpus
- Date: 2026-09-03
- Accepted: 2026-09-04
- Scope: habit evidence, deterministic mining, temporal validation, fitness,
  collision analysis, rule lifecycle, Information Governance, and the initial
  SHADOW-only compilation boundary

## Context

Noema can already evaluate immutable typed autonomic rules in a deterministic
shadow fabric, preserve bitemporal evidence, allocate bounded endogenous
cognition, discover dormant inquiries, and link later outcomes to cognitive
allocation traces. It cannot yet establish that a repeated deliberative
decision was correct, how often the same policy could have applied, or whether
silence was accepted rather than merely uncorrected.

Habit Learning asks a different question from cognition allocation:

```text
Endogenous Cognition:       what deserves thought now?
Historical Reconsideration: what may deserve thought again?
Dormant Discovery:          which history deserves revalidation?
Habit Learning:             what has earned the right not to require thought?
```

The downward and upward paths are complements:

```text
repeated, well-evidenced deliberation -> cheaper typed policy
novelty, contradiction, drift, correction -> abstain and restore cognition
```

This decision defines the eventual HabitForge boundary. Its acceptance does not
authorize a runtime implementation while the first real learning corpus lacks
a defensible exposure denominator and observed outcomes.

## Normative definition and identity boundaries

A habit is an evidence-backed, scoped, reversible compression of deliberative
policy whose demonstrated savings justify removing repeated cognition without
violating explicit limits on error, regret, privacy, externality, authority, or
user agency.

```text
Repetition != Habit
Behavior != Preference
Correlation != Intent
Frequency != Authority

Habit != Skill != Capability != Permission != EffectAuthority

HabitCandidate != AutonomicRuleVersion
AutonomicRuleVersion != HabitLifecycleState
HabitLifecycleState != RulesetMembership
RulesetMembership != EffectAuthority
```

Repeated behavior is evidence about a bounded decision policy. It is not
evidence that the user endorses a preference, has supplied intent, or has
granted authority. Historical Goal or Commitment provenance explains why an
episode occurred; it cannot grant current authority to a compiled rule.

## Implementation-readiness synthesis

### Current substrate map

| Contract or component | Implemented | Canonical | HabitForge sufficiency | Gap or intended reuse |
|---|---:|---:|---|---|
| `Event`, `EventStore`, deterministic schema upcasting | yes | yes | sufficient substrate | Reuse; new events need validators and adjacent-version upcasters. |
| expected-head conditional append | yes | yes | sufficient substrate | Reuse actual predecessor-head semantics; never assume contiguous sequences. |
| `ConsumerCheckpoint` and projection | yes | checkpoint events | sufficient substrate | Reuse after every required forge suffix is durable. |
| `SemanticAssertion`, `EvidenceLink`, memory projection | yes | yes | supporting evidence only | Reuse epistemic provenance; do not make memory a habit label store. |
| Information policies, lineage, bindings, access decisions | yes | yes | sufficient governance substrate | Distinct `LEARN` and `EVALUATE` operations and intersected secondary-use policy are implemented; legacy policies grant neither. |
| `InformationGovernanceProjection` | yes | projection | sufficient governance substrate | Reused by attention telemetry; it remains the policy view, not a training store. |
| `deliberative_attention_v1` contracts and exposure projection | yes | yes / projection | mechanics ready; real corpus absent | Records source policy, feature schema, actual disposition, later outcomes and explicit feedback; provider input is restricted to schema-approved features after source access admission, and denominator audit fails closed. |
| `AutonomicRule`, `PredicateSpec`, `SignalTemplate` | yes | registration event | sufficient first target IR | Reuse unchanged for the bounded predicate compiler; candidate governance does not become rule code. |
| `RuleRegistry` | yes | projection | sufficient inventory | Reuse unchanged; it must not own lifecycle. |
| `RulesetSnapshot` | yes | materialization event | sufficient artifact | Reuse `snapshot(refs=...)`; no direct mutation. |
| `RuleCell`, `RuleEvaluationTrace`, `SalienceResolver` | yes | traces/decisions | sufficient SHADOW evaluator | A failed required predicate is an abstention. The trace is counterfactual evidence, not an actual user outcome. |
| `AutonomicShadowWorker` | yes | worker outputs | incomplete selection policy | Later modify only ruleset-ref selection so DRAFT rules do not enter an epoch. |
| `decision.proposed` plus action lifecycle | yes | yes | insufficient corpus | Lacks typed context snapshot, complete exposure denominator, governing intent and information lineage, and correction semantics. Technical action success is not decision correctness. |
| autonomic evaluation and salience events | yes | yes | insufficient corpus | They are hypothetical policy outputs, not observed deliberative choices or outcomes. Mining them would be circular. |
| `CognitiveAllocationTrace` and outcome link | yes | yes | insufficient first corpus | Records whether thought was selected, with optional later links; it does not record an actual attention disposition or complete eligible exposures. |
| `ActionIntent`, policy, capability, and action outcomes | yes | yes | authority boundary only | Reuse as a prohibited downstream boundary. HabitForge never invokes it in the first slice. |
| `HabitEpisode` and exposure projection | no | projection only | required | Blocked on the telemetry precursor below. |
| evidence bundle, miner, candidate, reports, lifecycle | no | material artifacts will be canonical | required | Defined here; not authorized for implementation yet. |

### Readiness verdict

At proposal time, no existing canonical event family could supply the first
valid `HabitEpisode` corpus. The accepted precursor now supplies the required
observation mechanics, but the repository still contains no qualifying real
corpus.

- `decision.proposed` records trigger type, proposed intents, critic decisions,
  and cycle duration, but not the typed situation used by a candidate, a
  complete eligible-exposure denominator, current intent lineage, an authority
  ceiling for an attention disposition, Information Governance lineage, or
  user correction/acceptance.
- `action.succeeded` records technical capability completion. It neither proves
  that the deliberative choice was correct nor represents alternatives and
  exposures where no action was selected.
- `rule.evaluation_traced` and `rule.salience_decision_shadowed` are
  counterfactual outputs of already registered policy. They are useful for
  replay and collision evidence but cannot label the deliberation that a new
  habit proposes to replace.
- `CognitiveAllocationTrace` distinguishes cognitive selection labels and can
  cite later outcomes, but it measures allocation of thought rather than the
  resulting attention decision. Outcome linkage is optional and the trace
  family does not establish all eligible attention exposures.

Absence of correction therefore cannot be interpreted as success, and the
repository cannot currently distinguish a successful-looking positive-only
sample from a complete learning corpus. Runtime HabitForge is a **NO-GO** until
the implemented prerequisite has produced a qualifying real corpus.

## Implemented telemetry precursor

The first source family is deliberately narrow:

```text
deliberative attention disposition v1
```

It covers only an attention opportunity whose sanctioned feature schema names
the policy-safe context available to the actual decision and whose baseline
choice is `WAKE`, `REMEMBER`, `DEFER`, or `SUPPRESS`. The first Companion
acceptance profile declares `deep_work`, `requires_user_decision`, and `urgency`
as schema data; those fields are not branches in generic SDK logic. This is not
a generic “learn from all history” envelope.

The prerequisite implements three canonical observation contracts plus
content-addressed source-policy and feature-schema records:

1. `attention.disposition_recorded` records exactly one baseline decision for
   every recognized attention opportunity, including its trigger reference,
   causal situation cursor, label-blind source-eligibility policy ID/version,
   feature-schema identity and policy-safe typed feature snapshot,
   decision/proposal refs, governing-intent refs, authority ceiling,
   cognitive/latency/human-attention costs, valid and known time, governed-
   information refs, and separate source-use and derived-artifact access refs.
2. `attention.disposition_outcome_linked` links a causally later observed
   outcome without rewriting the decision. Typed outcomes include at least
   timely user decision, item handled within its declared window, missed
   opportunity, false wake, false suppression, and unknown.
3. `attention.disposition_feedback_recorded` preserves explicit acceptance,
   correction, temporary override, contextual exception, preference revision,
   explicit rejection, and permanent prohibition as distinct values.

Every recognized decision point must produce a disposition record, including a
choice to remain quiet. The source worker checkpoints only after that record is
durable. A denominator audit compares recognized canonical triggers with
disposition records and invalidates any cut with missing or duplicate
opportunities. Outcome and feedback links must follow the disposition in
canonical order and use their actual causal references.

The source-eligibility policy is versioned, deterministic, and fixed before it
observes a disposition or outcome. It selects triggers only from typed source
fields and the declared situation cut. A policy that chooses examples by their
later label cannot define a denominator.

The immutable source policy also declares which payload fields contain opaque
governed-information IDs. Before the application disposition provider is
called, the worker resolves those canonical lineages and records allowed source
`TELEMETRY` decisions. The provider sees only opaque source references,
schema-approved scalar features, governance references, and the admitted causal
cut—not the raw event, source, subject, or payload. Admission requires the
returned feature snapshot, information lineage, and causal cut to match that
prepared view exactly; replay separately verifies complete source-access and
derived-artifact access coverage.

Telemetry mechanics are complete. HabitForge data readiness is not: the
training and temporal-validation cuts must still contain policy-permitted,
feature-complete real exposures, observed positives, counterexamples, and
non-censored outcome or explicit acceptance evidence. Synthetic fixtures prove
correctness and recovery; they do not establish a production habit.

## Episode, exposure, and label semantics

`HabitEpisode` is a rebuildable projection over that source family, ordinary
memory evidence, and current governance state. There is no
`habit.episode_recorded` event. An episode contains:

```text
episode_id, source_kind
trigger_refs, decision/proposal_refs, outcome_refs, feedback_refs
start_cursor, end_cursor
source_eligibility_policy_ref, feature_schema_ref
policy-safe context feature snapshot
governing_intent_refs, authority_ceiling
cognitive_cost, latency, human_attention_cost
information_refs, policy/decision refs
valid_time, known_time
label and label provenance
```

For candidate `H`:

```text
EligibleExposures(H)
    = every feature-complete, scope-matching attention opportunity
      in the selected causal cut for which LEARN and EVALUATE are allowed

Positives(H)
    = eligible exposures with an observed matching baseline disposition
      and qualifying downstream outcome or explicit acceptance

Counterexamples(H)
    = eligible exposures on which H would disagree with an observed correct
      disposition, explicit correction/rejection, or qualifying negative outcome

Corrections(H)
    = the explicit-correction subset, retained with correction kind

UnknownOrCensored(H)
    = incomplete, unresolved, conflicting, or not-yet-observable outcomes
```

Candidate coverage separately reports how many source-family opportunities
were outside its applicable feature/scope contract. Missing required state is
an abstention, not a negative example and never receives the training-set mode.

Observed labels are canonical dispositions, explicit feedback, and causally
linked outcomes. A deterministic episode classifier may infer the derived
categories positive, counterexample, and censored only from versioned rules
over those observations. No correction, acceptance, preference, intent, or
outcome may be inferred from silence. Censored samples stay censored and do not
enter positive or negative numerators.

## Information Governance for learning

The implemented governance prerequisite extends `InformationOperation` with:

```text
LEARN     information may influence persistent future policy
EVALUATE  information may be used for replay, fitness, counterexample search,
          collision analysis, or offline habit evaluation
```

Both are internal information-access operations with ordinary purpose,
recipient, locality, provider, trust-domain, retention, and lineage checks.
Crossing a trust boundary additionally requires a `DisclosureDecision`.

`InformationPolicy` also gains an explicit `allowed_secondary_uses` dimension
whose only initial values are `LEARN` and `EVALUATE`. Composition intersects
that dimension, so either use can be granted without granting the other.
Historical policies and payloads that lack the dimension deterministically
upcast to an empty set: adding the new enum values cannot silently authorize
old information for secondary use. A matching purpose remains necessary but is
not sufficient without the matching secondary-use permission.

```text
REASON != LEARN
TELEMETRY != LEARN
EVALUATE != LEARN
LEARN != MODEL_TRAINING
LEARN != DISCLOSE
```

An episode may be operationally readable yet excluded from learning. Mining
requires an allowed `LEARN` decision for every source item. Holdout replay,
fitness, and collision analysis require separately allowed `EVALUATE`
decisions. Each decision pins an immutable `AccessContext`, policy versions,
lineage, purpose, principal, locality, and causal cursor. Revocation or policy
change prevents a new bundle or lifecycle advance; it does not rewrite an old
auditable bundle.

Evidence bundles, candidates, fitness reports, collision reports, and compiled
rules are derived information. They receive opaque information identities,
exact source lineage, composed policy bindings, and operation-specific
decisions. Raw protected content, identifiers, and low-entropy values never
enter ordinary feature names or rule literals. The first feature schema permits
only policy-safe booleans, approved categorical values, bounded numeric values,
and constants predeclared by policy.

## Immutable evidence and policy artifacts

### `HabitEvidenceBundle`

The content-addressed bundle pins:

```text
bundle_id, source_kind
extractor_id/version, episode_classifier_id/version
source_eligibility_policy_id/version, feature_schema_id/version
train_start_cursor, train_end_cursor
validation_start_cursor, validation_end_cursor
episode_digest
exposure refs/digest, positive refs/digest
counterexample refs/digest, correction refs/digest
censored refs/digest
governing_intent_refs
information_policy_versions
LEARN decision refs, EVALUATE decision refs
corpus_digest, created_at
```

`created_at` is the canonical timestamp at the validation cut, not worker wall
clock. Bundle identity is a digest of its normalized immutable content. The
same corpus, cuts, extractor/classifier, feature schema, governance decisions,
and policy reproduce the same identity. Cursor ranges are inclusive bounds over
rows that exist; gaps are legal.

### `HabitMiningPolicySnapshot`

The canonical policy snapshot pins:

- allowed source kind, feature names, value domains, operators, and literal
  constants;
- maximum clauses and maximum distinct features;
- minimum train and holdout exposures, positives, and counterexamples;
- maximum false-positive, correction, override, rejection, and regret rates;
- minimum outcome-quality and compression evidence;
- missingness and censoring ceilings;
- complexity ordering and stable tie-break;
- fitness policy, collision analyzer, compiler, and lifecycle policy versions;
- maximum authority, risk, privacy, and externality ceilings; and
- training and validation cuts.

It is a policy artifact, not a learned optimizer.

## Candidate and deterministic mining

`HabitCandidate` is immutable proposal data. It pins the bundle, miner and
compiler versions, purpose, scope, governing semantic refs, proposed rule
family/spec/signal, required context schema, authority ceiling, risk,
reversibility, externality, novelty escape, supporting and counterexample refs,
estimated deliberative savings, and Information Governance lineage.

It is not a registered rule. A rejected candidate remains canonical evidence.
Observed behavior cannot populate `intent_text`; only authenticated explicit
intent may do that. The first attention candidate has signal-only, SHADOW,
`OBSERVE` effect authority, negligible risk, no externality, and no capability
reference.

The first miner supports `RuleFamily.PREDICATE` only:

1. Verify the bundle, policy, current `LEARN`/`EVALUATE` decisions, and a valid
   exposure denominator.
2. Give candidate generation only the training slice. The validation slice is
   inaccessible through the miner interface.
3. Enumerate conjunctions of one through `max_clauses` from policy-approved
   feature/operator/literal triples. Data-derived protected literals are
   forbidden.
4. Evaluate each conjunction over every training exposure and retain full
   positive, counterexample, correction, and censored accounting.
5. Reject any conjunction that fails a hard support, error, correction, regret,
   missingness, privacy, authority, or complexity gate.
6. Order survivors by fewest clauses, then fewest distinct features, then
   canonical serialized clause bytes, then output bytes.
7. Select the first survivor. There is no hidden objective or random choice.
8. Evaluate that fixed candidate on the later validation slice. Holdout failure
   rejects it; the miner may not refine it using validation observations.

No model, embedding, reinforcement learning, bandit, program synthesis,
scoring optimization, workflow induction, state-machine synthesis, or graph
mining participates.

## Temporal validation

```text
training:   sequence <= train_cut
validation: train_cut < sequence <= validation_cut
drift:      validation_cut < sequence <= current_cut
```

The extractor observes only the requested cut. Candidate generation receives
training episode refs only. Validation runs after the candidate identity is
fixed, and a failed holdout cannot be used to mutate the same candidate. A
later attempt requires a new evidence bundle with explicit new cuts.

The same canonical corpus, cuts, extractor/classifier, feature schema, miner,
policy, and compiler reproduce byte-equivalent candidate semantics and reports.
Valid-time and known-time are both checked: evidence is usable only if it was
known by its cut and valid for the episode being evaluated.

## Fitness vector and SHADOW gates

`HabitFitnessReport` is an immutable vector, never one habit score. It records:

- eligible exposure, positive, counterexample, correction, and censored counts;
- support, coverage, missingness, and censoring;
- decision agreement, precision, false-positive rate, and identifiable
  false-negative evidence;
- correction, override, explicit-rejection, and permanent-prohibition rates;
- realized-utility, missed-opportunity, regret, and outcome-quality evidence;
- deliberative compute, latency, and human attention avoided;
- incremental rule-evaluation and privacy cost;
- collision rate, calibration, drift indicators, and time since useful evidence.

```text
CompressionGain
    = estimated deliberative cost avoided
      - compiled-policy evaluation cost

CompressionGain != UserValue
```

A candidate can reach SHADOW only if all gates pass:

```text
LearningPermitted
AND EvaluationPermitted
AND ExposureDenominatorValid
AND SupportSufficient
AND CounterexamplesWithinBound
AND TemporalHoldoutPasses
AND OutcomeQualityNonInferior
AND RegretWithinBound
AND UsefulCompressionDemonstrated
AND CollisionGatePasses
AND NoveltyEscapeExists
AND AuthorityDoesNotIncrease
AND PrivacyScopeValid
```

Positive compression never compensates for failure of another gate.

## Deterministic collision analysis

`HabitCollisionReport` pins candidate ID, exact ruleset ID/digest, ruleset
materialization cursor, rule refs, analyzer ID/version, and normalized collision
records. The initial taxonomy is:

```text
DUPLICATE
SUBSUMES_EXISTING
SUBSUMED_BY_EXISTING
OVERLAPPING_DIFFERENT_OUTPUT
PRECEDENCE_CONFLICT
INHIBITION_CONFLICT
PURPOSE_CONFLICT
AUTHORITY_CONFLICT
PRIVACY_SCOPE_CONFLICT
UNKNOWN_OVERLAP
```

The v1 analyzer proves relations only for bounded predicate conjunctions over
the same approved scalar feature schema and for trigger relations it can decide
exactly. It may compare equality and numeric intervals, exact signal outputs,
and explicit precedence/inhibition metadata. An unsupported operator, glob
intersection, temporal/scoring rule, missing legacy privacy/authority metadata,
or ambiguous purpose/scope relation yields `UNKNOWN_OVERLAP` whenever overlap
cannot be disproved.

`UNKNOWN_OVERLAP` fails the automatic SHADOW gate. The analyzer never invents a
precedence change, rewrites an existing rule, or treats evaluation order as a
conflict resolution mechanism.

## Compilation, registry compatibility, and lifecycle

The deterministic compiler maps a passing predicate candidate to the existing
`AutonomicRule`/`PredicateSpec`/`SignalTemplate` IR. All scope conditions become
required clauses. The compiled `rule_id` is deterministically namespaced from
the candidate identity, version starts at one, and `evidence_refs` cite the
bundle, candidate, fitness, and collision events. Compilation cannot add a
literal, operator, output, authority, or scope absent from the candidate.

`rule.version_registered` evolves to a v2 envelope with registration origin,
candidate reference where applicable, and compiler identity. The adjacent
upcaster classifies historical v1 registrations as legacy shadow-compatible.
The `AutonomicRule` value, `RuleRegistry`, and `RulesetSnapshot` contracts remain
unchanged.

Lifecycle is owned by canonical `rule.lifecycle_changed` events and a separate
`RuleLifecycleProjection`, never by `RuleRegistry`:

```text
HYPOTHESIS -> DRAFT -> SHADOW -> future CANARY -> future ACTIVE
                    \-> QUARANTINED
future ACTIVE <-> future THROTTLED
any nonterminal state -> SUPERSEDED or RETIRED
```

Candidate creation establishes `HYPOTHESIS`. Passing bundle, fitness, collision,
and governance gates permits an admitted transition to `DRAFT`. Compilation
registers an inert rule version. A separate transition binds that rule ref and
enters `SHADOW`. In the first runtime slice, `CANARY`, `ACTIVE`, and operational
`THROTTLED` transitions are rejected.

The shadow worker later constructs an explicit eligible-ref set and calls
`RuleRegistry.snapshot(through_sequence=..., refs=...)`. Historical v1 rules
remain eligible under derived `LEGACY_SHADOW_COMPAT` classification but cannot
enter CANARY or ACTIVE without a future explicit lifecycle admission. New v2
registrations without SHADOW lifecycle state are excluded. Consequently,
registration and “latest version” selection cannot activate a DRAFT
HabitForge rule.

SHADOW may be admitted automatically only under an explicitly authorized
lifecycle policy after every hard gate passes. Any future CANARY or ACTIVE
transition requires a separate implementation decision and explicit approval
appropriate to interruption, privacy, identity, relationship, externality, and
risk. No lifecycle transition grants effect authority or declassifies data.

## Authority, abstention, correction, and rollback

```text
compiled authority <= authorized source ceiling <= lifecycle ceiling
```

The first slice compiles signal-only SHADOW policy with no `ActionIntent` and no
capability. Future reflex policy could at most propose an `ActionIntent`, which
would still traverse intent, information, policy, authority, idempotency,
capability, dispatch, and outcome gates.

Every candidate has a `NoveltyEscapeContract`. It abstains when any required
feature is unknown, missing, stale, contradictory, outside the typed value
domain, outside scope or current intent applicability, privacy-incompatible,
under equal-or-higher precedence inhibition, explicitly corrected or
quarantined, or novel under its declared bounds. Unknown state is never imputed.
An abstention produces no compiled signal and leaves or makes cognition
valuable; in SHADOW it is durably visible through the evaluation trace.

The system preserves explicit correction, permanent prohibition, preference
revision, temporary override, contextual exception, negative outcome, and
concept drift as different evidence. A correction is strong counterevidence but
means permanent retirement only when its typed semantics say so. Meta-control
may propose `QUARANTINE`, `REVISE`, `THROTTLE`, or `RETIRE`; it cannot mutate
policy. In the first slice, a newly observed privacy/authority violation,
permanent prohibition, unexplained high-regret outcome, invalid denominator,
material holdout/drift failure, or newly detected collision requires fail-closed
quarantine. Revision creates a new evidence bundle and candidate; it never
edits the old rule.

## Canonical object and event map

| Object or event | Classification | Decision |
|---|---|---|
| `HabitEpisode` | projection only | Derived from the narrow attention family; no episode event. |
| `HabitEvidenceBundle` / `habit.evidence_bundle_recorded` | new canonical | Immutable content-addressed corpus identity. |
| `HabitMiningPolicySnapshot` / `habit.mining_policy_recorded` | new canonical | Pins bounded miner and all gates. |
| `HabitCandidate` / `habit.candidate_forged` | new canonical | Proposal data; never a registered rule or authority. |
| `HabitFitnessReport` / `habit.fitness_evaluated` | new canonical | Immutable vector and hard-gate results. |
| `HabitCollisionReport` / `habit.collision_analyzed` | new canonical | Pinned exact-ruleset analysis. |
| `HabitLifecycleState` | projection only | Current state derived from candidate and lifecycle events. |
| `HabitLifecycleTransition` / `rule.lifecycle_changed` | new canonical contract for documented event | State transition with evidence, authority receipt, actual predecessor head, and optional rule ref. |
| `RuleLifecycleProjection` | projection only | Separate lifecycle and ruleset-eligibility view. |
| `HabitEpisodeExtractor` | new projection service | Deterministic, versioned, cut-bounded. |
| `DeterministicHabitMiner` | new pure service | Predicate-only bounded enumeration. |
| `HabitReplayEvaluator` | new pure service | Train/holdout/drift vector calculation. |
| `HabitCollisionAnalyzer` | new pure service | Typed decidable relations; unknown fails closed. |
| `HabitForgeWorker` | new durable orchestrator | Adds required outputs then checkpoints; no execution boundary. |
| `rule.version_registered` | modified existing envelope | v2 origin/compiler/candidate provenance; rule value unchanged; v1 upcasts to legacy shadow. |
| `RuleRegistry`, `RulesetSnapshot` | reused projection/artifact | Inventory and immutable selected content remain unchanged. |
| `runtime.consumer_checkpoint_advanced` | reused canonical | Advances after a complete or durably terminal forge attempt. |
| `attention.disposition_*` family | implemented canonical prerequisite | Supplies the first actual episode and denominator; not part of HabitForge itself. |
| `InformationOperation`, `InformationPolicy`, and policy matrices | implemented extension | Independent `LEARN`/`EVALUATE` plus fail-closed `allowed_secondary_uses`; legacy policies permit neither. |
| CANARY, ACTIVE, live suppression/reflex | deferred | Explicitly outside the first implementation. |

## Replay and concurrency

Every material transition pins source cursors, extractor/classifier and feature
schema versions, train/validation cuts, mining/fitness policy, compiler,
candidate, ruleset digest, collision analyzer, governance decisions, and actual
predecessor head. State-dependent events append only through exact-head CAS.
Stored event sequence must be greater than its validated predecessor; it need
not equal predecessor plus one.

Content-derived IDs make concurrent identical forge attempts converge on one
effective bundle, candidate, report, registration, and transition. A different
bundle necessarily produces a different candidate. On a head race the worker
reloads canonical history, reruns all semantic checks, and either reuses the
same content or produces a new report against the new ruleset. It never appends
a stale lifecycle transition.

Crashes after bundle, candidate, fitness, collision, registration, or SHADOW
transition leave a valid prefix. Restart reconstructs the prefix, validates it,
and appends each missing suffix once before advancing `ConsumerCheckpoint`.
A crash after registration but before SHADOW leaves an inert registered rule.

## Exact first HabitForge vertical slice, once unblocked

```text
canonical deliberative-attention telemetry
    -> HabitEpisode projection and denominator audit
    -> content-addressed HabitEvidenceBundle
    -> deterministic bounded predicate miner
    -> immutable HabitCandidate
    -> temporal holdout HabitFitnessReport
    -> exact-ruleset HabitCollisionReport
    -> HYPOTHESIS -> DRAFT
    -> deterministic AutonomicRule registration
    -> DRAFT -> SHADOW
    -> explicit-ref shadow epoch and counterfactual traces
    -> ConsumerCheckpoint
```

The slice stops at SHADOW. It does not suppress a live wake, propose an action,
invoke a capability, change intent, admit work, or perform an external effect.

## Flagship acceptance scenario

The precursor produces a synthetic but canonical `deliberative_attention_v1`
history with complete source-trigger coverage and explicit outcome/feedback:

```text
deep_work = true
requires_user_decision = false
urgency < configured threshold
observed disposition = REMEMBER
observed result = handled within its window without missed opportunity

counterexamples:
requires_user_decision = true OR urgency >= configured threshold
observed disposition = WAKE
observed result = timely user decision, or an explicit correction of REMEMBER
```

The naive candidate:

```text
deep_work == true -> REMEMBER
```

must fail on its counterexamples. The least-complex passing candidate may be:

```text
deep_work == true
AND requires_user_decision == false
AND urgency < configured threshold
    -> REMEMBER
```

Acceptance proves that episodes derive from canonical history; every eligible
exposure is counted; positives are not the only evidence; candidate generation
cannot read holdout data; the naive candidate fails; the refined candidate and
reports replay byte-equivalently; protected raw values and generated code are
absent; candidate and rule identities differ; registration remains inert;
lifecycle reaches at most SHADOW; collision analysis pins the exact ruleset;
missing, stale, contradictory, novel, or out-of-domain context abstains; and no
Goal, Commitment, WorkOrder, ActionIntent, capability invocation, live wake
suppression, or effect occurs.

## Adversarial test matrix and fitness functions

| Attack or failure | Required proof |
|---|---|
| Positive-only corpus | Bundle admission rejects missing denominator, counterexample search, or qualifying outcomes. |
| Silent no-feedback labeling | Absence of correction remains censored, never success. |
| Missing source telemetry | Trigger-to-disposition denominator audit fails the cut. |
| Future-data leakage | Miner cannot access validation refs; holdout failure rejects rather than refines the candidate. |
| Protected literal leakage | Schema/envelope tests reject raw or low-entropy protected values in bundles, candidates, reports, rules, logs, and exceptions. |
| Operational permission reused | `REASON` or `TELEMETRY` without `LEARN`/`EVALUATE` fails closed. |
| Authority laundering | Compiler and lifecycle reject a ceiling above source or policy; no capability/effect imports exist. |
| Missing/unknown feature | Predicate does not activate; evaluation records abstention and never imputes a value. |
| Counterexample overgeneralization | The naive deep-work rule fails false-positive/correction gates. |
| Ruleset race | Collision report or lifecycle CAS loses, reloads, and reanalyzes the new exact ruleset. |
| PostgreSQL sequence gap | Bundle cuts, admission receipts, replay, and lifecycle accept actual predecessor heads with noncontiguous stored sequences. |
| Duplicate concurrent forge | Content IDs plus CAS yield one effective candidate and one SHADOW transition. |
| Crash at each stage | Canonical prefix is reused and the missing suffix is written once before checkpoint. |
| DRAFT registration | Explicit-ref ruleset excludes it; no trace exists until SHADOW and epoch rotation. |
| Legacy registration | v1 upcast remains shadow-compatible but cannot CANARY/ACTIVE. |
| Correction or drift | Typed evidence proposes or forces fail-closed quarantine; old candidate/rule remain immutable. |
| Collision ambiguity | `UNKNOWN_OVERLAP` blocks SHADOW. |
| Meta-rule self-promotion | Structural tests reject direct lifecycle/ruleset mutation and online self-modification. |
| Model dependency | The deterministic v1 miner runs with no `ModelProvider`. |

Architecture tests must reject `eval`, `exec`, generated Python, dynamic learned
imports, effect adapters, capability invocation, `ActionIntent`, `WorkOrder`,
Goal or Commitment mutation, InformationPolicy mutation, direct ruleset
mutation, silent lifecycle changes, automatic authority elevation, and online
self-modification in the HabitForge core and worker.

## Quality-attribute scenarios

| Attribute | Scenario and required response |
|---|---|
| Safety | A repeated low-cost choice correlates with an effect. The compiler can still emit only an effect-free SHADOW signal and cannot acquire effect authority. |
| Privacy | Employer-derived episodes permit reasoning but not learning. `LEARN` denies the bundle even when `REASON` allows the source. |
| Auditability | Given a SHADOW rule, replay resolves its exact episodes, labels, bundle, policy decisions, candidate, reports, lifecycle approvals, and ruleset. |
| Determinism | Two workers process the same cuts and policy. They derive the same content IDs and one effective canonical lineage. |
| Recoverability | Kill the worker after any forge stage. Restart completes the suffix once and never activates an inert registration. |
| Performance | A large canonical history contains few target episodes. A source-family index may accelerate projection, but the cut-bounded event log remains truth and mining is policy-bounded. |
| Modifiability | A later miner or feature schema is added. It receives a new version and cannot reinterpret an old bundle or candidate. |
| Local-first | Extraction, mining, replay, collision, and SHADOW evaluation require no provider or network service. |

## Consequences, risks, and sensitivity points

- A telemetry precursor delays HabitForge, but prevents positive-only behavior
  from being mistaken for learned legitimacy.
- Recording every eligible attention disposition increases canonical volume.
  The source is deliberately narrow, payloads are typed and governed, and
  projections/indexes may be bounded accelerators.
- Explicit `LEARN` and `EVALUATE` reduce the available corpus. That reduction is
  the intended consequence of purpose limitation.
- Predicate-only mining produces false negatives and small habits. This is
  preferable to uninspectable generalization before outcomes are trustworthy.
- Exact collision analysis will often return unknown against legacy or richer
  rules. Conservative abstention is accepted until typed metadata or a proven
  analyzer expands the decidable fragment.
- Thresholds for support, censoring, regret, and drift are safety-sensitive.
  They remain versioned policy, not constants hidden in code.
- SHADOW rules consume evaluation resources without saving live cognition.
  Their purpose is to measure disagreement and validate the compression claim
  before any future activation decision.

## Rejected alternatives

- **Mine current `decision.proposed` history:** incomplete context, lineage,
  outcomes, and denominators make causal labels indefensible.
- **Treat no correction as acceptance:** converts censored evidence into false
  positives.
- **Mine autonomic shadow traces as ground truth:** learns an existing policy's
  counterfactual output rather than observed deliberative correctness.
- **Use a scalar habit score:** permits savings to compensate for regret,
  privacy, or authority violations.
- **Random train/test split:** leaks later behavior into earlier candidate
  formation and ignores drift.
- **Let registration select the latest version automatically:** makes inventory
  mutation an activation path.
- **Put lifecycle in `RuleRegistry`:** combines immutable inventory and governed
  activation into two meanings of registry state.
- **Generate code or start with a model miner:** expands the trusted computing
  base before deterministic evidence semantics exist.
- **Infer preference or intent from repetition:** confuses observed behavior
  with user authority.

## Explicit deferrals

The first runtime wave does not include CANARY, ACTIVE, live wake suppression,
live reflex behavior, LLM rule induction, model-generated candidates,
reinforcement learning, bandits, online threshold tuning or retraining,
workflow/state-machine/graph/program synthesis, RETE, cross-user or federated
learning, SkillForge, automatic inferred preference, identity-sensitive
inferred habits, production learning from confidential employer data, or
learned cognitive allocation.

## Readiness answers

1. **First existing corpus:** none. The closest agent, action, autonomic, and
   cognitive-allocation families each miss required causal semantics.
2. **Outcomes or repetition:** action events have technical outcomes and
   cognitive traces may have optional links; neither provides a complete
   attention-outcome/correction corpus. Autonomic history is counterfactual.
3. **Exposure denominator:** after the precursor, every feature-complete,
   scope-matching, `LEARN`- and `EVALUATE`-permitted v1 attention opportunity in
   the cut, verified against recognized source triggers.
4. **Observed/inferred/censored:** dispositions, explicit feedback, and linked
   outcomes are observed; positive/counterexample categories are deterministic
   derived labels; missing or unresolved outcomes are censored.
5. **Runtime today:** NO-GO. The three-event deliberative-attention telemetry
   precursor is implemented; populate and verify a qualifying real corpus first.
6. **Learning permission:** distinct `InformationOperation.LEARN` and
   `.EVALUATE`, plus an intersected `allowed_secondary_uses` policy dimension;
   neither is implied by REASON, TELEMETRY, disclosure, legacy policy, or each
   other.
7. **Candidate to rule:** a versioned deterministic compiler registers an inert
   v2 rule with candidate provenance; a separate lifecycle event admits SHADOW.
8. **Legacy rules:** v1 registration upcasts to legacy-shadow compatibility,
   but has no path to CANARY/ACTIVE without future explicit admission.
9. **Unchanged rule contracts:** `AutonomicRule`, `PredicateSpec`,
   `SignalTemplate`, `RuleRegistry`, and `RulesetSnapshot`; the worker later
   supplies lifecycle-filtered explicit refs.
10. **Smallest miner:** bounded deterministic conjunction enumeration for
    `RuleFamily.PREDICATE` over pre-authorized scalar features and literals.
11. **Naive-rule counterexamples:** `requires_user_decision=true` or
    `urgency>=threshold` with observed WAKE/timely-decision evidence, plus any
    explicit correction of REMEMBER.
12. **Leakage prevention:** causal train/validation cuts, a train-only miner
    interface, fixed candidate identity before holdout, and no holdout-driven
    refinement.
13. **Safe-compression proof:** non-inferior outcome quality and bounded regret,
    errors, corrections, privacy, and externality alongside positive compute,
    latency, or attention `CompressionGain`.
14. **Collision safety:** exact ruleset pin, decidable typed predicate algebra,
    and fail-closed `UNKNOWN_OVERLAP`.
15. **Abstention:** missing, unknown, stale, contradictory, novel, out-of-scope,
    privacy-incompatible, corrected/quarantined, inhibited, or no-longer-current
    intent applicability.
16. **Approval:** first-slice SHADOW follows explicit lifecycle policy; every
    future CANARY/ACTIVE decision requires separate architecture and authority,
    with explicit human approval where user agency, identity, privacy,
    relationship, externality, or consequential risk is involved.
17. **Quarantine/retire evidence:** privacy/authority violation, permanent
    prohibition, high regret, denominator invalidity, material drift/holdout
    failure, or a newly detected collision quarantines; explicit permanent
    prohibition or superseding accepted policy may justify retirement.
18. **NO-GO conditions:** missing denominator completeness, insufficient
    observed outcomes/counterexamples, censored evidence above policy bounds,
    missing LEARN/EVALUATE permission, protected-literal leakage, temporal
    leakage, collision uncertainty, no novelty escape, authority increase, or
    inability to recover deterministically.

## Recommendation

**NO-GO for HabitForge runtime implementation today.** The architecture is
sufficiently specific to guide implementation, but the first source corpus is
not. Collect a qualifying canonical corpus through the separately implemented
deliberative-attention precursor, then rerun this readiness gate. Do not
compensate by widening the corpus or weakening labels.

This decision extends [ADR 0002](0002-autonomic-fabric.md),
[ADR 0004](0004-durable-consumer-checkpoints.md),
[ADR 0005](0005-persistent-cognitive-memory.md),
[ADR 0009](0009-information-governance-and-confidential-context.md), and
[ADR 0011](0011-governed-allocation-of-scarce-cognition-and-historical-reconsideration.md).
