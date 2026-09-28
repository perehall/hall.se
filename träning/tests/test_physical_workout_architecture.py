#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class PhysicalWorkoutArchitectureTests(unittest.TestCase):
    def test_catalog_contains_only_single_sport_recipes_unless_explicit_multisport(self):
        catalog = json.loads(
            (ROOT / "data" / "workout_catalog.json").read_text(encoding="utf-8")
        )
        prefixes = {
            "run": ("run_",),
            "swim": ("swim_",),
            "strength": ("strength_", "plyometric"),
            "bike": ("mtb_", "bike_"),
            "enduro": ("enduro_",),
        }
        for key, recipe in (catalog.get("recipes") or {}).items():
            families = {
                family
                for family, family_prefixes in prefixes.items()
                if any(
                    any(str(stimulus).startswith(prefix) for prefix in family_prefixes)
                    for stimulus in (
                        list(recipe.get("stimuli") or [])
                        + list(recipe.get("optional_stimuli") or [])
                    )
                )
            }
            sport = str(recipe.get("sport") or "")
            if sport == "multisport":
                continue
            self.assertLessEqual(
                len(families),
                1,
                f"{key} mixes physical sport families {sorted(families)}",
            )

    def test_current_canonical_workouts_do_not_mix_physical_sport_families(self):
        plan = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))
        family_prefixes = {
            "run": ("run_",),
            "swim": ("swim_",),
            "strength": ("strength_", "plyometric"),
            "bike": ("mtb_", "bike_"),
            "enduro": ("enduro_",),
        }
        for workout in plan["planned_workouts"]:
            sport = str(workout.get("sport") or "")
            if sport == "multisport":
                continue
            stimuli = list(workout.get("stimuli") or []) + list(
                workout.get("optional_stimuli") or []
            )
            families = {
                family
                for family, prefixes in family_prefixes.items()
                if any(
                    any(str(stimulus).startswith(prefix) for prefix in prefixes)
                    for stimulus in stimuli
                )
            }
            self.assertLessEqual(
                len(families),
                1,
                f"{workout.get('date')} {workout.get('session')} mixes {sorted(families)}",
            )

    def test_active_runtime_documents_have_calendar_axis_only(self):
        for filename in ("plan.json", "upcoming_week.json"):
            document = json.loads(
                (ROOT / "data" / filename).read_text(encoding="utf-8")
            )
            self.assertIsInstance(document.get("planned_workouts"), list)
            self.assertEqual(len(document.get("days") or []), 7)
            for row in document["days"]:
                self.assertEqual(
                    set(row),
                    {"date", "label"},
                    f"{filename} reintroduced workout state into days: {row}",
                )
            self.assertNotIn("additional_planned_workouts", json.dumps(document))

    def test_active_runtime_has_no_composite_same_day_workout_concept(self):
        active_sources = (
            SCRIPTS / "adaptive_planner.py",
            SCRIPTS / "workout_design.py",
            SCRIPTS / "rollover_week.py",
            SCRIPTS / "materialize_workout_designs.py",
            SCRIPTS / "materialize_device_workouts.py",
            SCRIPTS / "sync_intervals_workouts.py",
            SCRIPTS / "coach_rules.py",
            SCRIPTS / "coach_pipeline.py",
            SCRIPTS / "coach.py",
        )
        forbidden_tokens = (
            "swim_" + "strength",
            "swim_component",
            "Composite support day",
            "kombinerade dagen",
            "additional_planned_workouts",
        )
        for path in active_sources:
            source = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                self.assertNotIn(
                    token,
                    source,
                    f"{path.name} contains retired composite semantics: {token}",
                )

    def test_production_workout_consumers_cannot_read_calendar_days(self):
        consumers = (
            "coach_rules.py",
            "coach_pipeline.py",
            "coach.py",
            "weekly_review.py",
            "workout_design.py",
            "materialize_workout_designs.py",
            "materialize_device_workouts.py",
            "validate_workout_designs.py",
            "validate_device_workouts.py",
            "sync_intervals_workouts.py",
            "supabase_shadow_model.py",
            "apply_plan_overrides.py",
        )
        forbidden = (
            '.get("days")',
            ".get('days')",
            '["days"]',
            "['days']",
        )
        for filename in consumers:
            source = (SCRIPTS / filename).read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(
                    token,
                    source,
                    f"{filename} reads calendar days in a workout consumer: {token}",
                )

    def test_runtime_and_deploy_do_not_invoke_legacy_migration_or_projection(self):
        runtime_paths = (
            SCRIPTS / "training_job_runner.py",
            ROOT.parent / ".github" / "workflows" / "deploy-pages.yml",
            ROOT.parent / ".github" / "workflows" / "test-training.yml",
            ROOT.parent / ".github" / "workflows" / "training-regression-pr.yml",
        )
        forbidden = (
            "migrate_training_data_v3.py",
            "calendar_projection",
            "refresh_calendar_projection",
        )
        for path in runtime_paths:
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(
                    token,
                    source,
                    f"{path.name} still invokes retired migration/projection: {token}",
                )

    def test_calendar_projection_module_is_deleted(self):
        self.assertFalse((SCRIPTS / "calendar_projection.py").exists())

    def test_current_and_upcoming_allow_arbitrary_same_day_workouts_without_calendar_encoding(self):
        for filename in ("plan.json", "upcoming_week.json"):
            document = json.loads(
                (ROOT / "data" / filename).read_text(encoding="utf-8")
            )
            by_date = {}
            for workout in document["planned_workouts"]:
                by_date.setdefault(workout["date"], []).append(workout)
            for date_value, workouts in by_date.items():
                if len(workouts) > 1:
                    axis = next(
                        row for row in document["days"] if row["date"] == date_value
                    )
                    self.assertEqual(set(axis), {"date", "label"})
                    self.assertEqual(
                        len({str(w.get("microcycle_slot") or w.get("workout_key")) for w in workouts}),
                        len(workouts),
                    )

    def test_active_runtime_documents_have_no_retired_composite_identifiers(self):
        retired = "swim_" + "strength"
        for filename in ("plan.json", "upcoming_week.json"):
            document = json.loads(
                (ROOT / "data" / filename).read_text(encoding="utf-8")
            )
            self.assertNotIn(retired, json.dumps(document))


if __name__ == "__main__":
    unittest.main()
