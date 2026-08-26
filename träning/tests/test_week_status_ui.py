#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_week_status_ui import promote_week_status  # noqa: E402


class WeekStatusUiTests(unittest.TestCase):
    def test_week_status_moves_directly_under_current_week_heading(self):
        page = '''<html><style></style><body>
<h2 class="section">Aktuell vecka</h2>
<div class="day" id="dag-2026-08-26">Onsdag</div>
<details class="week-state"><summary>Veckoläge</summary><section class="dashboard" aria-label="Veckoöversikt"><div class="metrics">Mått</div><div class="dashboard-grid"><div class="dashboard-card">Grenfördelning</div><div class="dashboard-card">Plan → utfall</div></div><div class="dashboard-card"><div class="dashboard-title">Nästa dagar</div></div></section></details>
<div class="reference-tools"></div>
</body></html>'''
        rendered = promote_week_status(page)
        heading = rendered.find('<h2 class="section">Aktuell vecka</h2>')
        overview = rendered.find('class="week-overview"')
        day = rendered.find('id="dag-2026-08-26"')
        self.assertGreater(overview, heading)
        self.assertGreater(day, overview)
        self.assertNotIn('class="week-state"', rendered)
        self.assertNotIn('<summary>Veckoläge</summary>', rendered)
        self.assertIn('.week-overview .dashboard>.dashboard-card:last-child{display:none}', rendered)
        self.assertIn('Grenfördelning', rendered)
        self.assertIn('Plan → utfall', rendered)

    def test_transform_is_idempotent(self):
        page = '''<html><style></style><body><h2 class="section">Aktuell vecka</h2><div class="day">Dag</div><details class="week-state"><summary>Veckoläge</summary><section class="dashboard" aria-label="Veckoöversikt"></section></details></body></html>'''
        once = promote_week_status(page)
        twice = promote_week_status(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
