from __future__ import annotations

import hashlib
import unittest
from datetime import timedelta
from pathlib import Path

import noema
from examples.g2_live_prep_conformance import (
    AUTHORIZED_ROLE,
    CORPUS_SHA256,
    CORPUS_SOURCE_SHA,
    DESTINATION_DOMAIN,
    FIXTURE_TIME,
    PROVIDER_ID,
    PROVIDER_RECIPIENT,
    PURPOSE,
    CapturingModelProvider,
    GenerationMechanism,
    GovernedContextMaterial,
    PhysicalPlaybackEvidence,
    ProviderTarget,
    SourceWorldProvenance,
    derive_content_ref,
    dispatch_governed_context,
    principal_snapshot,
    record_fictional_material,
)
from noema import (
    DecisionReason,
    DisclosureForm,
    HmacOpaqueInformationIdDeriver,
    InformationAccessRequest,
    InformationGovernanceAdmission,
    InformationGovernanceEngine,
    InformationGovernanceProjection,
    InformationOperation,
    ModelMessage,
    NoemaKernel,
)

REPOSITORY = Path(__file__).parents[1]
CORPUS_PATH = (
    REPOSITORY
    / "docs"
    / "pilot"
    / "fixtures"
    / "situated-partner-consumer-corpus-v1.json"
)
TEST_DERIVER = HmacOpaqueInformationIdDeriver(
    b"fictional-g2-test-key-material-32"
)


def _target() -> ProviderTarget:
    return ProviderTarget(
        provider_id=PROVIDER_ID,
        destination_trust_domain=DESTINATION_DOMAIN,
        recipient=PROVIDER_RECIPIENT,
        purpose=PURPOSE,
    )


