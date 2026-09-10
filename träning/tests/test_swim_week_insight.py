#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_week_activity_insights import historical_insight, structured_swim_insight  # noqa: E402


class SwimWeekInsightTests(unittest.TestCase):
    def activity(self):
        return {
            "id": 20106458579,
            "sport_type": "Swim",
            "workout_analysis_context": {
                "swim": {
                    "structured": True,
                    "repeat_sets": [
                        {
                            "repetitions": 6,
                            "distance_per_rep_m": 50.0,
                            "total_distance_m": 300.0,
                            "pace_mean_s_per_100m": 77.67,
                            "pace_fastest_s_per_100m": 74.0,
                            "pace_slowest_s_per_100m": 84.0,
                            "pace_range_s_per_100m": 10.0,
                            "recorded_rest_between_reps_s": [15, 15, 15, 15, 15],
                        },
                        {
                            "repetitions": 4,
                            "distance_per_rep_m": 500.0,
                            "total_distance_m": 2000.0,
                            "pace_mean_s_per_100m": 88.0,
                            "pace_fastest_s_per_100m": 87.4,
                            "pace_slowest_s_per_100m": 88.4,
                            "pace_range_s_per_100m": 1.0,
                            "recorded_rest_between_reps_s": [29, 30, 29],
                        },
                        {
                            "repetitions": 6,
                            "distance_per_rep_m": 50.0,
                            "total_distance_m": 300.0,
                            "pace_mean_s_per_100m": 75.0,
                            "pace_fastest_s_per_100m": 72.0,
                            "pace_slowest_s_per_100m": 78.0,
                            "pace_range_s_per_100m": 6.0,
                            "recorded_rest_between_reps_s": [15, 15, 15, 15, 15],
                        },
                    ],
                }
            },
        }

    def test_main_set_is_selected_by_distance_and_reported_factually(self):
        insight = structured_swim_insight(self.activity())
        self.assertEqual(insight["headline"], "4×500 låg inom 1,0 s/100 m")
        self.assertEqual(
            insight["body"],
            "Snitt 1:28,0/100 m; snabbast 1:27,4/100 m och långsammast 1:28,4/100 m. Registrerad vila 29–30 s.",
        )

    def test_structured_swim_fact_wins_over_generic_ai_interpretation(self):
        analysis = {
            "assessment": {
                "interpretations": ["Tekniken såg fantastisk ut."],
                "load_interpretation": "Generisk tolkning.",
                "summary": "Generisk sammanfattning.",
            },
            "plan_action": {"action": "keep"},
        }
        insight = historical_insight(
            {"session": "Simning · aerob/teknik"},
            self.activity(),
            analysis,
            None,
        )
        self.assertEqual(insight["headline"], "4×500 låg inom 1,0 s/100 m")
        self.assertNotIn("Tekniken", insight["body"])
        self.assertIn("1:28,0/100 m", insight["body"])

    def test_unstructured_swim_does_not_invent_set_insight(self):
        activity = {"sport_type": "Swim", "workout_analysis_context": {"swim": {"structured": False}}}
        self.assertIsNone(structured_swim_insight(activity))


if __name__ == "__main__":
    unittest.main()
