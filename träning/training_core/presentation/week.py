"""Typed week presentation model built from canonical domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from training_core.presentation.today import CompletedActivity, PlannedDay


@dataclass(frozen=True)
class WeekDayReadModel:
    local_date: date
    planned_session: str
    actual_labels: tuple[str, ...]
    state: str


@dataclass(frozen=True)
class WeekReadModel:
    start: date
    end: date
    days: tuple[WeekDayReadModel, ...]
    planned_count: int
    completed_activity_count: int
    training_day_count: int


def build_week_read_model(
    *,
    start: date,
    end: date,
    plan: Iterable[PlannedDay],
    activities: Iterable[CompletedActivity],
) -> WeekReadModel:
    if end < start:
        raise ValueError("week end must not precede start")
    planned = sorted(
        (day for day in plan if start <= day.local_date <= end),
        key=lambda day: day.local_date,
    )
    by_date: dict[date, list[CompletedActivity]] = {}
    for activity in activities:
        if start <= activity.local_date <= end:
            by_date.setdefault(activity.local_date, []).append(activity)

    days: list[WeekDayReadModel] = []
    for day in planned:
        actual = tuple(a.label for a in by_date.get(day.local_date, []))
        days.append(
            WeekDayReadModel(
                local_date=day.local_date,
                planned_session=day.session,
                actual_labels=actual,
                state="completed" if actual else (
                    "fixed" if day.manual_lock or day.planning_status == "fixed"
                    else day.status or "open"
                ),
            )
        )
    return WeekReadModel(
        start=start,
        end=end,
        days=tuple(days),
        planned_count=len(planned),
        completed_activity_count=sum(len(v) for v in by_date.values()),
        training_day_count=len(by_date),
    )
