"""Run matched lessons and report code size without assuming a Noema win."""

import argparse
import ast
import asyncio
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

from .lessons import run_lesson

HERE = Path(__file__).resolve().parent
FRAMEWORKS = ("noema", "adk", "langgraph")


def code_size(path):
    source = path.read_text()
    tree = ast.parse(source)
    docstrings = set()
    doc_nodes = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            value = body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                doc_nodes.add(id(body[0]))
                docstrings.update(range(body[0].lineno, body[0].end_lineno + 1))
    return {
        "physical_code_lines": sum(
            bool(line.strip()) and not line.lstrip().startswith("#") and number not in docstrings
            for number, line in enumerate(source.splitlines(), 1)
        ),
        "ast_statements": sum(
            isinstance(node, ast.stmt) and id(node) not in doc_nodes for node in ast.walk(tree)
        ),
    }


async def compare():
    outcomes = []
    trace_examples = {}
    for level in (1, 2, 3):
        reference = None
        for framework in FRAMEWORKS:
            result = await run_lesson(framework, level)
            behavior = {key: result[key] for key in ("calls", "notices", "world")}
            reference = behavior if reference is None else reference
            assert behavior == reference, f"Behavior mismatch: {framework}, level {level}"
            outcomes.append(
                {
                    "framework": framework,
                    "level": level,
                    "behavior_matches": True,
                    "tool_calls": len(result["calls"]),
                    "notices": len(result["notices"]),
                }
            )
            if level == 2:
                trace_examples[framework] = result["trace"]

    noema_trace = trace_examples["noema"]
    records = {
        kind: sum(event["type"] == kind for event in noema_trace)
        for kind in (
            "decision.proposed",
            "decision.authorized",
            "action.succeeded",
        )
    }
    assert all(records.values())
    parents = {event["id"] for event in noema_trace}
    causal = all(
        event["causation_id"] in parents
        for event in noema_trace
        if event["type"] in {"decision.authorized", "action.succeeded"}
    )
    assert causal
    inventory = {str(path.relative_to(HERE)): code_size(path) for path in sorted(HERE.glob("*.py"))}
    shared = ("domain.py", "lessons.py", "live.py")
    totals = {}
    for framework in FRAMEWORKS:
        implementation = inventory[f"{framework}_agent.py"]
        totals[framework] = {
            "adapter": implementation,
            "adapter_plus_shared": {
                metric: implementation[metric] + sum(inventory[name][metric] for name in shared)
                for metric in implementation
            },
        }
    return {
        "schema": "proactive-examples-observations-v1",
        "python": platform.python_version(),
        "noema_source_baseline": "621be5a8a0823c1a02c893edc69967f552e0895d",
        "versions": {
            package: importlib.metadata.version(package)
            for package in (
                "noema-agent-sdk",
                "google-adk",
                "langgraph",
                "langgraph-checkpoint-sqlite",
            )
        },
        "lessons": outcomes,
        "code_inventory": inventory,
        "code_totals": totals,
        "shared_application_files": list(shared),
        "native_noema_records_in_medium_lesson": records,
        "native_noema_authorization_and_success_have_observed_causal_parents": causal,
        "interpretation": {
            "observed_benefit": (
                "SDK-generated domain decision/authorization/action records and causal links, "
                "without application-written lifecycle logging."
            ),
            "scope": (
                "The supplied deterministic examples; not all idiomatic implementations "
                "or a framework-wide capability benchmark."
            ),
            "competitor_evidence": (
                "ADK session/node events and LangGraph state updates are retained too; "
                "they expose different native vocabularies."
            ),
            "not_proved": [
                "fewer Noema lines",
                "greater production reliability",
                "LLM quality or cost advantage",
                "automatic durable watches",
                "in-flight exactly-once effects",
            ],
        },
        "source_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(HERE.glob("*.py"))
        },
    }, trace_examples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result, traces = asyncio.run(compare())
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
        for framework, trace in traces.items():
            (args.output / f"{framework}-medium-trace.json").write_text(
                json.dumps(trace, indent=2) + "\n"
            )
    print(
        json.dumps({"lessons": result["lessons"], "code_totals": result["code_totals"]}, indent=2)
    )


if __name__ == "__main__":
    main()
