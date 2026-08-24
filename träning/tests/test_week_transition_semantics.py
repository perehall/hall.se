#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach_rules import allowed_target_dates  # noqa: E402
from rollover_week import promote_upcoming  # noqa: E402


class WeekTransitionSemanticsTests(unittest.TestCase):
    def test_undosed_training_becomes_open_but_recreation_stays_planned(self):
        upcoming = {
            "state": "preliminary",
            "week_key": "2026-W35",
            "meta": {
                "timezone": "Europe/Stockholm",
                "week": 35,
                "week_start": "2026-08-24",
                "week_end": "2026-08-30",
                "title": "x",
                "principle": "x",
                "preview_summary": "x",
            },
            "days": [
                {
                    "date": "2026-08-24",
                    "label": "Måndag",
                    "status": "planned",
                    "planning_status": "fixed",
                    "sport": "enduro",
                    "session": "Enduroskola",
                    "reason": "Fast kalenderaktivitet.",
                },
                {
                    "date": "2026-08-25",
                    "label": "Tisdag",
                    "status": "preliminary",
                    "planning_status": "preliminary",
                    "sport": "strength",
                    "session": "Styrka + core",
                    "reason": "Ingen dos ännu.",
                },
            ],
        }
        promoted = promote_upcoming(upcoming)
        self.assertEqual(promoted["days"][0]["status"], "planned")
        self.assertEqual(promoted["days"][0]["classification"], "recreation")
        self.assertEqual(promoted["days"][1]["status"], "open")
        self.assertEqual(promoted["days"][1]["rollover_status_from"], "preliminary")

    def test_coach_cannot_target_open_or_recreation_days(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-24",
                    "status": "planned",
                    "sport": "enduro",
                    "classification": "recreation",
                },
                {
                    "date": "2026-08-25",
                    "status": "open",
                    "sport": "strength",
                },
                {
                    "date": "2026-08-26",
                    "status": "planned",
                    "sport": "run",
                },
            ]
        }
        self.assertEqual(
            allowed_target_dates(plan, [], "2026-08-24"),
            ["2026-08-26"],
        )


if __name__ == "__main__":
    unittest.main()
