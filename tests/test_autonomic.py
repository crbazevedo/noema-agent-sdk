from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

from noema import (
    AutonomicRule,
    ComparisonOperator,
    EvaluationEpoch,
    Event,
    InhibitionMode,
    InMemoryEventStore,
    PredicateClause,
    PredicateSpec,
    RuleCell,
    RuleFamily,
    RuleRegistry,
    SalienceDisposition,
    SalienceResolver,
    ScoringFeature,
    ScoringSpec,
    Signal,
    SignalRole,
    SignalTemplate,
    TemporalSpec,
    ValueRef,
    ValueSource,
)
from noema.autonomic import canonical_bytes

START = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def event_ref(key: str) -> ValueRef:
    return ValueRef(ValueSource.EVENT, key)


def fact_ref(key: str) -> ValueRef:
    return ValueRef(ValueSource.FACT, key)


def clause(
    ref: ValueRef,
    value: str | int | float | bool | None,
    operator: ComparisonOperator = ComparisonOperator.EQUALS,
) -> PredicateClause:
    return PredicateClause(ref, operator, value)


def pin_rules(*rules: AutonomicRule) -> EvaluationEpoch:
    registry = RuleRegistry()
    for index, rule in enumerate(rules):
        registration = rule.to_event(
            source="test",
            timestamp=START,
            event_id=f"rule-registration-{index}",
        ).with_sequence(index + 1)
        registry.apply(registration)
    cursor = len(rules)
    ruleset = registry.snapshot(through_sequence=cursor)
    return EvaluationEpoch.open(ruleset, started_at=START, event_log_cursor=cursor)


