"""Typed presentation-domain objects for architecture v2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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
from training_core.presentation.public_copy import public_reason
from training_core.presentation.prescription import (
    PrescriptionRow,
    prescription_lines,
    prescription_rows,
)
from training_core.presentation.sport_identity import (
    activity_icon_key,
    planned_icon_keys,
)


# Compatibility alias while remaining callers migrate from "day" to "workout".
PlannedDay = PlannedWorkout


FEELING_LABELS = {
    "fresh": "Pigg",
    "tired": "Trött",
    "strong_legs": "Starka ben",
    "heavy_legs": "Tunga ben",
    "pain": "Smärta",
    "could_do_more": "Kunde gjort mer",
}

PLAN_IMPACT_LABELS = {
    "keep": "Ingen ändring",
    "review": "Fortsatt bedömning",
}


@dataclass(frozen=True)
class CompletedActivity:
    provider_activity_id: str
    local_date: date
    label: str
    sport_family: str
    elapsed_time_s: int | None = None
    distance_m: float | None = None
    average_heartrate: float | None = None
    max_heartrate: float | None = None
    feedback_event_key: str = ""
    feedback_text: str = ""
    rpe: int | None = None
    feelings: tuple[str, ...] = ()
    coach_summary: str = ""
    plan_action: str = ""
    action_reason: str = ""
    recommendation: str = ""
    coach_auto_applied: bool = False


@dataclass(frozen=True)
class ActivityOutcomeReadModel:
    provider_activity_id: str
    label: str
    detail: str
    feedback_status: str
    feedback_event_key: str
    feedback_text: str
    rpe: int | None
    feelings: tuple[str, ...]
    coach_summary: str
    plan_impact: str
    action_reason: str
    next_step: str
    icon_key: str


@dataclass(frozen=True)
class PlannedWorkoutReadModel:
    workout_key: str
    session: str
    sport: str
    icon_keys: tuple[str, ...]
    component_sports: tuple[str, ...]
    prescription: tuple[str, ...]
    prescription_rows: tuple[PrescriptionRow, ...]
    reason: str
    development_focus: str
    device_sync: DeviceSyncReadModel | None


@dataclass(frozen=True)
class TodayReadModel:
    local_date: date
    state: str
    title: str
    details: tuple[str, ...]
    planned_session: str
    next_session: str | None = None
    reason: str = ""
    development_focus: str = ""
    prescription: tuple[str, ...] = ()
    outcomes: tuple[ActivityOutcomeReadModel, ...] = ()
    manual_activities: tuple[ManualActivityReadModel, ...] = ()
    icon_keys: tuple[str, ...] = ()
    device_sync: DeviceSyncReadModel | None = None
    planned_workouts: tuple[PlannedWorkoutReadModel, ...] = ()
    next_sessions: tuple[str, ...] = ()


def _duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    hours, rem = divmod(max(0, int(seconds)), 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def activity_detail(activity: CompletedActivity) -> str:
    facts: list[str] = []
    if activity.distance_m and activity.distance_m > 0:
        facts.append(f"{activity.distance_m / 1000:.2f} km".replace(".", ","))
    if activity.elapsed_time_s:
        facts.append(_duration(activity.elapsed_time_s))
    return activity.label + ((" · " + " · ".join(facts)) if facts else "")


def feedback_status(activity: CompletedActivity) -> str:
    parts: list[str] = []
    if activity.rpe is not None:
        parts.append(f"RPE {activity.rpe}")
    for code in activity.feelings:
        label = FEELING_LABELS.get(code)
        if label and label not in parts:
            parts.append(label)
    if parts:
        return " · ".join(parts)
    if activity.feedback_text:
        return "Sparat"
    return "Inte utvärderat"


def plan_impact(activity: CompletedActivity) -> str:
    action = activity.plan_action
    if action in PLAN_IMPACT_LABELS:
        return PLAN_IMPACT_LABELS[action]
    if action in {"reduce", "rest"}:
        return "Planen justerades" if activity.coach_auto_applied else "Ändring rekommenderades"
    return ""


def activity_outcome(activity: CompletedActivity) -> ActivityOutcomeReadModel:
    return ActivityOutcomeReadModel(
        provider_activity_id=activity.provider_activity_id,
        label=activity.label,
        detail=activity_detail(activity),
        feedback_status=feedback_status(activity),
        feedback_event_key=activity.feedback_event_key,
        feedback_text=activity.feedback_text,
        rpe=activity.rpe,
        feelings=activity.feelings,
        coach_summary=activity.coach_summary,
        plan_impact=plan_impact(activity),
        action_reason=activity.action_reason,
        next_step=activity.recommendation,
        icon_key=activity_icon_key(activity.sport_family),
    )


def _prescription_lines(workout: PlannedWorkout) -> tuple[str, ...]:
    return prescription_lines(workout.payload or {})


def _workout_read_model(
    workout: PlannedWorkout,
    *,
    completed: bool,
) -> PlannedWorkoutReadModel:
    return PlannedWorkoutReadModel(
        workout_key=workout.workout_key,
        session=workout.session,
        sport=workout.sport,
        icon_keys=planned_icon_keys(sport=workout.sport, payload=workout.payload),
        component_sports=tuple(component.sport for component in workout.components),
        prescription=_prescription_lines(workout),
        prescription_rows=prescription_rows(workout.payload or {}),
        reason=public_reason(workout.reason),
        development_focus=workout.development_focus,
        device_sync=build_device_sync_read_model(workout.payload, completed=completed),
    )


def _state_for(workouts: tuple[PlannedWorkout, ...]) -> str:
    if not workouts:
        return "open"
    if any(
        workout.manual_lock or workout.planning_status == "fixed"
        for workout in workouts
    ):
        return "fixed"
    states = [workout.status for workout in workouts if workout.status]
    return states[0] if len(set(states)) == 1 and states else "planned"


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


def _joined_unique(values: Iterable[str]) -> str:
    return " · ".join(dict.fromkeys(value for value in values if value))


def build_today_read_model(
    *,
    today: date,
    plan: Iterable[PlannedWorkout],
    activities: Iterable[CompletedActivity],
) -> TodayReadModel:
    plan_rows = tuple(plan)
    today_rows = tuple(row for row in plan_rows if row.local_date == today)

    training_rows = planned_training_workouts(today_rows)
    display_rows = training_rows or today_rows[:1]
    actual = tuple(activity for activity in activities if activity.local_date == today)
    manual = _manual_activities(today_rows)
    completed = bool(actual or manual)
    workout_models = tuple(
        _workout_read_model(workout, completed=completed)
        for workout in training_rows
    )

    future_dates = sorted(
        {row.local_date for row in plan_rows if row.local_date > today}
    )
    next_rows: tuple[PlannedWorkout, ...] = ()
    for future_date in future_dates:
        candidates = planned_training_workouts(
            [row for row in plan_rows if row.local_date == future_date]
        )
        if candidates:
            next_rows = candidates
            break
    next_sessions = tuple(row.session for row in next_rows)

    if completed:
        title_parts = [activity.label for activity in actual] + [
            activity.session for activity in manual
        ]
        title = " + ".join(title_parts)
        details = tuple(activity_detail(activity) for activity in actual) + tuple(
            f"{activity.session} · {activity.classification_label}"
            for activity in manual
        )
        outcomes = tuple(activity_outcome(activity) for activity in actual)
        state = "completed"
    else:
        if len(training_rows) > 1:
            title = f"{len(training_rows)} planerade pass"
        elif display_rows:
            title = display_rows[0].session
        else:
            title = "Vilodag"
        details = ()
        outcomes = ()
        state = _state_for(display_rows)

    planned_session = " + ".join(row.session for row in training_rows)
    if not planned_session and display_rows:
        planned_session = display_rows[0].session

    reason = _joined_unique(public_reason(row.reason) for row in display_rows)
    development_focus = _joined_unique(row.development_focus for row in display_rows)
    legacy_prescription = (
        _prescription_lines(training_rows[0])
        if len(training_rows) == 1
        else ()
    )
    legacy_device_sync = (
        build_device_sync_read_model(training_rows[0].payload, completed=completed)
        if len(training_rows) == 1
        else None
    )

    if completed:
        icon_keys = tuple(
            dict.fromkeys(
                [activity_icon_key(activity.sport_family) for activity in actual]
                + [activity.icon_key for activity in manual]
            )
        )
    else:
        planned_icons: list[str] = []
        for workout in training_rows:
            planned_icons.extend(
                planned_icon_keys(sport=workout.sport, payload=workout.payload)
            )
        icon_keys = tuple(dict.fromkeys(planned_icons))

    return TodayReadModel(
        local_date=today,
        state=state,
        title=title,
        details=details,
        planned_session=planned_session,
        next_session=" + ".join(next_sessions) if next_sessions else None,
        reason=reason,
        development_focus=development_focus,
        prescription=legacy_prescription,
        outcomes=outcomes,
        manual_activities=manual,
        icon_keys=icon_keys,
        device_sync=legacy_device_sync,
        planned_workouts=workout_models,
        next_sessions=next_sessions,
    )
