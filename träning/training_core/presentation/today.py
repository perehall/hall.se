"""Typed presentation-domain objects for architecture v2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class CompletedActivity:
    provider_activity_id: str
    local_date: date
    label: str
    sport_family: str
    elapsed_time_s: int | None = None
    distance_m: float | None = None


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
    future = sorted((day for day in days.values() if day.local_date > today), key=lambda day: day.local_date)

    if actual:
        title = " + ".join(activity.label for activity in actual)
        details = tuple(activity_detail(activity) for activity in actual)
        state = "completed"
    else:
        title = planned.session
        details = ()
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
    )
