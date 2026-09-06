#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import coach as legacy  # noqa: E402
from coach_pipeline import (  # noqa: E402
    COACH_PIPELINE_CONTRACT_VERSION,
    DEFERRED_REVIEW_REASON,
    analysis_code_signature,
    concretize_deferred_review,
    latest_for_analysis,
)


class CoachPipelineTests(unittest.TestCase):
    def test_latest_input_contains_deterministic_plan_comparison_and_code_signature(self):
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
        enriched, comparison = latest_for_analysis(
            latest,
            plan,
            "2026-09-06",
            code_signature="c" * 64,
        )
        context = enriched["workout_analysis_context"]
        self.assertEqual(
            context["coach_pipeline_contract_version"],
            COACH_PIPELINE_CONTRACT_VERSION,
        )
        self.assertEqual(context["analysis_code_sha256"], "c" * 64)
        self.assertEqual(
            comparison["duration_relation_to_approved_options"],
            "above_approved_duration_range",
        )
        self.assertIs(context["plan_comparison"], comparison)

    def test_analysis_code_signature_changes_when_contract_code_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "a.py"
            second = Path(temp_dir) / "b.py"
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")
            signature_a = analysis_code_signature((first, second))
            first.write_text("changed", encoding="utf-8")
            signature_b = analysis_code_signature((first, second))
            self.assertNotEqual(signature_a, signature_b)

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

    def test_deferred_review_names_fixed_enduro_and_following_threshold(self):
        action = {
            "action": "review",
            "target_date": "",
            "reason": DEFERRED_REVIEW_REASON,
            "recommendation": "Generic.",
            "requires_approval": False,
        }
        plan = {
            "days": [
                {
                    "date": "2026-09-07",
                    "label": "Måndag",
                    "session": "Enduroskola · fast tillfälle",
                    "planning_status": "fixed",
                    "manual_lock": True,
                },
                {
                    "date": "2026-09-08",
                    "label": "Tisdag",
                    "session": "Löpning · kontrollerad tröskel · 3 × 10 min / 90 s jogg",
                    "planning_status": "preliminary",
                },
            ]
        }
        normalized = concretize_deferred_review(action, plan, "2026-09-06")
        self.assertIn("Måndag: Enduroskola · fast tillfälle", normalized["recommendation"])
        self.assertIn("Tisdag: Löpning · kontrollerad tröskel", normalized["recommendation"])
        self.assertIn("måndag", normalized["recommendation"])


if __name__ == "__main__":
    unittest.main()
