#!/usr/bin/env python3
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from training_job_runner import Stage, build_stages, run_stage  # noqa: E402


class TrainingJobRunnerTests(unittest.TestCase):
    def stage_keys(self, mode):
        return [stage.key for stage in build_stages(mode)]

    def test_event_and_reconcile_share_one_pipeline_except_ingest(self):
        event = self.stage_keys("event")
        reconcile = self.stage_keys("reconcile")
        self.assertIn("strava_event", event)
        self.assertNotIn("strava_reconcile", event)
        self.assertIn("strava_reconcile", reconcile)
        self.assertNotIn("strava_event", reconcile)
        self.assertEqual(
            [key for key in event if key != "strava_event"],
            [key for key in reconcile if key != "strava_reconcile"],
        )

    def test_pipeline_order_is_explicit_and_stable(self):
        keys = self.stage_keys("event")
        self.assertEqual(
            keys[:9],
            [
                "hydrate_activity_backend",
                "strava_event",
                "persist_strava_refresh_token",
                "apply_activity_directives",
                "normalize_activity_semantics",
                "canonicalize_coach_source_facts",
                "migrate_typed_plan",
                "validate_ingested_data",
                "promote_activity_backend",
            ],
        )
        self.assertNotIn("sync_reported_progression_pre", keys)
        self.assertNotIn("sync_reported_progression_post", keys)
        self.assertLess(keys.index("sync_performance_details"), keys.index("build_athlete_state"))
        self.assertLess(keys.index("weekly_review"), keys.index("build_athlete_state"))
        self.assertLess(keys.index("build_athlete_state"), keys.index("commit_athlete_runtime_backend"))
        self.assertLess(keys.index("commit_athlete_runtime_backend"), keys.index("adaptive_planning"))
        self.assertLess(keys.index("adaptive_planning"), keys.index("validate_adaptive_plan"))
        self.assertLess(keys.index("adaptive_planning"), keys.index("rollover_calendar"))
        self.assertLess(keys.index("validate_workout_designs"), keys.index("commit_planning_runtime_backend"))
        self.assertLess(keys.index("commit_planning_runtime_backend"), keys.index("sync_weather"))
        self.assertLess(keys.index("commit_planning_runtime_backend"), keys.index("coach_analysis"))
        self.assertLess(keys.index("rollover_calendar"), keys.index("apply_plan_overrides"))
        self.assertLess(keys.index("apply_plan_overrides"), keys.index("validate_rollover"))
        self.assertLess(keys.index("rollover_calendar"), keys.index("sync_weather"))
        self.assertLess(keys.index("coach_analysis"), keys.index("materialize_device_workouts"))
        self.assertLess(keys.index("materialize_device_workouts"), keys.index("validate_device_workouts"))
        self.assertLess(keys.index("validate_device_workouts"), keys.index("sync_device_workouts"))
        self.assertLess(keys.index("sync_device_workouts"), keys.index("guard_coach_claims"))
        self.assertLess(keys.index("validate_post_coach"), keys.index("commit_final_runtime_backend"))
        self.assertLess(keys.index("commit_final_runtime_backend"), keys.index("render_and_validate_site"))
        self.assertEqual(keys[-1], "render_and_validate_site")

    def test_runtime_backend_commit_points_are_required(self):
        stages = {stage.key: stage for stage in build_stages("event")}
        for key, scope in (
            ("commit_athlete_runtime_backend", "athlete"),
            ("commit_planning_runtime_backend", "planning"),
            ("commit_final_runtime_backend", "final"),
        ):
            stage = stages[key]
            self.assertFalse(stage.optional)
            self.assertIn("supabase_runtime_state.py", stage.command[1])
            self.assertEqual(stage.command[-2:], ("--scope", scope))

    def test_training_input_is_applied_after_db_hydration_and_before_ingest(self):
        with patch.dict(os.environ, {"TRAINING_INPUT_EVENT": "true"}, clear=False):
            keys = self.stage_keys("reconcile")
        self.assertLess(keys.index("hydrate_activity_backend"), keys.index("apply_training_input"))
        self.assertLess(keys.index("apply_training_input"), keys.index("strava_reconcile"))

    def test_activity_backend_hydration_is_required_and_first(self):
        stages = {stage.key: stage for stage in build_stages("event")}
        keys = self.stage_keys("event")
        hydrated = stages["hydrate_activity_backend"]
        self.assertFalse(hydrated.optional)
        self.assertEqual(keys[0], "hydrate_activity_backend")
        self.assertIn("supabase_activity_backend.py", hydrated.command[1])
        self.assertEqual(hydrated.command[-2:], ("--mode", "hydrate"))

    def test_rotated_strava_token_is_persisted_before_backend_gate(self):
        keys = self.stage_keys("event")
        self.assertLess(
            keys.index("persist_strava_refresh_token"),
            keys.index("promote_activity_backend"),
        )

    def test_activity_backend_is_required_before_fact_consumers(self):
        stages = {stage.key: stage for stage in build_stages("event")}
        keys = self.stage_keys("event")
        promoted = stages["promote_activity_backend"]
        self.assertFalse(promoted.optional)
        self.assertLess(keys.index("apply_activity_directives"), keys.index("normalize_activity_semantics"))
        self.assertLess(keys.index("normalize_activity_semantics"), keys.index("canonicalize_coach_source_facts"))
        self.assertLess(keys.index("canonicalize_coach_source_facts"), keys.index("validate_ingested_data"))
        self.assertLess(keys.index("validate_ingested_data"), keys.index("promote_activity_backend"))
        self.assertLess(keys.index("promote_activity_backend"), keys.index("sync_performance_details"))
        self.assertLess(keys.index("promote_activity_backend"), keys.index("weekly_review"))
        self.assertLess(keys.index("promote_activity_backend"), keys.index("build_athlete_state"))
        self.assertLess(keys.index("build_athlete_state"), keys.index("adaptive_planning"))

    def test_pre_adaptive_validation_allows_goal_replan_only(self):
        stages = {stage.key: stage for stage in build_stages("event")}
        pre = stages["validate_ingested_data"].command
        post = stages["validate_adaptive_plan"].command
        self.assertIn("--allow-stale-goal", pre)
        self.assertNotIn("--allow-stale-goal", post)

    def test_only_resilient_enrichment_and_transport_stages_are_optional(self):
        optional = {stage.key for stage in build_stages("event") if stage.optional}
        self.assertEqual(
            optional,
            {
                "sync_performance_details",
                "load_wellness_context",
                "coach_analysis",
                "sync_device_workouts",
                "weekly_review",
            },
        )

    @patch("training_job_runner.subprocess.run")
    def test_required_stage_fails_closed(self, mocked_run):
        mocked_run.return_value = SimpleNamespace(returncode=7)
        with self.assertRaises(RuntimeError):
            run_stage(Stage("required", ("fake-command",)), 1, 1)

    @patch("training_job_runner.subprocess.run")
    def test_optional_stage_reports_failure_without_aborting(self, mocked_run):
        mocked_run.return_value = SimpleNamespace(returncode=9)
        self.assertFalse(run_stage(Stage("optional", ("fake-command",), optional=True), 1, 1))

    @patch("training_job_runner.subprocess.run")
    def test_retryable_optional_stage_recovers_on_second_attempt(self, mocked_run):
        mocked_run.side_effect = [
            SimpleNamespace(returncode=9),
            SimpleNamespace(returncode=0),
        ]
        stage = Stage("ai-enrichment", ("fake-command",), optional=True, attempts=2)

        self.assertTrue(run_stage(stage, 1, 1))
        self.assertEqual(mocked_run.call_count, 2)

    @patch("training_job_runner.subprocess.run")
    def test_retryable_optional_stage_degrades_after_final_failure(self, mocked_run):
        mocked_run.side_effect = [
            SimpleNamespace(returncode=9),
            SimpleNamespace(returncode=9),
        ]
        stage = Stage("ai-enrichment", ("fake-command",), optional=True, attempts=2)

        self.assertFalse(run_stage(stage, 1, 1))
        self.assertEqual(mocked_run.call_count, 2)

    def test_ai_enrichment_stages_retry_without_becoming_pipeline_requirements(self):
        stages = {stage.key: stage for stage in build_stages("event")}
        self.assertTrue(stages["coach_analysis"].optional)
        self.assertEqual(stages["coach_analysis"].attempts, 2)
        self.assertTrue(stages["weekly_review"].optional)
        self.assertEqual(stages["weekly_review"].attempts, 2)

    def test_persist_token_requires_repository_at_execution_time(self):
        stage = next(
            stage for stage in build_stages("event") if stage.key == "persist_strava_refresh_token"
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                run_stage(stage, 1, 1)


if __name__ == "__main__":
    unittest.main()