class G2LivePrepConformanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.kernel = NoemaKernel()
        await self.kernel.start()
        self.projection = InformationGovernanceProjection()
        self.provider = CapturingModelProvider()

    async def asyncTearDown(self) -> None:
        await self.kernel.stop()

    async def test_exact_provider_request_uses_canonically_admitted_redacted_content(
        self,
    ) -> None:
        material = await record_fictional_material(self.kernel, TEST_DERIVER)
        dispatch = await dispatch_governed_context(
            kernel=self.kernel,
            projection=self.projection,
            provider=self.provider,
            deriver=TEST_DERIVER,
            materials=(material,),
            principal=principal_snapshot(
                captured_at=FIXTURE_TIME,
                has_live_prep_role=True,
            ),
            target=_target(),
            decision_time=FIXTURE_TIME + timedelta(minutes=1),
            correlation_id="turn:g2-accepted",
            generation_mechanism=GenerationMechanism.MOCKED_PROVIDER_BOUNDARY,
        )

        self.assertEqual(self.provider.requests, [dispatch.request])
        self.assertEqual(self.provider.requests[0].messages, (material.message,))
        self.assertNotIn("Internal drafting note", material.message.content)
        self.assertEqual(dispatch.evidence.source_world, (SourceWorldProvenance.FICTIONAL,))
        self.assertEqual(
            dispatch.evidence.generation,
            GenerationMechanism.MOCKED_PROVIDER_BOUNDARY,
        )
        self.assertEqual(dispatch.evidence.physical_playback, PhysicalPlaybackEvidence.NOT_RUN)

        access = dispatch.access_receipts[0]
        disclosure = dispatch.disclosure_receipts[0]
        self.assertEqual(
            self.projection.access_decision(access.record.decision_id),
            access.record,
        )
        self.assertEqual(
            self.projection.disclosure_decision(disclosure.record.decision_id),
            disclosure.record,
        )
        for context in (access.record.request.context, disclosure.record.request.context):
            self.assertEqual(context.provider_id, PROVIDER_ID)
            self.assertEqual(context.destination_trust_domain, DESTINATION_DOMAIN)
            self.assertEqual(context.recipient, PROVIDER_RECIPIENT)
            self.assertEqual(context.purpose, PURPOSE)
            self.assertEqual(context.disclosure_form, DisclosureForm.REDACTED)
        self.assertEqual(
            dispatch.request.metadata["content_sha256"],
            [hashlib.sha256(material.message.content.encode("utf-8")).hexdigest()],
        )

    async def test_valid_ref_alias_boolean_and_matching_fingerprint_do_not_authorize(
        self,
    ) -> None:
        admitted = await record_fictional_material(self.kernel, TEST_DERIVER)
        claimed_authorized = True
        claimed_reference_fingerprint = admitted.content_sha256
        unresolved_content = admitted.message.content
        unresolved_ref = derive_content_ref(
            TEST_DERIVER,
            namespace="syntactically-valid-but-unresolved",
            content=unresolved_content,
        )
        unresolved = GovernedContextMaterial(
            information_ref=unresolved_ref,
            source_information_ref=admitted.source_information_ref,
            namespace="syntactically-valid-but-unresolved",
            message=ModelMessage("user", unresolved_content),
            disclosure_form=DisclosureForm.REDACTED,
            source_provenance=SourceWorldProvenance.FICTIONAL,
        )

        self.assertTrue(claimed_authorized)
        self.assertEqual(claimed_reference_fingerprint, unresolved.content_sha256)
        with self.assertRaisesRegex(PermissionError, "canonical redacted lineage"):
            await dispatch_governed_context(
                kernel=self.kernel,
                projection=self.projection,
                provider=self.provider,
                deriver=TEST_DERIVER,
                materials=(unresolved,),
                principal=principal_snapshot(
                    captured_at=FIXTURE_TIME,
                    has_live_prep_role=True,
                ),
                target=_target(),
                decision_time=FIXTURE_TIME + timedelta(minutes=1),
                correlation_id="turn:g2-unresolved",
                generation_mechanism=GenerationMechanism.MOCKED_PROVIDER_BOUNDARY,
            )
        self.assertEqual(self.provider.requests, [])

    async def test_externally_supplied_post_withdrawal_snapshot_blocks_transmission(
        self,
    ) -> None:
        material = await record_fictional_material(self.kernel, TEST_DERIVER)
        common = {
            "kernel": self.kernel,
            "projection": self.projection,
            "provider": self.provider,
            "deriver": TEST_DERIVER,
            "materials": (material,),
            "target": _target(),
            "generation_mechanism": GenerationMechanism.MOCKED_PROVIDER_BOUNDARY,
        }
        await dispatch_governed_context(
            **common,
            principal=principal_snapshot(
                captured_at=FIXTURE_TIME,
                has_live_prep_role=True,
            ),
            decision_time=FIXTURE_TIME + timedelta(minutes=1),
            correlation_id="turn:g2-before-withdrawal",
        )
        self.assertEqual(len(self.provider.requests), 1)

        post_withdrawal_principal = principal_snapshot(
            captured_at=FIXTURE_TIME + timedelta(minutes=2),
            has_live_prep_role=False,
        )
        self.assertNotIn(AUTHORIZED_ROLE, post_withdrawal_principal.roles)
        with self.assertRaisesRegex(PermissionError, "current access admission denied"):
            await dispatch_governed_context(
                **common,
                principal=post_withdrawal_principal,
                decision_time=FIXTURE_TIME + timedelta(minutes=2),
                correlation_id="turn:g2-after-withdrawal",
            )
        self.assertEqual(len(self.provider.requests), 1)

    async def test_evaluate_and_learn_remain_independently_denied(self) -> None:
        material = await record_fictional_material(self.kernel, TEST_DERIVER)
        principal = principal_snapshot(
            captured_at=FIXTURE_TIME,
            has_live_prep_role=True,
        )
        for operation in (InformationOperation.EVALUATE, InformationOperation.LEARN):
            with self.subTest(operation=operation.value):
                self.projection.rebuild(await self.kernel.history())
                engine = InformationGovernanceEngine(self.projection)
                request = InformationAccessRequest.create(
                    information_ref=material.information_ref,
                    context=engine.context_for(
                        information_ref=material.information_ref,
                        actor_id="agent:fictional-companion",
                        principal=principal,
                        purpose=PURPOSE,
                        operation=operation,
                        source_trust_domain="trust-domain:fictional-local",
                        destination_trust_domain=DESTINATION_DOMAIN,
                        recipient=PROVIDER_RECIPIENT,
                        decision_time=FIXTURE_TIME + timedelta(minutes=3),
                        locality="local",
                    ),
                )
                receipt = await InformationGovernanceAdmission(
                    self.kernel,
                    self.projection,
                    source="test:g2-live-prep",
                ).admit_access(request)
                self.assertFalse(receipt.record.allowed)
                self.assertIn(
                    DecisionReason.SECONDARY_USE_NOT_PERMITTED,
                    receipt.record.policy_decision.reasons,
                )

    async def test_evaluate_only_grant_does_not_grant_learning(self) -> None:
        material = await record_fictional_material(
            self.kernel,
            TEST_DERIVER,
            allowed_secondary_uses=(InformationOperation.EVALUATE,),
        )
        principal = principal_snapshot(
            captured_at=FIXTURE_TIME,
            has_live_prep_role=True,
        )
        decisions = {}
        for operation in (InformationOperation.EVALUATE, InformationOperation.LEARN):
            self.projection.rebuild(await self.kernel.history())
            engine = InformationGovernanceEngine(self.projection)
            request = InformationAccessRequest.create(
                information_ref=material.information_ref,
                context=engine.context_for(
                    information_ref=material.information_ref,
                    actor_id="agent:fictional-companion",
                    principal=principal,
                    purpose=PURPOSE,
                    operation=operation,
                    source_trust_domain="trust-domain:fictional-local",
                    destination_trust_domain=DESTINATION_DOMAIN,
                    recipient=PROVIDER_RECIPIENT,
                    decision_time=FIXTURE_TIME + timedelta(minutes=4),
                    locality="local",
                ),
            )
            decisions[operation] = (
                await InformationGovernanceAdmission(
                    self.kernel,
                    self.projection,
                    source="test:g2-live-prep",
                ).admit_access(request)
            ).record
        self.assertTrue(decisions[InformationOperation.EVALUATE].allowed)
        self.assertFalse(decisions[InformationOperation.LEARN].allowed)

    def test_shared_consumer_corpus_coordinate_is_exact(self) -> None:
        self.assertEqual(
            hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest(),
            CORPUS_SHA256,
        )
        self.assertEqual(
            CORPUS_SOURCE_SHA,
            "621be5a8a0823c1a02c893edc69967f552e0895d",
        )

    @unittest.expectedFailure
    def test_future_provider_use_port_is_content_bound_and_current(self) -> None:
        """Executable requirement for the generic gap; no ADR runtime is added here."""

        provider_use_admission = getattr(noema, "GovernedModelProviderAdmission", None)
        self.assertIsNotNone(provider_use_admission)


if __name__ == "__main__":
    unittest.main()
