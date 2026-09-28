#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.presentation.today import CompletedActivity, PlannedDay
from training_core.presentation.week import build_week_read_model


class WeekReadModelTests(unittest.TestCase):
    def test_multiple_activities_are_one_training_day_but_two_activities(self):
        start = date(2026, 9, 21)
        end = date(2026, 9, 27)
        plan = [
            PlannedDay(
                date(2026, 9, 26),
                "Simning · 4 000 m",
                "swim",
                "planned",
            )
        ]
        acts = [
            CompletedActivity(
                "1",
                date(2026, 9, 26),
                "Enduro",
                "enduro",
                elapsed_time_s=6062,
                distance_m=26611.2,
            ),
            CompletedActivity(
                "2",
                date(2026, 9, 26),
                "Simning",
                "swim",
                elapsed_time_s=3822,
                distance_m=3000,
            ),
        ]
        model = build_week_read_model(
            start=start,
            end=end,
            plan=plan,
            activities=acts,
        )
        self.assertEqual(model.training_day_count, 1)
        self.assertEqual(model.completed_activity_count, 2)
        saturday = next(day for day in model.days if day.local_date == date(2026, 9, 26))
        self.assertEqual(saturday.actual_labels, ("Enduro", "Simning"))
        self.assertEqual(saturday.completed_activity_count, 2)
        self.assertEqual(saturday.session_time, "2:44:44")
        self.assertEqual(saturday.total_distance, "29,61 km")
        self.assertEqual(
            saturday.status_summary,
            "2 pass · 2:44:44 · 29,61 km",
        )
        self.assertEqual(
            [activity.detail for activity in saturday.actual_activities],
            [
                "Enduro · 26,61 km · 1:41:02",
                "Simning · 3,00 km · 1:03:42",
            ],
        )
        self.assertEqual(saturday.state, "completed")
        self.assertEqual(model.session_time_s, 9884)
        self.assertEqual(model.session_time, "2:44:44")
        self.assertEqual(model.total_distance_m, 29611.2)
        self.assertEqual(model.total_distance, "29,61 km")
        self.assertEqual(
            model.status_summary,
            "2 pass · 2:44:44 · 29,61 km · 1 träningsdag",
        )
        self.assertEqual(
            [(item.label, item.duration, item.distance) for item in model.sport_distribution],
            [
                ("Enduro", "1:41:02", "26,61 km"),
                ("Simning", "1:03:42", "3,00 km"),
            ],
        )

    def test_multiple_planned_workouts_share_one_calendar_day(self):
        start = date(2026, 9, 21)
        end = date(2026, 9, 27)
        same_day = date(2026, 9, 25)
        model = build_week_read_model(
            start=start,
            end=end,
            plan=[
                PlannedDay(same_day, "Simning", "swim", "planned", workout_key="a"),
                PlannedDay(same_day, "Styrka", "strength", "planned", workout_key="b"),
                PlannedDay(same_day, "Löpning", "run", "planned", workout_key="c"),
            ],
            activities=[],
        )
        friday = next(day for day in model.days if day.local_date == same_day)
        self.assertEqual(friday.planned_sessions, ("Simning", "Styrka", "Löpning"))
        self.assertEqual(len(friday.planned_workouts), 3)
        self.assertEqual(model.planned_count, 3)
        self.assertEqual(len(model.days), 7)

    def test_week_status_matches_current_production_aggregate_contract(self):
        start = date(2026, 9, 21)
        end = date(2026, 9, 27)
        durations = [
            ("Enduro", "enduro", 11871),
            ("Löpning", "run", 8254),
            ("MTB/XC", "bike", 4976),
            ("Simning", "swim", 7359),
            ("Styrka", "strength", 2014),
        ]
        activities = []
        source_id = 1
        for index, (label, family, seconds) in enumerate(durations):
            activities.append(
                CompletedActivity(
                    str(source_id),
                    date(2026, 9, 21 + min(index, 5)),
                    label,
                    family,
                    elapsed_time_s=seconds,
                )
            )
            source_id += 1
        # Three extra activities with zero duration preserve the current
        # production count (8) without changing the known 34 474 s aggregate.
        for activity_date in (
            date(2026, 9, 21),
            date(2026, 9, 22),
            date(2026, 9, 26),
        ):
            activities.append(
                CompletedActivity(
                    str(source_id),
                    activity_date,
                    "Löpning",
                    "run",
                    elapsed_time_s=0,
                )
            )
            source_id += 1

        model = build_week_read_model(
            start=start,
            end=end,
            plan=[],
            activities=activities,
        )
        self.assertEqual(model.completed_activity_count, 8)
        self.assertEqual(model.session_time_s, 34474)
        self.assertEqual(model.session_time, "9:34:34")
        self.assertEqual(model.training_day_count, 6)


if __name__ == "__main__":
    unittest.main()
