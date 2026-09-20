#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach_pipeline import (  # noqa: E402
    normalize_invalid_dose_option_action,
    normalize_unapplicable_plan_action,
)


class InvalidDoseOptionGuardTests(unittest.TestCase):
    def setUp(self):
        self.plan = {
            "days": [
                {
                    "date": "2026-09-11",
                    "sport": "run",
                    "dose_open": True,
                    "dose_options": [
                        {"id": "run-hill-6x150"},
                        {"id": "run-hill-2x6x150"},
                        {"id": "run-hill-3x6x150"},
                    ],
                },
                {
                    "date": "2026-09-12",
                    "sport": "bike",
                    "dose_open": True,
                    "dose_options": [
                        {"id": "mtb-support-60"},
                    ],
                },
            ]
        }

    def test_cross_day_dose_option_degrades_to_review_without_guessing(self):
        action = {
            "action": "keep",
            "target_date": "2026-09-11",
            "reason": "Behåll planerad belastning.",
            "recommendation": "Kör stöddosen.",
            "dose_option_id": "mtb-support-60",
            "requires_approval": False,
        }

        normalized = normalize_invalid_dose_option_action(action, self.plan)

        self.assertEqual(normalized["action"], "review")
        self.assertEqual(normalized["target_date"], "")
        self.assertEqual(normalized["dose_option_id"], "")
        self.assertFalse(normalized["requires_approval"])
        self.assertIn("matchar inte", normalized["reason"])
        self.assertIn("ingen automatisk ändring", normalized["recommendation"])

    def test_missing_target_for_reduce_degrades_to_review(self):
        action = {
            "action": "reduce",
            "target_date": "",
            "reason": "Minska nästa pass.",
            "recommendation": "Kör mindre.",
            "dose_option_id": "",
            "requires_approval": False,
        }

        normalized = normalize_unapplicable_plan_action(
            action,
            self.plan,
            ready_dates=["2026-09-11"],
            local_date="2026-09-10",
        )

        self.assertEqual(normalized["action"], "review")
        self.assertEqual(normalized["target_date"], "")
        self.assertEqual(normalized["dose_option_id"], "")
        self.assertFalse(normalized["requires_approval"])
        self.assertIn("ingen automatisk ändring", normalized["recommendation"])

    def test_residual_invalid_option_degrades_to_review(self):
        action = {
            "action": "reduce",
            "target_date": "2026-09-11",
            "reason": "Konservativ justering.",
            "recommendation": "Kör ett okänt alternativ.",
            "dose_option_id": "invented-option",
            "requires_approval": False,
        }

        normalized = normalize_unapplicable_plan_action(
            action,
            self.plan,
            ready_dates=["2026-09-11"],
            local_date="2026-09-10",
        )

        self.assertEqual(normalized["action"], "review")
        self.assertEqual(normalized["target_date"], "")
        self.assertEqual(normalized["dose_option_id"], "")

    def test_valid_same_day_option_is_preserved(self):
        action = {
            "action": "reduce",
            "target_date": "2026-09-11",
            "reason": "Konservativ justering.",
            "recommendation": "Kör kortare backdos.",
            "dose_option_id": "run-hill-2x6x150",
            "requires_approval": False,
        }

        normalized = normalize_invalid_dose_option_action(action, self.plan)

        self.assertEqual(normalized, action)


if __name__ == "__main__":
    unittest.main()
