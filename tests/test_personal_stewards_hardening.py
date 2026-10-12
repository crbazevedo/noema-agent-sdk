"""Regressions from independent adversarial audit, not success-only fixture tests."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "references"))
from personal_stewards import PersonalSteward  # noqa: E402
from personal_stewards_domain import DOMAINS, initial_facts  # noqa: E402

from noema import Event


def assess(domain, changes=None, *, observed_at=0):
    facts = {**initial_facts(domain), **(changes or {})}
    return DOMAINS[domain].assess(
        {
            "now": 1,
            "sources": {
                key: {
                    "fixture": {
                        "value": value,
                        "valid_until": 120,
                        "observed_at": observed_at,
                        "event_id": "source",
                    }
                }
                for key, value in facts.items()
            },
        }
    )


class DomainHardeningTests(unittest.TestCase):
    def test_park_budget_access_and_count_are_hard_constraints(self):
        for change in (
            {"budget": 0},
            {"budget": 100},
            {"park_accessible": False},
            {"park_accessible": None},
            {"budget": True},
            {"adults": 0},
            {"adults": -1},
            {"adults": True},
        ):
            with self.subTest(change=change):
                result = assess("gathering", change)
                park = next((o for o in result.options if o["id"] == "park"), None)
                self.assertTrue(park is None or not park["admissible"])
        self.assertTrue(assess("gathering", {"budget": 120}).options[0]["admissible"])

    def test_malformed_rents_do_not_crash_or_invent_savings(self):
        for value in (["cheap"], [-100], [True], [None], [], None, "3800", [10**10]):
            with self.subTest(value=value):
                result = assess("finance", {"rent_alternatives": value})
                self.assertNotIn("potential_monthly_saving_brl", result.options[1])
                self.assertFalse(any(s.startswith("rent_alternatives:") for s in result.known))
                self.assertTrue(any("rent_alternatives" in u for u in result.uncertain))
        for value in (None, -1, True, "unknown"):
            result = assess("finance", {"rent_alternatives": [3800], "moving_cost": value})
            self.assertNotIn("break_even_months_rounded_up", result.options[1])
        result = assess("finance", {"rent_alternatives": [3800]})
        self.assertNotIn("break_even_months_rounded_up", result.options[1])
        result = assess("finance", {"rent_alternatives": [3800], "moving_cost": 6001})
        self.assertEqual(result.options[1]["break_even_months_rounded_up"], 7)

    def test_missing_text_and_future_evidence_abstain(self):
        for domain, key in (
            ("research", "protocol"),
            ("research", "deadline"),
            ("gathering", "time"),
        ):
            for value in (None, "", "   ", True, 1):
                with self.subTest(domain=domain, key=key, value=value):
                    self.assertFalse(assess(domain, {key: value}).ready)
        self.assertFalse(assess("finance", observed_at=60).ready)
        self.assertFalse(assess("gathering", {"time": "Saturday 17:00–20:00"}).ready)


class RuntimeHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_clock_and_expired_or_revoked_approval(self):
        with tempfile.TemporaryDirectory() as root:
            app = PersonalSteward("finance", root)
            await app.start()
            try:
                for value in (-121, True, 0.5, "5", 10**9):
                    with self.assertRaises(ValueError):
                        await app.command({"op": "advance", "minutes": value})
                self.assertEqual((await app.state())["now"], 0)
                await app.command({"op": "wake"})
                await app.command({"op": "wake"})
                await app.command({"op": "advance", "minutes": 121})
                await app.command({"op": "approve"})
                self.assertEqual((await app.state())["approved_revision"], -1)
                await app.command({"op": "revoke"})
                await app.command({"op": "approve"})
                self.assertEqual((await app.state())["approved_revision"], -1)
            finally:
                await app.stop()

    async def exercise_io_race(self, operation, mutation):
        with tempfile.TemporaryDirectory() as root:
            app = PersonalSteward("finance", root)
            await app.start()
            original = getattr(Path, "read_bytes" if operation == "verify" else "write_text")
            entered, release = threading.Event(), threading.Event()
            first = True

            def blocked(path, *args, **kwargs):
                nonlocal first
                if path.parent == Path(root) and path.suffix == ".json" and first:
                    first = False
                    # Capture old bytes before the competing mutation for verify.
                    result = original(path, *args, **kwargs)
                    entered.set()
                    if not release.wait(timeout=5):
                        raise TimeoutError("Test race barrier timed out")
                    return result
                return original(path, *args, **kwargs)

            try:
                await app.command({"op": "wake"})
                if operation == "verify":
                    await app.command({"op": "wake"})
                    await app.command({"op": "approve"})
                with patch.object(
                    Path, "read_bytes" if operation == "verify" else "write_text", blocked
                ):
                    task = asyncio.create_task(app.command({"op": "wake"}))
                    try:
                        await asyncio.wait_for(asyncio.to_thread(entered.wait), timeout=2)
                        if mutation == "observe":
                            await app.observe({"salary": 11000}, why="Evidence arrived during IO")
                        elif mutation == "revoke":
                            await app.command({"op": "revoke"})
                        else:
                            state = await app.state()
                            (Path(root) / state["artifact"]["path"]).write_text('{"tampered":true}')
                    finally:
                        release.set()
                        await task
                state = await app.state()
                self.assertFalse(state["closed"])
                events = await app.kernel.history()
                self.assertFalse(any(e.type == "reference.artifact_verified" for e in events))
                if mutation == "observe":
                    self.assertEqual(state["revision"], 2)
                    self.assertEqual(state["sources"]["salary"]["fixture"]["value"], 11000)
                    self.assertEqual(state["approved_revision"], -1)
                if mutation == "revoke":
                    self.assertFalse(state["allowed"])
                if operation == "prepare":
                    self.assertEqual(state["prepared_revision"], -1)
            finally:
                release.set()
                await app.stop()

    async def test_verify_does_not_overwrite_concurrent_evidence(self):
        await self.exercise_io_race("verify", "observe")

    async def test_prepare_does_not_publish_concurrent_stale_evidence(self):
        await self.exercise_io_race("prepare", "observe")

    async def test_revocation_during_io_blocks_result(self):
        await self.exercise_io_race("verify", "revoke")
        await self.exercise_io_race("prepare", "revoke")

    async def test_artifact_replaced_after_first_read_cannot_close(self):
        await self.exercise_io_race("verify", "tamper")

    async def test_update_after_verified_commit_reopens_without_rollback(self):
        with tempfile.TemporaryDirectory() as root:
            app = PersonalSteward("finance", root)
            await app.start()
            try:
                for op in ("wake", "wake", "approve", "wake"):
                    await app.command({"op": op})
                self.assertTrue((await app.state())["closed"])
                await app.observe({"salary": 11000})
                state = await app.state()
                self.assertFalse(state["closed"])
                self.assertEqual(state["revision"], 2)
                self.assertEqual(state["approved_revision"], -1)
                self.assertEqual(
                    (await app.kernel.snapshot()).commitments["finance"].status.value, "active"
                )
            finally:
                await app.stop()

    async def test_actual_compare_and_append_rejects_new_canonical_head(self):
        with tempfile.TemporaryDirectory() as root:
            app = PersonalSteward("finance", root)
            await app.start()
            try:
                await app.command({"op": "wake"})
                original = app.kernel.emit_if_head

                async def interposed(event, *, expected_head_sequence):
                    await app.kernel.emit(Event("reference.concurrent_event", "test"))
                    return await original(event, expected_head_sequence=expected_head_sequence)

                with patch.object(app.kernel, "emit_if_head", interposed):
                    await app.command({"op": "wake"})
                self.assertEqual((await app.state())["prepared_revision"], -1)
                self.assertFalse((await app.state())["closed"])
            finally:
                await app.stop()

    async def test_expired_accepted_document_is_not_projected_as_current(self):
        with tempfile.TemporaryDirectory() as root:
            app = PersonalSteward("finance", root)
            await app.start()
            try:
                for op in ("wake", "wake", "approve"):
                    await app.command({"op": op})
                await app.command({"op": "advance", "minutes": 121})
                events = await app.kernel.history()
                card = next(e.payload for e in reversed(events) if e.type == "reference.card")
                self.assertEqual(card["human_decision"], "pending")
                self.assertIsNone(card["artifact"])
                self.assertEqual(card["status"], "needs-current-evidence")
            finally:
                await app.stop()
