#!/usr/bin/env python3
"""Read-only canonical current-plan source tests for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from planning_current_plan_source import (  # noqa: E402
    load_canonical_current_planned_workouts,
)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.calls.append((" ".join(str(query).split()), params))

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj

    def rollback(self):
        self.rolled_back = True


class PlanningCurrentPlanSourceTests(unittest.TestCase):
    def test_source_is_read_only_current_and_date_bounded(self):
        conn = FakeConnection(
            [
                (
                    "mc1:2026-10-02:run_easy",
                    date(2026, 10, 2),
                    "preliminary",
                    False,
                    {
                        "date": "2026-10-02",
                        "session": "Lugn distans",
                        "recipe_key": "run_easy_distance",
                        "dose_resolution": {"option_id": "run-easy-75"},
                    },
                    "snapshot-1",
                )
            ]
        )

        def connect(url, **kwargs):
            self.assertEqual(url, "postgresql://example")
            self.assertEqual(kwargs["sslmode"], "require")
            return conn

        rows, metadata = load_canonical_current_planned_workouts(
            date(2026, 10, 2),
            date(2026, 10, 4),
            env={"SUPABASE_DB_URL": "postgresql://example"},
            connect_fn=connect,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-10-02")
        self.assertEqual(
            rows[0]["payload"]["dose_resolution"]["option_id"],
            "run-easy-75",
        )
        self.assertTrue(metadata["verified"])
        self.assertEqual(metadata["coverage_from"], "2026-10-02")
        self.assertEqual(metadata["coverage_through"], "2026-10-04")
        self.assertTrue(conn.rolled_back)

        first_query, first_params = conn.cursor_obj.calls[0]
        self.assertEqual(first_query.lower(), "set transaction read only")
        self.assertIsNone(first_params)
        query, params = conn.cursor_obj.calls[1]
        lowered = query.lower()
        self.assertIn("from training.planned_workouts", lowered)
        self.assertIn("where is_current", lowered)
        self.assertIn("scheduled_date >= %s", lowered)
        self.assertIn("scheduled_date <= %s", lowered)
        self.assertEqual(
            params,
            (date(2026, 10, 2), date(2026, 10, 4)),
        )

    def test_payload_date_disagreement_fails_closed(self):
        conn = FakeConnection(
            [
                (
                    "w1",
                    date(2026, 10, 2),
                    "preliminary",
                    False,
                    {"date": "2026-10-03"},
                    "snapshot",
                )
            ]
        )

        def connect(_url, **_kwargs):
            return conn

        with self.assertRaises(RuntimeError):
            load_canonical_current_planned_workouts(
                date(2026, 10, 2),
                date(2026, 10, 4),
                env={"SUPABASE_DB_URL": "postgresql://example"},
                connect_fn=connect,
            )


if __name__ == "__main__":
    unittest.main()
