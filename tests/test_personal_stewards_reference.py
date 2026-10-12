from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "references"))
from personal_stewards import PersonalSteward, run_scenario  # noqa: E402
from personal_stewards_domain import public_scenarios  # noqa: E402


class PersonalStewardTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_cases_have_exact_scope_and_replay(self):
        for scenario in public_scenarios():
            with self.subTest(scenario=scenario["name"]):
                result = await run_scenario(scenario)
                self.assertTrue(result["replay_equal"])
                self.assertEqual(result["metrics"]["external_effects"], 0)
                self.assertEqual(result["metrics"]["model_calls"], 0)
                self.assertEqual(
                    result["status"] == "closed-local-review",
                    scenario["name"].startswith(("P1", "P2", "P3")),
                )
                ids = {e["id"] for e in result["events"]}
                by_id = {e["id"]: e for e in result["events"]}
                for card in result["cards"]:
                    self.assertIn(card["event_id"], ids)
                    for eid in card["evidence_ids"]:
                        self.assertLess(by_id[eid]["sequence"], card["sequence"])
                    if card["artifact"]:
                        artifact = card["artifact"]
                        self.assertIn(artifact["event_id"], ids)
                        self.assertEqual(
                            hashlib.sha256(artifact["content"].encode()).hexdigest(),
                            artifact["sha256"],
                        )
                if result["status"] == "closed-local-review":
                    artifact = result["artifact"]
                    proof = by_id[artifact["readback_event_id"]]
                    self.assertEqual(proof["type"], "reference.artifact_verified")
                    self.assertIn(proof["payload"]["human_decision_event_id"], ids)

    async def test_finance_uses_cash_only_and_revises_reserve(self):
        result = await run_scenario(public_scenarios()[0])
        first, last = result["cards"][0], result["cards"][-1]
        self.assertEqual(first["options"][0]["reserve_target_brl"], 67200)
        self.assertEqual(last["options"][0]["reserve_target_brl"], 73200)
        self.assertEqual(last["options"][0]["cash_gap_brl"], 31200)
        self.assertEqual(last["options"][0]["unfunded_after_maturity_brl"], 13200)
        self.assertEqual(last["options"][1]["potential_monthly_saving_brl"], 1000)
        self.assertEqual(last["options"][1]["break_even_months_rounded_up"], 6)
        self.assertTrue(any("conflicting independent" in s for s in last["uncertain"]))
        self.assertFalse(last["options"][2]["admissible"])
        scheduled = [e for e in result["events"] if e["type"] == "reference.wake_scheduled"]
        self.assertTrue(any(e["payload"]["due_minute"] == 15 for e in scheduled))
        self.assertTrue(any(e["type"] == "reference.wake_cancelled" for e in result["events"]))

    async def test_research_does_not_promote_disagreement_to_findings(self):
        result = await run_scenario(public_scenarios()[1])
        card = result["cards"][-1]
        self.assertIn("inconclusive", card["recommendation"])
        self.assertFalse(card["options"][1]["admissible"])
        self.assertFalse(card["options"][2]["admissible"])
        self.assertTrue(any("conflicting independent" in s for s in card["uncertain"]))

    async def test_rain_and_accessibility_are_hard_constraints(self):
        result = await run_scenario(public_scenarios()[2])
        cards = [c for c in result["cards"] if "Rain and stairs" in c["changed"]]
        options = cards[0]["options"]
        self.assertFalse(options[0]["admissible"])
        self.assertFalse(options[1]["admissible"])
        self.assertTrue(options[2]["admissible"])
        self.assertTrue(result["cards"][-1]["options"][1]["admissible"])

    async def test_revocation_and_concurrent_input_prevent_effect(self):
        for index in (3, 6):
            result = await run_scenario(public_scenarios()[index])
            self.assertEqual(result["metrics"]["preparations"], 0)
            self.assertGreater(result["metrics"]["policy_denials"], 0)

    async def test_stale_required_input_abstains_without_zero_valued_advice(self):
        result = await run_scenario(public_scenarios()[4])
        self.assertEqual(result["metrics"]["preparations"], 0)
        self.assertEqual(result["cards"][-1]["options"][0]["id"], "refresh")
        self.assertTrue(any(e["type"] == "reference.abstained" for e in result["events"]))

    async def test_approval_cannot_survive_revision_and_restart(self):
        result = await run_scenario(public_scenarios()[5])
        self.assertEqual(result["status"], "needs-current-evidence")
        self.assertIsNone(result["artifact"]["readback_event_id"])
        self.assertIsNone(result["cards"][-1]["artifact"])
        self.assertEqual(result["cards"][-1]["human_decision"], "pending")
        self.assertIn("guest_availability_for_current_time", result["cards"][-1]["recommendation"])

    async def test_tampered_artifact_cannot_close(self):
        with tempfile.TemporaryDirectory() as root:
            app = PersonalSteward("finance", root)
            await app.start()
            try:
                await app.command({"op": "wake"})
                await app.command({"op": "wake"})
                state = await app.state()
                path = Path(root) / state["artifact"]["path"]
                path.write_text('{"forged": true}')
                await app.command({"op": "approve"})
                await app.command({"op": "wake"})
                self.assertFalse((await app.state())["closed"])
            finally:
                await app.stop()

    async def test_conflicting_required_sources_need_resolution(self):
        scenario = {
            "name": "conflicted-cash",
            "domain": "finance",
            "commands": [
                {"op": "observe", "facts": {"liquid_cash": 99999}, "source": "other-bank-summary"},
                {"op": "wake"},
                {"op": "wake"},
                {"op": "approve"},
                {"op": "wake"},
            ],
        }
        result = await run_scenario(scenario)
        self.assertEqual(result["status"], "needs-current-evidence")
        self.assertEqual(result["metrics"]["preparations"], 0)
        self.assertIsNone(result["artifact"])

    async def test_repeated_wake_is_not_repeated_preparation(self):
        scenario = {
            "name": "repeat",
            "domain": "finance",
            "commands": [
                {"op": "wake"},
                {"op": "wake"},
                {"op": "wake"},
                {"op": "wake"},
                {"op": "approve", "revision": 0},
                {"op": "wake"},
            ],
        }
        result = await run_scenario(scenario)
        self.assertEqual(result["metrics"]["preparations"], 1)
        self.assertEqual(result["status"], "needs-human-decision")
        self.assertEqual(json.loads(result["artifact"]["content"])["revision"], 1)

    async def test_new_venue_event_actually_changes_scheduled_due(self):
        result = await run_scenario(public_scenarios()[2])
        due = None
        transitions = []
        for event in result["events"]:
            if event["type"] == "reference.wake_scheduled":
                next_due = event["payload"]["due_minute"]
                transitions.append((due, next_due, event["payload"]["reason"]))
                due = next_due
        self.assertIn(
            (15, 12, "Rain and stairs invalidate first venue; deadline moved earlier"), transitions
        )
        self.assertIn(
            (22, 25, "New ground-floor room available until its own later deadline"), transitions
        )
