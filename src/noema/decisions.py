"""Typed judgments, deliberately separate from generation and action authority.

Probabilities describe the requested classification, not future outcomes. Provider
confidence is a distribution summary, not a calibrated guarantee or permission.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal, Protocol, TypeAlias

from .models import ModelUsage


class DecisionError(RuntimeError):
    """A decision request failed; messages never contain provider response bodies."""


class DecisionCapabilityError(DecisionError):
    """The configured route cannot represent the requested operation."""


class DecisionResponseError(DecisionError):
    """The provider returned an invalid or inconsistent typed response."""


class DecisionHTTPError(DecisionError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"Decision endpoint returned HTTP {status_code}")


class DecisionTimeoutError(DecisionError):
    """The overall deadline expired; remote work may already have been charged."""


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


@dataclass(frozen=True, slots=True)
class ChoiceOption:
    value: str | bool
    description: str | None = None

    def __post_init__(self) -> None:
        if type(self.value) not in (str, bool):
            raise ValueError("choice values must be strings or booleans")
        if self.description is not None and not isinstance(self.description, str):
            raise ValueError("choice description must be text")


@dataclass(frozen=True, slots=True)
class ScoreLevel:
    label: str
    description: str | None = None

    def __post_init__(self) -> None:
        _text(self.label, "label")
        if self.description is not None and not isinstance(self.description, str):
            raise ValueError("level description must be text")


@dataclass(frozen=True, slots=True)
class PredicateQuestion:
    name: str
    instructions: str

    def __post_init__(self) -> None:
        _text(self.name, "name")
        _text(self.instructions, "instructions")


@dataclass(frozen=True, slots=True)
class ChoiceQuestion:
    name: str
    instructions: str
    choices: tuple[ChoiceOption, ...]

    def __post_init__(self) -> None:
        _text(self.name, "name")
        _text(self.instructions, "instructions")
        object.__setattr__(self, "choices", tuple(self.choices))
        if not 2 <= len(self.choices) <= 255:
            raise ValueError("choice requires 2 to 255 options")
        if not all(isinstance(c, ChoiceOption) for c in self.choices):
            raise ValueError("choices must contain ChoiceOption objects")
        if len({(type(c.value), c.value) for c in self.choices}) != len(self.choices):
            raise ValueError("choice values must be unique")


@dataclass(frozen=True, slots=True)
class ScoreQuestion:
    name: str
    instructions: str
    levels: tuple[ScoreLevel, ...]

    def __post_init__(self) -> None:
        _text(self.name, "name")
        _text(self.instructions, "instructions")
        object.__setattr__(self, "levels", tuple(self.levels))
        if not 2 <= len(self.levels) <= 10:
            raise ValueError("score requires 2 to 10 levels")
        if not all(isinstance(level, ScoreLevel) for level in self.levels):
            raise ValueError("levels must contain ScoreLevel objects")
        if len({level.label for level in self.levels}) != len(self.levels):
            raise ValueError("score labels must be unique")


DecisionQuestion: TypeAlias = PredicateQuestion | ChoiceQuestion | ScoreQuestion


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    input: str
    questions: tuple[DecisionQuestion, ...]
    rubric_version: str = "v1"

    def __post_init__(self) -> None:
        if not isinstance(self.input, str):
            raise DecisionCapabilityError("This portable decision boundary accepts text input only")
        _text(self.rubric_version, "rubric_version")
        object.__setattr__(self, "questions", tuple(self.questions))
        if not 1 <= len(self.questions) <= 128:
            raise ValueError("a request requires 1 to 128 independent questions")
        if not all(
            isinstance(q, PredicateQuestion | ChoiceQuestion | ScoreQuestion)
            for q in self.questions
        ):
            raise DecisionCapabilityError("Unsupported decision question type")
        if len({q.name for q in self.questions}) != len(self.questions):
            raise ValueError("question names must be unique")

    def fingerprint(self) -> str:
        data = asdict(self)
        data["question_types"] = [type(q).__name__ for q in self.questions]
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class PredicateAnswer:
    name: str
    probability: float


@dataclass(frozen=True, slots=True)
class ChoiceProbability:
    value: str | bool
    probability: float


@dataclass(frozen=True, slots=True)
class ChoiceAnswer:
    name: str
    choice: str | bool
    probabilities: tuple[ChoiceProbability, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class ScoreProbability:
    value: int
    label: str
    probability: float


@dataclass(frozen=True, slots=True)
class ScoreAnswer:
    name: str
    score: float
    probabilities: tuple[ScoreProbability, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class RefusalAnswer:
    name: str


DecisionAnswer: TypeAlias = PredicateAnswer | ChoiceAnswer | ScoreAnswer | RefusalAnswer


@dataclass(frozen=True, slots=True)
class DecisionCapabilities:
    predicate: bool = True
    choice: bool = True
    score: bool = True
    boolean_choices: bool = True
    vision: bool = False
    streaming: bool = False


@dataclass(frozen=True, slots=True)
class DecisionProvenance:
    provider: str
    requested_model: str
    response_model: str
    transport: str
    request_fingerprint: str
    rubric_version: str
    attempts: int
    # An injected transport is not evidence of live inference.
    origin: Literal["http", "injected_transport", "fixture"]
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionResponse:
    answers: tuple[DecisionAnswer, ...]
    provenance: DecisionProvenance
    usage: ModelUsage
    latency_seconds: float


class DecisionProvider(Protocol):
    name: str
    model: str
    capabilities: DecisionCapabilities

    async def decide(self, request: DecisionRequest) -> DecisionResponse: ...
