import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "references"))
import hashlib
import tempfile
import unittest
from pathlib import Path

from evidence_analyst import run_scenario
from evidence_analyst_domain import parse, reconcile
from evidence_analyst_fixtures import public_scenarios
from evidence_analyst_replay import project


class DomainTests(unittest.TestCase):
    def test_duplicate_header_rejected(self):
        data = b"event_id,region,occurred_at,ingested_at,amount,amount\ne1,N,2026-01-01T00:00:00Z,2026-01-01T01:00:00Z,1,2\n"  # noqa: E501 - preserve frozen fixture/event text
        with self.assertRaises(ValueError):
            parse(data, "a.csv")

    def test_equivalent_dates_and_decimal_formats_not_conflict(self):
        a = "event_id,region,occurred_at,ingested_at,amount\nx,N,2026-01-01T01:00:00+01:00,2026-01-01T02:00:00+01:00,10.0\n"  # noqa: E501 - preserve frozen fixture/event text
        b = (
            a.replace("01:00:00+01:00", "00:00:00Z")
            .replace("02:00:00+01:00", "01:00:00Z")
            .replace(",10.0\n", ",10\n")
        )
        r = reconcile(
            {"z.csv": a.encode(), "a.csv": b.encode()},
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-02T00:00:00Z",
            region="N",
            bases={"z.csv": "occurred_at", "a.csv": "ingested_at"},
        )
        self.assertEqual(r["status"], "reconciled")
        self.assertEqual(r["metrics"]["unresolved_ids"], [])


class ReferenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            for case in public_scenarios():
                with self.subTest(case=case["name"]):
                    result = await run_scenario(case, Path(directory) / case["name"])
                    self.assertEqual(result["bus_errors"], [])
                    m = result["metrics"]
                    self.assertLessEqual(m["source_reads_used"], case["source_read_budget"])
                    self.assertLessEqual(m["capability_invocations"], 1)
                    self.assertLessEqual(m["sdk_selected_activities"], 1)
                    marker = result["current_artifact"]
                    replayed = project(result["events"])
                    self.assertEqual(replayed["current_artifact"], marker)
                    self.assertEqual(replayed["source_reads"], m["source_reads_used"])
                    self.assertEqual(replayed["goal_revision"], result["current_goal_revision"])
                    if case["name"] in {"nominal", "repeat_scan", "honest_partial"}:
                        self.assertIsNotNone(marker)
                        for artifact in marker["artifacts"]:
                            data = (Path(directory) / case["name"] / artifact["path"]).read_bytes()
                            self.assertEqual(hashlib.sha256(data).hexdigest(), artifact["sha256"])
                        self.assertEqual(m["source_reads_used"], 4)
                        self.assertGreaterEqual(result["real_wake_delay_seconds"], 0.04)
                        types = [e["type"] for e in result["events"]]
                        ordered = [
                            "reference.timer_fired",
                            "endogenous.scan_requested",
                            "endogenous.inquiry_recorded",
                            "endogenous.agenda_selected",
                            "reference.bridge_admitted",
                            "action.started",
                            "reference.source_read",
                            "reference.artifacts_staged",
                            "reference.artifact_readback_verified",
                            "reference.current_artifact_published",
                        ]
                        self.assertEqual(
                            sorted(types.index(t) for t in ordered),
                            [types.index(t) for t in ordered],
                        )
                        if case["name"] == "honest_partial":
                            self.assertEqual(marker["status"], "partial")
                            self.assertFalse(marker["goal_fulfilled"])
                            self.assertEqual(result["commitment_status"], "active")
                        else:
                            self.assertEqual(marker["metrics"]["a_total"], "110")
                            self.assertEqual(marker["metrics"]["b_total"], "120")
                            self.assertEqual(marker["metrics"]["late_current_ids"], ["e3"])
                            self.assertEqual(marker["metrics"]["carry_in_ids"], ["e0"])
                            self.assertEqual(result["commitment_status"], "closed")
                    elif case["name"] == "event_while_scan_queued":
                        if marker:
                            self.assertEqual(marker["metrics"]["a_total"], "110")
                        # An unrelated concurrent append can reject the strict cut.
                        # Safe incompleteness is recorded, not called useful success.
                    else:
                        self.assertIsNone(marker)
                    if case["name"] in {"cancel_before_wake", "budget_exhausted"}:
                        self.assertEqual(m["source_reads_used"], 0)
                    if case["name"] == "failure_after_stage":
                        self.assertTrue(
                            list(
                                (Path(directory) / case["name"] / "artifacts/staging").rglob(
                                    "note.md"
                                )
                            )
                        )


