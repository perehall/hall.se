#!/usr/bin/env python3
import sys
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from migrate_training_data_v3 import materialize_physical_workouts  # noqa: E402


def canonical_document():
    return {
        "schema_version": 3,
        "days": [
            {
                "date": "2026-10-02",
                "status": "preliminary",
                "sport": "swim",
                "session": "Kalenderprojektion",
            }
        ],
        "planned_workouts": [
            {
                "date": "2026-10-02",
                "sport": "swim",
                "status": "preliminary",
                "session": "Simning",
                "microcycle_slot": "swim-a",
                "workout_key": "w:swim-a",
            },
            {
                "date": "2026-10-02",
                "sport": "strength",
                "status": "preliminary",
                "session": "Styrka",
                "microcycle_slot": "strength-b",
                "workout_key": "w:strength-b",
            },
            {
                "date": "2026-10-02",
                "sport": "run",
                "status": "preliminary",
                "session": "Löpning",
                "microcycle_slot": "run-c",
                "workout_key": "w:run-c",
            },
        ],
    }


class MultiSessionMigrationTests(unittest.TestCase):
    def test_canonical_physical_workouts_are_never_reinterpreted(self):
        document = canonical_document()
        before = deepcopy(document["planned_workouts"])
        self.assertFalse(materialize_physical_workouts(document))
        self.assertEqual(document["planned_workouts"], before)
        self.assertEqual(
            [item["sport"] for item in document["planned_workouts"]],
            ["swim", "strength", "run"],
        )

    def test_runtime_refuses_premultipass_documents_instead_of_guessing(self):
        document = {
            "schema_version": 3,
            "days": [
                {
                    "date": "2026-10-02",
                    "sport": "strength",
                    "status": "preliminary",
                    "session": "Arbitrary legacy calendar row",
                }
            ],
        }
        with self.assertRaisesRegex(RuntimeError, "migreras explicit offline"):
            materialize_physical_workouts(document)

    def test_planned_workouts_must_be_a_collection(self):
        document = {"schema_version": 3, "days": [], "planned_workouts": {}}
        with self.assertRaisesRegex(RuntimeError, "måste vara en lista"):
            materialize_physical_workouts(document)


if __name__ == "__main__":
    unittest.main()
