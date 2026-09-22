#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_rest_day_language import humanize_rest_day_language  # noqa: E402


class RestDayLanguageTests(unittest.TestCase):
    def test_no_training_baseline_is_presented_as_vilodag(self):
        page = """
<div class="session">Ingen planerad träning</div>
<div class="brain-next"><strong>Onsdag · Ingen planerad träning</strong></div>
"""
        rendered = humanize_rest_day_language(page)
        self.assertIn('<div class="session">Vilodag</div>', rendered)
        self.assertIn("<strong>Onsdag · Vilodag</strong>", rendered)
        self.assertNotIn("Ingen planerad träning", rendered)

    def test_unrelated_open_copy_is_not_rewritten(self):
        page = '<div class="badge open">Inte bestämt</div><p>Öppen dag för beslut.</p>'
        self.assertEqual(humanize_rest_day_language(page), page)


if __name__ == "__main__":
    unittest.main()
