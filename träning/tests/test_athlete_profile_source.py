#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from athlete_profile_source import _read_from_database  # noqa: E402


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
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj

    def rollback(self):
        self.rolled_back = True


class AthleteProfileSourceTests(unittest.TestCase):
    def test_explicit_generation_reads_frozen_request_snapshot(self):
        conn = FakeConnection(({"schema_version": 1, "status": "complete"}, 7, "2026-09-29"))
        seen = {}

        def connect(url, **kwargs):
            seen["url"] = url
            seen["kwargs"] = kwargs
            return conn

        payload, revision, _ = _read_from_database(
            "postgresql://example",
            generation_request_id="9d0fca58-4c4d-4ef9-9158-c7b81fd11c51",
            connect_fn=connect,
        )
        query, params = conn.cursor_obj.calls[-1]
        self.assertIn("select r.profile_snapshot, r.profile_revision, r.requested_at", query.lower())
        self.assertNotIn("p.profile", query.lower())
        self.assertEqual(params, ("9d0fca58-4c4d-4ef9-9158-c7b81fd11c51",))
        self.assertEqual(revision, 7)
        self.assertEqual(payload["status"], "complete")

    def test_scheduled_planning_reads_only_activated_profile(self):
        conn = FakeConnection(({"schema_version": 1, "status": "complete"}, 4, "2026-09-29"))

        def connect(url, **kwargs):
            return conn

        _read_from_database("postgresql://example", connect_fn=connect)
        query, params = conn.cursor_obj.calls[-1]
        lowered = query.lower()
        self.assertIn("select active_profile, active_revision, activated_at", lowered)
        self.assertIn("active_profile is not null", lowered)
        self.assertNotIn("select profile, revision", lowered)
        self.assertIsNone(params)


if __name__ == "__main__":
    unittest.main()
