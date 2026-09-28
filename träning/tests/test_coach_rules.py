#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach_rules import (  # noqa: E402
    allowed_target_dates,
    allowed_target_workouts,
    canonical_activity_fact,
    canonical_facts,
    decision_ready_target_dates,
    decision_ready_target_workouts,
    fulfilled_plan_dates,
    fulfilled_plan_workouts,
    normalize_assessment_confidence,
    normalize_deferred_future_action,
    normalize_no_remaining_plan,
    normalize_target_workout,
    plan_for_coach,
    unresolved_intervening_dates,
    validate_plan_action,
)


class CoachRulesTests(unittest.TestCase):
    def test_run_fulfills_same_day_trail_plan_via_explicit_sport(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-23",
                    "status": "preliminary",
                    "sport": "run",
                    "session": "Trail · lugnt · ca 50–70 min",
                }
            ]
        }
        activities = [
            {
                "id": 19862241646,
                "sport_type": "Run",
                "start_date_local": "2026-08-23T10:50:28Z",
            }
        ]

        self.assertEqual(fulfilled_plan_dates(plan, activities), {"2026-08-23": 19862241646})
        self.assertEqual(allowed_target_dates(plan, activities, "2026-08-23"), [])

    def test_one_of_two_same_day_workouts_can_be_fulfilled_independently(self):
        plan = {
            "planned_workouts": [
                {
                    "workout_key": "swim-1",
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "swim",
                    "session": "Simning",
                },
                {
                    "workout_key": "strength-1",
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "strength",
                    "session": "Styrka",
                },
            ],
            "days": [
                {
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "swim",
                    "session": "Simning",
                }
            ],
        }
        activities = [
            {
                "id": 1,
                "sport_type": "Swim",
                "start_date_local": "2026-08-23T08:00:00Z",
            }
        ]

        self.assertEqual(
            fulfilled_plan_workouts(plan, activities),
            {"swim-1": (1,)},
        )
        self.assertEqual(fulfilled_plan_dates(plan, activities), {})
        targets = allowed_target_workouts(plan, activities, "2026-08-23")
        self.assertEqual(
            [item["workout_key"] for item in targets],
            ["strength-1"],
        )

    def test_two_different_same_day_workouts_can_both_be_fulfilled(self):
        plan = {
            "planned_workouts": [
                {
                    "workout_key": "run-1",
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "run",
                    "session": "Löpning",
                },
                {
                    "workout_key": "bike-1",
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "bike",
                    "session": "MTB",
                },
            ],
            "days": [
                {
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "run",
                    "session": "Löpning",
                }
            ],
        }
        activities = [
            {
                "id": 10,
                "sport_type": "Run",
                "start_date_local": "2026-08-23T08:00:00Z",
            },
            {
                "id": 11,
                "sport_type": "MountainBikeRide",
                "start_date_local": "2026-08-23T17:00:00Z",
            },
        ]
        fulfilled = fulfilled_plan_workouts(plan, activities)
        self.assertEqual(fulfilled["run-1"], (10,))
        self.assertEqual(fulfilled["bike-1"], (11,))
        self.assertIn("2026-08-23", fulfilled_plan_dates(plan, activities))

    def test_same_sport_same_day_matching_fails_closed_without_explicit_link(self):
        plan = {
            "planned_workouts": [
                {
                    "workout_key": "run-am",
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "run",
                    "session": "Löpning 1",
                },
                {
                    "workout_key": "run-pm",
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "run",
                    "session": "Löpning 2",
                },
            ],
            "days": [],
        }
        activities = [
            {
                "id": 20,
                "sport_type": "Run",
                "start_date_local": "2026-08-23T08:00:00Z",
            },
            {
                "id": 21,
                "sport_type": "Run",
                "start_date_local": "2026-08-23T17:00:00Z",
            },
        ]
        self.assertEqual(fulfilled_plan_workouts(plan, activities), {})
        self.assertEqual(
            {item["workout_key"] for item in allowed_target_workouts(plan, activities, "2026-08-23")},
            {"run-am", "run-pm"},
        )

    def test_explicit_activity_link_resolves_same_sport_ambiguity(self):
        plan = {
            "planned_workouts": [
                {
                    "workout_key": "run-am",
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "run",
                    "session": "Löpning 1",
                    "activity_id": 20,
                },
                {
                    "workout_key": "run-pm",
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "run",
                    "session": "Löpning 2",
                    "activity_id": 21,
                },
            ],
            "days": [],
        }
        activities = [
            {
                "id": 20,
                "sport_type": "Run",
                "start_date_local": "2026-08-23T08:00:00Z",
            },
            {
                "id": 21,
                "sport_type": "Run",
                "start_date_local": "2026-08-23T17:00:00Z",
            },
        ]
        self.assertEqual(
            fulfilled_plan_workouts(plan, activities),
            {"run-am": (20,), "run-pm": (21,)},
        )

    def test_brick_requires_all_ordered_sport_components(self):
        plan = {
            "planned_workouts": [
                {
                    "workout_key": "brick-1",
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "multisport",
                    "session": "Brick",
                    "components": [
                        {"order": 1, "sport": "bike"},
                        {"order": 2, "sport": "run"},
                    ],
                }
            ],
            "days": [],
        }
        bike = {
            "id": 30,
            "sport_type": "Ride",
            "start_date_local": "2026-08-23T08:00:00Z",
        }
        run = {
            "id": 31,
            "sport_type": "Run",
            "start_date_local": "2026-08-23T09:30:00Z",
        }
        self.assertEqual(fulfilled_plan_workouts(plan, [bike]), {})
        self.assertEqual(
            fulfilled_plan_workouts(plan, [bike, run]),
            {"brick-1": (30, 31)},
        )

    def test_date_only_action_is_neutralized_when_multiple_workouts_are_targets(self):
        action = {
            "action": "reduce",
            "target_date": "2026-08-23",
            "target_workout_key": "",
            "dose_option_id": "",
            "reason": "x",
            "recommendation": "x",
            "requires_approval": False,
        }
        normalized = normalize_target_workout(
            action,
            [
                {"workout_key": "run-1", "date": "2026-08-23", "session": "Run", "sport": "run"},
                {"workout_key": "bike-1", "date": "2026-08-23", "session": "Bike", "sport": "bike"},
            ],
        )
        self.assertEqual(normalized["action"], "review")
        self.assertEqual(normalized["target_date"], "")
        self.assertEqual(normalized["target_workout_key"], "")

    def test_session_wording_is_not_used_as_sport_source(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "swim",
                    "session": "Trail · den här texten får inte styra sportmatchningen",
                }
            ]
        }
        activities = [
            {"id": 1, "sport_type": "Run", "start_date_local": "2026-08-23T10:00:00Z"}
        ]
        self.assertEqual(fulfilled_plan_dates(plan, activities), {})
        self.assertEqual(allowed_target_dates(plan, activities, "2026-08-23"), ["2026-08-23"])

    def test_unrelated_activity_does_not_fulfill_plan(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-23",
                    "status": "planned",
                    "sport": "swim",
                    "session": "Simning · aerob/teknik",
                }
            ]
        }
        activities = [
            {
                "id": 1,
                "sport_type": "Run",
                "start_date_local": "2026-08-23T10:00:00Z",
            }
        ]

        self.assertEqual(fulfilled_plan_dates(plan, activities), {})
        self.assertEqual(allowed_target_dates(plan, activities, "2026-08-23"), ["2026-08-23"])

    def test_swimrun_can_be_fulfilled_by_run_family_source_activity(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-19",
                    "status": "planned",
                    "sport": "swimrun",
                    "session": "Swimrun · klubbpass",
                }
            ]
        }
        activities = [
            {"id": 11, "sport_type": "TrailRun", "start_date_local": "2026-08-19T18:00:00Z"}
        ]
        self.assertEqual(fulfilled_plan_dates(plan, activities), {"2026-08-19": 11})

    def test_completed_past_fulfilled_rest_and_open_dates_are_not_targets(self):
        plan = {
            "days": [
                {"date": "2026-08-22", "status": "planned", "sport": "run", "session": "Löpning · lugnt"},
                {"date": "2026-08-23", "status": "planned", "sport": "run", "session": "Trail · lugnt"},
                {"date": "2026-08-24", "status": "completed", "sport": "enduro", "session": "Enduro"},
                {"date": "2026-08-25", "status": "planned", "sport": "swim", "session": "Simning · lugnt"},
                {"date": "2026-08-26", "status": "planned", "sport": "rest", "session": "Vila"},
                {"date": "2026-08-27", "status": "open", "sport": "open", "session": "Öppet · trail eller vila"},
            ]
        }
        activities = [
            {"id": 2, "sport_type": "Run", "start_date_local": "2026-08-23T10:00:00Z"}
        ]

        self.assertEqual(allowed_target_dates(plan, activities, "2026-08-23"), ["2026-08-25"])

    def test_future_target_is_deferred_until_intervening_days_are_known(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-24",
                    "status": "planned",
                    "sport": "enduro",
                    "classification": "recreation",
                    "session": "Enduroskola",
                },
                {
                    "date": "2026-08-25",
                    "status": "planned",
                    "sport": "swim",
                    "session": "Simning · aerob/teknik",
                },
                {
                    "date": "2026-08-26",
                    "status": "conditional",
                    "sport": "run",
                    "session": "Löpning · kontrollerad tröskel · 3 × 10 min",
                },
            ]
        }
        activities = []

        self.assertEqual(
            unresolved_intervening_dates(plan, activities, "2026-08-24", "2026-08-26"),
            ["2026-08-24", "2026-08-25"],
        )
        self.assertEqual(
            allowed_target_dates(plan, activities, "2026-08-24"),
            ["2026-08-25", "2026-08-26"],
        )
        self.assertEqual(decision_ready_target_dates(plan, activities, "2026-08-24"), [])

    def test_tomorrows_target_becomes_ready_after_today_is_fulfilled(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-24",
                    "status": "planned",
                    "sport": "enduro",
                    "classification": "recreation",
                    "session": "Enduroskola",
                },
                {
                    "date": "2026-08-25",
                    "status": "planned",
                    "sport": "swim",
                    "session": "Simning · aerob/teknik",
                },
                {
                    "date": "2026-08-26",
                    "status": "conditional",
                    "sport": "run",
                    "session": "Löpning · kontrollerad tröskel",
                },
            ]
        }
        activities = [
            {"id": 20, "sport_type": "Enduro", "start_date_local": "2026-08-24T18:00:00+02:00"}
        ]

        self.assertEqual(decision_ready_target_dates(plan, activities, "2026-08-24"), ["2026-08-25"])

    def test_wednesday_becomes_ready_after_tuesday_is_fulfilled(self):
        plan = {
            "days": [
                {"date": "2026-08-24", "status": "completed", "sport": "enduro", "session": "Enduro"},
                {"date": "2026-08-25", "status": "planned", "sport": "swim", "session": "Simning"},
                {"date": "2026-08-26", "status": "conditional", "sport": "run", "session": "Tröskel"},
            ]
        }
        activities = [
            {"id": 21, "sport_type": "Swim", "start_date_local": "2026-08-25T07:00:00+02:00"}
        ]

        self.assertEqual(decision_ready_target_dates(plan, activities, "2026-08-25"), ["2026-08-26"])

    def test_model_reduce_on_deferred_target_is_normalized_to_review(self):
        action = {
            "action": "reduce",
            "target_date": "2026-08-26",
            "reason": "x",
            "recommendation": "Skala ner.",
            "requires_approval": False,
        }
        normalized = normalize_deferred_future_action(
            action,
            candidate_dates=["2026-08-25", "2026-08-26"],
            ready_dates=[],
        )
        self.assertEqual(normalized["action"], "review")
        self.assertEqual(normalized["target_date"], "")
        self.assertIn("Ändra inte", normalized["recommendation"])

    def test_cross_day_recommendation_cannot_auto_edit_wrong_target(self):
        action = {
            "action": "reduce",
            "target_date": "2026-08-26",
            "reason": "Veckans närbelastning påverkar kommande kvalitet.",
            "recommendation": (
                "Håll fredagspasset som backkvalitet men gör dosen konservativ. "
                "Justera slutlig dos först efter torsdagens MTB."
            ),
            "requires_approval": False,
        }
        normalized = normalize_deferred_future_action(
            action,
            candidate_dates=["2026-08-26", "2026-08-27", "2026-08-28"],
            ready_dates=["2026-08-26"],
        )
        self.assertEqual(normalized["action"], "review")
        self.assertEqual(normalized["target_date"], "")
        self.assertIn("inte kopplas entydigt", normalized["reason"])

    def test_target_day_may_reference_surrounding_day_when_target_is_explicit(self):
        action = {
            "action": "reduce",
            "target_date": "2026-08-28",
            "reason": "x",
            "recommendation": "Efter torsdagens MTB: skala ner fredagens backpass om benen är tunga.",
            "requires_approval": False,
        }
        normalized = normalize_deferred_future_action(
            action,
            candidate_dates=["2026-08-28"],
            ready_dates=["2026-08-28"],
        )
        self.assertEqual(normalized["action"], "reduce")
        self.assertEqual(normalized["target_date"], "2026-08-28")

    def test_coach_view_marks_matching_day_completed_without_mutating_plan(self):
        plan = {
            "days": [
                {"date": "2026-08-23", "status": "preliminary", "sport": "run", "session": "Trail · lugnt"}
            ]
        }
        activities = [
            {
                "id": 3,
                "sport_type": "Run",
                "display_label": "Löpning · grus/asfalt",
                "start_date_local": "2026-08-23T10:00:00Z",
            }
        ]

        coach_plan, fulfilled = plan_for_coach(plan, activities)
        self.assertEqual(fulfilled, {"2026-08-23": 3})
        self.assertEqual(coach_plan["days"][0]["status"], "completed")
        self.assertEqual(coach_plan["days"][0]["coach_fulfilled_by_activity"]["id"], 3)
        self.assertEqual(plan["days"][0]["status"], "preliminary")

    def test_invalid_ai_target_is_rejected(self):
        action = {
            "action": "keep",
            "target_date": "2026-08-23",
            "reason": "x",
            "recommendation": "x",
        }
        with self.assertRaises(RuntimeError):
            validate_plan_action(action, ["2026-08-25"])

    def test_reduce_requires_target(self):
        action = {
            "action": "reduce",
            "target_date": "",
            "reason": "x",
            "recommendation": "x",
        }
        with self.assertRaises(RuntimeError):
            validate_plan_action(action, [])

    def test_no_remaining_plan_cannot_reorder_today_workout(self):
        action = {
            "action": "keep",
            "target_date": "",
            "reason": "Passet såg kontrollerat ut.",
            "recommendation": "Kör trail 50–70 min idag.",
        }
        normalized = normalize_no_remaining_plan(
            action,
            allowed_dates=[],
            latest_date="2026-08-23",
            fulfilled_dates={"2026-08-23": 19862241646},
        )
        self.assertEqual(normalized["target_date"], "")
        self.assertNotIn("trail 50", normalized["recommendation"].lower())
        self.assertIn("redan genomfört", normalized["recommendation"].lower())

    def test_high_confidence_is_downgraded_when_unknowns_exist(self):
        assessment = {
            "confidence": "high",
            "unknowns": ["Subjektiv återhämtning saknas."],
            "summary": "x",
        }
        normalized = normalize_assessment_confidence(assessment)
        self.assertEqual(normalized["confidence"], "medium")
        self.assertEqual(assessment["confidence"], "high")

    def test_high_confidence_stays_high_without_unknowns(self):
        assessment = {"confidence": "high", "unknowns": [], "summary": "x"}
        self.assertEqual(normalize_assessment_confidence(assessment)["confidence"], "high")

    def test_canonical_activity_fact_uses_exact_source_duration(self):
        activity = {
            "sport_type": "Run",
            "display_label": "Löpning · grus/asfalt",
            "distance_m": 17158.0,
            "elapsed_time_s": 5459,
            "total_elevation_gain_m": 161.0,
            "average_heartrate": 138.9,
            "max_heartrate": 157.0,
        }
        self.assertEqual(
            canonical_activity_fact(activity),
            "Löpning · grus/asfalt: 17,16 km · 1:30:59 · 161 m+ · snittpuls 138,9 · maxpuls 157.",
        )

    def test_canonical_facts_include_user_report_and_fulfilled_plan(self):
        activity = {
            "sport_type": "Run",
            "distance_m": 5000,
            "elapsed_time_s": 1500,
            "user_report": "Underlag: grus och asfalt; inte trail.",
        }
        facts = canonical_facts(
            activity,
            latest_date="2026-08-23",
            fulfilled_dates={"2026-08-23": 1},
        )
        self.assertEqual(facts[0], "Löpning: 5,00 km · 25:00.")
        self.assertEqual(facts[1], "Användarrapport: Underlag: grus och asfalt; inte trail.")
        self.assertIn("Planstatus 2026-08-23", facts[2])


if __name__ == "__main__":
    unittest.main()