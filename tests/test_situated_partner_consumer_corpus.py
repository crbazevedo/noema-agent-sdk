from __future__ import annotations

import copy
import hashlib
import json
import unittest
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from examples.situated_partner_conformance import (
    envelope_by_id,
    load_fixture,
    load_schema,
    validate_envelope,
)
from noema import (
    Classification,
    DisclosureForm,
    GovernedInformationRef,
    HmacOpaqueInformationIdDeriver,
    InformationAccessRequest,
    InformationGovernanceAdmission,
    InformationGovernanceEngine,
    InformationGovernanceProjection,
    InformationLineage,
    InformationOperation,
    InformationPolicy,
    LineageTransformation,
    NoemaKernel,
    PolicyBinding,
    PrincipalSnapshot,
    RetentionPolicy,
)

REPOSITORY = Path(__file__).parents[1]
CORPUS_PATH = (
    REPOSITORY
    / "docs"
    / "pilot"
    / "fixtures"
    / "situated-partner-consumer-corpus-v1.json"
)
LOCK_PATH = REPOSITORY / "docs" / "pilot" / "situated-partner.lock.json"
WORKFLOW_PATH = REPOSITORY / ".github" / "workflows" / "ci.yml"
ADMISSION_TIME = datetime(2031, 5, 14, 14, 5, tzinfo=UTC)
TEST_DERIVER = HmacOpaqueInformationIdDeriver(
    b"0123456789abcdef0123456789abcdef"
)


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be an object")
    return cast(Mapping[str, object], value)


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return dict(_mapping(value, str(path)))


def _strict_shape_validate(envelope: Mapping[str, object]) -> None:
    # JSON Schema's Python number checker accepts NaN/Infinity. They are not
    # RFC JSON values, so transport validity is an explicit part of layer one.
    json.dumps(envelope, allow_nan=False)
    Draft202012Validator(load_schema()).validate(envelope)


def _mutate(envelope: dict[str, object], mutation: Mapping[str, object]) -> None:
    path = str(mutation["path"])
    parts = tuple(part.replace("~1", "/").replace("~0", "~") for part in path.split("/")[1:])
    if not parts:
        raise ValueError("mutation must target a nested path")
    parent: dict[str, object] = envelope
    for part in parts[:-1]:
        parent = cast(dict[str, object], parent[part])
    operation = mutation["op"]
    if operation == "remove":
        del parent[parts[-1]]
    elif operation == "set":
        parent[parts[-1]] = copy.deepcopy(mutation["value"])
    elif operation == "set_non_finite":
        token = mutation["token"]
        values = {"NaN": float("nan"), "Infinity": float("inf"), "-Infinity": -float("inf")}
        parent[parts[-1]] = values[str(token)]
    else:
        raise ValueError(f"unknown corpus mutation: {operation}")


def _inject_admitted_governance(
    envelope: dict[str, object],
    *,
    information_id: str,
    lineage_id: str,
    binding_id: str,
    policy_id: str,
    access_decision_id: str,
) -> None:
    governance = cast(dict[str, object], envelope["governance"])
    governance["information_refs"] = [information_id]
    governance["lineage_refs"] = [lineage_id]
    governance["policy_binding_refs"] = [binding_id]
    governance["policy_snapshot_refs"] = [policy_id]
    governance["access_decision_refs"] = [access_decision_id]


