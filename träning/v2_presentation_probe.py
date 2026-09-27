#!/usr/bin/env python3
"""Read-only v2 semantic probe against canonical PostgreSQL.

This is intentionally not a renderer cutover. It proves that the new core can
construct the current Today snapshot directly from canonical relational state.
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from training_core.application.presentation import build_presentation_snapshot
from training_core.presentation.renderer import render_today
from training_core.repositories.presentation import PostgresPresentationRepository


def snapshot_payload(today: date) -> dict:
    repository = PostgresPresentationRepository.from_environment()
    snapshot = build_presentation_snapshot(repository, today=today)
    model = snapshot.today
    return {
        "date": model.local_date.isoformat(),
        "state": model.state,
        "title": model.title,
        "details": list(model.details),
        "planned_session": model.planned_session,
        "next_session": model.next_session,
        "html": render_today(snapshot),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    print(json.dumps(snapshot_payload(args.date), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
