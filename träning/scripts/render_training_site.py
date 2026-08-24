#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent

# Canonical deterministic rendering order. CI and production must call this
# same pipeline instead of maintaining separate lists of finalizers.
PIPELINE = (
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


def run_pipeline(*, runner=None):
    runner = runner or subprocess.run
    for index, script_name in enumerate(PIPELINE, start=1):
        script = ROOT / "scripts" / script_name
        if not script.exists():
            raise RuntimeError(f"Render pipeline: script saknas: {script_name}")
        print(f"PIPELINE_STAGE_START {index}/{len(PIPELINE)} {script_name}", flush=True)
        runner([sys.executable, str(script)], check=True, cwd=REPO_ROOT)
        print(f"PIPELINE_STAGE_OK {index}/{len(PIPELINE)} {script_name}", flush=True)
    print(f"Render pipeline OK: {len(PIPELINE)} deterministiska steg.")


def main():
    run_pipeline()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
