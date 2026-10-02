#!/usr/bin/env python3
"""Read canonical current planned workouts for Planning Engine v1 pre-window load context."""

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


def load_canonical_current_planned_workouts(
    coverage_from: date,
    coverage_through: date,
    *,
    env: dict[str, str] | None = None,
    connect_fn: Callable[..., Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(coverage_from, date) or not isinstance(coverage_through, date):
        raise RuntimeError("planned-workout coverage bounds must be dates")
    if coverage_through < coverage_from:
        raise RuntimeError("planned-workout coverage_through cannot precede coverage_from")

    if connect_fn is None:
        try:
            import psycopg  # type: ignore
        except Exception as exc:
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
                  workout_key,
                  scheduled_date,
                  planning_status,
                  manual_lock,
                  payload,
                  last_seen_source_hash
                from training.planned_workouts
                where is_current
                  and scheduled_date >= %s
                  and scheduled_date <= %s
                order by scheduled_date, workout_key
                """,
                (coverage_from, coverage_through),
            )
            fetched = cur.fetchall()
            conn.rollback()

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in fetched:
        workout_key = str(raw[0] or "").strip()
        if not workout_key or workout_key in seen:
            raise RuntimeError(
                "canonical planned-workout source contains missing/duplicate workout_key"
            )
        seen.add(workout_key)

        local_day = raw[1]
        if isinstance(local_day, date):
            local_date = local_day.isoformat()
        else:
            local_date = str(local_day or "").strip()
            date.fromisoformat(local_date)

        payload = raw[4]
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"canonical planned workout {workout_key} lacks object payload"
            )
        payload_date = str(payload.get("date") or "").strip()
        if payload_date and payload_date != local_date:
            raise RuntimeError(
                f"canonical planned workout {workout_key} date disagrees with payload"
            )

        rows.append(
            {
                "workout_key": workout_key,
                "date": local_date,
                "planning_status": (
                    None if raw[2] is None else str(raw[2]).strip() or None
                ),
                "manual_lock": bool(raw[3]),
                "payload": payload,
                "last_seen_source_hash": (
                    None if raw[5] is None else str(raw[5]).strip() or None
                ),
            }
        )

    return rows, {
        "source": "supabase_db",
        "verified": True,
        "coverage_from": coverage_from.isoformat(),
        "coverage_through": coverage_through.isoformat(),
        "current_planned_workout_count": len(rows),
    }
