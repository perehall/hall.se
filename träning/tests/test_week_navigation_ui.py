#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_week_navigation_ui import nav_html, shift_week  # noqa: E402


class UnifiedWeekNavigationTests(unittest.TestCase):
    def setUp(self):
        self.current = "2026-W39"
        self.available = {
            "2026-W37",
            "2026-W38",
            "2026-W39",
            "2026-W40",
        }

    def test_current_week_has_history_left_and_future_right(self):
        rendered = nav_html("2026-W39", self.current, self.available)
        self.assertIn('href="/träning/vecka/2026-W38/">‹ Vecka 38</a>', rendered)
        self.assertIn('<strong>Vecka 39</strong><span>21–27 sep</span>', rendered)
        self.assertIn('href="/träning/vecka/2026-W40/">Vecka 40 ›</a>', rendered)

    def test_history_uses_same_previous_current_next_semantics(self):
        rendered = nav_html("2026-W38", self.current, self.available)
        self.assertIn('href="/träning/vecka/2026-W37/">‹ Vecka 37</a>', rendered)
        self.assertIn('<strong>Vecka 38</strong><span>14–20 sep · historik</span>', rendered)
        self.assertIn('href="/träning/">Vecka 39 ›</a>', rendered)

    def test_upcoming_week_uses_same_semantics_and_shows_unavailable_next_disabled(self):
        rendered = nav_html("2026-W40", self.current, self.available)
        self.assertIn('href="/träning/">‹ Vecka 39</a>', rendered)
        self.assertIn('<strong>Vecka 40</strong><span>28 sep–4 okt · preliminär</span>', rendered)
        self.assertIn('<span class="top-week-link next disabled">Vecka 41 ›</span>', rendered)

    def test_iso_week_shift_crosses_year_boundary(self):
        self.assertEqual(shift_week("2026-W53", 1), "2027-W01")


if __name__ == "__main__":
    unittest.main()
