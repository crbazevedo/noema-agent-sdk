# Autonomic Fabric

The Noema Autonomic Fabric is a control plane beneath deliberative agency. Its
first effect-free shadow kernel is implemented; activation, Forge, and active
wake control remain staged work. The fabric turns repeated, well-evidenced
cognition into cheap, persistent, governed micro-policies while promoting
novelty, uncertainty, contradiction, conflict, and opportunity into the
deliberative workspace.

It is not a classical business-rules engine and not a second path around
Noema's authority model.

```text
WORLD / USER / SUBSTRATE
          │ observations
          ▼
  canonical event log
          │
     ┌────┴─────────────┐
     ▼                  ▼
situation/memory   immutable rule registry
     │                  │
     └───────┬──────────┘
             ▼
       governed RuleCells
             │ RuleFiring events
             ▼
        signal workspace
       ┌─────┼───────────┐
       │     │           │
    ignore  wake     propose reflex
             │           │
             ▼           ▼
       deliberation  ActionIntent
             │           │
             └─────┬─────┘
                   ▼
          policy + capability boundary
                   │ outcomes/corrections
                   ▼
                Rule Forge
```

The biological analogy is limited but useful: regulation can be local and
concurrent; local processes need not construct a global world model; global
context can modulate many processes; and reflective control can inhibit or
revise lower-level policies. No biological equivalence is claimed.

## Why it belongs in Noema

An always-on agent should not require an always-running foundation model. The
fabric can handle routine perception, salience, temporal monitoring,
coordination, homeostasis, and bounded reflex proposals with deterministic
evaluation over durable state. The expensive reasoner wakes when its expected
value exceeds its cost.

This gives Noema four compounding capabilities:

1. **Cognitive compilation.** Repeated successful deliberation can become a
   candidate micro-policy; uncertainty or failure escalates in the opposite
   direction.
2. **An attention membrane.** Most raw events terminate below deliberation;
   only strong unresolved signals enter the aware workspace.
3. **Governed personalization.** Learned rhythms remain scoped, probabilistic,
   falsifiable, versioned, and reversible rather than becoming permanent facts
   about a person.
4. **Efficient situated continuity.** Cheap cells maintain temporal and
   opportunity state between awake epochs, waking cognition only when the
   situation becomes decision-relevant.

The research question is therefore: how much deliberation can safely compile
into governed autonomic policy without increasing error, regret, privacy cost,
or unwanted intervention?

## Flagship personal-agent scenarios

- **Deep-work attention:** infer probable focus from low-cost context, suppress
  routine interruptions, but promote urgent user-required decisions.
- **Opportunity windows:** combine expiring deadlines, collaborator presence,
  readiness, and expected value so cognition wakes while action is still useful.
- **Progressive perception:** request structured metadata first and richer
  sensing only when a current goal, stale evidence, and value of information
  justify the privacy and resource cost.
- **Memory consolidation:** promote stable repeated observations, retain
  corrections as learning episodes, and lower confidence when evidence drifts.
- **Delegation continuity:** monitor leases, progress absence, dependencies, and
  agent presence before escalating or reopening work.
- **Routine compilation:** move a repeatedly successful, reversible workflow
  from expensive deliberation into shadow evaluation and eventually a bounded
  reflex proposal.

## Canonical state and projections

The event store remains the only source of truth. A separate rule database,
cell-local truth, or model-managed policy memory would create unrecoverable
divergence.

Canonical rule events include:

```text
rule.intent_recorded
rule.version_registered
rule.lifecycle_changed
rule.ruleset_pinned
rule.firing_recorded
rule.evaluation_summarized
rule.outcome_linked
rule.feedback_recorded
rule.candidate_forged
rule.collision_detected
```

The rule registry, temporal state, active ruleset, signal workspace, metrics,
and Forge training views are projections. Cell checkpoints are disposable
accelerators and must be rebuildable from the log.

The durable causal chain is:

```text
Observation → Evidence → RuleEvaluationTrace → hypothetical Signal
```

Signals and salience decisions are disposable projections. Their evidence and
complete shadow evaluation traces are durable when monitoring or replay policy
requires it. Rule cells never become a second situation store.

A fabric `EvaluationEpoch` pins a `RulesetSnapshot`, including while the
deliberative agent sleeps. An `AwakeEpoch` references the current evaluation
epoch and ruleset. A rule registered or activated during an evaluation epoch
becomes eligible only at the next boundary. Given identical events, situation
state, model fixtures, ruleset snapshot, and configuration, the fabric must
produce identical activations.

## Core contracts

### `Signal`

A signal is a bounded, expiring claim about what may deserve internal or
deliberative attention:

```text
signal_id, kind, subject
confidence, salience, urgency, novelty
expected_value, expected_loss
valid_from, valid_until
evidence_event_ids, rule_version_refs
suggested_mode, privacy_class
status, correlation_id, causation_id
```

