# Situated Continuity

Situated Continuity is the planned v0.6 plane for agents that explicitly
reconstruct context after intermittent execution:

> An agent is a temporally discontinuous process that reconstructs sufficient
> situational continuity whenever it becomes active.

It is not an always-conscious process and not a prompt-resume mechanism.

## Required state scopes

```text
WORLD
├── SUBSTRATE  execution environment, resources, permissions, sensors
├── ECOLOGY    people, applications, projects, services, and agents
├── USER       explicit goals, inferred preferences, attention, constraints
└── SELF       commitments, delegations, suspended work, assumptions
```

The agent receives a goal-relevant projection, not the raw universe.

## Invariants

- Capability, OS permission, and Noema authority are separate.
- Raw artifacts are evidence, not memory or truth.
- Mutable assertions carry event/valid time, observation time, and record time.
- Explicit goals outrank committed, revealed, and inferred goals.
- Consequential action is blocked until critical prerequisites are sufficiently fresh.
- Sensing escalates from stored knowledge to metadata, APIs, UI structure, and
  only then targeted pixels/audio.
- Default raw screenshot/audio retention is zero beyond the processing window.
- Every retained `SituationCapsule` has provenance, sensitivity, validity, and confidence.
- A wake cycle with no relevant change may successfully perform no action.

## Autonomic integration

The [Autonomic Fabric](AUTONOMIC_FABRIC.md) is the attention membrane for
situated continuity. Temporal and opportunity cells can maintain cheap state
between awake epochs, but the event log remains canonical. Fabric evaluation
epochs pin rulesets even while cognition sleeps; a new awake epoch references
that pin, reconciles source cursors, and orients over the strongest unresolved
signals rather than replaying every raw observation into deliberation.

Sensing rules emit perception-request signals; they never capture directly.
The perception policy still evaluates goal relevance, source freshness,
permission, privacy, retention, latency, and expected value before authorizing
a sensor. Emergency L0 inhibition is the only rule control that can override an
epoch pin, and it may only reduce capability.

## Planned sequence

1. Temporal semantics: `occurred_at`, `observed_at`, `recorded_at`, source
   cursors, `AwakeEpoch`, and freshness models.
2. `WakeReconciler`, `AwarenessCoverage`, and an orientation barrier.
3. `SubstrateProvider`, `Sensor`, `SensorRegistry`, and a deterministic fake substrate.
4. `SituationCapsule`, `ArtifactStore`, bitemporal assertions, and retention policy.
5. Value-of-information `PerceptionPolicy` with privacy, latency, and attention costs.
6. User/workflow models and minimum-sufficient `InterventionPolicy`.
7. Durable agent presence, delegation contracts, work leases, and catch-up.
8. Expiry-aware `OpportunityWindow` scheduling.
9. A macOS Swift sidecar: NSWorkspace first, Accessibility second, targeted
   ScreenCaptureKit last—never continuous capture by default.
10. A flagship simulated sleep/wake acceptance scenario that selectively
    catches up, reconciles delegation, acts on a closing opportunity, persists
    continuity, and returns to sleep.

These abstractions live above the canonical event machinery. v0.2 delivery and
schema contracts are prerequisites; they are not alternate implementations of
continuity.
