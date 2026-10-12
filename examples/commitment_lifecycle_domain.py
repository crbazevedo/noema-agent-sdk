"""Shared synthetic world, controller and truth oracle; no SDK/framework imports.

This is an inspectable deterministic application policy, not learned intelligence.
Framework adapters must pass the same observed facts to these functions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Scenario:
    name: str
    commands: tuple[dict[str, Any], ...]
    expected_revision: int | None = 1


@dataclass
class World:
    """Physical provider state survives application restarts, like a remote service."""

    facts: dict[str, Any] = field(
        default_factory=lambda: {
            "revision": 1,
            "authorized": False,
            "cancelled": False,
            "sources": {"primary": {"available": True, "cost": 2, "text": "Evidence A"}},
            "budget": 3,
            "receipt_visible": True,
            "now": 0,
            "deadline": 10,
        }
    )
    ledger: list[dict[str, Any]] = field(default_factory=list)
    receipts: dict[str, dict[str, Any]] = field(default_factory=dict)
    invocations: list[dict[str, Any]] = field(default_factory=list)

    def dump(self, path) -> None:
        from dataclasses import asdict

        path.write_text(json.dumps(asdict(self), sort_keys=True))

    @classmethod
    def load(cls, path):
        return cls(**json.loads(path.read_text()))

    def update(self, values: dict[str, Any]) -> None:
        self.facts.update(values)

    def invoke(self, capability: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.invocations.append({"capability": capability, "arguments": dict(arguments)})
        if capability == "prepare_brief":
            source = self.facts["sources"].get(arguments["source"])
            if not source or not source["available"]:
                return {"success": False, "facts": {}, "error": "source unavailable"}
            brief = {
                "revision": arguments["revision"],
                "source": arguments["source"],
                "text": source["text"],
                "source_fingerprint": fingerprint(source),
            }
            return {
                "success": True,
                "facts": {"prepared": brief, "receipt": None, "verified": False},
            }
        if capability == "deliver_brief":
            brief = arguments["brief"]
            key = fingerprint(brief)
            # The provider deliberately does not implement the application's policy.
            # This lets the independent oracle detect unsafe effects in ablations.
            if key not in self.receipts:
                record = {
                    "key": key,
                    "brief": brief,
                    "world_at_effect": json.loads(json.dumps(self.facts)),
                }
                self.ledger.append(record)
                self.receipts[key] = record
            return {"success": True, "facts": {"receipt": key}}
        if capability == "verify_receipt":
            key = arguments["receipt"]
            record = self.receipts.get(key) if self.facts["receipt_visible"] else None
            verified = bool(
                record
                and valid_effect(record)
                and current_brief(record["brief"], self.facts)
                and not self.facts["cancelled"]
            )
            return {"success": True, "facts": {"verified": verified}, "close": verified}
        raise ValueError(f"unknown capability: {capability}")


def current_brief(brief: dict[str, Any], facts: dict[str, Any]) -> bool:
    source = facts.get("sources", {}).get(brief.get("source"))
    return bool(
        source
        and source["available"]
        and source["cost"] <= facts["budget"]
        and brief.get("revision") == facts["revision"]
        and brief.get("source_fingerprint") == fingerprint(source)
        and brief.get("text") == source["text"]
    )


def choose_action(facts: dict[str, Any], status: str) -> tuple[str, dict[str, Any]] | None:
    """Derive the next useful action from current state, never from a scenario name."""
    if status == "closed" or facts.get("cancelled") or facts["now"] > facts["deadline"]:
        return None
    if facts.get("receipt") and current_brief(facts.get("prepared", {}), facts):
        return "verify_receipt", {"receipt": facts["receipt"]}
    sources = facts.get("sources", {})
    feasible = [
        (source["cost"], name)
        for name, source in sources.items()
        if source["available"] and source["cost"] <= facts.get("budget", 0)
    ]
    if not feasible:
        return None
    _, name = min(feasible)
    prepared = facts.get("prepared", {})
    if (
        prepared.get("revision") != facts.get("revision")
        or prepared.get("source_fingerprint") != fingerprint(sources[name])
        or prepared.get("source") != name
    ):
        return "prepare_brief", {"revision": facts["revision"], "source": name}
    if facts.get("authorized"):
        return "deliver_brief", {"brief": prepared}
    return None


def deny_action(
    capability: str, arguments: dict[str, Any], facts: dict[str, Any], status: str
) -> str | None:
    if status == "closed" or facts.get("cancelled"):
        return "commitment is no longer active"
    if facts["now"] > facts["deadline"]:
        return "commitment deadline expired"
    if capability == "deliver_brief":
        if not facts.get("authorized"):
            return "delivery permission revoked"
        brief = arguments["brief"]
        source = facts.get("sources", {}).get(brief["source"])
        if (
            brief["revision"] != facts.get("revision")
            or not source
            or not source["available"]
            or source["cost"] > facts["budget"]
            or brief["source_fingerprint"] != fingerprint(source)
        ):
            return "prepared evidence is stale"
    return None


def valid_effect(record: dict[str, Any]) -> bool:
    """Evaluate physical truth at the effect, independently from reported success."""
    state, brief = record["world_at_effect"], record["brief"]
    source = state["sources"].get(brief["source"])
    return bool(
        state["authorized"]
        and not state["cancelled"]
        and state["now"] <= state["deadline"]
        and source
        and source["available"]
        and source["cost"] <= state["budget"]
        and brief["revision"] == state["revision"]
        and brief["source_fingerprint"] == fingerprint(source)
        and brief["text"] == source["text"]
    )


def evaluate(
    world: World, facts: dict[str, Any], status: str, expected_revision: int | None = None
) -> dict[str, Any]:
    valid = sum(valid_effect(record) for record in world.ledger)
    current_valid = any(
        valid_effect(record) and current_brief(record["brief"], facts) for record in world.ledger
    )
    delivered = {r["brief"]["revision"] for r in world.ledger if valid_effect(r)}
    return {
        "expected_revision": expected_revision,
        "missed_useful_outcome": expected_revision is not None
        and not (expected_revision in delivered and status == "closed"),
        "delivery_invocations": sum(i["capability"] == "deliver_brief" for i in world.invocations),
        "physical_effects": len(world.ledger),
        "valid_effects": valid,
        "unsafe_effects": len(world.ledger) - valid,
        "duplicate_effects": len(world.ledger) - len({r["key"] for r in world.ledger}),
        "closed": status == "closed",
        "false_closure": status == "closed" and not (current_valid and facts.get("verified")),
        "tool_calls": len(world.invocations),
        "preparations": sum(i["capability"] == "prepare_brief" for i in world.invocations),
    }


def public_scenarios() -> tuple[Scenario, ...]:
    wake = {"op": "wake"}
    return (
        Scenario(
            "replan_after_changed_evidence",
            (
                wake,
                {
                    "op": "update",
                    "facts": {
                        "revision": 2,
                        "sources": {
                            "primary": {
                                "available": True,
                                "cost": 2,
                                "text": "Corrected evidence C",
                            }
                        },
                    },
                },
                wake,
                {"op": "update", "facts": {"authorized": True}},
                wake,
                wake,
                wake,
            ),
            expected_revision=2,
        ),
        Scenario(
            "restart_before_delivery",
            (
                wake,
                {"op": "restart"},
                {"op": "update", "facts": {"authorized": True}},
                wake,
                {"op": "restart"},
                wake,
                wake,
            ),
        ),
        Scenario(
            "revocation_between_plan_and_effect",
            (
                wake,
                {"op": "update", "facts": {"authorized": True}},
                {"op": "wake", "before_effect": {"authorized": False}},
                wake,
                {"op": "update", "facts": {"authorized": True}},
                wake,
                wake,
            ),
        ),
        Scenario(
            "alternative_evidence_opportunity",
            (
                {
                    "op": "update",
                    "facts": {
                        "sources": {
                            "primary": {"available": False, "cost": 2, "text": "Unavailable"},
                            "backup": {"available": True, "cost": 1, "text": "Evidence B"},
                        }
                    },
                },
                wake,
                {"op": "update", "facts": {"authorized": True}},
                wake,
                wake,
            ),
        ),
        Scenario(
            "verification_waits_for_receipt",
            (
                wake,
                {"op": "update", "facts": {"authorized": True, "receipt_visible": False}},
                wake,
                wake,
                {"op": "restart"},
                {"op": "update", "facts": {"receipt_visible": True}},
                wake,
            ),
        ),
        Scenario(
            "cancelled_commitment",
            (
                wake,
                {"op": "update", "facts": {"authorized": True, "cancelled": True}},
                wake,
                {"op": "restart"},
                wake,
            ),
            expected_revision=None,
        ),
        Scenario(
            "deadline_opportunity",
            (
                {"op": "update", "facts": {"now": 7, "deadline": 9}},
                wake,
                {"op": "update", "facts": {"now": 8, "authorized": True}},
                wake,
                {"op": "update", "facts": {"now": 9}},
                wake,
            ),
        ),
    )
