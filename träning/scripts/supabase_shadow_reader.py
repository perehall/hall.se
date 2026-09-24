#!/usr/bin/env python3
"""Read back the committed Supabase shadow and compare it with canonical JSON.

This is an independent canary for the future database read path. It opens a
fresh PostgreSQL connection, marks the transaction read-only and verifies that
the persisted shadow can reproduce the same snapshot contract that the writer
used.

The live training system does not consume these reads yet.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


from supabase_shadow_model import build_shadow_payload, canonical_hash


def database_url() -> str:
    value = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not value:
        raise RuntimeError("SUPABASE_DB_URL is missing")
    return value


def normalize_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    else:
        raise RuntimeError(f"Unsupported timestamp value: {value!r}")

    if parsed.tzinfo is None:
        raise RuntimeError(f"Timestamp must be timezone-aware: {value!r}")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def compare_key_sets(label: str, expected: set[Any], actual: set[Any]) -> None:
    if expected == actual:
        return
    missing = sorted(expected - actual, key=str)
    extra = sorted(actual - expected, key=str)
    raise RuntimeError(
        f"{label} key-set mismatch: expected={len(expected)} actual={len(actual)} "
        f"missing={missing[:5]} extra={extra[:5]}"
    )


def expected_key_sets(payload: dict[str, Any]) -> dict[str, set[Any]]:
    return {
        "activities": {
            (row["provider"], row["provider_activity_id"])
            for row in payload["activities"]
        },
        "activity_laps": {
            (row["provider"], row["provider_activity_id"], int(row["lap_index"]))
            for row in payload["activity_laps"]
        },
        "activity_overrides": {
            (row["provider"], row["provider_activity_id"])
            for row in payload["activity_overrides"]
        },
        "activity_feedback": {
            row["event_key"] for row in payload["activity_feedback"]
        },
        "training_goals": {
            row["goal_id"] for row in payload["training_goals"]
        },
        "state_documents": {
            row["document_key"] for row in payload["state_documents"]
        },
        "mesocycles": {
            row["id"] for row in payload["mesocycles"]
        },
        "microcycles": {
            row["id"] for row in payload["microcycles"]
        },
        "planned_workouts": {
            row["workout_key"] for row in payload["planned_workouts"]
        },
        "coach_evaluations": {
            (
                row["provider"],
                row["provider_activity_id"],
                normalize_timestamp(row["generated_at"]),
            )
            for row in payload["coach_evaluations"]
        },
    }


def fetch_actual_key_sets(cur: Any) -> dict[str, set[Any]]:
    cur.execute("select provider, provider_activity_id from training.activities")
    activities = {(row[0], row[1]) for row in cur.fetchall()}

    cur.execute(
        """
        select a.provider, a.provider_activity_id, l.lap_index
        from training.activity_laps l
        join training.activities a on a.id = l.activity_id
        """
    )
    activity_laps = {(row[0], row[1], int(row[2])) for row in cur.fetchall()}

    cur.execute(
        """
        select a.provider, a.provider_activity_id
        from training.activity_overrides o
        join training.activities a on a.id = o.activity_id
        """
    )
    activity_overrides = {(row[0], row[1]) for row in cur.fetchall()}

    cur.execute("select event_key from training.activity_feedback")
    activity_feedback = {row[0] for row in cur.fetchall()}

    cur.execute("select goal_id from training.training_goals")
    training_goals = {row[0] for row in cur.fetchall()}

    cur.execute("select document_key from training.state_documents")
    state_documents = {row[0] for row in cur.fetchall()}

    cur.execute("select id from training.mesocycles")
    mesocycles = {row[0] for row in cur.fetchall()}

    cur.execute("select id from training.microcycles")
    microcycles = {row[0] for row in cur.fetchall()}

    cur.execute("select workout_key from training.planned_workouts")
    planned_workouts = {row[0] for row in cur.fetchall()}

    cur.execute(
        """
        select a.provider, a.provider_activity_id, c.generated_at
        from training.coach_evaluations c
        join training.activities a on a.id = c.activity_id
        """
    )
    coach_evaluations = {
        (row[0], row[1], normalize_timestamp(row[2]))
        for row in cur.fetchall()
    }

    return {
        "activities": activities,
        "activity_laps": activity_laps,
        "activity_overrides": activity_overrides,
        "activity_feedback": activity_feedback,
        "training_goals": training_goals,
        "state_documents": state_documents,
        "mesocycles": mesocycles,
        "microcycles": microcycles,
        "planned_workouts": planned_workouts,
        "coach_evaluations": coach_evaluations,
    }


def verify_state_documents(cur: Any, payload: dict[str, Any]) -> None:
    expected = {
        row["document_key"]: {
            "source_hash": row["source_hash"],
            "payload_hash": canonical_hash(row["payload"]),
        }
        for row in payload["state_documents"]
    }

    cur.execute(
        """
        select document_key, source_hash, payload
        from training.state_documents
        """
    )
    actual = {
        row[0]: {
            "source_hash": row[1],
            "payload_hash": canonical_hash(row[2]),
        }
        for row in cur.fetchall()
    }

    if expected != actual:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(
            key
            for key in set(expected) & set(actual)
            if expected[key] != actual[key]
        )
        raise RuntimeError(
            "state_documents content mismatch: "
            f"missing={missing[:5]} extra={extra[:5]} changed={changed[:5]}"
        )


def verify_manifest(cur: Any, payload: dict[str, Any]) -> None:
    key = f"supabase-shadow:{payload['source_hash']}"
    cur.execute(
        """
        select status, metadata
        from training.job_runs
        where idempotency_key = %s
        """,
        (key,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Shadow manifest missing for source hash {payload['source_hash']}")

    status, metadata = row
    if status != "succeeded":
        raise RuntimeError(f"Shadow manifest is not succeeded: {status}")

    metadata = metadata or {}
    if metadata.get("source_hash") != payload["source_hash"]:
        raise RuntimeError("Shadow manifest source_hash mismatch")
    if metadata.get("contract_version") != payload["contract_version"]:
        raise RuntimeError("Shadow manifest contract_version mismatch")
    if metadata.get("counts") != payload["counts"]:
        raise RuntimeError(
            f"Shadow manifest counts mismatch: source={payload['counts']} db={metadata.get('counts')}"
        )


def audit() -> dict[str, Any]:
    # Keep the database driver out of the normal training/test dependency graph.
    # Only the dedicated backend workflow installs and imports psycopg.
    import psycopg

    payload = build_shadow_payload()
    expected = expected_key_sets(payload)

    with psycopg.connect(
        database_url(),
        sslmode="require",
        connect_timeout=15,
    ) as conn:
        with conn.cursor() as cur:
            # Must be the first statement in this transaction. This canary is
            # deliberately incapable of changing the database.
            cur.execute("set transaction read only")

            actual = fetch_actual_key_sets(cur)
            for label, expected_keys in expected.items():
                compare_key_sets(label, expected_keys, actual[label])

            verify_state_documents(cur, payload)
            verify_manifest(cur, payload)
            conn.rollback()

    return {
        "source_hash": payload["source_hash"],
        "counts": payload["counts"],
    }


def main() -> int:
    try:
        result = audit()
    except Exception as exc:
        print(f"SUPABASE_SHADOW_READBACK_FAILED {type(exc).__name__}: {exc}")
        return 1

    print(
        "SUPABASE_SHADOW_READBACK_OK "
        f"source_hash={result['source_hash']} counts={result['counts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
