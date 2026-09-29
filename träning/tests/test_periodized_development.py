#!/usr/bin/env python3
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from adaptive_planner import (  # noqa: E402
    fallback_microcycle,
    materialize_template,
    mesocycle_block_context,
    microcycle_guard_failures,
)


class PeriodizedDevelopmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(
            (ROOT / "data" / "planning_policy.json").read_text(encoding="utf-8")
        )
        cls.catalog = json.loads(
            (ROOT / "data" / "workout_catalog.json").read_text(encoding="utf-8")
        )
        cls.meso = {
            "id": "test-swim-block",
            "start_date": "2026-09-21",
            "end_date": "2026-10-18",
            "duration_weeks": 4,
            "primary_capabilities": ["swim_aerobic", "swim_technique"],
            "secondary_capabilities": ["run_easy_distance"],
        }

    def test_four_week_block_has_establish_develop_develop_consolidate_wave(self):
        expected = ["establish", "develop", "develop", "consolidate"]
        for offset_weeks, intent in enumerate(expected):
            context = mesocycle_block_context(
                self.meso,
                date(2026, 9, 21 + 7 * offset_weeks)
                if offset_weeks < 2
                else date(2026, 10, 5 + 7 * (offset_weeks - 2)),
                self.policy,
            )
            self.assertEqual(context["block_intent"], intent)
            self.assertEqual(context["wave"], expected)

    def test_fallback_uses_distinct_swim_characters_instead_of_duplicate_template(self):
        result = fallback_microcycle(
            self.meso,
            self.policy,
            self.catalog,
            date(2026, 9, 28),
            completed_context={
                "swim_exposures": 0,
                "strength_exposures": 0,
                "direct_capabilities": [],
            },
        )
        swim_rows = [
            row
            for row in result["slots"]
            if "swim_aerobic"
            in set(self.catalog["recipes"][row["recipe_key"]].get("stimuli") or [])
        ]
        self.assertGreaterEqual(len(swim_rows), 2)
        recipe_keys = [row["recipe_key"] for row in swim_rows]
        self.assertEqual(len(recipe_keys), len(set(recipe_keys)))
        characters = {
            self.catalog["recipes"][key].get("development_character")
            for key in recipe_keys
        }
        self.assertGreaterEqual(len(characters), 2)

    def test_develop_microcycle_rejects_duplicate_primary_recipe(self):
        duplicate = {
            "rationale": "test",
            "slots": [
                {
                    "day_index": 2,
                    "recipe_key": "swim_aerobic_technique",
                    "action": "consolidate",
                    "rationale": "first",
                    "evidence_refs": [],
                },
                {
                    "day_index": 4,
                    "recipe_key": "swim_aerobic_technique",
                    "action": "consolidate",
                    "rationale": "duplicate",
                    "evidence_refs": [],
                },
                {
                    "day_index": 5,
                    "recipe_key": "strength_core",
                    "action": "consolidate",
                    "rationale": "protected",
                    "evidence_refs": [],
                },
                {
                    "day_index": 7,
                    "recipe_key": "run_easy_distance",
                    "action": "consolidate",
                    "rationale": "secondary",
                    "evidence_refs": [],
                },
            ],
        }
        failures = microcycle_guard_failures(
            duplicate,
            self.meso,
            self.policy,
            self.catalog,
            date(2026, 9, 28),
            completed_context={
                "swim_exposures": 0,
                "strength_exposures": 0,
                "completed_slot_days": 0,
                "direct_capabilities": [],
            },
        )
        self.assertTrue(
            any("upprepas 2 gånger i en develop-mikrocykel" in item for item in failures),
            failures,
        )

    def test_new_aerobic_endurance_swim_is_3600m_and_distinct(self):
        recipe = self.catalog["recipes"]["swim_aerobic_endurance"]
        option = recipe["options"][0]
        workout = option["watch_workout"]
        total = 0
        for block in workout["blocks"]:
            repeat = int(block.get("repeat", 1))
            for step in block.get("steps") or []:
                if step.get("kind") == "swim":
                    total += repeat * int(step["distance_m"])
        self.assertEqual(total, 3600)
        self.assertEqual(total, workout["planned_distance_m"])
        self.assertEqual(recipe["development_character"], "aerobic_endurance")
        self.assertNotEqual(
            recipe["development_character"],
            self.catalog["recipes"]["swim_aerobic_technique"]["development_character"],
        )

    def test_materialized_workout_keeps_recipe_identity_and_block_intent(self):
        micro = {
            "week_start": "2026-09-28",
            "slots": [
                {
                    "day_index": 2,
                    "recipe_key": "swim_aerobic_endurance",
                    "action": "establish",
                    "rationale": "Different development character.",
                    "evidence_refs": [],
                }
            ],
        }
        template, _ = materialize_template(
            self.meso,
            micro,
            self.policy,
            self.catalog,
            {},
        )
        self.assertEqual(template[0]["recipe_key"], "swim_aerobic_endurance")
        self.assertEqual(template[0]["development_character"], "aerobic_endurance")
        self.assertEqual(template[0]["block_intent"], "develop")


if __name__ == "__main__":
    unittest.main()
