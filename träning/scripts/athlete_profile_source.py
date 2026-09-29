#!/usr/bin/env python3
"""Read the declared athlete profile for planning.

The profile contains user-declared goals, availability and preferences. It is
separate from athlete_state, which contains observed training facts. Missing
profile data never gets invented here.
"""
from __future__ import annotations

import os
from typing import Any, Callable


def _read_from_database(
    database_url: str,
    *,
    connect_fn: Callable[..., Any] | None = None,
) -> tuple[Any, Any, Any]:
    if connect_fn is None:
        import psycopg  # type: ignore
        connect_fn = psycopg.connect

    with connect_fn(
        database_url,
        sslmode="require",
        connect_timeout=5,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("set transaction read only")
            cur.execute(
                """
                select profile, revision, updated_at
                from training.athlete_profiles
                where is_planning_default
                  and status = 'complete'
                limit 1
                """
            )
            row = cur.fetchone()
            conn.rollback()
    if row is None:
        return None, None, None
    return row[0], row[1], row[2]


def load_athlete_profile_for_planner(
    *,
    db_connect: Callable[..., Any] | None = None,
    env: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    environment = env if env is not None else os.environ
    database_url = str(environment.get("SUPABASE_DB_URL") or "").strip()
    if not database_url:
        return None, {
            "source": "none",
            "verified": False,
            "reason": "database_url_missing",
        }

    try:
        payload, revision, updated_at = _read_from_database(
            database_url,
            connect_fn=db_connect,
        )
    except Exception as exc:
        return None, {
            "source": "none",
            "verified": False,
            "reason": f"database_unavailable:{type(exc).__name__}",
        }

    if not isinstance(payload, dict) or not payload:
        return None, {
            "source": "supabase_db",
            "verified": True,
            "reason": "complete_profile_missing",
        }
    if payload.get("schema_version") != 1 or payload.get("status") != "complete":
        return None, {
            "source": "supabase_db",
            "verified": False,
            "reason": "invalid_profile_contract",
        }

    return payload, {
        "source": "supabase_db",
        "verified": True,
        "reason": "complete_profile",
        "revision": revision,
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else updated_at,
    }


def planner_profile_view(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return only declared planning inputs; never mix observed capacity into it."""
    if not profile:
        return None
    return {
        "goals": list(profile.get("goals") or []),
        "availability": dict(profile.get("availability") or {}),
        "preferences": dict(profile.get("preferences") or {}),
        "constraints": dict(profile.get("constraints") or {}),
        "coach_autonomy": profile.get("coach_autonomy"),
    }
