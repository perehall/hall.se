#!/usr/bin/env python3
"""Verified Supabase read path for the planner goal portfolio.

The planner prefers a direct read-only PostgreSQL connection using the existing
SUPABASE_DB_URL secret. A public RPC is retained only as a secondary read path
when a publishable key is configured. Supabase may influence planning only when
its persisted goal document exactly matches the repository fallback hash.

During this migration stage data/goal.json remains the write authority and
freshness oracle. Backend/configuration failures are non-blocking and fall back
to that file.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

PROJECT_URL = "https://izzevnhgtsvffpkccoai.supabase.co"
RPC_PATH = "/rest/v1/rpc/training_goal_document"


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _local_goal(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Planner goal fallback saknas: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not value:
        raise RuntimeError("Planner goal fallback är tom eller ogiltig")
    return value


def _fallback(
    local: dict[str, Any],
    *,
    expected_hash: str,
    reason: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return local, {
        "source": "json_fallback",
        "verified": False,
        "reason": reason,
        "source_hash": expected_hash,
    }


def _validated_backend_document(
    local: dict[str, Any],
    *,
    expected_hash: str,
    payload: Any,
    declared_hash: Any,
    source: str,
    updated_at: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if not isinstance(payload, dict) or not payload:
        return None

    declared = str(declared_hash or "")
    persisted_hash = canonical_hash(payload)
    if declared != expected_hash or persisted_hash != expected_hash:
        return None

    return payload, {
        "source": source,
        "verified": True,
        "reason": "hash_match",
        "source_hash": expected_hash,
        "backend_updated_at": (
            updated_at.isoformat()
            if hasattr(updated_at, "isoformat")
            else updated_at
        ),
    }


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
                select source_hash, payload, updated_at
                from training.state_documents
                where document_key = 'goal'
                limit 1
                """
            )
            row = cur.fetchone()
            if row is None:
                return None, None, None
            return row[1], row[0], row[2]


def _read_from_rpc(
    publishable_key: str,
    project_url: str,
    *,
    opener: Callable[..., Any] | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    request = urllib.request.Request(
        project_url.rstrip("/") + RPC_PATH,
        data=b"{}",
        headers={
            "apikey": publishable_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    open_request = opener or urllib.request.urlopen
    with open_request(request, timeout=timeout) as response:
        remote = json.load(response)
    if not isinstance(remote, dict):
        raise ValueError("Supabase goal RPC returned non-object JSON")
    return remote


def load_goal_for_planner(
    path: Path,
    *,
    opener: Callable[..., Any] | None = None,
    db_connect: Callable[..., Any] | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 5.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load a verified backend goal or fall back safely to data/goal.json."""

    local = _local_goal(path)
    expected_hash = canonical_hash(local)
    environment = env if env is not None else os.environ

    database_url = str(environment.get("SUPABASE_DB_URL") or "").strip()
    if database_url:
        try:
            payload, declared_hash, updated_at = _read_from_database(
                database_url,
                connect_fn=db_connect,
            )
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            database_reason = f"database_unavailable:{type(exc).__name__}"
        except Exception as exc:
            # psycopg exposes several driver-specific Operational/Interface
            # errors. The type is useful for diagnostics; the exception text is
            # intentionally not persisted because it may contain connection
            # details.
            database_reason = f"database_unavailable:{type(exc).__name__}"
        else:
            if payload is None:
                return _fallback(
                    local,
                    expected_hash=expected_hash,
                    reason="database_goal_missing",
                )
            verified = _validated_backend_document(
                local,
                expected_hash=expected_hash,
                payload=payload,
                declared_hash=declared_hash,
                source="supabase_db",
                updated_at=updated_at,
            )
            if verified is not None:
                return verified
            return _fallback(
                local,
                expected_hash=expected_hash,
                reason="database_snapshot_stale",
            )
    else:
        database_reason = "database_url_missing"

    publishable_key = str(environment.get("SUPABASE_PUBLISHABLE_KEY") or "").strip()
    if not publishable_key:
        return _fallback(
            local,
            expected_hash=expected_hash,
            reason=database_reason,
        )

    project_url = str(environment.get("SUPABASE_PROJECT_URL") or PROJECT_URL).strip()
    if not project_url.startswith("https://"):
        return _fallback(
            local,
            expected_hash=expected_hash,
            reason="project_url_invalid",
        )

    try:
        remote = _read_from_rpc(
            publishable_key,
            project_url,
            opener=opener,
            timeout=timeout,
        )
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        return _fallback(
            local,
            expected_hash=expected_hash,
            reason=f"rpc_unavailable:{type(exc).__name__}",
        )

    if remote.get("status") != "ok":
        return _fallback(
            local,
            expected_hash=expected_hash,
            reason="rpc_status_not_ok",
        )

    verified = _validated_backend_document(
        local,
        expected_hash=expected_hash,
        payload=remote.get("payload"),
        declared_hash=remote.get("source_hash"),
        source="supabase_rpc",
        updated_at=remote.get("updated_at"),
    )
    if verified is not None:
        return verified

    return _fallback(
        local,
        expected_hash=expected_hash,
        reason="rpc_snapshot_stale",
    )
