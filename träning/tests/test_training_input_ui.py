#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_training_input_ui import apply_training_input_ui  # noqa: E402


class TrainingInputUiTests(unittest.TestCase):
    def test_post_workout_card_gets_compact_input_surface(self):
        page = """<html><head><style>body{}</style></head><body>
<section class="today-outcome"><h2>Klart</h2><a class="today-outcome-link" href="#aktuell-vecka">Se hela planen ↓</a></section>
</body></html>"""
        plan = {
            "days": [
                {
                    "date": "2026-09-21",
                    "sport": "run",
                    "activity_id": 123,
                }
            ]
        }
        activities = {
            "activities": [
                {
                    "id": 123,
                    "sport_type": "Run",
                    "start_date_local": "2026-09-21T18:00:00+02:00",
                }
            ]
        }
        rendered = apply_training_input_ui(page, plan, activities, "2026-09-21")
        self.assertIn('data-training-input', rendered)
        self.assertIn('data-activity-id="123"', rendered)
        self.assertIn("Mycket lätt", rendered)
        self.assertIn("Kunde gjort mer", rendered)
        self.assertIn("Blev 4 × 8", rendered)
        self.assertIn("fetch('/training-api/input'", rendered)
        self.assertIn("NATURAL_LANGUAGE", rendered)

    def test_no_completed_card_means_no_input_surface(self):
        page = "<html><head><style></style></head><body></body></html>"
        rendered = apply_training_input_ui(page, {"days": []}, {"activities": []}, "2026-09-21")
        self.assertNotIn("data-training-input", rendered)


if __name__ == "__main__":
    unittest.main()
