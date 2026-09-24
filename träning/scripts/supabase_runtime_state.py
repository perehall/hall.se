#!/usr/bin/env python3
"""Promote generated training runtime state to Supabase and read it back.

Generated JSON is a candidate buffer only. A runtime scope becomes authoritative
after a transactional PostgreSQL write succeeds and a fresh read-only connection
reconstructs the exact documents. The verified database payload is then
materialized back to JSON as a compatibility cache for legacy consumers.

Scopes:
- athlete: athlete_state before adaptive planning.
- planning: strategy/mesocycle/microcycle/plan before downstream coaching.
- final: final plan plus coach state before rendering/publication.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import psycopg

from supabase_shadow_model import (
    DATA,
    DOCUMENT_FILES,
    build_shadow_payload,
    canonical_hash,
)
from supabase_shadow_writer import assert_schema, database_url, upsert


SCOPE_KEYS = {
    "athlete": ("athlete_state",),
    "planning": (
        "athlete_state",
        "training_strategy",
        "mesocycle_decision",
        "microcycle_decision",
        "plan",
        "upcoming_week",
    ),
    "final": (
        "athlete_state",
        "training_strategy",
        "mesocycle_decision",
        "microcycle_decision",
        "plan",
        "upcoming_week",
        "coach",
    ),
}


def _documents_by_key(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["document_key"]): row
        for row in payload.get("state_documents") or []
    }


def selected_document_rows(
    payload: dict[str, Any],
    scope: str,
) -> list[dict[str, Any]]:
    keys = SCOPE_KEYS[scope]
    available = _documents_by_key(payload)
    missing = [key for key in keys if key not in available]
    if missing:
        raise RuntimeError(
            "Runtime backend candidate is missing documents: " + ", ".join(missing)
        )
    return [dict(available[key]) for key in keys]


def scope_source_hash(rows: list[dict[str, Any]]) -> str:
    return canonical_hash(
        {
            row["document_key"]: {
                "source_hash": row["source_hash"],
                "payload": row["payload"],
            }
            for row in rows
        }
    )


def _activity_uuid_map(cur: Any, payload: dict[str, Any]) -> dict[tuple[str, str], Any]:
    references: set[tuple[str, str]] = set()
    for row in payload.get("planned_workouts") or []:
        provider = row.get("linked_provider")
        source_id = row.get("linked_provider_activity_id")
        if provider and source_id:
            references.add((str(provider), str(source_id)))
    for row in payload.get("coach_evaluations") or []:
        provider = row.get("provider")
        source_id = row.get("provider_activity_id")
        if provider and source_id:
            references.add((str(provider), str(source_id)))

    result: dict[tuple[str, str], Any] = {}
    for provider, source_id in sorted(references):
        cur.execute(
            """
            select id
            from training.activities
            where provider = %s
              and provider_activity_id = %s
            limit 1
            """,
            (provider, source_id),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                f"Runtime backend references unknown activity {provider}:{source_id}"
            )
        result[(provider, source_id)] = row[0]
    return result


def _linked_activity_id(
    activity_ids: dict[tuple[str, str], Any],
    provider: Any,
    source_id: Any,
) -> Any:
    if not provider or not source_id:
        return None
    key = (str(provider), str(source_id))
    if key not in activity_ids:
        raise RuntimeError(
            f"Runtime backend missing activity foreign key {key[0]}:{key[1]}"
        )
    return activity_ids[key]


def _write_documents(cur: Any, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        upsert(cur, "state_documents", dict(row), ("document_key",))


def _write_planning_relational(
    cur: Any,
    payload: dict[str, Any],
    runtime_hash: str,
    activity_ids: dict[tuple[str, str], Any],
) -> None:
    for row in payload.get("mesocycles") or []:
        upsert(cur, "mesocycles", dict(row), ("id",))

    for row in payload.get("microcycles") or []:
        upsert(cur, "microcycles", dict(row), ("id",))

    cur.execute(
        "update training.planned_workouts set is_current = false where is_current"
    )
    for source in payload.get("planned_workouts") or []:
        row = dict(source)
        provider = row.pop("linked_provider")
        source_id = row.pop("linked_provider_activity_id")
        row["linked_activity_id"] = _linked_activity_id(
            activity_ids, provider, source_id
        )
        row["is_current"] = True
        row["last_seen_source_hash"] = runtime_hash
        upsert(cur, "planned_workouts", row, ("workout_key",))


def _write_coach_relational(
    cur: Any,
    payload: dict[str, Any],
    activity_ids: dict[tuple[str, str], Any],
) -> None:
    for source in payload.get("coach_evaluations") or []:
        row = dict(source)
        provider = row.pop("provider")
        source_id = row.pop("provider_activity_id")
        row["activity_id"] = _linked_activity_id(
            activity_ids, provider, source_id
        )
        upsert(
            cur,
            "coach_evaluations",
            row,
            ("activity_id", "generated_at"),
        )


def _verify_transaction(
    cur: Any,
    rows: list[dict[str, Any]],
    payload: dict[str, Any],
    scope: str,
) -> None:
    expected = {row["document_key"]: row["source_hash"] for row in rows}
    cur.execute(
        """
        select document_key, source_hash
        from training.state_documents
        where document_key = any(%s)
        """,
        (list(expected),),
    )
    actual = dict(cur.fetchall())
    if actual != expected:
        raise RuntimeError(
            f"Runtime state document verification mismatch expected={sorted(expected)} "
            f"actual={sorted(actual)}"
        )

    if scope in {"planning", "final"}:
        expected_workouts = {
            row["workout_key"] for row in payload.get("planned_workouts") or []
        }
        cur.execute(
            "select workout_key from training.planned_workouts where is_current"
        )
        actual_workouts = {row[0] for row in cur.fetchall()}
        if actual_workouts != expected_workouts:
            raise RuntimeError(
                "Runtime planned-workout snapshot differs from candidate"
            )

    if scope == "final":
        expected_coach = {
            (str(row["provider_activity_id"]), str(row["generated_at"]))
            for row in payload.get("coach_evaluations") or []
        }
        if expected_coach:
            cur.execute(
                """
                select a.provider_activity_id, c.generated_at::text
                from training.coach_evaluations c
                join training.activities a on a.id = c.activity_id
                where a.provider = 'strava'
                """
            )
            actual_coach = {(str(a), str(g)) for a, g in cur.fetchall()}
            if not expected_coach.issubset(actual_coach):
                raise RuntimeError("Runtime coach evaluation verification mismatch")


def _fresh_readback(
    rows: list[dict[str, Any]],
    scope: str,
    expected_workouts: set[str],
) -> dict[str, dict[str, Any]]:
    expected = {row["document_key"]: row for row in rows}
    with psycopg.connect(
        database_url(),
        sslmode="require",
        connect_timeout=15,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("set transaction read only")
            cur.execute(
                """
                select document_key, source_hash, payload
                from training.state_documents
                where document_key = any(%s)
                """,
                (list(expected),),
            )
            actual_rows = {
                str(key): {
                    "source_hash": str(source_hash),
                    "payload": payload,
                }
                for key, source_hash, payload in cur.fetchall()
            }

            if set(actual_rows) != set(expected):
                raise RuntimeError("Fresh runtime readback is missing state documents")

            for key, candidate in expected.items():
                actual = actual_rows[key]
                if actual["source_hash"] != candidate["source_hash"]:
                    raise RuntimeError(
                        f"Fresh runtime readback hash mismatch for {key}"
                    )
                if canonical_hash(actual["payload"]) != candidate["source_hash"]:
                    raise RuntimeError(
                        f"Fresh runtime readback payload mismatch for {key}"
                    )

            if scope in {"planning", "final"}:
                cur.execute(
                    "select workout_key from training.planned_workouts where is_current"
                )
                actual_workouts = {row[0] for row in cur.fetchall()}
                if actual_workouts != expected_workouts:
                    raise RuntimeError(
                        "Fresh runtime readback planned-workout snapshot mismatch"
                    )
            conn.rollback()
    return actual_rows


def _materialize_cache(
    rows: dict[str, dict[str, Any]],
    data_dir: Path,
) -> None:
    for key, record in rows.items():
        filename = DOCUMENT_FILES.get(key)
        if not filename:
            continue
        path = data_dir / filename
        path.write_text(
            json.dumps(record["payload"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def promote_runtime_scope(
    scope: str,
    *,
    data_dir: Path = DATA,
) -> dict[str, Any]:
    if scope not in SCOPE_KEYS:
        raise RuntimeError(f"Unknown runtime backend scope: {scope}")

    payload = build_shadow_payload(data_dir)
    rows = selected_document_rows(payload, scope)
    runtime_hash = scope_source_hash(rows)
    activity_ids_needed = scope in {"planning", "final"}

    with psycopg.connect(
        database_url(),
        sslmode="require",
        connect_timeout=15,
    ) as conn:
        with conn.cursor() as cur:
            assert_schema(cur)
            activity_ids = (
                _activity_uuid_map(cur, payload) if activity_ids_needed else {}
            )
            _write_documents(cur, rows)
            if scope in {"planning", "final"}:
                _write_planning_relational(
                    cur,
                    payload,
                    runtime_hash,
                    activity_ids,
                )
            if scope == "final":
                _write_coach_relational(cur, payload, activity_ids)
            _verify_transaction(cur, rows, payload, scope)
            conn.commit()

    expected_workouts = (
        {row["workout_key"] for row in payload.get("planned_workouts") or []}
        if scope in {"planning", "final"}
        else set()
    )
    readback = _fresh_readback(rows, scope, expected_workouts)
    _materialize_cache(readback, data_dir)
    return {
        "scope": scope,
        "source": "supabase_db",
        "verified": True,
        "source_hash": runtime_hash,
        "documents": sorted(readback),
        "current_workouts": len(expected_workouts),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=tuple(SCOPE_KEYS), required=True)
    args = parser.parse_args(argv)
    try:
        result = promote_runtime_scope(args.scope)
    except Exception as exc:
        print(
            f"SUPABASE_RUNTIME_STATE_FAILED scope={args.scope} "
            f"error={type(exc).__name__}:{exc}"
        )
        return 1

    print(
        "SUPABASE_RUNTIME_STATE_OK "
        f"scope={result['scope']} source={result['source']} "
        f"verified={result['verified']} source_hash={result['source_hash']} "
        f"documents={','.join(result['documents'])} "
        f"current_workouts={result['current_workouts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