if __name__ == "__main__":
    unittest.main(verbosity=2)


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def run_probe(self, mode, **limits):
        from evidence_analyst import EvidenceAnalyst
        from evidence_analyst_fixtures import public_scenario

        class Probe(EvidenceAnalyst):
            async def setup(self):
                await super().setup()
                original = self.worker._append_epoch_start
                self.attempts = 0

                async def interfere(epoch):
                    self.attempts += 1
                    if mode == "repeated" or self.attempts == 1:
                        await self.emit("test.concurrent_observation", {"attempt": self.attempts})
                        if mode == "cancel":
                            from noema import GoalStatus

                            await self.record_goal(GoalStatus.CANCELLED, "test cancellation")
                        elif mode == "relevant":
                            for name in self.paths:
                                self.paths[name].write_text(
                                    self.paths[name].read_text().replace(",10\n", ",11\n")
                                )
                                await self.intervene(
                                    {
                                        "phase": "while_scan_queued",
                                        "op": "new_source_claim",
                                        "file": name,
                                        "claims": {
                                            "period_amount": str(
                                                int(self.claims[name]["period_amount"]) + 1
                                            )
                                        },
                                    }
                                )
                        elif mode == "revoke":
                            self.authorized = False
                    return await original(epoch)

                self.worker._append_epoch_start = interfere

        with tempfile.TemporaryDirectory() as directory:
            case = public_scenario("recovery_" + mode)
            case.update(limits)
            app = Probe(case, Path(directory) / case["name"])
            report = await app.run()
            self.assertEqual(report["bus_errors"], [])
            return report

    async def test_one_lost_cut_recovers(self):
        report = await self.run_probe("once")
        self.assertEqual(report["metrics"]["scans"], 2)
        self.assertEqual(report["metrics"]["scan_retries"], 1)
        self.assertEqual(report["metrics"]["source_reads_used"], 4)
        self.assertEqual(report["metrics"]["preparations_reserved"], 1)
        self.assertEqual(report["metrics"]["current_publications"], 1)
        recovered = next(
            e["payload"] for e in report["events"] if e["type"] == "reference.scan_recovered"
        )
        self.assertGreater(recovered["causal_cursor"], recovered["reservation_sequence"])

    async def test_relevant_claim_and_bytes_recomputed(self):
        report = await self.run_probe("relevant")
        self.assertEqual(report["current_artifact"]["metrics"]["a_total"], "111")
        self.assertEqual(report["current_artifact"]["metrics"]["b_total"], "121")
        self.assertEqual(report["metrics"]["scans"], 2)
        claims = [e["sequence"] for e in report["events"] if e["type"] == "reference.source_claim"]
        recovered = next(
            e["payload"] for e in report["events"] if e["type"] == "reference.scan_recovered"
        )
        self.assertGreater(recovered["causal_cursor"], max(claims))
        new_assertions = {
            "event:" + e["id"]
            for e in report["events"]
            if e["type"] == "memory.assertion_recorded"
            and e["source"] == "reference:new-reported-memory"
        }
        bridge = next(
            e["payload"] for e in report["events"] if e["type"] == "reference.bridge_admitted"
        )
        inquiry = next(
            e["payload"]["inquiry"]
            for e in report["events"]
            if e["type"] == "endogenous.inquiry_recorded"
            and e["payload"]["inquiry"]["inquiry_id"] == bridge["inquiry_id"]
        )
        self.assertTrue(new_assertions.intersection(inquiry["evidence_refs"]))

    async def test_interference_and_stop_gates(self):
        for mode, limits, attempts, reason in [
            ("repeated", {}, 3, "per-wake retry ceiling"),
            ("repeated", {"scan_attempt_ceiling": 2}, 2, "lifetime scan attempt"),
            ("once", {"scan_retry_limit": 0}, 1, "per-wake retry ceiling"),
            ("cancel", {}, 1, "canonical goal is not active"),
            ("revoke", {}, 1, "permission absent"),
            ("once", {"source_read_budget": 3}, 1, "read reservation insufficient"),
        ]:
            with self.subTest(mode=mode, limits=limits):
                report = await self.run_probe(mode, **limits)
                self.assertIsNone(report["current_artifact"])
                self.assertEqual(report["metrics"]["scans"], attempts)
                self.assertEqual(report["metrics"]["source_reads_used"], 0)
                self.assertEqual(report["metrics"]["scan_compute_units_reserved"], attempts)
                self.assertEqual(
                    report["metrics"]["scan_wall_time_seconds_reserved"], 60 * attempts
                )
                stops = [
                    e["payload"]["reason"]
                    for e in report["events"]
                    if e["type"] == "reference.scan_recovery_stopped"
                ]
                self.assertTrue(any(reason in stop for stop in stops), stops)
