#!/usr/bin/env python3
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL = REPO_ROOT / "supabase" / "migrations" / "20260924193000_activity_lap_ordinal.sql"


class ActivityLapOrdinalSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = SQL.read_text(encoding="utf-8").lower()

    def test_lap_ordinal_becomes_relational_primary_key(self):
        self.assertIn("add column if not exists lap_ordinal integer", self.sql)
        self.assertIn("drop constraint if exists activity_laps_pkey", self.sql)
        self.assertIn("add primary key (activity_id, lap_ordinal)", self.sql)

    def test_source_lap_index_is_preserved_as_non_unique_data(self):
        self.assertIn(
            "create index if not exists activity_laps_source_index_idx",
            self.sql,
        )
        self.assertNotIn("unique (activity_id, lap_index)", self.sql)

    def test_no_browser_permissions_are_added(self):
        self.assertNotIn("grant select", self.sql)
        self.assertNotIn("grant usage on schema training to anon", self.sql)


if __name__ == "__main__":
    unittest.main()
