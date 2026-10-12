"""Offline contract tests using actual HTTP requests/responses and fake transports."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import unittest
from contextlib import asynccontextmanager
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

from noema.adapters.decisions import (
    LiteLLMDecisionsProvider,
    OpenAIDecisionsProvider,
    TypeSafeDecisionsProvider,
)
from noema.decisions import (
    ChoiceAnswer,
    ChoiceOption,
    ChoiceQuestion,
    DecisionCapabilityError,
    DecisionError,
    DecisionHTTPError,
    DecisionRequest,
    DecisionResponseError,
    DecisionTimeoutError,
    PredicateAnswer,
    PredicateQuestion,
    RefusalAnswer,
    ScoreAnswer,
    ScoreLevel,
    ScoreQuestion,
)

REQUEST = DecisionRequest(
    input="Synthetic support example: export fails; a workaround is available.",
    questions=(
        PredicateQuestion("urgent", "Does this explicitly need attention today?"),
        ChoiceQuestion(
            "team",
            "Which team?",
            (
                ChoiceOption("support", "Technical support"),
                ChoiceOption("sales"),
            ),
        ),
        ScoreQuestion(
            "severity",
            "How severe?",
            (
                ScoreLevel("minor"),
                ScoreLevel("workaround"),
                ScoreLevel("blocked"),
            ),
        ),
    ),
    rubric_version="support-test-v1",
)
OPENAI_BODY = {
    "model": "gpt-6-luna",
    "answers": [
        {"type": "predicate", "name": "urgent", "probability": 0.9},
        {
            "type": "choice",
            "name": "team",
            "choice": "support",
            "probabilities": [
                {"value": "support", "probability": 0.9},
                {"value": "sales", "probability": 0.1},
            ],
            "confidence": 0.8,
        },
        {
            "type": "score",
            "name": "severity",
            "score": 1.1,
            "probabilities": [
                {"value": 0, "label": "minor", "probability": 0.1},
                {"value": 1, "label": "workaround", "probability": 0.7},
                {"value": 2, "label": "blocked", "probability": 0.2},
            ],
            "confidence": 0.55,
        },
    ],
    "usage": {
        "input_tokens": 42,
        "output_tokens": 0,
        "total_tokens": 42,
        "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    },
}
TYPESAFE_BODY = {
    "model": "jev-1.13.0",
    "answers": {
        "urgent": {"type": "noul", "noul": 0.9},
        "team": {
            "type": "choice",
            "choice": "support",
            "probabilities": {"support": 0.9, "sales": 0.1},
            "confidence": 0.8,
        },
        "severity": {
            "type": "score",
            "score": 1.1,
            "legend": {"0": "minor", "1": "workaround", "2": "blocked"},
            "probabilities": {"0": 0.1, "1": 0.7, "2": 0.2},
            "confidence": 0.55,
        },
    },
    "usage": {"input_tokens": 42, "output_tokens": 18},
}


class CapturingTracer:
    def __init__(self) -> None:
        self.attributes: dict[str, Any] = {}
        self.exceptions: list[BaseException] = []

    @asynccontextmanager
    async def span(self, name: str, attributes: Any = None) -> Any:
        self.attributes.update(attributes or {})
        yield self

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def record_exception(self, exception: BaseException) -> None:
        self.exceptions.append(exception)


@unittest.skipIf(httpx is None, "optional decisions extra is not installed")
class DecisionContractTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(
        self,
        provider: Any,
        body: Any,
        *,
        request: DecisionRequest = REQUEST,
        status: int = 200,
        **kwargs: Any,
    ) -> tuple[Any, list[Any]]:
        requests: list[Any] = []

        async def handle(req: Any) -> Any:
            requests.append(req)
            return httpx.Response(status, json=body, headers={"x-request-id": "req_test"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await provider(api_key="secret-test-key", client=client, **kwargs).decide(
                request
            )
        return result, requests

    async def test_openai_exact_native_contract(self) -> None:
        response, requests = await self.invoke(OpenAIDecisionsProvider, OPENAI_BODY)
        self.assertEqual(str(requests[0].url), "https://api.openai.com/v1/decisions")
        sent = json.loads(requests[0].content)
        self.assertEqual(
            sent,
            {
                "model": "gpt-6-luna",
                "input": REQUEST.input,
                "questions": [
                    {
                        "name": "urgent",
                        "instructions": REQUEST.questions[0].instructions,
                        "type": "predicate",
                    },
                    {
                        "name": "team",
                        "instructions": "Which team?",
                        "type": "choice",
                        "choices": [
                            {"value": "support", "description": "Technical support"},
                            {"value": "sales"},
                        ],
                    },
                    {
                        "name": "severity",
                        "instructions": "How severe?",
                        "type": "score",
                        "levels": [
                            {"label": "minor"},
                            {"label": "workaround"},
                            {"label": "blocked"},
                        ],
                    },
                ],
            },
        )
        self.assertEqual(requests[0].headers["authorization"], "Bearer secret-test-key")
        self.assertEqual(response.answers[0], PredicateAnswer("urgent", 0.9))
        self.assertIsInstance(response.answers[1], ChoiceAnswer)
        self.assertIsInstance(response.answers[2], ScoreAnswer)
        self.assertEqual(response.provenance.origin, "injected_transport")
        self.assertEqual(response.provenance.request_id, "req_test")
        self.assertEqual(response.provenance.request_fingerprint, REQUEST.fingerprint())
        self.assertEqual(response.usage.total_tokens, 42)

    async def test_typesafe_native_contract(self) -> None:
        response, requests = await self.invoke(TypeSafeDecisionsProvider, TYPESAFE_BODY)
        self.assertEqual(str(requests[0].url), "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(
            json.loads(requests[0].content),
            {
                "model": "jev-latest",
                "state": REQUEST.input,
                "questions": {
                    "urgent": {"type": "noul", "instructions": REQUEST.questions[0].instructions},
                    "team": {
                        "type": "choice",
                        "instructions": "Which team?",
                        "criteria": {"support": "Technical support", "sales": None},
                    },
                    "severity": {
                        "type": "score",
                        "instructions": "How severe?",
                        "criteria": ["minor", "workaround", "blocked"],
                    },
                },
            },
        )
        self.assertEqual(response.provenance.response_model, "jev-1.13.0")
        self.assertEqual(response.usage.total_tokens, 60)
        self.assertEqual(response.answers[2].score, 1.1)

    async def test_litellm_both_wire_formats(self) -> None:
        for wire, body in (("decisions", OPENAI_BODY), ("systemone", TYPESAFE_BODY)):
            with self.subTest(wire=wire):
                response, requests = await self.invoke(
                    LiteLLMDecisionsProvider,
                    body,
                    model="my-decision-alias",
                    base_url="http://localhost:4000/v1",
                    wire_format=wire,
                )
                self.assertEqual(requests[0].url.path, "/v1/" + wire)
                self.assertEqual(json.loads(requests[0].content)["model"], "my-decision-alias")
                self.assertEqual(response.provenance.provider, "litellm")
                self.assertEqual(response.provenance.requested_model, "my-decision-alias")

    async def test_boolean_and_same_text_string_remain_distinct(self) -> None:
        request = DecisionRequest(
            "synthetic",
            (
                ChoiceQuestion(
                    "pick",
                    "Select",
                    (ChoiceOption(True), ChoiceOption("true")),
                ),
            ),
        )
        body = copy.deepcopy(OPENAI_BODY)
        body["answers"] = [
            {
                "type": "choice",
                "name": "pick",
                "choice": True,
                "probabilities": [
                    {"value": True, "probability": 0.8},
                    {"value": "true", "probability": 0.2},
                ],
                "confidence": 0.6,
            }
        ]
        response, _ = await self.invoke(OpenAIDecisionsProvider, body, request=request)
        self.assertIs(response.answers[0].choice, True)
        with self.assertRaises(DecisionCapabilityError):
            await self.invoke(TypeSafeDecisionsProvider, body, request=request)

    async def test_partial_refusal_preserved_without_approval(self) -> None:
        body = copy.deepcopy(OPENAI_BODY)
        body["answers"][1] = {"type": "refusal", "name": "team"}
        result, _ = await self.invoke(OpenAIDecisionsProvider, body)
        self.assertEqual(result.answers[1], RefusalAnswer("team"))
        self.assertIsInstance(result.answers[0], PredicateAnswer)
        self.assertFalse(hasattr(result, "authorized"))

    async def test_malformed_responses_fail_closed(self) -> None:
        mutations = [
            lambda b: b["answers"].pop(),
            lambda b: b["answers"][0].update(name="other"),
            lambda b: b["answers"][0].update(probability=True),
            lambda b: b["answers"][0].update(probability=float("nan")),
            lambda b: b["answers"][0].update(probability=1.1),
            lambda b: b["answers"][0].update(type="choice"),
            lambda b: b["answers"][1].update(choice="missing"),
            lambda b: b["answers"][1].update(choice="sales"),
            lambda b: b["answers"][1].update(confidence=-0.1),
            lambda b: b["answers"][1]["probabilities"][1].update(value="support"),
            lambda b: b["answers"][1]["probabilities"][0].update(probability=0.5),
            lambda b: b["answers"][2].update(score=0.1),
            lambda b: b["answers"][2]["probabilities"][1].update(value=0),
            lambda b: b["answers"][2]["probabilities"][1].update(label="wrong"),
            lambda b: b["usage"].update(input_tokens="42"),
            lambda b: b["usage"].update(total_tokens=100),
            lambda b: b.update(model=None),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                body = copy.deepcopy(OPENAI_BODY)
                mutate(body)

                # Raw transport allows NaN to test parser independently of HTTPX's encoder.
                async def handle(req: Any, body: Any = body) -> Any:
                    return httpx.Response(200, content=json.dumps(body))

                async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                    with self.assertRaises(DecisionResponseError):
                        await OpenAIDecisionsProvider(api_key="test", client=client).decide(REQUEST)

    async def test_typesafe_missing_extra_and_mismatched_answers_rejected(self) -> None:
        for mutation in (
            lambda b: b["answers"].pop("urgent"),
            lambda b: b["answers"].update(extra={}),
            lambda b: b["answers"]["severity"]["legend"].update({"0": "wrong"}),
            lambda b: b["answers"]["severity"]["probabilities"].update({"3": 0}),
        ):
            body = copy.deepcopy(TYPESAFE_BODY)
            mutation(body)
            with self.assertRaises(DecisionResponseError):
                await self.invoke(TypeSafeDecisionsProvider, body)

    async def test_status_errors_and_no_automatic_fallback(self) -> None:
        for status in (400, 401, 403, 422, 429, 500, 529, 302):
            with self.subTest(status=status), self.assertRaises(DecisionHTTPError) as raised:
                await self.invoke(
                    OpenAIDecisionsProvider, {"error": "secret-test-key"}, status=status
                )
            self.assertEqual(raised.exception.status_code, status)
            self.assertNotIn("secret-test-key", str(raised.exception))
        for status in (404, 405, 501):
            with self.assertRaises(DecisionCapabilityError):
                await self.invoke(OpenAIDecisionsProvider, {}, status=status)

    async def test_retry_policy_only_explicit_retryable_statuses(self) -> None:
        for status in (429, 502, 503, 504, 529):
            calls = []

            async def handle(req: Any, calls: Any = calls, status: int = status) -> Any:
                calls.append(req)
                if len(calls) == 1:
                    return httpx.Response(status, headers={"retry-after": "0"}, json={})
                return httpx.Response(200, json=OPENAI_BODY)

            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                result = await OpenAIDecisionsProvider(
                    api_key="test",
                    client=client,
                    max_retries=1,
                    retry_backoff_seconds=0,
                ).decide(REQUEST)
            self.assertEqual(len(calls), 2)
            self.assertEqual(result.provenance.attempts, 2)

    async def test_no_retry_on_transport_errors_and_trace_redaction(self) -> None:
        calls = []
        tracer = CapturingTracer()

        async def handle(req: Any) -> Any:
            calls.append(req)
            raise RuntimeError("secret-test-key " + REQUEST.input)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with self.assertRaises(DecisionError) as raised:
                await OpenAIDecisionsProvider(
                    api_key="secret-test-key",
                    client=client,
                    max_retries=2,
                    tracer=tracer,
                ).decide(REQUEST)
        self.assertEqual(len(calls), 1)
        rendered = str(tracer.attributes) + str(tracer.exceptions) + str(raised.exception)
        self.assertNotIn("secret-test-key", rendered)
        self.assertNotIn(REQUEST.input, rendered)
        self.assertEqual(tracer.exceptions, [])
        self.assertTrue(raised.exception.__suppress_context__)

    async def test_deadline_includes_retry_wait(self) -> None:
        calls = []

        async def handle(req: Any) -> Any:
            calls.append(req)
            return httpx.Response(429, headers={"retry-after": "60"}, json={})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with self.assertRaises(DecisionTimeoutError):
                await OpenAIDecisionsProvider(
                    api_key="test",
                    client=client,
                    timeout_seconds=0.01,
                    max_retries=2,
                ).decide(REQUEST)
        self.assertEqual(len(calls), 1)

    async def test_cancellation_propagates_without_retry(self) -> None:
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def handle(req: Any) -> Any:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            task = asyncio.create_task(
                OpenAIDecisionsProvider(
                    api_key="test",
                    client=client,
                    max_retries=2,
                ).decide(REQUEST)
            )
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(cancelled.is_set())

    async def test_retry_exhaustion_and_nonretryable_errors(self) -> None:
        for status, count in ((429, 3), (529, 3), (401, 1), (422, 1), (500, 1)):
            calls: list[Any] = []

            async def handle(req: Any, status: int = status, calls: Any = calls) -> Any:
                calls.append(req)
                return httpx.Response(status, json={"error": "private"})

            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                with self.assertRaises(DecisionHTTPError):
                    await OpenAIDecisionsProvider(
                        api_key="test",
                        client=client,
                        max_retries=2,
                        retry_backoff_seconds=0,
                    ).decide(REQUEST)
            self.assertEqual(len(calls), count)

    async def test_httpx_timeout_normalized_without_retry(self) -> None:
        calls = []

        async def handle(req: Any) -> Any:
            calls.append(req)
            raise httpx.ReadTimeout("secret-test-key", request=req)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with self.assertRaises(DecisionTimeoutError) as raised:
                await OpenAIDecisionsProvider(
                    api_key="test",
                    client=client,
                    max_retries=2,
                ).decide(REQUEST)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("secret-test-key", str(raised.exception))

    async def test_described_typesafe_levels(self) -> None:
        request = DecisionRequest(
            "synthetic",
            (
                ScoreQuestion(
                    "severity",
                    "Rate impact",
                    (
                        ScoreLevel("low", "Cosmetic"),
                        ScoreLevel("high", "Task blocked"),
                    ),
                ),
            ),
        )
        body = {
            "model": "jev-1.13.0",
            "answers": {
                "severity": {
                    "type": "score",
                    "score": 0.8,
                    "confidence": 0.6,
                    "probabilities": {"0": 0.2, "1": 0.8},
                    "legend": {"0": "low: Cosmetic", "1": "high: Task blocked"},
                }
            },
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
        result, requests = await self.invoke(TypeSafeDecisionsProvider, body, request=request)
        criteria = json.loads(requests[0].content)["questions"]["severity"]["criteria"]
        self.assertEqual(criteria, ["low: Cosmetic", "high: Task blocked"])
        self.assertEqual(result.answers[0].probabilities[1].label, "high")

    async def test_duplicate_keys_cannot_override_refusal(self) -> None:
        request = DecisionRequest("synthetic", (PredicateQuestion("x", "Is it present?"),))
        cases = [
            '{"model":"luna","answers":[{"name":"x","type":"refusal",'
            '"type":"predicate","probability":0.9}],'
            '"usage":{"input_tokens":1,"output_tokens":0}}',
            '{"model":"luna","answers":[{"name":"x","type":"predicate",'
            '"probability":0.1,"probability":0.9}],'
            '"usage":{"input_tokens":1,"output_tokens":0}}',
        ]
        for content in cases:

            async def handle(req: Any, content: str = content) -> Any:
                return httpx.Response(200, content=content)

            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                with self.assertRaises(DecisionResponseError):
                    await OpenAIDecisionsProvider(api_key="test", client=client).decide(request)

    async def test_custom_decision_error_is_redacted_at_transport_boundary(self) -> None:
        tracer = CapturingTracer()

        async def handle(req: Any) -> Any:
            raise DecisionError("SENSITIVE KEY SENSITIVE INPUT")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with self.assertRaises(DecisionError) as raised:
                await OpenAIDecisionsProvider(api_key="test", client=client, tracer=tracer).decide(
                    REQUEST
                )
        self.assertNotIn("SENSITIVE", str(raised.exception))
        self.assertNotIn("SENSITIVE", str(tracer.attributes) + str(tracer.exceptions))
        self.assertTrue(raised.exception.__suppress_context__)

    async def test_scores_outside_bounds_rejected_even_within_tolerance(self) -> None:
        for score, probabilities in ((-0.00005, [1.0, 0.0, 0.0]), (2.00005, [0.0, 0.0, 1.0])):
            body = copy.deepcopy(OPENAI_BODY)
            body["answers"][2]["score"] = score
            for item, probability in zip(
                body["answers"][2]["probabilities"], probabilities, strict=True
            ):
                item["probability"] = probability
            with self.assertRaises(DecisionResponseError):
                await self.invoke(OpenAIDecisionsProvider, body)

    async def test_enormous_number_is_response_error(self) -> None:
        body = copy.deepcopy(OPENAI_BODY)
        body["answers"][0]["probability"] = 10**400
        with self.assertRaises(DecisionResponseError):
            await self.invoke(OpenAIDecisionsProvider, body)

    async def test_invalid_json(self) -> None:
        async def handle(req: Any) -> Any:
            return httpx.Response(200, content="not JSON")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with self.assertRaises(DecisionResponseError):
                await OpenAIDecisionsProvider(api_key="test", client=client).decide(REQUEST)


class DecisionValidationTests(unittest.TestCase):
    def test_invalid_input_and_question_shape(self) -> None:
        for input_value in ({"image": "url"}, ["text"]):
            with self.assertRaises(DecisionCapabilityError):
                DecisionRequest(input_value, REQUEST.questions)
        with self.assertRaises(ValueError):
            DecisionRequest("text", ())
        with self.assertRaises(ValueError):
            DecisionRequest("text", (REQUEST.questions[0], REQUEST.questions[0]))
        with self.assertRaises(ValueError):
            ChoiceQuestion("x", "pick", (ChoiceOption("a"), ChoiceOption("a")))
        with self.assertRaises(ValueError):
            ScoreQuestion("x", "score", (ScoreLevel("a"),))

    def test_configuration_rejects_unsafe_destinations(self) -> None:
        for url in (
            "http://example.com/v1",
            "https://user:secret@example.com/v1",
            "https://example.com/v1?key=secret",
            "file:///tmp/api",
        ):
            with self.assertRaises(ValueError):
                LiteLLMDecisionsProvider("alias", api_key="test", base_url=url)
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                OpenAIDecisionsProvider(api_key="test", timeout_seconds=timeout)
        for retries in (-1, 6, True):
            with self.assertRaises(ValueError):
                OpenAIDecisionsProvider(api_key="test", max_retries=retries)

    def test_fingerprint_tracks_rubric(self) -> None:
        altered = DecisionRequest(REQUEST.input, REQUEST.questions, "v2")
        self.assertNotEqual(altered.fingerprint(), REQUEST.fingerprint())


@unittest.skipUnless(os.environ.get("NOEMA_DECISIONS_LIVE") == "1", "paid live smoke disabled")
@unittest.skipIf(httpx is None, "optional decisions extra is not installed")
class DecisionLiveSmoke(unittest.IsolatedAsyncioTestCase):
    """Explicit opt-in; only fixed synthetic input. Never run during offline CI."""

    async def test_configured_endpoint(self) -> None:
        provider_name = os.environ.get("NOEMA_DECISIONS_PROVIDER", "litellm")
        keys = {
            "litellm": "LITELLM_API_KEY",
            "openai": "OPENAI_API_KEY",
            "typesafe": "TYPESAFE_API_KEY",
        }
        if provider_name not in keys:
            self.fail("Select litellm, openai or typesafe")
        key = os.environ.get(keys[provider_name])
        if not key:
            self.skipTest("provider credential not configured")
        if provider_name == "litellm":
            base = os.environ.get("LITELLM_BASE_URL")
            model = os.environ.get("NOEMA_DECISION_MODEL")
            if not base or not model:
                self.skipTest("gateway URL and model alias required")
            provider = LiteLLMDecisionsProvider(model, api_key=key, base_url=base)
        elif provider_name == "openai":
            provider = OpenAIDecisionsProvider(api_key=key)
        else:
            provider = TypeSafeDecisionsProvider(api_key=key)
        result = await provider.decide(
            DecisionRequest(
                "Synthetic example: The parcel has a red label.",
                (PredicateQuestion("red", "Does the text say the label is red?"),),
                "synthetic-smoke-v1",
            )
        )
        self.assertEqual(len(result.answers), 1)
        self.assertIn(type(result.answers[0]), (PredicateAnswer, RefusalAnswer))
        self.assertEqual(result.provenance.origin, "http")
