"""Policy-bounded autonomy and evidence-weighted delegation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import IntEnum
from math import sqrt
from typing import TYPE_CHECKING
from uuid import uuid4

from .types import JSONObject, JSONValue

if TYPE_CHECKING:
    from .capabilities import CapabilitySpec
    from .situation import SituationSnapshot


class AuthorityLevel(IntEnum):
    OBSERVE = 0
    PROPOSE = 1
    ACT_REVERSIBLE = 2
    ACT_IRREVERSIBLE = 3
    ADMINISTER = 4


class RiskLevel(IntEnum):
    NEGLIGIBLE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True, slots=True)
class ActionIntent:
    capability: str
    arguments: Mapping[str, JSONValue] = field(default_factory=dict)
    rationale: str = ""
    expected_value: float = 0.0
    information_value: float = 0.0
    risk_reduction: float = 0.0
    attention_cost: float = 1.0
    switching_cost: float = 0.0
    branch_cost: float = 0.0
    risk: RiskLevel = RiskLevel.LOW
    reversible: bool = True
    required_authority: AuthorityLevel = AuthorityLevel.ACT_REVERSIBLE
    confidence: float = 0.5
    alternatives: tuple[str, ...] = ()
    falsifiers: tuple[str, ...] = ()
    idempotency_key: str | None = None
    intent_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.capability:
            raise ValueError("action intent requires a capability")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.attention_cost < 0:
            raise ValueError("attention_cost cannot be negative")
        object.__setattr__(self, "arguments", dict(self.arguments))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> JSONObject:
        return {
            "intent_id": self.intent_id,
            "capability": self.capability,
            "arguments": dict(self.arguments),
            "rationale": self.rationale,
            "expected_value": self.expected_value,
            "information_value": self.information_value,
            "risk_reduction": self.risk_reduction,
            "attention_cost": self.attention_cost,
            "switching_cost": self.switching_cost,
            "branch_cost": self.branch_cost,
            "risk": int(self.risk),
            "reversible": self.reversible,
            "required_authority": int(self.required_authority),
            "confidence": self.confidence,
            "alternatives": list(self.alternatives),
            "falsifiers": list(self.falsifiers),
            "idempotency_key": self.idempotency_key,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class AutonomyProfile:
    authority_ceiling: AuthorityLevel = AuthorityLevel.ACT_REVERSIBLE
    max_risk: RiskLevel = RiskLevel.MEDIUM
    allow_irreversible: bool = False
    min_confidence: float = 0.5
    max_attention_per_action: float = 20.0
    require_falsifiers_above_risk: RiskLevel = RiskLevel.HIGH

    @classmethod
    def sovereign(cls) -> "AutonomyProfile":
        """Run without human approval while retaining explicit policy checks."""

        return cls(
            authority_ceiling=AuthorityLevel.ADMINISTER,
            max_risk=RiskLevel.CRITICAL,
            allow_irreversible=True,
            min_confidence=0.0,
            max_attention_per_action=float("inf"),
            require_falsifiers_above_risk=RiskLevel.CRITICAL,
        )


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    effective_authority: AuthorityLevel
    effective_risk: RiskLevel


PolicyRule = Callable[
    [ActionIntent, "CapabilitySpec", "SituationSnapshot"],
    str | None,
]


class PolicyEngine:
    """Authorize actions against an autonomy profile and custom deny rules."""

    def __init__(
        self,
        profile: AutonomyProfile | None = None,
        *,
        rules: tuple[PolicyRule, ...] = (),
    ) -> None:
        self.profile = profile or AutonomyProfile()
        self.rules = list(rules)

    def add_rule(self, rule: PolicyRule) -> None:
        self.rules.append(rule)

    def authorize(
        self,
        intent: ActionIntent,
        capability: "CapabilitySpec",
        situation: "SituationSnapshot",
    ) -> AuthorizationDecision:
        effective_authority = max(intent.required_authority, capability.required_authority)
        effective_risk = max(intent.risk, capability.risk_level)
        reversible = intent.reversible and capability.reversible

        if effective_authority > self.profile.authority_ceiling:
            return AuthorizationDecision(
                False,
                "required authority exceeds agent authority ceiling",
                effective_authority,
                effective_risk,
            )
        if effective_risk > self.profile.max_risk:
            return AuthorizationDecision(
                False,
                "effective risk exceeds agent risk ceiling",
                effective_authority,
                effective_risk,
            )
        if not reversible and not self.profile.allow_irreversible:
            return AuthorizationDecision(
                False,
                "irreversible actions are disabled by the autonomy profile",
                effective_authority,
                effective_risk,
            )
        if intent.confidence < self.profile.min_confidence:
            return AuthorizationDecision(
                False,
                "intent confidence is below the autonomy threshold",
                effective_authority,
                effective_risk,
            )
        if intent.attention_cost > self.profile.max_attention_per_action:
            return AuthorizationDecision(
                False,
                "action exceeds the per-action attention budget",
                effective_authority,
                effective_risk,
            )
        if (
            effective_risk >= self.profile.require_falsifiers_above_risk
            and not intent.falsifiers
        ):
            return AuthorizationDecision(
                False,
                "high-risk actions require explicit falsifiers",
                effective_authority,
                effective_risk,
            )
        for rule in self.rules:
            denial = rule(intent, capability, situation)
            if denial:
                return AuthorizationDecision(
                    False,
                    denial,
                    effective_authority,
                    effective_risk,
                )
        return AuthorizationDecision(
            True,
            "authorized",
            effective_authority,
            effective_risk,
        )


@dataclass(frozen=True, slots=True)
class TrustEstimate:
    """Beta-distribution estimate of actor reliability in a domain."""

    successes: float = 1.0
    failures: float = 1.0

    @property
    def mean(self) -> float:
        return self.successes / (self.successes + self.failures)

    @property
    def evidence(self) -> float:
        return self.successes + self.failures - 2.0

    @property
    def variance(self) -> float:
        total = self.successes + self.failures
        return (self.successes * self.failures) / (total * total * (total + 1.0))

    @property
    def conservative_bound(self) -> float:
        """Simple uncertainty-penalized trust score, bounded to [0, 1]."""

        return max(0.0, self.mean - 2.0 * sqrt(self.variance))

    def updated(self, *, success: bool, weight: float = 1.0) -> "TrustEstimate":
        if weight <= 0:
            raise ValueError("weight must be positive")
        if success:
            return TrustEstimate(self.successes + weight, self.failures)
        return TrustEstimate(self.successes, self.failures + weight)


class TrustLedger:
    """Evidence-weighted trust without converting reputation into truth."""

    def __init__(self) -> None:
        self._estimates: dict[tuple[str, str], TrustEstimate] = {}

    def estimate(self, actor: str, domain: str = "*") -> TrustEstimate:
        return self._estimates.get((actor, domain), TrustEstimate())

    def record(
        self,
        actor: str,
        *,
        domain: str = "*",
        success: bool,
        weight: float = 1.0,
    ) -> TrustEstimate:
        updated = self.estimate(actor, domain).updated(success=success, weight=weight)
        self._estimates[(actor, domain)] = updated
        return updated

    def recommended_authority(
        self,
        actor: str,
        *,
        domain: str = "*",
        reversible: bool,
        risk: RiskLevel,
    ) -> AuthorityLevel:
        score = self.estimate(actor, domain).conservative_bound
        if score < 0.35:
            return AuthorityLevel.OBSERVE
        if score < 0.55:
            return AuthorityLevel.PROPOSE
        if reversible and score >= 0.55 and risk <= RiskLevel.MEDIUM:
            return AuthorityLevel.ACT_REVERSIBLE
        if score >= 0.85 and risk <= RiskLevel.HIGH:
            return AuthorityLevel.ACT_IRREVERSIBLE
        return AuthorityLevel.PROPOSE
