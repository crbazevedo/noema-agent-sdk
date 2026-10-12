# Evidence Analyst V2: bounded revised-wake continuity

This deterministic local tutorial uses actual Noema memory, intent, endogenous shadow selection, scheduler and capability APIs. A reported contradiction leads to a real timer wake, a selected inquiry and an explicit application bridge that reads two synthetic CSVs and produces a verified factual note. V2 can replace a supported goal scope and its wake after an explicit renewed local grant, without resetting lifetime budgets.

## Reproduce

Use the repository development environment (Python3.11+). This integrated example imports the repository SDK; it does not vendor an SDK copy. The original independently audited standalone reference used cd4ecde33659f0403d8920e96f1c17837c45c5ea. Integration records its own checkout and tests; no new SDK core change is introduced here. No network, model calls or real-world effects.

```sh
PYTHONPATH=src python examples/references/evidence_analyst.py --scenarios examples/references/evidence_analyst_cases.json --output runs/revisions
PYTHONPATH=src python examples/references/evidence_analyst.py --public-all --output runs/regression
PYTHONPATH=src python -m unittest discover -s tests -p "test_evidence_analyst*.py" -v
python examples/references/evidence_analyst_replay.py runs/revisions/revised_after_reads/trace.json --through 70
```

Use a fresh output directory. Public input scenarios are ordinary JSON; the controller never branches on their names. Custom arrays use --scenarios. Actual note.md, derived.csv and result.json are under each scenario's artifacts/staging directory. Only artifacts/current.json marks accepted current output. Readback hashes and relative paths also appear in trace.json.

## Demonstrated development behavior

An initial North scope gives110/120. A supported revision expands to all regions, including a supplied South record15, and produces125/135 after a replacement real wake. When revision arrives after the first two source reads, the old result is discarded. The replacement consumes four additional reads: six actual reads, eight reserved reads, two preparations and two actual SDK scans in total. No budget is refunded. Revisions without renewed permission or enough lifetime reservation budget do not publish.

## Boundaries

EndogenousShadowWorker selects shadow activities; the separately logged application bridge dispatches local work. MemoryProjector is explicitly drained and stopped around each strict scan admission interval. Changed reported claims are not continuously projected during that quiet interval; a generation fence prevents old preparation promotion. This is an application workaround, not a production concurrency or durable-timer solution.

A supported revision is a complete report-scope update with updated reported claims, explicit renewed permission and due/deadline. Unknown revisions escalate. File replacement or changed claims alone still invalidate work without scheduling replacement and may miss feasible useful outcomes. Only declared before_wake/after_source_reads/while_scan_queued interventions are tested. Arbitrary concurrent external filesystem writes are not transactional.

SDK cognition estimates are not measured money/CPU. Actual source reads, reservations and output verification I/O are counted separately. No human-time conclusion follows from source size. Replay only projects events and never executes tools.

V1 is preserved separately. A supplemental independent V1 case exposed rounded large-Decimal totals and false closure. V2 explicitly bounds numeric inputs and uses a fixed sufficient precision. See EVIDENCE_ANALYST_PROTOCOL.md; do not extrapolate accepted arithmetic to unbounded numbers. Independent V2 audit follows source freeze.
