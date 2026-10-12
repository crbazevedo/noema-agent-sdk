# Alias-only cross-domain transfer, predeclared v1

Independent domain proposal: equipment return-to-service requires two independent
current evidence classes, inspection AND calibration, then an authorized release
and independent post-release functional-test confirmation. A cheap source in one
class cannot substitute for the other. Each class carries verdict, equipment
revision and valid-until time. Accessibility is not a passing verdict.

Freeze: reuse the exact lifecycle engine/domain at d50a90b (hashes recorded in
prior wave). The only permitted application mapping is equipment_mapping.json:
field aliases, display labels and explicit requirement metadata. The new mapper
copies aliases and preserves original facts; it cannot add conditional logic,
aggregate multiple sources, manufacture verdicts, or call tools. The JSON
requirements are deliberately not executable by the frozen engine. Success is
not assumed merely because vocabulary can be renamed.

Both Noema and native receive the same mapped commands, initial state, source
payloads, information, and inherited baseline policy. Independent author freezes
concrete scenarios only after this mapping/adapter freeze. The independent oracle
must inspect physical state at release and functional-test evidence at closure;
the inherited single-source receipt oracle is insufficient in this new domain.

Gates: no release without both current passing prerequisites; no closure without
causally later passing functional test; complete all legitimate positive cases
when requirements become satisfied. Preserve failures and exact effect records.
No edits after holdout. Report a declaration-only transfer failure if any
requirement needs procedural/model-evaluator changes, even if both systems fail.
Count new mapping data bytes/fields separately from adapter and evaluator code.
These are artifact change surface proxies, never human time or adaptation ease.

Stopping criterion: first frozen independent cases establish representability
success or a concrete gap. A repair becomes a separate development version and
requires fresh independent cases; do not rewrite failed evidence. New generic
conjunction and postcondition contracts must be justified by the observed gap,
not invented before measuring it.
