#!/usr/bin/env python3
"""Canonical execution pipeline for the training automation.

GitHub Actions selects the ingest source; this runner owns stage order,
required/optional semantics and private-file cleanup. Keeping those rules in
one place prevents webhook, scheduled and manual runs from drifting apart.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TRAINING_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TRAINING_ROOT.parent
SCRIPTS = TRAINING_ROOT / "scripts"


@dataclass(frozen=True)
class Stage:
    key: str
    command: tuple[str, ...]
    optional: bool = False
    stdin_file_env: str | None = None
    remove_stdin_on_success: bool = False


def python_stage(script: str, *args: str) -> tuple[str, ...]:
    return (sys.executable, str(SCRIPTS / script), *args)


def build_stages(ingest_mode: str) -> list[Stage]:
    if ingest_mode not in {"event", "reconcile"}:
        raise ValueError(f"Unsupported ingest mode: {ingest_mode}")

    ingest = (
        Stage("strava_event", python_stage("sync_strava_event.py"))
        if ingest_mode == "event"
        else Stage("strava_reconcile", python_stage("sync_strava.py"))
    )

    repository = os.environ.get("GITHUB_REPOSITORY", "")
    persist_token = Stage(
        "persist_strava_refresh_token",
        ("gh", "secret", "set", "STRAVA_REFRESH_TOKEN", "--repo", repository),
        stdin_file_env="STRAVA_REFRESH_TOKEN_FILE",
        remove_stdin_on_success=True,
    )

    return [
        Stage("sync_reported_progression_pre", python_stage("sync_user_reported_progression.py")),
        ingest,
        Stage("normalize_activity_semantics", python_stage("normalize_activity_semantics.py")),
        Stage("sync_reported_progression_post", python_stage("sync_user_reported_progression.py")),
        Stage("migrate_typed_plan", python_stage("migrate_training_data_v3.py")),
        Stage("validate_normalized_data", python_stage("validate_training_data.py")),
        Stage("rollover_calendar", python_stage("rollover_week.py")),
        Stage("apply_plan_overrides", python_stage("apply_plan_overrides.py")),
        Stage("validate_rollover", python_stage("validate_training_data.py")),
        Stage("materialize_workout_designs", python_stage("materialize_workout_designs.py")),
        Stage("validate_workout_designs", python_stage("validate_workout_designs.py")),
        persist_token,
        Stage("sync_weather", python_stage("sync_weather.py")),
        Stage(
            "sync_performance_details",
            python_stage("sync_performance_details.py", "--days", "60"),
            optional=True,
        ),
        Stage("validate_performance_data", python_stage("validate_training_data.py")),
        Stage(
            "load_wellness_context",
            python_stage("wellness_context.py", "--days", "28"),
            optional=True,
        ),
        Stage("coach_analysis", python_stage("coach_pipeline.py")),
        Stage("materialize_workout_designs_post_coach", python_stage("materialize_workout_designs.py")),
        Stage("validate_workout_designs_post_coach", python_stage("validate_workout_designs.py")),
        Stage("materialize_device_workouts", python_stage("materialize_device_workouts.py")),
        Stage("validate_device_workouts", python_stage("validate_device_workouts.py")),
        Stage(
            "sync_device_workouts",
            python_stage("sync_intervals_workouts.py"),
            optional=True,
        ),
        Stage("guard_coach_claims", python_stage("coach_output_guard.py")),
        Stage("validate_post_coach", python_stage("validate_training_data.py")),
        Stage("weekly_review", python_stage("weekly_review.py")),
        Stage("validate_week_reviews", python_stage("check_week_reviews.py")),
        Stage("render_and_validate_site", python_stage("render_training_site.py")),
    ]


def _stdin_file(stage: Stage):
    if not stage.stdin_file_env:
        return None, None
    raw_path = os.environ.get(stage.stdin_file_env, "")
    if not raw_path:
        raise RuntimeError(f"{stage.key}: environment variable {stage.stdin_file_env} is missing")
    path = Path(raw_path)
    if not path.is_file():
        raise RuntimeError(f"{stage.key}: expected input file was not produced")
    return path, path.open("rb")


def run_stage(stage: Stage, position: int, total: int) -> bool:
    print(f"JOB_STAGE_START {position}/{total} {stage.key}", flush=True)

    if stage.key == "persist_strava_refresh_token" and not os.environ.get("GITHUB_REPOSITORY"):
        raise RuntimeError("persist_strava_refresh_token: GITHUB_REPOSITORY is missing")

    input_path = None
    input_handle = None
    try:
        input_path, input_handle = _stdin_file(stage)
        result = subprocess.run(
            list(stage.command),
            cwd=REPO_ROOT,
            stdin=input_handle,
            check=False,
        )
    finally:
        if input_handle is not None:
            input_handle.close()

    if result.returncode == 0:
        if stage.remove_stdin_on_success and input_path is not None:
            input_path.unlink(missing_ok=True)
        print(f"JOB_STAGE_OK {position}/{total} {stage.key}", flush=True)
        return True

    if stage.optional:
        print(
            f"JOB_STAGE_OPTIONAL_FAILURE {position}/{total} {stage.key} exit={result.returncode}",
            file=sys.stderr,
            flush=True,
        )
        return False

    raise RuntimeError(f"{stage.key} failed with exit code {result.returncode}")


def cleanup_private_context() -> None:
    raw_path = os.environ.get("WELLNESS_CONTEXT_FILE", "/tmp/training_wellness_context.json")
    if raw_path:
        Path(raw_path).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ingest-mode", choices=("event", "reconcile"), required=True)
    args = parser.parse_args(argv)

    stages = build_stages(args.ingest_mode)
    optional_failures: list[str] = []
    try:
        for position, stage in enumerate(stages, start=1):
            if not run_stage(stage, position, len(stages)):
                optional_failures.append(stage.key)
    except (OSError, RuntimeError) as exc:
        print(f"JOB_PIPELINE_FAILED {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        cleanup_private_context()

    if optional_failures:
        print("JOB_PIPELINE_OK optional_failures=" + ",".join(optional_failures), flush=True)
    else:
        print("JOB_PIPELINE_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