class AutonomicRuleContractTests(unittest.TestCase):
    def test_rule_versions_and_pinned_rulesets_are_immutable(self) -> None:
        first = AutonomicRule(
            rule_id="attention.nonurgent",
            version=1,
            purpose="Recognize a routine interruption",
            family=RuleFamily.PREDICATE,
            trigger="external.email.received",
            spec=PredicateSpec((clause(event_ref("payload.urgent"), False),)),
            output=SignalTemplate("communication.notification", salience=0.5),
        )
        registry = RuleRegistry()
        registry.apply(first.to_event(source="test", timestamp=START).with_sequence(1))
        pinned = registry.snapshot(through_sequence=1)
        epoch = EvaluationEpoch.open(pinned, started_at=START, event_log_cursor=1)

        second = AutonomicRule(
            rule_id=first.rule_id,
            version=2,
            purpose=first.purpose,
            family=first.family,
            trigger=first.trigger,
            spec=first.spec,
            output=first.output,
        )
        registry.apply(
            second.to_event(source="test", timestamp=START + timedelta(hours=1)).with_sequence(2)
        )

        historical = registry.snapshot(through_sequence=1)

        self.assertEqual(epoch.ruleset.rule_refs, ("attention.nonurgent@1",))
        self.assertEqual(historical.snapshot_id, pinned.snapshot_id)
        self.assertEqual(historical.digest, pinned.digest)
        self.assertFalse(hasattr(pinned, "pinned_at"))
        with self.assertRaisesRegex(ValueError, "derived from its content"):
            replace(pinned, snapshot_id="caller-chosen")
        self.assertEqual(
            registry.snapshot(through_sequence=2).rule_refs,
            ("attention.nonurgent@2",),
        )
        self.assertEqual(
            registry.snapshot(through_sequence=1).rule_refs,
            ("attention.nonurgent@1",),
        )
        with self.assertRaisesRegex(ValueError, "multiple versions"):
            registry.snapshot(
                through_sequence=2,
                refs=("attention.nonurgent@1", "attention.nonurgent@2"),
            )
        with self.assertRaises(FrozenInstanceError):
            first.version = 3  # type: ignore[misc]
        with self.assertRaises(ValueError):
            PredicateClause(event_ref("payload.tags"), ComparisonOperator.EQUALS, ["urgent"])
        with self.assertRaises(ValueError):
            ComparisonOperator("in")
        with self.assertRaisesRegex(ValueError, "canonical sequence"):
            RuleRegistry().apply(first.to_event(source="test", timestamp=START))

    def test_rule_family_must_match_its_typed_spec(self) -> None:
        with self.assertRaisesRegex(ValueError, "wrong typed specification"):
            AutonomicRule(
                rule_id="invalid",
                version=1,
                purpose="Reject an untyped family mismatch",
                family=RuleFamily.TEMPORAL,
                trigger="*",
                spec=PredicateSpec((clause(event_ref("payload.ok"), True),)),
                output=SignalTemplate("invalid", salience=0.0),
            )

    def test_salience_inhibition_is_precedence_aware_and_order_independent(self) -> None:
        attention = Signal(
            signal_id="attention",
            kind="attention.request",
            subject="work:1",
            confidence=1.0,
            salience=0.9,
            urgency=0.9,
            expected_value=1.0,
            valid_from=START,
            valid_until=START + timedelta(hours=1),
            evidence_event_ids=("work-event",),
            rule_ref="attention@1",
            evaluation_epoch_id="epoch",
            precedence=10,
            suggested_disposition=SalienceDisposition.WAKE,
        )
        weak_inhibitor = Signal(
            signal_id="weak-inhibitor",
            kind="attention.quiet",
            subject="*",
            confidence=1.0,
            salience=1.0,
            urgency=0.0,
            expected_value=0.0,
            valid_from=START,
            valid_until=START + timedelta(hours=1),
            evidence_event_ids=("quiet-event",),
            rule_ref="quiet@1",
            evaluation_epoch_id="epoch",
            precedence=9,
            role=SignalRole.INHIBITORY,
            inhibits=("attention.*",),
            inhibition_mode=InhibitionMode.HARD,
        )
        resolver = SalienceResolver()
        forward = resolver.resolve((attention, weak_inhibitor), at=START)
        reverse = resolver.resolve((weak_inhibitor, attention), at=START)
        deduplicated = resolver.resolve((attention, attention, weak_inhibitor), at=START)
        self.assertEqual(forward[0].disposition, SalienceDisposition.WAKE)
        self.assertEqual(forward[0].to_dict(), reverse[0].to_dict())
        self.assertEqual(forward[0].to_dict(), deduplicated[0].to_dict())

        graded_inhibitor = Signal(
            signal_id="graded-inhibitor",
            kind=weak_inhibitor.kind,
            subject="*",
            confidence=1.0,
            salience=1.0,
            urgency=0.0,
            expected_value=0.0,
            valid_from=START,
            valid_until=START + timedelta(hours=1),
            evidence_event_ids=("quiet-event",),
            rule_ref="quiet@graded",
            evaluation_epoch_id="epoch",
            precedence=10,
            role=SignalRole.INHIBITORY,
            inhibits=("attention.*",),
            inhibition_mode=InhibitionMode.MODULATE,
            modulation_strength=0.5,
        )
        graded = resolver.resolve((attention, graded_inhibitor), at=START)
        self.assertEqual(graded[0].disposition, SalienceDisposition.REMEMBER)
        self.assertLess(graded[0].score, forward[0].score)
        self.assertEqual(graded[0].modulated_by, ("graded-inhibitor",))

        strong_inhibitor = Signal(
            signal_id="strong-inhibitor",
            kind=weak_inhibitor.kind,
            subject="*",
            confidence=0.01,
            salience=0.01,
            urgency=0.0,
            expected_value=0.0,
            valid_from=START,
            valid_until=START + timedelta(hours=1),
            evidence_event_ids=("quiet-event",),
            rule_ref="quiet@2",
            evaluation_epoch_id="epoch",
            precedence=10,
            role=SignalRole.INHIBITORY,
            inhibits=("attention.*",),
            inhibition_mode=InhibitionMode.HARD,
        )
        suppressed = resolver.resolve((attention, strong_inhibitor), at=START)
        self.assertEqual(suppressed[0].disposition, SalienceDisposition.SUPPRESS)


class AutonomicProjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_registry_and_trace_rebuild_from_canonical_events(self) -> None:
        rule = AutonomicRule(
            rule_id="projection.ready",
            version=1,
            purpose="Prove the registry is only a projection",
            family=RuleFamily.PREDICATE,
            trigger="work.ready",
            spec=PredicateSpec((clause(event_ref("payload.ready"), True),)),
            output=SignalTemplate("work.ready", salience=0.8),
        )
        store = InMemoryEventStore()
        await store.append(rule.to_event(source="test", timestamp=START))
        registry = RuleRegistry()
        registry.rebuild(await store.read())
        epoch = EvaluationEpoch.open(
            registry.snapshot(through_sequence=1),
            started_at=START,
            event_log_cursor=1,
        )
        await store.append(epoch.ruleset.to_event(source="autonomic:projection", timestamp=START))
        await store.append(epoch.to_event(source="autonomic:projection"))
        trigger = Event(
            "work.ready",
            "test",
            {"ready": True},
            subject="work:1",
            id="projection-event",
            timestamp=START,
        )
        trace = (await RuleCell("projection").replay(epoch, (trigger,)))[0]
        stored_trace = await store.append(trace.to_event(source="autonomic:projection"))

        self.assertEqual(registry.rules, (rule,))
        self.assertEqual(stored_trace.type, "rule.evaluation_traced")
        self.assertEqual(stored_trace.payload["trace_id"], trace.trace_id)
        self.assertEqual(
            [event.type for event in await store.read()][1:3],
            ["rule.ruleset_materialized", "rule.evaluation_epoch_started"],
        )


