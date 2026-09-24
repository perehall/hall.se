#!/usr/bin/env python3
import io
import json
import sys
import tempfile
import unittest
import urllib.error
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
        self.env = {
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

    def test_promotes_exact_hash_matched_supabase_document(self):
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
            env=self.env,
        )
        self.assertEqual(goal, self.goal)
        self.assertEqual(meta["source"], "supabase")
        self.assertTrue(meta["verified"])
        self.assertEqual(meta["source_hash"], digest)

    def test_stale_backend_cannot_influence_planner(self):
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
            env=self.env,
        )
        self.assertEqual(goal, self.goal)
        self.assertEqual(meta["source"], "json_fallback")
        self.assertEqual(meta["reason"], "backend_snapshot_stale")

    def test_declared_hash_mismatch_is_rejected_even_when_payload_matches(self):
        payload = {
            "status": "ok",
            "source_hash": "0" * 64,
            "payload": self.goal,
        }
        goal, meta = load_goal_for_planner(
            self.path,
            opener=self._opener(payload),
            env=self.env,
        )
        self.assertEqual(goal, self.goal)
        self.assertEqual(meta["reason"], "backend_snapshot_stale")

    def test_backend_failure_is_non_blocking(self):
        def failing(_request, timeout):
            raise urllib.error.URLError("offline")

        goal, meta = load_goal_for_planner(
            self.path,
            opener=failing,
            env=self.env,
        )
        self.assertEqual(goal, self.goal)
        self.assertEqual(meta["source"], "json_fallback")
        self.assertTrue(meta["reason"].startswith("backend_unavailable:"))

    def test_missing_publishable_key_uses_local_without_network(self):
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
        self.assertEqual(meta["reason"], "publishable_key_missing")


if __name__ == "__main__":
    unittest.main()
