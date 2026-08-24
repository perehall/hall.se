#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_header_ui import format_meta  # noqa: E402


class HeaderHistoryTests(unittest.TestCase):
    def test_historical_snapshot_meta_is_supported(self):
        css_class, text = format_meta("historik · data sparad 2026-08-24 08:30")
        self.assertEqual(css_class, "header-status")
        self.assertEqual(text, "Historik · data sparad 2026-08-24 08:30")

    def test_unknown_header_meta_still_fails_closed(self):
        with self.assertRaises(RuntimeError):
            format_meta("okänd metadata")


if __name__ == "__main__":
    unittest.main()
