from __future__ import annotations

import unittest

from noema import (
    ActionIntent,
    AuthorityLevel,
    AutonomyProfile,
    CapabilitySpec,
    NoemaKernel,
    PolicyEngine,
    RiskLevel,
    TrustLedger,
)


class AuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_policy_blocks_irreversible_action(self) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        snapshot = await kernel.snapshot()
        policy = PolicyEngine()
        intent = ActionIntent(
            "delete",
            expected_value=10,
            attention_cost=1,
            reversible=False,
            risk=RiskLevel.HIGH,
            required_authority=AuthorityLevel.ACT_IRREVERSIBLE,
        )
        spec = CapabilitySpec(
            "delete",
            "delete data",
            reversible=False,
            risk_level=RiskLevel.HIGH,
            required_authority=AuthorityLevel.ACT_IRREVERSIBLE,
        )
        decision = policy.authorize(intent, spec, snapshot)
        self.assertFalse(decision.allowed)
        await kernel.stop()

    async def test_sovereign_profile_allows_bounded_irreversible_action(self) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        snapshot = await kernel.snapshot()
        policy = PolicyEngine(AutonomyProfile.sovereign())
        intent = ActionIntent(
            "delete",
            expected_value=10,
            attention_cost=1,
            reversible=False,
            risk=RiskLevel.HIGH,
            required_authority=AuthorityLevel.ACT_IRREVERSIBLE,
            confidence=0.8,
        )
        spec = CapabilitySpec(
            "delete",
            "delete data",
            reversible=False,
            risk_level=RiskLevel.HIGH,
            required_authority=AuthorityLevel.ACT_IRREVERSIBLE,
        )
        self.assertTrue(policy.authorize(intent, spec, snapshot).allowed)
        await kernel.stop()

    def test_trust_ledger_starts_conservative_and_learns(self) -> None:
        ledger = TrustLedger()
        self.assertEqual(
            ledger.recommended_authority(
                "worker", reversible=True, risk=RiskLevel.LOW
            ),
            AuthorityLevel.OBSERVE,
        )
        for _ in range(30):
            ledger.record("worker", success=True)
        self.assertGreaterEqual(
            ledger.recommended_authority(
                "worker", reversible=True, risk=RiskLevel.LOW
            ),
            AuthorityLevel.ACT_REVERSIBLE,
        )
