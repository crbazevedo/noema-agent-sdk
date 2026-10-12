# Typed decision providers

Noema exposes a separate `DecisionProvider.decide` boundary for bounded semantic
judgments. It does not replace `ModelProvider.generate`, make an agent autonomous,
or grant permission to execute an action. Use deterministic code for arithmetic,
dates, budgets, freshness checks, authority and leases.

## Verified support matrix

Documentation checked 2026-10-12; HTTP contract tests use synthetic fixtures.
No live provider or deployed gateway was tested for this change.

| Noema adapter | Actual route | Predicate / choice / score | Limits in this adapter |
|---|---|---|---|
| `LiteLLMDecisionsProvider` (preferred configured gateway) | `/v1/decisions` | All three; native gateway translation to OpenAI or TypeSafe | Text only; gateway must support Decisions and have configured aliases |
| `LiteLLMDecisionsProvider(wire_format="systemone")` | `/v1/systemone` | Predicate maps to Noul; choice and score | String choices only |
| `OpenAIDecisionsProvider` | `https://api.openai.com/v1/decisions` | All three, including boolean choices | Text only; image input deliberately outside portable boundary |
| `TypeSafeDecisionsProvider` | `https://api.typesafe.ai/v1/systemone` | Noul, Choice and Score | String choices only; no boolean coercion |

This is genuine Decisions routing, not JSON generation through chat completions.
The LiteLLM integration is an HTTP **gateway client**, not a dependency on the
LiteLLM Python SDK. Installing Noema's extra does not install or start a gateway.

