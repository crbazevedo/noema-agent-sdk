from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from noema import (
    AccessContext,
    AgentPresence,
    AuthorityLevel,
    CapabilityManifest,
    Classification,
    CompetenceBasis,
    CompetenceEstimate,
    DecisionDisposition,
    DecisionReason,
    DeclassificationRequest,
    DefaultContextAssembler,
    DeliberationRequest,
    DisclosureForm,
    DisclosureRequest,
    DisclosureView,
    DurableWorkCoordinator,
    EpistemicType,
    Event,
    FakePlanner,
    GovernedContextAssembler,
    GovernedContextItem,
    GovernedInformationRef,
    GovernedMemoryAccess,
    GovernedWorkerAccess,
    HoldConstraint,
    InformationAccessDecision,
    InformationAccessRequest,
    InformationGovernanceEngine,
    InformationGovernanceProjection,
    InformationLineage,
    InformationOperation,
    InformationPolicy,
    LineageTransformation,
    MemoryProjection,
    MemoryQuery,
    MemoryRetriever,
    ModelMessage,
    NoemaKernel,
    PolicyBinding,
    PolicyConflictKind,
    PolicyDecision,
    PresenceStatus,
    PrincipalSnapshot,
    QuarantinedInformationRef,
    QuarantinePolicy,
    RetentionPolicy,
    SecurityAuditReceipt,
    SemanticAssertion,
    WorkerMatcher,
    WorkNode,
    WorkNodeKind,
    WorkOrder,
    opaque_information_id,
    validate_governance_event_envelope,
)

START = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _principal(
    principal_id: str,
    *,
    roles: tuple[str, ...] = (),
    trust_domains: tuple[str, ...] = ("local",),
) -> PrincipalSnapshot:
    return PrincipalSnapshot.create(
        principal_id=principal_id,
        roles=roles,
        groups=(),
        trust_domains=trust_domains,
        captured_at=START,
    )


def _policy(
    *,
    origin_domains: tuple[str, ...] = ("synthetic-source",),
    classification: Classification = Classification.CONFIDENTIAL,
    purposes: tuple[str, ...] = ("legal-review",),
    recipients: tuple[str, ...] = ("legal-review",),
    trust_domains: tuple[str, ...] = ("local",),
    localities: tuple[str, ...] = ("local",),
    providers: tuple[str, ...] = ("local-model",),
    sharing: bool = False,
    retention: RetentionPolicy | None = None,
    forms: tuple[DisclosureForm, ...] = (DisclosureForm.REDACTED,),
    authorities: tuple[str, ...] = ("legal-review",),
    version: int = 1,
) -> InformationPolicy:
    return InformationPolicy.create(
        version=version,
        origin_domains=origin_domains,
        classification=classification,
        allowed_purposes=purposes,
        allowed_recipients=recipients,
        allowed_trust_domains=trust_domains,
        allowed_localities=localities,
        allowed_providers=providers,
        cross_agent_sharing=sharing,
        retention=retention or RetentionPolicy(),
        disclosure_forms=forms,
        declassification_authorities=authorities,
        recorded_at=START,
    )


class _CanonicalGovernance:
    def __init__(self) -> None:
        self.projection = InformationGovernanceProjection()
        self.events: list[Event] = []

    def apply(self, event: Event) -> Event:
        canonical = event.with_sequence(len(self.events) + 1)
        self.projection.apply(canonical)
        self.events.append(canonical)
        return canonical

    def record_source(
        self,
        information_ref: GovernedInformationRef,
        policy: InformationPolicy,
    ) -> None:
        self.apply(policy.to_event(source="test:governance"))
        lineage = InformationLineage.create(
            information_id=information_ref.information_id,
            source_information_ids=(),
            transformation=LineageTransformation.SOURCE,
            recorded_at=START,
        )
        self.apply(lineage.to_event(source="test:governance"))
        self.apply(
            PolicyBinding.create(
                information_id=information_ref.information_id,
                lineage_id=lineage.lineage_id,
                policy_ids=(policy.policy_id,),
                bound_at=START,
            ).to_event(source="test:governance")
        )

    def record_derived(
        self,
        information_ref: GovernedInformationRef,
        source_refs: tuple[GovernedInformationRef, ...],
        policy_ids: tuple[str, ...],
        *,
        transformation: LineageTransformation = LineageTransformation.DERIVATION,
    ) -> None:
        lineage = InformationLineage.create(
            information_id=information_ref.information_id,
            source_information_ids=tuple(value.information_id for value in source_refs),
            transformation=transformation,
            recorded_at=START,
        )
        self.apply(lineage.to_event(source="test:governance"))
        self.apply(
            PolicyBinding.create(
                information_id=information_ref.information_id,
                lineage_id=lineage.lineage_id,
                policy_ids=policy_ids,
                bound_at=START,
            ).to_event(source="test:governance")
        )


class InformationPolicyKernelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = _CanonicalGovernance()
        self.source_a = GovernedInformationRef.create(namespace="test", stable_key="source-a")
        self.source_b = GovernedInformationRef.create(namespace="test", stable_key="source-b")
        self.derived = GovernedInformationRef.create(namespace="test", stable_key="derived-d")
        hold = HoldConstraint.create(authority_id="court", stable_key="synthetic-hold")
        self.policy_a = _policy(
            origin_domains=("user-owned",),
            classification=Classification.CONFIDENTIAL,
            purposes=("career-planning", "employment-work", "legal-review"),
            recipients=("employer-worker", "legal-review", "user"),
            trust_domains=("approved-provider", "legal", "local"),
            localities=("eu", "local"),
            providers=("local-model", "remote-model"),
            sharing=True,
            retention=RetentionPolicy(
                retain_until=START + timedelta(days=30),
                holds=(hold,),
            ),
            forms=(DisclosureForm.FULL, DisclosureForm.REDACTED),
            authorities=("legal-review", "privacy-officer"),
        )
        self.policy_b = _policy(
            origin_domains=("employer-owned",),
            classification=Classification.RESTRICTED,
            purposes=("employment-work", "legal-review"),
            recipients=("employer-worker", "legal-review"),
            trust_domains=("employer", "legal", "local"),
            localities=("local",),
            providers=("local-model",),
            sharing=True,
            retention=RetentionPolicy(
                delete_after=START + timedelta(days=7),
                deletion_required=True,
            ),
            forms=(DisclosureForm.REDACTED,),
            authorities=("legal-review",),
        )
        self.state.record_source(self.source_a, self.policy_a)
        self.state.record_source(self.source_b, self.policy_b)
        self.state.record_derived(
            self.derived,
            (self.source_a, self.source_b),
            (self.policy_a.policy_id, self.policy_b.policy_id),
        )
        self.engine = InformationGovernanceEngine(self.state.projection)

    def _context(
        self,
        information_ref: GovernedInformationRef,
        operation: InformationOperation,
        *,
        principal: PrincipalSnapshot | None = None,
        purpose: str = "legal-review",
        source_domain: str = "local",
        destination_domain: str | None = None,
        recipient: str | None = None,
        provider: str | None = None,
        form: DisclosureForm | None = None,
    ) -> AccessContext:
        return self.engine.context_for(
            information_ref=information_ref,
            actor_id="agent:steward",
            principal=principal or _principal("reviewer", roles=("legal-review",)),
            purpose=purpose,
            operation=operation,
            source_trust_domain=source_domain,
            destination_trust_domain=destination_domain,
            recipient=recipient,
            decision_time=START,
            locality="local",
            provider_id=provider,
            disclosure_form=form,
        )

    def test_flagship_composition_hold_delete_disclosure_and_transform(self) -> None:
        composition = self.engine.composition_for(self.derived)
        self.assertEqual(composition.classification, Classification.RESTRICTED)
        self.assertEqual(composition.allowed_purposes, ("employment-work", "legal-review"))
        self.assertEqual(composition.allowed_recipients, ("employer-worker", "legal-review"))
        self.assertEqual(composition.allowed_localities, ("local",))
        self.assertEqual(composition.allowed_providers, ("local-model",))
        self.assertEqual(composition.disclosure_forms, (DisclosureForm.REDACTED,))
        self.assertEqual(composition.declassification_authorities, ("legal-review",))

        read = self.engine.decide_access(
            InformationAccessRequest.create(
                information_ref=self.derived,
                context=self._context(self.derived, InformationOperation.READ),
            )
        )
        self.assertTrue(read.allowed)

        incompatible_career_use = self.engine.decide_access(
            InformationAccessRequest.create(
                information_ref=self.derived,
                context=self._context(
                    self.derived,
                    InformationOperation.READ,
                    principal=_principal("user"),
                    purpose="career-planning",
                ),
            )
        )
        self.assertFalse(incompatible_career_use.allowed)

        employment_use = self.engine.decide_access(
            InformationAccessRequest.create(
                information_ref=self.derived,
                context=self._context(
                    self.derived,
                    InformationOperation.READ,
                    principal=_principal("internal-worker", roles=("employer-worker",)),
                    purpose="employment-work",
                ),
            )
        )
        self.assertTrue(employment_use.allowed)

        remote_context = self._context(
            self.derived,
            InformationOperation.READ,
            principal=_principal("internal-worker", roles=("employer-worker",)),
            purpose="employment-work",
            destination_domain="remote",
            recipient="provider:remote",
            provider="remote-model",
            form=DisclosureForm.REDACTED,
        )
        remote_internal_access = self.engine.decide_access(
            InformationAccessRequest.create(
                information_ref=self.derived,
                context=remote_context,
            )
        )
        remote_disclosure = self.engine.decide_disclosure(
            DisclosureRequest.create(
                information_ref=self.derived,
                context=remote_context,
            )
        )
        self.assertTrue(remote_internal_access.allowed)
        self.assertFalse(remote_disclosure.allowed)

        deletion = self.engine.decide_access(
            InformationAccessRequest.create(
                information_ref=self.derived,
                context=self._context(self.derived, InformationOperation.DELETE),
            )
        )
        self.assertFalse(deletion.allowed)
        self.assertIn(PolicyConflictKind.LEGAL_HOLD_DELETION, deletion.policy_decision.conflicts)
        self.assertIn(PolicyConflictKind.RETENTION_WINDOW, deletion.policy_decision.conflicts)

        disclosure = self.engine.decide_disclosure(
            DisclosureRequest.create(
                information_ref=self.derived,
                context=self._context(
                    self.derived,
                    InformationOperation.READ,
                    destination_domain="legal",
                    recipient="legal-review",
                    provider="local-model",
                    form=DisclosureForm.REDACTED,
                ),
            )
        )
        self.assertTrue(disclosure.allowed)

        full_disclosure = self.engine.decide_disclosure(
            DisclosureRequest.create(
                information_ref=self.derived,
                context=self._context(
                    self.derived,
                    InformationOperation.READ,
                    destination_domain="legal",
                    recipient="legal-review",
                    provider="local-model",
                    form=DisclosureForm.FULL,
                ),
            )
        )
        self.assertFalse(full_disclosure.allowed)
        self.assertIn(
            DecisionReason.DISCLOSURE_FORM_NOT_PERMITTED,
            full_disclosure.policy_decision.reasons,
        )

        view = DisclosureView.create(
            source_information_ref=self.derived,
            transformation=LineageTransformation.REDACTION,
            inherited_policy_ids=composition.source_policy_ids,
            created_at=START,
        )
        self.state.record_derived(
            view.information_ref,
            (self.derived,),
            view.inherited_policy_ids,
            transformation=LineageTransformation.REDACTION,
        )
        transformed = self.engine.composition_for(view.information_ref)
        self.assertEqual(transformed.classification, Classification.RESTRICTED)
        self.assertEqual(transformed.source_policy_ids, composition.source_policy_ids)

    def test_declassification_requires_authority_acceptable_to_every_source(self) -> None:
        public_policy = _policy(
            classification=Classification.PUBLIC,
            recipients=("legal-review", "privacy-officer"),
            authorities=("legal-review",),
            version=2,
        )
        self.state.apply(public_policy.to_event(source="test:governance"))

        one_source_authority = self.engine.decide_declassification(
            DeclassificationRequest.create(
                information_ref=self.derived,
                proposed_policy_id=public_policy.policy_id,
                context=self._context(
                    self.derived,
                    InformationOperation.DECLASSIFY,
                    principal=_principal("privacy", roles=("privacy-officer",)),
                ),
            )
        )
        self.assertFalse(one_source_authority.allowed)

        user_attempt = self.engine.decide_declassification(
            DeclassificationRequest.create(
                information_ref=self.derived,
                proposed_policy_id=public_policy.policy_id,
                context=self._context(
                    self.derived,
                    InformationOperation.DECLASSIFY,
                    principal=_principal("user"),
                ),
            )
        )
        self.assertFalse(user_attempt.allowed)

        common_authority = self.engine.decide_declassification(
            DeclassificationRequest.create(
                information_ref=self.derived,
                proposed_policy_id=public_policy.policy_id,
                context=self._context(
                    self.derived,
                    InformationOperation.DECLASSIFY,
                ),
            )
        )
        self.assertTrue(common_authority.allowed)

    def test_replay_reruns_decisions_using_historical_principal_snapshot(self) -> None:
        request = InformationAccessRequest.create(
            information_ref=self.derived,
            context=self._context(self.derived, InformationOperation.READ),
        )
        decision = self.engine.decide_access(request)
        self.state.apply(decision.to_event(source="test:governance"))
        receipt = SecurityAuditReceipt.from_decision(decision)
        self.state.apply(receipt.to_event(source="test:governance"))

        current_roles = _principal("reviewer", roles=("visitor",))
        self.assertNotIn("legal-review", current_roles.roles)
        replayed = InformationGovernanceProjection()
        replayed.rebuild(self.state.events)
        self.assertEqual(replayed.semantic_snapshot(), self.state.projection.semantic_snapshot())

        forged = type(decision).create(
            request=request,
            composition_id=decision.composition_id,
            policy_decision=PolicyDecision(
                InformationOperation.READ,
                DecisionDisposition.DENY,
                (DecisionReason.PURPOSE_NOT_PERMITTED,),
                (),
            ),
            decided_at=START,
        )
        with self.assertRaisesRegex(ValueError, "deterministic policy evaluation"):
            replayed.apply(
                forged.to_event(source="test:governance").with_sequence(replayed.event_cursor + 1)
            )

    def test_quarantine_allows_local_classification_but_blocks_restricted_sinks(self) -> None:
        unknown = GovernedInformationRef.create(namespace="test", stable_key="unknown-input")
        quarantine = QuarantinedInformationRef.create(
            information_id=unknown.information_id,
            policy=QuarantinePolicy(),
            quarantined_at=START,
        )
        self.state.apply(quarantine.to_event(source="test:governance"))

        classify = self.engine.decide_access(
            InformationAccessRequest.create(
                information_ref=unknown,
                context=self._context(unknown, InformationOperation.CLASSIFY),
            )
        )
        self.assertTrue(classify.allowed)

        for operation in (
            InformationOperation.READ,
            InformationOperation.RETRIEVE,
            InformationOperation.REASON,
            InformationOperation.MODEL_CONTEXT,
            InformationOperation.WORK_ASSIGN,
            InformationOperation.SHARED_INDEX,
            InformationOperation.TELEMETRY,
            InformationOperation.EXTERNAL_CONNECTOR,
            InformationOperation.CROSS_AGENT_SHARE,
        ):
            denied = self.engine.decide_access(
                InformationAccessRequest.create(
                    information_ref=unknown,
                    context=self._context(unknown, operation),
                )
            )
            self.assertFalse(denied.allowed, operation)
            self.assertEqual(denied.policy_decision.reasons, (DecisionReason.QUARANTINED,))

        resolved_policy = _policy(
            purposes=("classification",),
            recipients=("classifier",),
        )
        self.state.apply(resolved_policy.to_event(source="test:governance"))
        resolved_lineage = InformationLineage.create(
            information_id=unknown.information_id,
            source_information_ids=(),
            transformation=LineageTransformation.SOURCE,
            recorded_at=START,
        )
        self.state.apply(resolved_lineage.to_event(source="test:governance"))
        self.state.apply(
            PolicyBinding.create(
                information_id=unknown.information_id,
                lineage_id=resolved_lineage.lineage_id,
                policy_ids=(resolved_policy.policy_id,),
                bound_at=START,
            ).to_event(source="test:governance")
        )
        self.assertIsNone(self.state.projection.quarantine(unknown.information_id))
        self.assertEqual(len(self.state.projection.quarantine_records), 1)
        resolved_read = self.engine.decide_access(
            InformationAccessRequest.create(
                information_ref=unknown,
                context=self._context(
                    unknown,
                    InformationOperation.READ,
                    principal=_principal("classifier"),
                    purpose="classification",
                ),
            )
        )
        self.assertTrue(resolved_read.allowed)

        human_only = GovernedInformationRef.create(
            namespace="test", stable_key="human-only-quarantine"
        )
        self.state.apply(
            QuarantinedInformationRef.create(
                information_id=human_only.information_id,
                policy=QuarantinePolicy(human_resolution_required=True),
                quarantined_at=START,
            ).to_event(source="test:governance")
        )
        human_only_classification = self.engine.decide_access(
            InformationAccessRequest.create(
                information_ref=human_only,
                context=self._context(human_only, InformationOperation.CLASSIFY),
            )
        )
        self.assertFalse(human_only_classification.allowed)

    def test_incomplete_lineage_missing_policy_and_stale_context_fail_closed(self) -> None:
        empty = InformationGovernanceProjection()
        incomplete_ref = GovernedInformationRef.create(namespace="test", stable_key="incomplete")
        incomplete_engine = InformationGovernanceEngine(empty)
        composition = incomplete_engine.composition_for(incomplete_ref)
        self.assertIn(
            PolicyConflictKind.INCOMPLETE_LINEAGE,
            {value.kind for value in composition.conflicts},
        )

        bad_lineage = InformationLineage.create(
            information_id=incomplete_ref.information_id,
            source_information_ids=(self.source_a.information_id,),
            transformation=LineageTransformation.DERIVATION,
            recorded_at=START,
        )
        with self.assertRaisesRegex(ValueError, "unknown source"):
            empty.apply(bad_lineage.to_event(source="test:governance").with_sequence(1))

        direct = InformationLineage.create(
            information_id=incomplete_ref.information_id,
            source_information_ids=(),
            transformation=LineageTransformation.SOURCE,
            recorded_at=START,
        )
        empty.apply(direct.to_event(source="test:governance").with_sequence(1))
        missing_policy_id = "ipol_" + "0" * 32
        bad_binding = PolicyBinding.create(
            information_id=incomplete_ref.information_id,
            lineage_id=direct.lineage_id,
            policy_ids=(missing_policy_id,),
            bound_at=START,
        )
        with self.assertRaisesRegex(ValueError, "unknown policy version"):
            empty.apply(bad_binding.to_event(source="test:governance").with_sequence(2))

        context = self._context(self.derived, InformationOperation.READ)
        stale_context = replace(context, policy_ids=(self.policy_a.policy_id,))
        stale = self.engine.decide_access(
            InformationAccessRequest.create(
                information_ref=self.derived,
                context=stale_context,
            )
        )
        self.assertFalse(stale.allowed)
        self.assertIn(DecisionReason.CONTEXT_POLICY_MISMATCH, stale.policy_decision.reasons)

    def test_safe_event_envelopes_use_opaque_index_fields(self) -> None:
        event = self.policy_a.to_event(source="test:governance")
        validate_governance_event_envelope(
            event,
            protected_values=("synthetic protected payload",),
        )
        self.assertTrue((event.subject or "").startswith("ipol_"))

        leaked = replace(event, source="test:synthetic protected payload")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            validate_governance_event_envelope(
                leaked,
                protected_values=("synthetic protected payload",),
            )
        unsafe_subject = replace(event, subject="synthetic protected payload")
        with self.assertRaisesRegex(ValueError, "opaque"):
            validate_governance_event_envelope(unsafe_subject)

    def test_adversarial_policy_dimensions_fail_only_affected_operations(self) -> None:
        empty_state = _CanonicalGovernance()
        left_ref = GovernedInformationRef.create(namespace="test", stable_key="empty-left")
        right_ref = GovernedInformationRef.create(namespace="test", stable_key="empty-right")
        empty_ref = GovernedInformationRef.create(namespace="test", stable_key="empty-derived")
        left = _policy(
            purposes=("purpose-a",),
            recipients=("recipient-a",),
            trust_domains=("domain-a",),
        )
        right = _policy(
            purposes=("purpose-b",),
            recipients=("recipient-b",),
            trust_domains=("domain-b",),
            version=2,
        )
        empty_state.record_source(left_ref, left)
        empty_state.record_source(right_ref, right)
        empty_state.record_derived(
            empty_ref,
            (left_ref, right_ref),
            (left.policy_id, right.policy_id),
        )
        empty_composition = InformationGovernanceEngine(empty_state.projection).composition_for(
            empty_ref
        )
        self.assertTrue(
            {
                PolicyConflictKind.EMPTY_PURPOSES,
                PolicyConflictKind.EMPTY_RECIPIENTS,
                PolicyConflictKind.EMPTY_TRUST_DOMAINS,
            }.issubset({value.kind for value in empty_composition.conflicts})
        )

        unknown_state = _CanonicalGovernance()
        unknown_ref = GovernedInformationRef.create(
            namespace="test", stable_key="unknown-classification"
        )
        unknown_state.record_source(
            unknown_ref,
            _policy(
                classification=Classification.UNKNOWN,
                purposes=("work",),
                recipients=("agent",),
            ),
        )
        unknown_engine = InformationGovernanceEngine(unknown_state.projection)
        unknown_context = unknown_engine.context_for(
            information_ref=unknown_ref,
            actor_id="agent",
            principal=_principal("agent"),
            purpose="work",
            operation=InformationOperation.READ,
            source_trust_domain="local",
            destination_trust_domain=None,
            recipient=None,
            decision_time=START,
            locality="local",
        )
        unknown = unknown_engine.decide_access(
            InformationAccessRequest.create(
                information_ref=unknown_ref,
                context=unknown_context,
            )
        )
        self.assertFalse(unknown.allowed)
        self.assertIn(
            PolicyConflictKind.UNKNOWN_CLASSIFICATION,
            unknown.policy_decision.conflicts,
        )

        guarded_state = _CanonicalGovernance()
        guarded_ref = GovernedInformationRef.create(namespace="test", stable_key="dimension-guards")
        guarded_state.record_source(
            guarded_ref,
            _policy(
                purposes=("work",),
                recipients=("agent",),
                trust_domains=("local",),
                localities=("local",),
                providers=("local-model",),
                sharing=False,
            ),
        )
        guarded_engine = InformationGovernanceEngine(guarded_state.projection)

        def decide(
            operation: InformationOperation,
            *,
            locality: str = "local",
            provider: str | None = None,
            recipient: str | None = None,
        ) -> InformationAccessDecision:
            context = guarded_engine.context_for(
                information_ref=guarded_ref,
                actor_id="agent",
                principal=_principal("agent"),
                purpose="work",
                operation=operation,
                source_trust_domain="local",
                destination_trust_domain="local",
                recipient=recipient,
                decision_time=START,
                locality=locality,
                provider_id=provider,
            )
            return guarded_engine.decide_access(
                InformationAccessRequest.create(
                    information_ref=guarded_ref,
                    context=context,
                )
            )

        cases = (
            (
                "provider",
                decide(InformationOperation.MODEL_CONTEXT, provider="remote-model"),
                DecisionReason.PROVIDER_NOT_PERMITTED,
            ),
            (
                "locality",
                decide(InformationOperation.READ, locality="remote"),
                DecisionReason.LOCALITY_NOT_PERMITTED,
            ),
            (
                "sharing",
                decide(InformationOperation.WORK_ASSIGN, recipient="agent"),
                DecisionReason.SHARING_NOT_PERMITTED,
            ),
            (
                "unknown operation",
                decide(InformationOperation.UNKNOWN),
                DecisionReason.UNKNOWN_OPERATION,
            ),
        )
        for name, decision, reason in cases:
            with self.subTest(name=name):
                self.assertFalse(decision.allowed)
                self.assertIn(reason, decision.policy_decision.reasons)


class InformationEnforcementIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_context_requires_access_and_cross_boundary_disclosure(self) -> None:
        state = _CanonicalGovernance()
        allowed_ref = GovernedInformationRef.create(namespace="test", stable_key="remote-allowed")
        disclosure_denied_ref = GovernedInformationRef.create(
            namespace="test", stable_key="remote-disclosure-denied"
        )
        allowed_policy = _policy(
            purposes=("deliberation",),
            recipients=("agent:user", "provider:remote"),
            trust_domains=("local", "remote"),
            providers=("local-model", "remote-model"),
            forms=(DisclosureForm.REDACTED,),
        )
        denied_policy = _policy(
            purposes=("deliberation",),
            recipients=("agent:user", "provider:remote"),
            trust_domains=("local",),
            providers=("local-model", "remote-model"),
            forms=(DisclosureForm.REDACTED,),
            version=2,
        )
        state.record_source(allowed_ref, allowed_policy)
        state.record_source(disclosure_denied_ref, denied_policy)
        engine = InformationGovernanceEngine(state.projection)

        kernel = NoemaKernel()
        await kernel.start()
        request = DeliberationRequest(
            "agent:user",
            Event("test.trigger", "test"),
            await kernel.snapshot(),
            (),
            10,
        )
        principal = _principal("agent:user")

        def context_factory(
            _request: DeliberationRequest,
            information_ref: GovernedInformationRef,
            operation: InformationOperation,
        ) -> AccessContext:
            return engine.context_for(
                information_ref=information_ref,
                actor_id="agent:user",
                principal=principal,
                purpose="deliberation",
                operation=operation,
                source_trust_domain="local",
                destination_trust_domain="remote",
                recipient="provider:remote",
                decision_time=START,
                locality="local",
                provider_id="remote-model",
                disclosure_form=DisclosureForm.REDACTED,
            )

        assembler = GovernedContextAssembler(
            DefaultContextAssembler(),
            engine,
            items=lambda _request: (
                GovernedContextItem(
                    allowed_ref,
                    ModelMessage("user", "synthetic allowed protected item"),
                ),
                GovernedContextItem(
                    disclosure_denied_ref,
                    ModelMessage("user", "synthetic blocked protected item"),
                ),
            ),
            context_factory=context_factory,
        )
        assembly = assembler.assemble_with_decisions(request)
        message_content = tuple(value.content for value in assembly.messages)
        self.assertIn("synthetic allowed protected item", message_content)
        self.assertNotIn("synthetic blocked protected item", message_content)
        self.assertEqual([value.allowed for value in assembly.access_decisions], [True, True])
        self.assertEqual([value.allowed for value in assembly.disclosure_decisions], [True, False])
        serialized_events = json.dumps(
            [value.to_dict() for value in assembly.decision_events(source="test:governance")]
        )
        self.assertNotIn("synthetic allowed protected item", serialized_events)
        self.assertNotIn("synthetic blocked protected item", serialized_events)

        def local_context_factory(
            _request: DeliberationRequest,
            information_ref: GovernedInformationRef,
            operation: InformationOperation,
        ) -> AccessContext:
            return engine.context_for(
                information_ref=information_ref,
                actor_id="agent:user",
                principal=principal,
                purpose="deliberation",
                operation=operation,
                source_trust_domain="local",
                destination_trust_domain="local",
                recipient="agent:user",
                decision_time=START,
                locality="local",
                provider_id="local-model",
            )

        local_assembly = GovernedContextAssembler(
            DefaultContextAssembler(),
            engine,
            items=lambda _request: (
                GovernedContextItem(
                    allowed_ref,
                    ModelMessage("user", "synthetic local protected item"),
                ),
            ),
            context_factory=local_context_factory,
        ).assemble_with_decisions(request)
        self.assertTrue(local_assembly.access_decisions[0].allowed)
        self.assertEqual(local_assembly.disclosure_decisions, ())
        self.assertIn(
            "synthetic local protected item",
            tuple(value.content for value in local_assembly.messages),
        )
        await kernel.stop()

    async def test_memory_retrieval_filters_denied_information_before_scoring(self) -> None:
        assertion = SemanticAssertion.create(
            subject="synthetic-user",
            predicate="private-preference",
            value="synthetic-value",
            epistemic_type=EpistemicType.OBSERVED,
            confidence=1.0,
            valid_from=START,
            recorded_at=START,
            source_refs=("event:synthetic",),
        )
        memory = MemoryProjection()
        memory.apply(
            Event(
                id="synthetic",
                type="test.observation",
                source="test:memory",
                timestamp=START,
            )
        )
        memory.apply(assertion.to_event(source="test:memory"))

        state = _CanonicalGovernance()
        information_ref = GovernedInformationRef.create(
            namespace="memory", stable_key=assertion.assertion_id
        )
        state.record_source(
            information_ref,
            _policy(
                purposes=("personalization",),
                recipients=("owner",),
            ),
        )
        engine = InformationGovernanceEngine(state.projection)
        evaluator = GovernedMemoryAccess(
            engine,
            information_ref_for=lambda candidate: (
                information_ref if candidate.assertion_id == assertion.assertion_id else None
            ),
            actor_id="agent:visitor",
            principal=_principal("visitor"),
            purpose="personalization",
            source_trust_domain="local",
            locality="local",
        )
        result = MemoryRetriever(memory, access_evaluator=evaluator).retrieve_with_decisions(
            MemoryQuery(
                "private preference",
                valid_at=START,
                known_at=START,
            )
        )
        self.assertEqual(result.results, ())
        self.assertEqual(len(result.access_decisions), 1)
        self.assertFalse(result.access_decisions[0].allowed)

    async def test_worker_matcher_treats_access_as_feasibility_and_lease_evidence(
        self,
    ) -> None:
        kernel = NoemaKernel()
        await kernel.start()
        information_ref = GovernedInformationRef.create(
            namespace="work", stable_key="protected-input"
        )
        policy = _policy(
            purposes=("governed-work",),
            recipients=("agent-allowed",),
            trust_domains=("local",),
            sharing=True,
        )
        lineage = InformationLineage.create(
            information_id=information_ref.information_id,
            source_information_ids=(),
            transformation=LineageTransformation.SOURCE,
            recorded_at=START,
        )
        binding = PolicyBinding.create(
            information_id=information_ref.information_id,
            lineage_id=lineage.lineage_id,
            policy_ids=(policy.policy_id,),
            bound_at=START,
        )
        for event in (
            policy.to_event(source="test:governance"),
            lineage.to_event(source="test:governance"),
            binding.to_event(source="test:governance"),
        ):
            await kernel.emit(event)
        governance = InformationGovernanceProjection()
        governance.rebuild(await kernel.history())
        engine = InformationGovernanceEngine(governance)

        principals = {
            "agent-allowed": _principal("agent-allowed"),
            "agent-denied": _principal("agent-denied"),
        }
        matcher = WorkerMatcher(
            GovernedWorkerAccess(
                engine,
                principal_for_agent=principals.__getitem__,
                actor_id="agent:coordinator",
                purpose="governed-work",
                source_trust_domain="local",
                locality="local",
            )
        )
        node = WorkNode(
            "A",
            WorkNodeKind.ANALYZE,
            "analyze synthetic protected input",
            ("analysis",),
            ("analysis exists",),
            governed_information_refs=(information_ref.information_id,),
        )
        planner = FakePlanner(
            nodes=(node,),
            dependencies=(),
            assumptions=(),
            done_conditions=("analysis exists",),
            replan_event_types=("information.policy_changed",),
            clock=lambda: START,
        )
        coordinator = DurableWorkCoordinator(
            kernel,
            planner=planner,
            matcher=matcher,
            information_projection=governance,
            clock=lambda: START,
        )
        order = WorkOrder.create(
            purpose="analyze governed information",
            governing_goal_refs=("goal:synthetic",),
            created_from=("request:synthetic",),
            priority=0.8,
            desired_outcome="analysis exists",
            success_criteria=("analysis exists",),
            created_at=START,
            authority_ceiling=AuthorityLevel.PROPOSE,
        )
        await coordinator.record_work_order(order)
        for agent_id, score in (("agent-denied", 0.99), ("agent-allowed", 0.80)):
            await coordinator.record_presence(
                AgentPresence(
                    agent_id,
                    PresenceStatus.AVAILABLE,
                    1,
                    START,
                    START + timedelta(hours=1),
                )
            )
            await coordinator.record_manifest(
                CapabilityManifest.create(
                    agent_id=agent_id,
                    capabilities=("analysis",),
                    recorded_at=START,
                )
            )
            await coordinator.record_competence(
                CompetenceEstimate.create(
                    agent_id=agent_id,
                    capability="analysis",
                    score=score,
                    evidence_confidence=1.0,
                    basis=CompetenceBasis.SEEDED,
                    evidence_refs=(),
                    estimated_at=START,
                )
            )
        await coordinator.plan(order.work_order_id)
        leases = await coordinator.assign_ready(order.work_order_id)
        self.assertEqual(len(leases), 1)
        self.assertEqual(leases[0].agent_id, "agent-allowed")
        self.assertEqual(len(leases[0].information_access_decision_refs), 1)

        replayed_governance = InformationGovernanceProjection()
        replayed_governance.rebuild(await kernel.history())
        self.assertEqual(len(replayed_governance.access_decisions), 2)
        denied_workers = {
            value.request.context.principal.principal_id
            for value in replayed_governance.access_decisions
            if not value.allowed
        }
        self.assertEqual(denied_workers, {"agent-denied"})
        self.assertIsNotNone(
            replayed_governance.access_decision(leases[0].information_access_decision_refs[0])
        )
        await kernel.stop()


class OpaqueIdentifierTests(unittest.TestCase):
    def test_fixture_identifier_does_not_embed_the_stable_key(self) -> None:
        identifier = opaque_information_id(
            namespace="synthetic", stable_key="descriptive-but-not-content"
        )
        self.assertNotIn("descriptive", identifier)
        self.assertRegex(identifier, r"^info_[0-9a-f]{32}$")
