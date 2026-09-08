"""Proactivity contracts run without models; optional framework parity is explicit."""

import asyncio
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from examples.proactive.domain import Tools
from examples.proactive.lessons import backend, run_lesson
from examples.proactive.live import run_clock

ROOT = Path(__file__).resolve().parents[1]


def frameworks():
    names = ["noema"]
    if importlib.util.find_spec("google") and importlib.util.find_spec("google.adk"):
        names.append("adk")
    if importlib.util.find_spec("langgraph"):
        names.append("langgraph")
    return names


class ProactiveExamples(unittest.IsolatedAsyncioTestCase):
    async def test_lessons_and_framework_parity(self):
        for level in (1, 2, 3):
            reference = None
            for framework in frameworks():
                with self.subTest(level=level, framework=framework):
                    result = await asyncio.wait_for(run_lesson(framework, level), 20)
                    observed = {k: result[k] for k in ("calls", "notices", "world")}
                    if reference is None:
                        reference = observed
                    self.assertEqual(observed, reference)

    async def test_silence_expiry_pause_and_duplicate_observations(self):
        for framework in frameworks():
            for case in ("early", "deadline", "paused", "quiet", "cancelled", "duplicate"):
                with self.subTest(framework=framework, case=case):
                    tools = Tools()
                    agent = await backend(framework)(1, tools).start()
                    try:
                        update = {"now": 5}
                        if case == "early":
                            update["now"] = 4
                        elif case == "deadline":
                            update["now"] = 10
                        elif case == "paused":
                            update["enabled"] = False
                        elif case == "quiet":
                            update["quiet"] = True
                        elif case == "cancelled":
                            update["meetings"] = {
                                "design": {
                                    "start": 10,
                                    "revision": 1,
                                    "importance": 5,
                                    "cancelled": True,
                                }
                            }
                        await agent.tick(**update)
                        await agent.tick(**update)
                        self.assertEqual(len(tools.notices), 1 if case == "duplicate" else 0)
                    finally:
                        await agent.close()

    async def test_unavailable_source_is_bounded_and_reconsidered(self):
        for framework in frameworks():
            with self.subTest(framework=framework):
                tools = Tools()
                agent = await backend(framework)(2, tools).start()
                try:
                    await agent.tick(now=5)
                    await agent.tick(now=5)
                    self.assertEqual(len(tools.calls), 1)
                    self.assertEqual(tools.notices, [])
                    tools.notes["design:v1"] = "New evidence"
                    await agent.tick(now=6)
                    self.assertEqual(len(tools.notices), 1)
                    self.assertEqual(tools.notices[0]["text"], "Brief: New evidence")
                finally:
                    await agent.close()

    async def test_autonomous_clock_host(self):
        for framework in frameworks():
            with self.subTest(framework=framework):
                notices = await run_clock(framework, interval=0.001)
                self.assertEqual(notices[0]["at"], 5)

    async def test_noema_native_causal_decision_records(self):
        result = await run_lesson("noema", 2)
        by_id = {event["id"]: event for event in result["trace"]}
        kinds = {event["type"] for event in result["trace"]}
        self.assertTrue({"decision.proposed", "decision.authorized", "action.succeeded"} <= kinds)
        for event in result["trace"]:
            if event["type"] in {"decision.authorized", "action.succeeded"}:
                self.assertIn(event["causation_id"], by_id)
                self.assertIsNotNone(event["correlation_id"])
        authorized = [e for e in result["trace"] if e["type"] == "decision.authorized"]
        self.assertTrue(all("effective_authority" in e["payload"] for e in authorized))
        self.assertTrue(all(e["payload"]["intent"]["falsifiers"] for e in authorized))

    async def test_clock_rejects_backwards_time(self):
        for framework in frameworks():
            with self.subTest(framework=framework):
                agent = await backend(framework)(1, Tools()).start()
                try:
                    await agent.tick(now=4)
                    with self.assertRaises(ValueError):
                        await agent.tick(now=3)
                finally:
                    await agent.close()


class ProcessPersistence(unittest.TestCase):
    def test_separate_processes_after_completed_observation(self):
        for framework in frameworks():
            with self.subTest(framework=framework), tempfile.TemporaryDirectory() as directory:
                command = [
                    sys.executable,
                    "-m",
                    "examples.proactive.restart_probe",
                    framework,
                    directory,
                ]
                first = subprocess.run(command + ["1"], cwd=ROOT, capture_output=True, timeout=40)
                self.assertEqual(first.returncode, 17, first.stderr.decode())
                second = subprocess.run(command + ["2"], cwd=ROOT, capture_output=True, timeout=40)
                self.assertEqual(second.returncode, 0, second.stderr.decode())
                a, b = [
                    json.loads((Path(directory) / f"phase-{n}.json").read_text()) for n in (1, 2)
                ]
                self.assertNotEqual(a["pid"], b["pid"])
                self.assertEqual(len(a["notices"]), 1)
                self.assertEqual(b["notices"], [])
                self.assertEqual(b["calls"], [])
                self.assertEqual(b["world"]["notified"], ["design:v1"])


if __name__ == "__main__":
    unittest.main()
