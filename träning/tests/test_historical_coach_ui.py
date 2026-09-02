#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_historical_coach_ui import strip_past_coaches, validate  # noqa: E402


class HistoricalCoachUiTests(unittest.TestCase):
    def test_past_completed_raw_coach_is_removed_but_future_coach_remains(self):
        page = '''<html><body>
<div class="day past-completed" id="dag-2026-08-24"><div class="daytop"></div><div class="coach yoda-v2"><div><div>Historiskt råd</div></div></div></div>
<div class="day decision-horizon" id="dag-2026-08-26"><div class="daytop"></div><div class="coach yoda-v2"><div>Nytt råd</div></div></div>
</body></html>'''
        rendered = strip_past_coaches(page)
        validate(rendered)
        self.assertNotIn("Historiskt råd", rendered)
        self.assertNotIn('class="historical-coach"', rendered)
        self.assertNotIn("AI-analys · historik", rendered)
        self.assertIn("Nytt råd", rendered)

    def test_old_empty_historical_wrapper_is_removed(self):
        page = '''<div class="day past-completed" id="dag-2026-08-24">
<details class="historical-coach"><summary>AI-analys · historik</summary><div class="coach yoda-v2"><div>Råd</div></div></details>
</div>'''
        rendered = strip_past_coaches(page)
        validate(rendered)
        self.assertNotIn("Råd", rendered)
        self.assertNotIn('class="historical-coach"', rendered)

    def test_transform_is_idempotent(self):
        page = '<div class="day past-completed" id="dag-2026-08-24"><div class="coach yoda-v2"><div>Råd</div></div></div>'
        once = strip_past_coaches(page)
        twice = strip_past_coaches(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
