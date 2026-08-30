"""Provider-agnostic cognition and metacontrol.

Reasoning is a replaceable async interface. The core can host deterministic
rules, LLM-backed reasoners, search/planning systems, ensembles, or hybrids.
The controller makes cognitive modes and critiques observable rather than
burying them inside an opaque prompt.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from .authority import ActionIntent, RiskLevel
from .capabilities import CapabilityResult, CapabilitySpec
from .events import Event
from .situation import SituationSnapshot
from .types import JSONValue, utc_now


class CognitiveMode(StrEnum):
    OBSERVE = "observe"
    EXPAND = "expand"
    STRUCTURE = "structure"
    FORMALIZE = "formalize"
    FALSIFY = "falsify"
    OPERATIONALIZE = "operationalize"
    GOVERN = "govern"
    REOPEN = "reopen"
    RESTORE = "restore"


@dataclass(frozen=True, slots=True)
class Hypothesis:
    statement: str
    probability: float
    evidence_for: tuple[str, ...] = ()
    evidence_against: tuple[str, ...] = ()
    falsifiers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.probability <= 1:
            raise ValueError("hypothesis probability must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class DeliberationRequest:
    agent_id: str
    trigger: Event
    situation: SituationSnapshot
    capabilities: tuple[CapabilitySpec, ...]
    attention_available: float
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeliberationResult:
    intents: tuple[ActionIntent, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    alternatives: tuple[str, ...] = ()
    modes: tuple[CognitiveMode, ...] = (
        CognitiveMode.OBSERVE,
        CognitiveMode.OPERATIONALIZE,
    )
    notes: tuple[str, ...] = ()
    confidence: float = 0.5


@dataclass(frozen=True, slots=True)
class Critique:
    approved: bool
    reason: str
    confidence_delta: float = 0.0
    revised_intent: ActionIntent | None = None


@dataclass(frozen=True, slots=True)
class IntentReview:
    original: ActionIntent
    final: ActionIntent | None
    critiques: tuple[Critique, ...]

    @property
    def approved(self) -> bool:
        return self.final is not None


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    request: DeliberationRequest
    result: DeliberationResult
    reviews: tuple[IntentReview, ...]
    started_at: datetime
    finished_at: datetime

    @property
    def accepted_intents(self) -> tuple[ActionIntent, ...]:
        return tuple(review.final for review in self.reviews if review.final is not None)


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    intent: ActionIntent
    result: CapabilityResult
    attempts: int
    started_at: datetime
    finished_at: datetime


class Reasoner(Protocol):
    async def deliberate(self, request: DeliberationRequest) -> DeliberationResult: ...


class ReflectiveReasoner(Protocol):
    async def reflect(
        self,
        outcome: ActionOutcome,
        request: DeliberationRequest,
    ) -> Sequence[Event]: ...


class Critic(Protocol):
    async def review(
        self,
        intent: ActionIntent,
        request: DeliberationRequest,
    ) -> Critique: ...


RuleReturn = ActionIntent | Sequence[ActionIntent] | None
Rule = Callable[[DeliberationRequest], RuleReturn | Awaitable[RuleReturn]]


class RuleBasedReasoner:
    """Deterministic async rule engine useful for tests and production control."""

    def __init__(self, rules: Sequence[Rule] = ()) -> None:
        self._rules = list(rules)

    def add_rule(self, rule: Rule) -> None:
        self._rules.append(rule)

    async def deliberate(self, request: DeliberationRequest) -> DeliberationResult:
        intents: list[ActionIntent] = []
        for rule in self._rules:
            result = rule(request)
            if inspect.isawaitable(result):
                result = await result
            if result is None:
                continue
            if isinstance(result, ActionIntent):
                intents.append(result)
            else:
                intents.extend(result)
        modes = [CognitiveMode.OBSERVE]
        if len(intents) > 1:
            modes.extend((CognitiveMode.EXPAND, CognitiveMode.STRUCTURE))
        if intents:
            modes.append(CognitiveMode.OPERATIONALIZE)
        return DeliberationResult(
            intents=tuple(intents),
            modes=tuple(modes),
            confidence=max((intent.confidence for intent in intents), default=0.5),
        )

    async def reflect(
        self,
        outcome: ActionOutcome,
        request: DeliberationRequest,
    ) -> Sequence[Event]:
        del outcome, request
        return ()


class CompositeReasoner:
    """Run multiple reasoners concurrently and merge their proposals."""

    def __init__(self, reasoners: Sequence[Reasoner]) -> None:
        if not reasoners:
            raise ValueError("CompositeReasoner requires at least one reasoner")
        self._reasoners = tuple(reasoners)

    async def deliberate(self, request: DeliberationRequest) -> DeliberationResult:
        import asyncio

        results = await asyncio.gather(
            *(reasoner.deliberate(request) for reasoner in self._reasoners)
        )
        modes: list[CognitiveMode] = [CognitiveMode.OBSERVE, CognitiveMode.EXPAND]
        intents: list[ActionIntent] = []
        hypotheses: list[Hypothesis] = []
        alternatives: list[str] = []
        notes: list[str] = []
        for result in results:
            intents.extend(result.intents)
            hypotheses.extend(result.hypotheses)
            alternatives.extend(result.alternatives)
            notes.extend(result.notes)
            for mode in result.modes:
                if mode not in modes:
                    modes.append(mode)
        if intents and CognitiveMode.OPERATIONALIZE not in modes:
            modes.append(CognitiveMode.OPERATIONALIZE)
        return DeliberationResult(
            intents=tuple(_deduplicate_intents(intents)),
            hypotheses=tuple(hypotheses),
            alternatives=tuple(dict.fromkeys(alternatives)),
            modes=tuple(modes),
            notes=tuple(notes),
            confidence=sum(result.confidence for result in results) / len(results),
        )


class OpportunityCostCritic:
    """Reject actions whose modeled benefits do not justify their resource cost."""

    def __init__(self, *, minimum_net_value: float = 0.0) -> None:
        self.minimum_net_value = minimum_net_value

    async def review(
        self,
        intent: ActionIntent,
        request: DeliberationRequest,
    ) -> Critique:
        del request
        benefit = intent.expected_value + intent.information_value + intent.risk_reduction
        cost = intent.attention_cost + intent.switching_cost + intent.branch_cost
        net = benefit - cost
        return Critique(
            approved=net >= self.minimum_net_value,
            reason=(
                f"net modeled value {net:.3f} meets threshold"
                if net >= self.minimum_net_value
                else f"net modeled value {net:.3f} is below threshold"
            ),
        )


class FalsificationCritic:
    """Require disconfirming conditions when consequences justify the cost."""

    def __init__(self, *, from_risk: RiskLevel = RiskLevel.HIGH) -> None:
        self.from_risk = from_risk

    async def review(
        self,
        intent: ActionIntent,
        request: DeliberationRequest,
    ) -> Critique:
        del request
        if intent.risk < self.from_risk or intent.falsifiers:
            return Critique(True, "falsification requirement satisfied")
        return Critique(False, "consequential action has no explicit falsifier")


class CapabilityExistenceCritic:
    async def review(
        self,
        intent: ActionIntent,
        request: DeliberationRequest,
    ) -> Critique:
        names = {capability.name for capability in request.capabilities}
        if intent.capability in names:
            return Critique(True, "capability is available")
        return Critique(False, f"capability is not available: {intent.capability}")


class CognitiveController:
    """Apply a reasoner, then independently review every proposed action."""

    def __init__(
        self,
        reasoner: Reasoner,
        *,
        critics: Sequence[Critic] = (),
    ) -> None:
        self.reasoner = reasoner
        self.critics = tuple(critics)

    async def deliberate(self, request: DeliberationRequest) -> DecisionTrace:
        started_at = utc_now()
        result = await self.reasoner.deliberate(request)
        reviews: list[IntentReview] = []
        for original in result.intents:
            current: ActionIntent | None = original
            critiques: list[Critique] = []
            for critic in self.critics:
                if current is None:
                    break
                critique = await critic.review(current, request)
                critiques.append(critique)
                if not critique.approved:
                    current = None
                    break
                if critique.revised_intent is not None:
                    current = critique.revised_intent
                elif critique.confidence_delta:
                    current = replace(
                        current,
                        confidence=min(
                            1.0, max(0.0, current.confidence + critique.confidence_delta)
                        ),
                    )
            reviews.append(IntentReview(original, current, tuple(critiques)))
        return DecisionTrace(
            request=request,
            result=result,
            reviews=tuple(reviews),
            started_at=started_at,
            finished_at=utc_now(),
        )

    async def reflect(
        self,
        outcome: ActionOutcome,
        request: DeliberationRequest,
    ) -> tuple[Event, ...]:
        reflect = getattr(self.reasoner, "reflect", None)
        if reflect is None:
            return ()
        events = reflect(outcome, request)
        if inspect.isawaitable(events):
            events = await events
        return tuple(events)


def _deduplicate_intents(intents: Sequence[ActionIntent]) -> list[ActionIntent]:
    seen: set[tuple[str, str | None, str]] = set()
    result: list[ActionIntent] = []
    for intent in intents:
        key = (intent.capability, intent.idempotency_key, repr(sorted(intent.arguments.items())))
        if key in seen:
            continue
        seen.add(key)
        result.append(intent)
    return result
