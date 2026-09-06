#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_completed_sport_icon import decorate_completed_today_icon  # noqa: E402


class CompletedSportIconTests(unittest.TestCase):
    def setUp(self):
        self.page = '''<html><head><style></style></head><body>
<section class="today-outcome" data-post-workout-state="completed" aria-labelledby="todayOutcomeTitle">
  <div class="today-outcome-main">
    <h2 class="today-outcome-title" id="todayOutcomeTitle">Löpning · 50:36</h2>
  </div>
</section>
</body></html>'''
        self.plan = {
            "days": [
                {
                    "date": "2026-09-06",
                    "sport": "run",
                    "session": "Löpning · lugn distans",
                }
            ]
        }
        self.upcoming = {"days": [{"date": "2026-09-07", "session": "Enduro"}]}
        self.activities = {
            "activities": [
                {
                    "id": 1,
                    "sport_type": "Run",
                    "start_date_local": "2026-09-06T08:00:00",
                }
            ]
        }
        self.icons = {
            "run": {"viewBox": "0 0 10 10", "path": "M1 1h8v8H1z"},
            "swim": {"viewBox": "0 0 10 10", "path": "M0 5h10"},
        }

    def test_completed_today_title_gets_run_icon(self):
        rendered = decorate_completed_today_icon(
            self.page,
            self.plan,
            self.upcoming,
            self.activities,
            "2026-09-06",
            self.icons,
        )
        self.assertIn('data-completed-sport-icon="run"', rendered)
        self.assertIn('class="sport-icon icon-run"', rendered)
        self.assertIn('<span>Löpning · 50:36</span>', rendered)
        self.assertIn('/* completed-sport-icon-v1 */', rendered)

    def test_actual_activity_fallback_selects_swim_icon_when_plan_sport_missing(self):
        plan = {
            "days": [
                {
                    "date": "2026-09-06",
                    "session": "Simning · aerob",
                }
            ]
        }
        activities = {
            "activities": [
                {
                    "id": 2,
                    "sport_type": "Swim",
                    "start_date_local": "2026-09-06T08:00:00",
                }
            ]
        }
        rendered = decorate_completed_today_icon(
            self.page.replace("Löpning", "Simning"),
            plan,
            self.upcoming,
            activities,
            "2026-09-06",
            self.icons,
        )
        self.assertIn('data-completed-sport-icon="swim"', rendered)
        self.assertIn('class="sport-icon icon-swim"', rendered)


if __name__ == "__main__":
    unittest.main()
