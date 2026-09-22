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

    def test_previous_day_activities_remain_open_for_feedback_after_midnight(self):
        page = """<html><head><style></style></head><body>
<!-- training-brain-v1:start --><section>Idag</section><!-- training-brain-v1:end -->
</body></html>"""
        activities = {
            "activities": [
                {
                    "id": 201,
                    "name": "Enduro på kvällen",
                    "sport_type": "Enduro",
                    "display_label": "Enduro",
                    "start_date_local": "2026-09-21T17:44:36+02:00",
                },
                {
                    "id": 202,
                    "name": "Styrketräning på kvällen",
                    "sport_type": "WeightTraining",
                    "start_date_local": "2026-09-21T20:47:51+02:00",
                },
            ]
        }
        rendered = apply_training_input_ui(page, {"days": []}, activities, "2026-09-22")
        self.assertIn('data-activity-id="201"', rendered)
        self.assertIn('data-activity-id="202"', rendered)
        self.assertIn("Feedback · Enduro", rendered)
        self.assertIn("Feedback · Styrketräning på kvällen", rendered)
        self.assertIn("querySelectorAll('[data-training-input]')", rendered)

    def test_no_recent_activity_means_no_input_surface(self):
        page = """<html><head><style></style></head><body>
<!-- training-brain-v1:start --><section>Idag</section><!-- training-brain-v1:end -->
</body></html>"""
        activities = {
            "activities": [
                {
                    "id": 301,
                    "sport_type": "Run",
                    "start_date_local": "2026-09-19T12:00:00+02:00",
                }
            ]
        }
        rendered = apply_training_input_ui(page, {"days": []}, activities, "2026-09-22")
        self.assertNotIn("data-training-input", rendered)


if __name__ == "__main__":
    unittest.main()
