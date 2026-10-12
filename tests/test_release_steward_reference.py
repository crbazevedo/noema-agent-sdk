from __future__ import annotations

import asyncio
import json
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "references"))
from release_steward import ReleaseSteward, public_scenarios, run_scenario  # noqa: E402


class ReleaseStewardReferenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_work_graph_cases_and_physical_outputs(self):
        for scenario in public_scenarios():
            with self.subTest(scenario=scenario["name"]):
                result = await run_scenario(scenario)
                self.assertTrue(result["replay_equal"])
                effects = result["effects"]
                packages = [e for e in effects if e["operation"] == "package"]
                if scenario["name"].startswith("R5"):
                    self.assertEqual(result["status"], "active")
                    self.assertEqual(packages, [])
                    self.assertFalse(any(e["operation"] == "verify" for e in effects))
                    continue
                self.assertEqual(result["status"], "closed")
                self.assertEqual(len(packages), 1)
                with zipfile.ZipFile(packages[0]["path"]) as archive:
                    prepared = json.loads(archive.read("prepared.json"))
                    receipt = json.loads(archive.read("verification.json"))
                    manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(prepared["features"], result["features"])
                self.assertEqual(manifest["revision"], result["revision"])
                self.assertNotEqual(receipt["verifier"], receipt["executor"])
                self.assertTrue(receipt["passed"])
                if scenario["name"].startswith("R2"):
                    self.assertEqual(result["stale_rejections"], 1)
                    self.assertEqual(effects[0]["token"], 2)
                    self.assertEqual(effects[0]["worker"], "replacement")
                if scenario["name"].startswith("R3"):
                    self.assertEqual(len(result["graphs"]), 2)
                    self.assertEqual(packages[0]["revision"], 2)

    async def test_revoked_effect_permission_prevents_fenced_dispatch(self):
        scenario = {
            "name": "permission-loss",
            "commands": [
                {"op": "plan"},
                {"op": "lease"},
                {"op": "permission", "allowed": False},
                {"op": "stale_dispatch"},
            ],
        }
        result = await run_scenario(scenario)
        self.assertEqual(result["effects"], [])
        self.assertNotEqual(result["status"], "closed")
        self.assertTrue(any(e["type"] == "decision.denied" for e in result["events"]))
        inventory = await asyncio.to_thread(
            lambda: list(Path(result["artifact_root"]).glob("*.zip"))
        )
        self.assertEqual(inventory, [])

    async def test_same_tick_new_presence_returns_and_packaged_program_runs(self):
        import tempfile

        scenario = {
            "name": "same-tick-return",
            "factor": "3",
            "commands": [
                {"op": "plan"},
                {"op": "step"},
                {"op": "step"},
                {"op": "presence", "worker": "packager", "status": "offline"},
                {"op": "step"},
                {"op": "presence", "worker": "packager", "status": "available"},
                {"op": "step"},
            ],
        }
        result = await run_scenario(scenario)
        self.assertEqual(result["status"], "closed")
        package = next(e for e in result["effects"] if e["operation"] == "package")
        with tempfile.TemporaryDirectory() as temporary:
            with zipfile.ZipFile(package["path"]) as archive:
                archive.extractall(temporary)
                report = json.loads(archive.read("verification.json"))
            self.assertTrue(all(test["passed"] for test in report["tests"]))
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",
                str(Path(temporary) / "transform.py"),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            output, _ = await process.communicate(b"id,amount\n audit ,10.5\n")
            self.assertEqual(process.returncode, 0)
            self.assertEqual(json.loads(output), [{"id": "audit", "amount": "31.5"}])

    async def test_bad_program_and_post_test_mutation_block_package(self):
        import tempfile

        for after_tests in (False, True):
            with self.subTest(after_tests=after_tests), tempfile.TemporaryDirectory() as directory:
                app = ReleaseSteward(Path(directory))
                await app.start()
                try:
                    await app.command({"op": "plan"})
                    await app.command({"op": "step"})
                    if after_tests:
                        await app.command({"op": "step"})
                    source = await asyncio.to_thread(
                        lambda: next(Path(directory).glob("*-transform.py"))
                    )
                    await asyncio.to_thread(source.write_text, "print('[]')\n")
                    await app.command({"op": "step"})
                    self.assertFalse(
                        await asyncio.to_thread(lambda: list(Path(directory).glob("*.zip")))
                    )
                    self.assertFalse(any(e["operation"] == "package" for e in app.effects))
                    if not after_tests:
                        history = await app.kernel.history()
                        self.assertTrue(
                            any(e.type == "reference.software_tests_failed" for e in history)
                        )
                finally:
                    result = await app.finish()
                self.assertNotEqual(result["status"], "closed")

    async def test_preverification_fixture_and_spec_tampering_rejected(self):
        import tempfile

        for member, replacement in (
            ("fixture.csv", "id,amount\nchanged,999\n"),
            (
                "spec.json",
                '{"revision":1,"factor":"999","input_columns":["id","amount"],"output_fields":["id","amount"]}',
            ),
        ):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as directory:
                app = ReleaseSteward(Path(directory))
                await app.start()
                try:
                    await app.command({"op": "plan"})
                    await app.command({"op": "step"})
                    source = await asyncio.to_thread(
                        lambda member=member: next(Path(directory).glob(f"*-{member}"))
                    )
                    await asyncio.to_thread(source.write_text, replacement)
                    await app.command({"op": "step"})
                    await app.command({"op": "step"})
                    self.assertFalse(
                        any(e["operation"] in ("verify", "package") for e in app.effects)
                    )
                    self.assertFalse(
                        await asyncio.to_thread(lambda: list(Path(directory).glob("*.zip")))
                    )
                finally:
                    result = await app.finish()
                self.assertNotEqual(result["status"], "closed")
