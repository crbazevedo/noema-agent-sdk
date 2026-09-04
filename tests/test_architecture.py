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

    def test_habit_compiler_uses_current_architecture_vocabulary(self) -> None:
        repository = Path(__file__).parents[1]
        excluded = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "build", "dist"}
        retired = (("rule" + "forge").encode(), ("rule" + " forge").encode())
        violations: list[str] = []
        for path in repository.rglob("*"):
            if not path.is_file() or any(part in excluded for part in path.parts):
                continue
            if path.suffix not in _TEXT_SUFFIXES and path.name not in {"LICENSE", "Makefile"}:
                continue
            data = path.read_bytes().lower()
            if any(term in data for term in retired):
                violations.append(str(path.relative_to(repository)))
        self.assertEqual(violations, [])

    def test_incident_demo_has_no_mode_specific_application_branch(self) -> None:
        example = Path(__file__).parents[1] / "examples" / "autonomous_incident_agent.py"
        source = example.read_text(encoding="utf-8")
        self.assertNotIn("DeploymentMode", source)
        self.assertNotIn("MODE ==", source)

    def test_autonomic_core_cannot_execute_dynamic_code_or_import_effect_plane(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        roots = (source_root / "autonomic", source_root / "habit_forge")
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

    def test_continuity_core_and_worker_cannot_reach_the_effect_plane(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        paths = tuple((source_root / "continuity").rglob("*.py")) + (
            source_root / "continuity_worker.py",
        )
        forbidden_modules = {"agent", "authority", "capabilities", "models", "reasoning"}
        forbidden_calls = {"authorize", "deliberate", "dispatch", "execute"}
        violations: list[str] = []
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and node.module.split(".")[0] in forbidden_modules
                    and (
                        node.level >= 2
                        or node.level == 1
                        and path.parent == source_root
                        or node.level == 0
                    )
                ):
                    violations.append(f"{path.relative_to(source_root)} imports {node.module}")
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in forbidden_calls
                ):
                    violations.append(f"{path.relative_to(source_root)} calls {node.func.attr}")
        self.assertEqual(violations, [])

    def test_memory_core_is_a_provider_free_projection_not_an_effect_plane(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        memory_root = source_root / "memory"
        forbidden_modules = {
            "adapters",
            "agent",
            "authority",
            "capabilities",
            "delivery",
            "kernel",
            "memory_worker",
            "models",
            "reasoning",
            "scheduler",
            "store",
            "system",
            "telemetry",
            "tracing",
        }
        forbidden_calls = {"compile", "eval", "exec"}
        violations: list[str] = []
        for path in memory_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and (
                    isinstance(node.func, ast.Name)
                    and node.func.id in forbidden_calls
                    or isinstance(node.func, ast.Attribute)
                    and node.func.attr in forbidden_calls
                    and not (
                        node.func.attr == "compile"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "re"
                    )
                ):
                    name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
                    violations.append(f"{path.relative_to(source_root)} calls {name}")
                if isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    if node.level >= 2 and root in forbidden_modules:
                        violations.append(
                            f"{path.relative_to(source_root)} imports effect plane {node.module}"
                        )
                    if (
                        node.level >= 2
                        and node.module == "events"
                        and any(alias.name == "AsyncEventBus" for alias in node.names)
                    ):
                        violations.append(f"{path.relative_to(source_root)} imports the event bus")
                    if "adapters" in node.module.split("."):
                        violations.append(f"{path.relative_to(source_root)} imports {node.module}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        parts = alias.name.split(".")
                        if "adapters" in parts or (
                            len(parts) >= 2
                            and parts[0] == "noema"
                            and parts[1] in forbidden_modules
                        ):
                            violations.append(
                                f"{path.relative_to(source_root)} imports {alias.name}"
                            )
        self.assertEqual(violations, [])

    def test_work_control_plane_cannot_plan_with_agents_or_execute_effects(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        work_root = source_root / "work"
        forbidden_modules = {
            "adapters",
            "agent",
            "capabilities",
            "delivery",
            "models",
            "reasoning",
            "scheduler",
            "system",
        }
        forbidden_calls = {
            "authorize",
            "deliberate",
            "dispatch",
            "execute",
            "invoke",
        }
        violations: list[str] = []
        for path in work_root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for deferred_name in (
                "LLMPlanSynthesizer",
                "RDDLPlanner",
                "MDPPlanner",
                "OversightAllocator",
                "HabitForge",
                "SkillForge",
                "WorkflowDSL",
            ):
                if deferred_name in source:
                    violations.append(
                        f"{path.relative_to(source_root)} implements deferred {deferred_name}"
                    )
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    if node.level >= 2 and root in forbidden_modules:
                        violations.append(
                            f"{path.relative_to(source_root)} imports {node.module}"
                        )
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        parts = alias.name.split(".")
                        if (
                            len(parts) >= 2
                            and parts[0] == "noema"
                            and parts[1] in forbidden_modules
                        ):
                            violations.append(
                                f"{path.relative_to(source_root)} imports {alias.name}"
                            )
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in {
                        "compile",
                        "eval",
                        "exec",
                    }:
                        violations.append(
                            f"{path.relative_to(source_root)} calls {node.func.id}"
                        )
                    if (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr in forbidden_calls
                    ):
                        violations.append(
                            f"{path.relative_to(source_root)} calls {node.func.attr}"
                        )
        planning_source = (work_root / "planning.py").read_text(encoding="utf-8")
        for forbidden_name in ("AgentPresence", "CompetenceEstimate", "WorkerMatcher"):
            if forbidden_name in planning_source:
                violations.append(f"work/planning.py references {forbidden_name}")
        self.assertEqual(violations, [])

    def test_endogenous_core_is_shadow_only_and_cannot_own_work_or_effects(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        endogenous_root = source_root / "endogenous"
        forbidden_modules = {
            "adapters",
            "agent",
            "authority",
            "capabilities",
            "delivery",
            "endogenous_worker",
            "kernel",
            "models",
            "reasoning",
            "scheduler",
            "store",
            "system",
            "work",
        }
        forbidden_calls = {"authorize", "deliberate", "dispatch", "execute", "invoke"}
        deferred_names = {
            "ReflectionManager",
            "CognitionEngine",
            "LLMReflection",
            "LearnedAllocator",
            "MDPAllocator",
            "HabitForge",
            "SkillForge",
            "WorkflowDSL",
        }
        violations: list[str] = []
        for path in endogenous_root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for name in deferred_names:
                if name in source:
                    violations.append(f"{path.relative_to(source_root)} implements deferred {name}")
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    if node.level >= 2 and root in forbidden_modules:
                        violations.append(f"{path.relative_to(source_root)} imports {node.module}")
                    if node.module == "intent.coordination":
                        violations.append(
                            f"{path.relative_to(source_root)} imports strategic mutation"
                        )
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        parts = alias.name.split(".")
                        if (
                            len(parts) >= 2
                            and parts[0] == "noema"
                            and parts[1] in forbidden_modules
                        ):
                            violations.append(
                                f"{path.relative_to(source_root)} imports {alias.name}"
                            )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in forbidden_calls
                ):
                    violations.append(f"{path.relative_to(source_root)} calls {node.func.attr}")
        self.assertEqual(violations, [])

    def test_endogenous_worker_cannot_reach_models_work_dispatch_or_effects(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        path = source_root / "endogenous_worker.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_modules = {
            "adapters",
            "agent",
            "authority",
            "capabilities",
            "models",
            "reasoning",
            "scheduler",
            "work",
        }
        forbidden_calls = {"authorize", "deliberate", "dispatch", "execute", "invoke"}
        violations: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if node.level >= 1 and root in forbidden_modules:
                    violations.append(f"imports {node.module}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in forbidden_calls
            ):
                violations.append(f"calls {node.func.attr}")
        self.assertEqual(violations, [])

    def test_reconsideration_core_is_history_only_and_cannot_mutate_agency(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        reconsideration_root = source_root / "reconsideration"
        forbidden_modules = {
            "adapters",
            "agent",
            "authority",
            "capabilities",
            "delivery",
            "intent",
            "kernel",
            "models",
            "reasoning",
            "scheduler",
            "store",
            "system",
            "work",
        }
        forbidden_calls = {
            "authorize",
            "deliberate",
            "dispatch",
            "execute",
            "invoke",
            "record_commitment",
            "record_goal_revision",
        }
        forbidden_names = {"ActionIntent", "Capability", "Commitment", "Goal", "WorkOrder"}
        violations: list[str] = []
        for path in reconsideration_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    if node.level >= 2 and root in forbidden_modules:
                        violations.append(
                            f"{path.relative_to(source_root)} imports {node.module}"
                        )
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        parts = alias.name.split(".")
                        if (
                            len(parts) >= 2
                            and parts[0] == "noema"
                            and parts[1] in forbidden_modules
                        ):
                            violations.append(
                                f"{path.relative_to(source_root)} imports {alias.name}"
                            )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in forbidden_calls
                ):
                    violations.append(
                        f"{path.relative_to(source_root)} calls {node.func.attr}"
                    )
                if isinstance(node, ast.Name) and node.id in forbidden_names:
                    violations.append(
                        f"{path.relative_to(source_root)} references {node.id}"
                    )
        self.assertEqual(violations, [])

    def test_reconsideration_worker_cannot_create_goals_work_actions_or_effects(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        paths = (
            source_root / "reconsideration_worker.py",
            source_root / "reconsideration_discovery_worker.py",
        )
        forbidden_modules = {
            "adapters",
            "agent",
            "authority",
            "capabilities",
            "intent",
            "models",
            "reasoning",
            "scheduler",
            "work",
        }
        forbidden_calls = {
            "authorize",
            "deliberate",
            "dispatch",
            "execute",
            "invoke",
            "record_commitment",
            "record_goal_revision",
        }
        forbidden_names = {"ActionIntent", "Capability", "Commitment", "Goal", "WorkOrder"}
        violations: list[str] = []
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    if node.level >= 1 and root in forbidden_modules:
                        violations.append(f"{path.name} imports {node.module}")
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in forbidden_calls
                ):
                    violations.append(f"{path.name} calls {node.func.attr}")
                if isinstance(node, ast.Name) and node.id in forbidden_names:
                    violations.append(f"{path.name} references {node.id}")
        self.assertEqual(violations, [])

    def test_information_governance_core_is_not_authority_memory_or_effect_plane(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        information_root = source_root / "information"
        core_paths = tuple(
            information_root / name for name in ("models.py", "policy.py", "projection.py")
        )
        forbidden_modules = {
            "adapters",
            "agent",
            "authority",
            "capabilities",
            "delivery",
            "intent",
            "kernel",
            "memory",
            "models",
            "reasoning",
            "scheduler",
            "store",
            "system",
            "telemetry",
            "tracing",
            "work",
        }
        forbidden_calls = {
            "authorize",
            "deliberate",
            "dispatch",
            "execute",
            "invoke",
        }
        forbidden_names = {
            "HabitForge",
            "PermissionManager",
            "SecurityContext",
            "SkillForge",
        }
        violations: list[str] = []
        for path in core_paths:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for name in forbidden_names:
                if name in source:
                    violations.append(f"{path.relative_to(source_root)} contains forbidden {name}")
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    if node.level >= 2 and root in forbidden_modules:
                        violations.append(f"{path.relative_to(source_root)} imports {node.module}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        parts = alias.name.split(".")
                        if (
                            len(parts) >= 2
                            and parts[0] == "noema"
                            and parts[1] in forbidden_modules
                        ):
                            violations.append(
                                f"{path.relative_to(source_root)} imports {alias.name}"
                            )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in forbidden_calls
                ):
                    violations.append(f"{path.relative_to(source_root)} calls {node.func.attr}")
        self.assertEqual(violations, [])

    def test_deliberative_attention_is_observation_not_agency_or_learning(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "noema"
        attention_root = source_root / "deliberative_attention"
        forbidden_modules = {"adapters", "authority", "capabilities", "models", "work"}
        forbidden_names = {
            "ActionIntent",
            "Capability",
            "Commitment",
            "Goal",
            "HabitCandidate",
            "HabitEpisode",
            "ModelProvider",
            "RuleRegistry",
            "WorkOrder",
        }
        forbidden_calls = {
            "authorize",
            "dispatch",
            "execute",
            "invoke",
            "mine",
            "register_rule",
        }
        violations: list[str] = []
        for path in attention_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    if node.level >= 2 and root in forbidden_modules:
                        violations.append(f"{path.relative_to(source_root)} imports {node.module}")
                    if "adapters" in node.module.split("."):
                        violations.append(f"{path.relative_to(source_root)} imports adapters")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        parts = alias.name.split(".")
                        if "adapters" in parts or (
                            len(parts) >= 2
                            and parts[0] == "noema"
                            and parts[1] in forbidden_modules
                        ):
                            violations.append(
                                f"{path.relative_to(source_root)} imports {alias.name}"
                            )
                if isinstance(node, ast.Name) and node.id in forbidden_names:
                    violations.append(
                        f"{path.relative_to(source_root)} references {node.id}"
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in forbidden_calls
                ):
                    violations.append(
                        f"{path.relative_to(source_root)} calls {node.func.attr}"
                    )
        self.assertEqual(violations, [])
