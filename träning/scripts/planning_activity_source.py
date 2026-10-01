#!/usr/bin/env python3
"""Read canonical training activities for Planning Engine v1 shadow history.

This source is read-only by construction. It returns the current relational
activity roster for an explicit local-date interval and does not read any
planner output.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Callable


def _database_url(env: dict[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    value = str(source.get("SUPABASE_DB_URL") or "").strip()
    if not value:
        raise RuntimeError("SUPABASE_DB_URL is missing")
    return value


def load_canonical_training_activities(
    coverage_from: date,
    coverage_through: date,
    *,
    env: dict[str, str] | None = None,
    connect_fn: Callable[..., Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(coverage_from, date) or not isinstance(coverage_through, date):
        raise RuntimeError("activity coverage bounds must be dates")
    if coverage_through < coverage_from:
        raise RuntimeError("activity coverage_through cannot precede coverage_from")

    if connect_fn is None:
        try:
            import psycopg  # type: ignore
        except Exception as exc:  # pragma: no cover - exercised in live workflow
            raise RuntimeError("psycopg is unavailable") from exc
        connect_fn = psycopg.connect

    with connect_fn(
        _database_url(env),
        sslmode="require",
        connect_timeout=15,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("set transaction read only")
            cur.execute(
                """
                select
                  provider_activity_id,
                  local_date,
                  sport_family,
                  classification,
                  elapsed_time_s,
                  distance_m
                from training.activities
                where is_current
                  and local_date >= %s
                  and local_date <= %s
                  and classification = 'training'
                order by local_date, started_at, provider_activity_id
                """,
                (coverage_from, coverage_through),
            )
            fetched = cur.fetchall()
            conn.rollback()

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in fetched:
        source_id = str(raw[0] or "").strip()
        if not source_id or source_id in seen:
            raise RuntimeError(
                "canonical activity source contains missing/duplicate provider id"
            )
        seen.add(source_id)
        local_day = raw[1]
        if isinstance(local_day, date):
            local_date = local_day.isoformat()
        else:
            local_date = str(local_day or "").strip()
            date.fromisoformat(local_date)
        elapsed = raw[4]
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or float(elapsed) < 0
        ):
            raise RuntimeError(
                f"canonical training activity {source_id} lacks valid elapsed_time_s"
            )
        distance = raw[5]
        if distance is not None and (
            isinstance(distance, bool)
            or not isinstance(distance, (int, float))
            or float(distance) < 0
        ):
            raise RuntimeError(
                f"canonical training activity {source_id} has invalid distance_m"
            )
        rows.append(
            {
                "id": source_id,
                "date": local_date,
                "sport_family": str(raw[2] or "").strip(),
                "classification": "training",
                "elapsed_time_s": float(elapsed),
                "distance_m": (
                    None if distance is None else float(distance)
                ),
            }
        )

    return rows, {
        "source": "supabase_db",
        "verified": True,
        "coverage_from": coverage_from.isoformat(),
        "coverage_through": coverage_through.isoformat(),
        "training_activity_count": len(rows),
    }
