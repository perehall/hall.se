#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from render_training_site import PIPELINE, REPO_ROOT, run_pipeline  # noqa: E402


EXPECTED_PIPELINE = (
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
    "finalize_progression_ui.py",
    "finalize_sport_icons.py",
    "finalize_day_session_icons.py",
    "finalize_workout_history.py",
    "build_home.py",
    "finalize_goal_link_layout.py",
    "publish_goal_cache_bypass.py",
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
        self.assertLess(PIPELINE.index("archive_weeks.py"), PIPELINE.index("finalize_week_review_ui.py"))
        self.assertLess(PIPELINE.index("finalize_week_review_ui.py"), PIPELINE.index("check_week_review_ui.py"))
        self.assertLess(PIPELINE.index("finalize_navigation_ui.py"), PIPELINE.index("finalize_progression_ui.py"))

    def test_runner_executes_every_stage_in_canonical_order(self):
        calls = []

        def fake_runner(command, *, check, cwd):
            calls.append((Path(command[1]).name, check, cwd))

        run_pipeline(runner=fake_runner)
        self.assertEqual([name for name, _, _ in calls], list(EXPECTED_PIPELINE))
        self.assertTrue(all(check is True for _, check, _ in calls))
        self.assertTrue(all(cwd == REPO_ROOT for _, _, cwd in calls))


if __name__ == "__main__":
    unittest.main()
