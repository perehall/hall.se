#!/usr/bin/env python3
import json
import sys
import unittest
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
STRATEGY = json.loads((ROOT / "data" / "training_strategy.json").read_text(encoding="utf-8"))

from rollover_week import (  # noqa: E402
    apply_swim_option_structure,
    build_open_next_week,
    is_enduro_school_date,
    repair_transition_week_from_previous,
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
        result = rollover_documents(
            plan_w34(), upcoming_w35(), date(2026, 8, 24), STRATEGY
        )
        self.assertIsNotNone(result)
        promoted, future = result

        self.assertEqual(promoted["meta"]["week"], 35)
        self.assertEqual(future["week_key"], "2026-W36")
        self.assertEqual(future["meta"]["week_start"], "2026-08-31")
        self.assertEqual(future["meta"]["week_end"], "2026-09-06")

        workouts = future["planned_workouts"]
        self.assertTrue(workouts)
        self.assertEqual(
            len({workout["microcycle_slot"] for workout in workouts}),
            len(workouts),
        )

        strategy_slots = STRATEGY["current_mesocycle"]["microcycle_template"]
        for slot in strategy_slots:
            workout = next(
                item for item in workouts if item["microcycle_slot"] == slot["slot"]
            )
            self.assertEqual(workout["sport"], slot["sport"])
            self.assertEqual(workout["stimuli"], slot["stimuli"])
            self.assertEqual(workout["planning_status"], "preliminary")

        same_day_groups = {}
        for workout in workouts:
            same_day_groups.setdefault(workout["date"], []).append(workout)
        for date_value, group in same_day_groups.items():
            day = next(item for item in future["days"] if item["date"] == date_value)
            if len(group) > 1:
                self.assertEqual(day["additional_planned_workouts"], len(group) - 1)
            self.assertEqual(day["session"], group[0]["session"])

        for workout in workouts:
            if workout["sport"] == "swim":
                self.assertTrue((workout.get("watch_workout") or {}).get("blocks"))
            else:
                self.assertNotIn("watch_workout", workout)

    def test_multiple_strategy_slots_on_same_day_materialize_as_distinct_workouts(self):
        strategy = deepcopy(STRATEGY)
        slots = strategy["current_mesocycle"]["microcycle_template"]
        slots[0]["day_index"] = 3
        slots[1]["day_index"] = 3

        promoted, _ = rollover_documents(
            plan_w34(), upcoming_w35(), date(2026, 8, 24), strategy
        )
        future = build_open_next_week(promoted, strategy)
        same_day = [
            workout
            for workout in future["planned_workouts"]
            if workout["date"] == "2026-09-02"
        ]
        self.assertGreaterEqual(len(same_day), 2)
        self.assertEqual(
            len({workout["microcycle_slot"] for workout in same_day}),
            len(same_day),
        )

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

    def test_future_week_has_concrete_baselines_with_mesocycle_progression(self):
        promoted, _ = rollover_documents(
            plan_w34(), upcoming_w35(), date(2026, 8, 24), STRATEGY
        )
        future = build_open_next_week(promoted, STRATEGY)

        workouts = future["planned_workouts"]
        self.assertTrue(workouts)
        for workout in workouts:
            self.assertEqual(workout["planning_status"], "preliminary")
            if workout.get("dose_options"):
                self.assertIn(
                    workout["baseline_option_id"],
                    {option["id"] for option in workout["dose_options"]},
                )
                self.assertEqual(workout["dose_resolution"]["state"], "baseline")
                self.assertNotIn("dos öppen", workout["session"].lower())

        strength = next(
            workout for workout in workouts if workout["sport"] == "strength"
        )
        self.assertEqual(strength["priority_role"], "protected_support")
        self.assertIn("strength_unilateral", strength["stimuli"])
        self.assertIn("strength_core", strength["stimuli"])
        self.assertNotIn("swim_aerobic", strength["stimuli"])
        self.assertNotIn("swim_technique", strength["stimuli"])

        swims = [workout for workout in workouts if workout["sport"] == "swim"]
        self.assertTrue(swims)
        self.assertTrue(
            all((workout.get("watch_workout") or {}).get("blocks") for workout in swims)
        )

    def test_catalog_swim_option_materializes_exact_watch_structure(self):
        day = {
            "sport": "swim",
            "baseline_option_id": "swim-4000",
            "dose_options": [
                {
                    "id": "swim-4000",
                    "kind": "structured",
                    "value": 4000,
                    "session": "Simning · 4 000 m",
                    "intent": "test",
                    "watch_workout": {
                        "type": "Swim",
                        "equipment": ["paddles", "pull_buoy"],
                        "name": "4K",
                        "planned_distance_m": 4000,
                        "blocks": [
                            {
                                "name": "Main",
                                "repeat": 20,
                                "steps": [
                                    {
                                        "kind": "swim",
                                        "text": "200",
                                        "distance_m": 200,
                                        "intensity": "active",
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
        }
        applied = apply_swim_option_structure(
            day, date(2026, 9, 23), "2026-W39"
        )
        self.assertTrue(applied)
        self.assertEqual(day["watch_workout"]["planned_distance_m"], 4000)
        self.assertEqual(
            day["swim_equipment"]["planned"], ["paddles", "pull_buoy"]
        )
        self.assertFalse(day["watch_workout"]["sync_enabled"])
        self.assertIn("swim-4000", day["watch_workout"]["id"])

    def test_swim_structure_is_owned_by_the_planned_swim_not_previous_calendar_day(self):
        upcoming = add_structured_swim(upcoming_w35())
        promoted, future = rollover_documents(
            plan_w34(), upcoming, date(2026, 8, 24), STRATEGY
        )
        source = promoted["days"][1]
        swim_workouts = [
            workout
            for workout in future["planned_workouts"]
            if workout["sport"] == "swim"
        ]
        self.assertTrue(swim_workouts)

        for workout in swim_workouts:
            self.assertTrue((workout.get("watch_workout") or {}).get("blocks"))
            selected = next(
                option
                for option in workout["dose_options"]
                if option["id"] == workout["baseline_option_id"]
            )
            self.assertEqual(
                workout["watch_workout"]["blocks"],
                selected["watch_workout"]["blocks"],
            )
            self.assertNotEqual(
                workout["watch_workout"]["blocks"],
                source["watch_workout"]["blocks"],
            )

    def test_mesocycle_end_builds_concrete_nonprogressive_bridge_week(self):
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
        self.assertIn("mesocykelutvärdering", future["meta"]["title"])
        self.assertEqual(future["meta"]["microcycle_id"], "")
        self.assertEqual(future["days"][0]["sport"], "enduro")
        self.assertEqual(
            [day["sport"] for day in future["days"][1:]],
            ["run", "swim", "bike", "run", "strength", "run"],
        )
        self.assertEqual(future["days"][1]["baseline_option_id"], "run-threshold-3x8")
        hill_slot = next(
            slot
            for slot in STRATEGY["current_mesocycle"]["microcycle_template"]
            if slot["slot"] == "run_hill_quality"
        )
        self.assertEqual(
            future["days"][4]["baseline_option_id"],
            hill_slot["development_progression"]["demonstrated_floor_option_id"],
        )
        self.assertTrue(all(day.get("transition_review") is True for day in future["days"][1:]))
        self.assertTrue(all(day.get("planning_status") == "preliminary" for day in future["days"][1:]))
        self.assertIn("utan automatisk belastningsökning", future["meta"]["principle"])

    def test_empty_promoted_review_week_is_repaired_from_previous_plan_on_monday(self):
        previous = {
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
        current_preview = build_open_next_week(previous, STRATEGY)
        current = {**current_preview}
        current.pop("state", None)
        current.pop("week_key", None)
        current["days"] = [dict(day) for day in current_preview["days"]]
        for day in current["days"]:
            day.pop("planning_status", None)
        # Simulera den gamla felaktiga produktionen: bara fast Enduro, resten öppet.
        for index in range(1, 7):
            current["days"][index] = {
                "date": (date(2026, 9, 21) + timedelta(days=index)).isoformat(),
                "label": "Dag",
                "status": "open",
                "sport": "open",
                "session": "Ingen planerad träning",
                "reason": "R",
            }
        repaired = repair_transition_week_from_previous(
            current, previous, STRATEGY, date(2026, 9, 21)
        )
        self.assertIsNotNone(repaired)
        self.assertEqual(repaired["meta"]["week_start"], "2026-09-21")
        self.assertEqual(repaired["days"][1]["sport"], "run")
        self.assertEqual(repaired["days"][1]["baseline_option_id"], "run-threshold-3x8")
        hill_slot = next(
            slot
            for slot in STRATEGY["current_mesocycle"]["microcycle_template"]
            if slot["slot"] == "run_hill_quality"
        )
        self.assertEqual(
            repaired["days"][4]["baseline_option_id"],
            hill_slot["development_progression"]["demonstrated_floor_option_id"],
        )

if __name__ == "__main__":
    unittest.main()
