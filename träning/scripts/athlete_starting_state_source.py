#!/usr/bin/env python3
"""Read immutable athlete starting-state snapshots for planning.

Starting state is onboarding baseline information. It is deliberately separate
from continuously observed athlete_state and from profile preferences. During
an explicit plan build the snapshot attached to the generation request is the
only allowed starting-state source.
"""
from __future__ import annotations

import os
from typing import Any, Callable


def _read_starting_state(
    database_url: str,
    *,
    generation_request_id: str | None = None,
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
            if generation_request_id:
                cur.execute(
                    """
                    select starting_state_snapshot, starting_state_revision, requested_at
                    from training.plan_generation_requests
                    where id = %s::uuid
                    limit 1
                    """,
                    (generation_request_id,),
                )
            else:
                cur.execute(
                    """
                    select s.active_state, s.active_revision, s.activated_at
                    from training.athlete_starting_states s
                    join training.athlete_profiles p
                      on p.athlete_subject = s.athlete_subject
                    where p.is_planning_default
                      and s.active_state is not null
                    limit 1
                    """
                )
            row = cur.fetchone()
            conn.rollback()
    if row is None:
        return None, None, None
    return row[0], row[1], row[2]


def load_starting_state_for_planner(
    *,
    generation_request_id: str | None = None,
    db_connect: Callable[..., Any] | None = None,
    env: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    environment = env if env is not None else os.environ
    database_url = str(environment.get("SUPABASE_DB_URL") or "").strip()
    if not database_url:
        return None, {"source": "none", "verified": False, "reason": "database_url_missing"}

    try:
        payload, revision, updated_at = _read_starting_state(
            database_url,
            generation_request_id=generation_request_id,
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
            "reason": (
                "generation_request_starting_state_missing"
                if generation_request_id
                else "active_starting_state_missing"
            ),
        }
    if payload.get("schema_version") != 1 or payload.get("status") != "confirmed":
        return None, {
            "source": "supabase_db",
            "verified": False,
            "reason": "invalid_starting_state_contract",
        }

    return payload, {
        "source": "supabase_db",
        "verified": True,
        "reason": (
            "generation_request_starting_state_snapshot"
            if generation_request_id
            else "active_starting_state"
        ),
        "revision": revision,
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else updated_at,
    }


def planner_starting_state_view(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not state:
        return None
    return {
        "source_mode": state.get("source_mode"),
        "observed_snapshot": state.get("observed_snapshot"),
        "manual_state": state.get("manual_state") or {},
        "confirmation": state.get("confirmation") or {},
    }
