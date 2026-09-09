#!/usr/bin/env python3
import json
from pathlib import Path

from workout_design import WORKOUT_DESIGN_SCHEMA_VERSION, WorkoutDesignError, validate_workout_design


ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_document(document, label):
    if document.get("workout_design_schema_version") != WORKOUT_DESIGN_SCHEMA_VERSION:
        raise WorkoutDesignError(
            f"{label}: workout_design_schema_version måste vara {WORKOUT_DESIGN_SCHEMA_VERSION}"
        )

    count = 0
    for index, day in enumerate(document.get("days") or []):
        if day.get("sport") in {"rest", "open"}:
            continue
        validate_workout_design(day, f"{label}.days[{index}]")
        count += 1
    return count


def main():
    current = validate_document(load_json(PLAN_FILE), "plan")
    upcoming = validate_document(load_json(UPCOMING_FILE), "upcoming")
    print(
        "Workout design contract OK: "
        f"{current} aktuella + {upcoming} kommande pass har rankad och validerad design."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
