#!/usr/bin/env python3
import json
from copy import deepcopy
from pathlib import Path

from strategy_contracts import validate_training_strategy
from workout_design import materialize_document, validate_workout_design
from calendar_projection import refresh_calendar_projection


ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
STRATEGY_FILE = ROOT / "data" / "training_strategy.json"
CATALOG_FILE = ROOT / "data" / "workout_catalog.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_if_changed(path, payload):
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    if previous == rendered:
        return False
    path.write_text(rendered, encoding="utf-8")
    return True


def catalog_swim_workouts(catalog):
    by_option_id = {}
    for recipe in (catalog.get("recipes") or {}).values():
        if recipe.get("sport") != "swim":
            continue
        for option in recipe.get("options") or []:
            workout = option.get("watch_workout")
            if not isinstance(workout, dict) or workout.get("type") != "Swim":
                continue
            option_id = str(option.get("id") or "").strip()
            if option_id:
                by_option_id[option_id] = deepcopy(workout)
    return by_option_id


def preferred_option_id(workout):
    for source in (
        workout.get("dose_resolution") or {},
        workout.get("development_step") or {},
    ):
        option_id = str(source.get("option_id") or "").strip()
        if option_id:
            return option_id
    return str(workout.get("baseline_option_id") or "").strip()


def preserve_runtime_watch_fields(canonical, existing):
    refreshed = deepcopy(canonical)
    for field in ("id", "sync_enabled"):
        if field in (existing or {}):
            refreshed[field] = deepcopy(existing[field])
    return refreshed


def refresh_swim_recipes(document, catalog):
    """Refresh only canonical swim workouts from catalog-owned recipes."""

    result = deepcopy(document)
    workouts = result.get("planned_workouts")
    if not isinstance(workouts, list):
        raise RuntimeError(
            "Workout design: planned_workouts saknas; simrecept får inte härledas från days"
        )
    by_option_id = catalog_swim_workouts(catalog)

    for workout in workouts:
        if workout.get("sport") != "swim":
            continue

        for option in workout.get("dose_options") or []:
            option_id = str(option.get("id") or "").strip()
            canonical = by_option_id.get(option_id)
            if canonical is not None:
                option["watch_workout"] = deepcopy(canonical)

        selected_id = preferred_option_id(workout)
        canonical = by_option_id.get(selected_id)
        if canonical is None:
            continue

        existing = workout.get("watch_workout") or {}
        workout["watch_workout"] = preserve_runtime_watch_fields(canonical, existing)
        workout["swim_equipment"] = {
            "planned": deepcopy(canonical.get("equipment") or [])
        }

    refresh_calendar_projection(result)
    return result

def validate_materialized(document, label):
    for collection_name in ("days", "planned_workouts"):
        if collection_name == "planned_workouts" and document.get(collection_name) is None:
            continue
        for index, day in enumerate(document.get(collection_name) or []):
            if day.get("sport") in {"rest", "open"}:
                continue
            validate_workout_design(day, f"{label}.{collection_name}[{index}]")


def main():
    strategy = load_json(STRATEGY_FILE)
    validate_training_strategy(strategy)
    catalog = load_json(CATALOG_FILE)

    changed = []
    counts = []
    for label, path in (("plan", PLAN_FILE), ("upcoming", UPCOMING_FILE)):
        source = refresh_swim_recipes(load_json(path), catalog)
        materialized = materialize_document(source, strategy)
        validate_materialized(materialized, label)
        if write_if_changed(path, materialized):
            changed.append(label)
        counts.append(
            f"{label}="
            + str(
                sum(
                    1
                    for day in (
                        materialized.get("planned_workouts")
                        if materialized.get("planned_workouts") is not None
                        else materialized.get("days") or []
                    )
                    if day.get("sport") not in {"rest", "open"}
                )
            )
        )

    suffix = "uppdaterade " + ", ".join(changed) if changed else "inga dataändringar"
    print("Workout design OK: " + ", ".join(counts) + "; " + suffix + ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
