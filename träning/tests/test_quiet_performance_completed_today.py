#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_quiet_performance_v2_ui import apply_v2, validate_page  # noqa: E402


class QuietPerformanceCompletedTodayTests(unittest.TestCase):
    def test_completed_post_workout_state_gets_today_date_and_validates(self):
        page = '''<!doctype html><html><head><style>/* quiet-performance-v1:start */
:root{--qp-line:#ddd;--qp-line-soft:#eee;--qp-text:#111;--qp-secondary:#666;--qp-tertiary:#999;--qp-green-soft:#efe;--qp-green:#282;--qp-amber-soft:#ffe;--qp-amber:#963}
/* quiet-performance-v1:end */</style></head><body class="quiet-performance"><div class="wrap">
<div class="hero week-focus-card"><h2 class="week-focus-title">Veckofokus</h2></div>
<!-- training-brain-v1:start -->
<section class="today-outcome" data-post-workout-state="completed"><div class="today-outcome-head"><div class="today-outcome-kicker">Dagens pass · genomfört</div></div><h2>MTB/XC</h2></section>
<!-- training-brain-v1:end -->
<section class="dashboard"><div class="dashboard-grid"><div class="dashboard-card"><div class="dashboard-title">Plan → utfall</div></div></div><div class="dashboard-card"><div class="dashboard-title">Kommande dagar</div></div></section>
</div></body></html>'''

        rendered = apply_v2(page, current=True, today=date(2026, 9, 10))
        validate_page(rendered, current=True, label="current-completed")

        self.assertIn(
            '<div class="today-outcome-kicker">Idag · torsdag 10 sep · genomfört</div>',
            rendered,
        )
        self.assertLess(
            rendered.index('<!-- training-brain-v1:start -->'),
            rendered.index('class="hero week-focus-card"'),
        )


if __name__ == "__main__":
    unittest.main()
