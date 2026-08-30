# Endogenous Drive Ecology

Noema needs two governed sources of cognitive demand:

```text
exogenous signals  observations, deadlines, other agents, opportunities
endogenous drives  coherence, maintenance, curiosity, preparedness, calibration
```

The Autonomic Fabric asks what in the observed situation deserves attention.
The Endogenous Drive Ecology asks what is worth investigating or maintaining
when no external event currently demands cognition. Both compete for the same
finite attention, cost, privacy, and authority budgets.

This is a mid-term architecture direction. The immediate implementation remains
the observational shadow worker and its evidence corpus. No intrinsic scheduler,
HabitForge, SkillForge, or self-generated external action is implemented yet.

## Governing invariants

1. **No self-chosen terminal values.** Endogenous processes may derive
   instrumental, epistemic, maintenance, and exploratory goals beneath user and
   mission goals. They cannot invent a new sovereign purpose.
2. **Questions before actions.** Intrinsic motivation creates inquiries,
   hypotheses, simulations, candidate goals, and maintenance proposals more
   readily than external actions.
3. **One effect path.** An endogenous result that eventually suggests action
   still becomes an `ActionIntent` and crosses ordinary policy, authority, and
   capability gates.
4. **Slack is finite.** Background cognition consumes an explicit renewable
   budget. Foreground demand can reduce growth work to zero; safety-critical
   homeostasis retains a separately bounded reserve.
5. **Authority never follows competence automatically.** A candidate skill may
   increase what the agent can technically do, but never what it may do.
6. **Canonical evidence, rebuildable agendas.** Inquiries, simulations,
   maintenance candidates, outcomes, and calibration exchanges enter the event
   log. Priority queues, portfolios, drive levels, and health metrics are
   projections.
7. **No hidden utility mutation.** Drive weights and metacognitive policies are
   explicit, versioned, provenance-bearing configuration.
8. **Dream outputs are observational by default.** Background cognition may
   observe, think, simulate, prepare, or forge a candidate. It may not silently
   send, delete, purchase, deploy, or widen sensing.

## Goal hierarchy

```text
G0  constitutional constraints  safety, privacy, authority, user sovereignty
G1  user and mission goals       explicitly desired outcomes
G2  durable commitments          accepted obligations
G3  instrumental goals           prerequisites and subgoals
G4  epistemic goals              decision-relevant questions
G5  maintenance goals            belief, memory, skill, and ecology health
G6  exploratory goals            bounded option-seeking hypotheses
```

Authority and conflict precedence flow downward. An endogenous process may
create G3–G6 candidates only when it can cite a governing G0–G2 context or an
explicit bounded maintenance mandate. It cannot demote or replace G0–G2.

## Intrinsic drives

The initial architecture uses a small generic set rather than a catalogue of
personality traits:

| Drive | Purpose | Typical output |
|---|---|---|
| Coherence | Resolve consequential contradictions | inquiry or revalidation candidate |
| Curiosity | Gain decision-relevant information | inquiry |
| Competence | Reduce likely capability gaps | skill candidate |
| Efficiency | Reduce repeated cognitive/operational cost | habit candidate |
| Preparedness | Preserve future options and contingencies | simulation or plan candidate |
| Alignment | Reduce divergence from user goals/preferences | clarification or interaction hypothesis |
| Social calibration | Explain important peer disagreement | calibration request |

Homeostatic drives maintain commitments, evidence, memory, calibration, and
rule ecology. Growth drives explore, simulate, learn, and propose new habits,
skills, or protocols. Under load, the growth budget falls first.

Drive strength is evidence, not permission. It may increase the priority of an
internal activity; it cannot grant authority or bypass a hard inhibitor.

## First-class internal events

The event fabric remains origin-neutral. Future event families include:

```text
self.question.generated
self.belief.stale
self.contradiction.detected
self.goal.progress_stalled
self.skill_gap.detected
self.habit.candidate_detected
self.memory.consolidation_due
self.strategy.performance_degraded
self.interaction_mismatch_detected
self.simulation.requested
self.peer_calibration_due
```

These events are observations or proposals. Their `self.*` origin does not make
them more authoritative than external evidence.

## Core durable objects

### `Inquiry`

```text
inquiry_id, question, origin
expected_information_value, decision_relevance
governing_goal_refs, evidence_refs, possible_methods
estimated_cost, privacy_class, deadline
status, outcome_refs
```

Questions form an Inquiry Portfolio; they are not all investigated immediately.

### `IntrinsicActivity`

A schedulable internal candidate such as inquiry, simulation, belief
maintenance, goal maintenance, peer calibration, memory consolidation, habit
candidate, skill candidate, or interaction adaptation. It declares expected
value, cost, urgency, confidence, interruptibility, governing goals, and
resource requirements.

### `BackgroundCognitiveBudget`

An explicit budget over model calls, wall-clock time, tokens, money, energy,
privacy exposure, and attention. Allocation is derived from foreground load,
commitments, resource pressure, and operator policy. Unspent capacity is
**cognitive slack**, not permission for unbounded reflection.

### `CalibrationExchange`

Versioned request/response objects compare propositions, confidence, evidence,
assumptions, and goals. The purpose is to explain why posteriors differ, not
merely vote.

### `DreamEpoch`

A bounded background-cognition interval pins drive policy, budget, model
fixtures, evidence cursor, and authority ceiling. Its outputs are replayable
proposals and observations. A dream epoch cannot create an effect path.

## Cognitive economics

Curiosity is expected decision value, not novelty seeking:

```text
curiosity(question)
  = probability the answer changes a future decision
  × decision impact
  × uncertainty
  - acquisition cost
```

All candidate internal cognition uses the same value-of-computation frame:

