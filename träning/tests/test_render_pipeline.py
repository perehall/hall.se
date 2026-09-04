#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from render_training_site import PIPELINE, REPO_ROOT, run_pipeline  # noqa: E402


EXPECTED_PIPELINE = (
    "normalize_coach_language.py",
    "build.py",
    "finalize_dashboard.py",
    "finalize_dashboard_ui.py",
    "finalize_activity_labels.py",
    "finalize_yoda_ui.py",
    "archive_weeks.py",
    "finalize_week_review_ui.py",
    "build_upcoming_week.py",
    "finalize_header_ui.py",
    "finalize_navigation_ui.py",
    "finalize_training_brain_ui.py",
    "finalize_progression_ui.py",
    "finalize_sport_icons.py",
    "finalize_day_session_icons.py",
    "finalize_workout_history.py",
    "finalize_signal_ui.py",
    "finalize_historical_coach_ui.py",
    "finalize_week_activity_insights.py",
    "finalize_week_status_ui.py",
    "finalize_post_workout_ui.py",
    "finalize_human_training_language.py",
    "finalize_completed_workout_truth.py",
    "build_home.py",
    "finalize_goal_link_layout.py",
    "publish_goal_cache_bypass.py",
    "finalize_generated_whitespace.py",
    "finalize_week_shell_ui.py",
    "check_week_reviews.py",
    "check_week_review_ui.py",
    "validate_site_contracts.py",
    "validate_training_data.py",
)


class RenderPipelineTests(unittest.TestCase):
    def test_pipeline_order_is_single_explicit_contract(self):
        self.assertEqual(PIPELINE, EXPECTED_PIPELINE)
        self.assertEqual(len(PIPELINE), len(set(PIPELINE)))
        self.assertEqual(PIPELINE[-2:], ("validate_site_contracts.py", "validate_training_data.py"))
        self.assertLess(PIPELINE.index("normalize_coach_language.py"), PIPELINE.index("build.py"))
        self.assertLess(PIPELINE.index("archive_weeks.py"), PIPELINE.index("finalize_week_review_ui.py"))
        self.assertLess(PIPELINE.index("finalize_week_review_ui.py"), PIPELINE.index("check_week_review_ui.py"))
        self.assertLess(PIPELINE.index("finalize_navigation_ui.py"), PIPELINE.index("finalize_training_brain_ui.py"))
        self.assertLess(PIPELINE.index("finalize_training_brain_ui.py"), PIPELINE.index("finalize_progression_ui.py"))
        self.assertLess(PIPELINE.index("finalize_workout_history.py"), PIPELINE.index("finalize_signal_ui.py"))
        self.assertLess(PIPELINE.index("finalize_signal_ui.py"), PIPELINE.index("finalize_historical_coach_ui.py"))
        self.assertLess(PIPELINE.index("finalize_historical_coach_ui.py"), PIPELINE.index("finalize_week_activity_insights.py"))
        self.assertLess(PIPELINE.index("finalize_week_activity_insights.py"), PIPELINE.index("finalize_week_status_ui.py"))
        self.assertLess(PIPELINE.index("finalize_week_status_ui.py"), PIPELINE.index("finalize_post_workout_ui.py"))
        self.assertLess(PIPELINE.index("finalize_post_workout_ui.py"), PIPELINE.index("finalize_human_training_language.py"))
        self.assertLess(PIPELINE.index("finalize_human_training_language.py"), PIPELINE.index("finalize_completed_workout_truth.py"))
        self.assertLess(PIPELINE.index("finalize_completed_workout_truth.py"), PIPELINE.index("build_home.py"))
        self.assertLess(PIPELINE.index("publish_goal_cache_bypass.py"), PIPELINE.index("finalize_generated_whitespace.py"))
        self.assertLess(PIPELINE.index("finalize_generated_whitespace.py"), PIPELINE.index("finalize_week_shell_ui.py"))
        self.assertLess(PIPELINE.index("finalize_week_shell_ui.py"), PIPELINE.index("validate_site_contracts.py"))

    def test_runner_executes_every_stage_in_canonical_order(self):
        calls = []

        def fake_runner(command, *, check, cwd):
            calls.append((Path(command[1]).name, check, cwd))

        run_pipeline(runner=fake_runner)
        self.assertEqual([name for name, _, _ in calls], list(EXPECTED_PIPELINE))
        self.assertTrue(all(check is True for _, check, _ in calls))
        self.assertTrue(all(cwd == REPO_ROOT for _, _, cwd in calls))

    def test_pages_deploy_builds_and_validates_before_upload(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(
            encoding="utf-8"
        )
        render = 'python "träning/scripts/render_training_site.py"'
        upload = "uses: actions/upload-pages-artifact@v4"
        deploy = "uses: actions/deploy-pages@v4"
        self.assertIn(render, workflow)
        self.assertIn(upload, workflow)
        self.assertIn(deploy, workflow)
        self.assertLess(workflow.index(render), workflow.index(upload))
        self.assertLess(workflow.index(upload), workflow.index(deploy))


if __name__ == "__main__":
    unittest.main()
