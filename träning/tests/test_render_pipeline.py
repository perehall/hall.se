#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from render_training_site import main  # noqa: E402

REPO_ROOT = SCRIPTS.parents[1]


EXPECTED_PIPELINE = (
    "apply_plan_overrides.py",
    "enforce_coach_output_contract.py",
    "normalize_coach_language.py",
    "finalize_canonical_coach_facts.py",
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
    "finalize_relative_next_ui.py",
    "finalize_progression_ui.py",
    "finalize_sport_icons.py",
    "finalize_day_session_icons.py",
    "finalize_workout_history.py",
    "finalize_signal_ui.py",
    "finalize_device_sync_ui.py",
    "finalize_historical_coach_ui.py",
    "finalize_week_activity_insights.py",
    "finalize_user_report_ui.py",
    "finalize_week_status_ui.py",
    "finalize_post_workout_ui.py",
    "finalize_training_input_ui.py",
    "finalize_human_training_language.py",
    "finalize_completed_workout_truth.py",
    "finalize_completed_sport_icon.py",
    "finalize_coach_clarity_ui.py",
    "finalize_card_v2_ui.py",
    "build_home.py",
    "finalize_goal_link_layout.py",
    "publish_goal_cache_bypass.py",
    "finalize_week_shell_ui.py",
    "finalize_backend_status_ui.py",
    "finalize_quiet_performance_ui.py",
    "finalize_quiet_performance_v2_ui.py",
    "finalize_upcoming_workout_shell_ui.py",
    "finalize_completed_day_summary_ui.py",
    "finalize_top_overview_ui.py",
    "finalize_rest_day_language.py",
    "finalize_training_timeline_ui.py",
    "finalize_week_navigation_ui.py",
    "finalize_week_page_consistency_ui.py",
    "finalize_all_week_pass_icons.py",
    "finalize_generated_whitespace.py",
    "check_week_reviews.py",
    "check_week_review_ui.py",
    "validate_site_contracts.py",
    "validate_training_data.py",
)


class RenderPipelineTests(unittest.TestCase):
    def test_production_entrypoint_contains_no_legacy_renderer_fallback(self):
        source = (SCRIPTS / "render_training_site.py").read_text(encoding="utf-8")
        self.assertNotIn("LEGACY_PARITY_PIPELINE", source)
        self.assertNotIn("run_legacy_parity_pipeline", source)
        self.assertNotIn("publish_v2_preview", source)
        self.assertIn("publish_v2_current_page()", source)
        self.assertIn("publish_v2_upcoming_page()", source)

    def test_production_main_publishes_current_and_upcoming_v2(self):
        import render_training_site

        original_current = render_training_site.publish_v2_current_page
        original_upcoming = render_training_site.publish_v2_upcoming_page
        calls = []
        try:
            render_training_site.publish_v2_current_page = lambda: calls.append("current")
            render_training_site.publish_v2_upcoming_page = lambda: calls.append("upcoming")
            self.assertEqual(main(), 0)
        finally:
            render_training_site.publish_v2_current_page = original_current
            render_training_site.publish_v2_upcoming_page = original_upcoming
        self.assertEqual(calls, ["current", "upcoming"])

    def test_production_renderer_uses_stockholm_calendar_date(self):
        source = (SCRIPTS / "render_training_site.py").read_text(encoding="utf-8")
        self.assertIn('ZoneInfo("Europe/Stockholm")', source)
        self.assertNotIn("date.today()", source)

    def test_pages_deploy_defers_stale_goal_state_without_failure(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Check generated planning freshness", workflow)
        self.assertIn("planning_goal_hash", workflow)
        self.assertIn("Deployment deferred", workflow)
        self.assertIn(
            "if: steps.planning_freshness.outputs.stale != 'true'",
            workflow,
        )
        self.assertIn(
            "if: steps.planning_freshness.outputs.stale == 'true'",
            workflow,
        )

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
        self.assertIn("SUPABASE_PUBLISHABLE_KEY: ${{ vars.SUPABASE_PUBLISHABLE_KEY }}", workflow)


if __name__ == "__main__":
    unittest.main()