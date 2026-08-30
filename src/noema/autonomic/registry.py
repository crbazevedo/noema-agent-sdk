"""Rebuildable rule-registry projection and immutable ruleset pinning."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ..events import Event
from ..types import JSONObject
from .models import AutonomicRule, RulesetSnapshot, canonical_bytes


@dataclass(frozen=True, slots=True)
class _RegisteredRule:
    rule: AutonomicRule
    sequence: int


class RuleRegistry:
    """In-memory projection of immutable rule-version events.

    The registry is deliberately not a persistence boundary. Rebuild it from
    canonical events after restart, and persist every registration before it is
    applied here.
    """

    def __init__(self) -> None:
        self._rules: dict[str, _RegisteredRule] = {}

    @property
    def rules(self) -> tuple[AutonomicRule, ...]:
        return tuple(self._rules[ref].rule for ref in sorted(self._rules))

    def get(self, ref: str) -> AutonomicRule:
        try:
            return self._rules[ref].rule
        except KeyError as exc:
            raise KeyError(f"unknown autonomic rule version: {ref}") from exc

    def apply(self, event: Event) -> bool:
        """Apply one canonical registry event to this projection."""

        if event.type != "rule.version_registered":
            return False
        rule_data = event.payload.get("rule")
        if not isinstance(rule_data, dict):
            raise ValueError("rule registration event requires a rule object")
        if event.sequence is None or event.sequence <= 0:
            raise ValueError("rule registration must be applied from a canonical sequenced event")
        self._register_projection(AutonomicRule.from_dict(rule_data), event.sequence)
        return True

    def rebuild(self, events: Iterable[Event]) -> None:
        self._rules.clear()
        for event in events:
            self.apply(event)

    def _register_projection(self, rule: AutonomicRule, sequence: int) -> None:
        """Update the projection after its registration event is durable."""

        current = self._rules.get(rule.ref)
        if current is not None:
            if current.rule != rule or current.sequence != sequence:
                raise ValueError(
                    f"immutable rule version already exists at another event: {rule.ref}"
                )
            return
        self._rules[rule.ref] = _RegisteredRule(rule=rule, sequence=sequence)

    def snapshot(
        self,
        *,
        through_sequence: int,
        refs: Sequence[str] | None = None,
    ) -> RulesetSnapshot:
        if through_sequence < 0:
            raise ValueError("ruleset sequence cursor cannot be negative")
        eligible = tuple(
            entry.rule for entry in self._rules.values() if entry.sequence <= through_sequence
        )
        if refs is None:
            latest: dict[str, AutonomicRule] = {}
            for rule in eligible:
                current = latest.get(rule.rule_id)
                if current is None or rule.version > current.version:
                    latest[rule.rule_id] = rule
            selected = tuple(sorted(latest.values(), key=lambda rule: rule.ref))
        else:
            eligible_by_ref = {rule.ref: rule for rule in eligible}
            missing = sorted(set(refs) - set(eligible_by_ref))
            if missing:
                raise ValueError(
                    "rule versions did not exist at the requested cursor: " + ", ".join(missing)
                )
            selected = tuple(eligible_by_ref[ref] for ref in sorted(set(refs)))
        payload: JSONObject = {"rules": [rule.to_dict() for rule in selected]}
        digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        return RulesetSnapshot(
            snapshot_id=f"ruleset:{digest[:32]}",
            digest=digest,
            rules=selected,
        )
