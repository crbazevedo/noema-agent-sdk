from __future__ import annotations

import ast
import unittest
from pathlib import Path


class ArchitectureFitnessTests(unittest.TestCase):
    def test_provider_sdks_are_confined_to_adapters(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        forbidden = {"openai", "nats", "psycopg", "boto3", "azure", "google.cloud"}
        violations: list[str] = []
        for path in source_root.rglob("*.py"):
            if "adapters" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    if any(name == item or name.startswith(f"{item}.") for item in forbidden):
                        violations.append(f"{path.relative_to(source_root)} imports {name}")
        self.assertEqual(violations, [])

    def test_incident_demo_has_no_mode_specific_application_branch(self) -> None:
        example = Path(__file__).parents[1] / "examples" / "autonomous_incident_agent.py"
        source = example.read_text(encoding="utf-8")
        self.assertNotIn("DeploymentMode", source)
        self.assertNotIn("MODE ==", source)
