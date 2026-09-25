#!/usr/bin/env python3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "20260925081500_direct_training_feedback_rpc.sql"


class DirectTrainingFeedbackRpcSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")

    def test_rpc_is_security_definer_and_service_role_only(self):
        self.assertIn("create or replace function public.training_submit_activity_feedback", self.sql)
        self.assertIn("security definer", self.sql.lower())
        self.assertIn("set search_path = ''", self.sql)
        self.assertIn("revoke all on function public.training_submit_activity_feedback", self.sql)
        self.assertIn("from public, anon, authenticated", self.sql)
        self.assertIn("to service_role", self.sql)

    def test_rpc_is_idempotent_and_append_only(self):
        self.assertIn("insert into training.activity_feedback", self.sql)
        self.assertIn("on conflict (event_key) where event_key is not null", self.sql)
        self.assertIn("do nothing", self.sql)
        self.assertNotIn("delete from training.activity_feedback", self.sql.lower())

    def test_rpc_requires_existing_current_activity_and_validates_input(self):
        self.assertIn("a.is_current", self.sql)
        self.assertIn("activity_not_found", self.sql)
        self.assertIn("invalid_event_key", self.sql)
        self.assertIn("empty_input", self.sql)
        self.assertIn("invalid_feeling", self.sql)


if __name__ == "__main__":
    unittest.main()
