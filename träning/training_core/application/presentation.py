"""Application use cases for canonical presentation snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from training_core.presentation.navigation import (
    WeekNavigationReadModel,
    build_week_navigation,
)
from training_core.presentation.today import TodayReadModel, build_today_read_model
from training_core.presentation.week import WeekReadModel, build_week_read_model
from training_core.repositories.archive import WeekArchiveRepository
from training_core.repositories.presentation import PresentationRepository


@dataclass(frozen=True)
class PresentationSnapshot:
    today: TodayReadModel
    week: WeekReadModel
    navigation: WeekNavigationReadModel


def week_bounds(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def build_presentation_snapshot(
    repository: PresentationRepository,
    *,
    today: date,
    archive_repository: WeekArchiveRepository | None = None,
) -> PresentationSnapshot:
    week_start, week_end = week_bounds(today)
    read_end = max(week_end, today + timedelta(days=7))
    plan = repository.planned_days(week_start, read_end)
    activities = repository.completed_activities(week_start, week_end)
    published = (
        archive_repository.published_weeks()
        if archive_repository is not None
        else ()
    )
    return PresentationSnapshot(
        today=build_today_read_model(today=today, plan=plan, activities=activities),
        week=build_week_read_model(
            start=week_start, end=week_end, plan=plan, activities=activities
        ),
        navigation=build_week_navigation(
            viewed_start=week_start,
            current_start=week_start,
            planned_days=(day.local_date for day in plan),
            published_weeks=published,
        ),
    )
