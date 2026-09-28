"""Compatibility projection from canonical physical workouts to calendar rows.

Physical workout identity lives only in planned_workouts. days is a seven-row
calendar cache for remaining legacy consumers and must never invent, merge or
split workouts. When several workouts share a date, the first canonical workout
is projected and additional_planned_workouts records how many more exist.
"""

from __future__ import annotations

from copy import deepcopy

PROJECTED_FIELDS = (
    "status",
    "planning_status",
    "session",
    "reason",
    "development_focus",
    "sport",
    "classification",
    "manual_lock",
    "priority_role",
    "stimuli",
    "load_dimensions",
    "mesocycle_id",
    "microcycle_id",
    "microcycle_index",
    "microcycle_day",
    "microcycle_slot",
    "dose_options",
    "baseline_option_id",
    "dose_resolution",
    "dose_open",
    "workout_design",
    "device_workout",
    "device_sync",
    "watch_workout",
    "swim_equipment",
    "coach_adjustment",
    "auto_coach",
    "original_session",
)


def canonical_workouts(document: dict) -> list[dict]:
    workouts = document.get("planned_workouts")
    if workouts is None:
        raise RuntimeError(
            "Kalenderprojektion: planned_workouts saknas; fysisk träningsidentitet "
            "får inte härledas från days"
        )
    if not isinstance(workouts, list):
        raise RuntimeError("Kalenderprojektion: planned_workouts måste vara en lista")
    return [
        workout
        for workout in workouts
        if isinstance(workout, dict)
        and str(workout.get("sport") or "").strip().lower() not in {"", "open", "rest"}
    ]


def refresh_calendar_projection(
    document: dict,
    *,
    target_date: str | None = None,
    fallback: dict | None = None,
) -> bool:
    """Refresh the non-authoritative seven-row calendar cache generically."""

    days = document.get("days") or []
    if not isinstance(days, list):
        raise RuntimeError("Kalenderprojektion: days måste vara en lista")

    by_date: dict[str, list[dict]] = {}
    for workout in canonical_workouts(document):
        date_value = str(workout.get("date") or "").strip()
        if not date_value:
            raise RuntimeError("Kalenderprojektion: planned workout saknar datum")
        by_date.setdefault(date_value, []).append(workout)

    changed = False
    for calendar_day in days:
        if not isinstance(calendar_day, dict):
            continue
        date_value = str(calendar_day.get("date") or "").strip()
        if not date_value or (target_date is not None and date_value != target_date):
            continue

        candidates = by_date.get(date_value, [])
        source = candidates[0] if candidates else fallback
        if not source:
            if calendar_day.pop("additional_planned_workouts", None) is not None:
                changed = True
            continue

        before = deepcopy(calendar_day)
        label = calendar_day.get("label")
        for field in PROJECTED_FIELDS:
            if field in source:
                calendar_day[field] = deepcopy(source[field])
            else:
                calendar_day.pop(field, None)
        if label is not None:
            calendar_day["label"] = label
        calendar_day["date"] = date_value

        extra = max(0, len(candidates) - 1)
        if extra:
            calendar_day["additional_planned_workouts"] = extra
        else:
            calendar_day.pop("additional_planned_workouts", None)

        if calendar_day != before:
            changed = True

    return changed
