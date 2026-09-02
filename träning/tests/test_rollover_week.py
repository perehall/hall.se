#!/usr/bin/env python3
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
STRATEGY = json.loads((ROOT / "data" / "training_strategy.json").read_text(encoding="utf-8"))

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
        result = rollover_documents(plan_w34(), upcoming_w35(), date(2026, 8, 24), STRATEGY)
        self.assertIsNotNone(result)
        promoted, future = result
        self.assertEqual(promoted["meta"]["week"], 35)
        self.assertNotIn("state", promoted)
        self.assertNotIn("week_key", promoted)
        self.assertEqual(promoted["days"][0]["planning_status"], "fixed")
        self.assertEqual(promoted["days"][0]["sport"], "enduro")
        self.assertEqual(promoted["days"][0]["classification"], "training")
        self.assertNotIn("dose_open", promoted["days"][0])
        self.assertEqual(future["week_key"], "2026-W36")
        self.assertEqual(future["meta"]["week_start"], "2026-08-31")
        self.assertEqual(future["meta"]["week_end"], "2026-09-06")
        self.assertEqual(future["days"][0]["sport"], "enduro")
        self.assertEqual(future["days"][0]["planning_status"], "fixed")
        self.assertEqual(future["days"][0]["microcycle_id"], "run-threshold-hill-4w:mc2")
        self.assertEqual(future["days"][0]["microcycle_day"], 1)
        self.assertEqual(future["days"][0]["classification"], "training")
        self.assertNotIn("dose_open", future["days"][0])
        self.assertEqual(future["meta"]["mesocycle_id"], "run-threshold-hill-4w")
        self.assertEqual(future["meta"]["microcycle_index"], 2)
        self.assertFalse(future["meta"]["requires_mesocycle_review"])
        self.assertTrue(future["meta"]["calendar_week_is_presentation"])
        self.assertEqual(future["meta"]["microcycle_length_days"], 7)
        self.assertEqual(future["days"][1]["stimuli"], ["run_threshold"])
        self.assertEqual(future["days"][1]["microcycle_day"], 2)
        self.assertEqual(future["days"][2]["sport"], "swim")
        self.assertEqual(future["days"][2]["swim_equipment"]["planned"], "tbd")
        self.assertEqual(future["days"][3]["sport"], "bike")
        self.assertEqual([item["value"] for item in future["days"][3]["dose_options"]], [45, 60])
        self.assertEqual(future["days"][4]["stimuli"], ["run_hill_quality"])
        self.assertEqual(future["days"][1]["performance_marker_id"], "run-threshold-control")
        self.assertIn("mechanical", future["days"][4]["load_dimensions"])
        self.assertEqual(future["meta"]["mesocycle_contract"]["primary"], ["run_threshold", "run_hill_quality", "run_easy_distance"])
        self.assertEqual(future["days"][5]["sport"], "strength")
        self.assertEqual(future["days"][5]["priority_role"], "protected_support")
        self.assertEqual(
            future["days"][5]["stimuli"],
            ["strength_unilateral", "strength_core", "swim_aerobic", "swim_technique"],
        )
        self.assertIn("3 200 m", future["days"][5]["session"])
        self.assertEqual(future["days"][6]["stimuli"], ["run_easy_distance"])

    def test_enduro_school_has_exactly_eight_mondays(self):
        self.assertTrue(is_enduro_school_date("2026-08-24"))
        self.assertTrue(is_enduro_school_date("2026-08-31"))
        self.assertTrue(is_enduro_school_date("2026-10-12"))
        self.assertFalse(is_enduro_school_date("2026-10-19"))
        self.assertFalse(is_enduro_school_date("2026-08-25"))

    def test_sunday_does_not_roll_early(self):
        self.assertIsNone(rollover_documents(plan_w34(), upcoming_w35(), date(2026, 8, 23), STRATEGY))

    def test_noncontiguous_upcoming_fails_closed(self):
        upcoming = upcoming_w35()
        upcoming["meta"]["week_start"] = "2026-08-25"
        upcoming["meta"]["week_end"] = "2026-08-31"
        with self.assertRaises(RuntimeError):
            rollover_documents(plan_w34(), upcoming, date(2026, 8, 24), STRATEGY)

    def test_future_week_has_concrete_baselines_without_automatic_progression(self):
        promoted, _ = rollover_documents(plan_w34(), upcoming_w35(), date(2026, 8, 24), STRATEGY)
        future = build_open_next_week(promoted, STRATEGY)
        enduro = future["days"][0]
        self.assertEqual(enduro["sport"], "enduro")
        self.assertNotIn("dose_open", enduro)

        expected = {
            1: ("run-threshold-3x8", "3 × 8 min"),
            2: ("swim-support-3200", "3 200 m"),
            3: ("mtb-support-60", "60 min"),
            4: ("run-hill-6x150", "6 × 150 m"),
            5: ("strength-support-35", "35 min"),
            6: ("run-easy-75", "75 min"),
        }
        for index, (option_id, marker) in expected.items():
            day = future["days"][index]
            self.assertEqual(day["planning_status"], "preliminary")
            self.assertEqual(day["baseline_option_id"], option_id)
            self.assertEqual(day["dose_resolution"]["state"], "baseline")
            self.assertIn(marker, day["session"])
            self.assertNotIn("dos öppen", day["session"].lower())

        strength_day = future["days"][5]
        self.assertEqual(strength_day["planning_status"], "preliminary")
        self.assertEqual(strength_day["priority_role"], "protected_support")
        self.assertIn("strength_unilateral", strength_day["stimuli"])
        self.assertIn("strength_core", strength_day["stimuli"])
        self.assertEqual(strength_day["performance_marker_id"], "strength-repeatability")
        self.assertEqual(future["meta"]["missing_protected_capabilities"], [])
        self.assertFalse(future["meta"]["requires_mesocycle_review"])

    def test_structured_swim_is_carried_forward_without_volume_increase(self):
        upcoming = add_structured_swim(upcoming_w35())
        promoted, future = rollover_documents(plan_w34(), upcoming, date(2026, 8, 24), STRATEGY)
        source = promoted["days"][1]
        target = future["days"][2]
        self.assertEqual(future["days"][1]["stimuli"], ["run_threshold"])

        self.assertEqual(source["sport"], "swim")
        self.assertEqual(target["sport"], "swim")
        self.assertEqual(target["status"], "preliminary")
        self.assertEqual(target["planning_status"], "preliminary")
        self.assertEqual(target["date"], "2026-09-02")
        self.assertEqual(target["watch_workout"]["planned_distance_m"], 3200)
        self.assertEqual(target["watch_workout"]["blocks"], source["watch_workout"]["blocks"])
        self.assertFalse(target["watch_workout"]["sync_enabled"])
        self.assertNotEqual(target["watch_workout"]["id"], source["watch_workout"]["id"])
        self.assertNotIn("external_id", target["watch_workout"])
        self.assertTrue(target["development_focus"])
        self.assertIn("ökas inte automatiskt", target["reason"])


    def test_mesocycle_end_requires_review_instead_of_inventing_next_direction(self):
        promoted = {
            "schema_version": 3,
            "meta": {
                "timezone": "Europe/Stockholm",
                "week": 38,
                "week_start": "2026-09-14",
                "week_end": "2026-09-20",
                "title": "Mesocykel vecka 4",
                "principle": "P",
            },
            "days": [
                {
                    "date": (date(2026, 9, 14) + timedelta(days=i)).isoformat(),
                    "label": "Dag",
                    "status": "open",
                    "sport": "open",
                    "session": "Öppet",
                    "reason": "R",
                }
                for i in range(7)
            ],
            "strength_template": ["Styrka"],
        }
        future = build_open_next_week(promoted, STRATEGY)
        self.assertTrue(future["meta"]["requires_mesocycle_review"])
        self.assertEqual(future["meta"]["mesocycle_id"], "")
        self.assertIn("utvärdering krävs", future["meta"]["title"])
        self.assertEqual(future["meta"]["microcycle_id"], "")
        self.assertEqual(future["days"][0]["sport"], "enduro")
        self.assertTrue(all(day["sport"] == "open" for day in future["days"][1:]))

if __name__ == "__main__":
    unittest.main()
