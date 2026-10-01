"""Canonical semantic hashing for Planning Engine v1 inputs."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from .content import plan_content_hash
from .objectives import ObjectivePolicy
from .validation import PlanValidationContext


def _dimension(item):
    return (item.dimension, item.level.value)


def _load(item):
    return (
        item.scope,
        item.subject,
        item.metric,
        item.unit,
        float(item.min_value),
        float(item.max_value),
    )


def _contribution(item):
    return (
        item.obligation_id,
        item.source_capability,
        item.kind.value,
        item.credit_numerator,
        item.credit_denominator,
    )


def semantic_planning_input_payload(
    context: PlanValidationContext,
    objective_policy: ObjectivePolicy,
    affected_from,
    affected_until,
    previous_plan=None,
) -> dict:
    """Return order-independent planning semantics.

    Provenance/source refs are intentionally excluded. They belong in the
    decision trace, not in the semantic identity of an otherwise identical
    planning problem.
    """

    strategy = context.strategy

    max_load_window = max(
        (item.window_days for item in strategy.load_envelope.bounds),
        default=1,
    )
    max_compat_gap = max(
        (item.max_separation_days for item in context.compatibility_policy.rules),
        default=0,
    )
    max_spacing_gap = max(
        (item.desired_min_gap_days for item in objective_policy.spacing_preferences),
        default=0,
    )
    history_required_from = affected_from - timedelta(
        days=max(
            max_load_window - 1,
            max(0, max_compat_gap - 1),
            max(0, max_spacing_gap - 1),
        )
    )
    history_required_through = affected_from - timedelta(days=1)
    future_required_through = affected_until + timedelta(
        days=max(
            max(0, max_compat_gap - 1),
            max(0, max_spacing_gap - 1),
        )
    )

    # Normalize coverage metadata to the evidence horizon that can actually
    # affect this solve. Extra old/future coverage is provenance, not planning
    # semantics. Insufficient coverage remains visible in the normalized range.
    normalized_history_from = max(context.history_from, history_required_from)
    normalized_history_through = min(
        context.history_through,
        history_required_through,
    )
    normalized_future_through = min(
        context.future_context_through,
        future_required_through,
    )
    obligations = [
        {
            "id": item.obligation_id,
            "capability": item.capability,
            "role": item.role,
            "priority": item.priority_tier,
            "min": item.min_exposures,
            "max": item.max_exposures,
            "recipes": sorted(item.recipe_family),
            "valid_from": item.valid_from.isoformat(),
            "valid_until": item.valid_until.isoformat(),
            "progression_axes": sorted(item.progression_axes),
            "partial": sorted(
                (
                    rule.source_capability,
                    rule.credit_numerator,
                    rule.credit_denominator,
                )
                for rule in item.partial_coverage
            ),
            "prefer_character_variation": item.prefer_character_variation,
            "accepted_observed_bases": sorted(
                basis.value for basis in item.accepted_observed_bases
            ),
        }
        for item in strategy.obligations
    ]

    bounds = [
        (
            item.bound_id,
            item.scope,
            item.subject,
            item.metric,
            item.unit,
            item.window_days,
            float(item.max_value),
            item.requires_complete_coverage,
        )
        for item in strategy.load_envelope.bounds
    ]

    catalog = [
        {
            "recipe": item.recipe_id,
            "dose": item.dose_option_id,
            "capabilities": sorted(item.capabilities),
            "components": sorted(
                (component.discipline, component.order)
                for component in item.components
            ),
            "dimensions": sorted(_dimension(value) for value in item.load_dimensions),
            "load": sorted(_load(value) for value in item.quantitative_load),
            "character": item.development_character,
            "planning_priority": item.planning_priority,
        }
        for item in context.catalog_options
    ]

    eligibility = [
        (
            item.recipe_id,
            item.dose_option_id,
            item.capability,
            item.kind.value,
        )
        for item in context.option_eligibility
    ]

    fixed = [
        {
            "id": item.commitment_id,
            "date": item.local_date.isoformat(),
            "dimensions": sorted(_dimension(value) for value in item.load_dimensions),
            "load": sorted(_load(value) for value in item.quantitative_load),
            "order": item.within_day_order,
        }
        for item in context.fixed_commitments
        if affected_from <= item.local_date <= future_required_through
    ]

    compatibility = [
        (
            item.rule_id,
            item.first_dimension,
            item.first_min_level.value,
            item.second_dimension,
            item.second_min_level.value,
            item.min_calendar_separation_days,
            item.first_to_second_days,
            item.second_to_first_days,
            item.same_day_order.value,
        )
        for item in context.compatibility_policy.rules
    ]

    availability = [
        (
            item.local_date.isoformat(),
            item.available,
            item.max_sessions,
            None
            if item.max_duration_minutes is None
            else float(item.max_duration_minutes),
        )
        for item in context.availability
        if affected_from <= item.local_date <= affected_until
    ]

    placement_constraints = [
        (
            item.constraint_id,
            item.local_date.isoformat(),
            item.recipe_id,
            item.dose_option_id,
            item.min_occurrences,
            item.max_occurrences,
            tuple(item.obligation_ids),
        )
        for item in context.placement_constraints
    ]

    observed_credits = [
        (
            item.local_date.isoformat(),
            item.basis.value,
            *_contribution(item.contribution),
        )
        for item in context.observed_obligation_credits
    ]

    observed_load = [
        {
            "id": item.exposure_id,
            "date": item.local_date.isoformat(),
            "dimensions": sorted(_dimension(value) for value in item.load_dimensions),
            "load": sorted(_load(value) for value in item.quantitative_load),
            "order": item.within_day_order,
        }
        for item in context.observed_load_exposures
        if history_required_from <= item.local_date <= affected_until
    ]

    spacing = [
        (
            item.subject_kind.value,
            item.subject,
            item.desired_min_gap_days,
            item.min_level.value,
        )
        for item in objective_policy.spacing_preferences
    ]

    return {
        "affected_from": affected_from.isoformat(),
        "affected_until": affected_until.isoformat(),
        "history_from": normalized_history_from.isoformat(),
        "history_through": normalized_history_through.isoformat(),
        "future_context_through": normalized_future_through.isoformat(),
        "strategy": {
            "revision_id": strategy.revision_id,
            "goal_set_hash": strategy.goal_set_hash,
            "valid_from": strategy.valid_from.isoformat(),
            "valid_until": strategy.valid_until.isoformat(),
            "accepted_by": strategy.accepted_by,
            "obligations": sorted(obligations, key=lambda item: item["id"]),
            "load_envelope": {
                "id": strategy.load_envelope.envelope_id,
                "unknown_policy": strategy.load_envelope.unknown_policy.value,
                "established_baseline_ref": strategy.load_envelope.established_baseline_ref,
                "bounds": sorted(bounds),
            },
        },
        "catalog": sorted(catalog, key=lambda item: (item["recipe"], item["dose"])),
        "eligibility": sorted(eligibility),
        "fixed_commitments": sorted(fixed, key=lambda item: item["id"]),
        "compatibility_policy": {
            "id": context.compatibility_policy.policy_id,
            "rules": sorted(compatibility),
        },
        "availability": sorted(availability),
        "placement_constraints": sorted(placement_constraints),
        "closed_dates": sorted(
            day.isoformat()
            for day in context.closed_dates
            if affected_from <= day <= affected_until
        ),
        "observed_credits": sorted(observed_credits),
        "observed_load": sorted(observed_load, key=lambda item: item["id"]),
        "objective_policy": {
            "schedule": (
                objective_policy.schedule.preferred_active_days,
                objective_policy.schedule.min_active_days,
                objective_policy.schedule.max_active_days,
                objective_policy.schedule.double_sessions.value,
            ),
            "spacing": sorted(spacing),
        },
        "previous_plan_hash": (
            plan_content_hash(previous_plan) if previous_plan is not None else None
        ),
    }


def planning_input_hash(
    context: PlanValidationContext,
    objective_policy: ObjectivePolicy,
    affected_from,
    affected_until,
    previous_plan=None,
) -> str:
    payload = semantic_planning_input_payload(
        context,
        objective_policy,
        affected_from,
        affected_until,
        previous_plan,
    )
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
