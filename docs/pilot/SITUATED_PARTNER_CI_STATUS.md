# Situated Partner CI and consumer-conformance status

Status: **review candidate; not merged**

Frozen contract source:
`2907b1fb6d9fac0d613a8574f6dea4bfa11c6ec8`

The schema, Project Meridian fixture, integration document, conformance example,
tests, and lock recorded by `8ba0aed8902a65d6df1c396a742392ba22a25911`
remain byte-for-byte unchanged. This descendant changes CI dependency selection
and adds a consumer test corpus; it does not change the contract revision or
implement ADR 0014 or ADR 0015.

## Hosted evidence before the parity correction

- Candidate run `33991573023`: Python 3.11, 3.12, and 3.13 tests passed;
  distributed PostgreSQL/NATS acceptance passed; the aggregate run was red.
- Accepted-main run `33928408668`: the same jobs passed and the aggregate run
  was also red.
- In both runs, the quality job installed only `.[dev]` and strict mypy failed
  on the same ten imports from the optional OpenTelemetry, NATS, PostgreSQL,
  and OpenAI adapters. The baseline failure is evidence of the defect, not a
  green result.

The quality job now installs `.[dev,all]`, matching the modules it checks. It
still runs Ruff, strict mypy, and the package build. Cross-version test jobs
continue to install only `.[dev]`, preserving proof that optional adapters are
not core runtime dependencies.

Local clean-room parity for this descendant used Python 3.13 with `.[dev,all]`
for Ruff, strict mypy over all 86 SDK source files, and build. Separate Python
3.11 and 3.12 environments installed only `.[dev]`; each passed 221 tests and
compilation. The unchanged PostgreSQL concurrency and distributed NATS
acceptance paths also passed locally.

## Shared consumer corpus

[`situated-partner-consumer-corpus-v1.json`](fixtures/situated-partner-consumer-corpus-v1.json)
is a bounded positive/negative corpus for SDK and Companion consumers. Its
assertions are deliberately separated:

1. **Shape validity** means strict JSON plus Draft 2020-12 schema validity.
2. **Referential/relational validity** means cross-field identities, finite
   budgets and usage, budget ceilings, and playback ranges are coherent.
3. **Permission/currentness** means referenced admissions actually resolve in
   current canonical SDK governance state and the envelope is neither stale,
   expired, cancelled, nor superseded.

A schema-valid opaque reference proves syntax only. A matching fingerprint
proves payload equality only. Neither proves that an access or disclosure
decision was canonically admitted. The corpus's `frozen_synthetic_placeholders`
profile is therefore expected to fail permission resolution. The positive
permission case substitutes records created through
`InformationGovernanceAdmission` and resolved through
`InformationGovernanceProjection`; no new registry is introduced.
