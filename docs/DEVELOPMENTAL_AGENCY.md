# Durable Developmental Agency

Status: Proposed architecture direction. No developmental-intervention runtime
is implemented or authorized by this document.

Noema's long-range purpose is to support applications that can run durable
work, improve decisions, and help users improve while preserving current
intent and human agency. The SDK provides general mechanisms; sentinel,
chief-of-staff, thought-partner, mentor, coach, and epistemic-steward behavior
remain application functions rather than SDK identities or personas.

## The architectural promise

Developmental agency means that an application may form an evidence-bearing
view that a bounded advisory intervention could improve a named current user
outcome. It does not mean that the agent chooses what the user should value or
silently rewrites the user's goals.

```text
preserve current intent
  + inspect evidence and uncertainty
  + allocate finite cognition
  + estimate immediate and secondary effects
  + respect explicit mode permission
  -> silence, or propose a bounded advisory intervention
```

The governing non-equivalences are:

```text
challenge authority != decision authority != intent authority != effect authority
past behavior != current intent
personalization != terminal values
developmental advice != user-goal mutation
always-on != continuous large-model invocation
background cognition != endless monologue
observation != truth
capability != permission != authority
```

## One stewardship chain

Developmental intervention extends the existing Intent & Outcome Stewardship
chain:

```text
current user outcome
  + current GoalRevision / roadmap outcome when one exists
  + OutcomeRoleAssignment
  + AssistanceEnvelope
  + typed assessment and evidence
  -> AdvisoryInterventionProposal
  -> deterministic, exact-head admission
  -> AdvisoryInterventionRecord
```

Every material intervention must name the immediate user outcome it expects to
improve. If that outcome is governed by a roadmap, the intervention also names
the exact current goal revision, roadmap revision, and outcome node. Direct
user outcomes remain legitimate without manufacturing a roadmap.

The outcome role assignment keeps outcome ownership, decision ownership,
execution, and verification separate. The assistance envelope supplies
privacy, risk, reversibility, attention, institutional, relationship,
identity, human-work, checkpoint, and support limits. A future schema may add
explicit permission for typed advice, challenge, teaching, coaching, and
preparation modes. Existing envelopes grant no such modes implicitly.

```text
AdvisoryIntervention != WorkOrder != ActionIntent
```

An intervention proposal cannot dispatch work, perform an effect, or mutate a
goal. If an application later delivers a notification or takes an action, that
operation still requires its normal policy, capability, authority, and effect
admission. A user may choose to revise intent after advice, but that revision
travels through the existing authenticated intent path as a distinct event.

## Immediate outcomes before developmental claims

The primary intervention claim is improvement to the named current outcome.
The proposed impact vector may also preserve:

- expected decision or outcome improvement;
- expected reduction in user effort;
- intervention, attention, delay, privacy, and opportunity costs;
- affected stakeholders and possible externalities;
- assumptions, counterevidence, alternatives, and tradeoffs;
- confidence and validity horizon; and
- expected long-term agency or capability effect.

Long-term agency effect is secondary evidence. It never supplies permission,
defines terminal values, compensates for expected harm to the immediate
outcome, or overrides the user's decision. The dimensions stay typed and
inspectable rather than collapsing into an opaque development score.

## A private cognitive ecology, not many schedulers

Always-on private cognition is a bounded ability to notice, inquire, assess,
and preserve useful typed claims even when no foreground request is active. It
is not a permanently running monologue.

Potential concerns include situation continuity, goal coherence, hazards,
scenarios, stakeholder impacts, epistemic health, developmental opportunities,
historical reconsideration, and cognitive compilation. They share one control
shape:

```text
detectors and governed evidence
-> Inquiry proposals
-> one scarce-cognition portfolio
-> bounded proposal-only cognition
-> typed assessments
-> intervention candidates
-> intervention policy
-> silence, advise, challenge, teach, coach, or prepare
```

