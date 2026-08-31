"""Deterministic episodic, evidence, and bitemporal belief projections."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from ..events import Event
from ..types import JSONScalar, parse_datetime, utc_now
from .models import (
    ASSERTION_RECORDED_EVENT,
    ASSERTION_SUPERSEDED_EVENT,
    CONTRADICTION_DETECTED_EVENT,
    CONTRADICTION_RESOLVED_EVENT,
    EVIDENCE_LINKED_EVENT,
    VALIDITY_CLOSED_EVENT,
    AssertionStatus,
    AssertionSupersession,
    EpistemicType,
    EvidenceLink,
    EvidenceRelation,
    MemoryContradiction,
    SemanticAssertion,
    ValidityClosure,
)


class BeliefDisposition(StrEnum):
    UNKNOWN = "unknown"
    HELD = "held"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class BeliefState:
    """A query result, not a mutable belief record."""

    subject: str
    predicate: str
    disposition: BeliefDisposition
    value: JSONScalar
    max_assertion_confidence: float
    assertions: tuple[SemanticAssertion, ...]
    evidence: tuple[EvidenceLink, ...]
    contradictions: tuple[MemoryContradiction, ...]
    valid_at: datetime
    known_at: datetime

    @property
    def uncertain(self) -> bool:
        return self.disposition is BeliefDisposition.UNCERTAIN


@dataclass(frozen=True, slots=True)
class EvidenceObject:
    """A provenance reference resolved against canonical memory state."""

    reference: str
    namespace: str
    value: Event | SemanticAssertion
    epistemic_type: EpistemicType | None


class EpisodicMemory:
    """A rebuildable chronological view of canonical events."""

    def __init__(self) -> None:
        self._events: dict[str, Event] = {}

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(
            sorted(
                self._events.values(),
                key=lambda event: (event.sequence or 0, event.timestamp, event.id),
            )
        )

    def get(self, event_id: str) -> Event | None:
        return self._events.get(event_id)

    def apply(self, event: Event) -> bool:
        existing = self._events.get(event.id)
        if existing is not None:
            if existing != event:
                raise ValueError(f"conflicting canonical event identity: {event.id}")
            return False
        self._events[event.id] = event
        return True

    def query(
        self,
        *,
        after: datetime | None = None,
        before: datetime | None = None,
        subject: str | None = None,
        event_types: tuple[str, ...] | None = None,
    ) -> tuple[Event, ...]:
        events = self.events
        return tuple(
            event
            for event in events
            if (after is None or event.timestamp >= after)
            and (before is None or event.timestamp < before)
            and (subject is None or event.subject == subject)
            and (event_types is None or event.type in event_types)
        )


class MemoryProjection:
    """Canonical projection of immutable assertions and epistemic transitions."""

    def __init__(self) -> None:
        self.episodes = EpisodicMemory()
        self._assertions: dict[str, SemanticAssertion] = {}
        self._evidence: dict[str, EvidenceLink] = {}
        self._supersessions: dict[str, AssertionSupersession] = {}
        self._closures: dict[str, ValidityClosure] = {}
        self._contradictions: dict[str, MemoryContradiction] = {}
        self._applied_memory_events: dict[str, Event] = {}

    @property
    def assertions(self) -> tuple[SemanticAssertion, ...]:
        return tuple(self._assertions[key] for key in sorted(self._assertions))

    @property
    def evidence_links(self) -> tuple[EvidenceLink, ...]:
        return tuple(self._evidence[key] for key in sorted(self._evidence))

    @property
    def supersessions(self) -> tuple[AssertionSupersession, ...]:
        return tuple(self._supersessions[key] for key in sorted(self._supersessions))

    @property
    def validity_closures(self) -> tuple[ValidityClosure, ...]:
        return tuple(self._closures[key] for key in sorted(self._closures))

    @property
    def contradictions(self) -> tuple[MemoryContradiction, ...]:
        return tuple(self._contradictions[key] for key in sorted(self._contradictions))

    def get_assertion(self, assertion_id: str) -> SemanticAssertion | None:
        return self._assertions.get(assertion_id)

    def apply(self, event: Event, *, derived_source: str | None = None) -> tuple[Event, ...]:
        """Apply one event and optionally return deterministic events it entails."""

        self.episodes.apply(event)
        if not event.type.startswith("memory."):
            return ()
        existing_event = self._applied_memory_events.get(event.id)
        if existing_event is not None:
            if existing_event != event:
                raise ValueError(f"conflicting memory event identity: {event.id}")
            return ()

        derived: list[Event] = []
        if event.type == ASSERTION_RECORDED_EVENT:
            assertion = SemanticAssertion.from_event(event)
            self._validate_assertion_provenance(assertion)
            existing_assertion = self._assertions.get(assertion.assertion_id)
            if existing_assertion is not None and existing_assertion != assertion:
                raise ValueError(f"conflicting assertion identity: {assertion.assertion_id}")
            if derived_source is not None:
                if assertion.supersedes is not None:
                    prior = self._require_assertion(assertion.supersedes)
                    if (prior.subject, prior.predicate) != (
                        assertion.subject,
                        assertion.predicate,
                    ):
                        raise ValueError("an assertion may only supersede the same semantic key")
            self._assertions[assertion.assertion_id] = assertion
            try:
                if (
                    derived_source is not None
                    and assertion.supersedes is not None
                    and not self._has_supersession(assertion.supersedes, assertion.assertion_id)
                ):
                    prior = self._require_assertion(assertion.supersedes)
                    transition = AssertionSupersession.create(
                        prior_assertion_ref=prior.assertion_id,
                        new_assertion_ref=assertion.assertion_id,
                        effective_at=assertion.valid_from,
                        recorded_at=assertion.recorded_at,
                    )
                    derived.append(
                        transition.to_event(source=derived_source, causation_id=event.id)
                    )
                if derived_source is not None:
                    derived.extend(self._new_contradiction_events(assertion, event, derived_source))
            except BaseException:
                if existing_assertion is None:
                    self._assertions.pop(assertion.assertion_id, None)
                raise
        elif event.type == EVIDENCE_LINKED_EVENT:
            link = EvidenceLink.from_event(event)
            target = self._require_assertion(link.assertion_ref)
            evidence_object = self.resolve_evidence_ref(link.evidence_ref)
            if (
                evidence_object.epistemic_type is not None
                and evidence_object.epistemic_type is not link.evidence_type
            ):
                raise ValueError("evidence link provenance does not match its source")
            if (
                target.epistemic_type is EpistemicType.OBSERVED
                and link.evidence_type is EpistemicType.SIMULATED
                and link.relation
                in {
                    EvidenceRelation.SUPPORTS,
                    EvidenceRelation.REFINES,
                    EvidenceRelation.SUPERSEDES,
                    EvidenceRelation.DERIVED_FROM,
                }
            ):
                raise ValueError("simulated evidence cannot support an observed assertion")
            existing_link = self._evidence.get(link.link_id)
            if existing_link is not None and existing_link != link:
                raise ValueError(f"conflicting evidence-link identity: {link.link_id}")
            self._evidence[link.link_id] = link
        elif event.type == ASSERTION_SUPERSEDED_EVENT:
            transition = AssertionSupersession.from_event(event)
            prior = self._require_assertion(transition.prior_assertion_ref)
            new = self._require_assertion(transition.new_assertion_ref)
            if (prior.subject, prior.predicate) != (new.subject, new.predicate):
                raise ValueError("supersession must preserve the semantic key")
            if new.supersedes not in (None, prior.assertion_id):
                raise ValueError("supersession conflicts with the new assertion record")
            existing_transition = self._supersessions.get(transition.transition_id)
            if existing_transition is not None and existing_transition != transition:
                raise ValueError(f"conflicting supersession identity: {transition.transition_id}")
            self._supersessions[transition.transition_id] = transition
            try:
                if derived_source is not None:
                    derived.extend(
                        self._new_resolution_events(
                            at=transition.recorded_at,
                            trigger=event,
                            source=derived_source,
                            reason="superseded",
                        )
                    )
            except BaseException:
                if existing_transition is None:
                    self._supersessions.pop(transition.transition_id, None)
                raise
        elif event.type == VALIDITY_CLOSED_EVENT:
            closure = ValidityClosure.from_event(event)
            assertion = self._require_assertion(closure.assertion_ref)
            if closure.valid_to <= assertion.valid_from:
                raise ValueError("validity closure must follow assertion valid_from")
            existing_closure = self._closures.get(closure.closure_id)
            if existing_closure is not None and existing_closure != closure:
                raise ValueError(f"conflicting validity-closure identity: {closure.closure_id}")
            self._closures[closure.closure_id] = closure
            try:
                if derived_source is not None:
                    derived.extend(
                        self._new_resolution_events(
                            at=closure.recorded_at,
                            trigger=event,
                            source=derived_source,
                            reason="validity_closed",
                        )
                    )
            except BaseException:
                if existing_closure is None:
                    self._closures.pop(closure.closure_id, None)
                raise
        elif event.type == CONTRADICTION_DETECTED_EVENT:
            contradiction = self._contradiction_from_detection(event)
            for assertion_ref in contradiction.assertion_refs:
                self._require_assertion(assertion_ref)
            existing_contradiction = self._contradictions.get(contradiction.contradiction_id)
            if existing_contradiction is not None and existing_contradiction != contradiction:
                raise ValueError(
                    f"conflicting contradiction identity: {contradiction.contradiction_id}"
                )
            self._contradictions[contradiction.contradiction_id] = contradiction
        elif event.type == CONTRADICTION_RESOLVED_EVENT:
            contradiction_id = str(event.payload["contradiction_id"])
            existing_contradiction = self._contradictions.get(contradiction_id)
            if existing_contradiction is None:
                raise ValueError(f"resolution references unknown contradiction: {contradiction_id}")
            resolved_at = parse_datetime(cast(str, event.payload["resolved_at"]))
            if resolved_at is None or event.timestamp != resolved_at:
                raise ValueError("contradiction resolution timestamp is inconsistent")
            reason = str(event.payload["reason"])
            resolved = existing_contradiction.resolve(resolved_at=resolved_at, reason=reason)
            if (
                existing_contradiction.resolved_at is not None
                and existing_contradiction != resolved
            ):
                raise ValueError(f"conflicting contradiction resolution: {contradiction_id}")
            self._contradictions[contradiction_id] = resolved
        else:
            raise ValueError(f"unsupported memory event type: {event.type}")

        self._applied_memory_events[event.id] = event
        return tuple(sorted(derived, key=lambda item: item.id))

    def rebuild(
        self,
        events: Iterable[Event],
        *,
        through_sequence: int | None = None,
    ) -> None:
        self.episodes = EpisodicMemory()
        self._assertions.clear()
        self._evidence.clear()
        self._supersessions.clear()
        self._closures.clear()
        self._contradictions.clear()
        self._applied_memory_events.clear()
        for event in events:
            if through_sequence is not None and (event.sequence or 0) > through_sequence:
                continue
            self.apply(event)

    def visible_assertions(
        self,
        *,
        valid_at: datetime | None = None,
        known_at: datetime | None = None,
        include_hypotheses: bool = False,
        include_stale: bool = False,
    ) -> tuple[SemanticAssertion, ...]:
        valid = valid_at or utc_now()
        known = known_at or valid
        self._validate_query_times(valid, known)
        visible = [
            assertion
            for assertion in self._assertions.values()
            if self._is_visible(
                assertion,
                valid_at=valid,
                known_at=known,
                include_stale=include_stale,
            )
            and (include_hypotheses or assertion.status is AssertionStatus.ACTIVE)
        ]
        return tuple(
            sorted(
                visible,
                key=lambda assertion: (
                    assertion.subject,
                    assertion.predicate,
                    assertion.recorded_at,
                    assertion.assertion_id,
                ),
            )
        )

    def belief(
        self,
        subject: str,
        predicate: str,
        *,
        valid_at: datetime | None = None,
        known_at: datetime | None = None,
        include_stale: bool = False,
    ) -> BeliefState:
        valid = valid_at or utc_now()
        known = known_at or valid
        assertions = tuple(
            assertion
            for assertion in self.visible_assertions(
                valid_at=valid,
                known_at=known,
                include_stale=include_stale,
            )
            if assertion.subject == subject and assertion.predicate == predicate
        )
        values = {self._value_key(assertion.value) for assertion in assertions}
        contradictions = self._visible_contradictions(assertions, known_at=known)
        evidence = tuple(
            link
            for link in self.evidence_links
            if link.assertion_ref in {item.assertion_id for item in assertions}
            and link.recorded_at <= known
        )
        if not assertions:
            disposition = BeliefDisposition.UNKNOWN
            value: JSONScalar = None
            max_assertion_confidence = 0.0
        elif len(values) > 1 or contradictions:
            disposition = BeliefDisposition.UNCERTAIN
            value = None
            max_assertion_confidence = max(assertion.confidence for assertion in assertions)
        else:
            disposition = BeliefDisposition.HELD
            value = assertions[-1].value
            max_assertion_confidence = max(assertion.confidence for assertion in assertions)
        return BeliefState(
            subject=subject,
            predicate=predicate,
            disposition=disposition,
            value=value,
            max_assertion_confidence=max_assertion_confidence,
            assertions=assertions,
            evidence=evidence,
            contradictions=contradictions,
            valid_at=valid,
            known_at=known,
        )

    def hypotheses(
        self,
        *,
        valid_at: datetime | None = None,
        known_at: datetime | None = None,
    ) -> tuple[SemanticAssertion, ...]:
        return tuple(
            assertion
            for assertion in self.visible_assertions(
                valid_at=valid_at,
                known_at=known_at,
                include_hypotheses=True,
            )
            if assertion.status is AssertionStatus.HYPOTHESIS
        )

    def unresolved_contradictions(
        self,
        *,
        known_at: datetime | None = None,
    ) -> tuple[MemoryContradiction, ...]:
        known = known_at or utc_now()
        return tuple(
            contradiction
            for contradiction in self.contradictions
            if contradiction.detected_at <= known
            and (contradiction.resolved_at is None or contradiction.resolved_at > known)
        )

    def effective_valid_to(
        self, assertion: SemanticAssertion, *, known_at: datetime
    ) -> datetime | None:
        boundaries = [assertion.valid_to] if assertion.valid_to is not None else []
        boundaries.extend(
            closure.valid_to
            for closure in self._closures.values()
            if closure.assertion_ref == assertion.assertion_id and closure.recorded_at <= known_at
        )
        return min(boundaries) if boundaries else None

    def is_contradicted(
        self,
        assertion_id: str,
        *,
        valid_at: datetime | None = None,
        known_at: datetime | None = None,
        include_stale: bool = False,
    ) -> bool:
        valid = valid_at or utc_now()
        known = known_at or valid
        visible_ids = {
            assertion.assertion_id
            for assertion in self.visible_assertions(
                valid_at=valid,
                known_at=known,
                include_hypotheses=True,
                include_stale=include_stale,
            )
        }
        if assertion_id not in visible_ids:
            return False
        return any(
            assertion_id in contradiction.assertion_refs
            and set(contradiction.assertion_refs).issubset(visible_ids)
            for contradiction in self.unresolved_contradictions(known_at=known)
        )

    def _is_visible(
        self,
        assertion: SemanticAssertion,
        *,
        valid_at: datetime,
        known_at: datetime,
        include_stale: bool,
    ) -> bool:
        if assertion.recorded_at > known_at or assertion.valid_from > valid_at:
            return False
        valid_to = self.effective_valid_to(assertion, known_at=known_at)
        if valid_to is not None and valid_at >= valid_to:
            return False
        if (
            not include_stale
            and assertion.fresh_until is not None
            and valid_at >= assertion.fresh_until
        ):
            return False
        return not any(
            transition.prior_assertion_ref == assertion.assertion_id
            and transition.recorded_at <= known_at
            and transition.effective_at <= valid_at
            for transition in self._supersessions.values()
        )

    def _new_contradiction_events(
        self,
        assertion: SemanticAssertion,
        trigger: Event,
        source: str,
    ) -> tuple[Event, ...]:
        events: list[Event] = []
        for other in self._assertions.values():
            if other.assertion_id == assertion.assertion_id:
                continue
            if (other.subject, other.predicate) != (assertion.subject, assertion.predicate):
                continue
            if self._value_key(other.value) == self._value_key(assertion.value):
                continue
            if (
                assertion.supersedes == other.assertion_id
                or other.supersedes == assertion.assertion_id
            ):
                continue
            if self._has_supersession(
                other.assertion_id, assertion.assertion_id
            ) or self._has_supersession(assertion.assertion_id, other.assertion_id):
                continue
            if not self._intervals_overlap(assertion, other, known_at=assertion.recorded_at):
                continue
            contradiction = MemoryContradiction.detect(
                assertion_refs=(assertion.assertion_id, other.assertion_id),
                subject=assertion.subject,
                predicate=assertion.predicate,
                detected_at=assertion.recorded_at,
            )
            if contradiction.contradiction_id in self._contradictions:
                continue
            events.append(contradiction.detection_event(source=source, causation_id=trigger.id))
        return tuple(events)

    def _new_resolution_events(
        self,
        *,
        at: datetime,
        trigger: Event,
        source: str,
        reason: str,
    ) -> tuple[Event, ...]:
        events: list[Event] = []
        for contradiction in self._contradictions.values():
            if contradiction.resolved_at is not None:
                continue
            left = self._require_assertion(contradiction.assertion_refs[0])
            right = self._require_assertion(contradiction.assertion_refs[1])
            if self._intervals_overlap(left, right, known_at=at) and not self._directly_superseded(
                left.assertion_id, right.assertion_id
            ):
                continue
            resolved = contradiction.resolve(resolved_at=at, reason=reason)
            events.append(resolved.resolution_event(source=source, causation_id=trigger.id))
        return tuple(events)

    def _intervals_overlap(
        self,
        left: SemanticAssertion,
        right: SemanticAssertion,
        *,
        known_at: datetime,
    ) -> bool:
        left_to = self.effective_valid_to(left, known_at=known_at)
        right_to = self.effective_valid_to(right, known_at=known_at)
        return (left_to is None or right.valid_from < left_to) and (
            right_to is None or left.valid_from < right_to
        )

    def _directly_superseded(self, left_id: str, right_id: str) -> bool:
        return self._has_supersession(left_id, right_id) or self._has_supersession(
            right_id, left_id
        )

    def _has_supersession(self, prior_id: str, new_id: str) -> bool:
        return any(
            transition.prior_assertion_ref == prior_id and transition.new_assertion_ref == new_id
            for transition in self._supersessions.values()
        )

    def _visible_contradictions(
        self,
        assertions: tuple[SemanticAssertion, ...],
        *,
        known_at: datetime,
    ) -> tuple[MemoryContradiction, ...]:
        visible_ids = {assertion.assertion_id for assertion in assertions}
        return tuple(
            contradiction
            for contradiction in self.unresolved_contradictions(known_at=known_at)
            if set(contradiction.assertion_refs).issubset(visible_ids)
        )

    def _require_assertion(self, assertion_id: str) -> SemanticAssertion:
        assertion = self._assertions.get(assertion_id)
        if assertion is None:
            raise ValueError(f"memory transition references unknown assertion: {assertion_id}")
        return assertion

    def _validate_assertion_provenance(self, assertion: SemanticAssertion) -> None:
        anchors = tuple(
            self.resolve_evidence_ref(ref)
            for ref in (*assertion.source_refs, *assertion.derivation_refs)
        )
        if assertion.epistemic_type is EpistemicType.OBSERVED and any(
            anchor.epistemic_type is EpistemicType.SIMULATED for anchor in anchors
        ):
            raise ValueError("simulated provenance cannot support an observed assertion")

    def resolve_evidence_ref(self, ref: str) -> EvidenceObject:
        """Resolve a closed provenance namespace or fail without recording an edge."""

        namespace, separator, identifier = ref.partition(":")
        if not separator or not namespace or not identifier:
            raise ValueError("evidence refs require a non-empty namespace and identity")
        if namespace == "event":
            event = self.episodes.get(identifier)
            if event is None:
                raise ValueError(f"unknown canonical evidence event: {identifier}")
            return EvidenceObject(
                reference=ref,
                namespace=namespace,
                value=event,
                epistemic_type=self._event_epistemic_type(event),
            )
        if namespace == "assertion":
            source_assertion = self._assertions.get(ref)
            if source_assertion is None:
                raise ValueError(f"unknown evidence assertion: {ref}")
            return EvidenceObject(
                reference=ref,
                namespace=namespace,
                value=source_assertion,
                epistemic_type=source_assertion.epistemic_type,
            )
        if namespace == "simulation":
            event = self.episodes.get(identifier)
            if event is None:
                raise ValueError(f"unknown simulation artifact: {identifier}")
            epistemic_type = self._event_epistemic_type(event)
            if epistemic_type is not EpistemicType.SIMULATED:
                raise ValueError(
                    f"simulation reference is not a registered simulation artifact: {identifier}"
                )
            return EvidenceObject(
                reference=ref,
                namespace=namespace,
                value=event,
                epistemic_type=epistemic_type,
            )
        raise ValueError(f"unsupported evidence reference namespace: {namespace}")

    @staticmethod
    def _event_epistemic_type(event: Event) -> EpistemicType | None:
        value = event.metadata.get("epistemic_type")
        if value is None:
            if event.type.startswith("simulation."):
                return EpistemicType.SIMULATED
            return None
        try:
            return EpistemicType(str(value))
        except ValueError as error:
            raise ValueError(
                f"canonical event has invalid epistemic provenance: {event.id}"
            ) from error

    @staticmethod
    def _value_key(value: JSONScalar) -> tuple[str, str]:
        return (type(value).__name__, repr(value))

    @staticmethod
    def _validate_query_times(valid_at: datetime, known_at: datetime) -> None:
        if valid_at.tzinfo is None or known_at.tzinfo is None:
            raise ValueError("memory query times must be timezone-aware")

    @staticmethod
    def _contradiction_from_detection(event: Event) -> MemoryContradiction:
        if event.subject is None:
            raise ValueError("contradiction event requires a subject")
        refs = cast(list[object], event.payload["assertion_refs"])
        if len(refs) != 2:
            raise ValueError("contradiction event requires exactly two assertion refs")
        detected_at = parse_datetime(cast(str, event.payload["detected_at"]))
        if detected_at is None or detected_at != event.timestamp:
            raise ValueError("contradiction detection timestamp is inconsistent")
        contradiction = MemoryContradiction.detect(
            assertion_refs=(str(refs[0]), str(refs[1])),
            subject=str(event.payload["subject"]),
            predicate=str(event.payload["predicate"]),
            detected_at=detected_at,
        )
        if event.subject != contradiction.subject:
            raise ValueError("contradiction event subject is inconsistent")
        if str(event.payload["contradiction_id"]) != contradiction.contradiction_id:
            raise ValueError("contradiction id does not match its assertions")
        return contradiction
