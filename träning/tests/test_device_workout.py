#!/usr/bin/env python3
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from device_workout import (  # noqa: E402
    DeviceWorkoutError,
    compile_device_workout,
    materialize_day,
    validate_device_workout,
)


def base_day(*, sport="run", candidate_id="run-threshold-3x10", blocks=None):
    return {
        "date": "2026-09-15",
        "status": "preliminary",
        "sport": sport,
        "microcycle_slot": "run_threshold" if sport == "run" else f"{sport}_support",
        "session": "Testpass",
        "workout_design": {
            "schema_version": 1,
            "selected_candidate_id": candidate_id,
            "candidates": [
                {
                    "id": candidate_id,
                    "session": "Löpning · kontrollerad tröskel · 3 × 10 min / 90 s jogg",
                    "prescription": {
                        "executable": True,
                        "completeness": "full",
                        "blocks": blocks
                        or [
                            {
                                "name": "Arbetsdel",
                                "work": {"repetitions": 3, "duration_s": 600},
                                "instruction": "Kontrollerad tröskel",
                                "intensity": "kontrollerad tröskel",
                                "recovery": {
                                    "duration_s": 90,
                                    "instruction": "Lugn jogg",
                                },
                            }
                        ],
                    },
                }
            ],
        },
    }


class DeviceWorkoutTests(unittest.TestCase):
    def test_threshold_compiles_from_selected_candidate_without_invented_target(self):
        workout = compile_device_workout(base_day())
        self.assertEqual(workout["provider_type"], "Run")
        self.assertEqual(workout["blocks"][0]["repetitions_per_set"], 3)
        work, recovery = workout["blocks"][0]["steps"]
        self.assertEqual(work["duration"], {"kind": "time", "seconds": 600})
        self.assertNotIn("target", work)
        self.assertEqual(recovery["duration"], {"kind": "time", "seconds": 90})
        self.assertFalse(recovery["press_lap"])
        self.assertTrue(validate_device_workout(workout, "threshold"))

    def test_hill_jog_recovery_becomes_lap_press_not_guessed_duration(self):
        day = base_day(
            candidate_id="run-hill-3x7x150",
            blocks=[
                {
                    "name": "Backkvalitet",
                    "work": {
                        "sets": 3,
                        "repetitions_per_set": 7,
                        "distance_m": 150,
                    },
                    "instruction": "Kraftfull men kontrollerad",
                    "intensity": "kraftfull men kontrollerad",
                    "recovery": {"instruction": "Lugn joggvila"},
                }
            ],
        )
        workout = compile_device_workout(day)
        block = workout["blocks"][0]
        self.assertEqual(block["sets"], 3)
        self.assertEqual(block["repetitions_per_set"], 7)
        recovery = block["steps"][1]
        self.assertTrue(recovery["press_lap"])
        self.assertTrue(recovery["transport_reference_only"])
        self.assertEqual(recovery["duration"], {"kind": "time", "seconds": 1})

    def test_same_calendar_slot_keeps_external_id_when_dose_changes(self):
        first = compile_device_workout(base_day(candidate_id="run-threshold-3x10"))
        reduced_day = base_day(candidate_id="run-threshold-3x8")
        reduced_day["workout_design"]["candidates"][0]["session"] = (
            "Löpning · kontrollerad tröskel · 3 × 8 min / 90 s jogg"
        )
        reduced_day["workout_design"]["candidates"][0]["prescription"]["blocks"][0][
            "work"
        ]["duration_s"] = 480
        second = compile_device_workout(reduced_day)
        self.assertEqual(first["external_id"], second["external_id"])
        self.assertNotEqual(first["source_hash"], second["source_hash"])

    def test_materializer_preserves_verified_sync_for_unchanged_source(self):
        day = materialize_day(base_day(), in_horizon=True)
        day["device_sync"] = {
            "status": "synced",
            "transport": "intervals_icu",
            "source_hash": day["device_workout"]["source_hash"],
            "device_delivery": "unverified",
            "provider_event_id": 123,
        }
        again = materialize_day(day, in_horizon=True)
        self.assertEqual(again["device_sync"]["status"], "synced")
        self.assertEqual(again["device_sync"]["provider_event_id"], 123)

    def test_source_change_returns_sync_to_pending(self):
        day = materialize_day(base_day(), in_horizon=True)
        day["device_sync"]["status"] = "synced"
        changed = copy.deepcopy(day)
        selected = changed["workout_design"]["candidates"][0]
        selected["prescription"]["blocks"][0]["work"]["duration_s"] = 480
        changed = materialize_day(changed, in_horizon=True)
        self.assertEqual(changed["device_sync"]["status"], "pending")

    def test_strength_is_not_silently_compiled(self):
        with self.assertRaises(DeviceWorkoutError):
            compile_device_workout(base_day(sport="strength"))


if __name__ == "__main__":
    unittest.main()
