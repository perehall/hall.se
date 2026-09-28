"""Canonical plan accessors.

A calendar date is only a coordinate. Physical training exists exclusively in
planned_workouts. Runtime code must fail closed if that collection is missing
rather than reinterpret the seven-row calendar axis as workouts.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

WEEKDAY_LABELS = (
    "Måndag",
    "Tisdag",
    "Onsdag",
    "Torsdag",
    "Fredag",
    "Lördag",
    "Söndag",
)


def planned_workouts(document: dict, *, context: str = "plan") -> list[dict]:
    rows = document.get("planned_workouts")
    if rows is None:
        raise RuntimeError(
            f"{context}: planned_workouts saknas; runtime får inte härleda pass från days"
        )
    if not isinstance(rows, list):
        raise RuntimeError(f"{context}: planned_workouts måste vara en lista")
    return [
        row
        for row in rows
        if isinstance(row, dict)
        and str(row.get("sport") or "").strip().lower() not in {"", "open", "rest"}
    ]


def week_bounds(document: dict, *, context: str = "plan") -> tuple[date, date]:
    meta = document.get("meta") or {}
    try:
        start = date.fromisoformat(str(meta["week_start"]))
        end = date.fromisoformat(str(meta["week_end"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"{context}: ogiltiga week_start/week_end") from exc
    if end != start + timedelta(days=6):
        raise RuntimeError(f"{context}: kalenderveckan måste omfatta exakt sju dagar")
    return start, end


def calendar_days(document: dict, *, context: str = "plan") -> list[dict]:
    """Return the seven-row presentation axis.

    Calendar rows intentionally contain only date/label. They are never a
    fallback source for workout state.
    """
    rows = document.get("days")
    if not isinstance(rows, list) or len(rows) != 7:
        raise RuntimeError(f"{context}: days måste vara en sjuraders kalenderaxel")
    return rows


def build_calendar_axis(start: date) -> list[dict]:
    return [
        {
            "date": (start + timedelta(days=offset)).isoformat(),
            "label": WEEKDAY_LABELS[offset],
        }
        for offset in range(7)
    ]


def workouts_by_date(document: dict, *, context: str = "plan") -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for workout in planned_workouts(document, context=context):
        value = str(workout.get("date") or "").strip()
        if not value:
            raise RuntimeError(f"{context}: planned workout saknar datum")
        grouped.setdefault(value, []).append(workout)
    return grouped


def near_term_window(plan: dict, upcoming: dict | None = None) -> dict:
    """Combine contiguous canonical workout collections for reasoning only."""
    result = deepcopy(plan)
    active_start, active_end = week_bounds(plan, context="aktiv plan")
    active_workouts = deepcopy(planned_workouts(plan, context="aktiv plan"))

    if not upcoming:
        result["planned_workouts"] = active_workouts
        result["near_term_window"] = {
            "active_week_start": active_start.isoformat(),
            "active_week_end": active_end.isoformat(),
            "window_end": active_end.isoformat(),
            "calendar_week_is_presentation": True,
        }
        return result

    upcoming_start, upcoming_end = week_bounds(upcoming, context="kommande plan")
    if upcoming_start != active_end + timedelta(days=1):
        raise RuntimeError(
            "Närtidsplan: upcoming_week är inte sammanhängande med aktiv plan"
        )

    result["planned_workouts"] = active_workouts + [
        deepcopy(workout)
        for workout in planned_workouts(upcoming, context="kommande plan")
        if date.fromisoformat(str(workout["date"])) > active_end
    ]
    result["near_term_window"] = {
        "active_week_start": active_start.isoformat(),
        "active_week_end": active_end.isoformat(),
        "upcoming_week_start": upcoming_start.isoformat(),
        "window_end": upcoming_end.isoformat(),
        "calendar_week_is_presentation": True,
    }
    return result
