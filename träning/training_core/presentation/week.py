"""Typed week presentation model built from canonical domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from training_core.domain.workouts import PlannedWorkout, planned_training_workouts
from training_core.presentation.device_sync import (
    DeviceSyncReadModel,
    build_device_sync_read_model,
)
from training_core.presentation.manual_activity import (
    ManualActivityReadModel,
    manual_activities_for_day,
)
from training_core.presentation.sport_identity import (
    activity_icon_key,
    planned_icon_keys,
)
from training_core.presentation.today import CompletedActivity, PlannedWorkoutReadModel


SPORT_GROUP_LABELS = {
    "run": "Löpning",
    "swim": "Simning",
    "strength": "Styrka",
    "enduro": "Enduro",
    "swimrun": "Swimrun",
}


@dataclass(frozen=True)
class WeekDayReadModel:
    local_date: date
    planned_session: str
    actual_labels: tuple[str, ...]
    manual_activities: tuple[ManualActivityReadModel, ...]
    icon_keys: tuple[str, ...]
    device_sync: DeviceSyncReadModel | None
    state: str
    planned_sessions: tuple[str, ...] = ()
    planned_workouts: tuple[PlannedWorkoutReadModel, ...] = ()


@dataclass(frozen=True)
class WeekSportReadModel:
    label: str
    duration_s: int

    @property
    def duration(self) -> str:
        return format_duration(self.duration_s)


@dataclass(frozen=True)
class WeekReadModel:
    start: date
    end: date
    days: tuple[WeekDayReadModel, ...]
    planned_count: int
    completed_activity_count: int
    training_day_count: int
    session_time_s: int
    sport_distribution: tuple[WeekSportReadModel, ...]

    @property
    def session_time(self) -> str:
        return format_duration(self.session_time_s)

    @property
    def status_summary(self) -> str:
        day_word = "träningsdag" if self.training_day_count == 1 else "träningsdagar"
        return (
            f"{self.completed_activity_count} pass · {self.session_time} · "
            f"{self.training_day_count} {day_word}"
        )


def format_duration(seconds: int | None) -> str:
    total = max(0, int(seconds or 0))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def sport_group(activity: CompletedActivity) -> str:
    family = str(activity.sport_family or "").strip().lower()
    if family == "bike":
        return "MTB/XC" if "MTB" in activity.label.upper() else "Cykel"
    return SPORT_GROUP_LABELS.get(
        family,
        activity.label or family or "Övrigt",
    )


def _planned_read_model(workout: PlannedWorkout) -> PlannedWorkoutReadModel:
    from training_core.presentation.today import _prescription_lines

    return PlannedWorkoutReadModel(
        workout_key=workout.workout_key,
        session=workout.session,
        sport=workout.sport,
        icon_keys=planned_icon_keys(sport=workout.sport, payload=workout.payload),
        component_sports=tuple(component.sport for component in workout.components),
        prescription=_prescription_lines(workout),
        reason=workout.reason,
        development_focus=workout.development_focus,
        device_sync=build_device_sync_read_model(workout.payload, completed=False),
    )


def _manual_activities(workouts: tuple[PlannedWorkout, ...]) -> tuple[ManualActivityReadModel, ...]:
    result: list[ManualActivityReadModel] = []
    seen: set[tuple[str, str, str]] = set()
    for workout in workouts:
        for activity in manual_activities_for_day(workout):
            key = (activity.session, activity.sport, activity.classification)
            if key in seen:
                continue
            seen.add(key)
            result.append(activity)
    return tuple(result)


def _planned_state(workouts: tuple[PlannedWorkout, ...]) -> str:
    if not workouts:
        return "open"
    if any(workout.manual_lock or workout.planning_status == "fixed" for workout in workouts):
        return "fixed"
    states = [workout.status for workout in workouts if workout.status]
    return states[0] if len(set(states)) == 1 and states else "planned"


def build_week_read_model(
    *,
    start: date,
    end: date,
    plan: Iterable[PlannedWorkout],
    activities: Iterable[CompletedActivity],
) -> WeekReadModel:
    if end < start:
        raise ValueError("week end must not precede start")

    plan_rows = tuple(
        workout for workout in plan if start <= workout.local_date <= end
    )
    plan_by_date: dict[date, list[PlannedWorkout]] = {}
    for workout in plan_rows:
        plan_by_date.setdefault(workout.local_date, []).append(workout)

    by_date: dict[date, list[CompletedActivity]] = {}
    week_activities: list[CompletedActivity] = []
    for activity in activities:
        if start <= activity.local_date <= end:
            by_date.setdefault(activity.local_date, []).append(activity)
            week_activities.append(activity)

    dates = tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))
    days: list[WeekDayReadModel] = []
    for local_date in dates:
        all_planned = tuple(plan_by_date.get(local_date, ()))
        planned = planned_training_workouts(all_planned)
        actual_activities = tuple(by_date.get(local_date, ()))
        actual = tuple(activity.label for activity in actual_activities)
        manual = _manual_activities(all_planned)
        workout_models = tuple(_planned_read_model(workout) for workout in planned)
        planned_sessions = tuple(workout.session for workout in planned)
        planned_session = " + ".join(planned_sessions)
        if not planned_session and all_planned:
            planned_session = all_planned[0].session

        if actual or manual:
            icons = tuple(
                dict.fromkeys(
                    [activity_icon_key(activity.sport_family) for activity in actual_activities]
                    + [activity.icon_key for activity in manual]
                )
            )
            state = "completed"
        else:
            keys: list[str] = []
            for workout in planned:
                keys.extend(planned_icon_keys(sport=workout.sport, payload=workout.payload))
            icons = tuple(dict.fromkeys(keys))
            state = _planned_state(all_planned)

        legacy_sync = (
            build_device_sync_read_model(planned[0].payload, completed=False)
            if len(planned) == 1
            else None
        )
        days.append(
            WeekDayReadModel(
                local_date=local_date,
                planned_session=planned_session,
                actual_labels=actual,
                manual_activities=manual,
                icon_keys=icons,
                device_sync=legacy_sync,
                state=state,
                planned_sessions=planned_sessions,
                planned_workouts=workout_models,
            )
        )

    sport_seconds: dict[str, int] = {}
    for activity in week_activities:
        group = sport_group(activity)
        sport_seconds[group] = sport_seconds.get(group, 0) + int(
            activity.elapsed_time_s or 0
        )
    distribution = tuple(
        WeekSportReadModel(label=label, duration_s=seconds)
        for label, seconds in sorted(
            sport_seconds.items(),
            key=lambda item: (-item[1], item[0]),
        )
    )
    return WeekReadModel(
        start=start,
        end=end,
        days=tuple(days),
        planned_count=sum(
            len(planned_training_workouts(tuple(rows)))
            for rows in plan_by_date.values()
        ),
        completed_activity_count=len(week_activities),
        training_day_count=len(by_date),
        session_time_s=sum(int(activity.elapsed_time_s or 0) for activity in week_activities),
        sport_distribution=distribution,
    )
