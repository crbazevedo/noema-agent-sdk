# Engineering roadmap

The substrate is deliberately operational before the research program begins.
Research should now be performed by implementing competing policies and replaying them against identical event histories.

## W1 — Distributed durability

- broker adapter protocol;
- transactional outbox/inbox;
- distributed leases;
- capability-side exactly-once keys;
- worker crash recovery;
- event schema versioning.

## W2 — Model-backed reasoning

- structured-output `Reasoner` adapters;
- model routing by task and budget;
- tool-result grounding;
- context construction from situation queries;
- model-call telemetry and replay fixtures;
- deterministic mock model.

## W3 — Durable cognition and memory

- episodic retrieval from event history;
- semantic assertions linked to evidence events;
- contradiction tracking;
- hypothesis lifecycle and posterior updates;
- commitment and maintenance-debt projections.

## W4 — Adaptive metacontrol

- learned cognitive-mode selection;
- value-of-computation estimates;
- branch-opening and branch-closing policies;
- attention replenishment and fatigue models;
- counterfactual policy replay.

## W5 — Agent contracts

- capability discovery;
- typed task offers and bids;
- delegation contracts;
- evidence-weighted trust by domain;
- rehabilitation and exploration quotas;
- multi-agent disagreement protocols.

## W6 — Autonomous research harness

- scenario generator;
- baseline agent policies;
- randomized interventions;
- event-trace replay;
- ablation runner;
- calibration, regret, maintenance, and intervention metrics;
- artifact and report generation.

## W7 — Production operation

- sandbox adapters;
- secrets isolation;
- policy-as-code integration;
- OpenTelemetry sink;
- dashboards and incident timelines;
- deployment templates;
- chaos testing.

## Immediate implementation priority

The next code should be a model-provider adapter plus a replayable experiment runner. Those two layers let the SDK become its own research instrument without changing the core runtime.
