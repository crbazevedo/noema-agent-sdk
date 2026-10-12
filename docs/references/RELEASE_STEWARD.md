# Release Steward: work graphs, recovery and verified local packages

This runnable reference uses real public Noema work coordination and agent APIs.
A deterministic `FakePlanner` proposes prepare → independently inspect → package.
`PlanValidator` admits the graph. `ReadyFrontier`, seeded worker matching, presence
expiry, fenced leases and replayed canonical completions control legal work.
Separate `AutonomousAgent` instances invoke typed capabilities under an explicit
local-effect policy. Work ownership is never treated as effect authorization.

The useful output is an actual local ZIP with prepared inputs, the separately
assigned worker's inspection receipt, and a revision/graph manifest. The package
is then reopened and checked against current revision, expected features, input
hash, graph identity and distinct worker assignments before commitment closure.
Input verification and final package readback are two separate phases.

## Run offline

From the source repository (Python 3.11+, no paid model or external account):

    PYTHONPATH=src python examples/references/release_steward.py --output release-traces.json --artifacts release-artifacts

Choose a new/empty artifact directory: prior evidence is never overwritten.
The JSON contains canonical events, admitted graphs, physical effects, source
hashes, current revision and replay equivalence. Replay is read-only; it does not
invoke capabilities. The reference uses the existing SDK SQLite event store.

## Public development cases

- R1: current input prepared, independent worker inspects it, local package built
  and reopened before completion.
- R2: builder holds a lease and disappears; logical time expires it, reconstructed
  coordinator recovers from canonical history, stale completion and stale dispatch
  are rejected, replacement uses a higher fencing token.
- R3: a changed constraint invalidates the admitted graph after input preparation.
  Empty old frontier precedes a new graph version; only current revision packages.
- R4: expired verifier presence and stale source coverage block progress; refreshed
  presence/evidence permit continuation.
- R5: no eligible independent verifier leaves work incomplete and produces no
  package; a builder cannot approve its own completed preparation.

These are development cases, not a claim of unseen-domain generalization. Fresh
independent perturbations and their exact source hashes are reported separately.

## Layer attribution and limits

SDK primitives provide graph validation, readiness, matching, identity-separated
verification, lease recovery, event replay, attention, and action-policy checks.
The application supplies the three-node graph, local file capabilities, physical
readback checks, effect/work bridge, logical source coverage and external stimuli.
Worker skill scores are seeded, not learned; identities are separate local agent
instances, not independent model judgments. No LLM, endogenous cognition, real
release deployment or durable timer is claimed in this reference.

Every capability checks current work/graph/revision/permission at admission and
again before local writing. Tests establish rejected stale dispatch and rejected
stale completion under serialized stimuli; file I/O and canonical events are not
one atomic transaction. This does not revoke a write already in progress under
arbitrary concurrent invalidation, and no exactly-once crash guarantee follows.
The recovery example reconstructs a coordinator from history, not a killed process.

An integration regression fixed alongside this reference normalizes numeric
`CompetenceEstimate.create` inputs before content-addressing. Integers such as 1
now round-trip like 1.0; existing valid float IDs stay unchanged. Historical bad
integer-hashed records are not silently migrated and may still be unreadable.
Any recovery of such records would require a separate explicit audited migration.

## V2: real tested software, and explicit presence occurrences

The first frozen version packaged metadata only. It is retained with its 8/9
fresh-case result: a packager returning within the same logical tick was wrongly
collapsed into an earlier identical presence event and missed a useful outcome.
That failure is not relabeled a pass.

V2 produces a runnable standard-library CSV transform module, input fixture and
explicit specification. It strips ID whitespace and scales decimal amounts by a
declared finite factor. This is a narrow template-backed reference capability,
not general autonomous software development. A separately assigned worker runs
the actual module in isolated-mode Python subprocesses against the declared
fixture and a second probe, compares actual stdout with expected rows, and records
exit status, observed rows and hashes. Packaging refuses changed tested bytes.
The final ZIP includes transform.py, fixture.csv, spec.json, test/verification
report and a manifest binding every member. Run it after extraction with:

    python transform.py < fixture.csv

Constraint revisions can change the declared factor/fixture; old admitted graphs
are invalidated and only a newly prepared, tested version may package. Final
readback checks every packaged file hash against its manifest in addition to
worker separation and current graph/revision. It does not deploy anything.

Presence observations now optionally carry an explicit observation_id. New
observations in the reference receive distinct IDs even when values and logical
timestamps repeat; redelivery of the exact same source occurrence stays
idempotent. Reusing one observation ID for conflicting payloads is rejected by
DurableWorkCoordinator's canonical event conflict check. Legacy payloads omitting
that field retain their exact old IDs and semantics. This is source-occurrence
identity, not a synthetic timestamp increment.

The verifier is independent by assigned worker/process. Its expected-row logic
uses the same declared Decimal formula; this is not an independently implemented
algorithm oracle. The reference tests wrong program output and changed bytes
after successful tests. Hash checks bind the serialized scenario's tested bytes;
they do not establish safety against arbitrary concurrent file mutation.

V2 fresh audit exposed two false closures: a fixture or spec changed before
verification was hashed into the receipt even though tests used in-memory inputs.
The revised verifier reads the actual prepared fixture/spec, rejects any mismatch
with the accepted current revision/contract, executes the actual fixture, and
binds the receipt to that tested byte snapshot. Both exposed cases are regression
tests; they are not counted as fresh validation of the repair.

## Bounded decimal contract

An additional precision probe after the ten-case V3 audit exposed Decimal's
28-digit default rounding: a 29-digit input with factor 1 was wrongly closed.
That failure is preserved separately; ten passing cases did not establish full
numeric correctness. The revised application and packaged program both enforce:
finite numbers, at most 18 coefficient digits, decimal exponent -6 through +6,
at most 64 characters per numeric value, exact id/amount CSV columns, 128-character
identifiers, 1,000 rows and 256 KiB input. Multiplication uses a local 40-digit
context, sufficient for the product of two admitted 18-digit coefficients.
Unsupported values are explicitly rejected. Independent Fraction tests cover
valid boundary products and rejection of the exposed 29-digit example.
