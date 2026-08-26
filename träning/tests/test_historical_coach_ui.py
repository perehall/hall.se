#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_historical_coach_ui import validate, wrap_past_coaches  # noqa: E402


class HistoricalCoachUiTests(unittest.TestCase):
    def test_past_completed_coach_is_collapsed_but_future_coach_is_not(self):
        page = '''<html><body>
<div class="day past-completed" id="dag-2026-08-24"><div class="daytop"></div><div class="coach yoda-v2"><div><div>Historiskt råd</div></div></div></div>
<div class="day decision-horizon" id="dag-2026-08-26"><div class="daytop"></div><div class="coach yoda-v2"><div>Nytt råd</div></div></div>
</body></html>'''
        rendered = wrap_past_coaches(page)
        validate(rendered)
        self.assertEqual(rendered.count('class="historical-coach"'), 1)
        self.assertIn('<summary>AI-analys · historik</summary>', rendered)
        self.assertIn('Historiskt råd', rendered)
        self.assertIn('Nytt råd', rendered)

    def test_wrapper_is_idempotent(self):
        page = '<div class="day past-completed" id="dag-2026-08-24"><div class="coach yoda-v2"><div>Råd</div></div></div>'
        once = wrap_past_coaches(page)
        twice = wrap_past_coaches(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
