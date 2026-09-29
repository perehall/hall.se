#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from athlete_starting_state_source import _read_starting_state  # noqa: E402


class FakeCursor:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.calls.append((" ".join(str(query).split()), params))

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.cursor_obj = FakeCursor(row)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj

    def rollback(self):
        pass


class AthleteStartingStateSourceTests(unittest.TestCase):
    def test_explicit_generation_reads_frozen_starting_state_snapshot(self):
        state = {"schema_version": 1, "status": "confirmed", "source_mode": "manual"}
        conn = FakeConnection((state, 3, "2026-09-29"))

        def connect(url, **kwargs):
            return conn

        payload, revision, _ = _read_starting_state(
            "postgresql://example",
            generation_request_id="9d0fca58-4c4d-4ef9-9158-c7b81fd11c51",
            connect_fn=connect,
        )
        query, params = conn.cursor_obj.calls[-1]
        lowered = query.lower()
        self.assertIn("starting_state_snapshot", lowered)
        self.assertIn("starting_state_revision", lowered)
        self.assertEqual(params, ("9d0fca58-4c4d-4ef9-9158-c7b81fd11c51",))
        self.assertEqual(payload, state)
        self.assertEqual(revision, 3)

    def test_scheduled_planning_reads_active_state_for_planning_default_athlete(self):
        state = {"schema_version": 1, "status": "confirmed", "source_mode": "observed"}
        conn = FakeConnection((state, 4, "2026-09-29"))

        def connect(url, **kwargs):
            return conn

        _read_starting_state("postgresql://example", connect_fn=connect)
        query, params = conn.cursor_obj.calls[-1]
        lowered = query.lower()
        self.assertIn("from training.athlete_starting_states s", lowered)
        self.assertIn("join training.athlete_profiles p", lowered)
        self.assertIn("p.is_planning_default", lowered)
        self.assertIn("s.active_state is not null", lowered)
        self.assertIsNone(params)


if __name__ == "__main__":
    unittest.main()
