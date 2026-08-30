from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from noema import (
    ActionIntent,
    DeliberationRequest,
    Event,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    NoemaKernel,
    RecordingModelProvider,
    ReplayModelProvider,
    StaticModelProvider,
    StructuredModelReasoner,
)
from noema.adapters.models import OpenAIResponsesProvider


class ModelFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_recorded_model_call_replays_by_semantic_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.jsonl"
            response = ModelResponse("fake", "m1", '{"ok":true}', {"ok": True})
            recorder = RecordingModelProvider(StaticModelProvider([response]), path)
            first_request = ModelRequest(
                (ModelMessage("user", "inspect"),),
                response_schema={"type": "object"},
                correlation_id="run-a",
            )
            self.assertEqual(await recorder.generate(first_request), response)

            replay = ReplayModelProvider(path)
            replayed = await replay.generate(
                ModelRequest(
                    (ModelMessage("user", "inspect"),),
                    response_schema={"type": "object"},
                    correlation_id="run-b",
                )
            )
            self.assertEqual(replayed.output, {"ok": True})

    async def test_structured_reasoner_validates_and_builds_intent(self) -> None:
        intent = ActionIntent(
            "inspect",
            {"service": "api"},
            expected_value=5,
            information_value=2,
            attention_cost=1,
            confidence=0.9,
            idempotency_key="inspect:api",
        )
        output = {
            "intents": [intent.to_payload()],
            "hypotheses": [],
            "alternatives": ["wait"],
            "modes": ["observe", "operationalize"],
            "notes": [],
            "confidence": 0.9,
        }
        provider = StaticModelProvider([ModelResponse("fake", "m1", "", output)])
        kernel = NoemaKernel()
        await kernel.start()
        request = DeliberationRequest(
            "agent",
            Event("external.alert", "test"),
            await kernel.snapshot(),
            (),
            10,
        )
        result = await StructuredModelReasoner(provider).deliberate(request)
        self.assertEqual(result.intents, (intent,))
        self.assertEqual(result.alternatives, ("wait",))
        await kernel.stop()


class _FakeResponses:
    def __init__(self) -> None:
        self.payload = None

    async def create(self, **payload):
        self.payload = payload
        return {
            "id": "response-1",
            "model": "test-model",
            "status": "completed",
            "output_text": '{"ok":true}',
            "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        }


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


class OpenAIAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_responses_adapter_uses_current_structured_output_shape(self) -> None:
        client = _FakeClient()
        provider = OpenAIResponsesProvider("test-model", client=client)
        response = await provider.generate(
            ModelRequest(
                (ModelMessage("user", "return ok"),),
                response_schema={
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
                schema_name="ok_response",
                correlation_id="corr-1",
            )
        )
        self.assertEqual(response.output, {"ok": True})
        assert client.responses.payload is not None
        self.assertEqual(
            client.responses.payload["text"]["format"]["type"],
            "json_schema",
        )
        self.assertTrue(client.responses.payload["text"]["format"]["strict"])
        self.assertFalse(client.responses.payload["store"])