Signals are not facts and do not grant authority. They may be contradicted,
inhibited, merged, resolved, or allowed to expire.

### `AutonomicRule`

Rule identity and versions are separate. Versions are immutable and include:

```text
rule_id, version, intent_text, purpose
family, scope, trigger selector, dependencies
encoding kind, typed encoding payload
output signal template or bounded reflex proposal
confidence, threshold, precedence
inhibits, inhibited_by, cooldown, ttl
authority_required, privacy_class, externality
evidence refs, test-suite ref, provenance
lifecycle state, supersedes
```

The original natural-language intent is retained verbatim as evidence of
purpose. It seeds an `IntentFrame`; it is never executed directly.

### `RuleFiring`

Every match, suppression, near-threshold activation, and emitted output records
the pinned rule version, activation components, evidence, modulators,
conflict decisions, emitted signal, downstream proposal/action linkage, and
eventual outcome. Pure nonmatches are periodic aggregate events unless an audit
or shadow experiment requests full detail. This is the feedback substrate for
calibration and rule fitness without turning every indexed lookup into a hot-log
write.

The implemented shadow form is `RuleEvaluationTrace`: it records candidates,
activation score and threshold, matched and failed conditions, evidence event
references, the signal that would have been emitted, suppression metadata, and
measured runtime cost. Wall-clock runtime cost is deliberately excluded from
byte-equivalent replay semantics.

### `SalienceResolver`

The resolver is the effect-free bridge between the event fabric and aware
cognition. It deduplicates and aggregates active signals by subject, applies
pattern-based inhibitory signals, enforces an optional wake budget, and returns
one of `WAKE`, `REMEMBER`, `REFLEX_PROPOSAL`, `SUPPRESS`, or `DEFER`. Every
result is a shadow decision with a compact evidence packet. The resolver does
not publish, wake a model, or invoke a capability.

### `GlobalModulator`

Values such as probable deep work, availability, privacy pressure, deadline
pressure, resource pressure, and exploration budget alter thresholds across
rule families. They are provenance-bearing situation projections, not hidden
mutable globals.

## Rule families

The initial taxonomy is behavioral rather than application-specific:

| Family | Purpose | Default output |
|---|---|---|
| Perceptual | Convert observations into meaningful, uncertain state | fact candidate or signal |
| Salience | Estimate what deserves attention | attention signal |
| Temporal | Detect sequence, repetition, absence, staleness, and deadlines | temporal signal |
| Opportunity | Detect expiring high-value action windows | opportunity signal |
| Homeostatic | Keep attention, memory, cost, and interruption within bounds | inhibitory/modulator signal |
| Coordination | Monitor delegations, leases, dependencies, and agent presence | coordination signal |
| Reflex | Propose a narrowly bounded and usually reversible action | `ActionIntent` proposal |

Rules emit signals by default. A reflex rule may only propose an `ActionIntent`;
it cannot invoke a capability. Critics, attention allocation, policy,
authorization, dispatch, idempotency, and the capability boundary remain
mandatory.

## Sanctioned rule encodings

Learned policies compile into a versioned, typed intermediate representation,
never generated Python or arbitrary executable code.

The shadow kernel supports exactly these first three encodings:

1. **Predicate:** safe comparisons over declared event and situation values.
2. **Scoring:** bounded weighted Boolean features with explicit normalization.
3. **Temporal:** an anchor, elapsed duration, absence/reset events, and current
   predicates.

State-machine and graph-pattern encodings remain future candidates and are not
accepted by the registry. The first slice also limits rule literals to immutable
JSON scalars so a frozen rule cannot conceal mutable policy state.

Rules reference capability IDs and signal kinds, not functions. The evaluator
validates operands, operations, dependency names, output types, and complexity
before registration.

Start with selector, scope, and dependency indexes. Shared condition caching or
a RETE-inspired network is justified only after profiling demonstrates that
incremental matching is the bottleneck.

## Probabilistic evidence, deterministic activation

The runtime does not randomly fire a rule. Uncertainty belongs in evidence and
calibrated feature values; evaluation remains reproducible.

```text
activation =
    condition_probability
  × context_relevance
  × expected_value
  × urgency
  - risk
  - interruption_cost
  - redundancy
  + excitation
  - inhibition
```

Every term, weight, normalizer, and threshold belongs to the pinned rule
version or ruleset configuration. Activation occurs only when hard gates pass
and the deterministic score reaches the threshold.

## Semi-decentralized execution

`RuleCell` is a deployment and state-locality boundary, not a source of truth
or authority. Cells subscribe to narrow event families, use bounded local
temporal state, and emit standard events. Example cells may cover attention,
calendar, code-host activity, communication, memory, opportunity, delegation,
or desktop context.

