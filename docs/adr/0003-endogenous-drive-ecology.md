# ADR 0003: Governed endogenous drive ecology

- Status: accepted architecture direction; implementation staged
- Date: 2026-08-30
- Scope: v0.4 and later

## Context

The Autonomic Fabric supplies cheap reactions to external and internal events,
but an always-on durable agent also needs bounded reasons to maintain beliefs,
steward goals, resolve contradictions, prepare, explore decision-relevant
questions, and calibrate with peers during idle periods. Treating this as one
unbounded `reflect()` loop would obscure costs, authority, causality, and halt
conditions. Allowing arbitrary self-generated goals would introduce a hidden
sovereign utility function.

The immediate engineering need remains empirical: run the existing autonomic
fabric continuously in shadow mode and collect trustworthy outcome data before
building systems that learn habits or skills from it.

## Decision

1. Model exogenous signals and endogenous drives as two sources of demand for
   one finite aware workspace and attention budget.
2. Permit endogenous processes to propose instrumental, epistemic, maintenance,
   and exploratory goals beneath constitutional, user, mission, and commitment
   goals. They cannot create terminal values or increase their authority.
3. Represent questions and internal activities as first-class durable objects
   with governing-goal references, evidence, expected value, cost, privacy,
   interruptibility, status, and outcomes.
4. Use explicit background cognitive budgets and renewable leases. Foreground
   work preempts growth activity; bounded critical homeostasis is separate.
5. Separate independent belief, goal, calibration, memory, simulation, and
   ecology-maintenance loops. They emit candidates into an `IntrinsicAgenda`
   rather than mutating one another directly.
6. Treat SLEEP, DREAM, and AWAKE as governed runtime regimes. DREAM has
   observe/think/simulate/prepare/candidate authority only by default.
7. Keep HabitForge, SkillForge, and interaction adaptation separate.
   Capabilities and authority never advance together automatically.
8. Make peer calibration preserve propositions, confidence, evidence,
   assumptions, goals, and protocol versions. Disagreement is evidence, not a
   vote to suppress.
9. Continue the evidence progression `observe → evaluate → measure → learn →
   compile`. Do not build a Forge before continuous shadow telemetry supplies a
   representative corpus.

## Consequences

- Noema gains genuine initiative without assigning itself a new terminal
  purpose or second effect path.
- Background cognition becomes schedulable, preemptible, auditable work rather
  than prompt-level ambience.
- Questions, maintenance, simulations, and calibration compete fairly with
  external signals under cognitive economics and finite slack.
- Event volume and projection complexity increase; retention and aggregation
  policies must preserve auditability without logging every rejected thought.
- Skill and protocol adaptation can expand technical attack surface even when
  authority is unchanged, requiring separate sandbox and governance work.
- The architecture deliberately delays attractive learning mechanisms until
  production-path evidence exists.

## Rejected alternatives

- **React only to external events:** produces a durable responder without
  maintenance, curiosity, preparedness, or self-calibration.
- **One generic reflection loop:** hides contracts, budgets, halt conditions,
  ownership, and failure isolation.
- **Free-form self-generated goals:** conflates instrumental initiative with
  terminal-value selection.
- **Let dream work act externally:** makes idle-time cognition an unbounded
  actuator plane.
- **Build the Forges first:** leaves learning targets and fitness functions
  ungrounded in actual behavior.

## Fitness functions for future implementation

- intrinsic activities require governing goal references and budget leases;
- dream-mode outputs cannot cross an effect boundary directly;
- background loops are preemptible and have explicit ceilings;
- capability registration never grants authority;
- simulated evidence cannot be deserialized as observed evidence;
- agenda, budget, inquiry, and calibration projections rebuild from events;
- identical captured inputs, policies, cursors, and model fixtures reproduce
  semantic activity selection.

This ADR extends [ADR 0002](0002-autonomic-fabric.md) and is elaborated in the
[Endogenous Drive Ecology](../ENDOGENOUS_DRIVE_ECOLOGY.md).
