#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_post_workout_ui import apply_post_workout_ui  # noqa: E402


BASE_PAGE = """<!doctype html><html><head><style>.hero{}</style></head><body><div class="wrap">
<!-- training-brain-v1:start -->
<section class="training-brain"><div>Dagens plan</div></section>
<!-- training-brain-v1:end -->
<section class="dashboard"></section>
<h2 class="section">Aktuell vecka</h2>
</div></body></html>"""


class PlannedActivityBindingTests(unittest.TestCase):
    def test_post_workout_uses_analysis_for_planned_activity_id_not_latest_same_day_analysis(self):
        plan = {
            "meta": {"timezone": "Europe/Stockholm"},
            "days": [
                {
                    "date": "2026-09-07",
                    "label": "Måndag",
                    "status": "completed",
                    "sport": "enduro",
                    "classification": "training",
                    "session": "Enduroskola · fast tillfälle",
                    "activity_id": 20078705519,
                },
                {
                    "date": "2026-09-08",
                    "label": "Tisdag",
                    "status": "planned",
                    "sport": "run",
                    "session": "Löpning · kontrollerad tröskel · 3 × 10 min / 90 s jogg",
                },
            ],
        }
        activities = {
            "activities": [
                {
                    "id": 20078705519,
                    "name": "Enduro på kvällen",
                    "sport_type": "Enduro",
                    "display_label": "Enduro",
                    "classification": "training",
                    "start_date_local": "2026-09-07T18:04:35Z",
                    "elapsed_time_s": 5718,
                    "moving_time_s": 2915,
                    "distance_m": 14637.8,
                    "average_heartrate": 106.7,
                    "max_heartrate": 168,
                },
                {
                    "id": 20079150228,
                    "name": "Styrketräning på natten",
                    "sport_type": "WeightTraining",
                    "start_date_local": "2026-09-07T21:00:00Z",
                    "elapsed_time_s": 1659,
                },
            ]
        }
        coach = {
            "analyses": [
                {
                    "activity_id": 20079150228,
                    "activity_date": "2026-09-07",
                    "generated_at_utc": "2026-09-07T21:10:00Z",
                    "assessment": {
                        "summary": "STRENGTH_ANALYSIS should never appear on Enduro card.",
                        "load_interpretation": "Strength load.",
                    },
                    "plan_action": {"action": "keep", "target_date": ""},
                },
                {
                    "activity_id": 20078705519,
                    "activity_date": "2026-09-07",
                    "generated_at_utc": "2026-09-07T20:00:00Z",
                    "assessment": {
                        "summary": "ENDURO_ANALYSIS belongs to the planned Enduro session.",
                        "load_interpretation": "Enduro load.",
                    },
                    "plan_action": {"action": "keep", "target_date": "2026-09-08"},
                },
            ]
        }
        rendered = apply_post_workout_ui(
            BASE_PAGE,
            plan,
            activities,
            coach,
            {"entries": []},
            "2026-09-07",
        )
        self.assertIn("Enduro · 1:35:18", rendered)
        self.assertIn("ENDURO_ANALYSIS", rendered)
        self.assertNotIn("STRENGTH_ANALYSIS", rendered)
        self.assertIn("3 × 10 min / 90 s jogg", rendered)


if __name__ == "__main__":
    unittest.main()
