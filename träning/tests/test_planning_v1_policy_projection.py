#!/usr/bin/env python3
"""Strict global Planning Engine v1 policy projection tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_policy_projection import (  # noqa: E402
    PolicyProjectionError,
    compile_policy_projection,
)


def explicit_policy():
    return {
        "decision_guards": [
            "Legacy guard text must not become executable V1 policy."
        ],
        "planning_engine_v1": {
            "schema_version": 1,
            "policy_revision": {
                "revision_id": "policy-v1",
                "source_refs": ["policy:reviewed"],
                "compatibility_policy": {
                    "policy_id": "compat-v1",
                    "source_refs": ["policy:reviewed"],
                    "rules": [
                        {
                            "rule_id": "mechanical-before-cardio",
                            "first_dimension": "mechanical_leg",
                            "first_min_level": "high",
                            "second_dimension": "cardiovascular",
                            "second_min_level": "high",
                            "min_calendar_separation_days": 1,
                            "min_first_to_second_days": 2,
                            "min_second_to_first_days": 1,
                            "same_day_order": "forbidden",
                            "source_refs": ["policy:reviewed"],
                        }
                    ],
                },
                "spacing_preferences": [
                    {
                        "subject_kind": "capability",
                        "subject": "swim_aerobic",
                        "desired_min_gap_days": 2,
                        "min_level": "low",
                    }
                ],
            },
        },
    }


class V1PolicyProjectionTests(unittest.TestCase):
    def test_explicit_global_policy_compiles_without_athlete_defaults(self):
        result = compile_policy_projection(explicit_policy())
        self.assertEqual(result.revision_id, "policy-v1")
        self.assertEqual(
            result.compatibility_policy.rules[0].first_to_second_days,
            2,
        )
        self.assertEqual(
            result.compatibility_policy.rules[0].second_to_first_days,
            1,
        )
        self.assertEqual(
            result.spacing_preferences[0].subject,
            "swim_aerobic",
        )

    def test_legacy_decision_guards_cannot_substitute_for_v1_policy(self):
        document = explicit_policy()
        document.pop("planning_engine_v1")
        with self.assertRaises(PolicyProjectionError) as raised:
            compile_policy_projection(document)
        self.assertEqual(
            raised.exception.code,
            "MISSING_V1_POLICY_PROJECTION",
        )

    def test_athlete_schedule_preferences_are_forbidden_in_global_policy(self):
        document = explicit_policy()
        document["planning_engine_v1"]["policy_revision"]["objective_policy"] = {
            "schedule": {
                "preferred_active_days": 5,
                "min_active_days": 0,
                "max_active_days": 7,
                "double_sessions": "sometimes",
            }
        }
        with self.assertRaises(PolicyProjectionError) as raised:
            compile_policy_projection(document)
        self.assertEqual(
            raised.exception.code,
            "ATHLETE_PREFERENCES_IN_GLOBAL_POLICY",
        )

    def test_policy_projection_contains_no_legacy_planner_dependency(self):
        import training_core.application.planning_policy_projection as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("decision_guards", source)
        self.assertNotIn("microcycle_policy", source)
        self.assertNotIn("preferred_active_days", source)
        self.assertNotIn("double_sessions", source)


if __name__ == "__main__":
    unittest.main()
