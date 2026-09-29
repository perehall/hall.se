import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "20260929094500_athlete_onboarding_profile.sql"


class AthleteProfileSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()

    def test_profile_is_per_athlete_and_backend_only(self):
        self.assertIn("create table if not exists training.athlete_profiles", self.sql)
        self.assertIn("athlete_subject text primary key", self.sql)
        self.assertIn("enable row level security", self.sql)
        self.assertIn("revoke all on training.athlete_profiles from public, anon, authenticated", self.sql)
        self.assertNotIn("grant select on training.athlete_profiles", self.sql)

    def test_worker_rpcs_are_service_role_only(self):
        self.assertIn("public.training_get_athlete_profile", self.sql)
        self.assertIn("public.training_upsert_athlete_profile", self.sql)
        self.assertIn("security definer", self.sql)
        self.assertIn("set search_path = ''", self.sql)
        self.assertIn("grant execute on function public.training_get_athlete_profile(text) to service_role", self.sql)
        self.assertIn("grant execute on function public.training_upsert_athlete_profile(text, jsonb, boolean) to service_role", self.sql)

    def test_frequency_contract_is_explicit(self):
        self.assertIn("preferred_days", self.sql)
        self.assertIn("min_days", self.sql)
        self.assertIn("max_days", self.sql)
        self.assertIn("min_days <= preferred_days", self.sql)
        self.assertIn("preferred_days <= max_days", self.sql)


if __name__ == "__main__":
    unittest.main()
