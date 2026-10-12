# Compositional evidence transfer v2

V1 independent alias-only transfer failed all three new domain cases: two releases
lacked jointly valid prerequisites; every case closed before a passing independent
functional test. The original single-source metrics missed the new-domain failure.
That result remains a transfer failure, not a successful zero-code generalization.

V2 changes application-level shared procedure, not canonical SDK semantics:
- generic conjunctive requirements over independently available source classes;
- declarative class/verdict/revision/expiry selectors and expected verdict;
- cheapest feasible eligible source per required class;
- joint current fingerprints at effect admission and at closure;
- a separate observed postcondition with declarative fact/verdict/revision fields.

No equipment identifier or special equipment control branch is embedded in code.
The new tests use different class/field names and non-boolean verdicts. The JSON
mapping inserts the same static evidence_contract fact for both runtimes. SDK
adds a domain-module injection parameter; native receives symmetric module
selection plumbing. Shared procedure additions must be charged to both arms.
This is explicitly a procedural repair; it does not retroactively satisfy V1's
strict declaration-only transfer criterion.

## Causality and contradiction semantics

The synthetic provider increments its trusted sequence on every external update
and invocation. It records each top-level fact's latest arrival sequence and
each effect's sequence, independently from any report's claimed date. A passing
postcondition must have arrived strictly after the exact receipt's effect and
match that effect's revision. A preloaded future-dated report cannot pass later
merely because time advanced. The latest observation replaces earlier values;
a later contradiction blocks closure. An earlier revision's success is ignored.
A receipt proves only that the effect happened, never that the postcondition
passed. Serialized provider state preserves these sequences across orderly
restarts. This is a synthetic provider's trusted provenance, not a proof that
all real connectors supply such guarantees.

Core Wave B limitations remain: one terminal commitment, process-local timers,
clean reconstruction, no provider transaction/crash atomicity claim, no learned
reasoning, no field efficacy, and no human effort estimate. Effects are local
synthetic records only. Conjunctive contracts currently require at least one
class; unsupported/absent contract produces no plan. Inputs are trusted typed
fixtures; comprehensive malformed-contract validation is outside this example.

## Freeze and completion

Public/development regressions are the three exposed V1 failures plus generic
unit tests for conjunction, preloaded future evidence, old revisions, later
contradiction, and persisted ordering. These cannot serve as new holdout.
Freeze module, mapper, adapters, config and tests before independent fresh
perturbation compositions. Both competent systems must receive identical data.
Pass gates: no unsafe release; no false closure; all specified legitimate
outcomes completed; physical evidence oracle independent of shared evaluator.

Stop this development cycle after the fresh independent V2 holdout and full
quality checks establish a reported terminal result. Any new defect is preserved
as a failed frozen result; further repair would require a newly numbered wave.
Structural code/data changes are reported as artifact counts, not saved hours.

Prefreeze review correction: arrival-after-effect and revision alone do not
identify the exact release when multiple releases share a revision. Independent
postcondition data must additionally name effect_index; the contract configures
that field name. The provider assigns an ordinal at each new physical effect,
and verification requires an exact match. Development copies of the exposed V1
cases therefore explicitly add effect_index=1 to reports; this schema addition
is counted and not hidden as unchanged-input success. The original V1 inputs
and failures are preserved. A late report about an older effect cannot close a
newer one even if revision and claimed timestamp match.

Reproduce the exposed development cases from repository root:

    PYTHONPATH=src:examples python examples/declarative_transfer.py --mapping research/declarative_transfer/equipment_mapping_v2.json --scenarios research/declarative_transfer/v2-development-cases.json --domain-module compositional_lifecycle_domain --output transfer-results.json

`post-effect observed outcome` is the precise evidence claim: trusted provider
arrival ordering plus explicit effect reference links the externally supplied
report to the effect. The simulator does not independently prove the real-world
functional test was physically executed; that depends on a trustworthy connector
in an actual deployment and remains unmeasured here.
