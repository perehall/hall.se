#!/usr/bin/env python3
import json
from copy import deepcopy
from pathlib import Path

from strategy_contracts import validate_training_strategy
from workout_design import materialize_document, validate_workout_design


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
    by_distance = {}
    for recipe in (catalog.get("recipes") or {}).values():
        for option in recipe.get("options") or []:
            workout = option.get("watch_workout")
            if not isinstance(workout, dict) or workout.get("type") != "Swim":
                continue
            option_id = str(option.get("id") or "").strip()
            if option_id:
                by_option_id[option_id] = deepcopy(workout)
            distance = workout.get("planned_distance_m")
            if isinstance(distance, int) and distance > 0:
                by_distance.setdefault(distance, []).append(deepcopy(workout))
    return by_option_id, by_distance


def preferred_option_id(day):
    for source in (
        day.get("dose_resolution") or {},
        day.get("development_step") or {},
    ):
        option_id = str(source.get("option_id") or "").strip()
        if option_id:
            return option_id
    return str(day.get("baseline_option_id") or "").strip()


def preserve_runtime_watch_fields(canonical, existing):
    refreshed = deepcopy(canonical)
    for field in ("id", "sync_enabled"):
        if field in (existing or {}):
            refreshed[field] = deepcopy(existing[field])
    return refreshed


def refresh_swim_recipes(document, catalog):
    """Refresh executable swim structure without replanning the microcycle.

    The plan owns the selected option. workout_catalog owns the executable
    recipe for that option. This allows wording/equipment fixes to reach an
    already-started week without changing the chosen training stimulus or dose.
    """
    result = deepcopy(document)
    by_option_id, by_distance = catalog_swim_workouts(catalog)

    for day in result.get("days") or []:
        for option in day.get("dose_options") or []:
            option_id = str(option.get("id") or "").strip()
            canonical = by_option_id.get(option_id)
            if canonical is not None:
                option["watch_workout"] = deepcopy(canonical)

        selected_id = preferred_option_id(day)
        canonical = by_option_id.get(selected_id)
        existing = day.get("watch_workout") or {}

        # Composite swim+strength days carry the swim recipe on the day rather
        # than on the strength dose option. Resolve only when distance identifies
        # one canonical swim recipe unambiguously.
        if canonical is None and day.get("swim_component") and existing:
            distance = existing.get("planned_distance_m")
            matches = by_distance.get(distance) or []
            if len(matches) == 1:
                canonical = matches[0]

        if canonical is None:
            continue

        day["watch_workout"] = preserve_runtime_watch_fields(canonical, existing)
        if day.get("sport") == "swim":
            day["swim_equipment"] = {
                "planned": deepcopy(canonical.get("equipment") or [])
            }

    return result


def validate_materialized(document, label):
    for index, day in enumerate(document.get("days") or []):
        if day.get("sport") in {"rest", "open"}:
            continue
        validate_workout_design(day, f"{label}.days[{index}]")


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
