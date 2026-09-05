# G2 Live-Preparation Conformance Handoff

Status: bounded SDK integration support; not an ADR 0014 or ADR 0015 runtime.

## Frozen consumer coordinate

The shared consumer corpus remains frozen at:

- SDK source: `621be5a8a0823c1a02c893edc69967f552e0895d`
- path: `docs/pilot/fixtures/situated-partner-consumer-corpus-v1.json`
- SHA-256: `30b7f207ab11bf286e8bf4db320bd7c3fcad724d56995a395e23096fc0902f80`

Consumers should copy or read that exact artifact. This branch does not change
the envelope schema, Project Meridian fixture, contract source, or lock bytes.
Evaluate its 17 cases in strict order: shape, then referential/relational, then
permission/currentness. Passing an earlier layer never implies a later one.

## Usable SDK composition

[`examples/g2_live_prep_conformance.py`](../../examples/g2_live_prep_conformance.py)
shows the narrow supervised composition using fictional content and public SDK
APIs only:

1. derive opaque source and transmitted-view references from exact fictional
   UTF-8 content using `HmacOpaqueInformationIdDeriver`;
2. append real `InformationPolicy`, `InformationLineage`, and `PolicyBinding`
   records to the canonical SDK event store;
3. build `MODEL_CONTEXT` access and cross-domain disclosure requests containing
   the actual provider, destination trust domain, recipient, purpose, locality,
   principal snapshot, and `REDACTED` form;
4. admit both decisions with `InformationGovernanceAdmission` and re-resolve
   them from `InformationGovernanceProjection` immediately before dispatch;
5. verify that the exact transmitted message derives the admitted governed
   reference and call a capturing mock `ModelProvider`.

Run it without credentials or network access:

```bash
PYTHONPATH=src python examples/g2_live_prep_conformance.py
```

`GovernedContextAssembler` alone is insufficient for this material boundary: it
performs pure filtering but does not canonically admit its decisions or bind the
selected provider and exact request. A schema-valid reference, an application
alias such as `authorization_evidence=true`, or a matching content fingerprint
is also insufficient. These are addressing/integrity signals, not current
permission.

The mocked tests show that the provider sees only the content-derived redacted
view, and only after exact provider/destination/purpose decisions have been
admitted. The deterministic helper constructs a fixture `PrincipalSnapshot`
from externally supplied role state; it performs no authentication or
authorization itself. A second fixture snapshot without the required role
simulates Companion's post-withdrawal input, is re-admitted as denied, and
prevents a second provider call. This proves denial given that input, not that
the SDK observed or authenticated a withdrawal. Companion must supply canonical
withdrawal/current-role evidence at its independent pre-use gate. The SDK does
not claim a durable consent-revocation registry, and `QuarantinedInformationRef`
is not used as a substitute for withdrawal.

## Independent evidence dimensions

Keep these axes independent in Companion records and reports:

| Axis | G2 rehearsal value | Meaning |
|---|---|---|
| Source-world provenance | `fictional` | The packet makes no real-world claim. |
| Generation mechanism | `mocked-provider-boundary` here; fixture or model-backed later | How the answer was produced. |
| Physical playback evidence | `not-run` here | Whether output was observably played on a device. |

A live model operating on fictional lineage produces a model-backed inference
over fictional material. It does not turn the packet into documentary evidence,
an observed real-world fact, or proof that any generated words were played,
heard, understood, or acted on.

Operational `MODEL_CONTEXT` permission does not imply secondary use. The example
policy grants neither `EVALUATE` nor `LEARN`, and the tests prove both are denied
independently.

## Sufficiency and one generic gap

Existing SDK APIs are sufficient primitives for the bounded fictional G2
exercise when the Companion supplies its canonical current principal/permission
state and performs the final pre-use comparison shown by the example. They do
not, by themselves, structurally govern every `ModelProvider.generate()` call.

The remaining generic requirement is a future
`GovernedModelProviderAdmission` port that binds current canonical access and
disclosure decisions to the actual provider, destination, purpose, disclosure
form, complete request bytes, and canonical withdrawal evidence. It must fail
closed on a changed causal cut and must not imply `EVALUATE` or `LEARN`.

The expected-failure test
`test_future_provider_use_port_is_content_bound_and_current` records that gap for
architecture review without implementing it or weakening current conformance.
No provider call, acquisition system, presentation lifecycle, connector, audio
capture, learned allocation, or habit runtime is introduced by this branch.
