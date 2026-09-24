#!/usr/bin/env python3
"""Verified Supabase read path for the planner goal portfolio.

This is the first promoted domain read. The planner may consume the goal
document from Supabase, but only when that document is proven to be exactly the
same canonical snapshot as the repository fallback. Any backend/configuration
failure is non-blocking and falls back to data/goal.json.

The local copy is intentionally retained during this migration stage as a
rollback/freshness oracle. Once writes are promoted to Supabase, this equality
check can be inverted and the JSON file can become a materialized cache.
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


def load_goal_for_planner(
    path: Path,
    *,
    opener: Callable[..., Any] | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 5.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the planner goal from Supabase when the shadow is provably current.

    Security/reliability properties:
    - only the browser-safe publishable key is used;
    - the RPC exposes only the already-public goal portfolio;
    - no table access is granted;
    - network/config/staleness failures fall back to the repository snapshot;
    - remote payload and declared source_hash must both match the local
      canonical hash before Supabase is allowed to influence planning.
    """

    local = _local_goal(path)
    expected_hash = canonical_hash(local)
    environment = env if env is not None else os.environ
    publishable_key = str(environment.get("SUPABASE_PUBLISHABLE_KEY") or "").strip()
    if not publishable_key:
        return _fallback(
            local,
            expected_hash=expected_hash,
            reason="publishable_key_missing",
        )

    project_url = str(environment.get("SUPABASE_PROJECT_URL") or PROJECT_URL).strip().rstrip("/")
    if not project_url.startswith("https://"):
        return _fallback(
            local,
            expected_hash=expected_hash,
            reason="project_url_invalid",
        )

    request = urllib.request.Request(
        project_url + RPC_PATH,
        data=b"{}",
        headers={
            "apikey": publishable_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    open_request = opener or urllib.request.urlopen

    try:
        with open_request(request, timeout=timeout) as response:
            remote = json.load(response)
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
            reason=f"backend_unavailable:{type(exc).__name__}",
        )

    if not isinstance(remote, dict) or remote.get("status") != "ok":
        return _fallback(
            local,
            expected_hash=expected_hash,
            reason="backend_status_not_ok",
        )

    payload = remote.get("payload")
    declared_hash = str(remote.get("source_hash") or "")
    if not isinstance(payload, dict) or not payload:
        return _fallback(
            local,
            expected_hash=expected_hash,
            reason="backend_payload_invalid",
        )

    persisted_hash = canonical_hash(payload)
    if declared_hash != expected_hash or persisted_hash != expected_hash:
        return _fallback(
            local,
            expected_hash=expected_hash,
            reason="backend_snapshot_stale",
        )

    return payload, {
        "source": "supabase",
        "verified": True,
        "reason": "hash_match",
        "source_hash": expected_hash,
        "backend_updated_at": remote.get("updated_at"),
    }
