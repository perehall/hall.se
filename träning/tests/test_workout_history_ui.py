#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_workout_history import matching_swim_dates  # noqa: E402


class WorkoutHistoryUiTests(unittest.TestCase):
    def test_swimrun_does_not_mark_planned_swim_workout_completed(self):
        activities = [
            {
                "id": 1,
                "sport_type": "Swimrun",
                "start_date_local": "2026-09-02T18:01:01+02:00",
            }
        ]
        self.assertEqual(matching_swim_dates(activities), set())

    def test_actual_planned_swim_can_mark_workout_completed(self):
        activities = [
            {
                "id": 2,
                "sport_type": "Swim",
                "start_date_local": "2026-09-05T10:00:00+02:00",
            }
        ]
        self.assertEqual(matching_swim_dates(activities), {"2026-09-05"})

    def test_separate_spontaneous_swim_does_not_fulfill_planned_workout(self):
        activities = [
            {
                "id": 3,
                "sport_type": "Swim",
                "plan_relation": "separate",
                "start_date_local": "2026-09-05T10:00:00+02:00",
            }
        ]
        self.assertEqual(matching_swim_dates(activities), set())


if __name__ == "__main__":
    unittest.main()
