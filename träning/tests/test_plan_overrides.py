#!/usr/bin/env python3
import sys
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from apply_plan_overrides import apply_overrides  # noqa: E402


class PlanOverrideTests(unittest.TestCase):
    def setUp(self):
        self.document = {
            "schema_version": 3,
            "meta": {"missing_protected_stimuli": []},
            "days": [
                {
                    "date": "2026-09-12",
                    "label": "Lördag",
                    "status": "preliminary",
                    "session": "Simning + styrka",
                    "sport": "strength",
                    "dose_options": [{"id": "old"}],
                    "workout_design": {"selected_candidate_id": "old"},
                }
            ],
        }
        self.config = {
            "schema_version": 1,
            "overrides": [
                {
                    "date": "2026-09-12",
                    "source": "user_confirmed",
                    "note": "Fast enduro",
                    "remove_fields": ["dose_options", "workout_design"],
                    "set": {
                        "status": "planned",
                        "planning_status": "fixed",
                        "session": "Enduro · Krokek · 10:00–14:00",
                        "sport": "enduro",
                        "manual_lock": True,
                    },
                    "set_meta": {
                        "missing_protected_stimuli": ["strength_unilateral", "strength_core"],
                        "protected_capacity_follow_up": {"action": "restore_in_next_absorbable_window"},
                    },
                }
            ],
        }

    def test_replaces_session_and_strips_stale_derived_state(self):
        changed = apply_overrides(self.document, self.config)
        self.assertEqual(changed, 1)
        day = self.document["days"][0]
        self.assertEqual(day["session"], "Enduro · Krokek · 10:00–14:00")
        self.assertEqual(day["original_session"], "Simning + styrka")
        self.assertEqual(day["planning_status"], "fixed")
        self.assertTrue(day["manual_lock"])
        self.assertNotIn("dose_options", day)
        self.assertNotIn("workout_design", day)
        self.assertEqual(day["manual_override"]["source"], "user_confirmed")
        self.assertEqual(
            self.document["meta"]["missing_protected_stimuli"],
            ["strength_unilateral", "strength_core"],
        )

    def test_application_is_idempotent(self):
        self.assertEqual(apply_overrides(self.document, self.config), 1)
        once = deepcopy(self.document)
        self.assertEqual(apply_overrides(self.document, self.config), 0)
        self.assertEqual(self.document, once)

    def test_completed_truth_is_not_rewritten(self):
        day = self.document["days"][0]
        day["status"] = "completed"
        before = deepcopy(self.document)
        self.assertEqual(apply_overrides(self.document, self.config), 0)
        self.assertEqual(self.document, before)


if __name__ == "__main__":
    unittest.main()
