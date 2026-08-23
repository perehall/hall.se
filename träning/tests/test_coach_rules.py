#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach_rules import (  # noqa: E402
    allowed_target_dates,
    fulfilled_plan_dates,
    normalize_assessment_confidence,
    normalize_no_remaining_plan,
    plan_for_coach,
    validate_plan_action,
)


class CoachRulesTests(unittest.TestCase):
    def test_run_fulfills_same_day_trail_plan(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-23",
                    "status": "preliminary",
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

    def test_unrelated_activity_does_not_fulfill_plan(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-23",
                    "status": "planned",
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

    def test_completed_past_and_fulfilled_dates_are_not_targets(self):
        plan = {
            "days": [
                {"date": "2026-08-22", "status": "planned", "session": "Löpning · lugnt"},
                {"date": "2026-08-23", "status": "planned", "session": "Trail · lugnt"},
                {"date": "2026-08-24", "status": "completed", "session": "Enduro"},
                {"date": "2026-08-25", "status": "planned", "session": "Simning · lugnt"},
            ]
        }
        activities = [
            {"id": 2, "sport_type": "Run", "start_date_local": "2026-08-23T10:00:00Z"}
        ]

        self.assertEqual(allowed_target_dates(plan, activities, "2026-08-23"), ["2026-08-25"])

    def test_coach_view_marks_matching_day_completed_without_mutating_plan(self):
        plan = {
            "days": [
                {"date": "2026-08-23", "status": "preliminary", "session": "Trail · lugnt"}
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


if __name__ == "__main__":
    unittest.main()
