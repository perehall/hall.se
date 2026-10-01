#!/usr/bin/env python3
"""Strict athlete schedule-preference projection tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_profile_projection import (  # noqa: E402
    ProfileProjectionError,
    compile_athlete_planning_preferences,
)


def profile_record():
    return {
        "status": "found",
        "revision": 7,
        "updated_at": "2026-10-01T10:00:00Z",
        "profile": {
            "schema_version": 1,
            "status": "complete",
            "current_step": 12,
            "preferences": {
                "frequency": {
                    "preferred_days": 6,
                    "min_days": 5,
                    "max_days": 7,
                },
                "double_sessions": "sometimes",
                "rest_days": "load_driven",
            },
        },
    }


class AthletePlanningPreferencesProjectionTests(unittest.TestCase):
    def test_explicit_saved_preferences_compile(self):
        result = compile_athlete_planning_preferences(profile_record())
        self.assertEqual(result.revision_id, "athlete-profile:7")
        self.assertEqual(result.schedule.preferred_active_days, 6)
        self.assertEqual(result.schedule.min_active_days, 5)
        self.assertEqual(result.schedule.max_active_days, 7)
        self.assertEqual(result.schedule.double_sessions.value, "sometimes")

    def test_missing_preference_never_falls_back_to_ui_default(self):
        document = profile_record()
        del document["profile"]["preferences"]["frequency"]["preferred_days"]
        with self.assertRaises(ProfileProjectionError) as raised:
            compile_athlete_planning_preferences(document)
        self.assertEqual(
            raised.exception.code,
            "INCOMPLETE_ATHLETE_SCHEDULE_PREFERENCES",
        )

    def test_draft_profile_cannot_drive_planning_preferences(self):
        document = profile_record()
        document["profile"]["status"] = "draft"
        with self.assertRaises(ProfileProjectionError) as raised:
            compile_athlete_planning_preferences(document)
        self.assertEqual(
            raised.exception.code,
            "ATHLETE_PROFILE_NOT_COMPLETE",
        )

    def test_not_found_profile_blocks(self):
        document = {"status": "not_found"}
        with self.assertRaises(ProfileProjectionError) as raised:
            compile_athlete_planning_preferences(document)
        self.assertEqual(
            raised.exception.code,
            "MISSING_CANONICAL_ATHLETE_PROFILE",
        )

    def test_projection_has_no_onboarding_default_dependency(self):
        import training_core.application.planning_profile_projection as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("onboarding", source.lower())
        self.assertNotIn("preferred_days=6", source)
        self.assertNotIn('double_sessions="sometimes"', source)


if __name__ == "__main__":
    unittest.main()
