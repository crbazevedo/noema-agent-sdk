"""Alias-only mapping for a falsifiable declaration-only transfer test.

No aggregation, conjunction, verdict interpretation or test simulation is allowed
in this adapter. Unsupported requirements remain visible instead of being hidden
in procedural glue. Original domain facts remain available to both systems.
"""

from __future__ import annotations

from typing import Any

from commitment_lifecycle_domain import Scenario


def map_scenario(data: dict[str, Any], mapping: dict[str, Any]) -> Scenario:
    aliases = mapping["aliases"]
    commands = []
    if "contract" in mapping:
        commands.append({"op": "update", "facts": {"evidence_contract": mapping["contract"]}})
    for original in data["commands"]:
        command = dict(original)
        for field in ("facts", "before_effect"):
            if field in command:
                values = dict(command[field])
                values.update(
                    {aliases[key]: value for key, value in command[field].items() if key in aliases}
                )
                command[field] = values
        commands.append(command)
    return Scenario(data["name"], tuple(commands), data.get("expected_revision", 1))


async def main():
    import argparse
    import importlib
    import json
    from pathlib import Path

    from commitment_lifecycle import run_scenario

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--domain-module",
        choices=(
            "commitment_lifecycle_domain",
            "compositional_lifecycle_domain",
            "artifact_import_domain",
        ),
        default="commitment_lifecycle_domain",
    )
    args = parser.parse_args()
    module = importlib.import_module(args.domain_module)
    mapping = json.loads(args.mapping.read_text())
    cases = json.loads(args.scenarios.read_text())
    results = []
    for case in cases:
        result = await run_scenario(
            map_scenario(case, mapping), domain_module=module, artifact_dir=args.output.parent
        )
        results.append(result)
        args.output.write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps({"scenario": case["name"], **result["metrics"]}))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