class AutonomicShadowScenarioTests(unittest.IsolatedAsyncioTestCase):
    async def test_deep_work_modulates_nonurgent_notification_without_wake(self) -> None:
        email = AutonomicRule(
            rule_id="email.nonurgent",
            version=1,
            purpose="Retain a nonurgent email as a possible notification",
            family=RuleFamily.PREDICATE,
            trigger="external.email.received",
            spec=PredicateSpec((clause(event_ref("payload.urgent"), False),)),
            output=SignalTemplate(
                "communication.notification",
                salience=0.65,
                suggested_disposition=SalienceDisposition.WAKE,
            ),
            threshold=1.0,
        )
        deep_work = AutonomicRule(
            rule_id="attention.deep_work",
            version=1,
            purpose="Protect a probable deep-work interval",
            family=RuleFamily.SCORING,
            trigger="external.email.received",
            spec=ScoringSpec(
                (
                    ScoringFeature("ide", clause(fact_ref("foreground_app"), "IDE"), 0.34),
                    ScoringFeature(
                        "keyboard",
                        clause(
                            fact_ref("keyboard_activity"),
                            0.8,
                            ComparisonOperator.GREATER_OR_EQUAL,
                        ),
                        0.33,
                    ),
                    ScoringFeature(
                        "calendar",
                        clause(fact_ref("calendar_clear"), True),
                        0.33,
                    ),
                )
            ),
            output=SignalTemplate(
                "attention.deep_work",
                salience=0.95,
                role=SignalRole.INHIBITORY,
                inhibits=("communication.notification",),
                inhibition_mode=InhibitionMode.MODULATE,
                modulation_strength=0.95,
                subject="*",
            ),
            threshold=0.9,
            precedence=100,
        )
        epoch = pin_rules(email, deep_work)
        events = (
            Event(
                "fact.observed",
                "desktop",
                {"key": "foreground_app", "value": "IDE"},
                id="fact-app",
                timestamp=START,
            ),
            Event(
                "fact.observed",
                "desktop",
                {"key": "keyboard_activity", "value": 0.92},
                id="fact-keyboard",
                timestamp=START + timedelta(seconds=1),
            ),
            Event(
                "fact.observed",
                "calendar",
                {"key": "calendar_clear", "value": True},
                id="fact-calendar",
                timestamp=START + timedelta(seconds=2),
            ),
            Event(
                "external.email.received",
                "mail",
                {"urgent": False},
                subject="email:1",
                id="email-1",
                timestamp=START + timedelta(seconds=3),
            ),
        )
        traces = await RuleCell("attention").replay(epoch, events)
        signals = tuple(
            trace.signal_would_emit for trace in traces if trace.signal_would_emit is not None
        )
        decisions = SalienceResolver().resolve(signals, at=events[-1].timestamp)

        self.assertEqual(len(signals), 2)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].disposition, SalienceDisposition.DEFER)
        self.assertNotIn(SalienceDisposition.WAKE, {item.disposition for item in decisions})
        self.assertFalse(decisions[0].inhibited_by)
        self.assertTrue(decisions[0].modulated_by)

    async def test_opportunity_signals_aggregate_into_compact_wake_packet(self) -> None:
        event_types = (
            "code.pr.ready",
            "code.ci.green",
            "code.approval.received",
            "code.merge_window.expiring",
        )
        rules = tuple(
            AutonomicRule(
                rule_id=f"opportunity.{event_type}",
                version=1,
                purpose=f"Recognize {event_type}",
                family=RuleFamily.PREDICATE,
                trigger=event_type,
                spec=PredicateSpec((clause(event_ref("payload.ready"), True),)),
                output=SignalTemplate(
                    f"opportunity.{event_type}",
                    salience=0.3,
                    urgency=0.8 if "expiring" in event_type else 0.2,
                    expected_value=1.0,
                    suggested_disposition=SalienceDisposition.WAKE,
                ),
            )
            for event_type in event_types
        )
        events = tuple(
            Event(
                event_type,
                "code-host",
                {"ready": True},
                subject="pr:42",
                id=f"opportunity-{index}",
                timestamp=START + timedelta(minutes=index),
            )
            for index, event_type in enumerate(event_types)
        )
        epoch = pin_rules(*rules)
        traces = await RuleCell("code-host", subscriptions=("code.*",)).replay(epoch, events)
        signals = tuple(
            trace.signal_would_emit for trace in traces if trace.signal_would_emit is not None
        )
        decisions = SalienceResolver().resolve(signals, at=events[-1].timestamp)

        self.assertEqual(len(signals), 4)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].disposition, SalienceDisposition.WAKE)
        self.assertEqual(decisions[0].subject, "pr:42")
        self.assertEqual(decisions[0].evidence_event_ids, tuple(event.id for event in events))

    async def test_stale_delegation_wakes_only_when_cheap_progress_check_fails(self) -> None:
        stale = AutonomicRule(
            rule_id="coordination.delegation_stale",
            version=1,
            purpose="Escalate an accepted delegation with no recent progress",
            family=RuleFamily.TEMPORAL,
            trigger="clock.tick",
            spec=TemporalSpec(
                anchor_event_type="delegation.accepted",
                min_elapsed_seconds=4 * 60 * 60,
                reset_event_types=("delegation.progress", "delegation.completed"),
                current_conditions=(
                    clause(
                        event_ref("payload.deadline_seconds"),
                        3600,
                        ComparisonOperator.LESS_OR_EQUAL,
                    ),
                ),
            ),
            output=SignalTemplate(
                "coordination.delegation_stale",
                salience=0.9,
                urgency=0.85,
                suggested_disposition=SalienceDisposition.WAKE,
            ),
        )
        epoch = pin_rules(stale)
        accepted = Event(
            "delegation.accepted",
            "agent:delegate",
            subject="delegation:7",
            id="delegation-accepted",
            timestamp=START,
        )
        tick = Event(
            "clock.tick",
            "scheduler",
            {"deadline_seconds": 1800},
            subject="delegation:7",
            id="delegation-tick",
            timestamp=START + timedelta(hours=4, seconds=1),
        )
        cell = RuleCell("coordination")
        unresolved = await cell.replay(epoch, (accepted, tick))
        unresolved_signals = tuple(
            trace.signal_would_emit for trace in unresolved if trace.signal_would_emit is not None
        )
        decisions = SalienceResolver().resolve(unresolved_signals, at=tick.timestamp)
        self.assertEqual(decisions[0].disposition, SalienceDisposition.WAKE)

        progress = Event(
            "delegation.progress",
            "agent:delegate",
            subject="delegation:7",
            id="delegation-progress",
            timestamp=START + timedelta(hours=2),
        )
        resolved = await cell.replay(epoch, (accepted, progress, tick))
        self.assertFalse(any(trace.signal_would_emit is not None for trace in resolved))

    async def test_same_replay_and_ruleset_are_byte_equivalent(self) -> None:
        rule = AutonomicRule(
            rule_id="replay.ready",
            version=1,
            purpose="Prove deterministic shadow semantics",
            family=RuleFamily.PREDICATE,
            trigger="work.ready",
            spec=PredicateSpec((clause(event_ref("payload.ready"), True),)),
            output=SignalTemplate(
                "work.ready",
                salience=0.8,
                suggested_disposition=SalienceDisposition.WAKE,
            ),
        )
        epoch = pin_rules(rule)
        events = (
            Event(
                "work.ready",
                "test",
                {"ready": True},
                subject="work:1",
                id="work-ready",
                timestamp=START,
            ),
        )
        cell = RuleCell("replay")
        first = await cell.replay(epoch, events)
        second = await cell.replay(epoch, events)

        self.assertEqual(
            b"\n".join(trace.semantic_bytes() for trace in first),
            b"\n".join(trace.semantic_bytes() for trace in second),
        )
        first_signals = [
            trace.signal_would_emit.to_dict()
            for trace in first
            if trace.signal_would_emit is not None
        ]
        second_signals = [
            trace.signal_would_emit.to_dict()
            for trace in second
            if trace.signal_would_emit is not None
        ]
        self.assertEqual(
            canonical_bytes({"signals": first_signals}),
            canonical_bytes({"signals": second_signals}),
        )
