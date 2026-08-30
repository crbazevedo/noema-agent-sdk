# Changelog

## Unreleased

- accepted the signal-first Autonomic Fabric architecture;
- staged immutable rules, signals, shadow cells, the governed Forge, and
  situated wake control across v0.3–v0.6;
- added architecture gates for retired terminology, dynamic rule execution,
  and adapter leakage.

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
