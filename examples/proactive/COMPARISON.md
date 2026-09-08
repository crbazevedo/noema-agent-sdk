# Observed comparison: a semantic benefit, not a source-line win

The reference run uses Noema 0.6.2 at SDK source `621be5a`, Google ADK 2.8.0 and
LangGraph 1.2.11 on Python 3.12. Exact versions, source hashes and observations are
in [observed/comparison.json](observed/comparison.json). Reproduce with:

```bash
python -m examples.proactive.comparison --output /tmp/proactive-observations
python -m unittest tests.test_proactive_examples -v
```

## Matched behavior

| Lesson | Noema calls / notices | ADK calls / notices | LangGraph calls / notices |
|---|---:|---:|---:|
| Anticipate | 1 / 1 | 1 / 1 | 1 / 1 |
| Investigate | 4 / 1 | 4 / 1 | 4 / 1 |
| Reconsider | 7 / 1 | 7 / 1 | 7 / 1 |

The call sequence, exact notice content and final world state match. The tests
also exercise early/expired observations, pause, quiet windows, cancellation,
duplicate observations, unavailable notes, later reconsideration and backwards
clock rejection. A finite live clock runs without additional human messages.

All three implementations pass a separate-process persistence check after a
completed observation. No in-flight side-effect or durable scheduling advantage
is established by that check.

## Maintained code

Physical code lines exclude blank lines, comment-only lines and docstrings.
They include imports, signatures and multiline punctuation. AST statements are
also reported because formatting affects physical line counts. Neither metric
measures comprehension, maintenance effort or correctness on its own.

| Implementation | Adapter code lines | Adapter AST statements | Adapter + shared application lines |
|---|---:|---:|---:|
| Noema | 91 | 40 | 300 |
| ADK | 73 | 43 | 282 |
| LangGraph | 50 | 49 | 259 |

The shared application files are domain.py, lessons.py and live.py. They include
the complete policy, tools, scenarios, assertions and finite clock host. The
shared ranking helper is conservatively counted for all three even though Noema
uses its own allocator. This does not hide framework-specific orchestration in
an uncounted convenience library.

The report separately inventories comparison.py, restart_probe.py, notebooks.py
and package scaffolding. Tests, notebook cells, dependency configuration and the
CI workflow are also visible in the repository; they are reproduction/teaching
infrastructure, not included in the application-line total. Requirements and a
transitive environment snapshot are supplied. Noema-only execution has no extra
runtime dependencies; the comparison installs the other frameworks explicitly.

Noema has more physical adapter lines and fewer AST statements in these exact
implementations. This disagreement is a reason to avoid declaring a general
simplicity winner. The Noema initializer configures more explicit SDK concepts.
ADK's current Workflow API and LangGraph's StateGraph both express the small
deterministic workflow compactly.

## The observed Noema benefit

Noema generated domain records for proposal, authorization and successful action
without application-written lifecycle logging. Its authorization records contain
the effective authority, risk, typed intent and falsifiers; the test verifies
that authorization and success records have actual causal predecessors.

Inspect the raw evidence:

- [Noema medium trace](observed/noema-medium-trace.json): domain decision/action events.
- [ADK medium trace](observed/adk-medium-trace.json): session and workflow-node events.
- [LangGraph medium trace](observed/langgraph-medium-trace.json): emitted node state updates.

The last file is deliberately a state-update stream, not a complete inventory of
LangGraph checkpoint or observability features. ADK also records rich node/session
information. They can carry additional domain decisions through application state,
events or instrumentation. This experiment observes that Noema already supplies
a relevant shared vocabulary and its recording path; it does not claim the other
frameworks cannot implement equivalent semantics.

That concrete semantic benefit is the basis for including the independently
runnable equivalents. The comparison is published with its unfavorable Noema
line-count result, rather than using only a favorable metric.

## What remains unmeasured

- The shortest idiomatic implementation possible in each framework.
- Runtime latency, throughput, infrastructure cost or developer task completion time.
- LLM reasoning quality or token savings: every implementation makes zero model calls.
- Fully matched domain-audit profiles across all three frameworks.
- In-flight effect reconciliation, cross-worker authority races, missed-timer recovery
  and a reliable always-on personal-agent deployment.
- User helpfulness or interruption burden over days of real use.

The experimental scope is explicit deterministic proactivity on small synthetic
inputs. It supports a tutorial and a narrow architectural observation, not a
production framework ranking.

## Current framework references

ADK's [Workflow API](https://adk.dev/graphs/) supports deterministic function nodes;
the example uses that API rather than an unnecessarily elaborate custom agent.
Its [ambient agents](https://adk.dev/runtime/ambient-agents/) offer event-driven
activation, and [resumability](https://adk.dev/runtime/resume/) has additional
documented requirements. This experiment does not deploy those cloud triggers.

LangGraph's [graph API](https://docs.langchain.com/oss/python/langgraph/graph-api),
[persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and
[interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) provide
related building blocks. The example uses graph routing and a checkpoint backend;
it does not benchmark every persistence or interrupt mode.
