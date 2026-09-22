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
        overrides = {
            "schema_version": 1,
            "overrides": {
                "123": {
                    "training_input_event_keys": [
                        "training-input:aaaaaaaaaaaaaaaaaaaaaaaa",
                        "training-input:0123456789abcdef01234567",
                    ],
                    "last_training_input_event_key": "training-input:0123456789abcdef01234567",
                    "training_feedback": {
                        "text": "Kändes kontrollerat.",
                        "rpe": 6,
                        "feeling": ["fresh", "could_do_more"],
                    },
                }
            },
        }
        rendered = apply_training_input_ui(
            page,
            plan,
            activities,
            "2026-09-21",
            overrides_state=overrides,
        )
        self.assertIn('data-training-input', rendered)
        self.assertIn('data-activity-id="123"', rendered)
        self.assertIn(
            'data-processed-event-keys="training-input:aaaaaaaaaaaaaaaaaaaaaaaa,training-input:0123456789abcdef01234567"',
            rendered,
        )
        self.assertIn('data-reviewed="true"', rendered)
        self.assertIn("Sparat · RPE 6 · Pigg · Kunde gjort mer", rendered)
        self.assertIn("Kändes kontrollerat.", rendered)
        self.assertIn(">Ändra</button>", rendered)
        self.assertIn("Mycket lätt", rendered)
        self.assertIn("Kunde gjort mer", rendered)
        self.assertIn("fetch('/träning/training-api/input'", rendered)
        self.assertIn("NATURAL_LANGUAGE", rendered)
        self.assertIn("waitForProcessed", rendered)
        self.assertIn("cache: 'no-store'", rendered)
        self.assertIn("window.location.replace", rendered)
        self.assertIn("Uppdaterar analys…", rendered)
        self.assertIn("processedKeys.includes(eventKey)", rendered)

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
        self.assertIn(">Enduro</span>", rendered)
        self.assertIn(">Styrka</span>", rendered)
        self.assertIn(">Utvärdera</button>", rendered)
        self.assertIn("querySelectorAll('[data-training-input]')", rendered)

    def test_legacy_saved_feedback_renders_as_compact_receipt(self):
        page = """<html><head><style></style></head><body>
<!-- training-brain-v1:start --><section>Idag</section><!-- training-brain-v1:end -->
</body></html>"""
        activities = {
            "activities": [
                {
                    "id": 401,
                    "sport_type": "WeightTraining",
                    "start_date_local": "2026-09-21T20:00:00+02:00",
                }
            ]
        }
        overrides = {
            "schema_version": 1,
            "overrides": {
                "401": {
                    "user_report": "RPE 2/10. Känsla: Pigg.",
                    "last_training_input_event_key": "training-input:aaaaaaaaaaaaaaaaaaaaaaaa",
                }
            },
        }
        rendered = apply_training_input_ui(
            page,
            {"days": []},
            activities,
            "2026-09-22",
            overrides_state=overrides,
        )
        self.assertIn(">Styrka</span>", rendered)
        self.assertIn("Sparat · RPE 2 · Pigg", rendered)
        self.assertIn(">Ändra</button>", rendered)

    def test_legacy_multiple_submissions_show_latest_receipt_only(self):
        page = """<html><head><style></style></head><body>
<!-- training-brain-v1:start --><section>Idag</section><!-- training-brain-v1:end -->
</body></html>"""
        activities = {
            "activities": [
                {
                    "id": 402,
                    "sport_type": "Enduro",
                    "start_date_local": "2026-09-21T18:00:00+02:00",
                }
            ]
        }
        overrides = {
            "schema_version": 1,
            "overrides": {
                "402": {
                    "user_report": (
                        "Första kommentaren. RPE 4/10. Känsla: Pigg. "
                        "Senaste kommentaren. RPE 6/10."
                    ),
                    "last_training_input_event_key": "training-input:aaaaaaaaaaaaaaaaaaaaaaaa",
                }
            },
        }
        rendered = apply_training_input_ui(
            page,
            {"days": []},
            activities,
            "2026-09-22",
            overrides_state=overrides,
        )
        self.assertIn("Sparat · RPE 6", rendered)
        self.assertIn("Senaste kommentaren.", rendered)
        self.assertNotIn("Första kommentaren.", rendered)

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
