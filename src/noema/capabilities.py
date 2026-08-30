"""Typed executable capabilities exposed to autonomous agents."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from .authority import AuthorityLevel, RiskLevel
from .events import Event
from .situation import SituationSnapshot
from .types import JSONValue


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    name: str
    description: str
    input_schema: Mapping[str, JSONValue] = field(default_factory=dict)
    output_schema: Mapping[str, JSONValue] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    reversible: bool = True
    idempotent: bool = True
    required_authority: AuthorityLevel = AuthorityLevel.ACT_REVERSIBLE
    timeout_seconds: float = 30.0
    max_retries: int = 0
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("capability name must be non-empty")
        if self.timeout_seconds <= 0:
            raise ValueError("capability timeout must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    success: bool
    output: Mapping[str, JSONValue] = field(default_factory=dict)
    facts: Mapping[str, JSONValue] = field(default_factory=dict)
    events: tuple[Event, ...] = ()
    error: str | None = None
    retryable: bool = False

    @classmethod
    def ok(
        cls,
        output: Mapping[str, JSONValue] | None = None,
        *,
        facts: Mapping[str, JSONValue] | None = None,
        events: Sequence[Event] = (),
    ) -> "CapabilityResult":
        return cls(
            True,
            dict(output or {}),
            dict(facts or {}),
            tuple(events),
        )

    @classmethod
    def fail(cls, error: str, *, retryable: bool = False) -> "CapabilityResult":
        return cls(False, error=error, retryable=retryable)


EmitFunction = Callable[[Event], Awaitable[Event]]


@dataclass(frozen=True, slots=True)
class CapabilityContext:
    agent_id: str
    trigger: Event
    situation: SituationSnapshot
    emit: EmitFunction
    attempt: int = 1


class Capability(Protocol):
    spec: CapabilitySpec

    async def invoke(
        self,
        arguments: Mapping[str, JSONValue],
        context: CapabilityContext,
    ) -> CapabilityResult: ...

    async def compensate(
        self,
        arguments: Mapping[str, JSONValue],
        result: CapabilityResult,
        context: CapabilityContext,
    ) -> CapabilityResult: ...


CapabilityFunction = Callable[
    [Mapping[str, JSONValue], CapabilityContext],
    CapabilityResult | Awaitable[CapabilityResult],
]
CompensationFunction = Callable[
    [Mapping[str, JSONValue], CapabilityResult, CapabilityContext],
    CapabilityResult | Awaitable[CapabilityResult],
]


class FunctionCapability:
    def __init__(
        self,
        spec: CapabilitySpec,
        function: CapabilityFunction,
        *,
        compensation: CompensationFunction | None = None,
    ) -> None:
        self.spec = spec
        self._function = function
        self._compensation = compensation

    async def invoke(
        self,
        arguments: Mapping[str, JSONValue],
        context: CapabilityContext,
    ) -> CapabilityResult:
        result = self._function(arguments, context)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, CapabilityResult):
            raise TypeError("capability functions must return CapabilityResult")
        return result

    async def compensate(
        self,
        arguments: Mapping[str, JSONValue],
        result: CapabilityResult,
        context: CapabilityContext,
    ) -> CapabilityResult:
        if self._compensation is None:
            return CapabilityResult.fail("no compensation is defined")
        compensated = self._compensation(arguments, result, context)
        if inspect.isawaitable(compensated):
            compensated = await compensated
        if not isinstance(compensated, CapabilityResult):
            raise TypeError("compensation functions must return CapabilityResult")
        return compensated


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability, *, replace: bool = False) -> None:
        name = capability.spec.name
        if name in self._capabilities and not replace:
            raise ValueError(f"capability already registered: {name}")
        self._capabilities[name] = capability

    def register_function(
        self,
        spec: CapabilitySpec,
        function: CapabilityFunction,
        *,
        compensation: CompensationFunction | None = None,
        replace: bool = False,
    ) -> FunctionCapability:
        capability = FunctionCapability(spec, function, compensation=compensation)
        self.register(capability, replace=replace)
        return capability

    def get(self, name: str) -> Capability:
        try:
            return self._capabilities[name]
        except KeyError as exc:
            raise KeyError(f"unknown capability: {name}") from exc

    def specs(self) -> tuple[CapabilitySpec, ...]:
        return tuple(capability.spec for capability in self._capabilities.values())

    def __contains__(self, name: object) -> bool:
        return name in self._capabilities

    def __len__(self) -> int:
        return len(self._capabilities)
