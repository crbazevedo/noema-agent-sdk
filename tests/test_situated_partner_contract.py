from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re
import unittest
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator

from examples.situated_partner_conformance import (
    FIXTURE_PATH,
    REQUIRED_CASES,
    SCHEMA_PATH,
    SPECIFIED_ONLY_CASES,
    SYNTHETICALLY_VERIFIED_CASES,
    PilotObserverProjection,
    envelope_by_id,
    existing_api_evidence,
    is_surface_eligible,
    load_fixture,
    load_schema,
    run_conformance,
    validate_envelope,
)
from noema import AssertionStatus, AuthorityLevel, EpistemicType, GoalStatus
from noema.schema import SchemaValidationError

REPOSITORY = Path(__file__).parents[1]
CONTRACT_PATH = REPOSITORY / "docs" / "pilot" / "situated-partner-contract-v1.json"
INTEGRATION_PATH = REPOSITORY / "docs" / "pilot" / "SITUATED_PARTNER_INTEGRATION.md"
EXPECTED_SOURCE_DIGEST = (
    "sha256:ce7cc401f1d4452c491acf438828dea801b5fc7e104a0a09cc6970cde1e6e587"
)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("expected object")
    return cast(Mapping[str, object], value)


class SituatedPartnerContractTests(unittest.TestCase):
    def test_requirement_traceability_digest_and_backlog_dag(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        requirements = tuple(_mapping(value) for value in contract["requirements"])
        cases = tuple(_mapping(value) for value in contract["acceptance_cases"])
        milestones = tuple(_mapping(value) for value in contract["milestones"])
        backlog = tuple(_mapping(value) for value in contract["backlog"])

        requirement_ids = {str(value["id"]) for value in requirements}
        self.assertEqual(requirement_ids, {f"REQ-{index:02d}" for index in range(1, 27)})
        self.assertEqual(
            contract["source_requirements_digest"],
            EXPECTED_SOURCE_DIGEST,
        )
        self.assertEqual(contract["source_acceptance_case_status"], "specified_not_executed")
        self.assertIn("only", contract["sdk_coverage_status_scope"])
        self.assertIn("only", contract["acceptance_case_status_scope"])
        self.assertEqual(
            load_schema()["properties"]["source_requirements_digest"]["enum"],
            [EXPECTED_SOURCE_DIGEST],
        )
        schema_properties = _mapping(load_schema()["properties"])
        source_result = _mapping(schema_properties["source_result"])
        source_result_properties = _mapping(source_result["properties"])
        result_status = _mapping(source_result_properties["status"])
        self.assertEqual(
            set(cast(list[str], result_status["enum"])),
            {
                "FOUND",
                "NO_MATCH_IN_SCOPE",
                "NOT_YET_AVAILABLE",
                "SOURCE_UNAVAILABLE",
                "ACCESS_DENIED",
                "AMBIGUOUS_MATCH",
                "FACT_NOT_ESTABLISHED",
                "CONTRADICTED",
            },
        )
        task = _mapping(schema_properties["task"])
        task_status = _mapping(_mapping(task["properties"])["state"])
        self.assertNotIn("stale", cast(list[str], task_status["enum"]))
        self.assertEqual(load_fixture()["source_requirements_digest"], EXPECTED_SOURCE_DIGEST)

        status_vocabulary = set(contract["status_vocabulary"])
        readiness_vocabulary = set(contract["readiness_vocabulary"])
        case_ids = {str(value["id"]) for value in cases}
        milestone_ids = {str(value["id"]) for value in milestones}
        self.assertEqual(case_ids, {f"T{index:02d}" for index in range(1, 38)})
        self.assertTrue(set(REQUIRED_CASES) <= case_ids)
        for requirement in requirements:
            self.assertEqual(requirement["program_status"], "USER_APPROVED_REQUIREMENT")
            self.assertIn(requirement["sdk_coverage_status"], status_vocabulary)
            self.assertIn(requirement["sdk_readiness"], readiness_vocabulary)
            self.assertTrue(set(requirement["dependencies"]) <= requirement_ids)
            self.assertTrue(set(requirement["acceptance_cases"]) <= case_ids)
            self.assertTrue(set(requirement["delivery_slices"]) <= milestone_ids)
            self.assertTrue(requirement["acceptance_cases"])
            spec_path, anchor = str(requirement["authoritative_spec"]).split("#", 1)
            self.assertEqual(spec_path, "docs/pilot/SITUATED_PARTNER_INTEGRATION.md")
            self.assertIn(anchor, INTEGRATION_PATH.read_text(encoding="utf-8"))
        self.assertFalse(
            {"LIVE_SUPERVISED", "PILOT_VALIDATED"}
            & {str(value["status"]) for value in cases}
        )
        self.assertEqual(
            {
                str(value["id"])
                for value in cases
                if value["status"] == "SYNTHETICALLY_VERIFIED"
                and value["id"] in REQUIRED_CASES
            },
            set(SYNTHETICALLY_VERIFIED_CASES),
        )
        self.assertEqual(
            set(REQUIRED_CASES) - set(SYNTHETICALLY_VERIFIED_CASES),
            set(SPECIFIED_ONLY_CASES),
        )
        for case in cases:
            if case["status"] == "SYNTHETICALLY_VERIFIED":
                evidence = str(case["evidence"])
                self.assertTrue(hasattr(type(self), evidence), evidence)

        work_by_id = {str(value["id"]): value for value in backlog}
        self.assertEqual(set(work_by_id), {f"W{index:02d}" for index in range(17)})
        seen: set[str] = set()
        while len(seen) < len(work_by_id):
            ready = {
                work_id
                for work_id, work in work_by_id.items()
                if set(cast(list[str], work["depends_on"])) <= seen
            } - seen
            self.assertTrue(ready, "backlog dependency cycle")
            seen.update(ready)
        self.assertEqual(seen, set(work_by_id))
        self.assertEqual(work_by_id["W14"]["depends_on"], ["W11"])

    def test_new_document_links_resolve(self) -> None:
        documents = (
            INTEGRATION_PATH,
            REPOSITORY / "docs" / "adr" / "0014-durable-situation-watch-and-source-acquisition.md",
            REPOSITORY / "docs" / "adr" / "0015-durable-material-output-presentation.md",
        )
        link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
        for document in documents:
            for raw_target in link_pattern.findall(document.read_text(encoding="utf-8")):
                if raw_target.startswith(("http://", "https://", "#")):
                    continue
                target = raw_target.split("#", 1)[0]
                self.assertTrue((document.parent / target).resolve().is_file(), raw_target)

    def test_envelope_schema_rejects_unknown_version_and_mixed_source_shape(self) -> None:
        fixture = load_fixture()
        schema = load_schema()
        Draft202012Validator.check_schema(schema)
        envelope = dict(envelope_by_id(fixture, "envelope:meridian:notes-request:2"))
        validate_envelope(envelope, schema)
        Draft202012Validator(schema).validate(envelope)

        future = dict(envelope)
        future["schema_version"] = 2
        with self.assertRaises(SchemaValidationError):
            validate_envelope(future, schema)
        self.assertTrue(tuple(Draft202012Validator(schema).iter_errors(future)))

        mixed = dict(envelope)
        mixed["source_result"] = envelope_by_id(
            fixture, "envelope:meridian:notes-result:2"
        )["source_result"]
        with self.assertRaisesRegex(ValueError, "request data and no result"):
            validate_envelope(mixed, schema)
        self.assertTrue(tuple(Draft202012Validator(schema).iter_errors(mixed)))

        unrevalidated = copy.deepcopy(
            envelope_by_id(fixture, "envelope:meridian:decision-card:1")
        )
        material = cast(dict[str, object], unrevalidated["material_output"])
        material["revalidated_context_revision"] = None
        material["revalidated_at_causal_cut"] = None
        with self.assertRaisesRegex(ValueError, "explicit revalidation"):
            validate_envelope(unrevalidated, schema)
        self.assertTrue(tuple(Draft202012Validator(schema).iter_errors(unrevalidated)))

        encoded_conditions = json.dumps(schema["allOf"], sort_keys=True)
        self.assertIn('"const": "source_acquisition_request"', encoded_conditions)
        self.assertIn('"const": "source_acquisition_result"', encoded_conditions)
        self.assertIn('"const": "material_output"', encoded_conditions)

        for value in cast(list[object], fixture["envelopes"]):
            Draft202012Validator(schema).validate(value)

    def test_cross_domain_payload_requires_matching_admitted_disclosure(self) -> None:
        fixture = load_fixture()
        schema = load_schema()
        envelope = copy.deepcopy(
            envelope_by_id(fixture, "envelope:meridian:notes-request:2")
        )
        governance = cast(dict[str, object], envelope["governance"])
        governance["target_trust_domain"] = "trust-domain:fictional-provider"
        governance["disclosure_decision_refs"] = [
            "disclosure_dddddddddddddddddddddddddddddddd"
        ]
        governance["disclosure_view_ref"] = "view_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        with self.assertRaisesRegex(ValueError, "admitted disclosure form"):
            validate_envelope(envelope, schema)
        governance["payload_fingerprint"] = f"hmac-sha256:{'a' * 64}"
        governance["admitted_payload_fingerprint"] = f"hmac-sha256:{'b' * 64}"
        with self.assertRaisesRegex(ValueError, "admitted disclosure form"):
            validate_envelope(envelope, schema)
        governance["admitted_payload_fingerprint"] = governance["payload_fingerprint"]
        validate_envelope(envelope, schema)

    def test_reschedule_cancels_obsolete_check(self) -> None:
        fixture = load_fixture()
        old_request = envelope_by_id(fixture, "envelope:meridian:calendar-request:1")
        cancellation = envelope_by_id(fixture, "envelope:meridian:calendar-cancelled:1")
        lifecycle = _mapping(old_request["lifecycle"])
        cancelled = _mapping(cancellation["lifecycle"])
        payload = _mapping(cancellation["payload"])

        self.assertIsNone(lifecycle["superseded_by_envelope_id"])
        self.assertEqual(cancelled["supersedes_envelope_id"], old_request["envelope_id"])
        self.assertEqual(cancelled["cancelled_by_event_id"], "event:calendar-rescheduled")
        self.assertTrue(payload["business_cutoff_unchanged"])
        self.assertNotEqual(payload["old_scheduled_start"], payload["new_scheduled_start"])
        self.assertEqual(
            fixture["scenario"]["independent_business_cutoff"],
            "2031-05-14T18:30:00+00:00",
        )

    def test_calendar_end_remains_epistemically_unresolved(self) -> None:
        fixture = load_fixture()
        case = _mapping(fixture["case_inputs"])["T02"]
        api = existing_api_evidence()
        self.assertTrue(_mapping(case)["scheduled_end_passed"])
        self.assertIsNone(_mapping(case)["actual_outcome_evidence"])
        self.assertEqual(_mapping(case)["expected_belief"], "unknown")
        self.assertIs(api.fact.epistemic_type, EpistemicType.OBSERVED)
        self.assertIs(api.forecast.epistemic_type, EpistemicType.SIMULATED)
        self.assertIs(api.forecast.status, AssertionStatus.HYPOTHESIS)

    def test_sleep_gap_is_reported_and_caught_up(self) -> None:
        fixture = load_fixture()
        case = _mapping(_mapping(fixture["case_inputs"])["T09"])
        api = existing_api_evidence()
        slept_from = datetime.fromisoformat(str(case["slept_from"]))
        woke_at = datetime.fromisoformat(str(case["woke_at"]))

        self.assertGreater(woke_at, slept_from)
        self.assertEqual(case["coverage_claim"], "awake_only")
        self.assertTrue(case["catch_up_required"])
        self.assertFalse(api.coverage.sufficient)
        self.assertGreater(api.coverage.weighted_uncertainty, 0.0)

    def test_cancelled_goal_prevents_stale_surface(self) -> None:
        fixture = load_fixture()
        case = _mapping(_mapping(fixture["case_inputs"])["T10"])
        api = existing_api_evidence()
        current = envelope_by_id(fixture, "envelope:river:context:3")
        stale = envelope_by_id(fixture, "envelope:meridian:calendar-result:late")

        self.assertIs(api.cancelled_goal.status, GoalStatus.CANCELLED)
        self.assertIs(api.current_goal.status, GoalStatus.ACTIVE)
        self.assertEqual(case["goal_status"], GoalStatus.CANCELLED.value)
        self.assertFalse(case["surface_eligible"])
        self.assertFalse(
            is_surface_eligible(
                stale,
                current,
                current_goal_status=api.current_goal.status,
            )
        )

    def test_budget_exhaustion_defers_without_extra_work(self) -> None:
        fixture = load_fixture()
        case = _mapping(_mapping(fixture["case_inputs"])["T11"])
        budget = _mapping(case["budget"])
        usage = _mapping(case["usage"])
        self.assertEqual(budget["max_query_calls"], usage["query_calls"])
        self.assertEqual(budget["max_content_reads"], usage["content_reads"])
        self.assertEqual(budget["max_model_calls"], usage["model_calls"])
        self.assertEqual(case["next_state"], "blocked")
        self.assertEqual(case["additional_calls"], 0)
        self.assertEqual(existing_api_evidence().observation_budget.max_sources, 2)
        envelope = copy.deepcopy(
            envelope_by_id(load_fixture(), "envelope:meridian:notes-request:2")
        )
        task = cast(dict[str, object], envelope["task"])
        usage = cast(dict[str, object], task["usage"])
        usage["query_calls"] = 3
        with self.assertRaisesRegex(ValueError, "query_calls budget"):
            validate_envelope(envelope, load_schema())

    def test_observer_projection_is_independent_of_otel(self) -> None:
        report = asyncio.run(run_conformance())
        case = _mapping(_mapping(load_fixture()["case_inputs"])["T13"])
        self.assertFalse(case["otel_available"])
        self.assertTrue(case["canonical_observer_available"])
        self.assertEqual(report.replay_cursor, report.canonical_event_count)
        self.assertIsNotNone(PilotObserverProjection())

    def test_stale_result_cannot_answer_current_topic(self) -> None:
        fixture = load_fixture()
        api = existing_api_evidence()
        current = envelope_by_id(fixture, "envelope:river:context:3")
        stale = envelope_by_id(fixture, "envelope:meridian:calendar-result:late")
        self.assertFalse(
            is_surface_eligible(
                stale,
                current,
                current_goal_status=api.current_goal.status,
            )
        )
        self.assertFalse(_mapping(stale["payload"])["surface_eligible"])
        self.assertEqual(_mapping(stale["freshness"])["state"], "stale")

    def test_surface_guard_rechecks_authority_policy_and_artifact_basis(self) -> None:
        api = existing_api_evidence()
        candidate = copy.deepcopy(
            envelope_by_id(load_fixture(), "envelope:meridian:decision-card:1")
        )
        self.assertTrue(
            is_surface_eligible(candidate, candidate, current_goal_status=api.goal.status)
        )

        obsolete_authority = copy.deepcopy(candidate)
        context = cast(dict[str, object], obsolete_authority["context"])
        context["goal_revision_id"] = api.current_goal.revision_id
        context["outcome_id"] = api.current_outcome.node_id
        self.assertFalse(
            is_surface_eligible(
                candidate,
                obsolete_authority,
                current_goal_status=api.current_goal.status,
            )
        )

        changed_artifact = copy.deepcopy(candidate)
        current_context = cast(dict[str, object], changed_artifact["context"])
        artifact_versions = cast(list[object], current_context["artifact_versions"])
        artifact = cast(dict[str, object], artifact_versions[0])
        artifact["version"] = 2
        self.assertFalse(
            is_surface_eligible(
                candidate,
                changed_artifact,
                current_goal_status=api.goal.status,
            )
        )

        changed_policy = copy.deepcopy(candidate)
        governance = cast(dict[str, object], changed_policy["governance"])
        governance["policy_snapshot_refs"] = ["policy_ffffffffffffffffffffffffffffffff"]
        self.assertFalse(
            is_surface_eligible(
                candidate,
                changed_policy,
                current_goal_status=api.goal.status,
            )
        )

        changed_correlation = copy.deepcopy(candidate)
        correlation = cast(dict[str, object], changed_correlation["correlation"])
        correlation["session_id"] = "session:other"
        correlation["turn_id"] = "turn:other"
        correlation["request_id"] = "request:other"
        self.assertFalse(
            is_surface_eligible(
                candidate,
                changed_correlation,
                current_goal_status=api.goal.status,
            )
        )

        revoked_access = copy.deepcopy(candidate)
        governance = cast(dict[str, object], revoked_access["governance"])
        governance["access_decision_refs"] = []
        governance["lineage_refs"] = []
        governance["policy_binding_refs"] = []
        self.assertFalse(
            is_surface_eligible(
                candidate,
                revoked_access,
                current_goal_status=api.goal.status,
            )
        )

        changed_disclosure = copy.deepcopy(candidate)
        governance = cast(dict[str, object], changed_disclosure["governance"])
        governance["target_trust_domain"] = "trust-domain:fictional-provider"
        governance["disclosure_decision_refs"] = [
            "disclosure_dddddddddddddddddddddddddddddddd"
        ]
        governance["disclosure_view_ref"] = "view_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        governance["payload_fingerprint"] = f"hmac-sha256:{'a' * 64}"
        governance["admitted_payload_fingerprint"] = governance["payload_fingerprint"]
        self.assertFalse(
            is_surface_eligible(
                candidate,
                changed_disclosure,
                current_goal_status=api.goal.status,
            )
        )

    def test_excluded_source_produces_no_observation(self) -> None:
        case = _mapping(_mapping(load_fixture()["case_inputs"])["T25"])
        self.assertEqual(case["scope_state"], "excluded")
        self.assertEqual(case["observations"], [])
        self.assertEqual(case["durable_observation_scope_runtime"], "unimplemented")

    def test_solicited_only_corpus_keeps_learning_blocked(self) -> None:
        case = _mapping(_mapping(load_fixture()["case_inputs"])["T30"])
        self.assertEqual(case["source_event_families"], ["conversation.requested"])
        self.assertFalse(case["unsolicited_denominator_present"])
        self.assertFalse(case["learning_eligible"])

    def test_restricted_source_waits_for_storage_and_permission_gates(self) -> None:
        case = _mapping(_mapping(load_fixture()["case_inputs"])["T31"])
        self.assertEqual(case["classification"], "restricted")
        self.assertEqual(case["storage_gate"], "blocked")
        self.assertEqual(case["access_disposition"], "deny")

    def test_current_intent_outranks_historical_pattern(self) -> None:
        case = _mapping(_mapping(load_fixture()["case_inputs"])["T35"])
        api = existing_api_evidence()
        self.assertNotEqual(case["historical_goal_revision_id"], case["current_goal_revision_id"])
        self.assertEqual(case["historical_goal_revision_id"], api.goal.revision_id)
        self.assertEqual(case["current_goal_revision_id"], api.current_goal.revision_id)
        self.assertEqual(api.cancelled_goal.supersedes_revision_id, api.goal.revision_id)
        self.assertEqual(case["governing_revision_id"], case["current_goal_revision_id"])

    def test_g1_integrated_contract_boundary(self) -> None:
        report = asyncio.run(run_conformance(FIXTURE_PATH))
        self.assertEqual(report.fixture_id, "situated-partner:project-meridian:g1:v1")
        self.assertEqual(report.evaluated_cases, REQUIRED_CASES)
        self.assertEqual(report.synthetically_verified_cases, SYNTHETICALLY_VERIFIED_CASES)
        self.assertEqual(report.specified_only_cases, SPECIFIED_ONLY_CASES)
        self.assertEqual(report.canonical_event_count, 20)
        self.assertEqual(report.replay_cursor, 20)
        self.assertIn("material-output-presentation-receipts", report.blocked_runtime_lanes)
        self.assertEqual(existing_api_evidence().order.authority_ceiling, AuthorityLevel.PROPOSE)

    def test_contract_source_files_have_stable_nonempty_digests(self) -> None:
        for path in (CONTRACT_PATH, SCHEMA_PATH, FIXTURE_PATH):
            self.assertTrue(path.is_file())
            self.assertEqual(len(hashlib.sha256(path.read_bytes()).hexdigest()), 64)


if __name__ == "__main__":
    unittest.main()
