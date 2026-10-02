"""Compile explicit user plan changes into solver-owned placement constraints.

This module never edits PlanContent. Add/remove/move actions are optimistic
commands against an exact immutable base plan. The result is one or more
absolute WorkoutPlacementConstraint values that become ordinary solver input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .content import plan_content_hash
from .models import (
    PlanContent,
    PlanningContractError,
    WorkoutPlacementConstraint,
)


class PlanChangeKind(str, Enum):
    ADD = "add"
    REMOVE = "remove"
    MOVE = "move"


@dataclass(frozen=True)
class UserPlanChange:
    request_id: str
    kind: PlanChangeKind
    base_plan_hash: str
    source_refs: tuple[str, ...]
    target_date: date | None = None
    target_workout_id: str | None = None
    recipe_id: str | None = None
    dose_option_id: str | None = None
    obligation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        request_id = str(self.request_id or "").strip()
        base_hash = str(self.base_plan_hash or "").strip()
        if not request_id:
            raise PlanningContractError("plan change request_id must be non-empty")
        if not base_hash:
            raise PlanningContractError("plan change base_plan_hash must be non-empty")
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "base_plan_hash", base_hash)

        refs = tuple(str(value or "").strip() for value in self.source_refs)
        if not refs or any(not value for value in refs) or len(set(refs)) != len(refs):
            raise PlanningContractError(
                "plan change source_refs must be unique non-empty values"
            )
        object.__setattr__(self, "source_refs", refs)

        obligations = tuple(
            sorted(str(value or "").strip() for value in self.obligation_ids)
        )
        if any(not value for value in obligations) or len(set(obligations)) != len(obligations):
            raise PlanningContractError(
                "plan change obligation_ids must be unique non-empty values"
            )
        object.__setattr__(self, "obligation_ids", obligations)

        if not isinstance(self.kind, PlanChangeKind):
            raise PlanningContractError("plan change kind must be PlanChangeKind")

        if self.kind is PlanChangeKind.ADD:
            if not isinstance(self.target_date, date):
                raise PlanningContractError("ADD requires target_date")
            if not str(self.recipe_id or "").strip() or not str(self.dose_option_id or "").strip():
                raise PlanningContractError("ADD requires recipe_id and dose_option_id")
            if self.target_workout_id is not None:
                raise PlanningContractError("ADD must not target an existing workout id")
        else:
            if not str(self.target_workout_id or "").strip():
                raise PlanningContractError(
                    f"{self.kind.value.upper()} requires target_workout_id"
                )
            if self.recipe_id is not None or self.dose_option_id is not None:
                raise PlanningContractError(
                    f"{self.kind.value.upper()} derives prescription from target workout"
                )
            if self.kind is PlanChangeKind.MOVE and not isinstance(self.target_date, date):
                raise PlanningContractError("MOVE requires target_date")
            if self.kind is PlanChangeKind.REMOVE and self.target_date is not None:
                raise PlanningContractError("REMOVE must not supply target_date")


def _workout(plan: PlanContent, workout_id: str):
    matches = [
        item for item in plan.workouts
        if item.workout_id == workout_id
    ]
    if len(matches) != 1:
        raise PlanningContractError(
            f"target workout {workout_id!r} is not uniquely present in base plan"
        )
    return matches[0]


def _obligation_ids(workout) -> tuple[str, ...]:
    return tuple(
        sorted(item.obligation_id for item in workout.obligation_contributions)
    )


def _matching_count(
    plan: PlanContent,
    *,
    local_date: date,
    recipe_id: str,
    dose_option_id: str,
    obligation_ids: tuple[str, ...],
) -> int:
    result = 0
    for workout in plan.workouts:
        if workout.local_date != local_date:
            continue
        if workout.recipe_id != recipe_id or workout.dose_option_id != dose_option_id:
            continue
        if obligation_ids and _obligation_ids(workout) != obligation_ids:
            continue
        result += 1
    return result


def _constraint_id(request_id: str, suffix: str) -> str:
    return f"user:{request_id}:{suffix}"


def compile_plan_change(
    change: UserPlanChange,
    base_plan: PlanContent,
) -> tuple[WorkoutPlacementConstraint, ...]:
    """Compile one user action into absolute result-state constraints."""

    actual_hash = plan_content_hash(base_plan)
    if change.base_plan_hash != actual_hash:
        raise PlanningContractError(
            "plan change was created against a stale base plan"
        )

    if change.kind is PlanChangeKind.ADD:
        obligation_ids = tuple(change.obligation_ids)
        current = _matching_count(
            base_plan,
            local_date=change.target_date,
            recipe_id=str(change.recipe_id),
            dose_option_id=str(change.dose_option_id),
            obligation_ids=obligation_ids,
        )
        return (
            WorkoutPlacementConstraint(
                constraint_id=_constraint_id(change.request_id, "add"),
                local_date=change.target_date,
                recipe_id=str(change.recipe_id),
                dose_option_id=str(change.dose_option_id),
                min_occurrences=current + 1,
                max_occurrences=None,
                obligation_ids=obligation_ids,
                source_refs=change.source_refs,
            ),
        )

    target = _workout(base_plan, str(change.target_workout_id))
    # User actions target the physical prescription. Obligation accounting is
    # recomputed by the solver from the current StrategyRevision and must not
    # become part of the UI identity of an otherwise identical workout.
    obligation_ids: tuple[str, ...] = ()
    source_count = _matching_count(
        base_plan,
        local_date=target.local_date,
        recipe_id=target.recipe_id,
        dose_option_id=target.dose_option_id,
        obligation_ids=obligation_ids,
    )

    if change.kind is PlanChangeKind.REMOVE:
        return (
            WorkoutPlacementConstraint(
                constraint_id=_constraint_id(change.request_id, "remove"),
                local_date=target.local_date,
                recipe_id=target.recipe_id,
                dose_option_id=target.dose_option_id,
                min_occurrences=0,
                max_occurrences=max(0, source_count - 1),
                obligation_ids=obligation_ids,
                source_refs=change.source_refs,
            ),
        )

    if change.target_date == target.local_date:
        raise PlanningContractError("MOVE target date equals current workout date")

    target_count = _matching_count(
        base_plan,
        local_date=change.target_date,
        recipe_id=target.recipe_id,
        dose_option_id=target.dose_option_id,
        obligation_ids=obligation_ids,
    )
    return (
        WorkoutPlacementConstraint(
            constraint_id=_constraint_id(change.request_id, "move-from"),
            local_date=target.local_date,
            recipe_id=target.recipe_id,
            dose_option_id=target.dose_option_id,
            min_occurrences=0,
            max_occurrences=max(0, source_count - 1),
            obligation_ids=obligation_ids,
            source_refs=change.source_refs,
        ),
        WorkoutPlacementConstraint(
            constraint_id=_constraint_id(change.request_id, "move-to"),
            local_date=change.target_date,
            recipe_id=target.recipe_id,
            dose_option_id=target.dose_option_id,
            min_occurrences=target_count + 1,
            max_occurrences=None,
            obligation_ids=obligation_ids,
            source_refs=change.source_refs,
        ),
    )


def merge_placement_constraints(
    existing: tuple[WorkoutPlacementConstraint, ...],
    updates: tuple[WorkoutPlacementConstraint, ...],
) -> tuple[WorkoutPlacementConstraint, ...]:
    """Replace prior absolute constraints that overlap the updated selector.

    Absolute constraints describe the desired resulting count, so a newer
    user action against the current authoritative plan supersedes an older
    constraint for the same semantic placement instead of stacking deltas.
    """

    def overlaps(first: WorkoutPlacementConstraint, second: WorkoutPlacementConstraint) -> bool:
        if first.local_date != second.local_date or first.option_key != second.option_key:
            return False
        return (
            not first.obligation_ids
            or not second.obligation_ids
            or first.obligation_ids == second.obligation_ids
        )

    retained = [
        item
        for item in existing
        if not any(overlaps(item, update) for update in updates)
    ]
    merged = tuple((*retained, *updates))
    return tuple(
        sorted(
            merged,
            key=lambda item: (
                item.local_date,
                item.recipe_id,
                item.dose_option_id,
                item.obligation_ids,
                item.constraint_id,
            ),
        )
    )
