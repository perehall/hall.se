#!/usr/bin/env python3
import sys
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from migrate_training_data_v3 import materialize_physical_workouts  # noqa: E402


CATALOG = {
    "recipes": {
        "swim_aerobic_technique": {
            "sport": "swim",
            "stimuli": ["swim_aerobic", "swim_technique"],
            "priority_role": "flex",
            "load_dimensions": ["cardiovascular", "technical"],
            "development_focus": "Aerob simning.",
            "options": [
                {
                    "id": "swim-3200",
                    "kind": "structured",
                    "value": 3200,
                    "session": "Simning · 3 200 m · aerob/teknik",
                    "watch_workout": {
                        "type": "Swim",
                        "planned_distance_m": 3200,
                        "equipment": [],
                        "blocks": [],
                    },
                }
            ],
        },
        "strength_core": {
            "sport": "strength",
            "stimuli": ["strength_unilateral", "strength_core"],
            "optional_stimuli": ["plyometric"],
            "priority_role": "protected_support",
            "load_dimensions": ["mechanical", "neuromuscular"],
            "development_focus": "Styrka/core.",
            "performance_marker_id": "strength-repeatability",
            "options": [
                {
                    "id": "strength-25",
                    "kind": "duration_minutes",
                    "value": 25,
                    "session": "Styrka/core · 25 min · styrkemall",
                },
                {
                    "id": "strength-35",
                    "kind": "duration_minutes",
                    "value": 35,
                    "session": "Styrka/core · ca 35 min · styrkemall",
                },
            ],
        },
    }
}


def legacy_document():
    return {
        "schema_version": 3,
        "meta": {
            "microcycle_id": "meso:mc2",
        },
        "days": [
            {
                "date": "2026-10-01",
                "sport": "run",
                "status": "preliminary",
                "session": "Löpning · lugn",
                "microcycle_slot": "run_1",
            },
            {
                "date": "2026-10-02",
                "sport": "strength",
                "status": "preliminary",
                "session": "Simning + styrka",
                "microcycle_slot": "swim_strength_2",
                "stimuli": [
                    "swim_aerobic",
                    "swim_technique",
                    "strength_unilateral",
                    "strength_core",
                ],
                "baseline_option_id": "swim-strength-35",
                "dose_options": [
                    {
                        "id": "swim-strength-35",
                        "kind": "structured",
                        "value": 35,
                        "session": "Simning + styrka",
                    }
                ],
                "dose_resolution": {
                    "state": "baseline",
                    "kind": "structured",
                    "value": 35,
                    "option_id": "swim-strength-35",
                },
                "swim_component": {"planned_distance_m": 3200},
                "watch_workout": {
                    "id": "legacy-swim",
                    "sync_enabled": False,
                    "type": "Swim",
                    "planned_distance_m": 3200,
                    "equipment": [],
                    "blocks": [],
                },
                "workout_design": {"selected_candidate_id": "swim-strength-35"},
            },
        ],
    }


class MultiSessionMigrationTests(unittest.TestCase):
    def test_legacy_composite_becomes_two_independent_workouts(self):
        document = legacy_document()
        self.assertTrue(materialize_physical_workouts(document, deepcopy(CATALOG)))

        workouts = document["planned_workouts"]
        self.assertEqual(len(workouts), 3)
        friday = [item for item in workouts if item["date"] == "2026-10-02"]
        self.assertEqual([item["sport"] for item in friday], ["swim", "strength"])
        self.assertEqual(
            {item["microcycle_slot"] for item in friday},
            {"swim_strength_2:swim", "swim_strength_2:strength"},
        )
        self.assertEqual(friday[0]["baseline_option_id"], "swim-3200")
        self.assertEqual(friday[1]["baseline_option_id"], "strength-35")
        self.assertNotIn("workout_design", friday[0])
        self.assertNotIn("workout_design", friday[1])
        self.assertIn("watch_workout", friday[0])
        self.assertNotIn("watch_workout", friday[1])

        # Calendar rows are compatibility presentation only; migration does not
        # rewrite or reinterpret the seven-day projection.
        self.assertEqual(document["days"][1]["session"], "Simning + styrka")

    def test_migration_is_idempotent(self):
        document = legacy_document()
        self.assertTrue(materialize_physical_workouts(document, deepcopy(CATALOG)))
        snapshot = deepcopy(document["planned_workouts"])
        self.assertFalse(materialize_physical_workouts(document, deepcopy(CATALOG)))
        self.assertEqual(document["planned_workouts"], snapshot)

    def test_linked_legacy_composite_fails_closed(self):
        document = legacy_document()
        document["days"][1]["activity_id"] = 123
        with self.assertRaisesRegex(RuntimeError, "vägrar gissa"):
            materialize_physical_workouts(document, deepcopy(CATALOG))


if __name__ == "__main__":
    unittest.main()
