"""Typed week presentation model built from canonical domain objects."""

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
from training_core.presentation.sport_identity import (
    activity_icon_key,
    planned_icon_keys,
)
from training_core.presentation.today import CompletedActivity, PlannedDay


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
    week_activities: list[CompletedActivity] = []
    for activity in activities:
        if start <= activity.local_date <= end:
            by_date.setdefault(activity.local_date, []).append(activity)
            week_activities.append(activity)

    days: list[WeekDayReadModel] = []
    for day in planned:
        actual = tuple(a.label for a in by_date.get(day.local_date, []))
        manual = manual_activities_for_day(day)
        days.append(
            WeekDayReadModel(
                local_date=day.local_date,
                planned_session=day.session,
                actual_labels=actual,
                manual_activities=manual,
                icon_keys=(
                    tuple(
                        dict.fromkeys(
                            [
                                activity_icon_key(activity.sport_family)
                                for activity in by_date.get(day.local_date, [])
                            ]
                            + [activity.icon_key for activity in manual]
                        )
                    )
                    if actual or manual
                    else planned_icon_keys(sport=day.sport, payload=day.payload)
                ),
                device_sync=build_device_sync_read_model(
                    day.payload,
                    completed=bool(actual or manual),
                ),
                state="completed" if actual or manual else (
                    "fixed" if day.manual_lock or day.planning_status == "fixed"
                    else day.status or "open"
                ),
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
        planned_count=len(planned),
        completed_activity_count=len(week_activities),
        training_day_count=len(by_date),
        session_time_s=sum(int(activity.elapsed_time_s or 0) for activity in week_activities),
        sport_distribution=distribution,
    )
