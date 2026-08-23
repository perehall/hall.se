#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach_rules import (  # noqa: E402
    allowed_target_dates,
    canonical_activity_fact,
    canonical_facts,
    fulfilled_plan_dates,
    normalize_assessment_confidence,
    normalize_no_remaining_plan,
    plan_for_coach,
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
        self.assertEqual(facts[0], "Run: 5,00 km · 25:00.")
        self.assertEqual(facts[1], "Användarrapport: Underlag: grus och asfalt; inte trail.")
        self.assertIn("Planstatus 2026-08-23", facts[2])


if __name__ == "__main__":
    unittest.main()
