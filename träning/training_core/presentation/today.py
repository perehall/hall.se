"""Typed presentation-domain objects for architecture v2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


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
    feedback_text: str
    coach_summary: str
    plan_impact: str
    action_reason: str
    next_step: str


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
        feedback_text=activity.feedback_text,
        coach_summary=activity.coach_summary,
        plan_impact=plan_impact(activity),
        action_reason=activity.action_reason,
        next_step=activity.recommendation,
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
    days = {day.local_date: day for day in plan}
    planned = days.get(today)
    if planned is None:
        raise ValueError(f"missing planned day for {today.isoformat()}")

    actual = tuple(activity for activity in activities if activity.local_date == today)
    future = sorted(
        (day for day in days.values() if day.local_date > today),
        key=lambda day: day.local_date,
    )

    if actual:
        title = " + ".join(activity.label for activity in actual)
        details = tuple(activity_detail(activity) for activity in actual)
        outcomes = tuple(activity_outcome(activity) for activity in actual)
        state = "completed"
    else:
        title = planned.session
        details = ()
        outcomes = ()
        state = (
            "fixed"
            if planned.manual_lock or planned.planning_status == "fixed"
            else planned.status or "open"
        )

    return TodayReadModel(
        local_date=today,
        state=state,
        title=title,
        details=details,
        planned_session=planned.session,
        next_session=future[0].session if future else None,
        reason=planned.reason,
        development_focus=planned.development_focus,
        prescription=_prescription_lines(planned),
        outcomes=outcomes,
    )
