#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.presentation import build_presentation_snapshot  # noqa: E402
from training_core.presentation.manual_activity import manual_activities_for_day  # noqa: E402
from training_core.presentation.renderer import render_snapshot  # noqa: E402
from training_core.presentation.today import PlannedDay  # noqa: E402


class ManualActivityRepository:
    def planned_days(self, start, end):
        return [
            PlannedDay(
                local_date=date(2026, 9, 27),
                session="Vilodag",
                sport="rest",
                status="planned",
                payload={
                    "manual_activities": [
                        {
                            "status": "completed",
                            "sport": "strength",
                            "classification": "training",
                            "session": "Styrka/core · 25 min",
                            "reason": "Spontant genomfört och rapporterat.",
                        }
                    ]
                },
            )
        ]

    def completed_activities(self, start, end):
        return []


class ManualActivityTests(unittest.TestCase):
    def test_manual_completed_activity_survives_repository_shape_to_html(self):
        snapshot = build_presentation_snapshot(
            ManualActivityRepository(),
            today=date(2026, 9, 27),
        )
        self.assertEqual(snapshot.today.state, "completed")
        self.assertEqual(snapshot.today.title, "Styrka/core · 25 min")
        self.assertEqual(len(snapshot.today.manual_activities), 1)
        sunday = next(
            day for day in snapshot.week.days
            if day.local_date == date(2026, 9, 27)
        )
        self.assertEqual(
            sunday.manual_activities[0].classification,
            "training",
        )

        rendered = render_snapshot(snapshot)
        self.assertIn("Manuellt rapporterade aktiviteter", rendered)
        self.assertIn("Styrka/core · 25 min", rendered)
        self.assertIn("Spontant genomfört och rapporterat.", rendered)
        self.assertIn('data-classification="training"', rendered)

    def test_invalid_manual_activity_fails_closed(self):
        day = PlannedDay(
            local_date=date(2026, 9, 27),
            session="Vilodag",
            sport="rest",
            status="planned",
            payload={
                "manual_activities": [
                    {
                        "status": "planned",
                        "sport": "run",
                        "session": "Felaktigt ej genomfört pass",
                    }
                ]
            },
        )
        with self.assertRaisesRegex(RuntimeError, "is not completed"):
            manual_activities_for_day(day)

    def test_manual_reason_uses_public_copy_boundary(self):
        day = PlannedDay(
            local_date=date(2026, 9, 27),
            session="Vilodag",
            sport="rest",
            status="planned",
            payload={
                "manual_activities": [
                    {
                        "status": "completed",
                        "sport": "run",
                        "classification": "recreation",
                        "session": "Promenad",
                        "reason": (
                            "Lugn promenad. Valet utgår från athlete_state och "
                            "materialiserad relation: hold."
                        ),
                    }
                ]
            },
        )
        item = manual_activities_for_day(day)[0]
        self.assertEqual(item.reason, "Lugn promenad.")
        self.assertEqual(item.classification_label, "Rekreation")


if __name__ == "__main__":
    unittest.main()
