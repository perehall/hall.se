#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from rollover_week import build_open_next_week, rollover_documents  # noqa: E402


def plan_w34():
    return {
        "schema_version": 3,
        "meta": {
            "timezone": "Europe/Stockholm",
            "week": 34,
            "week_start": "2026-08-17",
            "week_end": "2026-08-23",
            "title": "W34",
            "principle": "P",
        },
        "days": [
            {
                "date": f"2026-08-{17 + i:02d}",
                "label": "Dag",
                "status": "completed",
                "sport": "run",
                "session": "Pass",
                "reason": "R",
            }
            for i in range(7)
        ],
        "strength_template": ["Styrka"],
    }


def upcoming_w35():
    days = []
    for i in range(7):
        days.append(
            {
                "date": f"2026-08-{24 + i:02d}",
                "label": "Dag",
                "status": "planned" if i == 0 else "open",
                "planning_status": "fixed" if i == 0 else "open",
                "sport": "enduro" if i == 0 else "open",
                "session": "Enduroskola" if i == 0 else "Öppet",
                "reason": "R",
            }
        )
    return {
        "schema_version": 3,
        "state": "preliminary",
        "week_key": "2026-W35",
        "meta": {
            "timezone": "Europe/Stockholm",
            "week": 35,
            "week_start": "2026-08-24",
            "week_end": "2026-08-30",
            "title": "W35",
            "principle": "P",
            "preview_summary": "Preview",
        },
        "days": days,
        "strength_template": ["Styrka"],
    }


class WeeklyRolloverTests(unittest.TestCase):
    def test_monday_promotes_upcoming_and_builds_next_week(self):
        result = rollover_documents(plan_w34(), upcoming_w35(), date(2026, 8, 24))
        self.assertIsNotNone(result)
        promoted, future = result
        self.assertEqual(promoted["meta"]["week"], 35)
        self.assertNotIn("state", promoted)
        self.assertNotIn("week_key", promoted)
        self.assertNotIn("planning_status", promoted["days"][0])
        self.assertEqual(future["week_key"], "2026-W36")
        self.assertEqual(future["meta"]["week_start"], "2026-08-31")
        self.assertEqual(future["meta"]["week_end"], "2026-09-06")
        self.assertTrue(all(day["status"] == "open" for day in future["days"]))
        self.assertTrue(all(day["sport"] == "open" for day in future["days"]))

    def test_sunday_does_not_roll_early(self):
        self.assertIsNone(rollover_documents(plan_w34(), upcoming_w35(), date(2026, 8, 23)))

    def test_noncontiguous_upcoming_fails_closed(self):
        upcoming = upcoming_w35()
        upcoming["meta"]["week_start"] = "2026-08-25"
        upcoming["meta"]["week_end"] = "2026-08-31"
        with self.assertRaises(RuntimeError):
            rollover_documents(plan_w34(), upcoming, date(2026, 8, 24))

    def test_future_week_contains_no_invented_training_dose(self):
        promoted, _ = rollover_documents(plan_w34(), upcoming_w35(), date(2026, 8, 24))
        future = build_open_next_week(promoted)
        for day in future["days"]:
            self.assertEqual(day["planning_status"], "open")
            self.assertNotIn("duration", day)
            self.assertNotIn("distance", day)
            self.assertIn("Ingen träningsdos", day["reason"])


if __name__ == "__main__":
    unittest.main()
