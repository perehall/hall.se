#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workout_plan_context import (  # noqa: E402
    build_plan_comparison,
    plan_comparison_fact,
)


class WorkoutPlanContextTests(unittest.TestCase):
    def test_sep6_run_is_detected_as_above_approved_duration_range(self):
        plan = {
            "days": [
                {
                    "date": "2026-09-06",
                    "session": "Löpning · lugn distans · 75 min",
                    "status": "preliminary",
                    "sport": "run",
                    "priority_role": "flex",
                    "stimuli": ["run_easy_distance"],
                    "dose_resolution": {
                        "kind": "duration_minutes",
                        "value": 75,
                        "option_id": "run-easy-75",
                    },
                    "dose_options": [
                        {"kind": "duration_minutes", "value": 75},
                        {"kind": "duration_minutes", "value": 90},
                    ],
                }
            ]
        }
        activity = {"moving_time_s": 6960}
        context = build_plan_comparison(plan, activity, "2026-09-06")

        self.assertTrue(context["plan_day_found"])
        self.assertEqual(context["selected_duration_minutes"], 75.0)
        self.assertEqual(context["approved_duration_options_minutes"], [75.0, 90.0])
        self.assertEqual(context["actual_duration_minutes"], 116.0)
        self.assertEqual(context["duration_delta_vs_selected_minutes"], 41.0)
        self.assertEqual(context["duration_delta_vs_selected_percent"], 54.7)
        self.assertEqual(
            context["duration_relation_to_approved_options"],
            "above_approved_duration_range",
        )
        self.assertEqual(context["duration_outside_approved_range_minutes"], 26.0)
        fact = plan_comparison_fact(context)
        self.assertIn("Planerad tidsdos 75 min", fact)
        self.assertIn("faktisk rörelsetid 116 min", fact)
        self.assertIn("över längsta godkända alternativet 90 min", fact)

    def test_activity_inside_approved_duration_range_is_not_called_deviation(self):
        plan = {
            "days": [
                {
                    "date": "2026-09-01",
                    "session": "Löpning",
                    "dose_resolution": {"kind": "duration_minutes", "value": 60},
                    "dose_options": [
                        {"kind": "duration_minutes", "value": 60},
                        {"kind": "duration_minutes", "value": 75},
                    ],
                }
            ]
        }
        context = build_plan_comparison(
            plan,
            {"moving_time_s": 70 * 60},
            "2026-09-01",
        )
        self.assertEqual(
            context["duration_relation_to_approved_options"],
            "within_approved_duration_range",
        )

    def test_missing_plan_day_fails_open_without_inventing_a_match(self):
        context = build_plan_comparison({"days": []}, {"moving_time_s": 3600}, "2026-09-01")
        self.assertFalse(context["plan_day_found"])
        self.assertEqual(plan_comparison_fact(context), "")


if __name__ == "__main__":
    unittest.main()
