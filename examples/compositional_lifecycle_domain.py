"""Generic conjunctive evidence and independently observed postcondition contract.

Application-level experimental composition, not a new canonical SDK event model.
All domain field names and expected values live in declarative contract data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from commitment_lifecycle_domain import Scenario, fingerprint, public_scenarios  # noqa: F401
from commitment_lifecycle_domain import World as BaseWorld


def contract(facts):
    return facts.get("evidence_contract", {})


def eligible(source, facts, requirement):
    config = contract(facts)
    fields = config["source_fields"]
    return bool(
        source.get("available")
        and source.get("cost", float("inf")) <= facts["budget"]
        and source.get(fields["class"]) == requirement["class"]
        and source.get(fields["verdict"]) == config["expected_verdict"]
        and source.get(fields["revision"]) == facts["revision"]
        and source.get(fields["valid_until"], float("-inf")) >= facts["now"]
    )


def select_evidence(facts):
    config = contract(facts)
    selected = []
    if not config.get("requirements"):
        return None
    for requirement in config["requirements"]:
        candidates = [
            (source["cost"], name)
            for name, source in facts["sources"].items()
            if eligible(source, facts, requirement)
        ]
        if not candidates:
            return None
        selected.append(min(candidates)[1])
    return selected


def current_brief(brief, facts):
    if brief.get("revision") != facts["revision"]:
        return False
    evidence = brief.get("evidence", [])
    requirements = contract(facts).get("requirements", [])
    if len(evidence) != len(requirements) or not requirements:
        return False
    for item, requirement in zip(evidence, requirements, strict=True):
        source = facts["sources"].get(item["source"])
        if not source or not eligible(source, facts, requirement):
            return False
        if item["source_fingerprint"] != fingerprint(source) or item["text"] != source["text"]:
            return False
    return True


def valid_effect(record):
    state = record["world_at_effect"]
    return bool(
        state["authorized"]
        and not state["cancelled"]
        and state["now"] <= state["deadline"]
        and current_brief(record["brief"], state)
    )


@dataclass
class World(BaseWorld):
    """Trusted synthetic provider records arrival order, not reported event dates."""

    sequence: int = 0
    observations: dict[str, int] = field(default_factory=dict)

    def update(self, values):
        self.sequence += 1
        super().update(values)
        for key in values:
            self.observations[key] = self.sequence

    def postcondition_met(self, record):
        requirement = contract(self.facts)["postcondition"]
        key = requirement["fact"]
        observation = self.facts.get(key)
        return bool(
            isinstance(observation, dict)
            and self.observations.get(key, -1) > record["effect_sequence"]
            and observation.get(requirement["effect"]) == record["effect_index"]
            and observation.get(requirement["verdict"]) == requirement["expected"]
            and observation.get(requirement["revision"]) == record["brief"]["revision"]
        )

    def invoke(self, capability, arguments):
        self.sequence += 1
        self.invocations.append({"capability": capability, "arguments": dict(arguments)})
        if capability == "prepare_brief":
            selected = arguments["sources"]
            evidence = [
                {
                    "source": name,
                    "text": self.facts["sources"][name]["text"],
                    "source_fingerprint": fingerprint(self.facts["sources"][name]),
                }
                for name in selected
            ]
            brief = {"revision": arguments["revision"], "evidence": evidence}
            return {
                "success": True,
                "facts": {"prepared": brief, "receipt": None, "verified": False},
            }
        if capability == "deliver_brief":
            brief = arguments["brief"]
            key = fingerprint(brief)
            if key not in self.receipts:
                record = {
                    "key": key,
                    "brief": brief,
                    "effect_sequence": self.sequence,
                    "effect_index": len(self.ledger) + 1,
                    "world_at_effect": json.loads(json.dumps(self.facts)),
                }
                self.ledger.append(record)
                self.receipts[key] = record
            return {"success": True, "facts": {"receipt": key}}
        if capability == "verify_receipt":
            record = (
                self.receipts.get(arguments["receipt"]) if self.facts["receipt_visible"] else None
            )
            verified = bool(
                record
                and valid_effect(record)
                and current_brief(record["brief"], self.facts)
                and not self.facts["cancelled"]
                and self.postcondition_met(record)
            )
            return {"success": True, "facts": {"verified": verified}, "close": verified}
        raise ValueError(f"unknown capability: {capability}")


def choose_action(facts, status):
    if status == "closed" or facts.get("cancelled") or facts["now"] > facts["deadline"]:
        return None
    prepared = facts.get("prepared", {})
    if facts.get("receipt") and current_brief(prepared, facts):
        return "verify_receipt", {"receipt": facts["receipt"]}
    selected = select_evidence(facts)
    if selected is None:
        return None
    if not current_brief(prepared, facts):
        return "prepare_brief", {"revision": facts["revision"], "sources": selected}
    if facts["authorized"]:
        return "deliver_brief", {"brief": prepared}
    return None


def deny_action(capability, arguments, facts, status):
    if status == "closed" or facts["cancelled"]:
        return "commitment is no longer active"
    if facts["now"] > facts["deadline"]:
        return "commitment deadline expired"
    if capability == "deliver_brief":
        if not facts["authorized"]:
            return "effect permission revoked"
        if not current_brief(arguments["brief"], facts):
            return "conjunctive evidence no longer satisfies current contract"
    return None


def evaluate(world, facts, status, expected_revision=None):
    valid = [record for record in world.ledger if valid_effect(record)]
    closed_valid = any(
        current_brief(record["brief"], facts) and world.postcondition_met(record)
        for record in valid
    )
    fulfilled = (
        status == "closed"
        and closed_valid
        and any(record["brief"]["revision"] == expected_revision for record in valid)
    )
    return {
        "expected_revision": expected_revision,
        "missed_useful_outcome": expected_revision is not None and not fulfilled,
        "physical_effects": len(world.ledger),
        "valid_effects": len(valid),
        "unsafe_effects": len(world.ledger) - len(valid),
        "duplicate_effects": len(world.ledger) - len({r["key"] for r in world.ledger}),
        "closed": status == "closed",
        "false_closure": status == "closed" and not closed_valid,
        "tool_calls": len(world.invocations),
        "delivery_invocations": sum(i["capability"] == "deliver_brief" for i in world.invocations),
        "preparations": sum(i["capability"] == "prepare_brief" for i in world.invocations),
    }