def _validate_permission_currentness(
    envelope: Mapping[str, object],
    projection: InformationGovernanceProjection,
    *,
    use_time: datetime,
) -> None:
    freshness = _mapping(envelope["freshness"], "freshness")
    if freshness["state"] != "current":
        raise ValueError("evidence is not current")
    lifecycle = _mapping(envelope["lifecycle"], "lifecycle")
    if lifecycle["cancelled_by_event_id"] is not None:
        raise ValueError("envelope is cancelled")
    if lifecycle["superseded_by_envelope_id"] is not None:
        raise ValueError("envelope is superseded")
    valid_until = lifecycle["valid_until"]
    if valid_until is not None and datetime.fromisoformat(str(valid_until)) <= use_time:
        raise ValueError("envelope is expired")

    governance = _mapping(envelope["governance"], "governance")
    information_ids = tuple(
        str(value) for value in cast(list[object], governance["information_refs"])
    )
    if not information_ids:
        raise ValueError("permission check requires governed information")
    lineage_ids = {str(value) for value in cast(list[object], governance["lineage_refs"])}
    binding_ids = {
        str(value) for value in cast(list[object], governance["policy_binding_refs"])
    }
    policy_ids = {
        str(value) for value in cast(list[object], governance["policy_snapshot_refs"])
    }
    decisions = []
    for decision_id in cast(list[object], governance["access_decision_refs"]):
        decision = projection.access_decision(str(decision_id))
        if decision is None or not decision.allowed:
            raise ValueError("access reference is not a canonical allowed decision")
        decisions.append(decision)

    for information_id in information_ids:
        lineage = projection.lineage(information_id)
        binding = projection.binding(information_id)
        if lineage is None or binding is None:
            raise ValueError("governance lineage or binding is unresolved")
        if lineage.lineage_id not in lineage_ids or binding.binding_id not in binding_ids:
            raise ValueError("envelope does not name the current lineage and binding")
        if not set(binding.policy_ids) <= policy_ids:
            raise ValueError("envelope does not name the binding's policy versions")
        matching = [
            decision
            for decision in decisions
            if decision.request.information_ref.information_id == information_id
        ]
        if len(matching) != 1:
            raise ValueError("governed information lacks one resolved access decision")
        context = matching[0].request.context
        if (
            context.purpose != governance["purpose"]
            or context.principal.principal_id != governance["principal_id"]
            or context.source_trust_domain != governance["source_trust_domain"]
            or tuple(context.policy_ids) != tuple(sorted(binding.policy_ids))
            or tuple(context.source_lineage_refs) != tuple(sorted(information_ids))
        ):
            raise ValueError("access decision does not admit the envelope's use context")


async def _admitted_reference_state() -> tuple[
    InformationGovernanceProjection, dict[str, str]
]:
    kernel = NoemaKernel()
    await kernel.start()
    try:
        information = GovernedInformationRef.create(
            namespace="corpus",
            stable_key="fictional-project-meridian-notes",
            deriver=TEST_DERIVER,
        )
        policy = InformationPolicy.create(
            version=1,
            origin_domains=("fictional-source",),
            classification=Classification.CONFIDENTIAL,
            allowed_purposes=("resolve-decision-owner",),
            allowed_recipients=("principal:fictional-user",),
            allowed_trust_domains=("trust-domain:fictional-local",),
            allowed_localities=("local",),
            allowed_providers=(),
            cross_agent_sharing=False,
            retention=RetentionPolicy(),
            disclosure_forms=(DisclosureForm.REDACTED,),
            declassification_authorities=(),
            recorded_at=ADMISSION_TIME,
        )
        lineage = InformationLineage.create(
            information_id=information.information_id,
            source_information_ids=(),
            transformation=LineageTransformation.SOURCE,
            recorded_at=ADMISSION_TIME,
        )
        binding = PolicyBinding.create(
            information_id=information.information_id,
            lineage_id=lineage.lineage_id,
            policy_ids=(policy.policy_id,),
            bound_at=ADMISSION_TIME,
        )
        for event in (
            policy.to_event(source="test:situated-partner-corpus"),
            lineage.to_event(source="test:situated-partner-corpus"),
            binding.to_event(source="test:situated-partner-corpus"),
        ):
            await kernel.emit(event)

        projection = InformationGovernanceProjection()
        projection.rebuild(await kernel.history())
        principal = PrincipalSnapshot.create(
            principal_id="principal:fictional-user",
            roles=(),
            groups=(),
            trust_domains=("trust-domain:fictional-local",),
            captured_at=ADMISSION_TIME,
        )
        engine = InformationGovernanceEngine(projection)
        request = InformationAccessRequest.create(
            information_ref=information,
            context=engine.context_for(
                information_ref=information,
                actor_id="agent:fictional-companion",
                principal=principal,
                purpose="resolve-decision-owner",
                operation=InformationOperation.READ,
                source_trust_domain="trust-domain:fictional-local",
                destination_trust_domain=None,
                recipient=None,
                decision_time=ADMISSION_TIME,
                locality="local",
            ),
        )
        receipt = await InformationGovernanceAdmission(
            kernel,
            projection,
            source="test:situated-partner-corpus",
        ).admit_access(request)
        if not receipt.record.allowed:
            raise AssertionError("synthetic corpus access was not admitted")
        projection.rebuild(await kernel.history())
        return projection, {
            "information_id": information.information_id,
            "lineage_id": lineage.lineage_id,
            "binding_id": binding.binding_id,
            "policy_id": policy.policy_id,
            "access_decision_id": receipt.record.decision_id,
        }
    finally:
        await kernel.stop()


class SituatedPartnerConsumerCorpusTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_positive_and_negative_corpus(self) -> None:
        corpus = _load_json(CORPUS_PATH)
        projection, references = await _admitted_reference_state()
        use_time = datetime.fromisoformat(str(corpus["use_time"]))
        seen: set[str] = set()

        for raw_case in cast(list[object], corpus["cases"]):
            case = _mapping(raw_case, "corpus case")
            case_id = str(case["case_id"])
            with self.subTest(case_id=case_id):
                self.assertNotIn(case_id, seen)
                seen.add(case_id)
                envelope = copy.deepcopy(
                    dict(envelope_by_id(load_fixture(), str(case["base_envelope_id"])))
                )
                if case["permission_profile"] == "admitted_sdk_records":
                    _inject_admitted_governance(envelope, **references)
                for raw_mutation in cast(list[object], case["mutations"]):
                    _mutate(envelope, _mapping(raw_mutation, "mutation"))

                actual = {
                    "shape": "PASS",
                    "referential_relational": "NOT_EVALUATED",
                    "permission_currentness": "NOT_EVALUATED",
                }
                try:
                    _strict_shape_validate(envelope)
                except (TypeError, ValueError, JsonSchemaValidationError):
                    actual["shape"] = "FAIL"
                else:
                    try:
                        validate_envelope(envelope, load_schema())
                    except (TypeError, ValueError):
                        actual["referential_relational"] = "FAIL"
                    else:
                        actual["referential_relational"] = "PASS"
                        try:
                            _validate_permission_currentness(
                                envelope,
                                projection,
                                use_time=use_time,
                            )
                        except (TypeError, ValueError):
                            actual["permission_currentness"] = "FAIL"
                        else:
                            actual["permission_currentness"] = "PASS"
                self.assertEqual(actual, case["expected"])

        self.assertEqual(len(seen), 17)

    async def test_frozen_contract_bytes_still_match_the_lock(self) -> None:
        lock = _load_json(LOCK_PATH)
        self.assertEqual(
            lock["sdk_contract_source_sha"],
            "2907b1fb6d9fac0d613a8574f6dea4bfa11c6ec8",
        )
        for relative, expected in _mapping(lock["files"], "locked files").items():
            actual = "sha256:" + hashlib.sha256(
                (REPOSITORY / str(relative)).read_bytes()
            ).hexdigest()
            self.assertEqual(actual, expected, relative)

    async def test_ci_keeps_minimal_tests_and_full_quality_dependencies(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertEqual(workflow.count("python -m pip install -e '.[dev]'"), 1)
        self.assertEqual(workflow.count("python -m pip install -e '.[dev,all]'"), 1)
        self.assertIn("make lint typecheck build", workflow)


if __name__ == "__main__":
    unittest.main()
