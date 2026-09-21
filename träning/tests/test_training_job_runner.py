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
            keys[:4],
            [
                "strava_event",
                "normalize_activity_semantics",
                "migrate_typed_plan",
                "validate_ingested_data",
            ],
        )
        self.assertNotIn("sync_reported_progression_pre", keys)
        self.assertNotIn("sync_reported_progression_post", keys)
        self.assertLess(keys.index("sync_performance_details"), keys.index("build_athlete_state"))
        self.assertLess(keys.index("weekly_review"), keys.index("build_athlete_state"))
        self.assertLess(keys.index("build_athlete_state"), keys.index("adaptive_planning"))
        self.assertLess(keys.index("adaptive_planning"), keys.index("rollover_calendar"))
        self.assertLess(keys.index("rollover_calendar"), keys.index("apply_plan_overrides"))
        self.assertLess(keys.index("apply_plan_overrides"), keys.index("validate_rollover"))
        self.assertLess(keys.index("rollover_calendar"), keys.index("sync_weather"))
        self.assertLess(keys.index("coach_analysis"), keys.index("materialize_device_workouts"))
        self.assertLess(keys.index("materialize_device_workouts"), keys.index("validate_device_workouts"))
        self.assertLess(keys.index("validate_device_workouts"), keys.index("sync_device_workouts"))
        self.assertLess(keys.index("sync_device_workouts"), keys.index("guard_coach_claims"))
        self.assertEqual(keys[-1], "render_and_validate_site")

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
