#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_training_timeline_ui import (  # noqa: E402
    CSS_END,
    CSS_START,
    JS_END,
    JS_START,
    WRAP_END,
    WRAP_START,
    apply_timeline,
    validate_page,
)


class TrainingTimelineUiTests(unittest.TestCase):
    def sample_page(self):
        return '''<!doctype html><html><head><style>.day{background:white}</style></head>
<body class="quiet-performance qp-current"><div class="wrap">
<h2 class="section">Aktuell vecka</h2>
<details class="week-status-expander"><summary>Veckostatus</summary></details>
<div class="day workout-card-v2 past-completed" id="dag-2026-09-08"><div class="daytop"><div><div class="dow">Tisdag</div><div class="date">2026-09-08</div></div><div class="badge fixed">GENOMFÖRT</div></div><div class="session">Löpning · 4 × 8 min tröskel</div></div>
<div class="day workout-card-v2 card-v2-today" id="dag-2026-09-10"><div class="daytop"><div><div class="dow">Torsdag</div><div class="date">2026-09-10</div></div><div class="badge conditional">KAN ÄNDRAS</div></div><div class="session">MTB/XC · 60 min · teknik</div><div class="coach yoda-v2">Råd</div></div>
<div class="day workout-card-v2 future-compact" id="dag-2026-09-11"><div class="daytop"><div><div class="dow">Fredag</div><div class="date">2026-09-11</div></div><div class="badge planned">AKTUELL PLAN</div></div><div class="session">Löpning · backkvalitet</div></div>
<div class="principles">Efter veckan</div>
</div></body></html>'''

    def test_wraps_only_consecutive_current_week_days(self):
        rendered = apply_timeline(self.sample_page())
        validate_page(rendered)
        self.assertEqual(rendered.count(WRAP_START), 1)
        self.assertEqual(rendered.count(WRAP_END), 1)
        wrapper = rendered[rendered.index(WRAP_START):rendered.index(WRAP_END)]
        self.assertEqual(wrapper.count('id="dag-'), 3)
        self.assertNotIn('class="principles"', wrapper)
        self.assertLess(rendered.index('week-status-expander'), rendered.index(WRAP_START))

    def test_contract_is_flat_and_sticky_not_card_based(self):
        rendered = apply_timeline(self.sample_page())
        self.assertIn('class="timeline-scroll-context"', rendered)
        self.assertIn('position:sticky;', rendered)
        self.assertIn('grid-template-columns:92px minmax(0,1fr)', rendered)
        self.assertIn('background:transparent!important;', rendered)
        self.assertIn('border-radius:0!important;', rendered)
        self.assertIn('box-shadow:none!important;', rendered)
        self.assertIn('.week-timeline>.day>.daytop', rendered)
        self.assertIn('.week-timeline .coach.yoda-v2', rendered)

    def test_scroll_context_updates_day_and_session(self):
        rendered = apply_timeline(self.sample_page())
        self.assertIn(JS_START, rendered)
        self.assertIn(JS_END, rendered)
        self.assertIn("active.querySelector('.dow')", rendered)
        self.assertIn("active.querySelector('.date')", rendered)
        self.assertIn("active.querySelector('.session')", rendered)
        self.assertIn("classList.add('timeline-active')", rendered)
        self.assertIn("addEventListener('scroll',schedule,{passive:true})", rendered)

    def test_transform_is_idempotent(self):
        once = apply_timeline(self.sample_page())
        twice = apply_timeline(once)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count(CSS_START), 1)
        self.assertEqual(twice.count(CSS_END), 1)
        self.assertEqual(twice.count(JS_START), 1)
        self.assertEqual(twice.count(JS_END), 1)

    def test_requires_quiet_performance_current_page(self):
        with self.assertRaises(RuntimeError):
            apply_timeline(self.sample_page().replace('quiet-performance qp-current', 'quiet-performance'))


if __name__ == "__main__":
    unittest.main()
