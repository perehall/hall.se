#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_user_report_ui import apply_user_reports  # noqa: E402


PAGE = """<!doctype html><html><head><style>.x{}</style></head><body>
<section class="week-activity-insight" data-week-activity-insight="20092166843">
  <div class="week-activity-insight-kicker">Passinsikt</div>
  <h3>Tröskelpasset är registrerat</h3>
</section>
</body></html>"""


class UserReportUiTests(unittest.TestCase):
    def test_explicit_report_is_rendered_verbatim_on_matching_activity(self):
        activities = {
            "activities": [
                {
                    "id": 20092166843,
                    "user_report": (
                        "Löpband 4 × 8 min Tempo enligt Garmin. "
                        "Sista intervallen krävde lite mental ansträngning trots att pulsen bara låg runt 162 bpm i slutet."
                    ),
                }
            ]
        }
        rendered = apply_user_reports(PAGE, activities)
        self.assertIn("Din kommentar", rendered)
        self.assertIn("Löpband 4 × 8 min Tempo enligt Garmin.", rendered)
        self.assertIn("runt 162 bpm", rendered)

    def test_report_for_unmatched_activity_is_not_invented_into_page(self):
        activities = {"activities": [{"id": 99, "user_report": "Separat rapport"}]}
        rendered = apply_user_reports(PAGE, activities)
        self.assertNotIn("Separat rapport", rendered)
        self.assertNotIn("Din kommentar", rendered)

    def test_transform_is_idempotent(self):
        activities = {"activities": [{"id": 20092166843, "user_report": "4 × 8 min, kontrollerat."}]}
        once = apply_user_reports(PAGE, activities)
        twice = apply_user_reports(once, activities)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count('class="week-activity-user-report"'), 1)


if __name__ == "__main__":
    unittest.main()
