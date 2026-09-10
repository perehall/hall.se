#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_quiet_performance_ui import (  # noqa: E402
    CSS_END,
    CSS_START,
    THEME_COLOR,
    apply_quiet_performance,
    validate_page,
)


class QuietPerformanceUiTests(unittest.TestCase):
    def sample_page(self, body='<body>'):
        return (
            '<!doctype html><html><head>'
            '<meta name="theme-color" content="#0f172a">'
            '<style>.legacy{color:#2563eb}</style></head>'
            f'{body}<div class="day workout-card-v2 card-v2-today">Pass</div></body></html>'
        )

    def test_applies_canonical_palette_and_preserves_body_classes(self):
        rendered = apply_quiet_performance(self.sample_page('<body class="goal-page">'))
        validate_page(rendered, "test")
        self.assertIn('<meta name="theme-color" content="#F6F7F5">', rendered)
        self.assertIn('class="goal-page quiet-performance"', rendered)
        self.assertIn('--qp-surface:#FCFCFB', rendered)
        self.assertIn('--qp-text:#171918', rendered)
        self.assertIn('--qp-secondary:#6C716D', rendered)
        self.assertIn('--qp-tertiary:#979C98', rendered)
        self.assertIn('--qp-line:#E4E7E3', rendered)
        self.assertIn('--qp-accent:#5964E8', rendered)

    def test_visual_contract_keeps_cards_flat_and_today_subtle(self):
        rendered = apply_quiet_performance(self.sample_page())
        self.assertIn('box-shadow:inset 2px 0 0 var(--qp-accent)', rendered)
        self.assertIn('body.quiet-performance .day.workout-card-v2.card-v2-today', rendered)
        self.assertIn('body.quiet-performance .day.workout-card-v2.past-completed', rendered)
        self.assertIn('body.quiet-performance .workout-card-v2 .development-focus strong', rendered)
        self.assertIn('background:transparent;', rendered)
        self.assertIn('body.quiet-performance .coach.yoda-v2', rendered)
        self.assertIn('body.quiet-performance .sport-icon', rendered)

    def test_transform_is_idempotent(self):
        once = apply_quiet_performance(self.sample_page())
        twice = apply_quiet_performance(once)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count(CSS_START), 1)
        self.assertEqual(twice.count(CSS_END), 1)
        self.assertEqual(THEME_COLOR, "#F6F7F5")

    def test_incomplete_existing_theme_block_fails_closed(self):
        page = self.sample_page().replace('</style>', CSS_START + '</style>')
        with self.assertRaises(RuntimeError):
            apply_quiet_performance(page)


if __name__ == "__main__":
    unittest.main()
