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
    fmt_swim_pace,
    pace_s_per_100m,
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

    def test_enduro_uses_elapsed_time_as_session_duration(self):
        activity = {
            "id": 20078705519,
            "sport_type": "Enduro",
            "display_label": "Enduro",
            "classification": "training",
            "distance_m": 14637.8,
            "moving_time_s": 2915,
            "elapsed_time_s": 5718,
            "average_heartrate": 106.7,
            "max_heartrate": 168.0,
        }
        context = build_workout_analysis_context(activity)
        enduro = context["enduro"]
        self.assertEqual(context["contract_version"], WORKOUT_ANALYSIS_CONTRACT_VERSION)
        self.assertEqual(enduro["session_duration_s"], 5718.0)
        self.assertEqual(enduro["duration_basis"], "elapsed_time_s")
        self.assertEqual(enduro["moving_time_s"], 2915.0)
        self.assertEqual(enduro["non_moving_time_s"], 2803.0)
        self.assertIsNone(context["run"])

    def test_enduro_falls_back_to_moving_time_only_when_elapsed_is_missing(self):
        activity = {
            "id": 3,
            "sport_type": "Enduro",
            "moving_time_s": 3600,
        }
        context = build_workout_analysis_context(activity)
        self.assertEqual(context["enduro"]["session_duration_s"], 3600.0)
        self.assertEqual(context["enduro"]["duration_basis"], "moving_time_s_fallback")

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

    def test_swim_builds_repeat_sets_only_from_rest_separated_equal_distance_laps(self):
        activity = {
            "id": 20106458579,
            "sport_type": "Swim",
            "distance_m": 3200.0,
            "moving_time_s": 2768,
            "elapsed_time_s": 3518,
            "average_heartrate": 128.4,
            "max_heartrate": 157.0,
            "laps": [
                {"lap_index": 1, "distance_m": 400, "moving_time_s": 365, "elapsed_time_s": 365, "average_heartrate": 111.9},
                {"lap_index": 2, "distance_m": 0, "moving_time_s": 36, "elapsed_time_s": 36},
                {"lap_index": 3, "distance_m": 50, "moving_time_s": 42, "elapsed_time_s": 42, "average_heartrate": 93.8},
                {"lap_index": 4, "distance_m": 0, "moving_time_s": 15, "elapsed_time_s": 15},
                {"lap_index": 5, "distance_m": 50, "moving_time_s": 40, "elapsed_time_s": 40, "average_heartrate": 120.3},
                {"lap_index": 6, "distance_m": 0, "moving_time_s": 15, "elapsed_time_s": 15},
                {"lap_index": 7, "distance_m": 50, "moving_time_s": 38, "elapsed_time_s": 38, "average_heartrate": 121.9},
                {"lap_index": 8, "distance_m": 0, "moving_time_s": 15, "elapsed_time_s": 15},
                {"lap_index": 9, "distance_m": 50, "moving_time_s": 38, "elapsed_time_s": 38, "average_heartrate": 124.1},
                {"lap_index": 10, "distance_m": 0, "moving_time_s": 15, "elapsed_time_s": 15},
                {"lap_index": 11, "distance_m": 50, "moving_time_s": 38, "elapsed_time_s": 38, "average_heartrate": 130.4},
                {"lap_index": 12, "distance_m": 0, "moving_time_s": 15, "elapsed_time_s": 15},
                {"lap_index": 13, "distance_m": 50, "moving_time_s": 37, "elapsed_time_s": 37, "average_heartrate": 132.1},
                {"lap_index": 14, "distance_m": 0, "moving_time_s": 0, "elapsed_time_s": 0},
                {"lap_index": 15, "distance_m": 500, "moving_time_s": 440, "elapsed_time_s": 440, "average_heartrate": 130.9},
                {"lap_index": 16, "distance_m": 0, "moving_time_s": 12, "elapsed_time_s": 12},
                {"lap_index": 17, "distance_m": 0, "moving_time_s": 17, "elapsed_time_s": 17},
                {"lap_index": 18, "distance_m": 500, "moving_time_s": 437, "elapsed_time_s": 437, "average_heartrate": 139.5},
                {"lap_index": 19, "distance_m": 0, "moving_time_s": 30, "elapsed_time_s": 30},
                {"lap_index": 20, "distance_m": 500, "moving_time_s": 441, "elapsed_time_s": 441, "average_heartrate": 145.1},
                {"lap_index": 21, "distance_m": 0, "moving_time_s": 19, "elapsed_time_s": 19},
                {"lap_index": 22, "distance_m": 0, "moving_time_s": 10, "elapsed_time_s": 10},
                {"lap_index": 23, "distance_m": 500, "moving_time_s": 442, "elapsed_time_s": 442, "average_heartrate": 145.3},
                {"lap_index": 24, "distance_m": 0, "moving_time_s": 0, "elapsed_time_s": 0},
                {"lap_index": 25, "distance_m": 50, "moving_time_s": 39, "elapsed_time_s": 39, "average_heartrate": 107.2},
                {"lap_index": 26, "distance_m": 0, "moving_time_s": 15, "elapsed_time_s": 15},
                {"lap_index": 27, "distance_m": 50, "moving_time_s": 37, "elapsed_time_s": 37, "average_heartrate": 143.5},
                {"lap_index": 28, "distance_m": 0, "moving_time_s": 15, "elapsed_time_s": 15},
                {"lap_index": 29, "distance_m": 50, "moving_time_s": 37, "elapsed_time_s": 37, "average_heartrate": 146.6},
                {"lap_index": 30, "distance_m": 0, "moving_time_s": 15, "elapsed_time_s": 15},
                {"lap_index": 31, "distance_m": 50, "moving_time_s": 38, "elapsed_time_s": 38, "average_heartrate": 150.2},
                {"lap_index": 32, "distance_m": 0, "moving_time_s": 15, "elapsed_time_s": 15},
                {"lap_index": 33, "distance_m": 50, "moving_time_s": 38, "elapsed_time_s": 38, "average_heartrate": 149.0},
                {"lap_index": 34, "distance_m": 0, "moving_time_s": 15, "elapsed_time_s": 15},
                {"lap_index": 35, "distance_m": 50, "moving_time_s": 36, "elapsed_time_s": 36, "average_heartrate": 148.3},
                {"lap_index": 36, "distance_m": 0, "moving_time_s": 2, "elapsed_time_s": 2},
                {"lap_index": 37, "distance_m": 200, "moving_time_s": 176, "elapsed_time_s": 176, "average_heartrate": 124.6},
                {"lap_index": 38, "distance_m": 0, "moving_time_s": 2, "elapsed_time_s": 2},
            ],
        }

        context = build_workout_analysis_context(activity)
        swim = context["swim"]
        self.assertTrue(swim["structured"])
        self.assertEqual(swim["structure_signature"], "1x400+6x50+4x500+6x50+1x200")
        self.assertEqual(
            [(row["repetitions"], row["distance_per_rep_m"]) for row in swim["repeat_sets"]],
            [(6, 50.0), (4, 500.0), (6, 50.0)],
        )
        main_set = swim["repeat_sets"][1]
        self.assertEqual(main_set["lap_indices"], [15, 18, 20, 23])
        self.assertEqual(main_set["recorded_rest_between_reps_s"], [29.0, 30.0, 29.0])
        self.assertAlmostEqual(main_set["pace_mean_s_per_100m"], 88.0, places=2)
        self.assertAlmostEqual(main_set["pace_range_s_per_100m"], 1.0, places=2)
        self.assertAlmostEqual(main_set["pace_first_to_last_delta_s_per_100m"], 0.4, places=2)
        self.assertTrue(swim["source_lap_distance_matches_activity"])
        self.assertIsNone(context["run"])
        self.assertIsNone(context["enduro"])

    def test_swim_does_not_invent_repeat_set_without_rest_marker(self):
        activity = {
            "id": 2,
            "sport_type": "Swim",
            "distance_m": 150,
            "moving_time_s": 120,
            "laps": [
                {"lap_index": 1, "distance_m": 50, "moving_time_s": 40},
                {"lap_index": 2, "distance_m": 50, "moving_time_s": 39},
                {"lap_index": 3, "distance_m": 50, "moving_time_s": 41},
            ],
        }
        context = build_workout_analysis_context(activity)
        self.assertFalse(context["swim"]["structured"])
        self.assertEqual(context["swim"]["repeat_sets"], [])

    def test_non_run_non_swim_does_not_get_run_or_swim_lap_interpretation(self):
        activity = {
            "id": 2,
            "sport_type": "Ride",
            "distance_m": 4000,
            "moving_time_s": 3401,
            "laps": [
                {"lap_index": 1, "distance_m": 400, "moving_time_s": 378, "average_speed": 1.06},
                {"lap_index": 2, "distance_m": 0, "moving_time_s": 44, "average_speed": 0.0},
            ],
        }
        context = build_workout_analysis_context(activity)
        self.assertIsNone(context["run"])
        self.assertIsNone(context["swim"])
        self.assertIsNone(context["enduro"])
        self.assertEqual(context["total"]["distance_km"], 4.0)

    def test_pace_helpers_fail_closed_without_valid_distance(self):
        self.assertIsNone(pace_s_per_km(300, 0))
        self.assertIsNone(pace_s_per_100m(90, 0))
        self.assertEqual(fmt_pace(None), "")
        self.assertEqual(fmt_swim_pace(None), "")


if __name__ == "__main__":
    unittest.main()
