#!/usr/bin/env python3
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach_rules import allowed_target_dates  # noqa: E402
from rollover_week import promote_upcoming  # noqa: E402


class WeekTransitionSemanticsTests(unittest.TestCase):
    def test_vague_training_fails_closed_but_fixed_enduro_school_stays_concrete(self):
        start = date(2026, 8, 24)
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
                    "date": (start + timedelta(days=index)).isoformat(),
                    "label": f"Dag {index + 1}",
                }
                for index in range(7)
            ],
            "planned_workouts": [
                {
                    "workout_key": "enduro-fixed",
                    "microcycle_slot": "fixed_enduro_school",
                    "date": "2026-08-24",
                    "status": "planned",
                    "planning_status": "fixed",
                    "sport": "enduro",
                    "classification": "training",
                    "manual_lock": True,
                    "session": "Enduroskola",
                    "reason": "Fast kalenderaktivitet och faktisk träningsbelastning.",
                },
                {
                    "workout_key": "strength-vague",
                    "microcycle_slot": "strength-core",
                    "date": "2026-08-25",
                    "status": "preliminary",
                    "planning_status": "preliminary",
                    "sport": "strength",
                    "session": "Styrka + core",
                    "reason": "Ingen dos ännu.",
                },
            ],
        }
        with self.assertRaisesRegex(RuntimeError, "saknar konkret grundplan"):
            promote_upcoming(upcoming)

        fixed_only = {
            **upcoming,
            "planned_workouts": [upcoming["planned_workouts"][0]],
        }
        promoted = promote_upcoming(fixed_only)
        workout = promoted["planned_workouts"][0]
        self.assertEqual(workout["status"], "planned")
        self.assertEqual(workout["classification"], "training")
        self.assertNotIn("dose_open", workout)
        self.assertIn("Enduroskola", workout["session"])

    def test_coach_cannot_target_recreation_workouts(self):
        plan = {
            "planned_workouts": [
                {
                    "workout_key": "enduro-recreation",
                    "date": "2026-08-24",
                    "status": "planned",
                    "sport": "enduro",
                    "classification": "recreation",
                    "session": "Enduro",
                },
                {
                    "workout_key": "run-1",
                    "date": "2026-08-26",
                    "status": "planned",
                    "sport": "run",
                    "session": "Löpning",
                },
            ]
        }
        self.assertEqual(
            allowed_target_dates(plan, [], "2026-08-24"),
            ["2026-08-26"],
        )


if __name__ == "__main__":
    unittest.main()
