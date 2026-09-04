#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_human_training_language import humanize_page  # noqa: E402


class HumanTrainingLanguageTests(unittest.TestCase):
    def test_statuses_and_completed_details_use_human_language(self):
        page = '''
<div class="badge planned">PLANERAT</div>
<div class="badge conditional">VILLKORAT</div>
<div class="badge open">ÖPPET</div>
<div class="dashboard-legend">✓ genomfört · ● planerat · ◐ preliminärt/villkorat · · öppet</div>
<section data-post-workout-state="completed">
  <div class="today-outcome-compare">
    <div><span class="today-outcome-label">Plan</span><strong>6 × 150 m</strong></div>
    <div><span class="today-outcome-label">Utfall</span><strong>Löpning på kvällen</strong></div>
  </div>
  <strong>Stabilt utan tydlig försämring i lapparna</strong>
</section>
'''
        rendered = humanize_page(page, reported_structure="3 × 6 backintervaller (18 totalt)")

        self.assertIn(">AKTUELL PLAN<", rendered)
        self.assertIn(">KAN ÄNDRAS<", rendered)
        self.assertIn(">INTE BESTÄMT<", rendered)
        self.assertIn("Aktuell plan = passet du utgår från", rendered)
        self.assertIn("Plan före passet", rendered)
        self.assertIn("Genomfört", rendered)
        self.assertIn("3 × 6 backintervaller (18 totalt)", rendered)
        self.assertIn("intervallerna", rendered)
        self.assertNotIn("lapparna", rendered.lower())
        self.assertNotIn(">VILLKORAT<", rendered)


if __name__ == "__main__":
    unittest.main()
