from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from commitment_lifecycle import run_scenario  # noqa: E402
from commitment_lifecycle_domain import Scenario, public_scenarios  # noqa: E402


class CommitmentLifecycleExampleTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_public_cases_reach_useful_and_safe_outcomes(self):
        for scenario in public_scenarios():
            with self.subTest(scenario=scenario.name):
                result = await run_scenario(scenario)
                metrics = result["metrics"]
                self.assertEqual(metrics["unsafe_effects"], 0)
                self.assertFalse(metrics["false_closure"])
                self.assertFalse(metrics["missed_useful_outcome"])
                self.assertEqual(
                    metrics["delivery_invocations"], int(scenario.expected_revision is not None)
                )
                if scenario.name == "replan_after_changed_evidence":
                    self.assertEqual(result["ledger"][0]["brief"]["text"], "Corrected evidence C")
                    self.assertEqual(metrics["preparations"], 2)
                if scenario.name == "revocation_between_plan_and_effect":
                    self.assertEqual(metrics["policy_denials"], 1)

    async def test_policy_ablation_exposes_unsafe_effect(self):
        scenario = next(s for s in public_scenarios() if s.name.startswith("revocation"))
        result = await run_scenario(scenario, policy_enabled=False)
        self.assertGreater(result["metrics"]["unsafe_effects"], 0)
        self.assertFalse(result["metrics"]["closed"])

    async def test_replay_ablation_loses_useful_outcome(self):
        scenario = next(s for s in public_scenarios() if s.name == "restart_before_delivery")
        result = await run_scenario(scenario, replay_enabled=False)
        self.assertTrue(result["metrics"]["missed_useful_outcome"])

    async def test_changed_revision_after_delivery_requires_new_delivery(self):
        wake = {"op": "wake"}
        scenario = Scenario(
            "revision_after_delivery",
            (
                wake,
                {"op": "update", "facts": {"authorized": True}},
                wake,
                {"op": "update", "facts": {"revision": 2}},
                wake,
                wake,
                wake,
            ),
            expected_revision=2,
        )
        result = await run_scenario(scenario)
        self.assertEqual(result["metrics"]["valid_effects"], 2)
        self.assertFalse(result["metrics"]["false_closure"])
        self.assertFalse(result["metrics"]["missed_useful_outcome"])
