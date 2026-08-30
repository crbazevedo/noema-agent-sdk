# Changelog

## Unreleased

- accepted the signal-first Autonomic Fabric architecture;
- implemented the effect-free Autonomic Shadow Kernel with immutable rules,
  content-addressed rulesets and sequence-pinned evaluation epochs,
  predicate/temporal/scoring cells, complete evaluation traces, and
  deterministic salience resolution;
- added a continuous observational worker over the canonical event substrate
  that persists evaluations and would-have-signaled/woken/suppressed outcomes
  without invoking models, authority, agents, or capabilities;
- distinguished precedence-based hard inhibition from confidence-weighted
  graded modulation and removed collection-membership predicates from the
  deliberately small rule language;
- demonstrated deep-work suppression, opportunity escalation, stale-delegation
  escalation, cheap resolution, and byte-equivalent replay;
- moved temporal evaluation plus rule telemetry/replay into the mandatory v0.3
  substrate, before Forge or active reflexes;
- staged the governed Forge and situated wake control across v0.5–v0.6;
- accepted the Endogenous Drive Ecology as a staged mid-term architecture for
  bounded inquiry, calibration, consolidation, and intrinsic agenda formation;
- added architecture gates for retired terminology, dynamic rule execution,
  adapter leakage, and imports from the effect plane.

## 0.2.0 — 2026-08-30

Portable durable agent milestone:

- PostgreSQL event store with transactional outbox and durable inbox;
- NATS JetStream transport behind a provider-neutral broker protocol;
- at-least-once delivery, expiring leases, fencing tokens, and crash recovery;
- versioned events with deterministic projection-time upcasting;
- structured model-provider contracts and `ActionIntent` validation;
- OpenAI Responses and OpenAI-compatible local model adapters;
- record/replay model fixtures and provider routing;
- provider-neutral tracing with an OpenTelemetry/OTLP adapter;
- embedded and distributed deployment profiles plus Docker Compose topology;
- architecture fitness functions and real distributed acceptance coverage.

## 0.1.0 — 2026-08-30

Initial working substrate:

- asynchronous event bus with ordered per-subscriber delivery;
- durable event stores for memory and SQLite;
- event-sourced situation graph;
- typed capability registry;
- attention-aware deliberation;
- policy-bounded autonomous execution;
- cognitive controller with critics and falsification hooks;
- scheduler, multi-agent system runtime, telemetry, and tests;
- runnable autonomous incident-response example.
