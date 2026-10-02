"""Explainable machine-readable traces for Planning Engine v1.

This module derives explanations only from canonical solver inputs and evaluated
candidate plans. It never invents coaching rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

from .content import plan_content_hash
from .models import PlanContent, PlannedTrainingWorkout
from .objectives import ObjectiveVector
from .validation import PlanValidationContext


@dataclass(frozen=True)
class ObjectiveComparisonTrace:
    alternative_plan_hash: str
    first_deciding_objective: str
    selected_value: str
    alternative_value: str


@dataclass(frozen=True)
class WorkoutAlternativeTrace:
    local_date: str
    recipe_id: str
    dose_option_id: str
    comparison: ObjectiveComparisonTrace


@dataclass(frozen=True)
class WorkoutDecisionTrace:
    workout_id: str
    local_date: str
    recipe_id: str
    dose_option_id: str
    obligation_ids: tuple[str, ...]
    source_capabilities: tuple[str, ...]
    eligibility: tuple[tuple[str, str], ...]
    constraint_ids: tuple[str, ...]
    alternative_dates: tuple[str, ...]
    alternative_options: tuple[tuple[str, str], ...]
    alternative_comparisons: tuple[WorkoutAlternativeTrace, ...]
    stability_change: str


@dataclass(frozen=True)
class PlanChangeTrace:
    kind: str
    previous_workout_id: str | None
    current_workout_id: str | None
    from_date: str | None
    to_date: str | None
    before_option: tuple[str, str] | None
    after_option: tuple[str, str] | None


def _value_text(value) -> str:
    if isinstance(value, Fraction):
        return f"{value.numerator}/{value.denominator}"
    if isinstance(value, tuple):
        return "[" + ",".join(_value_text(item) for item in value) + "]"
    return str(value)


def compare_objective_vectors(
    selected: ObjectiveVector,
    alternative: ObjectiveVector,
    alternative_plan: PlanContent,
) -> ObjectiveComparisonTrace:
    tier_count = max(
        len(selected.required_deficit_by_tier),
        len(alternative.required_deficit_by_tier),
    )
    for index in range(tier_count):
        selected_tier = (
            selected.required_deficit_by_tier[index],
            selected.unserved_required_by_tier[index],
            selected.max_required_deficit_by_tier[index],
        )
        alternative_tier = (
            alternative.required_deficit_by_tier[index],
            alternative.unserved_required_by_tier[index],
            alternative.max_required_deficit_by_tier[index],
        )
        if selected_tier != alternative_tier:
            return ObjectiveComparisonTrace(
                alternative_plan_hash=plan_content_hash(alternative_plan),
                first_deciding_objective=f"required_coverage_tier_{index + 1}",
                selected_value=_value_text(selected_tier),
                alternative_value=_value_text(alternative_tier),
            )

    fields = (
        ("anti_filler_discretionary_excess", "discretionary_excess_by_tier"),
        ("spacing_shortfall_days", "spacing_shortfall_days"),
        ("spacing_violation_pairs", "spacing_violation_pairs"),
        ("stability_identity_churn", "stability_identity_churn"),
        ("stability_date_moves", "stability_date_moves"),
        ("stability_prescription_changes", "stability_prescription_changes"),
        ("stability_order_changes", "stability_order_changes"),
        ("schedule_range_violation", "schedule_range_violation"),
        ("schedule_preferred_distance", "schedule_preferred_distance"),
        ("schedule_double_penalty", "schedule_double_penalty"),
        ("variation_repeat_penalty", "variation_repeat_penalty"),
        ("canonical_tie_break", "canonical_tie_key"),
    )
    for label, field in fields:
        selected_value = getattr(selected, field)
        alternative_value = getattr(alternative, field)
        if selected_value != alternative_value:
            return ObjectiveComparisonTrace(
                alternative_plan_hash=plan_content_hash(alternative_plan),
                first_deciding_objective=label,
                selected_value=_value_text(selected_value),
                alternative_value=_value_text(alternative_value),
            )

    return ObjectiveComparisonTrace(
        alternative_plan_hash=plan_content_hash(alternative_plan),
        first_deciding_objective="semantic_tie",
        selected_value="equal",
        alternative_value="equal",
    )


def _intent_signature(workout: PlannedTrainingWorkout) -> tuple:
    contributions = tuple(
        sorted(
            (
                item.obligation_id,
                item.source_capability,
                item.kind.value,
                item.credit_numerator,
                item.credit_denominator,
            )
            for item in workout.obligation_contributions
        )
    )
    components = tuple(
        (item.discipline, item.order)
        for item in workout.components
    )
    return contributions, components


def _sort_workouts(rows: Iterable[PlannedTrainingWorkout]) -> list[PlannedTrainingWorkout]:
    return sorted(
        rows,
        key=lambda item: (
            item.local_date,
            item.within_day_order if item.within_day_order is not None else 999,
            item.recipe_id,
            item.dose_option_id,
            item.workout_id,
        ),
    )


def build_plan_changes(
    selected: PlanContent,
    previous: PlanContent | None,
) -> tuple[PlanChangeTrace, ...]:
    if previous is None:
        return tuple(
            PlanChangeTrace(
                kind="added",
                previous_workout_id=None,
                current_workout_id=item.workout_id,
                from_date=None,
                to_date=item.local_date.isoformat(),
                before_option=None,
                after_option=(item.recipe_id, item.dose_option_id),
            )
            for item in _sort_workouts(selected.workouts)
        )

    previous_rows = [
        item
        for item in previous.workouts
        if selected.affected_from <= item.local_date <= selected.affected_until
    ]
    current_rows = list(selected.workouts)

    before_by_intent: dict[tuple, list[PlannedTrainingWorkout]] = {}
    after_by_intent: dict[tuple, list[PlannedTrainingWorkout]] = {}
    for item in previous_rows:
        before_by_intent.setdefault(_intent_signature(item), []).append(item)
    for item in current_rows:
        after_by_intent.setdefault(_intent_signature(item), []).append(item)

    changes: list[PlanChangeTrace] = []
    for intent in sorted(set(before_by_intent) | set(after_by_intent), key=repr):
        before = _sort_workouts(before_by_intent.get(intent, ()))
        after = _sort_workouts(after_by_intent.get(intent, ()))
        paired = min(len(before), len(after))

        for index in range(paired):
            old = before[index]
            new = after[index]
            old_option = (old.recipe_id, old.dose_option_id)
            new_option = (new.recipe_id, new.dose_option_id)
            moved = old.local_date != new.local_date
            changed = old_option != new_option
            reordered = old.within_day_order != new.within_day_order
            if moved and changed:
                kind = "moved_and_changed"
            elif moved:
                kind = "moved"
            elif changed:
                kind = "prescription_changed"
            elif reordered:
                kind = "order_changed"
            else:
                kind = "kept"
            changes.append(
                PlanChangeTrace(
                    kind=kind,
                    previous_workout_id=old.workout_id,
                    current_workout_id=new.workout_id,
                    from_date=old.local_date.isoformat(),
                    to_date=new.local_date.isoformat(),
                    before_option=old_option,
                    after_option=new_option,
                )
            )

        for old in before[paired:]:
            changes.append(
                PlanChangeTrace(
                    kind="removed",
                    previous_workout_id=old.workout_id,
                    current_workout_id=None,
                    from_date=old.local_date.isoformat(),
                    to_date=None,
                    before_option=(old.recipe_id, old.dose_option_id),
                    after_option=None,
                )
            )
        for new in after[paired:]:
            changes.append(
                PlanChangeTrace(
                    kind="added",
                    previous_workout_id=None,
                    current_workout_id=new.workout_id,
                    from_date=None,
                    to_date=new.local_date.isoformat(),
                    before_option=None,
                    after_option=(new.recipe_id, new.dose_option_id),
                )
            )

    return tuple(
        sorted(
            changes,
            key=lambda item: (
                item.to_date or item.from_date or "",
                item.kind,
                item.current_workout_id or item.previous_workout_id or "",
            ),
        )
    )


def _stability_by_current_id(changes: tuple[PlanChangeTrace, ...]) -> dict[str, str]:
    return {
        item.current_workout_id: item.kind
        for item in changes
        if item.current_workout_id is not None
    }


def build_workout_decisions(
    selected: PlanContent,
    selected_vector: ObjectiveVector,
    valid_ranked: Iterable[tuple[PlanContent, ObjectiveVector]],
    context: PlanValidationContext,
    previous: PlanContent | None,
) -> tuple[WorkoutDecisionTrace, ...]:
    valid = tuple(valid_ranked)
    changes = build_plan_changes(selected, previous)
    stability = _stability_by_current_id(changes)

    eligibility = {
        (item.recipe_id, item.dose_option_id, item.capability): item.kind.value
        for item in context.option_eligibility
    }

    rows: list[WorkoutDecisionTrace] = []
    for workout in _sort_workouts(selected.workouts):
        intent = _intent_signature(workout)
        alternate_dates = set()
        alternate_options = set()
        best_alternatives: dict[tuple[str, str, str], WorkoutAlternativeTrace] = {}
        for plan, vector in valid:
            for candidate in plan.workouts:
                if _intent_signature(candidate) != intent:
                    continue
                if candidate.local_date != workout.local_date:
                    alternate_dates.add(candidate.local_date.isoformat())
                option = (candidate.recipe_id, candidate.dose_option_id)
                if option != (workout.recipe_id, workout.dose_option_id):
                    alternate_options.add(option)
                semantic_alt = (
                    candidate.local_date.isoformat(),
                    candidate.recipe_id,
                    candidate.dose_option_id,
                )
                if semantic_alt != (
                    workout.local_date.isoformat(),
                    workout.recipe_id,
                    workout.dose_option_id,
                ) and semantic_alt not in best_alternatives:
                    best_alternatives[semantic_alt] = WorkoutAlternativeTrace(
                        local_date=semantic_alt[0],
                        recipe_id=semantic_alt[1],
                        dose_option_id=semantic_alt[2],
                        comparison=compare_objective_vectors(
                            selected_vector,
                            vector,
                            plan,
                        ),
                    )

        source_capabilities = tuple(
            sorted(
                {
                    item.source_capability
                    for item in workout.obligation_contributions
                }
            )
        )
        eligibility_rows = tuple(
            sorted(
                (
                    capability,
                    eligibility.get(
                        (workout.recipe_id, workout.dose_option_id, capability),
                        "unknown",
                    ),
                )
                for capability in source_capabilities
            )
        )

        rows.append(
            WorkoutDecisionTrace(
                workout_id=workout.workout_id,
                local_date=workout.local_date.isoformat(),
                recipe_id=workout.recipe_id,
                dose_option_id=workout.dose_option_id,
                obligation_ids=tuple(
                    sorted(
                        item.obligation_id
                        for item in workout.obligation_contributions
                    )
                ),
                source_capabilities=source_capabilities,
                eligibility=eligibility_rows,
                constraint_ids=tuple(sorted(workout.constraint_ids)),
                alternative_dates=tuple(sorted(alternate_dates)),
                alternative_options=tuple(sorted(alternate_options)),
                alternative_comparisons=tuple(
                    best_alternatives[key]
                    for key in sorted(best_alternatives)
                ),
                stability_change=stability.get(workout.workout_id, "added"),
            )
        )

    return tuple(rows)
