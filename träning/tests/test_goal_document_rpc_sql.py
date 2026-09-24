#!/usr/bin/env python3
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL = REPO_ROOT / "supabase" / "migrations" / "20260924182500_goal_document_rpc.sql"


class GoalDocumentRpcSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = SQL.read_text(encoding="utf-8").lower()

    def test_rpc_is_security_definer_with_empty_search_path(self):
        self.assertIn("public.training_goal_document()", self.sql)
        self.assertIn("security definer", self.sql)
        self.assertIn("set search_path = ''", self.sql)

    def test_rpc_grants_function_only_not_training_tables(self):
        self.assertIn(
            "grant execute on function public.training_goal_document() to anon, authenticated",
            self.sql,
        )
        self.assertNotIn("grant select on", self.sql)
        self.assertNotIn("grant usage on schema training to anon", self.sql)

    def test_rpc_reads_only_goal_state_document(self):
        self.assertIn("from training.state_documents", self.sql)
        self.assertIn("where d.document_key = 'goal'", self.sql)


if __name__ == "__main__":
    unittest.main()
