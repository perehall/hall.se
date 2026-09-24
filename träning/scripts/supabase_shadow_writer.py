#!/usr/bin/env python3
"""Write the deterministic training shadow model to Supabase/PostgreSQL.

Safety properties:
- GitHub JSON remains source-of-truth.
- The complete import is one PostgreSQL transaction.
- Every mutable entity is written with an idempotent natural key.
- Verification runs before commit; any mismatch rolls the transaction back.
- No live training JSON, plan, rendering or coaching state is modified.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterable
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from supabase_shadow_model import build_shadow_payload

REQUIRED_TABLES = {
    "activities",
    "activity_laps",
    "activity_feedback",
    "activity_overrides",
    "training_goals",
    "state_documents",
    "mesocycles",
    "microcycles",
    "planned_workouts",
    "coach_evaluations",
    "job_runs",
}

JSON_COLUMNS = {
    "raw",
    "payload",
    "metadata",
    "evidence",
    "cursor",
    "before_state",
    "after_state",
}


def database_url() -> str:
    value = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not value:
        raise RuntimeError("SUPABASE_DB_URL is missing")
    return value


def json_adapted(row: dict[str, Any]) -> dict[str, Any]:
    adapted = dict(row)
    for key in JSON_COLUMNS:
        if key in adapted and adapted[key] is not None:
            adapted[key] = Jsonb(adapted[key])
    return adapted


def assert_schema(cur: psycopg.Cursor[Any]) -> None:
    cur.execute(
        """
        select table_name
        from information_schema.tables
        where table_schema = 'training'
        """
    )
    present = {row[0] for row in cur.fetchall()}
    missing = sorted(REQUIRED_TABLES - present)
    if missing:
        raise RuntimeError(
            "Supabase training schema is incomplete; missing tables: "
            + ", ".join(missing)
        )

    cur.execute(
        """
        select count(*)
        from information_schema.columns
        where table_schema = 'training'
          and table_name = 'activities'
          and column_name in (
            'provider', 'provider_activity_id', 'raw',
            'is_current', 'last_seen_source_hash'
          )
        """
    )
    if cur.fetchone()[0] != 5:
        raise RuntimeError(
            "Supabase training.activities currentness contract does not match promoted backend"
        )

    cur.execute(
        """
        select count(*)
        from information_schema.columns
        where table_schema = 'training'
          and table_name = 'planned_workouts'
          and column_name in ('is_current', 'last_seen_source_hash')
        """
    )
    if cur.fetchone()[0] != 2:
        raise RuntimeError(
            "Supabase planned_workouts currentness migration is not deployed"
        )


def upsert(
    cur: psycopg.Cursor[Any],
    table: str,
    row: dict[str, Any],
    conflict: tuple[str, ...],
    *,
    conflict_where: str | None = None,
    returning: str | None = None,
) -> Any:
    row = json_adapted(row)
    columns = tuple(row.keys())
    updates = tuple(column for column in columns if column not in conflict)

    query = sql.SQL("insert into training.{} ({}) values ({}) on conflict ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        sql.SQL(", ").join(map(sql.Identifier, conflict)),
    )
    if conflict_where:
        query += sql.SQL(" where ") + sql.SQL(conflict_where)

    if updates:
        query += sql.SQL(" do update set ") + sql.SQL(", ").join(
            sql.SQL("{} = excluded.{}").format(sql.Identifier(column), sql.Identifier(column))
            for column in updates
        )
    else:
        query += sql.SQL(" do nothing")

    if returning:
        query += sql.SQL(" returning {}").format(sql.Identifier(returning))

    cur.execute(query, tuple(row[column] for column in columns))
    if returning:
        result = cur.fetchone()
        if result is None:
            raise RuntimeError(f"{table}: upsert returned no {returning}")
        return result[0]
    return None


def require_activity_id(
    activity_ids: dict[tuple[str, str], Any],
    provider: str,
    provider_activity_id: str,
) -> Any:
    key = (str(provider), str(provider_activity_id))
    try:
        return activity_ids[key]
    except KeyError as exc:
        raise RuntimeError(f"Missing activity foreign key for {key[0]}:{key[1]}") from exc


def import_payload(cur: psycopg.Cursor[Any], payload: dict[str, Any]) -> dict[tuple[str, str], Any]:
    activity_ids: dict[tuple[str, str], Any] = {}

    # Activities are now an explicit current snapshot. Historical rows are
    # retained but cannot feed athlete-state/planning once absent from source.
    cur.execute(
        "update training.activities set is_current = false where provider = 'strava' and is_current"
    )

    for source in payload["activities"]:
        row = dict(source)
        row["is_current"] = True
        row["last_seen_source_hash"] = payload["source_hash"]
        activity_id = upsert(
            cur,
            "activities",
            row,
            ("provider", "provider_activity_id"),
            returning="id",
        )
        activity_ids[(row["provider"], row["provider_activity_id"])] = activity_id

    for source in payload["activity_laps"]:
        row = dict(source)
        provider = row.pop("provider")
        provider_activity_id = row.pop("provider_activity_id")
        row["activity_id"] = require_activity_id(
            activity_ids, provider, provider_activity_id
        )
        upsert(cur, "activity_laps", row, ("activity_id", "lap_index"))

    for source in payload["activity_overrides"]:
        row = dict(source)
        provider = row.pop("provider")
        provider_activity_id = row.pop("provider_activity_id")
        row["activity_id"] = require_activity_id(
            activity_ids, provider, provider_activity_id
        )
        upsert(cur, "activity_overrides", row, ("activity_id",))

    for source in payload["activity_feedback"]:
        row = dict(source)
        provider = row.pop("provider")
        provider_activity_id = row.pop("provider_activity_id")
        row["activity_id"] = require_activity_id(
            activity_ids, provider, provider_activity_id
        )
        if not row.get("event_key"):
            raise RuntimeError("activity_feedback requires deterministic event_key")
        upsert(
            cur,
            "activity_feedback",
            row,
            ("event_key",),
            conflict_where="event_key is not null",
        )

    for row in payload["training_goals"]:
        upsert(cur, "training_goals", dict(row), ("goal_id",))

    for row in payload["state_documents"]:
        upsert(cur, "state_documents", dict(row), ("document_key",))

    for row in payload["mesocycles"]:
        upsert(cur, "mesocycles", dict(row), ("id",))

    for row in payload["microcycles"]:
        upsert(cur, "microcycles", dict(row), ("id",))

    # Current plan state is a snapshot, while previous workout rows are retained
    # as history. Flip currentness transactionally before activating this snapshot.
    cur.execute(
        "update training.planned_workouts set is_current = false where is_current"
    )

    for source in payload["planned_workouts"]:
        row = dict(source)
        linked_provider = row.pop("linked_provider")
        linked_provider_activity_id = row.pop("linked_provider_activity_id")
        row["linked_activity_id"] = (
            require_activity_id(
                activity_ids, linked_provider, linked_provider_activity_id
            )
            if linked_provider and linked_provider_activity_id
            else None
        )
        row["is_current"] = True
        row["last_seen_source_hash"] = payload["source_hash"]
        upsert(cur, "planned_workouts", row, ("workout_key",))

    for source in payload["coach_evaluations"]:
        row = dict(source)
        provider = row.pop("provider")
        provider_activity_id = row.pop("provider_activity_id")
        row["activity_id"] = require_activity_id(
            activity_ids, provider, provider_activity_id
        )
        upsert(cur, "coach_evaluations", row, ("activity_id", "generated_at"))

    return activity_ids


def count_matching(
    cur: psycopg.Cursor[Any],
    table: str,
    column: str,
    values: Iterable[Any],
    *,
    extra_sql: str = "",
    extra_params: tuple[Any, ...] = (),
) -> int:
    values = list(values)
    if not values:
        return 0
    query = sql.SQL("select count(*) from training.{} where {} = any(%s)").format(
        sql.Identifier(table),
        sql.Identifier(column),
    )
    if extra_sql:
        query += sql.SQL(" and ") + sql.SQL(extra_sql)
    cur.execute(query, (values, *extra_params))
    return int(cur.fetchone()[0])


def verify_payload(
    cur: psycopg.Cursor[Any],
    payload: dict[str, Any],
    activity_ids: dict[tuple[str, str], Any],
) -> None:
    activity_source_ids = [
        row["provider_activity_id"]
        for row in payload["activities"]
        if row["provider"] == "strava"
    ]
    activity_count = count_matching(
        cur,
        "activities",
        "provider_activity_id",
        activity_source_ids,
        extra_sql="provider = %s and is_current = true",
        extra_params=("strava",),
    )
    if activity_count != len(activity_source_ids):
        raise RuntimeError(
            f"activities verification mismatch: source={len(activity_source_ids)} db={activity_count}"
        )
    cur.execute(
        "select count(*) from training.activities where provider = 'strava' and is_current"
    )
    if int(cur.fetchone()[0]) != len(activity_source_ids):
        raise RuntimeError("activities current snapshot contains stale/extra rows")

    source_lap_keys = {
        (
            require_activity_id(
                activity_ids, row["provider"], row["provider_activity_id"]
            ),
            int(row["lap_index"]),
        )
        for row in payload["activity_laps"]
    }
    if source_lap_keys:
        activity_uuid_values = sorted({str(key[0]) for key in source_lap_keys})
        cur.execute(
            """
            select activity_id::text, lap_index
            from training.activity_laps
            where activity_id::text = any(%s)
            """,
            (activity_uuid_values,),
        )
        db_lap_keys = {(row[0], int(row[1])) for row in cur.fetchall()}
        normalized_source = {(str(activity_id), lap_index) for activity_id, lap_index in source_lap_keys}
        missing_laps = normalized_source - db_lap_keys
        if missing_laps:
            raise RuntimeError(
                f"activity_laps verification missing {len(missing_laps)} source rows"
            )

    feedback_keys = [row["event_key"] for row in payload["activity_feedback"]]
    feedback_count = count_matching(
        cur, "activity_feedback", "event_key", feedback_keys
    )
    if feedback_count != len(feedback_keys):
        raise RuntimeError(
            f"activity_feedback verification mismatch: source={len(feedback_keys)} db={feedback_count}"
        )

    goal_ids = [row["goal_id"] for row in payload["training_goals"]]
    if count_matching(cur, "training_goals", "goal_id", goal_ids) != len(goal_ids):
        raise RuntimeError("training_goals verification mismatch")

    workout_keys = [row["workout_key"] for row in payload["planned_workouts"]]
    if count_matching(
        cur,
        "planned_workouts",
        "workout_key",
        workout_keys,
        extra_sql="is_current = true",
    ) != len(workout_keys):
        raise RuntimeError("planned_workouts verification mismatch")

    cur.execute("select count(*) from training.planned_workouts where is_current")
    current_workout_count = int(cur.fetchone()[0])
    if current_workout_count != len(workout_keys):
        raise RuntimeError(
            "planned_workouts current snapshot mismatch: "
            f"source={len(workout_keys)} db={current_workout_count}"
        )

    document_rows = payload["state_documents"]
    document_keys = [row["document_key"] for row in document_rows]
    expected_hashes = {
        row["document_key"]: row["source_hash"] for row in document_rows
    }
    if document_keys:
        cur.execute(
            """
            select document_key, source_hash
            from training.state_documents
            where document_key = any(%s)
            """,
            (document_keys,),
        )
        actual_hashes = dict(cur.fetchall())
        if actual_hashes != expected_hashes:
            missing = sorted(set(expected_hashes) - set(actual_hashes))
            changed = sorted(
                key
                for key in set(expected_hashes) & set(actual_hashes)
                if expected_hashes[key] != actual_hashes[key]
            )
            raise RuntimeError(
                f"state_documents verification mismatch: missing={missing} changed={changed}"
            )


def record_success(cur: psycopg.Cursor[Any], payload: dict[str, Any]) -> None:
    counts = payload.get("counts") or {}
    upsert(
        cur,
        "job_runs",
        {
            "job_type": "supabase_shadow_import",
            "trigger_source": "github_workflow_dispatch",
            "idempotency_key": f"supabase-shadow:{payload['source_hash']}",
            "status": "succeeded",
            "started_at": None,
            "finished_at": None,
            "metadata": {
                "contract_version": payload["contract_version"],
                "source_hash": payload["source_hash"],
                "counts": counts,
            },
        },
        ("idempotency_key",),
        conflict_where="idempotency_key is not null",
    )


def run(mode: str) -> None:
    payload = build_shadow_payload()
    with psycopg.connect(
        database_url(),
        sslmode="require",
        connect_timeout=15,
    ) as conn:
        with conn.cursor() as cur:
            assert_schema(cur)
            print("SUPABASE_SHADOW_SCHEMA_OK")

            if mode == "check":
                conn.rollback()
                print(
                    "SUPABASE_SHADOW_CHECK_OK "
                    f"source_hash={payload['source_hash']} counts={payload['counts']}"
                )
                return

            activity_ids = import_payload(cur, payload)
            verify_payload(cur, payload, activity_ids)
            record_success(cur, payload)
            conn.commit()
            print(
                "SUPABASE_SHADOW_WRITE_OK "
                f"source_hash={payload['source_hash']} counts={payload['counts']}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("check", "write"), default="check")
    args = parser.parse_args(argv)
    try:
        run(args.mode)
    except Exception as exc:
        print(f"SUPABASE_SHADOW_FAILED {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
