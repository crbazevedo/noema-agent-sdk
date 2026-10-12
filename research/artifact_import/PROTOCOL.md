# Wave D: actual local artifact import, scoped before implementation

## Objective

Test operational transfer using unchanged V2 controller/policy semantics and a
new explicitly counted capability/provider adapter. The useful outcome is an
actual isolated CSV artifact, followed by an independent read-back row-count and
SHA-256 observation. Renaming an evidence packet is insufficient.

## Procedure and data boundaries

The new module must re-export V2 choose_action and deny_action without edits.
It may subclass World for actual file operations and physical verification, and
supply a physical-output evaluator. Both frameworks use identical module bytes;
native adapter/controller plumbing remains unchanged. A serializable temporary
artifact_root created per provider isolates cases and arms and persists across
orderly restarts. All inputs are synthetic CSV strings, never user files.

Declarative evidence contract requires schema, provenance/license, and
source-version classes, with the same current revision/verdict/expiry semantics
as V2. artifact_contract declares operation=import_csv, expected columns,
expected row count and expected exact-byte SHA-256. source_csv supplies bytes.
The new capability validates UTF-8 CSV shape, declared header and checksum before
writing; this domain-specific procedure is charged to both arms. It does not
claim to validate the truth of external licensing assertions.

The single-file effect writes exact source bytes to an isolated staged path and
renames it to a deterministic per-effect file. Provider ledger records path,
content digest, and effect identity; evidence packets are not the output itself.
No claim of atomic transaction across file and event/checkpoint persistence or
crash durability is made. Clean reconstruction only, as in prior waves.

Verification separately opens the actual artifact and computes current bytes,
rows, header and SHA-256. It creates an observed postcondition referencing the
exact effect; neither delivery receipt nor source claim alone may fulfill the
goal. For repeatable external perturbations, an explicit fixture-only fault can
replace/delete an already-created artifact by effect ordinal (never a supplied
filesystem path). This mutation is environment simulation, not agent work.
Independent audit reads the actual produced bytes and prefix closure evidence,
not the provider's own pass boolean. Package output bytes and a path manifest.

## Explicit unsupported requirement

Any operation other than the supported single CSV import is rejected before a
write with a visible unsupported-operation result. In particular a two-resource
transaction requiring partial-success compensation is unsupported. No partial
second resource or automatic compensating action may be attempted. A negative
case must prove zero artifacts/effects and an explicit unsupported observation;
merely silently doing nothing is not sufficient.

## Measurement, freeze and stop

Count shared provider/validator/verifier code, declarations, tests, evaluator and
framework plumbing separately. Frozen controller semantic bytes must remain
identical. These counts are artifact surface, not human effort. Preserve failed
runs. Public development includes successful import, a blocked prerequisite,
and unsupported operation. Freeze source/data before independent new cases.

Independent gates: actual bytes/header/row count/hash match required outcome;
all legitimate positive cases complete; no effect under revoked/invalid evidence
or unsupported requirement; tampered/missing artifact cannot falsely close;
restart retains effect identity; native receives identical provider and data.
Ablations, if used, must be explicitly separated from competent baseline.

Stop after this bounded fresh holdout, full quality checks and portable evidence
have terminal results. Do not grow into transactions, general ETL, real licensing
verification, arbitrary filesystem access or model reasoning during this wave.

Prefreeze review clarifications:
- Prepared output binds the declared artifact contract and actual source digest.
  The source-version evidence must itself contain the matching digest through
  declared class/field selectors. Binding is rechecked before effect and closure.
- If artifact contract changes without updating evidence/revision, verification
  refuses closure. The frozen planner may keep checking the old receipt until
  current evidence changes; no hidden automatic replanning is claimed.
- Receipt and ledger records are canonically relinked after JSON load so actual
  readback evidence is preserved identically across both restart schedules.
- Returned facts expose both artifact_readback and the effect-bound observed
  postcondition, including measurement and provider arrival sequence. The latter
  is synthetic provider provenance, distinct from canonical event sequence.
- source_read_calls/source_bytes_read count in-memory source-byte validations.
  readback_calls/readback_bytes_read count actual filesystem reopen attempts and
  bytes. External fixture tampering is tracked separately from agent writes.
