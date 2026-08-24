#!/usr/bin/env python3
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
MODULE_PATH = SCRIPTS / "archive_weeks.py"
SPEC = importlib.util.spec_from_file_location("archive_weeks", MODULE_PATH)
archive_weeks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = archive_weeks
SPEC.loader.exec_module(archive_weeks)


class ArchiveWeekUrlTests(unittest.TestCase):
    def test_current_week_uses_training_root(self):
        self.assertEqual(
            archive_weeks.public_week_url("2026-W35", "2026-W35"),
            "/träning/",
        )

    def test_historical_week_keeps_archive_url(self):
        self.assertEqual(
            archive_weeks.public_week_url("2026-W34", "2026-W35"),
            "/träning/vecka/2026-W34/",
        )

    def test_history_next_link_targets_training_root_for_current_week(self):
        html = archive_weeks.nav_html(
            "2026-W34",
            ["2026-W34", "2026-W35"],
            "2026-W35",
            is_current=False,
        )
        self.assertIn('href="/träning/">Vecka 35 →</a>', html)
        self.assertNotIn('/träning/vecka/2026-W35/', html)


if __name__ == "__main__":
    unittest.main()
