#!/usr/bin/env python3
"""Publish the multi-week training overview from canonical current state + immutable history."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from development_roadmap import build_development_roadmap
from training_core.domain.workouts import PlannedWorkout
from training_core.presentation.overview import build_training_overview
from training_core.presentation.overview_renderer import render_overview_document
from training_core.presentation.today import CompletedActivity
from training_core.repositories.archive import ManifestWeekArchiveRepository
from training_core.repositories.icons import FileSportIconRepository
from training_core.repositories.presentation import PostgresPresentationRepository
from training_core.repositories.weather import FileWeatherRepository


DATA = ROOT / "data"
TARGET = ROOT / "oversikt" / "index.html"
VISIBLE_WEEKS_BEFORE = 2
VISIBLE_WEEKS_AFTER = 5


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _week_key(week_start: date) -> str:
    year, week, _ = week_start.isocalendar()
    return f"{year}-W{week:02d}"


def _roadmap() -> dict:
    strategy = _load_json(DATA / "training_strategy.json")
    policy = _load_json(DATA / "planning_policy.json")
    athlete_state = _load_json(DATA / "athlete_state.json")
    roadmap = strategy.get("development_roadmap")
    goal_hash = (strategy.get("goal_contract") or {}).get("goal_hash")
    if not isinstance(roadmap, dict) or roadmap.get("goal_basis_hash") != goal_hash:
        roadmap = build_development_roadmap(strategy, policy, athlete_state)
    return roadmap


def _archived_plan_rows(archive_repository, start: date, end: date) -> list[PlannedWorkout]:
    rows: list[PlannedWorkout] = []
    cursor = start
    while cursor <= end:
        key = _week_key(cursor)
        try:
            archived = archive_repository.archived_week(key)
        except KeyError:
            cursor += timedelta(days=7)
            continue
        for index, item in enumerate(archived.plan_days):
            payload = dict(item.payload or {})
            sport = str(payload.get("sport") or "").strip()
            rows.append(
                PlannedWorkout(
                    local_date=item.local_date,
                    session=item.session,
                    sport=sport,
                    status=item.status,
                    planning_status=item.planning_status,
                    manual_lock=item.manual_lock,
                    reason=item.reason,
                    development_focus=item.development_focus,
                    payload=payload,
                    workout_key=str(
                        payload.get("workout_key")
                        or f"{key}:{item.local_date.isoformat()}:{index + 1}"
                    ),
                )
            )
        cursor += timedelta(days=7)
    return rows


def _archived_activities(archive_repository, start: date, end: date) -> list[CompletedActivity]:
    rows: list[CompletedActivity] = []
    cursor = start
    while cursor <= end:
        key = _week_key(cursor)
        try:
            archived = archive_repository.archived_week(key)
        except KeyError:
            cursor += timedelta(days=7)
            continue
        for item in archived.activities:
            if str(item.classification or "training").strip().lower() == "recreation":
                continue
            rows.append(
                CompletedActivity(
                    provider_activity_id=item.provider_activity_id,
                    local_date=item.local_date,
                    label=item.label,
                    sport_family=item.sport_type,
                    elapsed_time_s=item.elapsed_time_s,
                    distance_m=item.distance_m,
                    average_heartrate=item.average_heartrate,
                    max_heartrate=item.max_heartrate,
                )
            )
        cursor += timedelta(days=7)
    return rows


def build_overview(local_date: date):
    current_week_start = local_date - timedelta(days=local_date.weekday())
    start = current_week_start - timedelta(weeks=VISIBLE_WEEKS_BEFORE)
    end = current_week_start + timedelta(weeks=VISIBLE_WEEKS_AFTER, days=6)

    current_repository = PostgresPresentationRepository.from_environment()
    archive_repository = ManifestWeekArchiveRepository(DATA / "weeks" / "index.json")
    weather_snapshot = FileWeatherRepository(DATA / "weather.json").current()

    historical_end = current_week_start - timedelta(days=1)
    historical_plan = _archived_plan_rows(archive_repository, start, historical_end)
    historical_activities = _archived_activities(archive_repository, start, historical_end)

    current_plan = current_repository.planned_days(current_week_start, end)
    current_activities = current_repository.completed_activities(current_week_start, end)

    model = build_training_overview(
        start=start,
        end=end,
        current_date=local_date,
        plan=tuple(historical_plan) + tuple(current_plan),
        activities=tuple(historical_activities) + tuple(current_activities),
        roadmap=_roadmap(),
        weather_snapshot=weather_snapshot,
    )
    icons = FileSportIconRepository(DATA / "sport_icons.json").current()
    return model, icons


def publish_overview_page(local_date: date | None = None):
    local_date = local_date or datetime.now(ZoneInfo("Europe/Stockholm")).date()
    model, icons = build_overview(local_date)
    document = render_overview_document(
        model,
        current_date=local_date,
        sport_icons=icons,
    )
    required = (
        "<!doctype html>",
        'class="overview-shell"',
        'class="overview-planbar"',
        'class="overview-calendar"',
        'class="overview-status-chip',
        'id="overview-detail"',
        "Granska plan",
        "/träning/oversikt/",
    )
    missing = [marker for marker in required if marker not in document]
    if missing:
        raise RuntimeError(
            "Training overview missing required structure: " + ", ".join(missing)
        )

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(document, encoding="utf-8")
    print(
        f"TRAINING_OVERVIEW_OK {TARGET.relative_to(ROOT)} "
        f"weeks={len(model.weeks)} date={local_date.isoformat()}",
        flush=True,
    )
    return TARGET


if __name__ == "__main__":
    publish_overview_page()
