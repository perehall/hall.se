#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workout_analysis_context import (  # noqa: E402
    WORKOUT_ANALYSIS_CONTRACT_VERSION,
    build_workout_analysis_context,
    fmt_pace,
    pace_s_per_km,
)


class WorkoutAnalysisContextTests(unittest.TestCase):
    def test_run_pace_is_derived_from_time_and_distance_not_raw_average_speed(self):
        activity = {
            "id": 20057585521,
            "sport_type": "Run",
            "display_label": "Löpning · distans",
            "distance_m": 22001.5,
            "moving_time_s": 6960,
            "elapsed_time_s": 6960,
            "average_speed": 3.16,
            "average_heartrate": 139.0,
            "max_heartrate": 164.0,
            "laps": [
                {
                    "lap_index": 1,
                    "distance_m": 1000.0,
                    "moving_time_s": 322,
                    "average_speed": 3.11,
                    "average_heartrate": 128.0,
                },
                {
                    "lap_index": 21,
                    "distance_m": 1000.0,
                    "moving_time_s": 264,
                    "average_speed": 3.79,
                    "average_heartrate": 157.3,
                },
            ],
        }

        context = build_workout_analysis_context(activity)
        self.assertEqual(context["contract_version"], WORKOUT_ANALYSIS_CONTRACT_VERSION)
        self.assertEqual(context["run"]["average_pace"], "5:16/km")
        self.assertAlmostEqual(context["run"]["average_pace_s_per_km"], 316.34, places=2)
        self.assertEqual(context["run"]["source_laps_near_1km"][0]["pace"], "5:22/km")
        self.assertEqual(context["run"]["source_laps_near_1km"][1]["pace"], "4:24/km")
        self.assertEqual(context["run"]["fastest_source_lap_near_1km"]["lap_index"], 21)

    def test_user_report_is_first_class_context(self):
        report = (
            "Stark hela passet och kontrollerat tempo. Pigg resten av dagen och ingen smärta."
        )
        activity = {
            "id": 1,
            "sport_type": "Run",
            "distance_m": 10000,
            "moving_time_s": 3000,
            "user_report": report,
        }
        context = build_workout_analysis_context(activity)
        self.assertEqual(context["user_report"], report)

    def test_non_run_does_not_get_run_lap_interpretation(self):
        activity = {
            "id": 2,
            "sport_type": "Swim",
            "distance_m": 4000,
            "moving_time_s": 3401,
            "laps": [
                {"lap_index": 1, "distance_m": 400, "moving_time_s": 378, "average_speed": 1.06},
                {"lap_index": 2, "distance_m": 0, "moving_time_s": 44, "average_speed": 0.0},
            ],
        }
        context = build_workout_analysis_context(activity)
        self.assertIsNone(context["run"])
        self.assertEqual(context["total"]["distance_km"], 4.0)

    def test_pace_helpers_fail_closed_without_valid_distance(self):
        self.assertIsNone(pace_s_per_km(300, 0))
        self.assertEqual(fmt_pace(None), "")


if __name__ == "__main__":
    unittest.main()
