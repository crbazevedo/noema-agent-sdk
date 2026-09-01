"""Replayable endogenous lifecycle, agenda, and budget projection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import TypeVar, cast

from ..events import Event
from ..intent.projection import StrategicProjection
from ..situation import GoalStatus
from ..types import JSONObject, parse_datetime
from .models import (
    AGENDA_SELECTED_EVENT,
    CALIBRATION_EXCHANGE_RECORDED_EVENT,
    COGNITION_SCAN_REQUESTED_EVENT,
    DREAM_EPOCH_EXPIRED_EVENT,
    DREAM_EPOCH_PREEMPTED_EVENT,
    DREAM_EPOCH_STARTED_EVENT,
    INQUIRY_RECORDED_EVENT,
    INTRINSIC_ACTIVITY_RECORDED_EVENT,
    POLICY_SNAPSHOT_RECORDED_EVENT,
    VOC_EVALUATED_EVENT,
    CalibrationExchange,
    CognitionScanRequest,
    DreamEpoch,
    DreamEpochStatus,
    EndogenousPolicySnapshot,
    GoverningIntentRef,
    Inquiry,
    IntrinsicActivity,
    IntrinsicAgendaSelection,
    ValueOfCognitionEstimate,
)
from .policy import evaluate_value_of_cognition, select_intrinsic_agenda

T = TypeVar("T")
K = TypeVar("K")


class EndogenousProjection:
    """Rebuild every durable endogenous decision from one canonical history."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._events: dict[str, Event] = {}
        self._last_sequence = 0
        self._strategy = StrategicProjection()
        self._policies: dict[str, EndogenousPolicySnapshot] = {}
        self._requests: dict[str, CognitionScanRequest] = {}
        self._epochs: dict[str, DreamEpoch] = {}
        self._epoch_by_trigger: dict[str, str] = {}
        self._epoch_status: dict[str, DreamEpochStatus] = {}
        self._inquiries: dict[str, Inquiry] = {}
        self._activities: dict[str, IntrinsicActivity] = {}
        self._epoch_activities: dict[str, set[str]] = {}
        self._estimates: dict[tuple[str, str], ValueOfCognitionEstimate] = {}
        self._selections: dict[str, IntrinsicAgendaSelection] = {}
        self._calibrations: dict[str, CalibrationExchange] = {}

    @property
    def event_cursor(self) -> int:
        return self._last_sequence

    @property
    def strategy(self) -> StrategicProjection:
        return self._strategy

    @property
    def policies(self) -> tuple[EndogenousPolicySnapshot, ...]:
        return tuple(self._policies[key] for key in sorted(self._policies))

    @property
    def requests(self) -> tuple[CognitionScanRequest, ...]:
        return tuple(self._requests[key] for key in sorted(self._requests))

    @property
    def epochs(self) -> tuple[DreamEpoch, ...]:
        return tuple(
            sorted(
                self._epochs.values(),
                key=lambda value: (value.started_at, value.epoch_id),
            )
        )

    @property
    def inquiries(self) -> tuple[Inquiry, ...]:
        return tuple(self._inquiries[key] for key in sorted(self._inquiries))

    @property
    def activities(self) -> tuple[IntrinsicActivity, ...]:
        return tuple(self._activities[key] for key in sorted(self._activities))

    @property
    def estimates(self) -> tuple[ValueOfCognitionEstimate, ...]:
        return tuple(self._estimates[key] for key in sorted(self._estimates))

    @property
    def selections(self) -> tuple[IntrinsicAgendaSelection, ...]:
        return tuple(self._selections[key] for key in sorted(self._selections))

    @property
    def calibrations(self) -> tuple[CalibrationExchange, ...]:
        return tuple(self._calibrations[key] for key in sorted(self._calibrations))

    @property
    def active_epochs(self) -> tuple[DreamEpoch, ...]:
        return tuple(
            value
            for value in self.epochs
            if self._epoch_status[value.epoch_id] is DreamEpochStatus.ACTIVE
        )

    def has_event(self, event_id: str) -> bool:
        return event_id in self._events

    def event(self, event_id: str) -> Event | None:
        return self._events.get(event_id)

    def policy(self, policy_id: str) -> EndogenousPolicySnapshot | None:
        return self._policies.get(policy_id)

    def request(self, request_id: str) -> CognitionScanRequest | None:
        return self._requests.get(request_id)

    def epoch(self, epoch_id: str) -> DreamEpoch | None:
        return self._epochs.get(epoch_id)

    def epoch_for_trigger(self, trigger_event_id: str) -> DreamEpoch | None:
        epoch_id = self._epoch_by_trigger.get(trigger_event_id)
        return self._epochs.get(epoch_id) if epoch_id is not None else None

    def epoch_status(self, epoch_id: str) -> DreamEpochStatus:
        if epoch_id not in self._epochs:
            raise KeyError(f"unknown dream epoch: {epoch_id}")
        return self._epoch_status[epoch_id]

    def inquiry(self, inquiry_id: str) -> Inquiry | None:
        return self._inquiries.get(inquiry_id)

    def activity(self, activity_id: str) -> IntrinsicActivity | None:
        return self._activities.get(activity_id)

    def activities_for_epoch(self, epoch_id: str) -> tuple[IntrinsicActivity, ...]:
        return tuple(
            self._activities[value] for value in sorted(self._epoch_activities.get(epoch_id, ()))
        )

    def estimates_for_epoch(self, epoch_id: str) -> tuple[ValueOfCognitionEstimate, ...]:
        return tuple(
            value
            for (known_epoch_id, _activity_id), value in sorted(self._estimates.items())
            if known_epoch_id == epoch_id
        )

    def selection(self, epoch_id: str) -> IntrinsicAgendaSelection | None:
        return self._selections.get(epoch_id)

    def intent_refs_are_current(self, refs: tuple[GoverningIntentRef, ...]) -> bool:
        return bool(refs) and all(
            (revision := self._strategy.goal_revision(ref.goal_revision_id)) is not None
            and revision.goal_id == ref.goal_id
            and self._strategy.current_goal_revision(ref.goal_id) == revision
            and revision.status in {GoalStatus.ACTIVE, GoalStatus.BLOCKED}
            for ref in refs
        )

    def eligible_inquiries(self, *, at: datetime) -> tuple[Inquiry, ...]:
        return tuple(
            value
            for value in self.inquiries
            if value.expires_at > at and self.intent_refs_are_current(value.governing_intent_refs)
        )

    def apply(self, event: Event) -> bool:
        existing = self._events.get(event.id)
        if existing is not None:
            if existing != event:
                raise ValueError(f"conflicting canonical endogenous event identity: {event.id}")
            return False
        if event.sequence is None:
            raise ValueError("endogenous projection requires canonical sequenced events")
        if event.sequence <= self._last_sequence:
            raise ValueError("endogenous projection events must be in canonical sequence order")

        handled = self._apply_event(event)
        self._strategy.apply(event)
        self._events[event.id] = event
        self._last_sequence = event.sequence
        return handled

    def rebuild(
        self,
        events: Iterable[Event],
        *,
        through_sequence: int | None = None,
    ) -> None:
        self._reset()
        for event in events:
            if through_sequence is not None and (event.sequence or 0) > through_sequence:
                continue
            self.apply(event)

    def _apply_event(self, event: Event) -> bool:
        if event.type == POLICY_SNAPSHOT_RECORDED_EVENT:
            policy = EndogenousPolicySnapshot.from_dict(event.payload)
            self._validate_envelope(
                event,
                expected_id=f"endogenous-policy-recorded:{policy.policy_id}",
                subject=policy.policy_id,
            )
            self._record_immutable(self._policies, policy.policy_id, policy, "policy")
            return True
        if event.type == COGNITION_SCAN_REQUESTED_EVENT:
            request = CognitionScanRequest.from_dict(event.payload)
            self._validate_envelope(
                event,
                expected_id=f"cognition-scan-requested:{request.request_id}",
                subject=request.request_id,
                timestamp=request.requested_at,
            )
            if request.policy_id not in self._policies:
                raise ValueError("cognition scan references an unknown policy snapshot")
            self._record_immutable(self._requests, request.request_id, request, "scan request")
            return True
        if event.type == CALIBRATION_EXCHANGE_RECORDED_EVENT:
            self._validate_exact_head_receipt(event)
            exchange = CalibrationExchange.from_dict(event.payload)
            self._validate_envelope(
                event,
                expected_id=f"calibration-exchange-recorded:{exchange.exchange_id}",
                subject=exchange.exchange_id,
                timestamp=exchange.recorded_at,
            )
            self._require_current_intent(exchange.governing_intent_refs)
            self._require_evidence(exchange.local_evidence_refs)
            self._require_evidence(exchange.peer_evidence_refs)
            self._require_evidence(
                (exchange.request_provenance_ref, exchange.response_provenance_ref)
            )
            self._record_immutable(
                self._calibrations,
                exchange.exchange_id,
                exchange,
                "calibration exchange",
            )
            return True
        if event.type == DREAM_EPOCH_STARTED_EVENT:
            self._validate_exact_head_receipt(event)
            epoch = DreamEpoch.from_dict(event.payload)
            self._validate_envelope(
                event,
                expected_id=f"dream-epoch-started:{epoch.epoch_id}",
                subject=epoch.epoch_id,
                timestamp=epoch.started_at,
            )
            request_event = self._events.get(epoch.trigger_event_id)
            if request_event is None or request_event.type != COGNITION_SCAN_REQUESTED_EVENT:
                raise ValueError("dream epoch trigger is not a canonical cognition scan")
            request = CognitionScanRequest.from_dict(request_event.payload)
            if request_event.sequence != epoch.event_log_cursor:
                raise ValueError("dream epoch cursor must pin its scan request")
            if (
                request.policy_id != epoch.policy_id
                or request.budget != epoch.budget
                or request.requested_at != epoch.started_at
                or request.expires_at != epoch.expires_at
            ):
                raise ValueError("dream epoch differs from its canonical scan request")
            epoch_policy = self._policies.get(epoch.policy_id)
            if epoch_policy is None or epoch_policy.version != epoch.policy_version:
                raise ValueError("dream epoch references an unknown policy version")
            if self._last_sequence != epoch.event_log_cursor:
                raise ValueError("dream epoch must start at the exact pinned event head")
            existing_epoch = self._epoch_by_trigger.get(epoch.trigger_event_id)
            if existing_epoch is not None and existing_epoch != epoch.epoch_id:
                raise ValueError("one cognition scan cannot start two dream epochs")
            self._record_immutable(self._epochs, epoch.epoch_id, epoch, "dream epoch")
            self._epoch_by_trigger[epoch.trigger_event_id] = epoch.epoch_id
            self._epoch_status[epoch.epoch_id] = DreamEpochStatus.ACTIVE
            self._epoch_activities.setdefault(epoch.epoch_id, set())
            return True
        if event.type == INQUIRY_RECORDED_EVENT:
            self._validate_exact_head_receipt(event)
            epoch_id = str(event.payload["epoch_id"])
            epoch = self._require_active_epoch(epoch_id, at=event.timestamp)
            inquiry = Inquiry.from_dict(cast(Mapping[str, object], event.payload["inquiry"]))
            self._validate_envelope(
                event,
                expected_id=f"inquiry-recorded:{inquiry.inquiry_id}",
                subject=inquiry.inquiry_id,
                timestamp=inquiry.created_at,
            )
            if inquiry.causal_cursor != epoch.event_log_cursor:
                raise ValueError("inquiry does not cite the dream epoch causal cut")
            self._require_current_intent(inquiry.governing_intent_refs)
            self._require_evidence(inquiry.evidence_refs)
            self._record_immutable(self._inquiries, inquiry.inquiry_id, inquiry, "inquiry")
            return True
        if event.type == INTRINSIC_ACTIVITY_RECORDED_EVENT:
            self._validate_exact_head_receipt(event)
            epoch_id = str(event.payload["epoch_id"])
            epoch = self._require_active_epoch(epoch_id, at=event.timestamp)
            activity = IntrinsicActivity.from_dict(
                cast(Mapping[str, object], event.payload["activity"])
            )
            self._validate_envelope(
                event,
                expected_id=f"intrinsic-activity-recorded:{epoch_id}:{activity.activity_id}",
                subject=activity.activity_id,
            )
            known_inquiry = self._inquiries.get(activity.inquiry_id)
            if known_inquiry is None:
                raise ValueError("intrinsic activity references an unknown inquiry")
            if activity.causal_cursor != epoch.event_log_cursor:
                raise ValueError("intrinsic activity does not cite the dream epoch causal cut")
            if (
                known_inquiry.governing_intent_refs != activity.governing_intent_refs
                or known_inquiry.evidence_refs != activity.evidence_refs
            ):
                raise ValueError("intrinsic activity diverges from its inquiry provenance")
            self._require_current_intent(activity.governing_intent_refs)
            self._require_evidence(activity.evidence_refs)
            self._record_immutable(
                self._activities,
                activity.activity_id,
                activity,
                "intrinsic activity",
            )
            self._epoch_activities.setdefault(epoch_id, set()).add(activity.activity_id)
            return True
        if event.type == VOC_EVALUATED_EVENT:
            self._validate_exact_head_receipt(event)
            estimate = ValueOfCognitionEstimate.from_dict(event.payload)
            epoch = self._require_active_epoch(estimate.epoch_id, at=estimate.evaluated_at)
            estimated_activity = self._activities.get(estimate.activity_id)
            estimate_policy = self._policies.get(estimate.policy_id)
            if (
                estimated_activity is None
                or estimate.activity_id not in self._epoch_activities[epoch.epoch_id]
            ):
                raise ValueError("VOC estimate references an unknown epoch activity")
            if estimate_policy is None:
                raise ValueError("VOC estimate references an unknown policy")
            expected_estimate = evaluate_value_of_cognition(
                estimated_activity,
                epoch=epoch,
                policy=estimate_policy,
                evaluated_at=estimate.evaluated_at,
            )
            if estimate != expected_estimate:
                raise ValueError("VOC estimate differs from deterministic policy evaluation")
            self._validate_envelope(
                event,
                expected_id=(f"voc-evaluated:{epoch.epoch_id}:{estimated_activity.activity_id}"),
                subject=estimated_activity.activity_id,
                timestamp=estimate.evaluated_at,
            )
            self._record_immutable(
                self._estimates,
                (epoch.epoch_id, estimated_activity.activity_id),
                estimate,
                "VOC estimate",
            )
            return True
        if event.type == AGENDA_SELECTED_EVENT:
            self._validate_exact_head_receipt(event)
            selection = IntrinsicAgendaSelection.from_dict(event.payload)
            epoch = self._require_active_epoch(selection.epoch_id, at=selection.selected_at)
            if selection.epoch_id in self._selections:
                raise ValueError("a dream epoch cannot spend its budget twice")
            selection_policy = self._policies.get(selection.policy_id)
            if selection_policy is None:
                raise ValueError("intrinsic agenda references an unknown policy")
            activities = self.activities_for_epoch(epoch.epoch_id)
            for activity in activities:
                self._require_current_intent(activity.governing_intent_refs)
            expected_selection = select_intrinsic_agenda(
                epoch=epoch,
                policy=selection_policy,
                activities=activities,
                estimates=self.estimates_for_epoch(epoch.epoch_id),
                selected_at=selection.selected_at,
            )
            if selection != expected_selection:
                raise ValueError("intrinsic agenda differs from deterministic selection")
            self._validate_envelope(
                event,
                expected_id=f"intrinsic-agenda-selected:{selection.selection_id}",
                subject=selection.epoch_id,
                timestamp=selection.selected_at,
            )
            self._selections[selection.epoch_id] = selection
            return True
        if event.type == DREAM_EPOCH_PREEMPTED_EVENT:
            self._validate_exact_head_receipt(event)
            epoch_id = str(event.payload["epoch_id"])
            self._require_active_epoch(epoch_id, at=event.timestamp, allow_expired_time=True)
            foreground_event_id = str(event.payload["foreground_event_id"])
            foreground = self._events.get(foreground_event_id)
            if foreground is None:
                raise ValueError("dream preemption references an unknown foreground event")
            preempted_at = parse_datetime(cast(str, event.payload["preempted_at"]))
            if preempted_at is None or preempted_at != event.timestamp:
                raise ValueError("dream preemption timestamp is inconsistent")
            self._validate_envelope(
                event,
                expected_id=f"dream-epoch-preempted:{epoch_id}:{foreground_event_id}",
                subject=epoch_id,
                timestamp=preempted_at,
            )
            if event.causation_id != foreground_event_id:
                raise ValueError("dream preemption must be caused by foreground demand")
            self._epoch_status[epoch_id] = DreamEpochStatus.PREEMPTED
            return True
        if event.type == DREAM_EPOCH_EXPIRED_EVENT:
            self._validate_exact_head_receipt(event)
            epoch_id = str(event.payload["epoch_id"])
            epoch = self._require_active_epoch(
                epoch_id,
                at=event.timestamp,
                allow_expired_time=True,
            )
            expired_at = parse_datetime(cast(str, event.payload["expired_at"]))
            if expired_at is None or expired_at != event.timestamp:
                raise ValueError("dream expiry timestamp is inconsistent")
            if expired_at < epoch.expires_at:
                raise ValueError("dream epoch cannot expire before its pinned deadline")
            self._validate_envelope(
                event,
                expected_id=f"dream-epoch-expired:{epoch_id}",
                subject=epoch_id,
                timestamp=expired_at,
            )
            self._epoch_status[epoch_id] = DreamEpochStatus.EXPIRED
            return True
        return False

    def _require_active_epoch(
        self,
        epoch_id: str,
        *,
        at: datetime,
        allow_expired_time: bool = False,
    ) -> DreamEpoch:
        epoch = self._epochs.get(epoch_id)
        if epoch is None:
            raise ValueError(f"unknown dream epoch: {epoch_id}")
        if self._epoch_status[epoch_id] is not DreamEpochStatus.ACTIVE:
            raise ValueError("preempted or expired dream epoch cannot consume cognition")
        if not allow_expired_time and at >= epoch.expires_at:
            raise ValueError("expired dream epoch cannot consume cognition")
        return epoch

    def _require_current_intent(self, refs: tuple[GoverningIntentRef, ...]) -> None:
        if not self.intent_refs_are_current(refs):
            raise ValueError("endogenous cognition requires current ACTIVE or BLOCKED intent")

    def _require_evidence(self, refs: tuple[str, ...]) -> None:
        if not refs:
            raise ValueError("endogenous cognition requires canonical evidence")
        for ref in refs:
            if not ref.startswith("event:"):
                raise ValueError(f"unsupported endogenous evidence reference: {ref}")
            event_id = ref.removeprefix("event:")
            if event_id not in self._events:
                raise ValueError(f"unknown endogenous evidence event: {event_id}")

    def _validate_exact_head_receipt(self, event: Event) -> None:
        if event.metadata.get("validated_at_event_cursor") != self._last_sequence:
            raise ValueError("endogenous transition lacks exact-head admission evidence")

    @staticmethod
    def _validate_envelope(
        event: Event,
        *,
        expected_id: str,
        subject: str,
        timestamp: datetime | None = None,
    ) -> None:
        if event.id != expected_id or event.subject != subject:
            raise ValueError("endogenous event envelope is inconsistent")
        if timestamp is not None and event.timestamp != timestamp:
            raise ValueError("endogenous event timestamp is inconsistent")

    @staticmethod
    def _record_immutable(
        values: dict[K, T],
        key: K,
        value: T,
        label: str,
    ) -> None:
        existing = values.get(key)
        if existing is not None and existing != value:
            raise ValueError(f"{label} changed in place: {key}")
        values[key] = value

    def semantic_snapshot(self) -> JSONObject:
        """Return replay-stable semantic state, excluding storage sequence metadata."""

        return {
            "policies": [value.to_dict() for value in self.policies],
            "requests": [value.to_dict() for value in self.requests],
            "epochs": [
                {
                    **value.to_dict(),
                    "status": self._epoch_status[value.epoch_id].value,
                }
                for value in self.epochs
            ],
            "inquiries": [value.to_dict() for value in self.inquiries],
            "activities": [value.to_dict() for value in self.activities],
            "estimates": [value.to_dict() for value in self.estimates],
            "selections": [value.to_dict() for value in self.selections],
            "calibrations": [value.to_dict() for value in self.calibrations],
        }
