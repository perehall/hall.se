import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260924165000_backend_status_rpc.sql"


class BackendStatusRpcSqlTests(unittest.TestCase):
    def test_rpc_is_sanitized_and_least_privilege(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("create or replace function public.training_backend_status()", sql)
        self.assertIn("security definer", sql)
        self.assertIn("set search_path = ''", sql)
        self.assertIn("revoke all on function public.training_backend_status() from public", sql)
        self.assertIn("grant execute on function public.training_backend_status() to anon, authenticated", sql)
        self.assertNotIn("grant select on training.", sql)
        self.assertNotIn("grant usage on schema training to anon", sql)


if __name__ == "__main__":
    unittest.main()