Detectors identify possible cognitive demand. They do not own timers, budgets,
workers, or effects. `Inquiry`, `IntrinsicActivity`, the background cognitive
budget, proposal-only epochs, allocation traces, and consumer checkpoints are
the reusable substrate. The eventual mixed portfolio must preserve finite
budgets, foreground preemption, expiry, deterministic recovery, and current
intent.

The only durable cognitive outputs are typed claims and their evidence,
counterevidence, uncertainty, provenance, validity, and policy lineage. Model
scratchpads and hidden reasoning transcripts are not canonical state and are
not a durable memory format.

## Evidence after intervention

An admitted intervention proves only what was proposed and admitted at a
particular causal cut. It does not prove correctness, delivery, adoption, or
benefit.

```text
intervention record
  + later observed outcome
  + explicit feedback, if any
  -> evidence for evaluation
```

A later outcome and user feedback are independent observations. A favorable
outcome does not prove acceptance; explicit acceptance does not prove a
favorable outcome. Correction, contextual exception, temporary override,
preference revision, rejection, and prohibition must remain distinct.
Silence, missing feedback, and unresolved outcomes are censored, not positive
or negative labels.

Information Governance applies both to forming an intervention and to later
reuse of its evidence. Operational access is not learning consent. Persistent
learning and retrospective evaluation require separate `LEARN` and `EVALUATE`
decisions, including the composed policy and lineage of derived assessments.

## Admission and replay

Material intervention is validated against one exact canonical state:

```text
capture H
-> rebuild current intent, outcome, roles, assistance, and information through H
-> validate mode permission and all limits
-> append_if_head(intervention, H)
    |-- admitted
    `-- head changed: reload and revalidate
```

Terminal governing intent denies new intervention. `BLOCKED` intent may still
receive bounded recovery assistance. Stale goal, roadmap, outcome, role,
assistance, information-policy, or validity references deny admission rather
than being silently rebound.

The canonical event log remains the source of truth. Current views and evidence
sets are deterministic projections. Replay checks the actual preceding
canonical head and does not assume durable sequence numbers are contiguous.

## What belongs in the SDK

The smallest proposed general contract family is:

- an immutable advisory intervention proposal;
- an exact-head admission record;
- a typed intervention mode and an explicit envelope permission;
- a versioned multi-dimensional impact estimate;
- a causally later outcome link; and
- an explicit feedback record with actor and provenance.

These contracts express outcome, permission, provenance, impact, and evidence.
They do not prescribe a user-development methodology.

## What remains application-local

Applications choose product language, presentation, relationships, timing,
curricula, interaction patterns, and any named functions such as mentor or
coach. Domain-specific hazards, scenarios, stakeholder maps, competency models,
and development programs stay application-local until repeated use across
consumers demonstrates a small stable core contract.

The SDK does not define:

- a personality or persona hierarchy;
- a universal model of human development;
- terminal values or a preferred life plan;
- a generalized coaching workflow;
- an opaque user-development score;
- application notification or interface behavior; or
- a second scheduler, work plane, effect plane, or memory substrate.

## Proposed delivery boundary

This architecture is intended for a later developmental-intervention
foundation after review and acceptance. The first implementation should be a
small deterministic vertical slice that proves:

1. exact current outcome, intent, role, and assistance provenance;
2. explicit advisory-mode permission with fail-closed legacy migration;
3. typed immediate and secondary impact estimates;
4. exact-head admission, deterministic replay, sequence-gap safety, crash
   recovery, and concurrency behavior;
5. no goal mutation, work dispatch, action intent, or external effect;
6. independent causally later outcomes and explicit feedback, with silence
   censored; and
7. information lineage and separate learning/evaluation permission.

Learned selection, adaptive timing, developmental personalization, generalized
private-cognition scheduling, effect connectors, and domain ontologies remain
deferred. The normative proposal and its quality scenarios, risks, rejected
alternatives, fitness functions, and deferrals are in
[ADR 0013](adr/0013-durable-developmental-intervention.md).
