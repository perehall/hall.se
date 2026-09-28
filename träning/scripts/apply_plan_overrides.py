#!/usr/bin/env python3
"""Apply durable, user-confirmed calendar overrides to mutable plan documents.

The generated plan is allowed to evolve as activities and recovery are assessed,
but a user-confirmed future commitment must survive both scheduled rebuilds and
calendar rollover. This small sidecar layer is deliberately deterministic: it
only touches an explicitly named date, never rewrites completed truth, and
removes derived workout state that belongs to the session being replaced.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERRIDES_FILE = ROOT / "data" / "plan_overrides.json"
PLAN_FILES = (
    ROOT / "data" / "plan.json",
    ROOT / "data" / "upcoming_week.json",
)

# These fields are regenerated from the selected session later in the pipeline.
# Clear them when an override actually replaces a session, but preserve the
# newly generated state when the same override is re-applied during rendering.
SESSION_DERIVED_FIELDS = {
    "workout_design",
    "device_workout",
    "device_sync",
}


class PlanOverrideError(RuntimeError):
    pass


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_config(config: dict) -> list[dict]:
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise PlanOverrideError("plan overrides: schema_version måste vara 1")
    overrides = config.get("overrides")
    if not isinstance(overrides, list):
        raise PlanOverrideError("plan overrides: overrides måste vara en lista")

    seen_targets: set[tuple[str, str]] = set()
    date_only_targets: set[str] = set()
    for index, override in enumerate(overrides):
        context = f"plan overrides[{index}]"
        if not isinstance(override, dict):
            raise PlanOverrideError(f"{context}: måste vara objekt")
        target_date = str(override.get("date") or "").strip()
        if not target_date:
            raise PlanOverrideError(f"{context}: date saknas")
        target_key = str(override.get("workout_key") or "").strip()
        identity = (target_date, target_key)
        if identity in seen_targets:
            raise PlanOverrideError(
                f"{context}: dubblerat override-mål {target_date} {target_key!r}"
            )
        if not target_key:
            if target_date in date_only_targets:
                raise PlanOverrideError(
                    f"{context}: flera date-only overrides för {target_date}"
                )
            date_only_targets.add(target_date)
        seen_targets.add(identity)
        if not isinstance(override.get("set") or {}, dict):
            raise PlanOverrideError(f"{context}: set måste vara objekt")
        if not isinstance(override.get("set_meta") or {}, dict):
            raise PlanOverrideError(f"{context}: set_meta måste vara objekt")
        remove_fields = override.get("remove_fields") or []
        if not isinstance(remove_fields, list) or not all(isinstance(value, str) for value in remove_fields):
            raise PlanOverrideError(f"{context}: remove_fields måste vara en lista av strängar")
    return overrides


def _workout_key(workout: dict, meta: dict) -> str:
    explicit = str(workout.get("workout_key") or "").strip()
    if explicit:
        return explicit
    microcycle_id = str(
        workout.get("microcycle_id") or meta.get("microcycle_id") or ""
    ).strip()
    slot = str(workout.get("microcycle_slot") or "").strip()
    date_value = str(workout.get("date") or "").strip()
    if microcycle_id and slot and date_value:
        return f"{microcycle_id}:{date_value}:{slot}"
    return ""


def _target_workout(document: dict, override: dict):
    target_date = str(override.get("date") or "").strip()
    target_key = str(override.get("workout_key") or "").strip()
    physical = document.get("planned_workouts")

    if isinstance(physical, list):
        matches = [
            workout
            for workout in physical
            if isinstance(workout, dict)
            and workout.get("date") == target_date
            and (
                not target_key
                or _workout_key(workout, document.get("meta") or {}) == target_key
            )
        ]
        if target_key and len(matches) != 1:
            raise PlanOverrideError(
                f"plan overrides: workout_key {target_key!r} matchar {len(matches)} pass"
            )
        if not target_key and len(matches) > 1:
            raise PlanOverrideError(
                f"plan overrides: {target_date} har {len(matches)} pass; workout_key krävs"
            )
        if matches:
            return matches[0], True

    days = document.get("days") or []
    matches = [
        day
        for day in days
        if isinstance(day, dict) and day.get("date") == target_date
    ]
    if len(matches) > 1:
        raise PlanOverrideError(
            f"plan overrides: kalenderdatum {target_date} förekommer {len(matches)} gånger"
        )
    return (matches[0], False) if matches else (None, False)


def _refresh_calendar_projection(document: dict, target_date: str) -> None:
    physical = document.get("planned_workouts")
    if not isinstance(physical, list):
        return
    calendar = next(
        (
            day
            for day in document.get("days") or []
            if isinstance(day, dict) and day.get("date") == target_date
        ),
        None,
    )
    if calendar is None:
        return
    candidates = [
        workout
        for workout in physical
        if workout.get("date") == target_date
        and workout.get("sport") not in {"open", "rest"}
    ]
    if not candidates:
        return
    source = candidates[0]
    label = calendar.get("label")
    date_value = calendar.get("date")
    calendar.clear()
    calendar.update(deepcopy(source))
    if label is not None:
        calendar["label"] = label
    calendar["date"] = date_value


def apply_overrides(document: dict, config: dict) -> int:
    """Apply matching overrides and return the number of documents changed (0/1)."""
    overrides = _validate_config(config)
    days = document.get("days")
    if not isinstance(days, list):
        raise PlanOverrideError("plan overrides: dokumentet saknar days-lista")

    changed = False
    for override in overrides:
        target_date = str(override["date"])
        day, is_physical_workout = _target_workout(document, override)
        if day is None:
            continue
        # Completed activity truth wins over a stale future commitment.
        if day.get("status") == "completed":
            continue

        before_day = deepcopy(day)
        before_meta = deepcopy(document.get("meta") or {})
        set_values = deepcopy(override.get("set") or {})

        replacement_session = str(set_values.get("session") or "").strip()
        existing_session = str(day.get("session") or "").strip()
        session_is_replaced = bool(replacement_session and replacement_session != existing_session)
        if session_is_replaced and existing_session:
            day.setdefault("original_session", existing_session)

        for field in override.get("remove_fields") or []:
            if (
                field in SESSION_DERIVED_FIELDS
                and replacement_session
                and not session_is_replaced
            ):
                continue
            day.pop(field, None)
        day.update(set_values)
        day["manual_override"] = {
            "source": str(override.get("source") or "user_confirmed"),
            "note": str(override.get("note") or "").strip(),
        }

        meta_updates = deepcopy(override.get("set_meta") or {})
        if meta_updates:
            meta = document.setdefault("meta", {})
            if not isinstance(meta, dict):
                raise PlanOverrideError("plan overrides: document.meta måste vara objekt")
            meta.update(meta_updates)

        row_changed = day != before_day
        if row_changed and is_physical_workout:
            _refresh_calendar_projection(document, target_date)
        changed = changed or row_changed or (document.get("meta") or {}) != before_meta

    return 1 if changed else 0


def main() -> int:
    if not OVERRIDES_FILE.is_file():
        print("PLAN_OVERRIDES_OK no-sidecar")
        return 0

    config = load_json(OVERRIDES_FILE)
    changed_files = 0
    for path in PLAN_FILES:
        if not path.is_file():
            continue
        document = load_json(path)
        changed = apply_overrides(document, config)
        if changed:
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed_files += 1
            print(f"PLAN_OVERRIDE_APPLIED {path.relative_to(ROOT)}")

    print(f"PLAN_OVERRIDES_OK changed_files={changed_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