```text
NetVOC(activity)
  = expected decision improvement
  - compute cost
  - delay cost
  - attention cost
  - opportunity cost
  - privacy/risk cost
```

Positive NetVOC makes an activity eligible, not mandatory. Goal precedence,
hard constraints, renewable budgets, diversity requirements, and portfolio
selection still apply.

## Intrinsic Agenda

The future `IntrinsicAgenda` is a projection and scheduler of contracted
`IntrinsicActivity` values:

```text
internal observations
  → drive detectors
  → activity candidates
  → hard-governance filter
  → NetVOC and portfolio scoring
  → background budget lease
  → SLEEP, DREAM, or AWAKE workspace
  → durable outcome and calibration evidence
```

Independent durable loops produce candidates rather than sharing one opaque
`reflect()` method:

- belief hygiene detects stale, weak, or contradictory claims;
- goal stewardship detects stalled, obsolete, blocked, or misallocated goals;
- self-calibration compares predictions, confidence, sensors, rules, and
  delegation estimates with outcomes;
- memory consolidation proposes merge, abstraction, decay, contradiction, or
  bounded forgetting;
- counterfactual simulation explores likely events, failures, deadlines, and
  contingencies under strict branch and cost ceilings.

## Cognitive regimes

The names are engineering metaphors:

```text
SLEEP  cheap autonomic regulation; no expensive cognition
DREAM  budgeted endogenous cognition; observational/proposal authority only
AWAKE  explicit cognition focused on foreground or promoted internal demand
```

An `EvaluationEpoch` may continue during all three. A `DreamEpoch` and an
`AwakeEpoch` reference the active evaluation epoch and the same canonical event
cursor so the source of promoted cognition remains reconstructable.

## Aware workspace

Exogenous signals and endogenous activities compete in one scarce global
workspace. Eligible content includes external novelty, contradiction, goal
discrepancy, opportunity, peer disagreement, skill gap, important uncertainty,
and failure. Cross-module integration happens here; origin alone does not set
priority.

## Learning directions

Three different mechanisms must remain separate:

- **HabitForge — think less:** compile repeated successful deliberation into a
  typed candidate autonomic policy.
- **SkillForge — become able to do more:** propose a capability from recurring
  unmet need, then require sandboxing, tests, review, registration, and separate
  authority.
- **Interaction adaptation — coordinate better:** learn scoped, uncertain,
  reversible hypotheses about users, channels, handoffs, or inter-agent
  protocols.

The Forge systems are metacognitive consumers of evidence, outside both the
autonomic execution boundary and the capability boundary. None is the next
runtime milestone. The required progression is:

```text
observe → evaluate → measure → learn → compile
```

The continuous shadow worker supplies the first empirical corpus: rule
evaluations, hypothetical signals, hypothetical wakes/suppressions, actual
deliberative episodes, corrections, misses, and overrides.

## Agent ecology and social epistemology

Durable agents may exchange compact state deltas, evidence, hypotheses,
unresolved questions, and commitments through versioned protocols. Protocol
adaptation must preserve inspectability and fallback compatibility.

High-impact disagreement becomes a signal when agents differ because of
evidence, assumptions, goals, freshness, or reasoning. Deployments may preserve
epistemic diversity deliberately through independent inference, adversarial
critique, outside-view reasoning, alternative simulations, and source
verification.

## Metrics

- background compute and cost by drive and governing goal;
- foreground interference and preemption latency;
- inquiry value: decision improvement per information-acquisition cost;
- contradictions resolved and high-impact beliefs revalidated;
- calibration error before/after maintenance;
- useful contingencies discovered versus simulation branches explored;
- deliberation-to-habit candidate rate and accepted compilation rate;
- recurring incapability-to-skill candidate rate;
- user rejection, override, and clarification rates;
- stale inquiry, goal, habit, skill, and rule debt;
- external effects proposed from dream mode, which should remain tightly bounded
  and separately authorized.

## Quality-attribute scenarios

| Attribute | Scenario and response |
|---|---|
| Alignment | Curiosity proposes an unrelated terminal goal; hierarchy validation rejects it because no governing G0–G2 context exists. |
| Safety | A dream simulation suggests sending a message; only a proposal is recorded and the ordinary action path remains mandatory. |
| Resource control | Foreground demand arrives during simulation; the background lease is preempted or expires and growth budget falls toward zero. |
| Auditability | An internal question wakes cognition; its drive evidence, activity score, budget lease, epoch, and governing goal are reconstructable. |
| Privacy | A question would require richer sensing; perception policy independently evaluates value, consent, retention, and privacy cost. |
| Reliability | The intrinsic scheduler restarts; its agenda and leases rebuild from events and unfinished work is reconciled explicitly. |
| Multi-agent integrity | Peers disagree; calibration preserves propositions, confidence, evidence, assumptions, and protocol version rather than collapsing to a vote. |

## Risks and sensitivity points

- Drive weights can become a hidden utility function if they are not explicit
  and governed.
- Self-referential cognition can consume unbounded resources; ceilings,
  preemption, and stop conditions are mandatory.
- Maintenance can destroy valuable minority evidence; forgetting and merging
  require provenance and reversibility proportional to impact.
- Simulations can produce persuasive but unsupported artifacts; simulated and
  observed evidence remain distinct types.
- Interaction adaptation can overfit a user or context; hypotheses are scoped,
  confidence-bearing, and reversible.
- Skill creation expands attack surface even without authority expansion;
  sandboxing, supply-chain review, tests, and operator governance remain
  independent gates.
- Agent convergence can erase useful epistemic diversity; calibration protocols
  should expose disagreement before attempting consensus.

See [Autonomic Fabric](AUTONOMIC_FABRIC.md),
[Situated Continuity](SITUATED_CONTINUITY.md), and
[ADR 0003](adr/0003-endogenous-drive-ecology.md).
