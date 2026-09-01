"""Decision-relevant retrieval over canonical semantic memory."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..information.models import InformationAccessDecision
from .models import EvidenceRelation, SemanticAssertion
from .projection import MemoryProjection

_TOKEN = re.compile(r"[\w:-]+", re.UNICODE)


def _tokens(value: object) -> frozenset[str]:
    return frozenset(token.casefold() for token in _TOKEN.findall(str(value)))


@dataclass(frozen=True, slots=True)
class RetrievalWeights:
    semantic: float = 0.30
    temporal: float = 0.20
    goal: float = 0.10
    evidence: float = 0.20
    freshness: float = 0.20
    contradiction: float = 0.15

    def __post_init__(self) -> None:
        values = (
            self.semantic,
            self.temporal,
            self.goal,
            self.evidence,
            self.freshness,
            self.contradiction,
        )
        if any(value < 0.0 for value in values):
            raise ValueError("retrieval weights cannot be negative")


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    text: str
    valid_at: datetime
    known_at: datetime
    goal_terms: tuple[str, ...] = ()
    limit: int = 10
    include_hypotheses: bool = False
    include_stale: bool = False

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("memory query text must be non-empty")
        if self.valid_at.tzinfo is None or self.known_at.tzinfo is None:
            raise ValueError("memory query times must be timezone-aware")
        if self.limit <= 0:
            raise ValueError("memory query limit must be positive")


@dataclass(frozen=True, slots=True)
class RetrievalComponents:
    semantic: float
    temporal: float
    goal: float
    evidence: float
    freshness: float
    contradiction: float


@dataclass(frozen=True, slots=True)
class RetrievedMemory:
    assertion: SemanticAssertion
    score: float
    components: RetrievalComponents
    access_decision: InformationAccessDecision | None = None


@dataclass(frozen=True, slots=True)
class MemoryRetrieval:
    results: tuple[RetrievedMemory, ...]
    access_decisions: tuple[InformationAccessDecision, ...]


class MemoryAccessEvaluator(Protocol):
    """Return a material decision for governed memory, or ``None`` if unbound."""

    def evaluate(
        self,
        assertion: SemanticAssertion,
        query: MemoryQuery,
    ) -> InformationAccessDecision | None: ...


class LexicalMemoryIndex:
    """Optional, disposable token projection; never a source of memory truth."""

    def __init__(self) -> None:
        self._tokens_by_assertion: dict[str, frozenset[str]] = {}

    @property
    def assertion_count(self) -> int:
        return len(self._tokens_by_assertion)

    def clear(self) -> None:
        self._tokens_by_assertion.clear()

    def rebuild(self, projection: MemoryProjection) -> None:
        self._tokens_by_assertion = {
            assertion.assertion_id: self.tokens_for(assertion)
            for assertion in projection.assertions
        }

    def get(self, assertion_id: str) -> frozenset[str] | None:
        return self._tokens_by_assertion.get(assertion_id)

    @staticmethod
    def tokens_for(assertion: SemanticAssertion) -> frozenset[str]:
        return _tokens(f"{assertion.subject} {assertion.predicate} {assertion.value}")


class MemoryRetriever:
    """Rank visible assertions using semantic, temporal, and epistemic signals."""

    def __init__(
        self,
        projection: MemoryProjection,
        *,
        weights: RetrievalWeights | None = None,
        index: LexicalMemoryIndex | None = None,
        access_evaluator: MemoryAccessEvaluator | None = None,
    ) -> None:
        self.projection = projection
        self.weights = weights or RetrievalWeights()
        self.index = index or LexicalMemoryIndex()
        self.access_evaluator = access_evaluator

    def rebuild_index(self) -> None:
        self.index.rebuild(self.projection)

    def drop_index(self) -> None:
        self.index.clear()

    def retrieve(self, query: MemoryQuery) -> tuple[RetrievedMemory, ...]:
        return self.retrieve_with_decisions(query).results

    def retrieve_with_decisions(self, query: MemoryQuery) -> MemoryRetrieval:
        assertions = self.projection.visible_assertions(
            valid_at=query.valid_at,
            known_at=query.known_at,
            include_hypotheses=query.include_hypotheses,
            include_stale=query.include_stale,
        )
        query_tokens = _tokens(query.text)
        goal_tokens = _tokens(" ".join(query.goal_terms))
        ranked: list[RetrievedMemory] = []
        access_decisions: list[InformationAccessDecision] = []
        for assertion in assertions:
            decision = (
                self.access_evaluator.evaluate(assertion, query)
                if self.access_evaluator is not None
                else None
            )
            if decision is not None:
                access_decisions.append(decision)
            if decision is not None and not decision.allowed:
                continue
            ranked.append(
                self._score(
                    assertion,
                    query=query,
                    query_tokens=query_tokens,
                    goal_tokens=goal_tokens,
                    access_decision=decision,
                )
            )
        ranked.sort(
            key=lambda result: (
                -result.score,
                -result.assertion.recorded_at.timestamp(),
                result.assertion.assertion_id,
            )
        )
        return MemoryRetrieval(
            results=tuple(ranked[: query.limit]),
            access_decisions=tuple(access_decisions),
        )

    def _score(
        self,
        assertion: SemanticAssertion,
        *,
        query: MemoryQuery,
        query_tokens: frozenset[str],
        goal_tokens: frozenset[str],
        access_decision: InformationAccessDecision | None,
    ) -> RetrievedMemory:
        assertion_tokens = self.index.get(assertion.assertion_id)
        if assertion_tokens is None:
            assertion_tokens = self.index.tokens_for(assertion)
        semantic = self._overlap(query_tokens, assertion_tokens)
        goal = self._overlap(goal_tokens, assertion_tokens) if goal_tokens else 0.0
        age_seconds = max(0.0, (query.valid_at - assertion.valid_from).total_seconds())
        temporal = 1.0 / (1.0 + age_seconds / (30.0 * 86_400.0))
        freshness = self._freshness(assertion, query.valid_at)
        evidence = self._evidence_strength(assertion, query.known_at)
        contradicted = self.projection.is_contradicted(
            assertion.assertion_id,
            valid_at=query.valid_at,
            known_at=query.known_at,
            include_stale=query.include_stale,
        )
        stale = assertion.fresh_until is not None and query.valid_at >= assertion.fresh_until
        contradiction = min(1.0, (0.65 if contradicted else 0.0) + (0.6 if stale else 0.0))
        components = RetrievalComponents(
            semantic=semantic,
            temporal=temporal,
            goal=goal,
            evidence=evidence,
            freshness=freshness,
            contradiction=contradiction,
        )
        weights = self.weights
        score = (
            weights.semantic * semantic
            + weights.temporal * temporal
            + weights.goal * goal
            + weights.evidence * evidence
            + weights.freshness * freshness
            - weights.contradiction * contradiction
        )
        return RetrievedMemory(
            assertion=assertion,
            score=score,
            components=components,
            access_decision=access_decision,
        )

    def _evidence_strength(self, assertion: SemanticAssertion, known_at: datetime) -> float:
        links = [
            link
            for link in self.projection.evidence_links
            if link.assertion_ref == assertion.assertion_id and link.recorded_at <= known_at
        ]
        if not links:
            return assertion.confidence
        positive = [
            link.strength
            for link in links
            if link.relation
            in {
                EvidenceRelation.SUPPORTS,
                EvidenceRelation.REFINES,
                EvidenceRelation.DERIVED_FROM,
            }
        ]
        negative = [
            link.strength for link in links if link.relation is EvidenceRelation.CONTRADICTS
        ]
        support = sum(positive) / len(positive) if positive else assertion.confidence
        opposition = sum(negative) / len(negative) if negative else 0.0
        return max(0.0, min(1.0, support * (1.0 - opposition)))

    @staticmethod
    def _freshness(assertion: SemanticAssertion, valid_at: datetime) -> float:
        if assertion.fresh_until is None:
            return 1.0
        lifetime = (assertion.fresh_until - assertion.recorded_at).total_seconds()
        remaining = (assertion.fresh_until - valid_at).total_seconds()
        return max(0.0, min(1.0, remaining / lifetime))

    @staticmethod
    def _overlap(left: frozenset[str], right: frozenset[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)
