#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from adaptive_planner import (  # noqa: E402
    generated_capability_portfolio,
    response_profile_for_recipe,
)
from capability_registry import (  # noqa: E402
    capability_recipe_family,
    validate_registry_against_catalog,
)
from capability_state import build_capability_states  # noqa: E402
from dose_response import build_dose_response  # noqa: E402


class CapabilityFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(
            (ROOT / "data" / "workout_catalog.json").read_text(encoding="utf-8")
        )
        cls.policy = json.loads(
            (ROOT / "data" / "planning_policy.json").read_text(encoding="utf-8")
        )

    def test_registry_matches_catalog_and_owns_recipe_families(self):
        self.assertEqual(validate_registry_against_catalog(self.catalog), [])
        self.assertEqual(
            capability_recipe_family("run_threshold"),
            ("run_threshold", "run_threshold_short_reps"),
        )
        self.assertGreaterEqual(len(capability_recipe_family("swim_aerobic")), 3)

    def test_unlinked_generic_swim_is_not_promoted_to_aerobic_dose_response(self):
        sessions = [{
            "id": 1,
            "date": "2026-10-01",
            "family": "swim",
            "classification": "training",
            "elapsed_time_s": 3600,
            "distance_m": 3200,
            "user_report": "Bra kontroll.",
            "training_profile": {
                "stimuli": [],
                "planning_credits": [],
            },
        }]
        result = build_dose_response(sessions, [], today="2026-10-05")
        swim = result["by_capability"]["swim_aerobic"]
        self.assertEqual(swim["evidence_state"], "missing")
        self.assertFalse(swim["progression_ready"])

    def test_plan_matched_repeated_swim_can_become_absorbed(self):
        sessions = [
            {
                "id": 1,
                "date": "2026-09-25",
                "family": "swim",
                "classification": "training",
                "elapsed_time_s": 3600,
                "distance_m": 3200,
                "user_report": "Bra kontroll, pigg.",
                "training_profile": {
                    "stimuli": [],
                    "planning_credits": ["swim_aerobic", "swim_technique"],
                },
            },
            {
                "id": 2,
                "date": "2026-10-01",
                "family": "swim",
                "classification": "training",
                "elapsed_time_s": 3650,
                "distance_m": 3200,
                "user_report": "Riktigt bra, kände mig stark.",
                "training_profile": {
                    "stimuli": [],
                    "planning_credits": ["swim_aerobic", "swim_technique"],
                },
            },
        ]
        result = build_dose_response(sessions, [], today="2026-10-05")
        swim = result["by_capability"]["swim_aerobic"]
        self.assertEqual(swim["absorbed_value"], 3200)
        self.assertTrue(swim["progression_ready"])
        self.assertEqual(swim["progression_state"], "ready")
        self.assertEqual(swim["progression_reason_code"], "absorbed_supportive_repeat")
        self.assertTrue(
            all(
                row["evidence_basis"] == "confirmed_or_plan_matched"
                for row in swim["exposures"]
            )
        )

    def test_technique_can_be_observed_without_fake_numeric_progression(self):
        sessions = [{
            "id": 9,
            "date": "2026-10-01",
            "family": "swim",
            "classification": "training",
            "elapsed_time_s": 3600,
            "distance_m": 3200,
            "user_report": "Bra kontroll.",
            "training_profile": {
                "stimuli": [],
                "planning_credits": ["swim_aerobic", "swim_technique"],
            },
        }]
        dose = build_dose_response(sessions, [], today="2026-10-05")
        states = build_capability_states(sessions, dose)
        technique = states["by_capability"]["swim_technique"]
        self.assertEqual(technique["evidence_state"], "observed")
        self.assertEqual(technique["progression_state"], "qualitative_review")
        self.assertFalse(technique["progression_ready"])
        self.assertIsNone(technique["metric"])

    def test_planner_prefers_capability_state_over_legacy_dose_response(self):
        athlete_state = {
            "capability_states": {
                "by_capability": {
                    "run_threshold": {
                        "progression_ready": True,
                        "absorbed_value": 32.0,
                        "progression_reason": "state layer",
                    }
                }
            },
            "dose_response": {
                "by_capability": {
                    "run_threshold": {
                        "progression_ready": False,
                        "absorbed_value": 24.0,
                        "progression_reason": "legacy layer",
                    }
                }
            },
        }
        profile = response_profile_for_recipe("run_threshold_short_reps", athlete_state)
        self.assertTrue(profile["progression_ready"])
        self.assertEqual(profile["absorbed_value"], 32.0)
        self.assertEqual(profile["progression_reason"], "state layer")

    def test_generated_portfolio_exposes_progression_semantics(self):
        meso = {
            "primary_capabilities": ["run_threshold"],
            "secondary_capabilities": ["swim_aerobic"],
        }
        rows = generated_capability_portfolio(self.policy, meso)
        threshold = next(row for row in rows if row["key"] == "run_threshold")
        self.assertEqual(threshold["response_metric"], "work_minutes")
        self.assertIn("interval_structure", threshold["progression_axes"])
        self.assertIn("run_threshold_short_reps", threshold["recipe_family"])
        self.assertEqual(threshold["evidence_policy"], "confirmed_or_plan_matched")


if __name__ == "__main__":
    unittest.main()
