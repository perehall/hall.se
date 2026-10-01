#!/usr/bin/env python3
"""Read-only canonical activity source tests for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from planning_activity_source import load_canonical_training_activities  # noqa: E402


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


class PlanningActivitySourceTests(unittest.TestCase):
    def source(self, rows):
        conn = FakeConnection(rows)

        def connect(url, **kwargs):
            self.assertEqual(url, "postgresql://example")
            self.assertEqual(kwargs["sslmode"], "require")
            return conn

        result = load_canonical_training_activities(
            date(2026, 9, 28),
            date(2026, 10, 1),
            env={"SUPABASE_DB_URL": "postgresql://example"},
            connect_fn=connect,
        )
        return result, conn

    def test_source_is_read_only_and_date_bounded(self):
        (rows, metadata), conn = self.source(
            [
                (
                    "1",
                    date(2026, 9, 29),
                    "run",
                    "training",
                    3600,
                    12000.0,
                )
            ]
        )
        self.assertEqual(rows[0]["id"], "1")
        self.assertEqual(rows[0]["date"], "2026-09-29")
        self.assertEqual(metadata["training_activity_count"], 1)
        self.assertTrue(metadata["verified"])
        self.assertTrue(conn.rolled_back)
        first_query, first_params = conn.cursor_obj.calls[0]
        self.assertEqual(first_query.lower(), "set transaction read only")
        self.assertIsNone(first_params)
        query, params = conn.cursor_obj.calls[1]
        lowered = query.lower()
        self.assertIn("from training.activities", lowered)
        self.assertIn("is_current", lowered)
        self.assertIn("classification = 'training'", lowered)
        self.assertIn("local_date >= %s", lowered)
        self.assertIn("local_date <= %s", lowered)
        self.assertEqual(
            params,
            (date(2026, 9, 28), date(2026, 10, 1)),
        )

    def test_duplicate_provider_activity_id_fails_closed(self):
        with self.assertRaises(RuntimeError):
            self.source(
                [
                    ("1", date(2026, 9, 29), "run", "training", 3600, 10000),
                    ("1", date(2026, 9, 30), "run", "training", 3000, 9000),
                ]
            )

    def test_missing_duration_fails_closed(self):
        with self.assertRaises(RuntimeError):
            self.source(
                [
                    ("1", date(2026, 9, 29), "run", "training", None, 10000),
                ]
            )


if __name__ == "__main__":
    unittest.main()
