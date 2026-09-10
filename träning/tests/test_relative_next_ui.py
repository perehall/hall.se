#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_relative_next_ui import patch_page, relative_next_label  # noqa: E402


class RelativeNextUiTests(unittest.TestCase):
    def test_tomorrow_is_explicit(self):
        self.assertEqual(
            relative_next_label(date(2026, 9, 10), {"date": "2026-09-11"}),
            "Nästa · imorgon",
        )

    def test_later_date_keeps_normal_label(self):
        self.assertEqual(
            relative_next_label(date(2026, 9, 10), {"date": "2026-09-12"}),
            "Nästa",
        )

    def test_patch_is_scoped_to_training_brain(self):
        page = '''<div class="brain-next-label">Nästa</div>
<!-- training-brain-v1:start -->
<div class="brain-next-label">Nästa</div>
<!-- training-brain-v1:end -->'''
        patched = patch_page(page, "Nästa · imorgon")
        self.assertEqual(patched.count('<div class="brain-next-label">Nästa · imorgon</div>'), 1)
        self.assertTrue(patched.startswith('<div class="brain-next-label">Nästa</div>'))


if __name__ == "__main__":
    unittest.main()
