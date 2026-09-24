#!/usr/bin/env python3
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from supabase_goal_source import canonical_hash, load_goal_for_planner  # noqa: E402


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class _Cursor:
    def __init__(self, row):
        self.row = row
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query):
        self.queries.append(" ".join(str(query).split()))

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.cursor_object = _Cursor(row)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_object


class SupabaseGoalSourceTests(unittest.TestCase):
    def setUp(self):
        self.goal = {
            "schema_version": 3,
            "goal": "Allround",
            "development_goals": [{"id": "allround-athlete", "type": "development"}],
            "performance_goals": [{"id": "race", "type": "performance"}],
        }
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "goal.json"
        self.path.write_text(json.dumps(self.goal, ensure_ascii=False), encoding="utf-8")
        self.rpc_env = {
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            "SUPABASE_PROJECT_URL": "https://example.supabase.co",
        }

    def tearDown(self):
        self.temp.cleanup()

    def _opener(self, payload):
        encoded = json.dumps(payload).encode("utf-8")

        def open_request(request, timeout):
            self.assertEqual(request.full_url, "https://example.supabase.co/rest/v1/rpc/training_goal_document")
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(timeout, 5.0)
            self.assertEqual(request.headers.get("Apikey"), "sb_publishable_test")
            return _Response(encoded)

        return open_request

    def _db_connect(self, row, observed):
        def connect(database_url, **kwargs):
            observed["url"] = database_url
            observed["kwargs"] = kwargs
            connection = _Connection(row)
            observed["connection"] = connection
            return connection

        return connect

    def test_prefers_exact_hash_matched_database_document(self):
        digest = canonical_hash(self.goal)
        updated_at = datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc)
        observed = {}
        goal, meta = load_goal_for_planner(
            self.path,
            db_connect=self._db_connect((digest, self.goal, updated_at), observed),
            env={"SUPABASE_DB_URL": "postgresql://example.invalid/db"},
        )
        self.assertEqual(goal, self.goal)
        self.assertEqual(meta["source"], "supabase_db")
        self.assertTrue(meta["verified"])
        self.assertEqual(meta["source_hash"], digest)
        self.assertEqual(observed["kwargs"]["sslmode"], "require")
        self.assertEqual(observed["kwargs"]["connect_timeout"], 5)
        self.assertEqual(
            observed["connection"].cursor_object.queries[0],
            "set transaction read only",
        )

    def test_stale_database_cannot_influence_planner(self):
        stale = dict(self.goal)
        stale["goal"] = "Stale"
        observed = {}
        goal, meta = load_goal_for_planner(
            self.path,
            db_connect=self._db_connect((canonical_hash(stale), stale, None), observed),
            env={"SUPABASE_DB_URL": "postgresql://example.invalid/db"},
        )
        self.assertEqual(goal, self.goal)
        self.assertEqual(meta["source"], "json_fallback")
        self.assertEqual(meta["reason"], "database_snapshot_stale")

    def test_database_failure_falls_back_without_leaking_connection_text(self):
        def failing(_url, **_kwargs):
            raise RuntimeError("postgresql://secret-user:secret-pass@example.invalid/db")

        goal, meta = load_goal_for_planner(
            self.path,
            db_connect=failing,
            env={"SUPABASE_DB_URL": "postgresql://secret"},
        )
        self.assertEqual(goal, self.goal)
        self.assertEqual(meta["source"], "json_fallback")
        self.assertEqual(meta["reason"], "database_unavailable:RuntimeError")
        self.assertNotIn("secret", meta["reason"])

    def test_rpc_promotes_exact_hash_when_database_is_not_configured(self):
        digest = canonical_hash(self.goal)
        payload = {
            "status": "ok",
            "source": "supabase",
            "source_hash": digest,
            "updated_at": "2026-09-24T16:00:00+00:00",
            "payload": self.goal,
        }
        goal, meta = load_goal_for_planner(
            self.path,
            opener=self._opener(payload),
            env=self.rpc_env,
        )
        self.assertEqual(goal, self.goal)
        self.assertEqual(meta["source"], "supabase_rpc")
        self.assertTrue(meta["verified"])

    def test_rpc_stale_backend_cannot_influence_planner(self):
        stale = dict(self.goal)
        stale["goal"] = "Stale"
        payload = {
            "status": "ok",
            "source_hash": canonical_hash(stale),
            "payload": stale,
        }
        goal, meta = load_goal_for_planner(
            self.path,
            opener=self._opener(payload),
            env=self.rpc_env,
        )
        self.assertEqual(goal, self.goal)
        self.assertEqual(meta["reason"], "rpc_snapshot_stale")

    def test_no_backend_configuration_uses_local_without_network(self):
        called = False

        def should_not_call(_request, timeout):
            nonlocal called
            called = True
            raise AssertionError("network should not be called")

        goal, meta = load_goal_for_planner(
            self.path,
            opener=should_not_call,
            env={},
        )
        self.assertEqual(goal, self.goal)
        self.assertFalse(called)
        self.assertEqual(meta["reason"], "database_url_missing")


if __name__ == "__main__":
    unittest.main()
