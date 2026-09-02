"""Pure deterministic policy for governed scarce-cognition allocation."""

from __future__ import annotations

from datetime import datetime

from .models import (
    STABLE_RECONSIDERATION_ALLOCATOR_ID,
    STABLE_RECONSIDERATION_ALLOCATOR_VERSION,
    AllocationLabel,
    HardGateOutcome,
    ReconsiderationAllocation,
    ReconsiderationCandidate,
    ReconsiderationDecision,
    ReconsiderationPolicySnapshot,
    ReconsiderationScanRequest,
    ScarceCognitionCostSnapshot,
)


def ensure_allocator_supported(policy: ReconsiderationPolicySnapshot) -> None:
    if (policy.allocator_id, policy.allocator_version) != (
        STABLE_RECONSIDERATION_ALLOCATOR_ID,
        STABLE_RECONSIDERATION_ALLOCATOR_VERSION,
    ):
        raise ValueError(
            "unsupported reconsideration allocator: "
            f"{policy.allocator_id} v{policy.allocator_version}"
        )


def allocate_reconsideration(
    *,
    scan: ReconsiderationScanRequest,
    policy: ReconsiderationPolicySnapshot,
    candidates: tuple[ReconsiderationCandidate, ...],
    derived_information_id: str,
    foreground_demand_refs: tuple[str, ...],
    allocated_at: datetime,
) -> ReconsiderationAllocation:
    """Allocate a finite portfolio with an immutable deterministic v1 policy."""

    ensure_allocator_supported(policy)
    if allocated_at.tzinfo is None:
        raise ValueError("reconsideration allocation time must be timezone-aware")
    if scan.policy_id != policy.policy_id:
        raise ValueError("reconsideration scan does not pin the supplied policy")
    if not candidates:
        raise ValueError("reconsideration allocation requires candidates")
    if {value.candidate_id for value in candidates} != {
        value.candidate_id for value in scan.candidate_inputs
    }:
        raise ValueError("reconsideration candidates differ from the scan portfolio")
    if len({value.candidate_id for value in candidates}) != len(candidates):
        raise ValueError("reconsideration candidates must be unique")

    terms = {value.candidate_id: _terms(value, policy, allocated_at) for value in candidates}
    ranked = sorted(
        candidates,
        key=lambda value: (
            -terms[value.candidate_id][2],
            -value.features.opportunity_window,
            -value.features.meaningful_new_evidence,
            value.candidate_id,
        ),
    )
    consumed = ScarceCognitionCostSnapshot()
    selected_count = 0
    decisions: list[ReconsiderationDecision] = []
    foreground_clear = not foreground_demand_refs
    for candidate in ranked:
        benefit, cost, net_voc, features_current = terms[candidate.candidate_id]
        gates = (
            HardGateOutcome(
                "current_basis",
                candidate.features.current_basis_validity > 0.0,
                "current cognitive basis is valid"
                if candidate.features.current_basis_validity > 0.0
                else "current cognitive basis is invalid",
            ),
            HardGateOutcome(
                "critical_features",
                candidate.features.critical_features_known,
                "critical estimates are explicit and provenance-bearing"
                if candidate.features.critical_features_known
                else "one or more critical estimates are unknown",
            ),
            HardGateOutcome(
                "feature_freshness",
                features_current,
                "all estimate evidence is temporally valid"
                if features_current
                else "one or more estimates are stale",
            ),
            HardGateOutcome(
                "foreground_preemption",
                foreground_clear,
                "no foreground demand is pinned by the scan"
                if foreground_clear
                else "foreground demand preempts reconsideration",
            ),
        )
        failed = next((gate for gate in gates if not gate.passed), None)
        if failed is not None:
            label = (
                AllocationLabel.DEFERRED_BY_CONSTRAINT
                if failed.gate == "foreground_preemption"
                else AllocationLabel.SUPPRESSED
            )
            decisions.append(
                ReconsiderationDecision(
                    candidate.candidate_id,
                    label,
                    benefit,
                    cost,
                    net_voc,
                    gates,
                    failed.reason,
                    failed.gate,
                )
            )
            continue
        if net_voc <= policy.minimum_net_voc:
            decisions.append(
                ReconsiderationDecision(
                    candidate.candidate_id,
                    AllocationLabel.SUPPRESSED,
                    benefit,
                    cost,
                    net_voc,
                    gates,
                    "NetVOC is not positive under the pinned policy",
                    "minimum_net_voc",
                )
            )
            continue
        proposed = consumed.plus(candidate.costs)
        aggregate_interruption_exceeded = (
            proposed.interruption_units > scan.maximum_interruption_units + 1e-12
        )
        if (
            selected_count >= scan.budget.max_candidates
            or not proposed.fits_within(scan.budget.ceiling)
            or aggregate_interruption_exceeded
        ):
            binding_constraint = (
                "maximum_interruption_units"
                if aggregate_interruption_exceeded
                else _binding_budget_dimension(
                    candidate.costs,
                    consumed,
                    scan.budget.ceiling,
                    selected_count,
                    scan.budget.max_candidates,
                )
            )
            decisions.append(
                ReconsiderationDecision(
                    candidate.candidate_id,
                    AllocationLabel.DEFERRED_BY_CONSTRAINT,
                    benefit,
                    cost,
                    net_voc,
                    gates,
                    "finite scarce-cognition budget is exhausted",
                    binding_constraint,
                )
            )
            continue
        consumed = proposed
        selected_count += 1
        decisions.append(
            ReconsiderationDecision(
                candidate.candidate_id,
                AllocationLabel.SELECTED,
                benefit,
                cost,
                net_voc,
                gates,
                "positive NetVOC fits every hard scarce-cognition ceiling",
                None,
            )
        )
    return ReconsiderationAllocation.create(
        derived_information_id=derived_information_id,
        scan_request_id=scan.request_id,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        budget=scan.budget,
        decisions=tuple(decisions),
        consumed_candidates=selected_count,
        consumed=consumed,
        remaining=scan.budget.ceiling.minus(consumed),
        foreground_demand_refs=foreground_demand_refs,
        allocated_at=allocated_at,
    )


