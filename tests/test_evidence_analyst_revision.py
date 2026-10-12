import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "references"))
import tempfile
import unittest
from decimal import Decimal, localcontext
from pathlib import Path

from evidence_analyst import run_scenario
from evidence_analyst_domain import parse, reconcile
from evidence_analyst_fixtures import csv_text, revised_scenarios


class NumericBoundsTests(unittest.TestCase):
    def test_bounded_aggregate_exact(self):
        rows = [
            [
                str(i),
                "North",
                "2026-10-02T00:00:00Z",
                "2026-10-02T01:00:00Z",
                "999999999999.9999",
            ]
            for i in range(10000)
        ]
        data = csv_text(rows).encode()
        with localcontext() as context:
            context.prec = 6
            result = reconcile(
                {"a.csv": data, "b.csv": data},
                window_start="2026-10-01T00:00:00Z",
                window_end="2026-10-04T00:00:00Z",
                region="North",
                bases={"a.csv": "occurred_at", "b.csv": "ingested_at"},
            )
        self.assertEqual(Decimal(result["metrics"]["a_total"]), Decimal("9999999999999999.0000"))
        self.assertEqual(Decimal(result["metrics"]["difference_a_minus_b"]), Decimal(0))
        with self.assertRaisesRegex(ValueError, "10000"):
            parse(csv_text(rows + [["extra", *rows[0][1:]]]).encode(), "a.csv")

    def test_large_amount_and_scale_rejected(self):
        for amount in [
            "123456789012345678901234567890.12",
            "0.00001",
            "-1000000000001",
        ]:
            with self.assertRaises(ValueError):
                parse(
                    csv_text(
                        [
                            [
                                "a",
                                "N",
                                "2026-10-01T00:00:00Z",
                                "2026-10-01T01:00:00Z",
                                amount,
                            ]
                        ]
                    ).encode(),
                    "a.csv",
                )


class RevisedWakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_revisions(self):
        with tempfile.TemporaryDirectory() as root:
            for scenario in revised_scenarios():
                report = await run_scenario(scenario, Path(root) / scenario["name"])
                self.assertFalse(report["bus_errors"])
                m = report["metrics"]
                self.assertLessEqual(m["source_reads_used"], scenario["source_read_budget"])
                self.assertLessEqual(m["source_reads_reserved"], scenario["source_read_budget"])
                if scenario["name"] in {"revised_before_wake", "revised_after_reads"}:
                    self.assertEqual(report["current_artifact"]["status"], "reconciled")
                    self.assertEqual(
                        report["current_artifact"]["goal_revision"],
                        report["current_goal_revision"],
                    )
                    self.assertIsNone(report["current_artifact"]["scope"]["region"])
                    self.assertEqual(report["current_artifact"]["metrics"]["a_total"], "125")
                    self.assertEqual(report["current_artifact"]["metrics"]["b_total"], "135")
                    self.assertEqual(m["current_publications"], 1)
                    revised = [
                        e for e in report["events"] if e["type"] == "reference.revision_grant"
                    ][0]
                    pub = [
                        e
                        for e in report["events"]
                        if e["type"] == "reference.current_artifact_published"
                    ][0]
                    self.assertLess(revised["sequence"], pub["sequence"])
                    if scenario["name"] == "revised_after_reads":
                        self.assertEqual(
                            (
                                m["source_reads_used"],
                                m["source_reads_reserved"],
                                m["preparations_reserved"],
                                m["scans"],
                            ),
                            (6, 8, 2, 2),
                        )
                        self.assertTrue(
                            any(
                                e["type"] == "reference.preparation_discarded"
                                for e in report["events"]
                            )
                        )
                else:
                    self.assertIsNone(report["current_artifact"])
