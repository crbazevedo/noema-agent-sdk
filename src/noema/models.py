"""Provider-neutral model contracts and structured reasoning adapters."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from .authority import ACTION_INTENT_JSON_SCHEMA, ActionIntent
from .reasoning import (
    CognitiveMode,
    DeliberationRequest,
    DeliberationResult,
    Hypothesis,
)
from .schema import validate_json_schema
from .types import JSONObject, JSONValue


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    structured_output: bool = False
    tool_calls: bool = False
    streaming: bool = False
    embeddings: bool = False
    vision: bool = False
    reasoning: bool = False
    context_limit: int | None = None
    batching: bool = False
    estimated_cost: float | None = None
    latency_class: str = "unknown"
    privacy_class: str = "provider"


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: str
    content: str

    def to_dict(self) -> JSONObject:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class ModelRequest:
    messages: tuple[ModelMessage, ...]
    response_schema: Mapping[str, JSONValue] | None = None
    schema_name: str = "noema_response"
    instructions: str | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None
    correlation_id: str | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("model request requires at least one message")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self, *, include_correlation: bool = True) -> JSONObject:
        data: JSONObject = {
            "messages": [message.to_dict() for message in self.messages],
            "response_schema": (
                dict(self.response_schema) if self.response_schema is not None else None
            ),
            "schema_name": self.schema_name,
            "instructions": self.instructions,
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "metadata": dict(self.metadata),
        }
        if include_correlation:
            data["correlation_id"] = self.correlation_id
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ModelRequest:
        values = cast(Mapping[str, Any], data)
        raw_messages = values.get("messages", [])
        if not isinstance(raw_messages, list):
            raise ValueError("fixture model request messages must be a list")
        messages = tuple(
            ModelMessage(str(item["role"]), str(item["content"]))
            for item in raw_messages
            if isinstance(item, Mapping)
        )
        schema = values.get("response_schema")
        metadata = values.get("metadata", {})
        return cls(
            messages,
            response_schema=dict(schema) if isinstance(schema, Mapping) else None,
            schema_name=str(values.get("schema_name", "noema_response")),
            instructions=(
                str(values["instructions"]) if values.get("instructions") is not None else None
            ),
            max_output_tokens=(
                int(values["max_output_tokens"])
                if values.get("max_output_tokens") is not None
                else None
            ),
            temperature=(
                float(values["temperature"]) if values.get("temperature") is not None else None
            ),
            correlation_id=(
                str(values["correlation_id"]) if values.get("correlation_id") is not None else None
            ),
            metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
        )


@dataclass(frozen=True, slots=True)
class ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float | None = None


@dataclass(frozen=True, slots=True)
class ModelResponse:
    provider: str
    model: str
    text: str
    output: JSONValue = None
    response_id: str | None = None
    finish_reason: str | None = None
    usage: ModelUsage = field(default_factory=ModelUsage)
    latency_seconds: float | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> JSONObject:
        return {
            "provider": self.provider,
            "model": self.model,
            "text": self.text,
            "output": self.output,
            "response_id": self.response_id,
            "finish_reason": self.finish_reason,
            "usage": asdict(self.usage),
            "latency_seconds": self.latency_seconds,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ModelResponse:
        values = cast(Mapping[str, Any], data)
        raw_usage = values.get("usage", {})
        usage = cast(Mapping[str, Any], raw_usage) if isinstance(raw_usage, Mapping) else {}
        metadata = values.get("metadata", {})
        return cls(
            provider=str(values["provider"]),
            model=str(values["model"]),
            text=str(values.get("text", "")),
            output=cast(JSONValue, values.get("output")),
            response_id=(str(values["response_id"]) if values.get("response_id") else None),
            finish_reason=(str(values["finish_reason"]) if values.get("finish_reason") else None),
            usage=ModelUsage(
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                total_tokens=int(usage.get("total_tokens", 0)),
                estimated_cost=(
                    float(usage["estimated_cost"])
                    if usage.get("estimated_cost") is not None
                    else None
                ),
            ),
            latency_seconds=(
                float(values["latency_seconds"])
                if values.get("latency_seconds") is not None
                else None
            ),
            metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
        )


class ModelProvider(Protocol):
    name: str
    model: str
    capabilities: ModelCapabilities

    async def generate(self, request: ModelRequest) -> ModelResponse: ...


class ContextAssembler(Protocol):
    def assemble(self, request: DeliberationRequest) -> tuple[ModelMessage, ...]: ...


class DefaultContextAssembler:
    """Produce a bounded structured view of situation state for a model."""

    def assemble(self, request: DeliberationRequest) -> tuple[ModelMessage, ...]:
        snapshot = request.situation
        context = {
            "agent_id": request.agent_id,
            "trigger": request.trigger.to_dict(),
            "situation": {
                "version": snapshot.version,
                "facts": {
                    key: {
                        "value": fact.value,
                        "confidence": fact.confidence,
                        "source": fact.source,
                        "expires_at": (fact.expires_at.isoformat() if fact.expires_at else None),
                    }
                    for key, fact in snapshot.facts.items()
                },
                "goals": [
                    {
                        "id": goal.id,
                        "description": goal.description,
                        "priority": goal.priority,
                        "status": goal.status.value,
                    }
                    for goal in snapshot.active_goals()
                ],
                "commitments": [
                    {
                        "id": commitment.id,
                        "description": commitment.description,
                        "priority": commitment.priority,
                        "deadline": (
                            commitment.deadline.isoformat()
                            if commitment.deadline is not None
                            else None
                        ),
                    }
                    for commitment in snapshot.open_commitments()
                ],
                "risks": [
                    {
                        "id": risk.id,
                        "description": risk.description,
                        "expected_loss": risk.expected_loss,
                    }
                    for risk in snapshot.active_risks()
                ],
                "resources": dict(snapshot.resources),
            },
            "capabilities": [
                {
                    "name": capability.name,
                    "description": capability.description,
                    "input_schema": dict(capability.input_schema),
                    "risk": int(capability.risk_level),
                    "reversible": capability.reversible,
                    "required_authority": int(capability.required_authority),
                }
                for capability in request.capabilities
            ],
            "attention_available": request.attention_available,
        }
        return (
            ModelMessage(
                "user",
                json.dumps(context, separators=(",", ":"), sort_keys=True),
            ),
        )


DELIBERATION_JSON_SCHEMA: JSONObject = {
    "type": "object",
    "properties": {
        "intents": {"type": "array", "items": ACTION_INTENT_JSON_SCHEMA},
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "probability": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_for": {"type": "array", "items": {"type": "string"}},
                    "evidence_against": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "falsifiers": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "statement",
                    "probability",
                    "evidence_for",
                    "evidence_against",
                    "falsifiers",
                ],
                "additionalProperties": False,
            },
        },
        "alternatives": {"type": "array", "items": {"type": "string"}},
        "modes": {
            "type": "array",
            "items": {"type": "string", "enum": [mode.value for mode in CognitiveMode]},
        },
        "notes": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["intents", "hypotheses", "alternatives", "modes", "notes", "confidence"],
    "additionalProperties": False,
}


class StructuredModelReasoner:
    """Turn schema-constrained model output into independently governed intents."""

    def __init__(
        self,
        provider: ModelProvider,
        *,
        assembler: ContextAssembler | None = None,
        instructions: str | None = None,
        max_output_tokens: int = 4096,
    ) -> None:
        if not provider.capabilities.structured_output:
            raise ValueError("StructuredModelReasoner requires structured-output support")
        self.provider = provider
        self.assembler = assembler or DefaultContextAssembler()
        self.instructions = instructions or (
            "Propose typed Noema ActionIntents only. Do not perform tool calls or side effects. "
            "Every proposal will be independently critiqued and authorized."
        )
        self.max_output_tokens = max_output_tokens

    async def deliberate(self, request: DeliberationRequest) -> DeliberationResult:
        response = await self.provider.generate(
            ModelRequest(
                self.assembler.assemble(request),
                response_schema=DELIBERATION_JSON_SCHEMA,
                schema_name="noema_deliberation",
                instructions=self.instructions,
                max_output_tokens=self.max_output_tokens,
                correlation_id=request.trigger.correlation_id or request.trigger.id,
                metadata={"agent_id": request.agent_id},
            )
        )
        if not isinstance(response.output, Mapping):
            raise ValueError("structured model response must be a JSON object")
        validate_json_schema(response.output, DELIBERATION_JSON_SCHEMA)
        output = cast(Mapping[str, Any], response.output)
        intents = tuple(
            ActionIntent.from_payload(item)
            for item in output["intents"]
            if isinstance(item, Mapping)
        )
        hypotheses = tuple(
            Hypothesis(
                statement=str(item["statement"]),
                probability=float(item["probability"]),
                evidence_for=tuple(str(value) for value in item["evidence_for"]),
                evidence_against=tuple(str(value) for value in item["evidence_against"]),
                falsifiers=tuple(str(value) for value in item["falsifiers"]),
            )
            for item in output["hypotheses"]
            if isinstance(item, Mapping)
        )
        return DeliberationResult(
            intents=intents,
            hypotheses=hypotheses,
            alternatives=tuple(str(value) for value in output["alternatives"]),
            modes=tuple(CognitiveMode(str(value)) for value in output["modes"]),
            notes=tuple(str(value) for value in output["notes"]),
            confidence=float(output["confidence"]),
        )


class ModelRouter:
    """Select the lowest modeled cost provider satisfying hard capabilities."""

    def __init__(self, providers: Sequence[ModelProvider]) -> None:
        if not providers:
            raise ValueError("ModelRouter requires at least one provider")
        self.providers = tuple(providers)

    def select(
        self,
        *,
        structured_output: bool = False,
        vision: bool = False,
        reasoning: bool = False,
        privacy_classes: set[str] | None = None,
    ) -> ModelProvider:
        candidates = [
            provider
            for provider in self.providers
            if (not structured_output or provider.capabilities.structured_output)
            and (not vision or provider.capabilities.vision)
            and (not reasoning or provider.capabilities.reasoning)
            and (privacy_classes is None or provider.capabilities.privacy_class in privacy_classes)
        ]
        if not candidates:
            raise LookupError("no model provider satisfies the requested capabilities")
        return min(
            candidates,
            key=lambda provider: (
                provider.capabilities.estimated_cost
                if provider.capabilities.estimated_cost is not None
                else float("inf"),
                provider.name,
            ),
        )


class RecordingModelProvider:
    """Record portable JSONL fixtures around a real or deterministic provider."""

    def __init__(self, provider: ModelProvider, path: str | Path) -> None:
        self.provider = provider
        self.name = f"recording:{provider.name}"
        self.model = provider.model
        self.capabilities = provider.capabilities
        self.path = Path(path)
        self._lock = asyncio.Lock()

    async def generate(self, request: ModelRequest) -> ModelResponse:
        response = await self.provider.generate(request)
        record = {
            "fixture_version": 1,
            "fingerprint": model_request_fingerprint(request),
            "request": request.to_dict(),
            "response": response.to_dict(),
        }
        line = json.dumps(record, separators=(",", ":"), sort_keys=True)
        async with self._lock:
            await asyncio.to_thread(self._append, line)
        return response

    def _append(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")


class ReplayModelProvider:
    """Replay captured outputs without network access or model nondeterminism."""

    name = "replay"
    model = "captured"
    capabilities = ModelCapabilities(structured_output=True, privacy_class="local")

    def __init__(self, path: str | Path, *, strict: bool = True) -> None:
        self.path = Path(path)
        self.strict = strict
        self._responses: dict[str, deque[ModelResponse]] = defaultdict(deque)
        self._load()

    def _load(self) -> None:
        with self.path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                data = json.loads(line)
                if int(data.get("fixture_version", 0)) != 1:
                    raise ValueError(f"unsupported fixture version on line {line_number}")
                self._responses[str(data["fingerprint"])].append(
                    ModelResponse.from_dict(data["response"])
                )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        fingerprint = model_request_fingerprint(request)
        responses = self._responses.get(fingerprint)
        if not responses:
            if self.strict:
                raise LookupError(f"no replay fixture for model request {fingerprint}")
            candidates = [queue for queue in self._responses.values() if queue]
            if len(candidates) != 1:
                raise LookupError("non-strict replay is ambiguous")
            responses = candidates[0]
        return responses.popleft()


class StaticModelProvider:
    """Deterministic test provider that returns queued responses."""

    name = "static"
    model = "deterministic"
    capabilities = ModelCapabilities(structured_output=True, privacy_class="local")

    def __init__(self, responses: Sequence[ModelResponse]) -> None:
        self._responses = deque(responses)
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self._responses:
            raise LookupError("static model provider has no remaining responses")
        return self._responses.popleft()


def model_request_fingerprint(request: ModelRequest) -> str:
    """Stable semantic request id; correlation metadata is deliberately excluded."""

    encoded = json.dumps(
        request.to_dict(include_correlation=False),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
