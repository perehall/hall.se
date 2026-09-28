#!/usr/bin/env python3
import json
from copy import deepcopy
from pathlib import Path

from training_contracts import PLAN_SCHEMA_VERSION, VALID_PLAN_SPORTS

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILES = [ROOT / "data" / "plan.json", ROOT / "data" / "upcoming_week.json"]
COACH_FILE = ROOT / "data" / "coach.json"
CATALOG_FILE = ROOT / "data" / "workout_catalog.json"

# One-time reviewed migration. No sport is inferred from Swedish free text.
# Unknown dates fail closed instead of being guessed.
SPORT_BY_DATE = {
    "2026-08-17": "swim",
    "2026-08-18": "strength",
    "2026-08-19": "swimrun",
    "2026-08-20": "run",
    "2026-08-21": "swim",
    "2026-08-22": "enduro",
    "2026-08-23": "run",
    "2026-08-24": "enduro",
    "2026-08-25": "swim",
    "2026-08-26": "run",
    "2026-08-27": "strength",
    "2026-08-28": "swim",
    "2026-08-29": "bike",
    "2026-08-30": "open",
}



def _legacy_composite_swim_strength(day):
    """Recognize only the retired pre-multi-session representation.

    This is migration-only compatibility code. Runtime planning must never
    create this shape again.
    """
    slot = str(day.get("microcycle_slot") or "").strip()
    stimuli = set(day.get("stimuli") or [])
    return (
        slot.startswith("swim_strength_")
        or (
            day.get("swim_component") is not None
            and {"swim_aerobic", "strength_core"}.issubset(stimuli)
        )
    )


def _selected_numeric_value(day):
    resolution = day.get("dose_resolution") or {}
    value = resolution.get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    baseline_id = str(day.get("baseline_option_id") or "").strip()
    for option in day.get("dose_options") or []:
        if str(option.get("id") or "").strip() != baseline_id:
            continue
        value = option.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _select_option(recipe, *, value=None, planned_distance_m=None):
    options = recipe.get("options") or []
    if planned_distance_m is not None:
        for option in options:
            workout = option.get("watch_workout") or {}
            if workout.get("planned_distance_m") == planned_distance_m:
                return deepcopy(option)
    if value is not None:
        for option in options:
            candidate = option.get("value")
            if isinstance(candidate, (int, float)) and float(candidate) == float(value):
                return deepcopy(option)
    if len(options) == 1:
        return deepcopy(options[0])
    raise RuntimeError("Multi-session migration: kan inte välja kanoniskt dosalternativ utan att gissa")


def _base_workout(day, *, slot_suffix):
    workout = deepcopy(day)
    original_slot = str(day.get("microcycle_slot") or "legacy").strip()
    workout["microcycle_slot"] = f"{original_slot}:{slot_suffix}"
    workout.pop("workout_key", None)
    workout.pop("additional_planned_workouts", None)
    workout.pop("workout_design", None)
    workout.pop("device_workout", None)
    if workout.get("activity_id") is not None or workout.get("activity_ids"):
        raise RuntimeError(
            f"Multi-session migration: {day.get('date')} har redan aktivitetslänk på ett äldre kombinationspass; vägrar gissa fördelning"
        )
    return workout


def _apply_recipe(workout, recipe, option):
    workout["sport"] = recipe["sport"]
    workout["session"] = option["session"]
    workout["stimuli"] = deepcopy(recipe.get("stimuli") or [])
    workout["load_dimensions"] = deepcopy(recipe.get("load_dimensions") or [])
    workout["priority_role"] = recipe.get("priority_role") or workout.get("priority_role")
    workout["development_focus"] = recipe["development_focus"]
    workout["dose_options"] = deepcopy(recipe.get("options") or [])
    workout["baseline_option_id"] = option["id"]
    workout["dose_resolution"] = {
        "state": "baseline",
        "kind": option["kind"],
        "value": option["value"],
        "option_id": option["id"],
    }
    if recipe.get("optional_stimuli"):
        workout["optional_stimuli"] = deepcopy(recipe["optional_stimuli"])
    else:
        workout.pop("optional_stimuli", None)
    if recipe.get("performance_marker_id"):
        workout["performance_marker_id"] = recipe["performance_marker_id"]
    else:
        workout.pop("performance_marker_id", None)


