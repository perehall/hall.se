"""Canonical planned-workout domain objects.

Calendar dates are containers. A date can hold zero or more planned workouts.
A workout is independently addressable and may itself contain one or more
ordered sport components (for example a brick or triathlon-specific session).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class WorkoutComponent:
    sport: str
    label: str = ""
    order: int = 0


@dataclass(frozen=True)
class PlannedWorkout:
    local_date: date
    session: str
    sport: str
    status: str
    planning_status: str = ""
    manual_lock: bool = False
    reason: str = ""
    development_focus: str = ""
    payload: dict | None = None
    workout_key: str = ""

    @property
    def components(self) -> tuple[WorkoutComponent, ...]:
        raw = self.payload or {}
        explicit = raw.get("components") or raw.get("workout_components") or ()
        result: list[WorkoutComponent] = []
        if isinstance(explicit, list):
            for index, item in enumerate(explicit):
                if not isinstance(item, dict):
                    continue
                sport = str(item.get("sport") or "").strip()
                if not sport:
                    continue
                result.append(
                    WorkoutComponent(
                        sport=sport,
                        label=str(item.get("label") or item.get("session") or "").strip(),
                        order=int(item.get("order") or index + 1),
                    )
                )
        if result:
            return tuple(sorted(result, key=lambda item: item.order))

        sport = str(self.sport or "").strip()
        if sport and sport not in {"open", "rest"}:
            return (WorkoutComponent(sport=sport, label=self.session, order=1),)
        return ()


def planned_training_workouts(
    workouts: tuple[PlannedWorkout, ...] | list[PlannedWorkout],
) -> tuple[PlannedWorkout, ...]:
    return tuple(
        workout
        for workout in workouts
        if str(workout.sport or "").strip().lower() not in {"", "open", "rest"}
    )
