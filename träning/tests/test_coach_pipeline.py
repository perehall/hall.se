#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import coach as legacy  # noqa: E402
from coach_pipeline import (  # noqa: E402
    COACH_PIPELINE_CONTRACT_VERSION,
    latest_for_analysis,
)


class CoachPipelineTests(unittest.TestCase):
    def test_latest_input_contains_deterministic_plan_comparison(self):
        latest = {
            "id": 20057585521,
            "sport_type": "Run",
            "moving_time_s": 6960,
            "workout_analysis_context": {
                "contract_version": 1,
                "coach_prompt_sha256": "a" * 64,
            },
        }
        plan = {
            "days": [
                {
                    "date": "2026-09-06",
                    "session": "Löpning · lugn distans · 75 min",
                    "dose_resolution": {"kind": "duration_minutes", "value": 75},
                    "dose_options": [
                        {"kind": "duration_minutes", "value": 75},
                        {"kind": "duration_minutes", "value": 90},
                    ],
                }
            ]
        }
        enriched, comparison = latest_for_analysis(latest, plan, "2026-09-06")
        context = enriched["workout_analysis_context"]
        self.assertEqual(
            context["coach_pipeline_contract_version"],
            COACH_PIPELINE_CONTRACT_VERSION,
        )
        self.assertEqual(
            comparison["duration_relation_to_approved_options"],
            "above_approved_duration_range",
        )
        self.assertIs(context["plan_comparison"], comparison)

    def test_plan_comparison_changes_trigger_hash(self):
        base_latest = {
            "id": 1,
            "workout_analysis_context": {
                "contract_version": 1,
                "coach_prompt_sha256": "a" * 64,
            },
        }
        a = dict(base_latest)
        a["workout_analysis_context"] = dict(base_latest["workout_analysis_context"])
        a["workout_analysis_context"]["plan_comparison"] = {
            "selected_duration_minutes": 75
        }
        b = dict(base_latest)
        b["workout_analysis_context"] = dict(base_latest["workout_analysis_context"])
        b["workout_analysis_context"]["plan_comparison"] = {
            "selected_duration_minutes": 90
        }
        self.assertNotEqual(
            legacy.stable_hash({}, a, "2026-09-06"),
            legacy.stable_hash({}, b, "2026-09-06"),
        )


if __name__ == "__main__":
    unittest.main()