Cells:

- do not call one another directly;
- do not invoke capabilities;
- do not own canonical rule or situation state;
- declare subscriptions, dependencies, queue bounds, and restart semantics;
- can be placed in-process or distributed without changing rule semantics.

This supports local causal loops without a single global evaluation pass. A
logical agenda remains responsible for conflict resolution and governance. It
may be deterministically partitioned by subject or scope; it need not be one
process.

## Agenda, inhibition, and hard precedence

Execution order never resolves conflicts. The agenda first applies hard
precedence, then explicit inhibition, then utility arbitration and deduplication.
Excitatory and inhibitory contributions are preserved in the firing record.

The policy hierarchy is:

```text
L0  invariants          fixed security, privacy, sandbox, and authority limits
L1  autonomic reflexes  stable cheap policies
L2  adaptive heuristics probabilistic learned policies
L3  hypotheses          shadow candidates under evaluation
```

No lower level may override a higher one. In particular, learned rules cannot
weaken L0, increase their own authority, change privacy policy, activate
arbitrary sensing, or bypass capability governance.

The deliberative layer can issue governed inhibition/modulation events: suppress
a family temporarily, lower an opportunity threshold, make a capability
prepare-only, or reduce exploration. These controls are scoped and expiring.

## Rule Forge

Natural-language preferences and observed behavior seed hypotheses, not active
rules. The Forge preserves the original intent and produces a structured
`IntentFrame` containing goals, contexts, preferences, exceptions,
non-goals, ambiguities, and required clarification.

Candidate sources include repeated user corrections, repeated deliberative
trajectories, recurring manual workflows, unresolved-signal clusters, missed
opportunities, false wakeups, and delegation failures.

```text
intent or observed pattern
  → intent frame / pattern hypothesis
  → evidence and episode retrieval
  → typed candidate generation
  → counterexample search
  → historical replay
  → impact simulation
  → collision analysis
  → shadow
  → canary
  → active
```

The model may propose an intent frame or typed candidate. Deterministic schema
validation, semantic-alignment checks, evidence, counterexamples, replay,
collision analysis, policy, and lifecycle gates decide whether it advances.
Ambiguity produces a clarification or a retained hypothesis, never a guessed
active policy.

## Lifecycle and authority

```text
HYPOTHESIS → DRAFT → SHADOW → CANARY → ACTIVE
                            ↘ QUARANTINED
ACTIVE ⇄ THROTTLED → QUARANTINED
any nonterminal state → SUPERSEDED or RETIRED
```

Lifecycle transitions are events. Versions never mutate in place. A revised
rule supersedes an earlier version while preserving both histories.

Graduation burden is proportional to risk, reversibility, privacy,
externality, resource cost, confidence calibration, support, and user impact:

- internal annotation, salience, memory tagging, or wake suppression may
  graduate automatically behind replay and shadow evidence;
- interruption, private sensing, or expensive inference requires stronger
  evidence and tight canary budgets;
- file changes, communication, purchase, deletion, or other external effects
  require explicit authority and continue through the normal action pipeline.

Meta-rules may propose throttling, quarantine, generalization, revision, or
retirement. They cannot silently rewrite or activate executable policy.

## Self-observation and fitness

Rule fitness is a projection over firing and outcome events:

```text
fitness =
    precision
  + realized utility
  + opportunity gain
  + user acceptance
  - false wakeups
  - interruption cost
  - action regret
  - conflict rate
```

Support, coverage, calibration, firing/suppression frequency, overrides,
concept drift, time since useful firing, and downstream cost remain visible.
Age alone never increases legitimacy.

The first research metrics should be deliberative episodes avoided per active
rule, utility retained, false-escalation rate, regret, latency, model cost,
privacy cost, and user intervention.

## Technology and deployment mapping

The fabric extends existing Noema ports rather than introducing a separate rule
server:

| Layer | Embedded | Distributed | Invariant |
|---|---|---|---|
| Canonical history | SQLite `EventStore` | PostgreSQL `EventStore` | Events remain authoritative |
| Delivery | `AsyncEventBus` | NATS through outbox/inbox | At-least-once with idempotent firing IDs |
| Registry/signals | In-process projections | Rebuildable database-backed projections | Never independent truth |
| Evaluation | Pure Python typed-IR evaluators | Same evaluators in workers | No provider SDK or dynamic code |
| Temporal wakeups | `AsyncScheduler` and event time | Partitioned timer/cell workers | Time decisions become events |
| Candidate generation | `ModelProvider` or deterministic miner | Routed provider adapters | Models stay outside hot-path evaluation |
| Replay | Captured events and model fixtures | Same artifacts | Pinned epoch and ruleset |
| Operations | Event trace and local metrics | OpenTelemetry plus firing projections | Audit derives from canonical causality |

