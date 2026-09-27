#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.presentation.today import (  # noqa: E402
    CompletedActivity,
    PlannedDay,
    build_today_read_model,
)


class TodayReadModelTests(unittest.TestCase):
    def test_actual_multi_session_truth_overrides_planned_session(self):
        today = date(2026, 9, 26)
        model = build_today_read_model(
            today=today,
            plan=[
                PlannedDay(today, "Simning · 4 000 m", "swim", "planned"),
                PlannedDay(date(2026, 9, 27), "Löpning · lugn distans · 120 min", "run", "planned"),
            ],
            activities=[
                CompletedActivity("1", today, "Enduro", "enduro", 6062, 26611.2),
                CompletedActivity("2", today, "Simning", "swim", 3822, 3000),
            ],
        )

        self.assertEqual(model.state, "completed")
        self.assertEqual(model.title, "Enduro + Simning")
        self.assertEqual(
            model.details,
            ("Enduro · 26,61 km · 1:41:02", "Simning · 3,00 km · 1:03:42"),
        )
        self.assertEqual(model.planned_session, "Simning · 4 000 m")
        self.assertEqual(model.next_session, "Löpning · lugn distans · 120 min")

    def test_plan_is_used_only_when_no_actual_activity_exists(self):
        today = date(2026, 9, 25)
        model = build_today_read_model(
            today=today,
            plan=[PlannedDay(today, "Simning · 4 000 m", "swim", "preliminary")],
            activities=[],
        )
        self.assertEqual(model.state, "preliminary")
        self.assertEqual(model.title, "Simning · 4 000 m")
        self.assertEqual(model.details, ())


if __name__ == "__main__":
    unittest.main()
