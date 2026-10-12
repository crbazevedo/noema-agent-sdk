"""Counted CSV capability adapter over the unchanged V2 controller and policy.

Only synthetic source_csv data is accepted. Effects live in an isolated provider
root; read-back verification measures actual files rather than trusting receipts.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from compositional_lifecycle_domain import (  # noqa: F401
    Scenario,
    choose_action,
    deny_action,
    fingerprint,
    public_scenarios,
)
from compositional_lifecycle_domain import World as EvidenceWorld
from compositional_lifecycle_domain import evaluate as evidence_evaluate


def inspect_csv(data, expected):
    digest = hashlib.sha256(data).hexdigest()
    try:
        rows = list(csv.reader(io.StringIO(data.decode("utf-8"), newline=""), strict=True))
    except (UnicodeDecodeError, csv.Error) as error:
        return {
            "passed": False,
            "reason": f"invalid CSV: {error}",
            "sha256": digest,
            "rows": None,
            "header": None,
            "bytes": len(data),
        }
    header = rows[0] if rows else []
    count = max(len(rows) - 1, 0)
    valid = (
        bool(header)
        and header == expected["columns"]
        and count == expected["row_count"]
        and digest == expected["sha256"]
        and all(len(row) == len(header) for row in rows[1:])
    )
    return {
        "passed": valid,
        "reason": "verified" if valid else "CSV integrity mismatch",
        "sha256": digest,
        "rows": count,
        "header": header,
        "bytes": len(data),
    }


@dataclass
class World(EvidenceWorld):
    artifact_root: str = field(default_factory=lambda: tempfile.mkdtemp(prefix="noema-import-"))
    io_metrics: dict[str, int] = field(
        default_factory=lambda: {
            "source_read_calls": 0,
            "source_bytes_read": 0,
            "write_calls": 0,
            "bytes_written": 0,
            "readback_calls": 0,
            "readback_bytes_read": 0,
            "external_fault_writes": 0,
        }
    )

    def __post_init__(self):
        # JSON round trips do not preserve shared object identity.
        self.receipts = {record["key"]: record for record in self.ledger}

    def update(self, values):
        super().update(values)
        fault = values.get("artifact_fault")
        if fault:
            record = next(
                (r for r in self.ledger if r["effect_index"] == fault["effect_index"]), None
            )
            if record is None:
                raise ValueError("artifact fault references a nonexistent effect")
            path = Path(record["artifact_path"])
            if fault["kind"] == "delete":
                path.unlink(missing_ok=True)
            elif fault["kind"] == "replace":
                path.write_bytes(fault["source_csv"].encode("utf-8"))
            else:
                raise ValueError("unknown fixture-only artifact fault")
            self.io_metrics["external_fault_writes"] += 1

    def reject(self, capability, arguments, reason, *, status="invalid"):
        self.sequence += 1
        self.invocations.append(
            {
                "capability": capability,
                "arguments": dict(arguments),
                "admission_status": status,
                "reason": reason,
            }
        )
        return {"success": False, "facts": {}, "error": reason, "admission_status": status}

    def invoke(self, capability, arguments):
        expected = self.facts.get("artifact_contract", {})
        if expected.get("operation") != "import_csv":
            return self.reject(
                capability,
                arguments,
                "unsupported operation: only single-artifact CSV import is supported",
                status="unsupported",
            )
        if capability in {"prepare_brief", "deliver_brief"}:
            data = self.facts.get("source_csv", "").encode("utf-8")
            self.io_metrics["source_read_calls"] += 1
            self.io_metrics["source_bytes_read"] += len(data)
            try:
                measurement = inspect_csv(data, expected)
            except KeyError as error:
                return self.reject(capability, arguments, f"incomplete artifact contract: {error}")
            if not measurement["passed"]:
                return self.reject(capability, arguments, measurement["reason"])
            binding = fingerprint({"contract": expected, "source_sha256": measurement["sha256"]})
            selected = (
                arguments["sources"]
                if capability == "prepare_brief"
                else [item["source"] for item in arguments["brief"]["evidence"]]
            )
            source_fields = self.facts["evidence_contract"]["source_fields"]
            content_binding = expected.get("content_binding", {})
            bound = any(
                self.facts["sources"][name].get(source_fields["class"])
                == content_binding.get("source_class")
                and self.facts["sources"][name].get(content_binding.get("digest_field", ""))
                == measurement["sha256"]
                for name in selected
            )
            if not bound:
                return self.reject(capability, arguments, "source-version evidence digest mismatch")
            if capability == "prepare_brief":
                result = super().invoke(capability, arguments)
                result["facts"]["prepared"]["artifact_binding"] = binding
                return result
            if arguments["brief"].get("artifact_binding") != binding:
                return self.reject(capability, arguments, "prepared artifact binding is stale")
            key = fingerprint(arguments["brief"])
            if key not in self.receipts:
                effect_index = len(self.ledger) + 1
                path = Path(self.artifact_root) / f"import-{effect_index}.csv"
                staged = path.with_suffix(".partial")
                try:
                    staged.write_bytes(data)
                    os.replace(staged, path)
                except OSError as error:
                    # Keep any partial file for diagnosis instead of claiming success.
                    return self.reject(capability, arguments, f"artifact write failed: {error}")
                self.io_metrics["write_calls"] += 1
                self.io_metrics["bytes_written"] += len(data)
                result = super().invoke(capability, arguments)
                self.receipts[key].update(
                    {"artifact_path": str(path), "import_measurement": measurement, "readbacks": []}
                )
                return result
            return super().invoke(capability, arguments)
        if capability == "verify_receipt":
            record = self.receipts.get(arguments["receipt"])
            if record is None:
                return self.reject(capability, arguments, "unknown effect receipt")
            self.io_metrics["readback_calls"] += 1
            try:
                data = Path(record["artifact_path"]).read_bytes()
                self.io_metrics["readback_bytes_read"] += len(data)
                measurement = inspect_csv(data, record["world_at_effect"]["artifact_contract"])
            except (OSError, KeyError) as error:
                measurement = {
                    "passed": False,
                    "reason": f"read-back failed: {error}",
                    "sha256": None,
                    "rows": None,
                    "header": None,
                    "bytes": 0,
                }
            current_source = self.facts.get("source_csv", "").encode("utf-8")
            self.io_metrics["source_read_calls"] += 1
            self.io_metrics["source_bytes_read"] += len(current_source)
            current_binding = fingerprint(
                {"contract": expected, "source_sha256": hashlib.sha256(current_source).hexdigest()}
            )
            if record["brief"].get("artifact_binding") != current_binding:
                measurement["passed"] = False
                measurement["reason"] = "current artifact contract or source differs from effect"
            measurement["effect_index"] = record["effect_index"]
            record["readbacks"].append(measurement)
            postcondition = self.facts["evidence_contract"]["postcondition"]
            observation = {
                postcondition["verdict"]: measurement["passed"],
                postcondition["revision"]: record["brief"]["revision"],
                postcondition["effect"]: record["effect_index"],
                "measurement": dict(measurement),
                "provider_observation_sequence": self.sequence + 1,
                "artifact_binding": record["brief"].get("artifact_binding"),
            }
            self.update({postcondition["fact"]: observation})
            result = super().invoke(capability, arguments)
            result["facts"]["artifact_readback"] = measurement
            result["facts"][postcondition["fact"]] = observation
            return result
        return self.reject(capability, arguments, "unsupported capability", status="unsupported")


def evaluate(world, facts, status, expected_revision=None):
    result = evidence_evaluate(world, facts, status, expected_revision)
    result.update(world.io_metrics)
    result["unsupported_invocations"] = sum(
        i.get("admission_status") == "unsupported" for i in world.invocations
    )
    result["artifact_paths"] = [record["artifact_path"] for record in world.ledger]
    result["artifact_root"] = world.artifact_root
    result["artifact_inventory"] = [
        {
            "relative_path": str(path.relative_to(world.artifact_root)),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(Path(world.artifact_root).rglob("*"))
        if path.is_file()
    ]
    return result
