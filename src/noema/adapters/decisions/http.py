"""Optional HTTP transport for native typed-decision endpoints.

LiteLLM support targets its documented proxy routes, not its completion SDK.
No retries by default: retries can incur another charge. Cancellation propagates.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from dataclasses import asdict
from time import monotonic
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from ...decisions import (
    ChoiceAnswer,
    ChoiceProbability,
    ChoiceQuestion,
    DecisionAnswer,
    DecisionCapabilities,
    DecisionCapabilityError,
    DecisionError,
    DecisionHTTPError,
    DecisionProvenance,
    DecisionRequest,
    DecisionResponse,
    DecisionResponseError,
    DecisionTimeoutError,
    PredicateAnswer,
    PredicateQuestion,
    RefusalAnswer,
    ScoreAnswer,
    ScoreProbability,
)
from ...models import ModelUsage
from ...tracing import NullTracer, Tracer


def _object(value: object) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise DecisionResponseError("Expected a JSON object")
    return cast(Mapping[str, Any], value)


def _number(value: object) -> float:
    if type(value) not in (int, float):
        raise DecisionResponseError("Expected a finite number")
    try:
        result = float(cast(float, value))
    except OverflowError:
        raise DecisionResponseError("Expected a finite number") from None
    if not math.isfinite(result):
        raise DecisionResponseError("Expected a finite number")
    return result


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("Non-finite JSON constant")


def _probability(value: object) -> float:
    result = _number(value)
    if not 0 <= result <= 1:
        raise DecisionResponseError("Probability or confidence is outside [0, 1]")
    return result


def _distribution(values: list[float]) -> None:
    if not math.isclose(sum(values), 1.0, abs_tol=1e-5):
        raise DecisionResponseError("Probabilities must sum to one")


def _tokens(value: object) -> int:
    if type(value) is not int or value < 0:
        raise DecisionResponseError("Usage token counts must be non-negative integers")
    return value


class _HTTPDecisionProvider:
    def __init__(
        self,
        model: str,
        *,
        api_key: str,
        base_url: str,
        name: str,
        wire_format: Literal["decisions", "systemone"],
        timeout_seconds: float = 30.0,
        max_retries: int = 0,
        retry_backoff_seconds: float = 0.5,
        client: Any | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be non-empty")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be supplied explicitly")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if type(max_retries) is not int or not 0 <= max_retries <= 5:
            raise ValueError("max_retries must be an integer from 0 to 5")
        if not math.isfinite(retry_backoff_seconds) or retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be finite and non-negative")
        parts = urlsplit(base_url)
        if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname:
            raise ValueError("base_url must not contain credentials, query or fragment")
        if parts.scheme != "https" and not (
            parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")
        ):
            raise ValueError("Use HTTPS, or HTTP only for a loopback gateway")
        self.model, self.name = model, name
        self.capabilities = DecisionCapabilities(boolean_choices=wire_format == "decisions")
        self._wire_format = wire_format
        self._url = base_url.rstrip("/") + "/" + wire_format
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.tracer = tracer or NullTracer()
        self._client = client
        self._injected = client is not None

    def _payload(self, request: DecisionRequest) -> dict[str, Any]:
        if self._wire_format == "systemone":
            questions: dict[str, Any] = {}
            for q in request.questions:
                item: dict[str, Any] = {"instructions": q.instructions}
                if isinstance(q, PredicateQuestion):
                    item["type"] = "noul"
                elif isinstance(q, ChoiceQuestion):
                    if any(type(c.value) is not str for c in q.choices):
                        raise DecisionCapabilityError(
                            "Direct TypeSafe choices require strings; booleans are not coerced"
                        )
                    item.update(type="choice", criteria={c.value: c.description for c in q.choices})
                else:
                    item.update(
                        type="score",
                        criteria=[
                            level.label
                            if level.description is None
                            else f"{level.label}: {level.description}"
                            for level in q.levels
                        ],
                    )
                questions[q.name] = item
            return {"model": self.model, "state": request.input, "questions": questions}
        array: list[dict[str, Any]] = []
        for q in request.questions:
            item = {"name": q.name, "instructions": q.instructions}
            if isinstance(q, PredicateQuestion):
                item["type"] = "predicate"
            elif isinstance(q, ChoiceQuestion):
                item.update(
                    type="choice",
                    choices=[
                        {k: v for k, v in asdict(c).items() if v is not None} for c in q.choices
                    ],
                )
            else:
                item.update(
                    type="score",
                    levels=[
                        {k: v for k, v in asdict(level).items() if v is not None}
                        for level in q.levels
                    ],
                )
            array.append(item)
        return {"model": self.model, "input": request.input, "questions": array}

    async def decide(self, request: DecisionRequest) -> DecisionResponse:
        payload = self._payload(request)  # Capability failure must happen before network I/O.
        started = monotonic()
        async with self.tracer.span("decision.decide", {"decision.provider": self.name}) as span:
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    result = await self._perform(request, payload, started)
            except asyncio.CancelledError:
                span.set_attribute("decision.status", "cancelled")
                raise
            except TimeoutError:
                span.set_attribute("decision.status", "timeout")
                raise DecisionTimeoutError(
                    "Decision deadline exceeded; remote status unknown"
                ) from None
            except DecisionError:
                span.set_attribute("decision.status", "error")
                raise
            except Exception:
                # HTTP libraries may include headers, URL or body in exception text.
                span.set_attribute("decision.status", "transport_error")
                raise DecisionError("Decision transport failed; remote status unknown") from None
            span.set_attribute("decision.status", "completed")
            span.set_attribute("decision.attempts", result.provenance.attempts)
            # Deliberately no input, answers, URL, arbitrary metadata or exception recording.
            return result

    async def _perform(
        self,
        request: DecisionRequest,
        payload: dict[str, Any],
        started: float,
    ) -> DecisionResponse:
        try:
            import httpx
        except ImportError:
            if self._client is not None:
                return await self._send(self._client, request, payload, started)
            raise DecisionError("Install noema-agent-sdk[decisions] for HTTP decisions") from None
        try:
            if self._client is not None:
                return await self._send(self._client, request, payload, started)
            async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
                return await self._send(client, request, payload, started)
        except httpx.TimeoutException:
            raise TimeoutError from None

    async def _send(
        self,
        client: Any,
        request: DecisionRequest,
        payload: dict[str, Any],
        started: float,
    ) -> DecisionResponse:
        for attempt in range(1, self.max_retries + 2):
            # No retries after transport exceptions, timeouts, cancellation or parse failure.
            try:
                import httpx
            except ImportError:
                timeout_types: tuple[type[Exception], ...] = (TimeoutError,)
            else:
                timeout_types = (TimeoutError, httpx.TimeoutException)
            try:
                response = await client.post(
                    self._url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=self.timeout_seconds,
                    follow_redirects=False,
                )
            except asyncio.CancelledError:
                raise
            except timeout_types:
                raise TimeoutError from None
            except Exception:
                # Sanitize even DecisionError subclasses raised by a foreign transport.
                raise DecisionError("Decision transport failed; remote status unknown") from None
            status = response.status_code
            if status in (429, 502, 503, 504, 529) and attempt <= self.max_retries:
                delay = self.retry_backoff_seconds * 2 ** (attempt - 1)
                raw_delay = response.headers.get("retry-after")
                if raw_delay:
                    try:
                        supplied = float(raw_delay)
                        if math.isfinite(supplied) and supplied >= 0:
                            delay = max(delay, supplied)
                    except (TypeError, ValueError):
                        pass
                await asyncio.sleep(delay)  # Included in the overall deadline.
                continue
            if status in (404, 405, 501):
                raise DecisionCapabilityError(
                    "Native decision route unavailable; no fallback attempted"
                )
            if status != 200:
                raise DecisionHTTPError(status)
            try:
                decoded = response.json(
                    object_pairs_hook=_unique_object,
                    parse_constant=_invalid_constant,
                )
            except Exception:
                raise DecisionResponseError("Malformed decision JSON response") from None
            try:
                data = _object(decoded)
                answers = self._parse_answers(request, data)
                model = data["model"]
                if not isinstance(model, str) or not model:
                    raise DecisionResponseError("Response model must be non-empty text")
                usage = _object(data["usage"])
                input_tokens, output_tokens = (
                    _tokens(usage["input_tokens"]),
                    _tokens(usage["output_tokens"]),
                )
                total = _tokens(usage.get("total_tokens", input_tokens + output_tokens))
                if total != input_tokens + output_tokens:
                    raise DecisionResponseError("Inconsistent total token count")
            except (KeyError, TypeError, ValueError):
                raise DecisionResponseError("Malformed decision response") from None
            return DecisionResponse(
                answers=answers,
                provenance=DecisionProvenance(
                    provider=self.name,
                    requested_model=self.model,
                    response_model=model,
                    transport=self._wire_format,
                    request_fingerprint=request.fingerprint(),
                    rubric_version=request.rubric_version,
                    attempts=attempt,
                    origin="injected_transport" if self._injected else "http",
                    request_id=response.headers.get("x-request-id"),
                ),
                usage=ModelUsage(
                    input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total
                ),
                latency_seconds=monotonic() - started,
            )
        raise AssertionError("unreachable")

    def _parse_answers(
        self,
        request: DecisionRequest,
        data: Mapping[str, Any],
    ) -> tuple[DecisionAnswer, ...]:
        raw = data["answers"]
        if self._wire_format == "systemone":
            mapped = _object(raw)
            if set(mapped) != {q.name for q in request.questions}:
                raise DecisionResponseError("Answer names do not match questions")
            items = [mapped[q.name] for q in request.questions]
        else:
            if not isinstance(raw, list) or len(raw) != len(request.questions):
                raise DecisionResponseError("Answer count does not match questions")
            items = raw
        result: list[DecisionAnswer] = []
        for q, raw_item in zip(request.questions, items, strict=True):
            item = _object(raw_item)
            if self._wire_format == "decisions" and item.get("name") != q.name:
                raise DecisionResponseError("Answer name or order does not match question")
            kind = item.get("type")
            if kind == "refusal" and self._wire_format == "decisions":
                result.append(RefusalAnswer(q.name))
                continue
            if isinstance(q, PredicateQuestion):
                expected = "noul" if self._wire_format == "systemone" else "predicate"
                if kind != expected:
                    raise DecisionResponseError("Unexpected answer type")
                result.append(
                    PredicateAnswer(
                        q.name, _probability(item["noul" if expected == "noul" else "probability"])
                    )
                )
            elif isinstance(q, ChoiceQuestion):
                if kind != "choice":
                    raise DecisionResponseError("Unexpected answer type")
                if self._wire_format == "systemone":
                    values = _object(item["probabilities"])
                    entries = [{"value": k, "probability": v} for k, v in values.items()]
                else:
                    entries = item["probabilities"]
                if not isinstance(entries, list):
                    raise DecisionResponseError("Expected choice probability array")
                probabilities: list[ChoiceProbability] = []
                for raw_entry in entries:
                    entry = _object(raw_entry)
                    if type(entry["value"]) not in (str, bool):
                        raise DecisionResponseError("Invalid choice value type")
                    probabilities.append(
                        ChoiceProbability(entry["value"], _probability(entry["probability"]))
                    )
                expected_values = {(type(c.value), c.value) for c in q.choices}
                if (
                    len(probabilities) != len(q.choices)
                    or {(type(p.value), p.value) for p in probabilities} != expected_values
                    or (type(item["choice"]), item["choice"]) not in expected_values
                ):
                    raise DecisionResponseError("Choices do not match request")
                _distribution([p.probability for p in probabilities])
                selected = next(
                    p.probability
                    for p in probabilities
                    if type(p.value) is type(item["choice"]) and p.value == item["choice"]
                )
                if selected + 1e-5 < max(p.probability for p in probabilities):
                    raise DecisionResponseError(
                        "Selected choice is not a highest-probability option"
                    )
                result.append(
                    ChoiceAnswer(
                        q.name,
                        item["choice"],
                        tuple(probabilities),
                        _probability(item["confidence"]),
                    )
                )
            else:
                if kind != "score":
                    raise DecisionResponseError("Unexpected answer type")
                score_probabilities: list[ScoreProbability] = []
                if self._wire_format == "systemone":
                    values = _object(item["probabilities"])
                    legend = _object(item["legend"])
                    expected_keys = {str(i) for i in range(len(q.levels))}
                    if set(values) != expected_keys or set(legend) != expected_keys:
                        raise DecisionResponseError("Score levels do not match request")
                    for i, level in enumerate(q.levels):
                        criterion = (
                            level.label
                            if level.description is None
                            else f"{level.label}: {level.description}"
                        )
                        if legend[str(i)] != criterion:
                            raise DecisionResponseError("Score legend does not match request")
                        score_probabilities.append(
                            ScoreProbability(i, level.label, _probability(values[str(i)]))
                        )
                else:
                    entries = item["probabilities"]
                    if not isinstance(entries, list) or len(entries) != len(q.levels):
                        raise DecisionResponseError("Score levels do not match request")
                    seen: set[int] = set()
                    for raw_entry in entries:
                        entry = _object(raw_entry)
                        index = entry["value"]
                        if (
                            type(index) is not int
                            or not 0 <= index < len(q.levels)
                            or index in seen
                        ):
                            raise DecisionResponseError("Invalid score level index")
                        seen.add(index)
                        if entry["label"] != q.levels[index].label:
                            raise DecisionResponseError("Score label does not match request")
                        score_probabilities.append(
                            ScoreProbability(
                                index, entry["label"], _probability(entry["probability"])
                            )
                        )
                _distribution([p.probability for p in score_probabilities])
                score = _number(item["score"])
                if not 0 <= score <= len(q.levels) - 1:
                    raise DecisionResponseError("Score is outside the requested level range")
                expected_score = sum(p.value * p.probability for p in score_probabilities)
                if not math.isclose(score, expected_score, abs_tol=1e-4):
                    raise DecisionResponseError("Score is inconsistent with its distribution")
                result.append(
                    ScoreAnswer(
                        q.name, score, tuple(score_probabilities), _probability(item["confidence"])
                    )
                )
        return tuple(result)


class OpenAIDecisionsProvider(_HTTPDecisionProvider):
    """Direct OpenAI /v1/decisions, independent of Responses API support."""

    def __init__(self, model: str = "gpt-6-luna", *, api_key: str, **kwargs: Any) -> None:
        super().__init__(
            model,
            api_key=api_key,
            base_url="https://api.openai.com/v1",
            name="openai",
            wire_format="decisions",
            **kwargs,
        )


class TypeSafeDecisionsProvider(_HTTPDecisionProvider):
    """Direct TypeSafe /v1/systemone; predicate maps to Noul."""

    def __init__(self, model: str = "jev-latest", *, api_key: str, **kwargs: Any) -> None:
        super().__init__(
            model,
            api_key=api_key,
            base_url="https://api.typesafe.ai/v1",
            name="typesafe",
            wire_format="systemone",
            **kwargs,
        )


class LiteLLMDecisionsProvider(_HTTPDecisionProvider):
    """Explicitly configured LiteLLM gateway, with no implicit provider fallback.

    Configure one upstream per alias and disable gateway fallbacks if exact
    provider identity is required. Returned model is reported, not inferred.
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str,
        base_url: str,
        wire_format: Literal["decisions", "systemone"] = "decisions",
        **kwargs: Any,
    ) -> None:
        if wire_format not in ("decisions", "systemone"):
            raise DecisionCapabilityError("LiteLLM requires decisions or systemone route")
        super().__init__(
            model,
            api_key=api_key,
            base_url=base_url,
            name="litellm",
            wire_format=wire_format,
            **kwargs,
        )