def _split_legacy_composite(day, catalog):
    recipes = catalog.get("recipes") or {}
    swim_recipe = recipes.get("swim_aerobic_technique") or {}
    strength_recipe = recipes.get("strength_core") or {}
    if not swim_recipe or not strength_recipe:
        raise RuntimeError("Multi-session migration: kanoniska sim-/styrkerecept saknas")

    existing_watch = day.get("watch_workout") or {}
    planned_distance = existing_watch.get("planned_distance_m")
    if not isinstance(planned_distance, int) or planned_distance <= 0:
        planned_distance = (day.get("swim_component") or {}).get("planned_distance_m")
    swim_option = _select_option(
        swim_recipe,
        planned_distance_m=planned_distance,
    )
    strength_option = _select_option(
        strength_recipe,
        value=_selected_numeric_value(day),
    )

    swim = _base_workout(day, slot_suffix="swim")
    _apply_recipe(swim, swim_recipe, swim_option)
    swim["reason"] = (
        "Den redan planerade simexponeringen ligger kvar som ett självständigt pass på samma datum."
    )
    canonical_watch = deepcopy(swim_option.get("watch_workout") or {})
    if existing_watch:
        for field in ("id", "sync_enabled", "external_id"):
            if field in existing_watch:
                canonical_watch[field] = deepcopy(existing_watch[field])
    if canonical_watch:
        swim["watch_workout"] = canonical_watch
        swim["swim_equipment"] = {
            "planned": deepcopy(canonical_watch.get("equipment") or [])
        }
    swim.pop("swim_component", None)

    strength = _base_workout(day, slot_suffix="strength")
    _apply_recipe(strength, strength_recipe, strength_option)
    strength["reason"] = (
        "Den redan planerade styrka/core-exponeringen ligger kvar som ett självständigt pass på samma datum."
    )
    for field in ("watch_workout", "swim_component", "swim_equipment"):
        strength.pop(field, None)

    return [swim, strength]


def _standalone_legacy_workout(day):
    workout = deepcopy(day)
    if not str(workout.get("microcycle_slot") or "").strip():
        date_value = str(workout.get("date") or "").strip()
        sport = str(workout.get("sport") or "training").strip().lower()
        if not date_value:
            raise RuntimeError("Multi-session migration: fristående pass saknar datum")
        workout["microcycle_slot"] = f"legacy-{date_value}-{sport}"
    workout.pop("workout_key", None)
    workout.pop("additional_planned_workouts", None)
    return workout


def materialize_physical_workouts(document, catalog):
    """Upgrade the calendar projection to canonical 0..N workout identity.

    days remains a seven-row compatibility projection for the legacy UI.
    planned_workouts becomes the physical-workout collection used by the
    canonical backend and v2 presentation. The only split performed here is
    the explicitly retired legacy swim_strength representation.
    """
    if document.get("planned_workouts") is not None:
        return False

    workouts = []
    for day in document.get("days") or []:
        sport = str(day.get("sport") or "").strip().lower()
        if sport in {"", "open", "rest"}:
            continue
        if _legacy_composite_swim_strength(day):
            workouts.extend(_split_legacy_composite(day, catalog))
        else:
            workouts.append(_standalone_legacy_workout(day))

    document["planned_workouts"] = workouts
    return True

def migrate_plan(path, catalog):
    if not path.exists():
        return False
    document = json.loads(path.read_text(encoding="utf-8"))
    version = document.get("schema_version")
    if version == PLAN_SCHEMA_VERSION:
        for day in document.get("days", []):
            if day.get("sport") not in VALID_PLAN_SPORTS:
                raise RuntimeError(f"Migration v3: {path.name} har ogiltig sport för {day.get('date')}")
        changed = materialize_physical_workouts(document, catalog)
        if changed:
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return changed
    if version not in (None, 2):
        raise RuntimeError(f"Migration v3: stöder inte schema_version {version!r} i {path.name}")

    for day in document.get("days", []):
        day_date = day.get("date")
        expected = SPORT_BY_DATE.get(day_date)
        if not expected:
            raise RuntimeError(
                f"Migration v3: saknar explicit, granskad sportmapping för {day_date!r}; vägrar gissa"
            )
        existing = day.get("sport")
        if existing and existing != expected:
            raise RuntimeError(
                f"Migration v3: {day_date} har sport {existing!r}, men migrationen förväntar {expected!r}"
            )
        day["sport"] = expected

    document["schema_version"] = PLAN_SCHEMA_VERSION
    materialize_physical_workouts(document, catalog)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def migrate_coach_history():
    if not COACH_FILE.exists():
        return False
    document = json.loads(COACH_FILE.read_text(encoding="utf-8"))
    changed = False
    for entry in document.get("analyses") or []:
        assessment = entry.get("assessment") or {}
        if assessment.get("confidence") == "high" and assessment.get("unknowns"):
            assessment["confidence"] = "medium"
            changed = True
    if changed:
        COACH_FILE.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main():
    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    changed = [path.name for path in PLAN_FILES if migrate_plan(path, catalog)]
    if migrate_coach_history():
        changed.append(COACH_FILE.name)
    if changed:
        print("Migration v3 OK: " + ", ".join(changed))
    else:
        print("Migration v3: redan migrerat; inga ändringar.")


if __name__ == "__main__":
    main()
