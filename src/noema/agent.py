"""Long-running autonomous agent runtime."""

from __future__ import annotations

import asyncio
import fnmatch
import random
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .attention import AttentionAccount, AttentionAllocator, WorkItem
from .authority import ActionIntent, PolicyEngine
from .capabilities import CapabilityContext, CapabilityRegistry, CapabilityResult
from .events import Event
from .kernel import NoemaKernel
from .reasoning import ActionOutcome, CognitiveController, DecisionTrace, DeliberationRequest
from .telemetry import InMemoryTelemetry, Metric, TelemetrySink
from .types import utc_now


@dataclass(frozen=True, slots=True)
class AutonomousAgentConfig:
    agent_id: str
    trigger_patterns: tuple[str, ...] = (
        "external.*",
        "signal.*",
        "fact.*",
        "goal.*",
        "commitment.*",
        "risk.*",
        "opportunity.*",
        "timer.*",
    )
    ignored_patterns: tuple[str, ...] = (
        "agent.*",
        "decision.*",
        "action.*",
        "trace.*",
        "telemetry.*",
    )
    workers: int = 1
    max_concurrent_actions: int = 4
    max_actions_per_cycle: int = 4
    attention_capacity: float = 100.0
    attention_budget_per_cycle: float = 20.0
    queue_size: int = 1000
    heartbeat_seconds: float | None = None
    retry_backoff_seconds: float = 0.25
    retry_jitter_fraction: float = 0.2
    processed_event_cache: int = 10_000

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id must be non-empty")
        if self.workers <= 0:
            raise ValueError("workers must be positive")
        if self.max_concurrent_actions <= 0:
            raise ValueError("max_concurrent_actions must be positive")
        if self.max_actions_per_cycle <= 0:
            raise ValueError("max_actions_per_cycle must be positive")
        if self.attention_capacity <= 0 or self.attention_budget_per_cycle <= 0:
            raise ValueError("attention budgets must be positive")
        if not 0.0 <= self.retry_jitter_fraction <= 1.0:
            raise ValueError("retry_jitter_fraction must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class AgentStatus:
    agent_id: str
    running: bool
    queued_events: int
    active_actions: int
    attention_available: float
    processed_events: int


class AutonomousAgent:
    """Situation-aware, event-driven, self-triggering autonomous agent.

    The agent receives material events, reconstructs the current situation,
    deliberates asynchronously, allocates finite attention across proposals,
    authorizes actions through policy, executes typed capabilities, persists
    every transition, and can reflect on its own outcomes.
    """

    def __init__(
        self,
        *,
        config: AutonomousAgentConfig,
        kernel: NoemaKernel,
        controller: CognitiveController,
        capabilities: CapabilityRegistry,
        policy: PolicyEngine,
        attention_allocator: AttentionAllocator | None = None,
        telemetry: TelemetrySink | None = None,
    ) -> None:
        self.config = config
        self.kernel = kernel
        self.controller = controller
        self.capabilities = capabilities
        self.policy = policy
        self.attention_allocator = attention_allocator or AttentionAllocator()
        self.telemetry = telemetry or InMemoryTelemetry()
        self.attention = AttentionAccount(config.attention_capacity)

        self._queue: asyncio.PriorityQueue[tuple[int, int, Event | None]] = asyncio.PriorityQueue(
            maxsize=config.queue_size
        )
        self._queue_counter = 0
        self._workers: list[asyncio.Task[None]] = []
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._subscription_id: str | None = None
        self._action_semaphore = asyncio.Semaphore(config.max_concurrent_actions)
        self._active_actions = 0
        self._running = False
        self._stopping = False
        self._seen_ids: set[str] = set()
        self._seen_order: deque[str] = deque()
        self._seen_lock = asyncio.Lock()
        self._idempotency_ledger: dict[str, CapabilityResult] = {}

    @property
    def agent_id(self) -> str:
        return self.config.agent_id

    @property
    def running(self) -> bool:
        return self._running and not self._stopping

    def status(self) -> AgentStatus:
        return AgentStatus(
            agent_id=self.agent_id,
            running=self.running,
            queued_events=self._queue.qsize(),
            active_actions=self._active_actions,
            attention_available=self.attention.available,
            processed_events=len(self._seen_ids),
        )

    async def start(self) -> None:
        if self._running:
            return
        await self.kernel.start()
        self._stopping = False
        self._subscription_id = await self.kernel.bus.subscribe("*", self._on_event)
        self._workers = [
            asyncio.create_task(
                self._worker(index),
                name=f"noema-agent:{self.agent_id}:worker:{index}",
            )
            for index in range(self.config.workers)
        ]
        if self.config.heartbeat_seconds is not None:
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(),
                name=f"noema-agent:{self.agent_id}:heartbeat",
            )
        self._running = True
        started_event = await self.kernel.emit(
            Event(
                type="agent.started",
                source=self.agent_id,
                subject=self.agent_id,
                payload={"workers": self.config.workers},
            )
        )
        await self._restore_execution_state(started_event)

    async def stop(self, *, graceful: bool = True) -> None:
        if not self._running or self._stopping:
            return
        self._stopping = True
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            await asyncio.gather(self._heartbeat_task, return_exceptions=True)
            self._heartbeat_task = None
        if self._subscription_id is not None:
            await self.kernel.bus.unsubscribe(self._subscription_id)
            self._subscription_id = None
        if graceful:
            await self._queue.join()
        for _ in self._workers:
            self._queue_counter += 1
            await self._queue.put((0, self._queue_counter, None))
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._running = False
        await self.kernel.emit(
            Event(
                type="agent.stopped",
                source=self.agent_id,
                subject=self.agent_id,
                payload={},
            )
        )
        await self.telemetry.close()

    async def wait_until_idle(self, *, timeout: float = 5.0) -> None:
        async with asyncio.timeout(timeout):
            while True:
                await self.kernel.bus.drain()
                await self._queue.join()
                if self._queue.empty() and self._active_actions == 0:
                    # A final loop turn lets action-emitted events reach the queue.
                    await asyncio.sleep(0)
                    await self.kernel.bus.drain()
                    if self._queue.empty() and self._active_actions == 0:
                        return
                await asyncio.sleep(0.01)

    async def _on_event(self, event: Event) -> None:
        if not self._material(event):
            return
        async with self._seen_lock:
            if event.id in self._seen_ids:
                return
            self._seen_ids.add(event.id)
            self._seen_order.append(event.id)
            while len(self._seen_order) > self.config.processed_event_cache:
                old = self._seen_order.popleft()
                self._seen_ids.discard(old)
            self._queue_counter += 1
            counter = self._queue_counter
        await self._queue.put((-event.priority, counter, event))

    def _material(self, event: Event) -> bool:
        if any(
            fnmatch.fnmatchcase(event.type, pattern) for pattern in self.config.ignored_patterns
        ):
            return False
        return any(
            fnmatch.fnmatchcase(event.type, pattern) for pattern in self.config.trigger_patterns
        )

    async def _worker(self, index: int) -> None:
        del index
        while True:
            _, _, trigger = await self._queue.get()
            try:
                if trigger is None:
                    return
                try:
                    await self._handle_trigger(trigger)
                except asyncio.CancelledError:
                    raise
                except BaseException as exc:
                    await self.kernel.emit(
                        Event(
                            type="agent.cycle_failed",
                            source=self.agent_id,
                            subject=self.agent_id,
                            correlation_id=trigger.correlation_id or trigger.id,
                            causation_id=trigger.id,
                            payload={
                                "trigger_id": trigger.id,
                                "trigger_type": trigger.type,
                                "error": repr(exc),
                            },
                        )
                    )
            finally:
                self._queue.task_done()

    async def _handle_trigger(self, trigger: Event) -> None:
        async with self.kernel.tracer.span(
            "noema.agent.cycle",
            {
                "noema.agent_id": self.agent_id,
                "noema.trigger_id": trigger.id,
                "noema.trigger_type": trigger.type,
                "noema.correlation_id": trigger.correlation_id or trigger.id,
            },
        ):
            snapshot = await self.kernel.snapshot()
            request = DeliberationRequest(
                agent_id=self.agent_id,
                trigger=trigger,
                situation=snapshot,
                capabilities=self.capabilities.specs(),
                attention_available=min(
                    self.attention.available,
                    self.config.attention_budget_per_cycle,
                ),
            )
            trace = await self.controller.deliberate(request)
            await self._emit_decision_trace(trace)

            accepted = trace.accepted_intents
            if not accepted:
                return
            work_items = [self._intent_to_work_item(intent) for intent in accepted]
            selected = self.attention_allocator.select(
                work_items,
                min(self.attention.available, self.config.attention_budget_per_cycle),
            )[: self.config.max_actions_per_cycle]
            selected_intents = [
                item.payload for item in selected if isinstance(item.payload, ActionIntent)
            ]

            tasks: list[asyncio.Task[ActionOutcome | None]] = []
            for intent in selected_intents:
                capability = self.capabilities.get(intent.capability)
                async with self.kernel.tracer.span(
                    "noema.action.authorize",
                    {
                        "noema.agent_id": self.agent_id,
                        "noema.intent_id": intent.intent_id,
                        "noema.capability": intent.capability,
                    },
                ) as span:
                    authorization = self.policy.authorize(intent, capability.spec, snapshot)
                    span.set_attribute("noema.authorization.allowed", authorization.allowed)
                event_type = "decision.authorized" if authorization.allowed else "decision.denied"
                authorization_event = await self.kernel.emit(
                    Event(
                        type=event_type,
                        source=self.agent_id,
                        subject=intent.intent_id,
                        correlation_id=trigger.correlation_id or trigger.id,
                        causation_id=trigger.id,
                        payload={
                            "intent": intent.to_payload(),
                            "reason": authorization.reason,
                            "effective_authority": int(authorization.effective_authority),
                            "effective_risk": int(authorization.effective_risk),
                        },
                    )
                )
                if not authorization.allowed:
                    await self.telemetry.record(
                        Metric("decision.denied", 1.0, {"agent": self.agent_id})
                    )
                    continue
                lease = await self.attention.acquire(intent.attention_cost)
                if lease is None:
                    await self.kernel.emit(
                        Event(
                            type="decision.deferred",
                            source=self.agent_id,
                            subject=intent.intent_id,
                            correlation_id=authorization_event.correlation_id,
                            causation_id=authorization_event.id,
                            payload={
                                "reason": "insufficient concurrent attention capacity",
                                "intent": intent.to_payload(),
                            },
                        )
                    )
                    continue
                tasks.append(
                    asyncio.create_task(
                        self._execute_with_lease(intent, request, authorization_event, lease),
                        name=(
                            f"noema-action:{self.agent_id}:{intent.capability}:{intent.intent_id}"
                        ),
                    )
                )

            if tasks:
                outcomes = await asyncio.gather(*tasks, return_exceptions=False)
                for outcome in outcomes:
                    if outcome is None:
                        continue
                    reflection_events = await self.controller.reflect(outcome, request)
                    for event in reflection_events:
                        linked = event.caused_by(
                            trigger,
                            source=event.source or self.agent_id,
                        )
                        await self.kernel.emit(linked)

    async def _execute_with_lease(
        self,
        intent: ActionIntent,
        request: DeliberationRequest,
        authorization_event: Event,
        lease: Any,
    ) -> ActionOutcome | None:
        async with lease:
            async with self._action_semaphore:
                self._active_actions += 1
                try:
                    return await self._execute_intent(intent, request, authorization_event)
                finally:
                    self._active_actions -= 1

    async def _execute_intent(
        self,
        intent: ActionIntent,
        request: DeliberationRequest,
        authorization_event: Event,
    ) -> ActionOutcome | None:
        capability = self.capabilities.get(intent.capability)
        if intent.idempotency_key is not None:
            previous = self._idempotency_ledger.get(intent.idempotency_key)
            if previous is not None and previous.success:
                await self.kernel.emit(
                    Event(
                        type="action.skipped",
                        source=self.agent_id,
                        subject=intent.intent_id,
                        correlation_id=authorization_event.correlation_id,
                        causation_id=authorization_event.id,
                        payload={
                            "reason": "idempotency key already succeeded",
                            "idempotency_key": intent.idempotency_key,
                        },
                    )
                )
                return None

        dispatched_event = await self.kernel.emit(
            Event(
                type="action.dispatched",
                source=self.agent_id,
                subject=intent.intent_id,
                correlation_id=authorization_event.correlation_id,
                causation_id=authorization_event.id,
                payload={
                    "intent": intent.to_payload(),
                    "idempotency_key": intent.idempotency_key,
                },
            )
        )
        started_at = utc_now()
        started_event = await self.kernel.emit(
            Event(
                type="action.started",
                source=self.agent_id,
                subject=intent.intent_id,
                correlation_id=authorization_event.correlation_id,
                causation_id=dispatched_event.id,
                payload={
                    "intent": intent.to_payload(),
                    "idempotency_key": intent.idempotency_key,
                },
            )
        )
        await self.telemetry.record(Metric("action.started", 1.0, {"agent": self.agent_id}))

        attempts = 0
        result = CapabilityResult.fail("capability was not invoked")
        max_retries = capability.spec.max_retries if capability.spec.idempotent else 0
        while attempts <= max_retries:
            attempts += 1
            context = CapabilityContext(
                agent_id=self.agent_id,
                trigger=request.trigger,
                situation=request.situation,
                emit=self.kernel.emit,
                attempt=attempts,
                idempotency_key=intent.idempotency_key,
            )
            try:
                async with self.kernel.tracer.span(
                    "noema.capability.invoke",
                    {
                        "noema.agent_id": self.agent_id,
                        "noema.intent_id": intent.intent_id,
                        "noema.capability": intent.capability,
                        "noema.action_attempt": attempts,
                        "noema.correlation_id": started_event.correlation_id or started_event.id,
                    },
                ) as span:
                    try:
                        async with asyncio.timeout(capability.spec.timeout_seconds):
                            result = await capability.invoke(intent.arguments, context)
                    except BaseException as exc:
                        span.record_exception(exc)
                        raise
            except TimeoutError:
                result = CapabilityResult.fail(
                    f"capability timed out after {capability.spec.timeout_seconds}s",
                    retryable=True,
                )
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                result = CapabilityResult.fail(repr(exc), retryable=False)

            if result.success or not result.retryable or attempts > max_retries:
                break
            backoff = self.config.retry_backoff_seconds * (2 ** (attempts - 1))
            jitter = random.uniform(
                -self.config.retry_jitter_fraction,
                self.config.retry_jitter_fraction,
            )
            await asyncio.sleep(max(0.0, backoff * (1.0 + jitter)))

        finished_at = utc_now()
        outcome = ActionOutcome(intent, result, attempts, started_at, finished_at)
        if result.success:
            completed_event = await self.kernel.emit(
                Event(
                    type="action.succeeded",
                    source=self.agent_id,
                    subject=intent.intent_id,
                    correlation_id=started_event.correlation_id,
                    causation_id=started_event.id,
                    payload={
                        "capability": intent.capability,
                        "attempts": attempts,
                        "output": dict(result.output),
                        "idempotency_key": intent.idempotency_key,
                        "duration_seconds": (finished_at - started_at).total_seconds(),
                    },
                )
            )
            if intent.idempotency_key is not None:
                self._idempotency_ledger[intent.idempotency_key] = result
            for key, value in result.facts.items():
                await self.kernel.emit(
                    Event(
                        type="fact.observed",
                        source=self.agent_id,
                        subject=key,
                        correlation_id=completed_event.correlation_id,
                        causation_id=completed_event.id,
                        payload={"key": key, "value": value, "confidence": 1.0},
                    )
                )
            for event in result.events:
                await self.kernel.emit(event.caused_by(completed_event))
            await self.telemetry.record(
                Metric(
                    "action.succeeded",
                    1.0,
                    {"agent": self.agent_id, "capability": intent.capability},
                )
            )
            return outcome

        failed_event = await self.kernel.emit(
            Event(
                type="action.failed",
                source=self.agent_id,
                subject=intent.intent_id,
                correlation_id=started_event.correlation_id,
                causation_id=started_event.id,
                payload={
                    "capability": intent.capability,
                    "attempts": attempts,
                    "error": result.error,
                    "retryable": result.retryable,
                    "idempotency_key": intent.idempotency_key,
                    "duration_seconds": (finished_at - started_at).total_seconds(),
                },
            )
        )
        await self.telemetry.record(
            Metric(
                "action.failed",
                1.0,
                {"agent": self.agent_id, "capability": intent.capability},
            )
        )
        if bool(intent.metadata.get("compensate_on_failure")) and capability.spec.reversible:
            context = CapabilityContext(
                agent_id=self.agent_id,
                trigger=request.trigger,
                situation=request.situation,
                emit=self.kernel.emit,
                attempt=attempts,
                idempotency_key=intent.idempotency_key,
            )
            compensation = await capability.compensate(intent.arguments, result, context)
            await self.kernel.emit(
                Event(
                    type=(
                        "action.compensated"
                        if compensation.success
                        else "action.compensation_failed"
                    ),
                    source=self.agent_id,
                    subject=intent.intent_id,
                    correlation_id=failed_event.correlation_id,
                    causation_id=failed_event.id,
                    payload={
                        "success": compensation.success,
                        "output": dict(compensation.output),
                        "error": compensation.error,
                    },
                )
            )
        return outcome

    async def _restore_execution_state(self, started_event: Event) -> None:
        """Recover durable idempotency state and unfinished authorized actions."""

        lifecycle_types = (
            "decision.authorized",
            "action.succeeded",
            "action.failed",
            "action.skipped",
            "action.compensated",
            "action.compensation_failed",
            "action.abandoned",
        )
        history = await self.kernel.history(types=lifecycle_types)
        authorized: dict[str, tuple[Event, ActionIntent]] = {}
        terminal: set[str] = set()
        for event in history:
            if event.source != self.agent_id or event.subject is None:
                continue
            if event.type == "decision.authorized":
                raw_intent = event.payload.get("intent")
                if isinstance(raw_intent, dict):
                    authorized[event.subject] = (
                        event,
                        ActionIntent.from_payload(raw_intent),
                    )
                continue
            if event.type == "action.succeeded":
                key = event.payload.get("idempotency_key")
                output = event.payload.get("output")
                if isinstance(key, str):
                    self._idempotency_ledger[key] = CapabilityResult.ok(
                        output if isinstance(output, dict) else {}
                    )
            terminal.add(event.subject)

        pending = [pair for intent_id, pair in authorized.items() if intent_id not in terminal]
        pending.sort(key=lambda pair: pair[0].sequence or 0)
        for authorization_event, intent in pending:
            if intent.capability not in self.capabilities:
                await self.kernel.emit(
                    Event(
                        type="action.abandoned",
                        source=self.agent_id,
                        subject=intent.intent_id,
                        correlation_id=authorization_event.correlation_id,
                        causation_id=started_event.id,
                        payload={
                            "reason": "capability unavailable during crash recovery",
                            "capability": intent.capability,
                        },
                    )
                )
                continue
            snapshot = await self.kernel.snapshot()
            capability = self.capabilities.get(intent.capability)
            if not capability.spec.idempotent:
                await self.kernel.emit(
                    Event(
                        type="action.abandoned",
                        source=self.agent_id,
                        subject=intent.intent_id,
                        correlation_id=authorization_event.correlation_id,
                        causation_id=started_event.id,
                        payload={
                            "reason": (
                                "non-idempotent capability requires explicit "
                                "operator reconciliation after crash"
                            ),
                            "capability": intent.capability,
                            "idempotency_key": intent.idempotency_key,
                        },
                    )
                )
                continue
            authorization = self.policy.authorize(intent, capability.spec, snapshot)
            if not authorization.allowed:
                await self.kernel.emit(
                    Event(
                        type="action.abandoned",
                        source=self.agent_id,
                        subject=intent.intent_id,
                        correlation_id=authorization_event.correlation_id,
                        causation_id=started_event.id,
                        payload={
                            "reason": f"recovery reauthorization failed: {authorization.reason}",
                            "capability": intent.capability,
                        },
                    )
                )
                continue
            reauthorization_event = await self.kernel.emit(
                Event(
                    type="decision.reauthorized",
                    source=self.agent_id,
                    subject=intent.intent_id,
                    correlation_id=authorization_event.correlation_id,
                    causation_id=started_event.id,
                    payload={
                        "original_authorization_event_id": authorization_event.id,
                        "reason": authorization.reason,
                        "effective_authority": int(authorization.effective_authority),
                        "effective_risk": int(authorization.effective_risk),
                    },
                )
            )
            recovery_event = await self.kernel.emit(
                Event(
                    type="action.recovery_requested",
                    source=self.agent_id,
                    subject=intent.intent_id,
                    correlation_id=authorization_event.correlation_id,
                    causation_id=reauthorization_event.id,
                    payload={
                        "authorization_event_id": authorization_event.id,
                        "intent": intent.to_payload(),
                    },
                )
            )
            request = DeliberationRequest(
                agent_id=self.agent_id,
                trigger=recovery_event,
                situation=snapshot,
                capabilities=self.capabilities.specs(),
                attention_available=min(
                    self.attention.available,
                    self.config.attention_budget_per_cycle,
                ),
                metadata={"recovery": True},
            )
            lease = await self.attention.acquire(intent.attention_cost)
            if lease is None:
                continue
            outcome = await self._execute_with_lease(
                intent,
                request,
                recovery_event,
                lease,
            )
            if outcome is not None:
                for reflection_event in await self.controller.reflect(outcome, request):
                    await self.kernel.emit(reflection_event.caused_by(recovery_event))

    async def _emit_decision_trace(self, trace: DecisionTrace) -> None:
        trigger = trace.request.trigger
        await self.kernel.emit(
            Event(
                type="decision.proposed",
                source=self.agent_id,
                subject=self.agent_id,
                correlation_id=trigger.correlation_id or trigger.id,
                causation_id=trigger.id,
                payload={
                    "trigger_type": trigger.type,
                    "modes": [mode.value for mode in trace.result.modes],
                    "proposed": len(trace.result.intents),
                    "intents": [intent.to_payload() for intent in trace.result.intents],
                    "accepted_after_critique": len(trace.accepted_intents),
                    "hypotheses": [
                        {
                            "statement": hypothesis.statement,
                            "probability": hypothesis.probability,
                            "falsifiers": list(hypothesis.falsifiers),
                        }
                        for hypothesis in trace.result.hypotheses
                    ],
                    "reviews": [
                        {
                            "intent_id": review.original.intent_id,
                            "approved": review.approved,
                            "critiques": [
                                {"approved": critique.approved, "reason": critique.reason}
                                for critique in review.critiques
                            ],
                        }
                        for review in trace.reviews
                    ],
                    "duration_seconds": (trace.finished_at - trace.started_at).total_seconds(),
                },
            )
        )
        await self.telemetry.record(Metric("decision.cycle", 1.0, {"agent": self.agent_id}))

    @staticmethod
    def _intent_to_work_item(intent: ActionIntent) -> WorkItem:
        urgency_value = intent.metadata.get("urgency", 0.0)
        maintenance_value_raw = intent.metadata.get("maintenance_value", 0.0)
        urgency = float(urgency_value) if isinstance(urgency_value, (int, float)) else 0.0
        maintenance_value = (
            float(maintenance_value_raw) if isinstance(maintenance_value_raw, (int, float)) else 0.0
        )
        deadline_value = intent.metadata.get("deadline")
        deadline: datetime | None = None
        if isinstance(deadline_value, str):
            deadline = datetime.fromisoformat(deadline_value)
        return WorkItem(
            key=intent.intent_id,
            impact=intent.expected_value,
            urgency=urgency,
            information_value=intent.information_value,
            risk_reduction=intent.risk_reduction,
            maintenance_value=maintenance_value,
            attention_cost=intent.attention_cost,
            switching_cost=intent.switching_cost,
            branch_cost=intent.branch_cost,
            deadline=deadline,
            payload=intent,
        )

    async def _heartbeat_loop(self) -> None:
        assert self.config.heartbeat_seconds is not None
        while True:
            await asyncio.sleep(self.config.heartbeat_seconds)
            await self.kernel.emit(
                Event(
                    type="timer.heartbeat",
                    source=self.agent_id,
                    subject=self.agent_id,
                    payload={"agent_id": self.agent_id},
                )
            )
