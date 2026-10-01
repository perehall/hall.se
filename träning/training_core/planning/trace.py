"""Explainable machine-readable traces for Planning Engine v1.

This module derives explanations only from canonical solver inputs and evaluated
candidate plans. It never invents coaching rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import PlanContent, PlannedTrainingWorkout
from .validation import PlanValidationContext


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
    valid_plans: Iterable[PlanContent],
    context: PlanValidationContext,
    previous: PlanContent | None,
) -> tuple[WorkoutDecisionTrace, ...]:
    valid = tuple(valid_plans)
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
        for plan in valid:
            for candidate in plan.workouts:
                if _intent_signature(candidate) != intent:
                    continue
                if candidate.local_date != workout.local_date:
                    alternate_dates.add(candidate.local_date.isoformat())
                option = (candidate.recipe_id, candidate.dose_option_id)
                if option != (workout.recipe_id, workout.dose_option_id):
                    alternate_options.add(option)

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
                stability_change=stability.get(workout.workout_id, "added"),
            )
        )

    return tuple(rows)
