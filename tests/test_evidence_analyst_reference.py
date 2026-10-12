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
