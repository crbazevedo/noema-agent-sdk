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
    InboxConsumer,
    InMemoryBroker,
    NoemaKernel,
    OutboxPublisher,
    PolicyEngine,
    RuleBasedReasoner,
    SQLiteEventStore,
)
from noema.testing import EventCollector


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_broker_echo_is_not_republished(self) -> None:
        kernel = NoemaKernel(store=SQLiteEventStore(":memory:"), distributed=True)
        await kernel.start()
        collector = await EventCollector(kernel).start()
        event = await kernel.emit(Event("external.once", "test"))
        await kernel.ingest(event)
        await kernel.bus.drain()
        self.assertEqual([item.id for item in collector.events], [event.id])
        await collector.stop()
        await kernel.stop()

    async def test_late_broker_event_rebuilds_projection_in_store_order(self) -> None:
        store = SQLiteEventStore(":memory:")
        kernel = NoemaKernel(store=store, distributed=True)
        await kernel.start()
        older = await store.append(
            Event(
                "fact.observed",
                "remote",
                {"key": "service.api.health", "value": "degraded"},
            )
        )
        newer = await store.append(
            Event(
                "fact.observed",
                "remote",
                {"key": "service.api.health", "value": "healthy"},
            )
        )
        await kernel.ingest(newer)
        await kernel.ingest(older)
        self.assertEqual((await kernel.snapshot()).fact("service.api.health"), "healthy")
        await kernel.stop()

    async def test_startup_history_is_not_redelivered_to_local_agents(self) -> None:
        store = SQLiteEventStore(":memory:")
        event = await store.append(Event("external.old", "remote"))
        kernel = NoemaKernel(store=store, distributed=True)
        await kernel.start()
        collector = await EventCollector(kernel).start()
        await kernel.ingest(event)
        await kernel.bus.drain()
        self.assertEqual(collector.events, [])
        await collector.stop()
        await kernel.stop()

    async def test_outbox_recovers_and_inbox_deduplicates_redelivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sender_store = SQLiteEventStore(Path(directory) / "sender.sqlite3")
            receiver_store = SQLiteEventStore(Path(directory) / "receiver.sqlite3")
            sender = NoemaKernel(store=sender_store, distributed=True)
            receiver = NoemaKernel(store=receiver_store, distributed=True)
            broker = InMemoryBroker(fail_publishes=1)
            publisher = OutboxPublisher(
                sender_store,
                broker,
                poll_seconds=0.001,
                max_backoff_seconds=0.001,
            )
            consumer = InboxConsumer(
                receiver_store,
                broker,
                receiver.ingest,
                consumer_id="receiver",
            )
            await sender.start()
            await receiver.start()
            await consumer.start()

            event = await sender.emit(Event("external.once", "test", {"value": 1}))
            self.assertEqual(await sender_store.pending_outbox_count(), 1)
            self.assertEqual(await publisher.run_once(), 0)
            await asyncio.sleep(0.003)
            self.assertEqual(await publisher.run_once(), 1)
            await asyncio.sleep(0.02)
            self.assertEqual([item.id for item in await receiver.history()], [event.id])

            await broker.publish(
                "noema.external.once",
                __import__("json").dumps(event.to_dict()).encode(),
                message_id=event.id,
            )
            await asyncio.sleep(0.02)
            self.assertEqual(len(await receiver.history()), 1)

            await consumer.stop()
            await sender.stop()
            await receiver.stop()
            await broker.close()

    async def test_expired_outbox_lease_uses_fencing_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "events.sqlite3")
            await store.append_with_outbox(Event("external.work", "test"), topic="noema.work")
            first = (await store.claim_outbox("worker-a", limit=1, lease_seconds=0.001))[0]
            await asyncio.sleep(0.003)
            second = (await store.claim_outbox("worker-b", limit=1, lease_seconds=1))[0]
            self.assertGreater(second.fencing_token, first.fencing_token)
            self.assertFalse(await store.complete_outbox(first.id, first.fencing_token))
            self.assertTrue(await store.complete_outbox(second.id, second.fencing_token))
            await store.close()

    async def test_expired_inbox_lease_rejects_stale_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "events.sqlite3")
            first = await store.claim_inbox("message-1", "consumer", lease_seconds=0.001)
            await asyncio.sleep(0.003)
            second = await store.claim_inbox("message-1", "consumer", lease_seconds=1)
            assert first.fencing_token is not None
            assert second.fencing_token is not None
            self.assertGreater(second.fencing_token, first.fencing_token)
            self.assertFalse(
                await store.complete_inbox("message-1", "consumer", first.fencing_token)
            )
            self.assertTrue(
                await store.complete_inbox("message-1", "consumer", second.fencing_token)
            )
            await store.close()


class ActionRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_reuses_business_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite3"
            intent = ActionIntent(
                "charge",
                {"invoice": "42"},
                expected_value=10,
                attention_cost=1,
                confidence=0.9,
                idempotency_key="charge:42:v1",
            )
            first_kernel = NoemaKernel(store=SQLiteEventStore(path))
            await first_kernel.start()
            await first_kernel.emit(
                Event(
                    "decision.authorized",
                    "billing-agent",
                    {"intent": intent.to_payload(), "reason": "authorized"},
                    subject=intent.intent_id,
                )
            )
            await first_kernel.stop()

            business_effects = {"charge:42:v1"}
            invocation_attempts = 0

            async def charge(arguments, context):
                nonlocal invocation_attempts
                invocation_attempts += 1
                key = context.idempotency_key
                if key not in business_effects:
                    business_effects.add(key)
                return CapabilityResult.ok({"invoice": arguments["invoice"]})

            registry = CapabilityRegistry()
            registry.register_function(
                CapabilitySpec(
                    "charge",
                    "Charge an invoice",
                    idempotent=True,
                    max_retries=2,
                ),
                charge,
            )
            second_kernel = NoemaKernel(store=SQLiteEventStore(path))
            agent = AutonomousAgent(
                config=AutonomousAgentConfig(agent_id="billing-agent"),
                kernel=second_kernel,
                controller=CognitiveController(RuleBasedReasoner()),
                capabilities=registry,
                policy=PolicyEngine(),
            )
            await agent.start()
            self.assertEqual(invocation_attempts, 1)
            self.assertEqual(business_effects, {"charge:42:v1"})
            self.assertEqual(len(await second_kernel.history(types=["action.succeeded"])), 1)
            self.assertEqual(
                len(await second_kernel.history(types=["decision.reauthorized"])),
                1,
            )
            await agent.stop()
            await second_kernel.stop()

            third_kernel = NoemaKernel(store=SQLiteEventStore(path))
            restarted = AutonomousAgent(
                config=AutonomousAgentConfig(agent_id="billing-agent"),
                kernel=third_kernel,
                controller=CognitiveController(RuleBasedReasoner()),
                capabilities=registry,
                policy=PolicyEngine(),
            )
            await restarted.start()
            self.assertEqual(invocation_attempts, 1)
            await restarted.stop()
            await third_kernel.stop()

    async def test_recovery_does_not_replay_non_idempotent_capability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite3"
            intent = ActionIntent(
                "send_payment",
                {"invoice": "42"},
                expected_value=10,
                attention_cost=1,
                confidence=0.9,
                idempotency_key="payment:42:v1",
            )
            first_kernel = NoemaKernel(store=SQLiteEventStore(path))
            await first_kernel.start()
            await first_kernel.emit(
                Event(
                    "decision.authorized",
                    "billing-agent",
                    {"intent": intent.to_payload(), "reason": "authorized"},
                    subject=intent.intent_id,
                )
            )
            await first_kernel.stop()

            calls = 0

            async def send_payment(arguments, context):
                nonlocal calls
                calls += 1
                return CapabilityResult.ok({"invoice": arguments["invoice"]})

            registry = CapabilityRegistry()
            registry.register_function(
                CapabilitySpec(
                    "send_payment",
                    "Send a payment",
                    idempotent=False,
                    max_retries=3,
                ),
                send_payment,
            )
            recovered_kernel = NoemaKernel(store=SQLiteEventStore(path))
            agent = AutonomousAgent(
                config=AutonomousAgentConfig(agent_id="billing-agent"),
                kernel=recovered_kernel,
                controller=CognitiveController(RuleBasedReasoner()),
                capabilities=registry,
                policy=PolicyEngine(),
            )
            await agent.start()
            self.assertEqual(calls, 0)
            abandoned = await recovered_kernel.history(types=["action.abandoned"])
            self.assertEqual(len(abandoned), 1)
            self.assertIn("non-idempotent", str(abandoned[0].payload["reason"]))
            await agent.stop()
            await recovered_kernel.stop()
