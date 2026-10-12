# Measured lifecycle development, 2026-10-12

## What this contribution changes

A runnable application composes Noema's real embedded kernel, SQLite event store,
situation projection, autonomous agent/controller, typed capabilities, attention,
policy and scheduler. It does useful synthetic work: prepare a current
source-backed brief, replan after changed content, use an alternative source,
deliver when allowed, and close only after verification. A second experimental
application composes multiple evidence requirements and an effect-bound observed
postcondition through declarative field selectors. The latter is application
procedure, not a new canonical SDK contract or production equipment controller.

The branch is stacked on PR2 commit 471a279 (attempt-time policy revalidation and
recovery provenance). No merge, deployment, release, paid model, or real-world
external effect is part of this work.

## Evidence progression

1. **Brief lifecycle public development:** seven cases, six legitimate verified
   completions and one safe cancellation. Original metric/contract defects are
   retained in compressed development runs. Frozen source: d50a90b.
2. **Independent frozen brief holdout:** fourteen newly authored cases. SDK and
   competent actual native LangGraph both pass all fourteen, with eleven useful
   completions and three safe non-completions. This is parity. Native cached
   authority is an ablation, not the competent baseline.
3. **Strict alias-only domain transfer:** independent equipment-release domain
   requires inspection AND calibration plus an independent functional test.
   Both original systems fail all three cases: two unsafe releases and three
   premature closures. The old single-source metrics failed to detect the new
   requirement. Preserve this negative result. Frozen mapping: f8ae3e3.
4. **Bounded procedural repair:** shared generic conjunction and postcondition
   interpreter, declarative selectors, explicit effect-reference report schema,
   and trusted synthetic arrival ordering. Adds 200 shared procedural lines;
   the SDK runner adds five module-injection lines. Costs are shared by both
   systems. The three exposed failed cases pass only as development regressions.
   Frozen source: 34ffb63. Fresh independent results are in the associated audit.

The native comparator uses real LangGraph 1.2.14 and checkpoint-sqlite 3.1.1.
Both receive the same domain data, planner, policy, provider and commands. This
is a total-system mechanics comparison, not an incremental-layer estimate of
Noema on an otherwise identical native runtime. No advantage is inferred from
tied outcomes. Native restarts a process for each command; SDK recreates runtime
instances only on declared restart commands, so timing rankings are invalid.

## Reproduce

Install the repository dev extras, then from its root:

    PYTHONPATH=src:examples python examples/commitment_lifecycle.py --output brief-results.json
    PYTHONPATH=src:examples python examples/declarative_transfer.py --mapping research/declarative_transfer/equipment_mapping_v2.json --scenarios research/declarative_transfer/v2-development-cases.json --domain-module compositional_lifecycle_domain --output transfer-results.json
    make check
    make build

The public transfer command uses exposed development cases, not independent
holdout. Audit bundles contain frozen independent inputs, physical/prefix
checkers, and raw results. Compressed JSON evidence can be read with gzip -dc.

## Claims that remain unsupported

- General intelligence, production chief-of-staff usefulness, or field efficacy
- Declaration-only cross-domain transfer: the initial attempt failed
- Lower human effort, hours saved, or lower maintenance cost
- Noema superiority over a competent native application
- Durable timer service, abrupt crash atomicity, distributed exactly-once effect
- Receipt existence proving the real functional test actually happened

Providers enforce fingerprint idempotence; physical duplicate zero is partly
structural. Repeated invocation counts are reported separately. Logical deadlines
and per-source feasibility ceilings are domain facts, not measured real time or
consumed money. Trusted synthetic observation provenance is not real connector
security. The latest observed postcondition replaces prior reports; closure is
terminal, not perpetual post-completion tracking.

## Highest-information next experiment

Keep V2 procedure frozen, independently specify a third domain genuinely covered
by its conjunctive evidence/effect-bound postcondition vocabulary, and allow only
declarative mappings. Give the same task to the competent native arm. Count
additional semantics, data and procedural edits separately and preserve any
unsupported requirement as a transfer failure. If the outcome is parity, retain
it. A separate matched-process experiment is needed for runtime overhead; a real
human implementation study is needed for engineering-effort claims.
