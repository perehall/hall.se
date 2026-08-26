#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from rollover_week import (  # noqa: E402
    build_open_next_week,
    is_enduro_school_date,
    rollover_documents,
)


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
                **(
                    {"classification": "training", "dose_open": True}
                    if i == 0
                    else {}
                ),
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


def add_structured_swim(upcoming):
    upcoming = {**upcoming, "days": [dict(day) for day in upcoming["days"]]}
    upcoming["days"][1] = {
        "date": "2026-08-25",
        "label": "Tisdag",
        "status": "preliminary",
        "planning_status": "preliminary",
        "sport": "swim",
        "session": "Simning · aerob/teknik · 3 200 m",
        "reason": "Preliminärt simpass.",
        "development_focus": "Tidigt grepp.",
        "swim_equipment": {"planned": "none"},
        "watch_workout": {
            "sync_enabled": False,
            "id": "swim-w35-test",
            "type": "Swim",
            "equipment": [],
            "name": "Aerob 3200",
            "planned_distance_m": 3200,
            "blocks": [
                {
                    "name": "Aerob",
                    "repeat": 8,
                    "steps": [
                        {
                            "kind": "swim",
                            "text": "Jämnt",
                            "distance_m": 400,
                            "intensity": "active",
                        }
                    ],
                }
            ],
        },
    }
    return upcoming


class WeeklyRolloverTests(unittest.TestCase):
    def test_monday_promotes_upcoming_and_builds_next_week(self):
        result = rollover_documents(plan_w34(), upcoming_w35(), date(2026, 8, 24))
        self.assertIsNotNone(result)
        promoted, future = result
        self.assertEqual(promoted["meta"]["week"], 35)
        self.assertNotIn("state", promoted)
        self.assertNotIn("week_key", promoted)
        self.assertEqual(promoted["days"][0]["planning_status"], "fixed")
        self.assertEqual(promoted["days"][0]["sport"], "enduro")
        self.assertEqual(promoted["days"][0]["classification"], "training")
        self.assertTrue(promoted["days"][0]["dose_open"])
        self.assertEqual(future["week_key"], "2026-W36")
        self.assertEqual(future["meta"]["week_start"], "2026-08-31")
        self.assertEqual(future["meta"]["week_end"], "2026-09-06")
        self.assertEqual(future["days"][0]["sport"], "enduro")
        self.assertEqual(future["days"][0]["planning_status"], "fixed")
        self.assertEqual(future["days"][0]["classification"], "training")
        self.assertTrue(future["days"][0]["dose_open"])
        self.assertTrue(all(day["status"] == "open" for day in future["days"][1:]))
        self.assertTrue(all(day["sport"] == "open" for day in future["days"][1:]))

    def test_enduro_school_has_exactly_eight_mondays(self):
        self.assertTrue(is_enduro_school_date("2026-08-24"))
        self.assertTrue(is_enduro_school_date("2026-08-31"))
        self.assertTrue(is_enduro_school_date("2026-10-12"))
        self.assertFalse(is_enduro_school_date("2026-10-19"))
        self.assertFalse(is_enduro_school_date("2026-08-25"))

    def test_sunday_does_not_roll_early(self):
        self.assertIsNone(rollover_documents(plan_w34(), upcoming_w35(), date(2026, 8, 23)))

    def test_noncontiguous_upcoming_fails_closed(self):
        upcoming = upcoming_w35()
        upcoming["meta"]["week_start"] = "2026-08-25"
        upcoming["meta"]["week_end"] = "2026-08-31"
        with self.assertRaises(RuntimeError):
            rollover_documents(plan_w34(), upcoming, date(2026, 8, 24))

    def test_future_week_contains_no_invented_training_dose_without_established_session(self):
        promoted, _ = rollover_documents(plan_w34(), upcoming_w35(), date(2026, 8, 24))
        future = build_open_next_week(promoted)
        enduro = future["days"][0]
        self.assertEqual(enduro["sport"], "enduro")
        self.assertTrue(enduro["dose_open"])
        for day in future["days"][1:]:
            self.assertEqual(day["planning_status"], "open")
            self.assertNotIn("duration", day)
            self.assertNotIn("distance", day)
            self.assertIn("Ingen träningsdos", day["reason"])

    def test_structured_swim_is_carried_forward_without_volume_increase(self):
        upcoming = add_structured_swim(upcoming_w35())
        promoted, future = rollover_documents(plan_w34(), upcoming, date(2026, 8, 24))
        source = promoted["days"][1]
        target = future["days"][1]

        self.assertEqual(source["sport"], "swim")
        self.assertEqual(target["sport"], "swim")
        self.assertEqual(target["status"], "preliminary")
        self.assertEqual(target["planning_status"], "preliminary")
        self.assertEqual(target["date"], "2026-09-01")
        self.assertEqual(target["watch_workout"]["planned_distance_m"], 3200)
        self.assertEqual(target["watch_workout"]["blocks"], source["watch_workout"]["blocks"])
        self.assertFalse(target["watch_workout"]["sync_enabled"])
        self.assertNotEqual(target["watch_workout"]["id"], source["watch_workout"]["id"])
        self.assertNotIn("external_id", target["watch_workout"])
        self.assertTrue(target["development_focus"])
        self.assertIn("ökas inte automatiskt", target["reason"])


if __name__ == "__main__":
    unittest.main()
