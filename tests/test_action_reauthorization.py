from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from noema import (
    ActionIntent,
    AutonomousAgent,
    AutonomousAgentConfig,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    CognitiveController,
    Event,
    NoemaKernel,
    PolicyEngine,
    RuleBasedReasoner,
    SQLiteEventStore,
)


class ActionReauthorizationTests(unittest.IsolatedAsyncioTestCase):
    def make_agent(self, kernel, registry, intents, *, policy=None):
        return AutonomousAgent(
            config=AutonomousAgentConfig(
                agent_id="worker",
                trigger_patterns=("external.run",),
                max_concurrent_actions=1,
                retry_backoff_seconds=0,
                retry_jitter_fraction=0,
            ),
            kernel=kernel,
            controller=CognitiveController(
                RuleBasedReasoner(
                    [lambda request: intents if request.trigger.type == "external.run" else None]
                )
            ),
            capabilities=registry,
            policy=policy
            or PolicyEngine(
                rules=(
                    lambda intent, spec, situation: (
                        "permission revoked" if situation.fact("permission") == "revoked" else None
                    ),
                )
            ),
        )

    async def revoke(self, kernel):
        return await kernel.emit(
            Event("fact.observed", "operator", {"key": "permission", "value": "revoked"})
        )

    async def test_queued_action_rechecks_permission_before_first_invocation(self) -> None:
        kernel = NoemaKernel()
        registry = CapabilityRegistry()
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def blocker(arguments, context):
            calls.append("blocker")
            entered.set()
            await release.wait()
            return CapabilityResult.ok()

        async def queued(arguments, context):
            calls.append("queued")
            return CapabilityResult.ok()

        registry.register_function(CapabilitySpec("blocker", "Hold execution"), blocker)
        registry.register_function(CapabilitySpec("queued", "Queued execution"), queued)
        intents = [
            ActionIntent("blocker", expected_value=20),
            ActionIntent("queued", expected_value=10),
        ]
        agent = self.make_agent(kernel, registry, intents)
        await agent.start()
        try:
            await kernel.emit(Event("external.run", "test"))
            await asyncio.wait_for(entered.wait(), 2)
            revoked = await self.revoke(kernel)
            release.set()
            await agent.wait_until_idle()
            self.assertEqual(calls, ["blocker"])
            abandoned = await kernel.history(types=["action.abandoned"])
            self.assertEqual(len(abandoned), 1)
            self.assertEqual(abandoned[0].subject, intents[1].intent_id)
            self.assertEqual(abandoned[0].payload["attempts"], 0)
            self.assertIsNone(abandoned[0].payload["previous_attempt_error"])
            self.assertGreaterEqual(abandoned[0].payload["situation_version"], revoked.sequence)
            self.assertEqual(len(await kernel.history(types=["action.succeeded"])), 1)
        finally:
            release.set()
            await agent.stop()
            await kernel.stop()

    async def test_retry_denial_is_durable_without_compensation_or_effect_free_claim(self) -> None:
        for timeout in (False, True):
            with self.subTest(timeout=timeout), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "events.sqlite3"
                kernel = NoemaKernel(store=SQLiteEventStore(path))
                registry = CapabilityRegistry()
                calls = []
                compensations = []

                async def invoke(arguments, context, calls=calls, kernel=kernel, timeout=timeout):
                    calls.append(context.attempt)
                    await context.emit(Event("effect.observed", "adapter", {"partial": True}))
                    await self.revoke(kernel)
                    if timeout:
                        await asyncio.Event().wait()
                    return CapabilityResult.fail(
                        "partial attempt requires reconciliation", retryable=True
                    )

                async def compensate(arguments, result, context, compensations=compensations):
                    compensations.append(context.attempt)
                    return CapabilityResult.ok()

                registry.register_function(
                    CapabilitySpec(
                        "work", "Perform work", idempotent=True, max_retries=2, timeout_seconds=0.05
                    ),
                    invoke,
                    compensation=compensate,
                )
                intent = ActionIntent(
                    "work",
                    expected_value=10,
                    idempotency_key="work:1",
                    metadata={"compensate_on_failure": True},
                )
                agent = self.make_agent(kernel, registry, [intent])
                await agent.start()
                try:
                    await kernel.emit(Event("external.run", "test"))
                    await agent.wait_until_idle()
                    self.assertEqual(calls, [1])
                    self.assertEqual(compensations, [])
                    abandoned = await kernel.history(types=["action.abandoned"])
                    self.assertEqual(len(abandoned), 1)
                    self.assertEqual(abandoned[0].payload["attempts"], 1)
                    self.assertEqual(abandoned[0].payload["idempotency_key"], "work:1")
                    self.assertIn("permission revoked", abandoned[0].payload["reason"])
                    self.assertIsNotNone(abandoned[0].payload["previous_attempt_error"])
                    authorized = await kernel.history(types=["decision.authorized"])
                    self.assertEqual(
                        abandoned[0].payload["original_authorization_event_id"], authorized[0].id
                    )
                    self.assertEqual(len(await kernel.history(types=["effect.observed"])), 1)
                    self.assertEqual(await kernel.history(types=["action.failed"]), [])
                    self.assertEqual(await kernel.history(types=["action.succeeded"]), [])
                    self.assertNotIn("no_effect", abandoned[0].payload)
                finally:
                    await agent.stop()
                    await kernel.stop()

                recovered_kernel = NoemaKernel(store=SQLiteEventStore(path))
                # Even a newly permissive policy must not replay an abandoned intent.
                recovered = self.make_agent(recovered_kernel, registry, [], policy=PolicyEngine())
                await recovered.start()
                try:
                    await recovered.wait_until_idle()
                    self.assertEqual(calls, [1])
                    self.assertEqual(compensations, [])
                    self.assertEqual(
                        len(await recovered_kernel.history(types=["action.abandoned"])), 1
                    )
                    self.assertEqual(
                        await recovered_kernel.history(types=["decision.reauthorized"]), []
                    )
                finally:
                    await recovered.stop()
                    await recovered_kernel.stop()

    async def test_allowed_retry_receives_fresh_snapshot_and_preserves_identity(self) -> None:
        kernel = NoemaKernel()
        registry = CapabilityRegistry()
        calls = []

        async def invoke(arguments, context):
            calls.append(
                (context.attempt, context.idempotency_key, context.situation.fact("revision"))
            )
            if context.attempt == 1:
                await context.emit(
                    Event("fact.observed", "adapter", {"key": "revision", "value": 2})
                )
                return CapabilityResult.fail("temporary error", retryable=True)
            return CapabilityResult.ok()

        registry.register_function(
            CapabilitySpec("work", "Perform work", idempotent=True, max_retries=1), invoke
        )
        agent = self.make_agent(
            kernel,
            registry,
            [ActionIntent("work", expected_value=10, idempotency_key="stable-key")],
        )
        await agent.start()
        try:
            await kernel.emit(Event("external.run", "test"))
            await agent.wait_until_idle()
            self.assertEqual(calls, [(1, "stable-key", None), (2, "stable-key", 2)])
            self.assertEqual(await kernel.history(types=["action.abandoned"]), [])
            succeeded = await kernel.history(types=["action.succeeded"])
            self.assertEqual(succeeded[0].payload["attempts"], 2)
        finally:
            await agent.stop()
            await kernel.stop()

    async def test_retry_limits_and_non_idempotent_guard_remain_unchanged(self) -> None:
        for idempotent, expected_attempts in ((False, 1), (True, 3)):
            with self.subTest(idempotent=idempotent):
                kernel = NoemaKernel()
                registry = CapabilityRegistry()
                calls = []

                async def invoke(arguments, context, calls=calls):
                    calls.append(context.attempt)
                    return CapabilityResult.fail("temporary error", retryable=True)

                registry.register_function(
                    CapabilitySpec("work", "Perform work", idempotent=idempotent, max_retries=2),
                    invoke,
                )
                agent = self.make_agent(kernel, registry, [ActionIntent("work", expected_value=10)])
                await agent.start()
                try:
                    await kernel.emit(Event("external.run", "test"))
                    await agent.wait_until_idle()
                    self.assertEqual(calls, list(range(1, expected_attempts + 1)))
                    failed = await kernel.history(types=["action.failed"])
                    self.assertEqual(failed[0].payload["attempts"], expected_attempts)
                finally:
                    await agent.stop()
                    await kernel.stop()