The [LiteLLM endpoint documentation](https://docs.litellm.ai/docs/decisions)
specifies both routes in stable **1.104.2+ on the 1.104.x line**, and
**1.105.0-rc.3 and later**. Its `1.106.0-dev.1` build used a different format at
`/v1/decisions`; avoid that build for the default adapter. Do not infer support
from ordinary OpenAI-compatible completion routes. The
[1.104.2 release notes](https://docs.litellm.ai/release_notes/v1.104.2/v1-104-2)
confirm the new endpoint and providers. Noema does not probe server version or
silently switch routes or providers.

Native contract references:
[OpenAI Decisions](https://developers.openai.com/api/reference/resources/decisions/methods/create),
[TypeSafe System One](https://docs.typesafe.ai/api).

## Setup and first request

Install the optional async HTTP transport:

```bash
pip install 'noema-agent-sdk[decisions]'
```

For an existing approved LiteLLM gateway, configure distinct model aliases:

```yaml
model_list:
  - model_name: luna-decisions
    litellm_params:
      model: openai/gpt-6-luna
      api_key: os.environ/OPENAI_API_KEY
  - model_name: jev-decisions
    litellm_params:
      model: typesafe/jev-latest
      api_key: os.environ/TYPESAFE_API_KEY
```

Use a single upstream per alias and disable gateway fallback/retry policies if
exact provider identity and one-attempt charging are required. The adapter cannot
verify server-side routing from an alias alone. Review gateway logging, retention
and access before transmitting data. Do not put personal financial information
into this tutorial or its smoke test.

```python
import asyncio
import os
from noema.adapters.decisions import LiteLLMDecisionsProvider
from noema.decisions import DecisionRequest, PredicateQuestion, PredicateAnswer

async def main():
    provider = LiteLLMDecisionsProvider(
        model="jev-decisions",  # use luna-decisions for the other configured alias
        base_url=os.environ["LITELLM_BASE_URL"],  # includes /v1
        api_key=os.environ["LITELLM_API_KEY"],
        timeout_seconds=15,
        max_retries=0,
    )
    result = await provider.decide(DecisionRequest(
        input="Synthetic example: A venue says its entrance has three steps.",
        questions=(PredicateQuestion(
            name="steps_reported",
            instructions="Does the text explicitly report entrance steps?",
        ),),
        rubric_version="venue-access-v1",
    ))
    answer = result.answers[0]
    if isinstance(answer, PredicateAnswer):
        print(answer.probability)  # classify the statement; do not reserve a venue
    else:
        print("Question refused; human review needed")

# Running this makes a billable external request. Run only after approving it.
# asyncio.run(main())
```

For direct access, explicitly select `OpenAIDecisionsProvider(api_key=...)` or
`TypeSafeDecisionsProvider(api_key=...)`; their defaults are `gpt-6-luna` and
`jev-latest`. Credentials come from the application's chosen environment/vault,
never from Noema's core or traces. There is no automatic fallback to direct access.

Additional independent question types:

```python
from noema.decisions import ChoiceQuestion, ChoiceOption, ScoreQuestion, ScoreLevel

team = ChoiceQuestion("team", "Which team should review?", (
    ChoiceOption("support", "Technical issue"),
    ChoiceOption("sales", "New purchase inquiry"),
))
severity = ScoreQuestion("severity", "Rate the described impact", (
    ScoreLevel("minor", "Cosmetic only"),
    ScoreLevel("workaround", "A task needs an alternative workflow"),
    ScoreLevel("blocked", "The task cannot be completed"),
))
```

Answers preserve per-option probabilities and provider confidence. Score is the
weighted zero-based level index, not a selected category or a success probability.
If one question depends on another answer, use a second request.

## Semantics and safety

- Predicate probability concerns the stated classification. It is not evidence
  that an intervention will succeed or that a future event will occur.
- Provider confidence summarizes its output distribution. Application calibration
  needs labeled, held-out examples and explicit false-positive/negative costs.
- Responses never contain authorization. Apply hard policy, consent, freshness,
  budget and lease checks independently before any effect.
- Duplicate JSON keys, non-finite values, unknown/malformed answer types,
  mismatched names/options, invalid probabilities,
  inconsistent scores and invalid usage fail closed with `DecisionResponseError`.
  Explicit refusal remains `RefusalAnswer`, even in a partially answered batch.
- One overall async deadline includes retry waits. Cancellation propagates; it
  cannot revoke a request already received or billed by the remote service.
- Retries default to zero. Optional `max_retries` (0–5) retries only HTTP 429,
  502, 503, 504 and 529 with exponential delay and numeric Retry-After support.
  Transport errors, parse errors and timeouts are not retried. Retried attempts
  may incur more charges; usage is the final successful response, not an aggregate
  of failed attempts. Gateway retries may add attempts invisible to this client.
- Missing native routes produce `DecisionCapabilityError`; other non-200 statuses
  produce `DecisionHTTPError`. Raw HTTP bodies and transport exceptions are not
  emitted in messages or traces. Redirects are disabled. HTTPS is required except
  for loopback development gateways.
- Default HTTP clients are scoped and closed per call. Injected async clients are
  caller-owned and must support `post(..., json, headers, timeout, follow_redirects)`.
  Configure their HTTP-library logging separately; third-party instrumentation is
  outside Noema's redaction boundary.

Provenance contains adapter identity, requested and returned model, wire format,
rubric version, semantic request hash, client attempt count and provider request
ID when supplied. Gateway identity is not proof of its hidden upstream. `origin`
is `http` for the default transport, `injected_transport` for injected clients;
neither a fake response nor a replay should be presented as observed live inference.
A hash supports equality checks; it is not anonymization and may be guessable.
Noema's trace attributes contain only adapter identity, status and attempt count.

## Validation and optional live smoke

```bash
# Offline tests: no network inference, no credentials required.
NOEMA_DECISIONS_LIVE=0 python -m unittest discover -s tests -p test_decision_providers.py -v
```

The opt-in smoke requires `NOEMA_DECISIONS_LIVE=1`, `NOEMA_DECISIONS_PROVIDER`
(`litellm`, `openai`, or `typesafe`), and the matching API key environment variable.
LiteLLM also requires `LITELLM_BASE_URL` and `NOEMA_DECISION_MODEL`. It sends only a
fixed synthetic sentence. Without opt-in or credentials it skips. Enabling it can
incur provider charges; it was **not run** for this contribution.

The offline suite uses HTTPX `MockTransport` with realistic native payloads. It
checks all primitives, typed boolean/string distinction, route selection, refusal,
malformed distributions, exact question alignment, auth headers, error redaction,
retry limits, timeout and cancellation. These tests establish adapter behavior,
not live access, model quality, calibration or gateway deployment correctness.
