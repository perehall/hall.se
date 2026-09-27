#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.repositories.presentation import PostgresPresentationRepository


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = ""
        self.params = None

    def execute(self, q, p):
        self.query = q
        self.params = p

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Conn:
    def __init__(self, rows):
        self.cursor_instance = Cursor(rows)

    def cursor(self):
        return self.cursor_instance

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class CapturingFactory:
    def __init__(self, rows):
        self.rows = rows
        self.connections = []

    def __call__(self):
        conn = Conn(self.rows)
        self.connections.append(conn)
        return conn

    @property
    def last_query(self):
        return self.connections[-1].cursor_instance.query


class PostgresPresentationRepositoryTests(unittest.TestCase):
    def test_plans_are_read_only_from_current_relational_rows(self):
        rows = [
            (
                date(2026, 9, 27),
                "Löpning · 60 min",
                "run",
                "conditional",
                "fixed",
                False,
                "Skäl",
                "Fokus",
                {
                    "manual_activities": [
                        {
                            "status": "completed",
                            "sport": "strength",
                            "session": "Styrka/core · 25 min",
                        }
                    ]
                },
            )
        ]
        factory = CapturingFactory(rows)
        repo = PostgresPresentationRepository(factory)
        days = repo.planned_days(date(2026, 9, 27), date(2026, 10, 4))
        self.assertEqual(days[0].session, "Löpning · 60 min")
        self.assertEqual(days[0].planning_status, "fixed")
        self.assertEqual(
            days[0].payload["manual_activities"][0]["session"],
            "Styrka/core · 25 min",
        )
        self.assertIn("where is_current", factory.last_query)

    def test_activity_override_label_and_latest_outcome_are_resolved_by_repository(self):
        rows = [
            (
                "42",
                date(2026, 9, 26),
                "Enduro",
                "enduro",
                6062,
                26611.2,
                142.0,
                171.0,
                "training-input:aaaaaaaaaaaaaaaaaaaaaaaa",
                "Bra kontroll.",
                6,
                ["fresh", "could_do_more"],
                "Avsett stimulus genomfört.",
                "keep",
                "Ingen ändring behövs.",
                "Fortsätt enligt plan.",
                False,
            )
        ]
        factory = CapturingFactory(rows)
        repo = PostgresPresentationRepository(factory)
        activities = repo.completed_activities(
            date(2026, 9, 26), date(2026, 9, 26)
        )
        activity = activities[0]
        self.assertEqual(activity.label, "Enduro")
        self.assertEqual(activity.distance_m, 26611.2)
        self.assertEqual(
            activity.feedback_event_key,
            "training-input:aaaaaaaaaaaaaaaaaaaaaaaa",
        )
        self.assertEqual(activity.rpe, 6)
        self.assertEqual(activity.feelings, ("fresh", "could_do_more"))
        self.assertEqual(activity.coach_summary, "Avsett stimulus genomfört.")
        self.assertEqual(activity.plan_action, "keep")
        self.assertIn("where a.is_current", factory.last_query)
        self.assertIn("training.activity_feedback", factory.last_query)
        self.assertIn("training.coach_evaluations", factory.last_query)

    def test_trailrun_provider_vocabulary_is_public_traillopning(self):
        rows = [
            (
                "43",
                date(2026, 9, 27),
                "TrailRun",
                "run",
                4804,
                13460.0,
                130.0,
                150.0,
                "",
                "",
                None,
                [],
                "",
                "",
                "",
                "",
                False,
            )
        ]
        repo = PostgresPresentationRepository(CapturingFactory(rows))
        activities = repo.completed_activities(
            date(2026, 9, 27), date(2026, 9, 27)
        )
        self.assertEqual(activities[0].label, "Traillöpning")

    def test_provider_vocabulary_is_normalized_before_presentation(self):
        rows = [
            (
                "42",
                date(2026, 9, 26),
                "Swim",
                "swim",
                3822,
                3000.0,
                None,
                None,
                "",
                "",
                None,
                [],
                "",
                "",
                "",
                "",
                False,
            )
        ]
        repo = PostgresPresentationRepository(CapturingFactory(rows))
        activities = repo.completed_activities(
            date(2026, 9, 26), date(2026, 9, 26)
        )
        self.assertEqual(activities[0].label, "Simning")


if __name__ == "__main__":
    unittest.main()
