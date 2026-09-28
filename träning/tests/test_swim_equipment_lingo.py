#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from device_workout import compile_device_workout  # noqa: E402
from finalize_progression_ui import prescription_html  # noqa: E402
from materialize_workout_designs import refresh_swim_recipes  # noqa: E402
from swim_lingo import equipment_lingo  # noqa: E402


def swim_day():
    blocks = [
        {
            "name": "Insim",
            "work": {"repetitions": 1, "distance_m": 400, "total_distance_m": 400},
            "instruction": "Lugn insim",
            "intensity": "warmup",
            "equipment": [],
        },
        {
            "name": "Kontrollerad tröskel",
            "work": {"repetitions": 4, "distance_m": 200, "total_distance_m": 800},
            "instruction": "Kontrollerad tröskel",
            "intensity": "active",
            "equipment": ["paddles", "pull_buoy"],
            "recovery": {"duration_s": 25},
        },
    ]
    return {
        "date": "2026-09-25",
        "sport": "swim",
        "status": "planned",
        "workout_design": {
            "selected_candidate_id": "swim-test",
            "candidates": [
                {
                    "id": "swim-test",
                    "session": "Simning · test",
                    "prescription": {
                        "executable": True,
                        "completeness": "full",
                        "blocks": blocks,
                    },
                }
            ],
        },
    }


class SwimEquipmentLingoTests(unittest.TestCase):
    def test_standard_swedish_equipment_terms(self):
        self.assertEqual(equipment_lingo([]), "utan redskap")
        self.assertEqual(
            equipment_lingo(["paddles", "pull_buoy"]),
            "paddlar + dolme",
        )
        self.assertEqual(
            equipment_lingo(["fins", "snorkel", "kickboard"]),
            "fenor + snorkel + platta",
        )

    def test_web_prescription_marks_equipment_on_every_swim_set(self):
        rendered = prescription_html(swim_day())
        self.assertIn("Lugn insim · utan redskap", rendered)
        self.assertIn("Kontrollerad tröskel · paddlar + dolme · v 25 s", rendered)
        self.assertNotIn("vila 25 s", rendered)

    def test_device_instruction_keeps_equipment_explicit(self):
        workout = compile_device_workout(swim_day())
        self.assertEqual(
            workout["blocks"][0]["steps"][0]["instruction"],
            "Lugn insim · utan redskap",
        )
        self.assertEqual(
            workout["blocks"][1]["steps"][0]["instruction"],
            "Kontrollerad tröskel · paddlar + dolme",
        )

    def test_catalog_recipe_refresh_reaches_started_week_without_replanning(self):
        stale = {
            "days": [
                {
                    "date": "2026-09-25",
                    "sport": "swim",
                    "baseline_option_id": "swim-4000",
                    "dose_resolution": {"option_id": "swim-4000"},
                    "dose_options": [
                        {
                            "id": "swim-4000",
                            "watch_workout": {
                                "type": "Swim",
                                "equipment": ["paddles", "pull_buoy"],
                                "planned_distance_m": 4000,
                                "blocks": [],
                            },
                        }
                    ],
                    "watch_workout": {
                        "id": "dated-workout-id",
                        "sync_enabled": False,
                        "type": "Swim",
                        "equipment": ["paddles", "pull_buoy"],
                        "planned_distance_m": 4000,
                        "blocks": [],
                    },
                }
            ]
        }
        catalog = {
            "recipes": {
                "swim": {
                    "options": [
                        {
                            "id": "swim-4000",
                            "watch_workout": {
                                "type": "Swim",
                                "equipment": ["paddles", "pull_buoy"],
                                "planned_distance_m": 4000,
                                "blocks": [
                                    {
                                        "name": "Tröskel",
                                        "steps": [
                                            {
                                                "kind": "swim",
                                                "text": "Kontrollerad tröskel",
                                                "distance_m": 200,
                                                "equipment": ["paddles", "pull_buoy"],
                                            }
                                        ],
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }

        refreshed = refresh_swim_recipes(stale, catalog)
        day = refreshed["days"][0]
        step = day["dose_options"][0]["watch_workout"]["blocks"][0]["steps"][0]
        self.assertEqual(step["equipment"], ["paddles", "pull_buoy"])
        self.assertEqual(day["watch_workout"]["id"], "dated-workout-id")
        self.assertFalse(day["watch_workout"]["sync_enabled"])
        self.assertEqual(
            day["swim_equipment"]["planned"],
            ["paddles", "pull_buoy"],
        )


if __name__ == "__main__":
    unittest.main()