def _terms(
    candidate: ReconsiderationCandidate,
    policy: ReconsiderationPolicySnapshot,
    at: datetime,
) -> tuple[float, float, float, bool]:
    features = candidate.features
    estimates = {
        "value_alignment_estimate": features.value_alignment_estimate,
        "expected_outcome_value": features.expected_outcome_value,
        "motivation_estimate": features.motivation_estimate,
    }
    feature_values = {
        "unresolvedness": features.unresolvedness,
        "evidence_freshness": features.evidence_freshness,
        "meaningful_new_evidence": features.meaningful_new_evidence,
        "opportunity_window": features.opportunity_window,
        "current_basis_validity": features.current_basis_validity,
        **{name: value.value if value is not None else 0.0 for name, value in estimates.items()},
    }
    benefit = round(
        sum(feature_values[name] * policy.feature_weights[name] for name in feature_values),
        12,
    )
    cost = round(
        sum(
            getattr(candidate.costs, name) * policy.cost_weights[name]
            for name in candidate.costs.__dataclass_fields__
        ),
        12,
    )
    current = all(value.valid_until > at for value in estimates.values() if value is not None)
    return benefit, cost, round(benefit - cost, 12), current


def _binding_budget_dimension(
    candidate: ScarceCognitionCostSnapshot,
    consumed: ScarceCognitionCostSnapshot,
    ceiling: ScarceCognitionCostSnapshot,
    selected_count: int,
    max_candidates: int,
) -> str:
    if selected_count >= max_candidates:
        return "max_candidates"
    proposed = consumed.plus(candidate)
    for name in candidate.__dataclass_fields__:
        if getattr(proposed, name) > getattr(ceiling, name) + 1e-12:
            return name
    return "scarce_cognition_budget"
