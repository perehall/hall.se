#!/usr/bin/env python3
import json
from pathlib import Path

from strategy_contracts import validate_training_strategy
from workout_design import materialize_document, validate_workout_design


ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
STRATEGY_FILE = ROOT / "data" / "training_strategy.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_if_changed(path, payload):
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    if previous == rendered:
        return False
    path.write_text(rendered, encoding="utf-8")
    return True


def validate_materialized(document, label):
    for index, day in enumerate(document.get("days") or []):
        if day.get("sport") in {"rest", "open"}:
            continue
        validate_workout_design(day, f"{label}.days[{index}]")


def main():
    strategy = load_json(STRATEGY_FILE)
    validate_training_strategy(strategy)

    changed = []
    counts = []
    for label, path in (("plan", PLAN_FILE), ("upcoming", UPCOMING_FILE)):
        source = load_json(path)
        materialized = materialize_document(source, strategy)
        validate_materialized(materialized, label)
        if write_if_changed(path, materialized):
            changed.append(label)
        counts.append(
            f"{label}="
            + str(
                sum(
                    1
                    for day in materialized.get("days") or []
                    if day.get("sport") not in {"rest", "open"}
                )
            )
        )

    suffix = "uppdaterade " + ", ".join(changed) if changed else "inga dataändringar"
    print("Workout design OK: " + ", ".join(counts) + "; " + suffix + ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
