from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import compositional_lifecycle_domain as domain  # noqa: E402
from commitment_lifecycle import run_scenario  # noqa: E402
from commitment_lifecycle_domain import Scenario  # noqa: E402
from compositional_lifecycle_domain import World, choose_action  # noqa: E402


def sample_facts():
    return {
        "revision": 3,
        "authorized": True,
        "now": 1,
        "evidence_contract": {
            "requirements": [{"class": "a"}, {"class": "b"}],
            "source_fields": {
                "class": "kind",
                "verdict": "ok",
                "revision": "rev",
                "valid_until": "expires",
            },
            "expected_verdict": "yes",
            "postcondition": {
                "fact": "independent_result",
                "verdict": "status",
                "expected": "good",
                "revision": "rev",
                "effect": "effect_ref",
            },
        },
        "sources": {
            "one": {
                "available": True,
                "cost": 1,
                "text": "A",
                "kind": "a",
                "ok": "yes",
                "rev": 3,
                "expires": 5,
            },
            "two": {
                "available": True,
                "cost": 2,
                "text": "B",
                "kind": "b",
                "ok": "yes",
                "rev": 3,
                "expires": 5,
            },
        },
    }


class CompositionalDomainTests(unittest.TestCase):
    def test_all_classes_required_and_field_names_are_declarative(self):
        world = World()
        facts = sample_facts()
        facts["sources"]["two"]["ok"] = "no"
        world.update(facts)
        self.assertIsNone(choose_action(world.facts, "active"))
        facts["sources"]["two"]["ok"] = "yes"
        world.update(facts)
        self.assertEqual(choose_action(world.facts, "active")[1]["sources"], ["one", "two"])

    def test_future_report_cannot_replace_causally_later_evidence(self):
        world = World()
        world.update(sample_facts())
        world.update(
            {
                "independent_result": {
                    "status": "good",
                    "rev": 3,
                    "effect_ref": 1,
                    "observed_at": 999999,
                }
            }
        )
        prepared = world.invoke("prepare_brief", {"revision": 3, "sources": ["one", "two"]})
        brief = prepared["facts"]["prepared"]
        receipt = world.invoke("deliver_brief", {"brief": brief})["facts"]["receipt"]
        self.assertFalse(world.invoke("verify_receipt", {"receipt": receipt})["close"])
        world.update({"independent_result": {"status": "good", "rev": 2, "effect_ref": 1}})
        self.assertFalse(world.invoke("verify_receipt", {"receipt": receipt})["close"])
        world.update({"independent_result": {"status": "good", "rev": 3, "effect_ref": 99}})
        self.assertFalse(world.invoke("verify_receipt", {"receipt": receipt})["close"])
        world.update({"independent_result": {"status": "good", "rev": 3, "effect_ref": 1}})
        self.assertTrue(world.invoke("verify_receipt", {"receipt": receipt})["close"])
        world.update({"independent_result": {"status": "bad", "rev": 3, "effect_ref": 1}})
        self.assertFalse(world.invoke("verify_receipt", {"receipt": receipt})["close"])


class CompositionalRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_preserves_causal_observation_and_effect_order(self):
        wake = {"op": "wake"}
        case = Scenario(
            "generic-conjunction",
            (
                {"op": "update", "facts": sample_facts()},
                wake,
                wake,
                {"op": "restart"},
                wake,
                {
                    "op": "update",
                    "facts": {"independent_result": {"status": "good", "rev": 3, "effect_ref": 1}},
                },
                wake,
                wake,
            ),
            expected_revision=3,
        )
        result = await run_scenario(case, domain_module=domain)
        self.assertEqual(result["metrics"]["valid_effects"], 1)
        self.assertEqual(result["metrics"]["delivery_invocations"], 1)
        self.assertFalse(result["metrics"]["false_closure"])
        self.assertFalse(result["metrics"]["missed_useful_outcome"])
