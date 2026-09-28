#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from calendar_projection import refresh_calendar_projection  # noqa: E402


class PhysicalWorkoutArchitectureTests(unittest.TestCase):
    def test_catalog_contains_only_single_sport_recipes_unless_explicit_multisport(self):
        catalog = json.loads(
            (ROOT / "data" / "workout_catalog.json").read_text(encoding="utf-8")
        )
        prefixes = {
            "run": ("run_",),
            "swim": ("swim_",),
            "strength": ("strength_", "plyometric"),
            "bike": ("mtb_", "bike_"),
            "enduro": ("enduro_",),
        }
        for key, recipe in (catalog.get("recipes") or {}).items():
            families = {
                family
                for family, family_prefixes in prefixes.items()
                if any(
                    any(str(stimulus).startswith(prefix) for prefix in family_prefixes)
                    for stimulus in (
                        list(recipe.get("stimuli") or [])
                        + list(recipe.get("optional_stimuli") or [])
                    )
                )
            }
            sport = str(recipe.get("sport") or "")
            if sport == "multisport":
                continue
            self.assertLessEqual(
                len(families),
                1,
                f"{key} mixes physical sport families {sorted(families)}",
            )

    def test_current_canonical_workouts_do_not_mix_physical_sport_families(self):
        plan = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))
        family_prefixes = {
            "run": ("run_",),
            "swim": ("swim_",),
            "strength": ("strength_", "plyometric"),
            "bike": ("mtb_", "bike_"),
            "enduro": ("enduro_",),
        }
        for workout in plan.get("planned_workouts") or []:
            sport = str(workout.get("sport") or "")
            if sport in {"multisport", "open", "rest"}:
                continue
            stimuli = list(workout.get("stimuli") or []) + list(
                workout.get("optional_stimuli") or []
            )
            families = {
                family
                for family, prefixes in family_prefixes.items()
                if any(
                    any(str(stimulus).startswith(prefix) for prefix in prefixes)
                    for stimulus in stimuli
                )
            }
            self.assertLessEqual(
                len(families),
                1,
                f"{workout.get('date')} {workout.get('session')} mixes {sorted(families)}",
            )

    def test_active_runtime_has_no_composite_same_day_workout_concept(self):
        active_sources = (
            ROOT / "scripts" / "adaptive_planner.py",
            ROOT / "scripts" / "workout_design.py",
            ROOT / "scripts" / "migrate_training_data_v3.py",
            ROOT / "scripts" / "rollover_week.py",
            ROOT / "scripts" / "materialize_workout_designs.py",
        )
        forbidden_tokens = (
            "swim_" + "strength",
            "swim_component",
            "Composite support day",
            "kombinerade dagen",
        )
        for path in active_sources:
            source = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                self.assertNotIn(
                    token,
                    source,
                    f"{path.name} must not contain composite workout semantics: {token}",
                )

    def test_current_runtime_documents_have_no_retired_composite_fields(self):
        for filename in ("plan.json", "upcoming_week.json"):
            document = json.loads(
                (ROOT / "data" / filename).read_text(encoding="utf-8")
            )

            def assert_clean(value, path="root"):
                if isinstance(value, list):
                    for index, item in enumerate(value):
                        assert_clean(item, f"{path}[{index}]")
                    return
                if not isinstance(value, dict):
                    return
                self.assertNotIn(
                    "swim_component",
                    value,
                    f"{filename}:{path} contains retired composite state",
                )
                for key, item in value.items():
                    assert_clean(item, f"{path}.{key}")

            assert_clean(document)

    def test_active_runtime_documents_have_no_retired_composite_identifiers(self):
        retired = "swim_" + "strength"
        for filename in ("plan.json", "upcoming_week.json"):
            document = json.loads(
                (ROOT / "data" / filename).read_text(encoding="utf-8")
            )

            def walk(value):
                if isinstance(value, dict):
                    for key, item in value.items():
                        yield str(key)
                        yield from walk(item)
                elif isinstance(value, list):
                    for item in value:
                        yield from walk(item)
                elif isinstance(value, str):
                    yield value

            offenders = [value for value in walk(document) if retired in value]
            self.assertEqual(
                offenders,
                [],
                f"{filename} contains retired composite identity/state: {offenders[:5]}",
            )

    def test_calendar_projection_does_not_merge_three_same_day_workouts(self):
        document = {
            "days": [
                {
                    "date": "2026-10-02",
                    "label": "Fredag",
                    "status": "preliminary",
                    "sport": "open",
                    "session": "Old cache",
                }
            ],
            "planned_workouts": [
                {
                    "date": "2026-10-02",
                    "status": "preliminary",
                    "sport": "run",
                    "session": "Löpning",
                    "microcycle_slot": "run-a",
                },
                {
                    "date": "2026-10-02",
                    "status": "preliminary",
                    "sport": "bike",
                    "session": "MTB",
                    "microcycle_slot": "bike-b",
                },
                {
                    "date": "2026-10-02",
                    "status": "preliminary",
                    "sport": "strength",
                    "session": "Styrka",
                    "microcycle_slot": "strength-c",
                },
            ],
        }
        self.assertTrue(refresh_calendar_projection(document))
        day = document["days"][0]
        self.assertEqual(day["session"], "Löpning")
        self.assertEqual(day["additional_planned_workouts"], 2)
        self.assertEqual(
            [workout["session"] for workout in document["planned_workouts"]],
            ["Löpning", "MTB", "Styrka"],
        )


if __name__ == "__main__":
    unittest.main()
