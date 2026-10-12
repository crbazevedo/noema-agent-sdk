from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
sys.path.insert(0, str(EXAMPLES))
import artifact_import_domain as domain  # noqa: E402
from artifact_import_domain import World, choose_action  # noqa: E402
from commitment_lifecycle import run_scenario  # noqa: E402
from declarative_transfer import map_scenario  # noqa: E402

ROOT = EXAMPLES.parent / "research" / "artifact_import"


def fixtures():
    return (
        json.loads((ROOT / "mapping.json").read_text()),
        json.loads((ROOT / "public_cases.json").read_text()),
    )


class ArtifactProviderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name) / "artifacts"
        root.mkdir()
        self.world = World(artifact_root=str(root))
        mapping, cases = fixtures()
        self.world.update({"evidence_contract": mapping["contract"]})
        self.world.update(cases[0]["commands"][0]["facts"])

    def step(self):
        action = choose_action(self.world.facts, "active")
        result = self.world.invoke(*action)
        self.world.facts.update(result["facts"])
        return result

    def test_json_restart_relinks_readback_and_reads_real_file(self):
        self.step()
        self.step()
        persisted = Path(self.temporary.name) / "provider.json"
        self.world.dump(persisted)
        self.world = World.load(persisted)
        self.assertTrue(self.step()["close"])
        self.assertEqual(len(self.world.ledger[0]["readbacks"]), 1)
        self.assertIn("import_verified", self.world.facts)
        self.assertEqual(self.world.io_metrics["readback_bytes_read"], 24)
        path = Path(self.world.ledger[0]["artifact_path"])
        path.write_text("id,value\n999,tampered\n")
        self.assertFalse(self.step()["close"])
        self.assertEqual(len(self.world.ledger[0]["readbacks"]), 2)

    def test_changed_contract_cannot_close_old_artifact(self):
        self.step()
        self.step()
        changed = dict(self.world.facts["artifact_contract"])
        changed["row_count"] = 99
        self.world.update({"artifact_contract": changed})
        self.assertFalse(self.step()["close"])

    def test_actual_bad_source_and_unsupported_operation_never_write(self):
        self.world.update({"source_csv": "id,value\n1,changed\n"})
        self.assertFalse(self.step()["success"])
        self.assertEqual(list(Path(self.world.artifact_root).iterdir()), [])
        changed = dict(self.world.facts["artifact_contract"])
        changed["operation"] = "transaction_with_compensation"
        self.world.update({"artifact_contract": changed})
        result = self.step()
        self.assertEqual(result["admission_status"], "unsupported")
        self.assertEqual(list(Path(self.world.artifact_root).iterdir()), [])


class ArtifactRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_cases_produce_expected_real_outputs(self):
        mapping, cases = fixtures()
        for case in cases:
            with self.subTest(case=case["name"]):
                result = await run_scenario(map_scenario(case, mapping), domain_module=domain)
                metrics = result["metrics"]
                self.assertFalse(metrics["false_closure"])
                self.assertFalse(metrics["missed_useful_outcome"])
                if case["expected_revision"] is None:
                    self.assertEqual(metrics["write_calls"], 0)
                    self.assertGreater(metrics["unsupported_invocations"], 0)
                    self.assertEqual(metrics["artifact_inventory"], [])
                else:
                    self.assertEqual(metrics["write_calls"], 1)
                    self.assertEqual(metrics["readback_calls"], 1)
                    self.assertEqual(metrics["bytes_written"], 24)
                    self.assertEqual(
                        await asyncio.to_thread(Path(metrics["artifact_paths"][0]).read_text),
                        "id,value\n1,alpha\n2,beta\n",
                    )
