#!/usr/bin/env python3
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL = REPO_ROOT / "supabase" / "migrations" / "20260924190000_activity_currentness.sql"


class ActivityCurrentnessSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = SQL.read_text(encoding="utf-8").lower()

    def test_activity_snapshot_currentness_columns_exist(self):
        self.assertIn("add column if not exists is_current boolean not null default true", self.sql)
        self.assertIn("add column if not exists last_seen_source_hash text", self.sql)

    def test_migration_does_not_grant_browser_table_access(self):
        self.assertNotIn("grant select", self.sql)
        self.assertNotIn("grant usage on schema training to anon", self.sql)


if __name__ == "__main__":
    unittest.main()
