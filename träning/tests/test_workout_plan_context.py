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

    def test_swim_structure_detects_a_different_structured_session(self):
        plan = {
            "days": [
                {
                    "date": "2026-09-16",
                    "session": "Simning · 3 200 m · aerob/teknik",
                    "sport": "swim",
                    "stimuli": ["swim_aerobic", "swim_technique"],
                    "dose_resolution": {
                        "kind": "structured",
                        "value": 3200,
                        "option_id": "swim-support-3200",
                    },
                    "watch_workout": {
                        "planned_distance_m": 3200,
                        "blocks": [
                            {"name": "Insim", "steps": [{"kind": "swim", "distance_m": 400}]},
                            {
                                "name": "Teknik",
                                "repeat": 6,
                                "steps": [
                                    {"kind": "swim", "distance_m": 50},
                                    {"kind": "rest", "duration_s": 15},
                                ],
                            },
                            {
                                "name": "Aerob",
                                "repeat": 4,
                                "steps": [
                                    {"kind": "swim", "distance_m": 500},
                                    {"kind": "rest", "duration_s": 30},
                                ],
                            },
                            {
                                "name": "Frekvens",
                                "repeat": 6,
                                "steps": [
                                    {"kind": "swim", "distance_m": 50},
                                    {"kind": "rest", "duration_s": 15},
                                ],
                            },
                            {"name": "Ned", "steps": [{"kind": "swim", "distance_m": 200}]},
                        ],
                    },
                }
            ]
        }
        activity = {
            "distance_m": 3500,
            "moving_time_s": 2896,
            "workout_analysis_context": {
                "swim": {
                    "structure_signature": "1x200+4x50+1x150+24x100+3x50+1x400",
                    "structure": [
                        {"repetitions": 1, "distance_per_rep_m": 200},
                        {"repetitions": 4, "distance_per_rep_m": 50},
                        {"repetitions": 1, "distance_per_rep_m": 150},
                        {"repetitions": 24, "distance_per_rep_m": 100},
                        {"repetitions": 3, "distance_per_rep_m": 50},
                        {"repetitions": 1, "distance_per_rep_m": 400},
                    ],
                }
            },
        }

        context = build_plan_comparison(plan, activity, "2026-09-16")

        self.assertEqual(context["planned_swim_distance_m"], 3200.0)
        self.assertEqual(context["actual_swim_distance_m"], 3500.0)
        self.assertEqual(context["swim_distance_delta_m"], 300.0)
        self.assertEqual(context["swim_structure_relation"], "different_structured_session")
        self.assertLess(context["swim_structure_overlap_ratio"], 0.5)
        self.assertIn(
            "ett annat strukturerat pass än planens setstruktur",
            plan_comparison_fact(context),
        )

    def test_swim_structure_treats_small_omissions_as_modified_planned_structure(self):
        plan = {
            "days": [
                {
                    "date": "2026-09-16",
                    "session": "Kontrollerad tröskel 3 600 m",
                    "sport": "swim",
                    "watch_workout": {
                        "planned_distance_m": 3600,
                        "blocks": [
                            {"steps": [{"kind": "swim", "distance_m": 200}]},
                            {"repeat": 4, "steps": [{"kind": "swim", "distance_m": 50}]},
                            {"steps": [{"kind": "swim", "distance_m": 200}]},
                            {"repeat": 24, "steps": [{"kind": "swim", "distance_m": 100}]},
                            {"repeat": 4, "steps": [{"kind": "swim", "distance_m": 50}]},
                            {"steps": [{"kind": "swim", "distance_m": 400}]},
                        ],
                    },
                }
            ]
        }
        activity = {
            "distance_m": 3500,
            "workout_analysis_context": {
                "swim": {
                    "structure_signature": "1x200+4x50+1x150+24x100+3x50+1x400",
                    "structure": [
                        {"repetitions": 1, "distance_per_rep_m": 200},
                        {"repetitions": 4, "distance_per_rep_m": 50},
                        {"repetitions": 1, "distance_per_rep_m": 150},
                        {"repetitions": 24, "distance_per_rep_m": 100},
                        {"repetitions": 3, "distance_per_rep_m": 50},
                        {"repetitions": 1, "distance_per_rep_m": 400},
                    ],
                }
            },
        }

        context = build_plan_comparison(plan, activity, "2026-09-16")

        self.assertEqual(context["swim_structure_relation"], "modified_planned_structure")
        self.assertGreaterEqual(context["swim_structure_overlap_ratio"], 0.9)
        self.assertIn(
            "motsvarar huvudsakligen planens struktur med mindre avvikelse",
            plan_comparison_fact(context),
        )


if __name__ == "__main__":
    unittest.main()