Selector, scope, and dependency indexes are the initial performance mechanism.
PostgreSQL indexes or local dictionaries are deployment details behind the same
matcher contracts. No heavyweight engine is required for the first slice.

## Relationship to the release sequence

The fabric is a cross-cutting track, not one monolithic release:

- **v0.3:** introduce `Signal`, immutable rule versions, `RulesetSnapshot`,
  `EvaluationEpoch`, deterministic predicate/temporal/scoring evaluation,
  complete firing telemetry/replay, salience resolution, and shadow-only cells.
  The Autonomic Shadow Kernel foundation is implemented; persistent memory
  provides the broader evidence substrate.
- **v0.4:** add coordination cells for delegations, leases, and agent ecology;
  rules remain protocol-neutral.
- **v0.5:** add counterfactual replay, compile-down candidate mining, fitness,
  meta-rule proposals, and governed lifecycle transitions.
- **v0.6:** add durable timer workers, richer opportunity patterns,
  sensing-request signals, evaluation/awake-epoch linkage, active wake control,
  and salience-based situated continuity.

Automatic canary reflexes should wait until these foundations provide durable
evidence, replay, temporal semantics, and metacontrol.

## Autonomic Shadow Kernel

The implemented first vertical slice is deliberately effect-free:

1. immutable `AutonomicRule` versions and event-rebuildable `RuleRegistry`;
2. digest-verified `RulesetSnapshot` with exactly one version per rule identity,
   and a pinned `EvaluationEpoch`;
3. predicate, temporal, and bounded scoring encodings with a safe evaluator;
4. stateless `RuleCell` evaluation over caller-supplied situation and history;
5. complete `RuleEvaluationTrace` telemetry with hypothetical `Signal` output;
6. deterministic `SalienceResolver` aggregation, inhibition, and wake budgets;
7. `SHADOW` outputs only, with an architecture gate against effect-plane imports;
8. replay fixtures for deep work, opportunity windows, and stale delegation.

Acceptance requires:

- identical inputs and pinned ruleset produce byte-equivalent firing semantics;
- shadow rules produce no active signal, deliberative wake, or action;
- a late rule version cannot enter the current evaluation epoch;
- inhibition and hard precedence are independent of evaluation order;
- restart replay rebuilds registry, temporal state, and unresolved shadow signals
  from canonical events;
- no online model call is required for evaluation;
- no learned rule contains or invokes arbitrary code;
- the same cell runs embedded and distributed without application branching;
- a personal workflow demonstrates fewer deliberative wakeups without losing a
  relevant opportunity.

## Quality-attribute scenarios

| Attribute | Scenario and response |
|---|---|
| Safety | A forged rule proposes an external effect; the fabric can only emit an `ActionIntent`, and existing policy/capability gates still decide. |
| Auditability | Given a user-visible interruption, correlation links its action to signal, firing, pinned rule version, evidence, intent, and activation decision. |
| Determinism | Replaying an awake epoch with captured model outputs and its ruleset snapshot reproduces activation and conflict outcomes. |
| Reliability | A cell crashes after firing; event identity and the durable firing ledger prevent a second logical signal while at-least-once delivery continues. |
| Privacy | A rule requests richer sensing; a signal enters the perception policy, which applies permission, freshness, retention, and authority gates before capture. |
| Performance | Ten thousand rules observe a sparse event; selectors and dependency indexes evaluate only candidates, with RETE deferred until profiling. |
| Modifiability | A new rule encoding implements a stable evaluator port and schema without changing cells, the registry, lifecycle, or authority. |
| Local-first | The effect-free slice runs with SQLite and deterministic local classifiers; distributed stores and brokers change deployment only. |

## Risks and sensitivity points

- **Threshold calibration** controls both missed opportunities and signal storms.
- **Ruleset pin duration** trades reproducibility against responsiveness to a
  newly quarantined rule; L0 emergency inhibition must take effect immediately.
- **Cell partitioning** trades locality against duplicated state and cross-cell
  coordination pressure.
- **Forge correlation errors** can encode coincidental behavior as preference;
  counterexamples, support thresholds, drift monitoring, and reversibility are
  mandatory.
- **Inferred private context** can be more sensitive than raw inputs; privacy
  classification applies to signals, intent frames, and firing records.
  Preserving intent does not imply broad retrieval or prompt inclusion.
- **Meta-rule recursion** can destabilize governance; meta-rules propose changes
  and cannot bypass lifecycle gates.
- **Full RETE, arbitrary CEP, and general policy languages** would turn the SDK
  into a framework inside a framework. Add only measured capabilities.

See [ADR 0002](adr/0002-autonomic-fabric.md),
[architecture principles](ARCHITECTURE_PRINCIPLES.md), and
[Situated Continuity](SITUATED_CONTINUITY.md).
