import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "20260929094500_athlete_onboarding_profile.sql"
GENERATION_MIGRATION = ROOT / "supabase" / "migrations" / "20260929123000_plan_generation_requests.sql"
ACTIVATION_MIGRATION = ROOT / "supabase" / "migrations" / "20260929132000_profile_activation_boundary.sql"
STARTING_STATE_MIGRATION = ROOT / "supabase" / "migrations" / "20260929141000_athlete_starting_state.sql"


class AthleteProfileSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()
        cls.generation_sql = GENERATION_MIGRATION.read_text(encoding="utf-8").lower()
        cls.activation_sql = ACTIVATION_MIGRATION.read_text(encoding="utf-8").lower()
        cls.starting_state_sql = STARTING_STATE_MIGRATION.read_text(encoding="utf-8").lower()

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

    def test_plan_generation_is_durable_and_backend_only(self):
        self.assertIn("create table if not exists training.plan_generation_requests", self.generation_sql)
        self.assertIn("profile_revision bigint not null", self.generation_sql)
        self.assertIn("status text not null default 'queued'", self.generation_sql)
        self.assertIn("enable row level security", self.generation_sql)
        self.assertIn("revoke all on training.plan_generation_requests from public, anon, authenticated", self.generation_sql)
        self.assertIn("training_request_plan_generation", self.generation_sql)
        self.assertIn("training_get_plan_generation", self.generation_sql)
        self.assertIn("training_set_plan_generation_status", self.generation_sql)

    def test_profile_activation_is_separate_from_profile_save(self):
        self.assertIn("active_profile jsonb", self.activation_sql)
        self.assertIn("active_revision bigint", self.activation_sql)
        self.assertIn("profile_snapshot jsonb", self.activation_sql)
        self.assertIn("v_profile.profile", self.activation_sql)
        self.assertIn("active_profile = v_request.profile_snapshot", self.activation_sql)
        self.assertIn("active_revision = v_request.profile_revision", self.activation_sql)
        self.assertIn("if p_status = 'completed' then", self.activation_sql)

    def test_generation_snapshot_becomes_immutable_planning_input(self):
        self.assertIn("alter column profile_snapshot set not null", self.activation_sql)
        self.assertIn("jsonb_typeof(profile_snapshot) = 'object'", self.activation_sql)
        self.assertIn("profile revision it was created from", self.activation_sql)

    def test_starting_state_is_per_athlete_and_separate_from_preferences(self):
        self.assertIn("create table if not exists training.athlete_starting_states", self.starting_state_sql)
        self.assertIn("athlete_subject text primary key", self.starting_state_sql)
        self.assertIn("source_mode text not null", self.starting_state_sql)
        self.assertIn("manual_state jsonb", self.starting_state_sql)
        self.assertIn("observed_snapshot jsonb", self.starting_state_sql)
        self.assertIn("active_state jsonb", self.starting_state_sql)
        self.assertIn("enable row level security", self.starting_state_sql)

    def test_observed_candidate_is_confirmation_input_not_progression_proof(self):
        self.assertIn("presentation threshold", self.starting_state_sql)
        self.assertIn("not a physiological", self.starting_state_sql)
        self.assertIn("observed_starting_state_requires_confirmation", self.starting_state_sql)
        self.assertIn("v_state->'load_windows'->'windows'->'recent_28d'", self.starting_state_sql)

    def test_generation_freezes_profile_and_starting_state_together(self):
        self.assertIn("starting_state_revision bigint", self.starting_state_sql)
        self.assertIn("starting_state_snapshot jsonb", self.starting_state_sql)
        self.assertIn("confirmed_starting_state_required", self.starting_state_sql)
        self.assertIn("active_state = v_request.starting_state_snapshot", self.starting_state_sql)
        self.assertIn("active_starting_state_revision", self.starting_state_sql)

    def test_frequency_contract_is_explicit(self):
        self.assertIn("preferred_days", self.sql)
        self.assertIn("min_days", self.sql)
        self.assertIn("max_days", self.sql)
        self.assertIn("min_days <= preferred_days", self.sql)
        self.assertIn("preferred_days <= max_days", self.sql)


if __name__ == "__main__":
    unittest.main()
