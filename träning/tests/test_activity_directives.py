#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from apply_activity_directives import apply_directives, ActivityDirectiveError  # noqa: E402


class ActivityDirectiveTests(unittest.TestCase):
    def test_merges_only_explicit_fields_and_preserves_backend_feedback(self):
        activities = {"activities": [{"id": 20326850936, "sport_type": "Run"}]}
        overrides = {
            "schema_version": 1,
            "overrides": {
                "20326850936": {
                    "sport": "Run",
                    "classification": "training",
                    "display_label": "Löpning",
                    "training_feedback": {"text": "Pigg", "rpe": 5},
                }
            },
        }
        config = {
            "schema_version": 1,
            "directives": [
                {
                    "activity_id": "20326850936",
                    "set": {
                        "display_label": "Löpning · backintervaller",
                        "user_report": "3 × 8 backintervaller.",
                    },
                }
            ],
        }

        applied, skipped = apply_directives(activities, overrides, config)

        self.assertEqual((applied, skipped), (1, 0))
        merged = overrides["overrides"]["20326850936"]
        self.assertEqual(merged["display_label"], "Löpning · backintervaller")
        self.assertEqual(merged["user_report"], "3 × 8 backintervaller.")
        self.assertEqual(merged["training_feedback"], {"text": "Pigg", "rpe": 5})
        self.assertEqual(merged["sport"], "Run")

    def test_missing_historical_activity_is_skipped_without_breaking_pipeline(self):
        activities = {"activities": [{"id": 1, "sport_type": "Run"}]}
        overrides = {"schema_version": 1, "overrides": {}}
        config = {
            "schema_version": 1,
            "directives": [{"activity_id": "999", "set": {"sport": "Run"}}],
        }
        self.assertEqual(apply_directives(activities, overrides, config), (0, 1))
        self.assertEqual(overrides["overrides"], {})

    def test_duplicate_target_fails_closed(self):
        activities = {"activities": [{"id": 1, "sport_type": "Run"}]}
        overrides = {"schema_version": 1, "overrides": {}}
        config = {
            "schema_version": 1,
            "directives": [
                {"activity_id": "1", "set": {"sport": "Run"}},
                {"activity_id": "1", "set": {"sport": "Run"}},
            ],
        }
        with self.assertRaises(ActivityDirectiveError):
            apply_directives(activities, overrides, config)


if __name__ == "__main__":
    unittest.main()
