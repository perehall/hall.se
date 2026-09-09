#!/usr/bin/env python3
import json
from pathlib import Path

from device_workout import validate_device_workout


ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_document(document, label):
    if document.get("device_workout_schema_version") != 1:
        raise RuntimeError(f"{label}: device_workout_schema_version måste vara 1")
    count = 0
    for index, day in enumerate(document.get("days") or []):
        workout = day.get("device_workout")
        sync = day.get("device_sync")
        if workout is None:
            if sync is not None:
                raise RuntimeError(f"{label}.days[{index}]: device_sync finns utan device_workout")
            continue
        validate_device_workout(workout, f"{label}.days[{index}]")
        if not isinstance(sync, dict):
            raise RuntimeError(f"{label}.days[{index}]: device_sync saknas")
        if sync.get("source_hash") != workout.get("source_hash"):
            raise RuntimeError(f"{label}.days[{index}]: device_sync source_hash avviker")
        if sync.get("transport") != "intervals_icu":
            raise RuntimeError(f"{label}.days[{index}]: device_sync transport ogiltig")
        if sync.get("device_delivery") != "unverified":
            raise RuntimeError(
                f"{label}.days[{index}]: systemet får inte påstå verifiererad leverans till Garmin"
            )
        if sync.get("status") not in {"pending", "synced", "error", "deferred"}:
            raise RuntimeError(f"{label}.days[{index}]: device_sync status ogiltig")
        count += 1
    return count


def main():
    current = validate_document(load_json(PLAN_FILE), "plan")
    upcoming = validate_document(load_json(UPCOMING_FILE), "upcoming")
    print(
        "Device workout contract OK: "
        f"{current} aktuella + {upcoming} kommande enhetsrecept validerade."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
