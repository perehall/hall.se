"""Typed week navigation built from explicit published/planned week availability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


MONTHS = {
    1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "maj", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "okt", 11: "nov", 12: "dec",
}


@dataclass(frozen=True)
class PublishedWeek:
    key: str
    week_start: date
    week_end: date
    url: str


@dataclass(frozen=True)
class WeekNavigationLink:
    key: str
    label: str
    url: str


@dataclass(frozen=True)
class WeekNavigationReadModel:
    key: str
    label: str
    period: str
    state: str
    previous: WeekNavigationLink | None
    next: WeekNavigationLink | None


def iso_week_key(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_number(key: str) -> int:
    return int(key.split("-W", 1)[1])


def week_period(start: date, end: date) -> str:
    if start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS[end.month]}"
    return (
        f"{start.day} {MONTHS[start.month]}–"
        f"{end.day} {MONTHS[end.month]}"
    )


def week_url(key: str, current_key: str) -> str:
    return "/träning/" if key == current_key else f"/träning/vecka/{key}/"


def build_week_navigation(
    *,
    viewed_start: date,
    current_start: date,
    planned_days: Iterable[date],
    published_weeks: Iterable[PublishedWeek] = (),
) -> WeekNavigationReadModel:
    viewed_key = iso_week_key(viewed_start)
    current_key = iso_week_key(current_start)

    available: dict[str, tuple[date, date, str]] = {}
    for entry in published_weeks:
        if iso_week_key(entry.week_start) != entry.key:
            raise ValueError(f"archive key/date mismatch: {entry.key}")
        available[entry.key] = (entry.week_start, entry.week_end, entry.url)

    for day in planned_days:
        start = day - timedelta(days=day.weekday())
        end = start + timedelta(days=6)
        key = iso_week_key(start)
        available[key] = (start, end, week_url(key, current_key))

    current_end = current_start + timedelta(days=6)
    available[current_key] = (
        current_start,
        current_end,
        "/träning/",
    )

    if viewed_key not in available:
        viewed_end = viewed_start + timedelta(days=6)
        available[viewed_key] = (
            viewed_start,
            viewed_end,
            week_url(viewed_key, current_key),
        )

    ordered = sorted(available)
    index = ordered.index(viewed_key)

    def link(key: str | None) -> WeekNavigationLink | None:
        if key is None:
            return None
        return WeekNavigationLink(
            key=key,
            label=f"Vecka {week_number(key)}",
            url=week_url(key, current_key),
        )

    previous_key = ordered[index - 1] if index > 0 else None
    next_key = ordered[index + 1] if index + 1 < len(ordered) else None
    start, end, _ = available[viewed_key]
    state = (
        "aktuell" if viewed_key == current_key
        else "historik" if viewed_start < current_start
        else "kommande"
    )
    return WeekNavigationReadModel(
        key=viewed_key,
        label=f"Vecka {week_number(viewed_key)}",
        period=week_period(start, end),
        state=state,
        previous=link(previous_key),
        next=link(next_key),
    )
