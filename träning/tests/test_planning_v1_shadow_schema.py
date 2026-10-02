import unittest

from scripts.planning_v1_shadow_schema import _validate_migration_scope


class PlanningV1ShadowSchemaScopeTests(unittest.TestCase):
    def test_accepts_shadow_audit_only_schema(self):
        _validate_migration_scope(
            """
            create table training.planning_v1_shadow_runs (id uuid);
            alter table training.planning_v1_shadow_runs enable row level security;
            """
        )

    def test_rejects_authoritative_plan_mutation_surface(self):
        with self.assertRaises(RuntimeError):
            _validate_migration_scope(
                """
                create table training.planning_v1_shadow_runs (id uuid);
                alter table training.planning_v1_shadow_runs enable row level security;
                update training.planned_workouts set title = 'x';
                """
            )

    def test_rejects_data_writes_even_to_shadow_relation(self):
        with self.assertRaises(RuntimeError):
            _validate_migration_scope(
                """
                create table training.planning_v1_shadow_runs (id uuid);
                alter table training.planning_v1_shadow_runs enable row level security;
                insert into training.planning_v1_shadow_runs(id) values (gen_random_uuid());
                """
            )


if __name__ == "__main__":
    unittest.main()
