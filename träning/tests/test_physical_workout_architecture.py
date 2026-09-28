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

    def test_active_runtime_has_no_composite_swim_strength_concept(self):
        active_sources = (
            ROOT / "scripts" / "adaptive_planner.py",
            ROOT / "scripts" / "workout_design.py",
            ROOT / "scripts" / "migrate_training_data_v3.py",
        )
        forbidden = "swim_" + "strength"
        for path in active_sources:
            self.assertNotIn(
                forbidden,
                path.read_text(encoding="utf-8"),
                f"{path.name} must not contain composite workout semantics",
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
