# Integration provenance and verification

This source integration is based on Release Steward commit
5f8fa979ede9697f1a6364347cc464393b94024c. It retains the independently audited
standalone Analyst V2 procedure with frozen digest
fc95874aa27f71023d0c9f2a75eb0d0cd9c5faf5e4e09bc0b1096d0cf7db3fa9.

The integrated example imports the repository SDK, not the standalone vendored
cd4ecde33659f0403d8920e96f1c17837c45c5ea snapshot. Between that snapshot and the
integration base, SDK changes are confined to work/models.py (numeric normalization
and optional work occurrence identity). This integration adds no SDK changes.

Adaptations: namespaced example module filenames/imports, repository test discovery,
Ruff formatting/import order/UTC constant, and trace provenance fields. The trace
now calls the old SDK identifier original_frozen_sdk_commit and labels its current
SDK source as the repository/installed import. Do not interpret the old provenance
identifier as the integrated checkout.

AST comparison after removing imports and normalizing timezone.utc to UTC finds
no procedure changes in domain, fixtures or replay. All runtime functions match
under the same comparison except run, whose only change is report provenance fields.
No policy, arithmetic, timer, budget, planner or capability behavior was changed.

Verification on the integration tree:
- make check:254 tests, six explicit skips; Ruff pass; mypy86 source files pass;
  compileall pass.
- Analyst CLI:all eight exposed V2 cases executed; two revised positives and six
  abstentions, no corpus failures.
- Release Steward CLI:four closed cases and one intended active case; replay equal
  in all five, with actual local output artifacts.

Original independent Analyst V2 outcomes remain fifteen fresh cases:six useful
outputs and nine justified abstentions, plus a separate safe-but-missed second-scan
race. These are standalone audit results; the integration checks are separately
identified reproduction, not fifteen newly independent cases.
