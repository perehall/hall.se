#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_quiet_performance_v2_ui import (  # noqa: E402
    CSS_END,
    CSS_START,
    TRAINING_START,
    UPCOMING_TITLE,
    apply_v2,
    validate_page,
)


class QuietPerformanceV2Tests(unittest.TestCase):
    def sample_page(self):
        return '''<!doctype html><html><head><meta name="theme-color" content="#F6F7F5"><style>/* quiet-performance-v1:start */
:root{--qp-accent:#5964E8;--qp-line:#E4E7E3;--qp-line-soft:#ECEEEB;--qp-text:#171918;--qp-secondary:#6C716D;--qp-tertiary:#979C98;--qp-canvas:#F6F7F5;--qp-green-soft:#EDF7F1;--qp-green:#287A54;--qp-amber-soft:#FFF6DD;--qp-amber:#946200}
/* quiet-performance-v1:end */</style></head><body class="quiet-performance"><div class="wrap">
<div class="hero week-focus-card"><h2 class="week-focus-title">Veckofokus</h2></div>
<!-- training-brain-v1:start -->
<section class="training-brain"><div class="brain-today"><div class="brain-headline">Dagens pass</div><div class="brain-next"><div class="brain-next-label">Nästa</div><strong>Fredag</strong></div></div></section>
<!-- training-brain-v1:end -->
<section class="dashboard">
<div class="metrics"><div class="metric"><strong>4</strong><span>pass</span></div></div>
<div class="dashboard-grid"><div class="dashboard-card"><div class="dashboard-title">Grenfördelning</div></div><div class="dashboard-card"><div class="dashboard-title">Plan → utfall</div></div></div>
<div class="dashboard-card"><div class="dashboard-title">Kommande dagar</div><div class="next-item"><div>Fredag</div></div></div>
</section>
<h2 class="section">Aktuell vecka</h2>
<div class="day workout-card-v2 past-completed" id="dag-2026-09-08"><div class="session">Löpning</div></div>
</div></body></html>'''

    def test_current_page_moves_today_first_and_removes_duplicate_upcoming(self):
        rendered = apply_v2(self.sample_page(), current=True)
        validate_page(rendered, current=True, label="current")
        self.assertIn('class="quiet-performance qp-current"', rendered)
        self.assertLess(rendered.index(TRAINING_START), rendered.index('class="hero week-focus-card"'))
        self.assertNotIn(UPCOMING_TITLE, rendered)
        self.assertIn('class="dashboard-grid"', rendered)
        self.assertIn('class="day workout-card-v2 past-completed"', rendered)

    def test_history_keeps_structure_but_gets_history_class(self):
        rendered = apply_v2(self.sample_page(), current=False)
        validate_page(rendered, current=False, label="history")
        self.assertIn('class="quiet-performance qp-history"', rendered)
        self.assertIn(UPCOMING_TITLE, rendered)
        self.assertGreater(rendered.index(TRAINING_START), rendered.index('class="hero week-focus-card"'))

    def test_transform_is_idempotent(self):
        once = apply_v2(self.sample_page(), current=True)
        twice = apply_v2(once, current=True)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count(CSS_START), 1)
        self.assertEqual(twice.count(CSS_END), 1)

    def test_v1_is_required(self):
        raw = self.sample_page().replace('quiet-performance', 'legacy', 1)
        with self.assertRaises(RuntimeError):
            apply_v2(raw, current=True)


if __name__ == "__main__":
    unittest.main()
