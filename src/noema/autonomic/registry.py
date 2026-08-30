"""Rebuildable rule-registry projection and immutable ruleset pinning."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from datetime import datetime

from ..events import Event
from ..types import JSONObject
from .models import AutonomicRule, RulesetSnapshot, canonical_bytes


class RuleRegistry:
    """In-memory projection of immutable rule-version events.

    The registry is deliberately not a persistence boundary. Rebuild it from
    canonical events after restart, and persist every registration before it is
    applied here.
    """

    def __init__(self) -> None:
        self._rules: dict[str, AutonomicRule] = {}

    @property
    def rules(self) -> tuple[AutonomicRule, ...]:
        return tuple(self._rules[ref] for ref in sorted(self._rules))

    def get(self, ref: str) -> AutonomicRule:
        try:
            return self._rules[ref]
        except KeyError as exc:
            raise KeyError(f"unknown autonomic rule version: {ref}") from exc

    def apply(self, event: Event) -> bool:
        """Apply one canonical registry event to this projection."""

        if event.type != "rule.version_registered":
            return False
        rule_data = event.payload.get("rule")
        if not isinstance(rule_data, dict):
            raise ValueError("rule registration event requires a rule object")
        self._register_projection(AutonomicRule.from_dict(rule_data))
        return True

    def rebuild(self, events: Iterable[Event]) -> None:
        self._rules.clear()
        for event in events:
            self.apply(event)

    def _register_projection(self, rule: AutonomicRule) -> None:
        """Update the projection after its registration event is durable."""

        current = self._rules.get(rule.ref)
        if current is not None and current != rule:
            raise ValueError(
                f"immutable rule version already exists with other content: {rule.ref}"
            )
        self._rules[rule.ref] = rule

    def snapshot(
        self,
        *,
        pinned_at: datetime,
        refs: Sequence[str] | None = None,
        snapshot_id: str | None = None,
    ) -> RulesetSnapshot:
        if pinned_at.tzinfo is None:
            raise ValueError("ruleset pinned_at must be timezone-aware")
        if refs is None:
            latest: dict[str, AutonomicRule] = {}
            for rule in self.rules:
                current = latest.get(rule.rule_id)
                if current is None or rule.version > current.version:
                    latest[rule.rule_id] = rule
            selected = tuple(sorted(latest.values(), key=lambda rule: rule.ref))
        else:
            selected = tuple(self.get(ref) for ref in sorted(set(refs)))
        payload: JSONObject = {"rules": [rule.to_dict() for rule in selected]}
        digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        return RulesetSnapshot(
            snapshot_id=snapshot_id or f"ruleset:{digest[:32]}",
            digest=digest,
            pinned_at=pinned_at,
            rules=selected,
        )
