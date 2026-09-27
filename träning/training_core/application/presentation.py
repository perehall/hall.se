"""Application use cases for canonical presentation snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from training_core.presentation.today import TodayReadModel, build_today_read_model
from training_core.presentation.week import WeekReadModel, build_week_read_model
from training_core.repositories.presentation import PresentationRepository


@dataclass(frozen=True)
class PresentationSnapshot:
    today: TodayReadModel
    week: WeekReadModel


def week_bounds(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def build_presentation_snapshot(
    repository: PresentationRepository,
    *,
    today: date,
) -> PresentationSnapshot:
    week_start, week_end = week_bounds(today)
    read_end = max(week_end, today + timedelta(days=7))
    plan = repository.planned_days(week_start, read_end)
    activities = repository.completed_activities(week_start, week_end)
    return PresentationSnapshot(
        today=build_today_read_model(today=today, plan=plan, activities=activities),
        week=build_week_read_model(
            start=week_start, end=week_end, plan=plan, activities=activities
        ),
    )
