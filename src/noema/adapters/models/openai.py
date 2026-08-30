"""OpenAI Responses API and OpenAI-compatible local model adapters."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from time import monotonic
from typing import Any

from ...models import (
    ModelCapabilities,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from ...tracing import NullTracer, Tracer


class OpenAIResponsesProvider:
    """Schema-aware adapter for the OpenAI Responses API.

    The optional official SDK is loaded only when a client is not injected.
    Noema gives the model no capability credentials: the adapter returns data,
    and the runtime independently critiques and authorizes each ActionIntent.
    """

    name = "openai"

    def __init__(
        self,
        model: str,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
        tracer: Tracer | None = None,
        provider_name: str = "openai",
        privacy_class: str = "provider",
    ) -> None:
        if not model:
            raise ValueError("model must be non-empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        client_instance: Any = client
        if client_instance is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "OpenAI support requires `pip install 'noema-agent-sdk[openai]'`"
                ) from exc
            client_instance = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.name = provider_name
        self._client: Any = client_instance
        self.timeout_seconds = timeout_seconds
        self.tracer = tracer or NullTracer()
        self.capabilities = ModelCapabilities(
            structured_output=True,
            tool_calls=True,
            streaming=True,
            vision=True,
            reasoning=True,
            privacy_class=privacy_class,
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, object] = {
            "model": self.model,
            "input": [message.to_dict() for message in request.messages],
            "store": False,
        }
        if request.instructions is not None:
            payload["instructions"] = request.instructions
        if request.max_output_tokens is not None:
            payload["max_output_tokens"] = request.max_output_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.response_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": request.schema_name,
                    "schema": dict(request.response_schema),
                    "strict": True,
                }
            }
        metadata = {
            str(key): str(value) for key, value in request.metadata.items() if value is not None
        }
        if request.correlation_id is not None:
            metadata["correlation_id"] = request.correlation_id
        if metadata:
            payload["metadata"] = metadata

        attributes = {
            "gen_ai.system": self.name,
            "gen_ai.request.model": self.model,
        }
        if request.correlation_id is not None:
            attributes["noema.correlation_id"] = request.correlation_id
        started = monotonic()
        async with self.tracer.span("model.generate", attributes) as span:
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    response = await self._client.responses.create(**payload)
            except BaseException as exc:
                span.record_exception(exc)
                raise
            latency = monotonic() - started
            parsed = self._parse_response(response, request, latency)
            span.set_attribute("gen_ai.response.model", parsed.model)
            span.set_attribute("gen_ai.usage.input_tokens", parsed.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", parsed.usage.output_tokens)
            return parsed

    def _parse_response(
        self,
        response: Any,
        request: ModelRequest,
        latency_seconds: float,
    ) -> ModelResponse:
        data = _as_mapping(response)
        text = str(data.get("output_text") or _extract_output_text(data))
        output = None
        if request.response_schema is not None:
            try:
                output = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("model returned invalid JSON for a structured request") from exc
        usage_data = data.get("usage")
        usage = usage_data if isinstance(usage_data, Mapping) else {}
        return ModelResponse(
            provider=self.name,
            model=str(data.get("model") or self.model),
            text=text,
            output=output,
            response_id=str(data["id"]) if data.get("id") is not None else None,
            finish_reason=(str(data["status"]) if data.get("status") is not None else None),
            usage=ModelUsage(
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                total_tokens=int(usage.get("total_tokens", 0)),
            ),
            latency_seconds=latency_seconds,
            metadata={"status": str(data.get("status", "unknown"))},
        )


class OpenAICompatibleProvider(OpenAIResponsesProvider):
    """OpenAI Responses-compatible local/server provider, including vLLM."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        client: Any | None = None,
        api_key: str = "local",
        timeout_seconds: float = 60.0,
        tracer: Tracer | None = None,
        provider_name: str = "openai-compatible-local",
    ) -> None:
        if not base_url:
            raise ValueError("base_url must be non-empty")
        super().__init__(
            model,
            client=client,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            tracer=tracer,
            provider_name=provider_name,
            privacy_class="local",
        )


def _as_mapping(response: Any) -> Mapping[str, Any]:
    if isinstance(response, Mapping):
        return response
    dump = getattr(response, "model_dump", None)
    if dump is not None:
        data = dump(mode="json")
        if isinstance(data, Mapping):
            return data
    raise TypeError("OpenAI response must be mapping-like or support model_dump")


def _extract_output_text(data: Mapping[str, Any]) -> str:
    for item in data.get("output", []):
        if not isinstance(item, Mapping):
            continue
        for content in item.get("content", []):
            if (
                isinstance(content, Mapping)
                and content.get("type") == "output_text"
                and content.get("text") is not None
            ):
                return str(content["text"])
    return ""
