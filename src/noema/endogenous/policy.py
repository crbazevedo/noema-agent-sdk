"""Pure deterministic Value-of-Cognition evaluation and agenda selection."""

from __future__ import annotations

from datetime import datetime

from ..types import JSONObject
from .models import (
    ActivityDisposition,
    AgendaDecision,
    CognitiveResourceVector,
    DreamEpoch,
    EndogenousPolicySnapshot,
    IntrinsicActivity,
    IntrinsicAgendaSelection,
    ValueOfCognitionEstimate,
    _canonical_id,
)


def evaluate_value_of_cognition(
    activity: IntrinsicActivity,
    *,
    epoch: DreamEpoch,
    policy: EndogenousPolicySnapshot,
    evaluated_at: datetime,
) -> ValueOfCognitionEstimate:
    """Evaluate one activity with every term explicit and replay-visible."""

    if epoch.policy_id != policy.policy_id or epoch.policy_version != policy.version:
        raise ValueError("dream epoch does not pin the supplied endogenous policy")
    if activity.causal_cursor != epoch.event_log_cursor:
        raise ValueError("intrinsic activity does not belong to the dream epoch causal cut")
    inputs = activity.voc_inputs
    expected_improvement = round(inputs.expected_decision_improvement, 12)
    compute_cost = round(inputs.compute_cost_basis * policy.compute_cost_weight, 12)
    delay_cost = round(inputs.delay_cost_basis * policy.delay_cost_weight, 12)
    attention_cost = round(inputs.attention_cost_basis * policy.attention_cost_weight, 12)
    opportunity_cost = round(
        inputs.opportunity_cost_basis * policy.opportunity_cost_weight,
        12,
    )
    privacy_risk_cost = round(
        inputs.privacy_risk_cost_basis * policy.privacy_risk_cost_weight,
        12,
    )
    net_value = round(
        expected_improvement
        - compute_cost
        - delay_cost
        - attention_cost
        - opportunity_cost
        - privacy_risk_cost,
        12,
    )
    identity: JSONObject = {
        "epoch_id": epoch.epoch_id,
        "activity_id": activity.activity_id,
        "policy_id": policy.policy_id,
        "expected_decision_improvement": expected_improvement,
        "compute_cost": compute_cost,
        "delay_cost": delay_cost,
        "attention_cost": attention_cost,
        "opportunity_cost": opportunity_cost,
        "privacy_risk_cost": privacy_risk_cost,
        "net_value": net_value,
        "evaluated_at": evaluated_at.isoformat(),
    }
    return ValueOfCognitionEstimate(
        estimate_id=_canonical_id("voc-estimate", identity),
        epoch_id=epoch.epoch_id,
        activity_id=activity.activity_id,
        policy_id=policy.policy_id,
        expected_decision_improvement=expected_improvement,
        compute_cost=compute_cost,
        delay_cost=delay_cost,
        attention_cost=attention_cost,
        opportunity_cost=opportunity_cost,
        privacy_risk_cost=privacy_risk_cost,
        net_value=net_value,
        evaluated_at=evaluated_at,
    )


def select_intrinsic_agenda(
    *,
    epoch: DreamEpoch,
    policy: EndogenousPolicySnapshot,
    activities: tuple[IntrinsicActivity, ...],
    estimates: tuple[ValueOfCognitionEstimate, ...],
    selected_at: datetime,
) -> IntrinsicAgendaSelection:
    """Greedily select an audit-stable feasible subset; this is not an optimizer."""

    if selected_at.tzinfo is None:
        raise ValueError("agenda selection time must be timezone-aware")
    if selected_at >= epoch.expires_at:
        raise ValueError("an expired dream epoch cannot select an agenda")
    if epoch.policy_id != policy.policy_id:
        raise ValueError("agenda policy differs from the dream epoch policy")
    by_activity = {value.activity_id: value for value in activities}
    if len(by_activity) != len(activities):
        raise ValueError("intrinsic agenda activities must be unique")
    by_estimate = {value.activity_id: value for value in estimates}
    if set(by_estimate) != set(by_activity):
        raise ValueError("every intrinsic activity requires exactly one VOC estimate")
    if any(
        value.epoch_id != epoch.epoch_id or value.policy_id != policy.policy_id
        for value in estimates
    ):
        raise ValueError("VOC estimates do not belong to the selected epoch and policy")

    ranked = sorted(
        activities,
        key=lambda value: (
            -by_estimate[value.activity_id].net_value,
            -value.urgency,
            -value.confidence,
            value.activity_id,
        ),
    )
    consumed = CognitiveResourceVector()
    decisions: list[AgendaDecision] = []
    threshold = max(0.0, policy.minimum_net_voc)
    for activity in ranked:
        estimate = by_estimate[activity.activity_id]
        if activity.expires_at <= selected_at:
            decisions.append(
                AgendaDecision(
                    activity.activity_id,
                    ActivityDisposition.SUPPRESSED,
                    "activity expired before agenda selection",
                )
            )
            continue
        if estimate.net_value <= threshold:
            decisions.append(
                AgendaDecision(
                    activity.activity_id,
                    ActivityDisposition.SUPPRESSED,
                    "NetVOC is not positive under the pinned policy",
                )
            )
            continue
        proposed = consumed.plus(activity.resources)
        if not proposed.fits_within(epoch.budget.ceiling):
            decisions.append(
                AgendaDecision(
                    activity.activity_id,
                    ActivityDisposition.DEFERRED,
                    "finite background cognitive budget is insufficient",
                )
            )
            continue
        consumed = proposed
        decisions.append(
            AgendaDecision(
                activity.activity_id,
                ActivityDisposition.SELECTED,
                "positive NetVOC fits every pinned budget ceiling",
            )
        )
    if not decisions:
        raise ValueError("agenda selection requires at least one evaluated candidate")
    remaining = epoch.budget.ceiling.minus(consumed)
    return IntrinsicAgendaSelection.create(
        epoch_id=epoch.epoch_id,
        policy_id=policy.policy_id,
        decisions=tuple(decisions),
        consumed=consumed,
        remaining=remaining,
        selected_at=selected_at,
    )
