"""Public synthetic inputs. Expected outcomes belong to separate tests/oracles."""
import csv
import io
from copy import deepcopy


def csv_text(rows):
    out = io.StringIO(newline="")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["event_id", "region", "occurred_at", "ingested_at", "amount"])
    w.writerows(rows)
    return out.getvalue()


def public_scenario(name="nominal"):
    rows = {
        "e0": ["e0", "North", "2026-09-30T10:00:00Z", "2026-10-01T09:00:00Z", "40"],
        "e1": ["e1", "North", "2026-10-01T10:00:00Z", "2026-10-01T11:00:00Z", "10"],
        "e2": ["e2", "North", "2026-10-02T10:00:00Z", "2026-10-03T09:00:00Z", "20"],
        "e3": ["e3", "North", "2026-10-03T10:00:00Z", "2026-10-06T09:00:00Z", "30"],
        "e4": ["e4", "North", "2026-10-03T11:00:00Z", "2026-10-03T12:00:00Z", "50"],
    }
    return {
        "name": name,
        "files": {
            "report_a.csv": csv_text([rows[k] for k in ["e1", "e2", "e3", "e4"]]),
            "report_b.csv": csv_text([rows[k] for k in ["e0", "e1", "e2", "e4"]]),
        },
        "claims": {
            "report_a.csv": {
                "period_amount": "110",
                "period_population": ["e1", "e2", "e3", "e4"],
                "basis": "occurred_at",
            },
            "report_b.csv": {
                "period_amount": "120",
                "period_population": ["e0", "e1", "e2", "e4"],
                "basis": "ingested_at",
            },
        },
        "window_start": "2026-10-01T00:00:00Z",
        "window_end": "2026-10-04T00:00:00Z",
        "region": "North",
        "source_read_budget": 4,
        "activity_budget": 1,
        "authorized": True,
        "wake_delay_seconds": 0.06,
        "analysis_delay_seconds": 0.06,
        "interventions": [],
        "repeat_scan": False,
    }


def public_scenarios():
    cases = [public_scenario()]
    for name, intervention in [
        ("cancel_before_wake", {"phase": "before_wake", "op": "cancel"}),
        (
            "revision_during_analysis",
            {"phase": "after_source_reads", "op": "revise", "region": None},
        ),
        ("revoke_during_analysis", {"phase": "after_source_reads", "op": "revoke"}),
        (
            "changed_bytes_during_analysis",
            {
                "phase": "after_source_reads",
                "op": "replace_file",
                "file": "report_a.csv",
                "text": "corrupted\n",
            },
        ),
        (
            "failure_after_stage",
            {"phase": "after_source_reads", "op": "fail_after_stage"},
        ),
    ]:
        case = public_scenario(name)
        case["interventions"] = [intervention]
        cases.append(case)
    case = public_scenario("budget_exhausted")
    case["source_read_budget"] = 3
    cases.append(case)
    case = public_scenario("repeat_scan")
    case["repeat_scan"] = True
    cases.append(case)
    case = public_scenario("honest_partial")
    case["files"]["report_b.csv"] = case["files"]["report_b.csv"].replace(",20\n", ",25\n")
    cases.append(case)
    case = public_scenario("malformed_csv")
    case["files"]["report_a.csv"] = "wrong,header\n1,2\n"
    cases.append(case)
    case = public_scenario("new_claim_during_analysis")
    case["interventions"] = [
        {
            "phase": "after_source_reads",
            "op": "new_source_claim",
            "file": "report_a.csv",
            "claims": {"period_amount": "999"},
        }
    ]
    cases.append(case)
    case = public_scenario("event_while_scan_queued")
    case["interventions"] = [
        {
            "phase": "while_scan_queued",
            "op": "unrelated_event",
            "value": "new observation during strict scan admission",
        }
    ]
    cases.append(case)
    return cases


def revised_scenarios():
    cases = []
    for name, phase, renew, reads, kind in [
        ("revised_before_wake", "before_wake", True, 8, "report_scope"),
        ("revised_after_reads", "after_source_reads", True, 8, "report_scope"),
        ("revision_without_permission", "before_wake", False, 8, "report_scope"),
        (
            "revision_lifetime_budget_exhausted",
            "after_source_reads",
            True,
            4,
            "report_scope",
        ),
        ("unsupported_revision", "before_wake", True, 8, "new_external_effect"),
    ]:
        case = public_scenario(name)
        case.update(activity_budget=2, preparation_budget=2, source_read_budget=reads)
        for filename in case["files"]:
            case["files"][filename] += "e5,South,2026-10-02T00:00:00Z,2026-10-02T01:00:00Z,15\n"
        revised_claims = deepcopy(case["claims"])
        revised_claims["report_a.csv"]["period_amount"] = "125"
        revised_claims["report_b.csv"]["period_amount"] = "135"
        for claim in revised_claims.values():
            claim["period_population"].append("e5")

        case["interventions"] = [
            {
                "phase": phase,
                "op": "revise_and_reauthorize",
                "revision_kind": kind,
                "scope": {
                    "region": None,
                    "window_start": case["window_start"],
                    "window_end": case["window_end"],
                },
                "claims": revised_claims,
                "renew_authorization": renew,
                "wake_delay_seconds": 0.04,
                "deadline_seconds": 60,
            }
        ]
        cases.append(case)
    case = public_scenario("out_of_range_amount_rejected")
    case["files"] = {
        k: v.replace(",10\n", ",123456789012345678901234567890.12\n")
        for k, v in case["files"].items()
    }
    cases.append(case)
    for name, field, value in [
        (
            "malformed_revision_region",
            "scope",
            {
                "region": 123,
                "window_start": "2026-10-01T00:00:00Z",
                "window_end": "2026-10-04T00:00:00Z",
            },
        ),
        ("missing_revision_deadline", "deadline_seconds", None),
    ]:
        case = deepcopy(cases[0])
        case["name"] = name
        case["interventions"][0][field] = value
        cases.append(case)
    return cases
