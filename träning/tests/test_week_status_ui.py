#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_week_status_ui import compact_duration, promote_week_status  # noqa: E402


class WeekStatusUiTests(unittest.TestCase):
    def test_compact_duration_drops_only_zero_seconds(self):
        self.assertEqual(compact_duration("2:58:00"), "2:58")
        self.assertEqual(compact_duration("2:58:37"), "2:58:37")
        self.assertEqual(compact_duration("48:23"), "48:23")

    def test_week_status_expander_sits_directly_under_current_week_heading(self):
        page = '''<html><style></style><body>
<h2 class="section">Aktuell vecka</h2>
<div class="day" id="dag-2026-08-26">Onsdag</div>
<details class="week-state"><summary>Veckoläge</summary><section class="dashboard" aria-label="Veckoöversikt"><div class="metrics"><div class="metric"><strong>3</strong><span>pass</span></div><div class="metric"><strong>2:58:00</strong><span>passtid</span></div><div class="metric"><strong>2</strong><span>träningsdagar</span></div></div><div class="dashboard-grid"><div class="dashboard-card">Grenfördelning</div><div class="dashboard-card">Plan → utfall</div></div><div class="dashboard-card"><div class="dashboard-title">Nästa dagar</div></div></section></details>
<div class="reference-tools"></div>
</body></html>'''
        rendered = promote_week_status(page)
        heading = rendered.find('<h2 class="section">Aktuell vecka</h2>')
        status = rendered.find('class="week-status"')
        day = rendered.find('id="dag-2026-08-26"')
        self.assertGreater(status, heading)
        self.assertGreater(day, status)
        self.assertNotIn('class="week-state"', rendered)
        self.assertNotIn('<summary>Veckoläge</summary>', rendered)
        self.assertNotIn('class="week-overview"', rendered)
        self.assertIn('<summary>Veckostatus · 3 pass · 2:58 · 2 dagar</summary>', rendered)
        self.assertIn('.week-status>summary:after{content:" +"}', rendered)
        self.assertIn('.week-status[open]>summary:after{content:" −"}', rendered)
        self.assertIn('.week-status .dashboard>.dashboard-card:last-child{display:none}', rendered)
        self.assertIn('Grenfördelning', rendered)
        self.assertIn('Plan → utfall', rendered)

    def test_singular_day_is_used_when_needed(self):
        page = '''<html><style></style><body><h2 class="section">Aktuell vecka</h2><div class="day">Dag</div><details class="week-state"><summary>Veckoläge</summary><section class="dashboard" aria-label="Veckoöversikt"><div class="metrics"><div class="metric"><strong>1</strong><span>pass</span></div><div class="metric"><strong>45:00</strong><span>passtid</span></div><div class="metric"><strong>1</strong><span>träningsdagar</span></div></div></section></details></body></html>'''
        rendered = promote_week_status(page)
        self.assertIn('Veckostatus · 1 pass · 45:00 · 1 dag', rendered)

    def test_transform_is_idempotent(self):
        page = '''<html><style></style><body><h2 class="section">Aktuell vecka</h2><div class="day">Dag</div><details class="week-state"><summary>Veckoläge</summary><section class="dashboard" aria-label="Veckoöversikt"><div class="metrics"><div class="metric"><strong>0</strong><span>pass</span></div><div class="metric"><strong>0:00</strong><span>passtid</span></div><div class="metric"><strong>0</strong><span>träningsdagar</span></div></div></section></details></body></html>'''
        once = promote_week_status(page)
        twice = promote_week_status(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
