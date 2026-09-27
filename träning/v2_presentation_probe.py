#!/usr/bin/env python3
"""Read-only v2 semantic probe against canonical PostgreSQL.

This is intentionally not a renderer cutover. It proves that the new core can
construct the current Today snapshot directly from canonical relational state.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from training_core.application.presentation import build_presentation_snapshot
from training_core.presentation.parity import semantic_snapshot
from training_core.presentation.renderer import render_document, render_snapshot
from training_core.repositories.archive import ManifestWeekArchiveRepository
from training_core.repositories.context import PostgresPlanningContextRepository
from training_core.repositories.icons import FileSportIconRepository
from training_core.repositories.presentation import PostgresPresentationRepository
from training_core.repositories.weather import FileWeatherRepository


ROOT = Path(__file__).resolve().parent


def build_snapshot(today: date):
    repository = PostgresPresentationRepository.from_environment()
    archive_repository = ManifestWeekArchiveRepository(
        ROOT / "data" / "weeks" / "index.json"
    )
    weather_repository = FileWeatherRepository(ROOT / "data" / "weather.json")
    context_repository = PostgresPlanningContextRepository.from_environment()
    icon_repository = FileSportIconRepository(ROOT / "data" / "sport_icons.json")
    snapshot = build_presentation_snapshot(
        repository,
        today=today,
        archive_repository=archive_repository,
        weather_repository=weather_repository,
        context_repository=context_repository,
        icon_repository=icon_repository,
    )
    return snapshot


def snapshot_payload(today: date) -> dict:
    snapshot = build_snapshot(today)
    return {
        "semantics": semantic_snapshot(snapshot),
        "html": render_snapshot(snapshot),
        "document": render_document(snapshot),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    payload = snapshot_payload(args.date)
    output = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    print(output)
    output_path = str(os.environ.get("V2_PROBE_OUTPUT") or "").strip()
    if output_path:
        Path(output_path).write_text(output + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
