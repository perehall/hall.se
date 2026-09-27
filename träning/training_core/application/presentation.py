"""Application use cases for canonical and historical presentation snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from training_core.presentation.history import (
    HistoricalWeekReadModel,
    build_historical_week_read_model,
)
from training_core.presentation.navigation import (
    WeekNavigationReadModel,
    build_week_navigation,
)
from training_core.presentation.today import TodayReadModel, build_today_read_model
from training_core.presentation.weather import WeatherReadModel, build_weather_read_model
from training_core.presentation.week import WeekReadModel, build_week_read_model
from training_core.repositories.archive import WeekArchiveRepository
from training_core.repositories.presentation import PresentationRepository
from training_core.repositories.weather import WeatherRepository


@dataclass(frozen=True)
class PresentationSnapshot:
    today: TodayReadModel
    week: WeekReadModel
    navigation: WeekNavigationReadModel
    weather: WeatherReadModel


@dataclass(frozen=True)
class HistoricalPresentationSnapshot:
    history: HistoricalWeekReadModel
    navigation: WeekNavigationReadModel


def week_bounds(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def build_presentation_snapshot(
    repository: PresentationRepository,
    *,
    today: date,
    archive_repository: WeekArchiveRepository | None = None,
    weather_repository: WeatherRepository | None = None,
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
    weather_snapshot = (
        weather_repository.current()
        if weather_repository is not None
        else None
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
        weather=build_weather_read_model(
            plan=plan,
            snapshot=weather_snapshot,
        ),
    )


def build_historical_presentation_snapshot(
    archive_repository: WeekArchiveRepository,
    *,
    week_key: str,
) -> HistoricalPresentationSnapshot:
    archived = archive_repository.archived_week(week_key)
    current = archive_repository.current_published_week()
    published = archive_repository.published_weeks()
    return HistoricalPresentationSnapshot(
        history=build_historical_week_read_model(archived),
        navigation=build_week_navigation(
            viewed_start=archived.start,
            current_start=current.week_start,
            planned_days=(),
            published_weeks=published,
        ),
    )
