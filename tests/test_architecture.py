from __future__ import annotations

import ast
import hashlib
import unittest
from pathlib import Path

_PROHIBITED_BRAND_DIGEST = "790d99fa7bbad8fce9479676d4283da79d1b0528774f79714455b59c7e928d11"
_PROHIBITED_BRAND_LENGTH = 10
_TEXT_SUFFIXES = {
    ".env",
    ".example",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


class ArchitectureFitnessTests(unittest.TestCase):
    def test_retired_brand_token_is_absent_from_repository_text(self) -> None:
        repository = Path(__file__).parents[1]
        excluded = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "build", "dist"}
        violations: list[str] = []
        for path in repository.rglob("*"):
            if not path.is_file() or any(part in excluded for part in path.parts):
                continue
            if path.suffix not in _TEXT_SUFFIXES and path.name not in {"LICENSE", "Makefile"}:
                continue
            data = path.read_bytes().lower()
            path_data = str(path.relative_to(repository)).lower().encode()
            if self._contains_prohibited_brand(data) or self._contains_prohibited_brand(path_data):
                violations.append(str(path.relative_to(repository)))
        self.assertEqual(violations, [])

    @staticmethod
    def _contains_prohibited_brand(data: bytes) -> bool:
        return any(
            hashlib.sha256(data[index : index + _PROHIBITED_BRAND_LENGTH]).hexdigest()
            == _PROHIBITED_BRAND_DIGEST
            for index in range(len(data) - _PROHIBITED_BRAND_LENGTH + 1)
        )

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

    def test_autonomic_core_cannot_execute_dynamic_code_or_import_effect_plane(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        roots = (source_root / "autonomic", source_root / "forge")
        forbidden_effect_modules = {
            "adapters",
            "agent",
            "authority",
            "capabilities",
            "delivery",
            "kernel",
            "models",
            "reasoning",
            "scheduler",
            "store",
            "system",
            "telemetry",
            "tracing",
        }
        violations: list[str] = []
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and (
                        isinstance(node.func, ast.Name)
                        and node.func.id in {"compile", "eval", "exec"}
                        or isinstance(node.func, ast.Attribute)
                        and node.func.attr in {"compile", "eval", "exec"}
                    ):
                        function_name = (
                            node.func.id if isinstance(node.func, ast.Name) else node.func.attr
                        )
                        violations.append(f"{path.relative_to(source_root)} calls {function_name}")
                    if isinstance(node, ast.ImportFrom) and node.module:
                        if (
                            node.level >= 2
                            and node.module == "events"
                            and any(alias.name == "AsyncEventBus" for alias in node.names)
                        ):
                            violations.append(
                                f"{path.relative_to(source_root)} imports the event bus"
                            )
                        if "adapters" in node.module.split("."):
                            violations.append(
                                f"{path.relative_to(source_root)} imports {node.module}"
                            )
                        if (
                            node.level >= 2
                            and node.module.split(".")[0] in forbidden_effect_modules
                        ):
                            violations.append(
                                f"{path.relative_to(source_root)} imports effect plane "
                                f"{node.module}"
                            )
                        if node.module == "noema":
                            violations.append(
                                f"{path.relative_to(source_root)} imports the root effect surface"
                            )
                    if isinstance(node, ast.ImportFrom) and node.module is None:
                        if node.level >= 2:
                            violations.append(
                                f"{path.relative_to(source_root)} imports the root effect surface"
                            )
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == "noema":
                                violations.append(
                                    f"{path.relative_to(source_root)} imports the root "
                                    "effect surface"
                                )
                            if "adapters" in alias.name.split("."):
                                violations.append(
                                    f"{path.relative_to(source_root)} imports {alias.name}"
                                )
                            parts = alias.name.split(".")
                            if (
                                len(parts) >= 2
                                and parts[0] == "noema"
                                and parts[1] in forbidden_effect_modules
                            ):
                                violations.append(
                                    f"{path.relative_to(source_root)} imports effect plane "
                                    f"{alias.name}"
                                )
        self.assertEqual(violations, [])

    def test_shadow_worker_cannot_import_or_call_the_effect_plane(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        path = source_root / "shadow.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_modules = {"agent", "authority", "capabilities", "models", "reasoning"}
        forbidden_calls = {"authorize", "deliberate", "dispatch", "execute"}
        violations: list[str] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.split(".")[0] in forbidden_modules
            ):
                violations.append(f"imports {node.module}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in forbidden_calls
            ):
                violations.append(f"calls {node.func.attr}")
        self.assertEqual(violations, [])
