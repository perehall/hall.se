"""Typed presentation-domain objects for architecture v2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from training_core.presentation.device_sync import (
    DeviceSyncReadModel,
    build_device_sync_read_model,
)
from training_core.presentation.manual_activity import (
    ManualActivityReadModel,
    manual_activities_for_day,
)
from training_core.presentation.public_copy import public_reason
from training_core.presentation.sport_identity import (
    activity_icon_key,
    planned_icon_keys,
)


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
class PlannedDay:
    local_date: date
    session: str
    sport: str
    status: str
    planning_status: str = ""
    manual_lock: bool = False
    reason: str = ""
    development_focus: str = ""
    payload: dict | None = None


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
class TodayReadModel:
    local_date: date
    state: str
    title: str
    details: tuple[str, ...]
    planned_session: str
    planned_sessions: tuple[str, ...] = ()
    next_session: str | None = None
    reason: str = ""
    development_focus: str = ""
    prescription: tuple[str, ...] = ()
    outcomes: tuple[ActivityOutcomeReadModel, ...] = ()
    manual_activities: tuple[ManualActivityReadModel, ...] = ()
    icon_keys: tuple[str, ...] = ()
    device_sync: DeviceSyncReadModel | None = None


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


def _prescription_lines(day: PlannedDay) -> tuple[str, ...]:
    payload = day.payload or {}
    design = payload.get("workout_design") or {}
    selected_id = design.get("selected_candidate_id")
    candidates = design.get("candidates") or []
    selected = next((item for item in candidates if item.get("id") == selected_id), None)
    if selected is None and len(candidates) == 1:
        selected = candidates[0]
    blocks = ((selected or {}).get("prescription") or {}).get("blocks") or []
    lines = []
    for block in blocks:
        name = str(block.get("name") or "").strip()
        instruction = str(block.get("instruction") or "").strip()
        intensity = str(block.get("intensity") or "").strip()
        value = " · ".join(part for part in (name, intensity, instruction) if part)
        if value:
            lines.append(value)
    return tuple(lines)


def build_today_read_model(
    *,
    today: date,
    plan: Iterable[PlannedDay],
    activities: Iterable[CompletedActivity],
) -> TodayReadModel:
    planned_days = list(plan)
    todays_plan = tuple(day for day in planned_days if day.local_date == today)
    if not todays_plan:
        raise ValueError(f"missing planned day for {today.isoformat()}")

    actual = tuple(activity for activity in activities if activity.local_date == today)
    manual = tuple(
        activity for day in todays_plan for activity in manual_activities_for_day(day)
    )
    future_by_date: dict[date, list[PlannedDay]] = {}
    for day in planned_days:
        if day.local_date > today:
            future_by_date.setdefault(day.local_date, []).append(day)
    next_session = None
    if future_by_date:
        first_date = min(future_by_date)
        next_session = " + ".join(day.session for day in future_by_date[first_date])

    planned_sessions = tuple(day.session for day in todays_plan)
    planned_session = " + ".join(planned_sessions)

    if actual or manual:
        title_parts = [activity.label for activity in actual] + [activity.session for activity in manual]
        title = " + ".join(title_parts)
        details = tuple(activity_detail(activity) for activity in actual) + tuple(
            f"{activity.session} · {activity.classification_label}" for activity in manual
        )
        outcomes = tuple(activity_outcome(activity) for activity in actual)
        state = "completed"
    else:
        title = planned_session
        details = planned_sessions if len(planned_sessions) > 1 else ()
        outcomes = ()
        states = [
            "fixed" if day.manual_lock or day.planning_status == "fixed"
            else day.status or "open"
            for day in todays_plan
        ]
        state = "fixed" if "fixed" in states else states[0]

    reasons = tuple(value for value in (public_reason(day.reason) for day in todays_plan) if value)
    focuses = tuple(day.development_focus for day in todays_plan if day.development_focus)
    prescriptions = tuple(line for day in todays_plan for line in _prescription_lines(day))
    icon_keys = tuple(dict.fromkeys(
        [activity_icon_key(activity.sport_family) for activity in actual]
        + [activity.icon_key for activity in manual]
    )) if actual or manual else tuple(dict.fromkeys(
        key for day in todays_plan for key in planned_icon_keys(sport=day.sport, payload=day.payload)
    ))
    sync_models = [
        model for day in todays_plan
        if (model := build_device_sync_read_model(day.payload, completed=bool(actual or manual))) is not None
    ]

    return TodayReadModel(
        local_date=today,
        state=state,
        title=title,
        details=details,
        planned_session=planned_session,
        planned_sessions=planned_sessions,
        next_session=next_session,
        reason=" ".join(dict.fromkeys(reasons)),
        development_focus=" ".join(dict.fromkeys(focuses)),
        prescription=prescriptions,
        outcomes=outcomes,
        manual_activities=manual,
        icon_keys=icon_keys,
        device_sync=sync_models[0] if len(sync_models) == 1 else None,
    )
