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

    def test_legacy_mtb_label_expansion_is_repaired_recursively_and_idempotently(self):
        snapshot = {
            "plan": {"days": [{"session": "MTB/XC · 60 min"}]},
            "coach_analyses": [
                {
                    "assessment": {
                        "summary": "71,8 min MTB/XC/XC/XC visade längre varaktighet."
                    },
                    "plan_action": {
                        "recommendation": "Behåll planerad MTB/XC/XC/XC/XC 60 min."
                    },
                }
            ],
        }

        self.assertTrue(archive_weeks.repair_legacy_snapshot_copy(snapshot))
        self.assertEqual(
            snapshot["coach_analyses"][0]["assessment"]["summary"],
            "71,8 min MTB/XC visade längre varaktighet.",
        )
        self.assertEqual(
            snapshot["coach_analyses"][0]["plan_action"]["recommendation"],
            "Behåll planerad MTB/XC 60 min.",
        )
        self.assertFalse(archive_weeks.repair_legacy_snapshot_copy(snapshot))


if __name__ == "__main__":
    unittest.main()
