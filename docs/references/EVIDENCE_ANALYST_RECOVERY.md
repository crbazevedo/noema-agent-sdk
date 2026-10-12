# Bounded recovery of an unadmitted inquiry

This application-level extension retries **preselection only**. An endogenous SDK scan
can return `None` after a concurrent canonical append makes its strict causal cut stale.
The prior V2 reference safely stopped there, losing a feasible preparation. Its original
independent probe remains historical failure evidence, not a success credited to this change.

The V2 results/protocol documents describe the earlier frozen baseline. This document
supersedes only their preselection no-retry boundary; prior results are not reclassified.

## Contract and stopping gate

The application owns at most two retries per wake (10ms, then 20ms backoff) and four
scan attempts over its lifetime by default. `scan_retry_limit` accepts integers 0–8;
`scan_attempt_ceiling` accepts integers 0–32. Backoff is capped at 100ms. Every attempted
scan irreversibly reserves one compute unit, 60 seconds of SDK-estimated wall capacity,
and 0.2 attention units before calling the SDK. These are conservative reservations,
not CPU measurements, money, token counts, or observed latency. Trace elapsed time is
measured separately. `metrics.scans` counts charged attempts, including an attempt stopped
during memory catch-up before an SDK request. Count `endogenous.scan_requested` events
for actual SDK requests. No model or paid call is used.

All wakes share a lock and lifetime counters. Selected activity, preparation and source
read ceilings are still separate and never refunded. A revision grant does not reset
any counter. Before each retry and before accepting its selection, the application
reconstructs the canonical goal and checks active status, exact revision, existing
permission, original deadline and remaining preparation/read/activity capacity.
Cancellation, supersession, revocation, expired deadlines and exhausted budgets stop
explicitly. Repeated interference stops at the smaller applicable finite limit.

Same-goal relevant evidence is allowed to change. Before each retry, the application uses the public MemoryProjector start/stop catch-up
to derive real contradiction events from the available canonical prefix. Its checkpoint
is traced. Concurrent external appends remain enabled. The SDK then reconstructs memory
and obtains a fresh scan cut; the bridge captures the new evidence
generation and computation reads current source bytes. Contradictory assertions are not
deleted or overwritten. Evidence does not create a new permission or change the goal.
A supported explicit goal revision still needs the existing renewed authorization flow.

`None` does not expose a typed SDK rejection reason. The trace therefore says “no current
candidate or strict causal-cut admission lost”; it does not claim every retry diagnosed a
concurrency failure. Empty agendas can consume this same bounded retry allowance.
Returned retry selections must have an epoch cursor after their attempt reservation;
an older active-epoch selection is refused rather than relabeled fresh. SDK admission is
never bypassed. Already discarded preparations, partially admitted inquiry continuation,
process restart and durable timers remain outside this recovery contract.

## Reading a real structured trace

Run the public reference normally, or use the deterministic boundary probes in
`tests/test_evidence_analyst_reference.py`. The probes inject canonical events immediately
before real SDK epoch admission; they do not replace the SDK decision or its return value.
The relevant-evidence probe changes current bytes and reports, so successful recovery must
produce totals 111 and 121 instead of the old 110 and 120.

The actual event stream records:

1. `reference.scan_attempt_reserved` before `endogenous.scan_requested` captures a cut.
2. Concurrent canonical evidence, followed by `reference.scan_no_selection` on refusal.
3. `reference.scan_retry_scheduled`, its finite delay and retained deadline.
4. A second charged reservation, public projector catch-up and its recorded checkpoint,
   then a new actual SDK request/inquiry/selection.
5. `reference.scan_recovered` with actual selection, epoch, causal cursor and reservation
   sequence. The cursor must follow the reservation and the newly available evidence.
6. Normal bridge admission, source reads, hash revalidation, artifact readback and current
   publication, or an explicit `reference.scan_recovery_stopped`.

These are decision inputs, outcomes, provenance and costs, not hidden reasoning.
One-interference developer regression uses two scans, one selected activity, one preparation,
four reserved/actual source reads and one publication. Repeated interference uses three
scans and no reads or publications. Independent post-freeze findings are a separate cohort;
passing these developer cases alone is not evidence of general reliability.
