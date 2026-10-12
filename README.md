# Noema Agent SDK

**Build agents that remember what happened, know what they owe, and act within explicit authority.**

Noema is a Python SDK for long-running, event-driven agents. It gives an agent
persistent history, a queryable model of its situation, and a controlled path
from a proposed action to an executed capability. You supply the reasoning,
tools, and application policy.

## The vision

An agent that works over time needs more than a good answer. It needs to notice
change, keep commitments, distinguish evidence from assumptions, recover from
interruption, and know when it should act or leave a decision to a person.

Noema's thesis is that these responsibilities belong in the system around the
model: durable memory, explicit intent, limited attention, verifiable work, and
bounded authority. The aspiration is **“Run my work. Improve my decisions. Help
me improve.”** This SDK builds the infrastructure for that aspiration; the
full developmental partner is still a roadmap goal.

Three principles guide it:

- **History is the source of continuity.** Events preserve what happened and
  why; projections reconstruct the agent's situation and memory.
- **A proposal is not permission.** Reasoning, work assignment, and effect
  authority have separate contracts.
- **Attention has a cost.** Candidate actions and background inquiries compete
  under explicit budgets rather than assuming unlimited reasoning.

Use Noema when you need to build an agent whose work continues across events,
process restarts, or multiple workers, and whose decisions must be inspectable.
It is an SDK, not a ready-to-use assistant: application behavior and real-world
integrations remain your responsibility.

## Try a complete loop

Requires Python 3.11+ and Git. The embedded core has no third-party runtime
dependencies. These commands use a POSIX shell:

```bash
git clone https://github.com/crbazevedo/noema-agent-sdk.git
cd noema-agent-sdk
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
MODE=embedded NOEMA_SQLITE_PATH=:memory: python examples/autonomous_incident_agent.py
```

The [incident example](examples/autonomous_incident_agent.py) receives one
service metric, inspects a simulated service, proposes a restart, checks policy,
and records the resulting healthy state. It prints:

```text
Final API health: healthy

Causal event trace:
...
```

The service is a Python dictionary. No model, API key, network service, or real
restart is involved. This demonstrates the event-to-action loop, not production
incident remediation. The in-memory database is discarded when the process
exits; use a file path for persistent SQLite storage.

Next: [write your own agent](docs/RUNTIME_GUIDE.md#minimal-api),
[run with PostgreSQL and NATS](docs/RUNTIME_GUIDE.md#run-the-autonomous-example),
or explore the [examples](examples/).

## What works today

The following describes code in this repository, not every milestone named in
the roadmap. The package is marked **alpha**; APIs and contracts can change.

| Capability | Available behavior | Boundary |
| --- | --- | --- |
| Event-driven action loop | Async agents, scheduling, critics, attention allocation, policy checks, and typed capabilities | You implement tools and their risk/authority declarations |
| Durable runtime | SQLite history and replay; optional PostgreSQL, outbox/inbox, and NATS adapters | External effects need their own idempotency guarantees |
| Situation and memory | Facts, relationships, goals, commitments, evidence-bearing assertions, temporal beliefs, and preserved contradictions | Recorded beliefs are not a guarantee of truth |
| Work and intent | Validated dependency graphs, worker matching, fenced leases, and intent/outcome records | A work lease does not authorize an external action |
| Replaceable reasoning | Rule-based reasoning and structured model interfaces; optional OpenAI and OpenAI-compatible adapters | Model quality and costs depend on your configuration |
| Information governance | Policy/lineage checks at implemented memory, model-context, and worker-selection boundaries | Enforcement is opt-in; confidential production ingestion and exhaustive sink coverage remain staged |

### Implemented, but deliberately limited

Several foundations run and have tests without being full autonomous features:

- [Autonomic rules](docs/AUTONOMIC_FABRIC.md) record hypothetical signals and
  decisions. Their shadow worker cannot wake cognition or invoke capabilities.
- [Situated continuity](docs/SITUATED_CONTINUITY.md) reconstructs context and
  freshness using fake sources; its orientation barrier is shadow-only.
- [Background inquiry](docs/ENDOGENOUS_COGNITION.md),
  [historical reconsideration](docs/COGNITIVE_RECONSIDERATION.md), and
  [dormant discovery](docs/DORMANT_COGNITION_DISCOVERY.md) select or propose
  bounded cognitive work. These workers do not call models, dispatch work, or
  execute external effects.
- [Attention telemetry](docs/adr/0012-governed-habit-learning-and-cognitive-compilation.md)
  records opportunities, dispositions, outcomes, and feedback. A qualifying
  real operating corpus and runtime habit learning are still pending.

Developmental interventions, learned habits, durable source watches, and
material-output presentation remain accepted or proposed architecture, not
shipped runtime. The [roadmap](docs/ROADMAP.md) records those distinctions;
the [situated-partner rehearsal](docs/pilot/SITUATED_PARTNER_INTEGRATION.md)
is synthetic contract evidence, not a live companion or proof of field value.

## How the pieces fit

```text
Observation → Event log → Situation and memory
                              ↓
                           Reasoner
                              ↓
                         Action proposal
                              ↓
                  Critics → Attention → Policy
                              ↓
                          Capability
                              ↓
                      Result → Event log
```

`NoemaKernel` coordinates persistence, projection, and event delivery.
`AutonomousAgent` runs the decision loop. `CognitiveController` wraps a
replaceable `Reasoner` and critics. `PolicyEngine` checks proposals against
configured authority; `CapabilityRegistry` holds the functions that can act.
`NoemaSystem` hosts agents and runtime services around a shared kernel.

See the [minimal API](docs/RUNTIME_GUIDE.md#minimal-api) for a complete small
agent and the [architecture](docs/ARCHITECTURE.md) for the deeper contracts.

## Before connecting real effects

- Start with simulated capabilities and the minimum authority your application
  needs. The default profile permits bounded reversible actions; it is not an
  approval-only sandbox. Review [autonomy](docs/AUTONOMY.md) before changing it.
- Recovery is not exactly-once execution of external systems. Declare
  idempotency honestly and enforce it in the external tool. Unfinished
  non-idempotent capabilities are not automatically replayed after a crash.
- Do not treat the information-governance foundation as a complete security
  boundary for restricted data. Read its [implemented coverage and remaining
  gaps](docs/INFORMATION_GOVERNANCE.md) before deployment.
- Deterministic tests and synthetic rehearsals establish behavior under their
  fixtures. They do not establish real-world effectiveness, learned causal
  understanding, or general intelligence.

## Develop and go deeper

```bash
python -m pip install -e '.[dev]'
make check
```

`make check` runs unit tests, lint, type checks, and bytecode compilation.
[CI](.github/workflows/ci.yml) additionally exercises the incident application
with real PostgreSQL and NATS services. Those services transport and persist
the demo's events; the incident itself remains simulated.

- [Runtime guide](docs/RUNTIME_GUIDE.md): installation, API, recovery contracts,
  optional adapters, and focused test commands
- [Architecture](docs/ARCHITECTURE.md) and [principles](docs/ARCHITECTURE_PRINCIPLES.md)
- [Event semantics](docs/EVENTS.md), [memory](docs/PERSISTENT_COGNITIVE_MEMORY.md),
  [work coordination](docs/DURABLE_WORK_COORDINATION.md), and
  [intent/outcome stewardship](docs/INTENT_OUTCOME_STEWARDSHIP.md)
- [Evaluation](docs/EVALUATION.md) and [non-functional requirements](docs/NFRS.md)
- [Roadmap](docs/ROADMAP.md) and [architecture decisions](docs/adr/)

Licensed under [Apache 2.0](LICENSE).
