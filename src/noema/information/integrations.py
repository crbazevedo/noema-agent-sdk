"""Narrow adapters that gate memory, model context, and worker feasibility."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from ..memory.models import SemanticAssertion
from ..memory.retrieval import MemoryQuery
from ..models import ContextAssembler, ModelMessage
from ..reasoning import DeliberationRequest
from ..work.models import WorkGraph, WorkNode
from .models import (
    AccessContext,
    DisclosureDecision,
    DisclosureForm,
    DisclosureRequest,
    GovernedInformationRef,
    InformationAccessDecision,
    InformationAccessRequest,
    InformationOperation,
    PrincipalSnapshot,
    SecurityAuditReceipt,
)
from .policy import InformationGovernanceEngine

InformationRefForAssertion = Callable[[SemanticAssertion], GovernedInformationRef | None]
ContextFactory = Callable[
    [DeliberationRequest, GovernedInformationRef, InformationOperation], AccessContext
]
ContextItemProvider = Callable[[DeliberationRequest], Iterable["GovernedContextItem"]]
PrincipalForAgent = Callable[[str], PrincipalSnapshot]
DestinationTrustDomainForAgent = Callable[[str, PrincipalSnapshot], str]


class GovernedMemoryAccess:
    """MemoryRetriever adapter that evaluates protected assertions before scoring."""

    def __init__(
        self,
        engine: InformationGovernanceEngine,
        *,
        information_ref_for: InformationRefForAssertion,
        actor_id: str,
        principal: PrincipalSnapshot,
        purpose: str,
        source_trust_domain: str,
        locality: str,
    ) -> None:
        self._engine = engine
        self._information_ref_for = information_ref_for
        self._actor_id = actor_id
        self._principal = principal
        self._purpose = purpose
        self._source_trust_domain = source_trust_domain
        self._locality = locality

    def evaluate(
        self,
        assertion: SemanticAssertion,
        query: MemoryQuery,
    ) -> InformationAccessDecision | None:
        information_ref = self._information_ref_for(assertion)
        if information_ref is None:
            return None
        context = self._engine.context_for(
            information_ref=information_ref,
            actor_id=self._actor_id,
            principal=self._principal,
            purpose=self._purpose,
            operation=InformationOperation.RETRIEVE,
            source_trust_domain=self._source_trust_domain,
            destination_trust_domain=None,
            recipient=None,
            decision_time=query.known_at,
            locality=self._locality,
        )
        return self._engine.decide_access(
            InformationAccessRequest.create(
                information_ref=information_ref,
                context=context,
            )
        )


@dataclass(frozen=True, slots=True)
class GovernedContextItem:
    information_ref: GovernedInformationRef
    message: ModelMessage


@dataclass(frozen=True, slots=True)
class GovernedContextAssembly:
    messages: tuple[ModelMessage, ...]
    access_decisions: tuple[InformationAccessDecision, ...]
    disclosure_decisions: tuple[DisclosureDecision, ...]

    def routine_audit_receipts(self) -> tuple[SecurityAuditReceipt, ...]:
        """Return bounded non-authorizing evidence for successful routine checks."""

        access_receipts = tuple(
            SecurityAuditReceipt.from_decision(value)
            for value in self.access_decisions
            if value.allowed
        )
        disclosure_receipts = tuple(
            SecurityAuditReceipt.from_decision(value)
            for value in self.disclosure_decisions
            if value.allowed
        )
        return (*access_receipts, *disclosure_receipts)


class GovernedContextAssembler:
    """Add explicitly governed items only after access and boundary disclosure checks."""

    def __init__(
        self,
        base: ContextAssembler,
        engine: InformationGovernanceEngine,
        *,
        items: ContextItemProvider,
        context_factory: ContextFactory,
    ) -> None:
        self._base = base
        self._engine = engine
        self._items = items
        self._context_factory = context_factory

    def assemble(self, request: DeliberationRequest) -> tuple[ModelMessage, ...]:
        return self.assemble_with_decisions(request).messages

    def assemble_with_decisions(self, request: DeliberationRequest) -> GovernedContextAssembly:
        messages = list(self._base.assemble(request))
        access_decisions: list[InformationAccessDecision] = []
        disclosure_decisions: list[DisclosureDecision] = []
        for item in self._items(request):
            context = self._context_factory(
                request,
                item.information_ref,
                InformationOperation.MODEL_CONTEXT,
            )
            if context.operation is not InformationOperation.MODEL_CONTEXT:
                raise ValueError("model context factory returned a different operation")
            access = self._engine.decide_access(
                InformationAccessRequest.create(
                    information_ref=item.information_ref,
                    context=context,
                )
            )
            access_decisions.append(access)
            if not access.allowed:
                continue
            crosses_boundary = (
                context.destination_trust_domain is not None
                and context.destination_trust_domain != context.source_trust_domain
            )
            if crosses_boundary:
                disclosure = self._engine.decide_disclosure(
                    DisclosureRequest.create(
                        information_ref=item.information_ref,
                        context=context,
                    )
                )
                disclosure_decisions.append(disclosure)
                if not disclosure.allowed:
                    continue
            messages.append(item.message)
        return GovernedContextAssembly(
            messages=tuple(messages),
            access_decisions=tuple(access_decisions),
            disclosure_decisions=tuple(disclosure_decisions),
        )


class GovernedWorkerAccess:
    """WorkerMatcher adapter: information feasibility precedes lease assignment."""

    def __init__(
        self,
        engine: InformationGovernanceEngine,
        *,
        principal_for_agent: PrincipalForAgent,
        actor_id: str,
        purpose: str,
        source_trust_domain: str,
        locality: str,
        disclosure_form: DisclosureForm = DisclosureForm.FULL,
        destination_trust_domain_for_agent: DestinationTrustDomainForAgent | None = None,
    ) -> None:
        self._engine = engine
        self._principal_for_agent = principal_for_agent
        self._actor_id = actor_id
        self._purpose = purpose
        self._source_trust_domain = source_trust_domain
        self._locality = locality
        self._disclosure_form = disclosure_form
        self._destination_trust_domain_for_agent = destination_trust_domain_for_agent

    @property
    def governance_state(self) -> object:
        return self._engine.state

    def evaluate(
        self,
        graph: WorkGraph,
        node: WorkNode,
        agent_id: str,
        *,
        at: datetime,
    ) -> tuple[InformationAccessDecision | DisclosureDecision, ...]:
        del graph
        principal = self._principal_for_agent(agent_id)
        destination_trust_domain = self._destination_domain(agent_id, principal)
        decisions: list[InformationAccessDecision | DisclosureDecision] = []
        for information_id in node.governed_information_refs:
            information_ref = GovernedInformationRef(information_id)
            context = self._engine.context_for(
                information_ref=information_ref,
                actor_id=self._actor_id,
                principal=principal,
                purpose=self._purpose,
                operation=InformationOperation.WORK_ASSIGN,
                source_trust_domain=self._source_trust_domain,
                destination_trust_domain=destination_trust_domain,
                recipient=agent_id,
                decision_time=at,
                locality=self._locality,
                disclosure_form=self._disclosure_form,
            )
            decisions.append(
                self._engine.decide_access(
                    InformationAccessRequest.create(
                        information_ref=information_ref,
                        context=context,
                    )
                )
            )
            if destination_trust_domain != self._source_trust_domain:
                decisions.append(
                    self._engine.decide_disclosure(
                        DisclosureRequest.create(
                            information_ref=information_ref,
                            context=context,
                        )
                    )
                )
        return tuple(decisions)

    def _destination_domain(
        self,
        agent_id: str,
        principal: PrincipalSnapshot,
    ) -> str:
        if self._destination_trust_domain_for_agent is not None:
            destination = self._destination_trust_domain_for_agent(agent_id, principal)
        elif len(principal.trust_domains) == 1:
            destination = principal.trust_domains[0]
        else:
            raise ValueError(
                "worker destination trust domain must be explicit for multi-domain principals"
            )
        if destination not in principal.trust_domains:
            raise ValueError(
                "worker destination trust domain is absent from its principal snapshot"
            )
        return destination
