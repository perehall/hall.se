#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_activity_semantics import apply_semantics, auto_enduro_ride_candidate  # noqa: E402


class EnduroRideFallbackTests(unittest.TestCase):
    def test_actual_sep7_ride_shape_is_normalized_to_enduro_training(self):
        state = {
            "activities": [
                {
                    "id": 20078705519,
                    "name": "Enduro på kvällen",
                    "sport_type": "Ride",
                    "gear_name": "KTM 300 EXC TPI",
                    "start_date_local": "2026-09-07T18:04:35Z",
                    "distance_m": 14637.8,
                    "moving_time_s": 2915,
                    "elapsed_time_s": 5718,
                }
            ]
        }
        _, auto_count, _ = apply_semantics(state, {"schema_version": 1, "overrides": {}})
        activity = state["activities"][0]
        self.assertEqual(auto_count, 1)
        self.assertEqual(activity["source_sport_type"], "Ride")
        self.assertEqual(activity["sport_type"], "Enduro")
        self.assertEqual(activity["classification"], "training")
        self.assertEqual(activity["display_label"], "Enduro")
        self.assertEqual(
            activity["sport_normalization"]["rule"],
            "ride-explicit-enduro-motorcycle-gear-v1",
        )
        self.assertEqual(
            activity["workout_analysis_context"]["enduro"]["session_duration_s"],
            5718.0,
        )
        self.assertEqual(
            activity["workout_analysis_context"]["enduro"]["duration_basis"],
            "elapsed_time_s",
        )

    def test_plain_ride_named_enduro_without_motorcycle_gear_stays_ride(self):
        activity = {
            "name": "Enduro på kvällen",
            "sport_type": "Ride",
            "gear_name": "Specialized Stumpjumper",
        }
        self.assertFalse(auto_enduro_ride_candidate(activity))

    def test_motorcycle_gear_without_enduro_name_does_not_reclassify(self):
        activity = {
            "name": "Kvällstur",
            "sport_type": "Ride",
            "gear_name": "KTM 300 EXC TPI",
        }
        self.assertFalse(auto_enduro_ride_candidate(activity))


if __name__ == "__main__":
    unittest.main()
