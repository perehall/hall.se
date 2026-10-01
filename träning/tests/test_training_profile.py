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

    def test_detects_work_blocks_split_across_provider_laps_like_real_run(self):
        activity = {
            "id": 101,
            "sport_type": "Run",
            "classification": "training",
            "start_date_local": "2026-09-29T18:00:00",
            "user_report": "",
            "laps": [
                lap(1, 322, 1000, 3.11),
                lap(2, 316, 979, 3.10),
                lap(3, 225, 655, 2.91),
                lap(4, 257, 1000, 3.89),
                lap(5, 228, 874, 3.83),
                lap(6, 92, 279, 3.03),
                lap(7, 258, 1000, 3.88),
                lap(8, 226, 898, 3.97),
                lap(9, 91, 246, 2.71),
                lap(10, 257, 1000, 3.89),
                lap(11, 227, 877, 3.86),
                lap(12, 108, 307, 2.84),
                lap(13, 263, 1000, 3.80),
                lap(14, 253, 1000, 3.95),
                lap(15, 321, 1000, 3.12),
                lap(16, 156, 503, 3.22),
            ],
        }
        structure = run_time_interval_structure(activity)
        self.assertTrue(structure["structured"])
        self.assertEqual(structure["repetitions"], 4)
        self.assertLess(abs(structure["representative_work_duration_s"] - 480), 45)
        self.assertLess(abs(structure["representative_recovery_duration_s"] - 90), 20)

        profile = build_training_profile(
            activity,
            planned_workouts=[threshold_plan()],
        )
        self.assertEqual(profile["planning_credits"], ["run_threshold"])
        self.assertEqual(profile["stimuli"], [])

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

    def test_old_profile_schema_does_not_preserve_stale_intent_match(self):
        activity = four_by_eight_activity(
            report="Spontant pass: 4 × 8 min tröskel, kontrollerat."
        )
        current = build_training_profile(activity)
        stale = dict(current)
        stale["schema_version"] = 1
        stale["intent_matches"] = [
            {
                "workout_key": "stale-easy-run",
                "target_date": "2026-09-27",
                "day_delta": -2,
                "stimuli": ["run_easy_distance"],
                "relation": "fulfills_planned_dose",
                "confidence": "high",
                "evidence": {"basis": "legacy_scalar_match"},
            }
        ]
        stale["planning_credits"] = ["run_easy_distance", "run_threshold"]

        rebuilt = build_training_profile(
            activity,
            planned_workouts=[],
            previous_profile=stale,
        )
        self.assertEqual(rebuilt["schema_version"], 2)
        self.assertEqual(rebuilt["planning_credits"], ["run_threshold"])
        self.assertEqual(rebuilt["intent_matches"], [])

    def test_explicit_report_confirms_stimulus_independently_of_plan(self):
        activity = four_by_eight_activity(
            report="Spontant pass: 4 × 8 min tröskel, kontrollerat."
        )
        profile = build_training_profile(activity)
        self.assertEqual(profile["planning_credits"], ["run_threshold"])
        self.assertEqual(profile["stimuli"][0]["key"], "run_threshold")
        self.assertEqual(profile["stimuli"][0]["status"], "confirmed")
        self.assertEqual(profile["stimuli"][0]["source"], "explicit_user_report")


    def test_swim_same_day_comparable_dose_can_receive_planning_credit(self):
        activity = {
            "id": 500,
            "sport_type": "Swim",
            "classification": "training",
            "start_date_local": "2026-10-06T18:00:00",
            "distance_m": 3190,
            "elapsed_time_s": 3900,
            "user_report": "Bra kontroll.",
            "laps": [],
        }
        planned = [{
            "date": "2026-10-06",
            "sport": "swim",
            "workout_key": "swim-aerobic-1",
            "session": "Simning · 3 200 m · grepp/teknik + aerob",
            "stimuli": ["swim_aerobic", "swim_technique"],
        }]
        profile = build_training_profile(activity, planned_workouts=planned)
        self.assertEqual(
            profile["planning_credits"],
            ["swim_aerobic", "swim_technique"],
        )
        self.assertEqual(profile["intent_matches"][0]["confidence"], "high")
        self.assertEqual(
            profile["intent_matches"][0]["evidence"]["basis"],
            "same_day_comparable_scalar_dose",
        )

    def test_scalar_dose_match_does_not_bridge_calendar_days(self):
        activity = {
            "id": 502,
            "sport_type": "Run",
            "classification": "training",
            "start_date_local": "2026-09-29T18:00:00",
            "elapsed_time_s": 3755,
            "distance_m": 13135,
            "user_report": "",
            "laps": [],
        }
        planned = [{
            "date": "2026-09-27",
            "sport": "run",
            "workout_key": "run-easy-60",
            "session": "Löpning · lugn distans · 60 min",
            "stimuli": ["run_easy_distance"],
        }]
        profile = build_training_profile(activity, planned_workouts=planned)
        self.assertEqual(profile["planning_credits"], [])
        self.assertEqual(profile["intent_matches"], [])

    def test_explicit_threshold_cannot_be_scalar_matched_to_easy_run(self):
        activity = {
            "id": 503,
            "sport_type": "Run",
            "classification": "training",
            "start_date_local": "2026-09-29T18:00:00",
            "elapsed_time_s": 3755,
            "distance_m": 13135,
            "user_report": "4 x 8 min tröskel. Bra kontroll. RPE 6/10.",
            "laps": [],
        }
        planned = [{
            "date": "2026-09-29",
            "sport": "run",
            "workout_key": "run-easy-same-day",
            "session": "Löpning · lugn distans · 60 min",
            "stimuli": ["run_easy_distance"],
        }]
        profile = build_training_profile(activity, planned_workouts=planned)
        self.assertEqual(profile["planning_credits"], ["run_threshold"])
        self.assertEqual(profile["intent_matches"], [])

    def test_two_equally_plausible_swims_fail_closed_without_planning_credit(self):
        activity = {
            "id": 501,
            "sport_type": "Swim",
            "classification": "training",
            "start_date_local": "2026-10-06T18:00:00",
            "distance_m": 3200,
            "elapsed_time_s": 3900,
            "user_report": "",
            "laps": [],
        }
        planned = [
            {
                "date": "2026-10-06",
                "sport": "swim",
                "workout_key": "swim-a",
                "session": "Simning · 3 200 m · aerob uthållighet",
                "stimuli": ["swim_aerobic"],
            },
            {
                "date": "2026-10-06",
                "sport": "swim",
                "workout_key": "swim-b",
                "session": "Simning · 3 200 m · grepp/teknik + aerob",
                "stimuli": ["swim_aerobic", "swim_technique"],
            },
        ]
        profile = build_training_profile(activity, planned_workouts=planned)
        self.assertEqual(profile["planning_credits"], [])
        self.assertEqual(profile["intent_matches"], [])

    def test_explicit_strength_exercises_confirm_unilateral_and_core(self):
        activity = {
            "id": 600,
            "sport_type": "WeightTraining",
            "classification": "training",
            "start_date_local": "2026-09-28T18:00:00",
            "elapsed_time_s": 2212,
            "user_report": "Pallof press 3x10, Bulgarian split squats 3x8, dead bug och reverse plank. RPE 6/10. Pigg.",
            "laps": [],
        }
        profile = build_training_profile(activity)
        self.assertEqual(
            profile["planning_credits"],
            ["strength_core", "strength_unilateral"],
        )
        self.assertEqual(
            {row["key"] for row in profile["stimuli"]},
            {"strength_core", "strength_unilateral"},
        )

    def test_explicit_easy_trail_report_confirms_easy_distance(self):
        activity = {
            "id": 601,
            "sport_type": "TrailRun",
            "classification": "training",
            "start_date_local": "2026-09-27T10:00:00",
            "elapsed_time_s": 4800,
            "distance_m": 13400,
            "user_report": "Gick ut väldigt lugnt och försökte hålla pulsen runt 130. RPE 4/10.",
            "laps": [],
        }
        profile = build_training_profile(activity)
        self.assertEqual(profile["planning_credits"], ["run_easy_distance"])
        self.assertEqual(profile["stimuli"][0]["dose"]["duration_minutes"], 80.0)

    def test_explicit_calm_trail_mtb_confirms_technical_and_aerobic_intent(self):
        activity = {
            "id": 602,
            "sport_type": "MountainBikeRide",
            "classification": "training",
            "start_date_local": "2026-09-24T18:00:00",
            "elapsed_time_s": 4800,
            "distance_m": 19000,
            "user_report": "80 min lugn stig-MTB. Bra flyt, ingen fartjakt. RPE 4/10.",
            "laps": [],
        }
        profile = build_training_profile(activity)
        self.assertEqual(
            profile["planning_credits"],
            ["mtb_aerobic", "mtb_technical"],
        )

if __name__ == "__main__":
    unittest.main()
