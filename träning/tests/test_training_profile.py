#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from training_profile import (  # noqa: E402
    build_training_profile,
    run_time_interval_structure,
)


def lap(index, seconds, distance, speed=None):
    row = {
        "lap_index": index,
        "moving_time_s": seconds,
        "elapsed_time_s": seconds,
        "distance_m": distance,
    }
    if speed is not None:
        row["average_speed"] = speed
    return row


def four_by_eight_activity(activity_id=100, report=""):
    # Warm-up, four eight-minute work blocks, three 90 s recoveries, cool-down.
    # Speeds are intentionally descriptive only; the physiological label comes
    # from explicit evidence or a unique plan-intent match.
    return {
        "id": activity_id,
        "sport_type": "Run",
        "classification": "training",
        "start_date_local": "2026-09-29T18:00:00",
        "user_report": report,
        "laps": [
            lap(1, 600, 1800, 3.0),
            lap(2, 480, 1900, 3.958),
            lap(3, 90, 250, 2.778),
            lap(4, 480, 1910, 3.979),
            lap(5, 90, 245, 2.722),
            lap(6, 480, 1890, 3.938),
            lap(7, 90, 255, 2.833),
            lap(8, 480, 1920, 4.0),
            lap(9, 600, 1800, 3.0),
        ],
    }


def threshold_plan(date_value="2026-09-30", slot="run_threshold_1"):
    return {
        "date": date_value,
        "sport": "run",
        "microcycle_id": "meso:mc1",
        "microcycle_slot": slot,
        "stimuli": ["run_threshold"],
        "device_workout": {
            "sport": "run",
            "blocks": [
                {
                    "sets": 1,
                    "repetitions_per_set": 4,
                    "steps": [
                        {
                            "kind": "work",
                            "duration": {"kind": "time", "seconds": 480},
                        },
                        {
                            "kind": "recovery",
                            "duration": {"kind": "time", "seconds": 90},
                        },
                    ],
                }
            ],
        },
    }


class TrainingProfileTests(unittest.TestCase):
    def test_detects_repeated_time_structure_without_inventing_intensity(self):
        activity = four_by_eight_activity()
        structure = run_time_interval_structure(activity)
        self.assertTrue(structure["structured"])
        self.assertEqual(structure["repetitions"], 4)
        self.assertAlmostEqual(structure["representative_work_duration_s"], 480.0)
        self.assertAlmostEqual(structure["representative_recovery_duration_s"], 90.0)

        profile = build_training_profile(activity)
        self.assertEqual(profile["stimuli"], [])
        self.assertEqual(profile["planning_credits"], [])
        self.assertTrue(profile["uncertainties"])

    def test_unique_nearby_plan_structure_creates_planning_credit_without_physiology_claim(self):
        activity = four_by_eight_activity()
        profile = build_training_profile(
            activity,
            planned_workouts=[threshold_plan()],
        )
        self.assertEqual(profile["stimuli"], [])
        self.assertEqual(profile["planning_credits"], ["run_threshold"])
        self.assertEqual(len(profile["intent_matches"]), 1)
        match = profile["intent_matches"][0]
        self.assertEqual(match["relation"], "fulfills_planned_dose")
        self.assertEqual(match["confidence"], "high")
        self.assertEqual(match["target_date"], "2026-09-30")

    def test_ambiguous_structural_matches_fail_closed(self):
        activity = four_by_eight_activity()
        profile = build_training_profile(
            activity,
            planned_workouts=[
                threshold_plan("2026-09-30", "run_threshold_a"),
                threshold_plan("2026-10-01", "run_threshold_b"),
            ],
        )
        self.assertEqual(profile["intent_matches"], [])
        self.assertEqual(profile["planning_credits"], [])

    def test_durable_intent_match_survives_after_future_duplicate_is_removed(self):
        activity = four_by_eight_activity()
        first = build_training_profile(
            activity,
            planned_workouts=[threshold_plan()],
        )
        second = build_training_profile(
            activity,
            planned_workouts=[],
            previous_profile=first,
        )
        self.assertEqual(second["planning_credits"], ["run_threshold"])
        self.assertEqual(second["intent_matches"], first["intent_matches"])

    def test_explicit_report_confirms_stimulus_independently_of_plan(self):
        activity = four_by_eight_activity(
            report="Spontant pass: 4 × 8 min tröskel, kontrollerat."
        )
        profile = build_training_profile(activity)
        self.assertEqual(profile["planning_credits"], ["run_threshold"])
        self.assertEqual(profile["stimuli"][0]["key"], "run_threshold")
        self.assertEqual(profile["stimuli"][0]["status"], "confirmed")
        self.assertEqual(profile["stimuli"][0]["source"], "explicit_user_report")


if __name__ == "__main__":
    unittest.main()
