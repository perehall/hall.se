#!/usr/bin/env python3
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from canonical_plan import planned_workouts as canonical_planned_workouts
from device_workout import materialize_day, validate_device_workout


ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_if_changed(path, payload):
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    if previous == rendered:
        return False
    path.write_text(rendered, encoding="utf-8")
    return True


def _materialize_collection(items, *, today, horizon_end):
    materialized = []
    for day in items or []:
        date_text = str(day.get("date") or "")
        if date_text < today:
            cleaned = dict(day)
            cleaned.pop("device_workout", None)
            cleaned.pop("device_sync", None)
            materialized.append(cleaned)
            continue
        in_horizon = today <= date_text <= horizon_end
        materialized.append(materialize_day(day, in_horizon=in_horizon))
    return materialized


def materialize_document(document, *, today, horizon_end):
    result = dict(document)
    result["device_workout_schema_version"] = 1
    result["planned_workouts"] = _materialize_collection(
        canonical_planned_workouts(document, context="device materialization"),
        today=today,
        horizon_end=horizon_end,
    )
    return result


def validate_document(document, label):
    if document.get("device_workout_schema_version") != 1:
        raise RuntimeError(f"{label}: device_workout_schema_version måste vara 1")
    count = 0
    for index, workout_row in enumerate(
        canonical_planned_workouts(document, context=label)
    ):
        workout = workout_row.get("device_workout")
        if workout is None:
            continue
        context = f"{label}.planned_workouts[{index}]"
        validate_device_workout(workout, context)
        sync = workout_row.get("device_sync") or {}
        if sync.get("source_hash") != workout.get("source_hash"):
            raise RuntimeError(f"{context}: device_sync source_hash avviker")
        if sync.get("status") not in {"pending", "synced", "error", "deferred"}:
            raise RuntimeError(f"{context}: device_sync status ogiltig")
        count += 1
    return count


def main():
    plan = load_json(PLAN_FILE)
    timezone_name = (plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    today_date = datetime.now(ZoneInfo(timezone_name)).date()
    today = today_date.isoformat()
    horizon_end = (today_date + timedelta(days=6)).isoformat()

    changed = []
    counts = []
    for label, path in (("plan", PLAN_FILE), ("upcoming", UPCOMING_FILE)):
        source = load_json(path)
        materialized = materialize_document(source, today=today, horizon_end=horizon_end)
        count = validate_document(materialized, label)
        if write_if_changed(path, materialized):
            changed.append(label)
        counts.append(f"{label}={count}")

    suffix = "uppdaterade " + ", ".join(changed) if changed else "inga dataändringar"
    print(
        "Device workout materialization OK: "
        + ", ".join(counts)
        + f"; horisont {today}–{horizon_end}; {suffix}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
