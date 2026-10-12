# Measured commitment lifecycle: protocol v1

## Goal and scope

Wave A is the separate PR2 attempt-policy and recovery-provenance correction.
Wave B composes the **real embedded Noema SDK** into a bounded useful application:
prepare a source-backed brief, adapt it to changed evidence, use an available
backup source, deliver within current authority and a logical deadline, and
verify a provider receipt before closing a commitment. It uses the canonical
situation projection, SQLite event store, autonomous agent, controller, typed
capability registry, attention allocation, policy, and timer scheduler. It does
not exercise every SDK subsystem. All content and providers are synthetic.

The controller is a shared inspectable deterministic policy, not an LLM and not
an intelligence demonstration. Framework orchestration is the experimental
variable; neither side receives privileged scenario labels or future inputs.

Wave C compares actual native LangGraph to standalone Noema as **total systems**
with equal domain logic, information, and provider. It does not estimate the
incremental effect of adding Noema to LangGraph. Wave D publishes bounded claims
and reproducible evidence only. Passing these waves does not establish a
world-class chief of staff, field usefulness, or hours saved.

## Frozen task semantics

One command is an update, timer wake, or restart. Each wake permits one selected
action; updates do not themselves spend a reasoning/action cycle. The scheduler
is real but process-local: this is **not durable timer recovery**. Restarts
close runtime instances and reconstruct fresh objects from a SQLite event log.
Noema restart evidence is same-process instance reconstruction, not kill -9.
The provider is separately serialized across restarts. Native process tests,
if present, are reported separately and not treated as matched crash evidence.

Source selection minimizes per-source cost among available sources within a
**per-source feasibility ceiling**, not a consumable budget. Logical now and
deadline are public facts, not wall-clock performance. Delivery must use current
revision/content within that ceiling and deadline, with permission still active.
A before_effect update occurs after planning and before invocation policy.
The provider does not enforce these application constraints, allowing physical
unsafe effects to be measured. It owns idempotence keyed by briefing fingerprint;
zero physical duplicates alone is therefore not an orchestration achievement.
Repeated delivery invocations are reported separately.

A changed revision before verification requires preparing, delivering, and
verifying the new revision. A closed commitment is terminal: opening a new goal
after closure is outside this protocol. A cancelled commitment remains open but
inactive in the application; this demo does not claim a canonical cancellation
transition. Provider observation failure leaves the commitment unfulfilled and
eligible for a later wake. No retry sleeps, paid models, private data or external
effects are used.

## Gates, metrics, and stopping criteria

Before independent holdout, freeze domain, adapter, tests, and this protocol at a
Git commit and hash. Do not inspect held-out scenarios until then. Preserve
first-pass holdout results; repairs must be labeled development, not retested
holdout generalization.

Public gate: every positive scenario delivers its expected revision and closes
only after provider verification; negative cancellation has no effect. All
scenarios require zero unsafe effects and false closures. Changed-content and
backup-source scenarios must actually deliver those contents. Extra terminal
wakes must not duplicate delivery calls. Count tool calls, preparations, timer
wakes, decisions, persisted events, effect records, denials and restarts; none
is real human effort or real-world time saved.

Ablations: disable current execution policy (must expose revocation failure),
and disable replay (must lose a legitimate restarted outcome). Native fresh
policy is the competent comparator; a cached-policy native arm is an ablation,
not the native baseline. Record ties honestly. Do not add ad hoc features to win.

Stop this wave after public gates, aggregate lint/type/test checks, independent
holdout, and review reach a terminal reported outcome. Any uncovered capability
or ecological gap becomes a specific next-wave proposal, not an unbounded claim.

## Reproduce

From repository root with dev extras installed:

    PYTHONPATH=src:examples python examples/commitment_lifecycle.py --output results.json
    PYTHONPATH=src:examples python -m unittest discover -s tests -p 'test_commitment_lifecycle_example.py' -v
    make check

Initial development run 001 is retained. It had successful public end states but
an incorrect denial counter (searched action.denied, while runtime emits
action.abandoned/decision.denied), no positive-outcome metric, and inadequate
revision/closure and budget semantics. Run 002 followed metric/domain corrections;
subsequent frozen results supersede both. These are development iterations, not
independent experiments. Full event IDs/timestamps vary; semantic metrics should
be stable. The baseline is PR2 471a279, stacked on main 621be5a.

Closure freshness clarification: before closure, the delivered brief must match
both current revision and current available source content/fingerprint, even
when a source changes without a revision bump. Permission is checked at delivery;
revocation alone does not undo an already valid delivery. Verification is a read.

Development event JSON artifacts are gzip-compressed; use gzip -dc to inspect.
Frozen source commit: d50a90b990f58215f99b2f7c291dcd00301f847a.
