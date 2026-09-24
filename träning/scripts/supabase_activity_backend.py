#!/usr/bin/env python3
"""Promote normalized activity/feedback state into Supabase before planning.

The Strava adapters still use activities.json as a transient ingestion buffer.
After semantic normalization this module atomically promotes the normalized
activity snapshot, current overrides and append-retained feedback to PostgreSQL,
then performs an independent relational readback. The readback materializes the
JSON files again as compatibility caches for legacy consumers.

Production athlete-state may only consume a verified backend snapshot when
SUPABASE_DB_URL is configured.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from supabase_shadow_model import (
    activity_records,
    canonical_hash,
    document_records,
    override_and_feedback_records,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ACTIVITIES_FILE = DATA / "activities.json"
OVERRIDES_FILE = DATA / "activity_overrides.json"


def database_url(env: dict[str, str] | None = None) -> str:
    environment = env if env is not None else os.environ
    value = str(environment.get("SUPABASE_DB_URL") or "").strip()
    if not value:
        raise RuntimeError("SUPABASE_DB_URL is missing")
    return value


def load_json(path: Path, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        if fallback is None:
            raise RuntimeError(f"Activity backend source missing: {path}")
        return deepcopy(fallback)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Activity backend source must be an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def safe_error_detail(exc: Exception) -> str:
    # RuntimeError messages in this module are explicit contract failures and
    # contain no credentials. Driver/network exceptions may include connection
    # metadata, so only their type is logged.
    if type(exc) is RuntimeError:
        return f"RuntimeError:{exc}"
    return type(exc).__name__


def build_activity_snapshot(
    data_dir: Path = DATA,
) -> dict[str, Any]:
    activities_doc = load_json(data_dir / "activities.json")
    overrides_doc = load_json(
        data_dir / "activity_overrides.json",
        {"schema_version": 1, "overrides": {}},
    )
    activities, laps = activity_records(activities_doc)
    overrides, feedback = override_and_feedback_records(overrides_doc)
    activity_ids = {row["provider_activity_id"] for row in activities}
    referenced = {
        row["provider_activity_id"]
        for row in overrides + feedback
    }
    missing = sorted(referenced - activity_ids)
    if missing:
        raise RuntimeError(
            "Activity backend snapshot references missing activities: "
            + ", ".join(missing[:10])
        )

    documents = document_records(
        {
            "activities": activities_doc,
            "activity_overrides": overrides_doc,
        }
    )
    source_hash = canonical_hash(
        {
            "activities": activities_doc,
            "activity_overrides": overrides_doc,
        }
    )
    return {
        "source_hash": source_hash,
        "activities_document": activities_doc,
        "overrides_document": overrides_doc,
        "activities": activities,
        "activity_laps": laps,
        "activity_overrides": overrides,
        "activity_feedback": feedback,
        "state_documents": documents,
        "counts": {
            "activities": len(activities),
            "activity_laps": len(laps),
            "activity_overrides": len(overrides),
            "activity_feedback_current_projection": len(feedback),
        },
    }


def _driver():
    import psycopg  # type: ignore
    from psycopg import sql  # type: ignore
    from psycopg.types.json import Jsonb  # type: ignore

    return psycopg, sql, Jsonb


def _adapt_row(row: dict[str, Any], Jsonb: Any) -> dict[str, Any]:
    result = dict(row)
    for key in ("raw", "payload", "metadata"):
        if key in result and result[key] is not None:
            result[key] = Jsonb(result[key])
    return result


def _upsert(
    cur: Any,
    table: str,
    row: dict[str, Any],
    conflict: tuple[str, ...],
    *,
    returning: str | None = None,
    conflict_where: str | None = None,
) -> Any:
    _psycopg, sql, Jsonb = _driver()
    row = _adapt_row(row, Jsonb)
    columns = tuple(row)
    updates = tuple(column for column in columns if column not in conflict)
    query = sql.SQL(
        "insert into training.{} ({}) values ({}) on conflict ({})"
    ).format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        sql.SQL(", ").join(map(sql.Identifier, conflict)),
    )
    if conflict_where:
        query += sql.SQL(" where ") + sql.SQL(conflict_where)
    if updates:
        query += sql.SQL(" do update set ") + sql.SQL(", ").join(
            sql.SQL("{} = excluded.{}").format(
                sql.Identifier(column),
                sql.Identifier(column),
            )
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


def assert_activity_schema(cur: Any) -> None:
    cur.execute(
        """
        select column_name
        from information_schema.columns
        where table_schema = 'training'
          and table_name = 'activities'
          and column_name in (
            'provider', 'provider_activity_id', 'raw',
            'is_current', 'last_seen_source_hash'
          )
        """
    )
    present = {row[0] for row in cur.fetchall()}
    required = {
        "provider",
        "provider_activity_id",
        "raw",
        "is_current",
        "last_seen_source_hash",
    }
    if present != required:
        raise RuntimeError(
            "Supabase activity currentness migration is incomplete: "
            f"present={sorted(present)}"
        )


def _activity_id_map(cur: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for source in snapshot["activities"]:
        row = dict(source)
        row["is_current"] = True
        row["last_seen_source_hash"] = snapshot["source_hash"]
        activity_id = _upsert(
            cur,
            "activities",
            row,
            ("provider", "provider_activity_id"),
            returning="id",
        )
        result[str(row["provider_activity_id"])] = activity_id
    return result


def _replace_current_laps(
    cur: Any,
    snapshot: dict[str, Any],
    activity_ids: dict[str, Any],
) -> None:
    for activity_id in activity_ids.values():
        cur.execute(
            "delete from training.activity_laps where activity_id = %s",
            (activity_id,),
        )
    for source in snapshot["activity_laps"]:
        row = dict(source)
        provider = row.pop("provider")
        source_id = str(row.pop("provider_activity_id"))
        if provider != "strava" or source_id not in activity_ids:
            raise RuntimeError(f"Activity lap has unknown parent {provider}:{source_id}")
        row["activity_id"] = activity_ids[source_id]
        _upsert(cur, "activity_laps", row, ("activity_id", "lap_index"))


def _replace_current_overrides(
    cur: Any,
    snapshot: dict[str, Any],
    activity_ids: dict[str, Any],
) -> None:
    cur.execute(
        """
        delete from training.activity_overrides o
        using training.activities a
        where o.activity_id = a.id
          and a.provider = 'strava'
        """
    )
    for source in snapshot["activity_overrides"]:
        row = dict(source)
        provider = row.pop("provider")
        source_id = str(row.pop("provider_activity_id"))
        if provider != "strava" or source_id not in activity_ids:
            raise RuntimeError(f"Activity override has unknown parent {provider}:{source_id}")
        row["activity_id"] = activity_ids[source_id]
        _upsert(cur, "activity_overrides", row, ("activity_id",))


def _append_feedback(
    cur: Any,
    snapshot: dict[str, Any],
    activity_ids: dict[str, Any],
) -> None:
    for source in snapshot["activity_feedback"]:
        row = dict(source)
        provider = row.pop("provider")
        source_id = str(row.pop("provider_activity_id"))
        event_key = str(row.get("event_key") or "").strip()
        if provider != "strava" or source_id not in activity_ids:
            raise RuntimeError(f"Activity feedback has unknown parent {provider}:{source_id}")
        if not event_key:
            raise RuntimeError("Activity feedback requires deterministic event_key")
        row["activity_id"] = activity_ids[source_id]
        _upsert(
            cur,
            "activity_feedback",
            row,
            ("event_key",),
            conflict_where="event_key is not null",
        )


def _write_documents(cur: Any, snapshot: dict[str, Any]) -> None:
    for row in snapshot["state_documents"]:
        _upsert(cur, "state_documents", dict(row), ("document_key",))


def _record_manifest(cur: Any, snapshot: dict[str, Any]) -> None:
    _upsert(
        cur,
        "job_runs",
        {
            "job_type": "activity_backend_promote",
            "trigger_source": "canonical_training_pipeline",
            "idempotency_key": "activity-backend:" + snapshot["source_hash"],
            "status": "succeeded",
            "started_at": None,
            "finished_at": None,
            "metadata": {
                "source_hash": snapshot["source_hash"],
                "counts": snapshot["counts"],
            },
        },
        ("idempotency_key",),
        conflict_where="idempotency_key is not null",
    )


def _verify_write(
    cur: Any,
    snapshot: dict[str, Any],
    activity_ids: dict[str, Any],
) -> None:
    expected_ids = {
        str(row["provider_activity_id"])
        for row in snapshot["activities"]
        if row["provider"] == "strava"
    }
    cur.execute(
        """
        select provider_activity_id
        from training.activities
        where provider = 'strava'
          and is_current
        """
    )
    actual_ids = {str(row[0]) for row in cur.fetchall()}
    if actual_ids != expected_ids:
        raise RuntimeError(
            "Current activity key-set mismatch: "
            f"missing={sorted(expected_ids - actual_ids)[:5]} "
            f"extra={sorted(actual_ids - expected_ids)[:5]}"
        )

    expected_laps = {
        (str(row["provider_activity_id"]), int(row["lap_index"]))
        for row in snapshot["activity_laps"]
    }
    cur.execute(
        """
        select a.provider_activity_id, l.lap_index
        from training.activity_laps l
        join training.activities a on a.id = l.activity_id
        where a.provider = 'strava'
          and a.is_current
        """
    )
    actual_laps = {(str(row[0]), int(row[1])) for row in cur.fetchall()}
    if actual_laps != expected_laps:
        raise RuntimeError(
            "Current lap key-set mismatch: "
            f"missing={len(expected_laps - actual_laps)} "
            f"extra={len(actual_laps - expected_laps)}"
        )

    expected_overrides = {
        str(row["provider_activity_id"])
        for row in snapshot["activity_overrides"]
    }
    cur.execute(
        """
        select a.provider_activity_id
        from training.activity_overrides o
        join training.activities a on a.id = o.activity_id
        where a.provider = 'strava'
        """
    )
    actual_overrides = {str(row[0]) for row in cur.fetchall()}
    if actual_overrides != expected_overrides:
        raise RuntimeError("Current activity override key-set mismatch")

    expected_documents = {
        row["document_key"]: row["source_hash"]
        for row in snapshot["state_documents"]
    }
    cur.execute(
        """
        select document_key, source_hash
        from training.state_documents
        where document_key = any(%s)
        """,
        (list(expected_documents),),
    )
    actual_documents = {str(row[0]): str(row[1]) for row in cur.fetchall()}
    if actual_documents != expected_documents:
        raise RuntimeError("Activity state-document hash mismatch")


def promote_snapshot(
    snapshot: dict[str, Any],
    *,
    connection_factory: Callable[..., Any] | None = None,
    env: dict[str, str] | None = None,
) -> None:
    psycopg, _sql, _Jsonb = _driver()
    connect = connection_factory or psycopg.connect
    with connect(
        database_url(env),
        sslmode="require",
        connect_timeout=15,
    ) as conn:
        with conn.cursor() as cur:
            assert_activity_schema(cur)
            cur.execute(
                """
                update training.activities
                set is_current = false
                where provider = 'strava'
                  and is_current
                """
            )
            activity_ids = _activity_id_map(cur, snapshot)
            _replace_current_laps(cur, snapshot, activity_ids)
            _replace_current_overrides(cur, snapshot, activity_ids)
            _append_feedback(cur, snapshot, activity_ids)
            _write_documents(cur, snapshot)
            _verify_write(cur, snapshot, activity_ids)
            _record_manifest(cur, snapshot)
            conn.commit()


def _documents_from_relational_cursor(cur: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cur.execute(
        """
        select document_key, source_hash, payload
        from training.state_documents
        where document_key in ('activities', 'activity_overrides')
        """
    )
    documents = {
        str(row[0]): {
            "source_hash": str(row[1] or ""),
            "payload": row[2],
        }
        for row in cur.fetchall()
    }
    if set(documents) != {"activities", "activity_overrides"}:
        raise RuntimeError("Backend activity documents are incomplete")

    activity_template = documents["activities"]["payload"]
    override_template = documents["activity_overrides"]["payload"]
    if not isinstance(activity_template, dict) or not isinstance(override_template, dict):
        raise RuntimeError("Backend activity documents are malformed")

    cur.execute(
        """
        select provider_activity_id, raw
        from training.activities
        where provider = 'strava'
          and is_current
        """
    )
    raw_activities = {
        str(row[0]): dict(row[1] or {})
        for row in cur.fetchall()
    }

    cur.execute(
        """
        select a.provider_activity_id, l.lap_index, l.raw
        from training.activity_laps l
        join training.activities a on a.id = l.activity_id
        where a.provider = 'strava'
          and a.is_current
        order by a.provider_activity_id, l.lap_index
        """
    )
    laps: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for source_id, lap_index, raw in cur.fetchall():
        laps.setdefault(str(source_id), []).append((int(lap_index), dict(raw or {})))

    template_rows = activity_template.get("activities") or []
    template_ids = [str(row.get("id")) for row in template_rows]
    if set(template_ids) != set(raw_activities):
        raise RuntimeError(
            "Relational activities cannot reproduce persisted activity document"
        )

    rebuilt_rows = []
    for template_row in template_rows:
        source_id = str(template_row.get("id"))
        row = deepcopy(raw_activities[source_id])
        lap_rows = [
            raw
            for _index, raw in sorted(laps.get(source_id, []), key=lambda pair: pair[0])
        ]
        if lap_rows:
            row["laps"] = lap_rows
        rebuilt_rows.append(row)

    rebuilt_activities = {
        key: deepcopy(value)
        for key, value in activity_template.items()
        if key != "activities"
    }
    rebuilt_activities["activities"] = rebuilt_rows

    cur.execute(
        """
        select a.provider_activity_id, o.raw
        from training.activity_overrides o
        join training.activities a on a.id = o.activity_id
        where a.provider = 'strava'
        """
    )
    raw_overrides = {str(row[0]): dict(row[1] or {}) for row in cur.fetchall()}
    template_mapping = override_template.get("overrides") or {}
    if set(raw_overrides) != {str(key) for key in template_mapping}:
        raise RuntimeError(
            "Relational overrides cannot reproduce persisted override document"
        )
    rebuilt_overrides = {
        key: deepcopy(value)
        for key, value in override_template.items()
        if key != "overrides"
    }
    rebuilt_overrides["overrides"] = {
        str(key): deepcopy(raw_overrides[str(key)])
        for key in template_mapping
    }

    if canonical_hash(rebuilt_activities) != documents["activities"]["source_hash"]:
        raise RuntimeError("Relational activity payload hash does not match promoted document")
    if canonical_hash(rebuilt_overrides) != documents["activity_overrides"]["source_hash"]:
        raise RuntimeError("Relational override payload hash does not match promoted document")

    return rebuilt_activities, rebuilt_overrides, {
        "source": "supabase_db",
        "verified": True,
        "activities_hash": documents["activities"]["source_hash"],
        "overrides_hash": documents["activity_overrides"]["source_hash"],
    }


def read_backend_documents(
    *,
    connection_factory: Callable[..., Any] | None = None,
    env: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    psycopg, _sql, _Jsonb = _driver()
    connect = connection_factory or psycopg.connect
    with connect(
        database_url(env),
        sslmode="require",
        connect_timeout=10,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("set transaction read only")
            activities, overrides, metadata = _documents_from_relational_cursor(cur)
            conn.rollback()
    return activities, overrides, metadata


def load_activities_for_runtime(
    local_path: Path = ACTIVITIES_FILE,
    *,
    connection_factory: Callable[..., Any] | None = None,
    env: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    environment = env if env is not None else os.environ
    if not str(environment.get("SUPABASE_DB_URL") or "").strip():
        return load_json(local_path, {"activities": []}), {
            "source": "json_local_dev",
            "verified": False,
            "reason": "database_url_missing",
        }

    activities, _overrides, metadata = read_backend_documents(
        connection_factory=connection_factory,
        env=environment,
    )
    return activities, metadata


def promote_and_materialize(
    *,
    data_dir: Path = DATA,
    connection_factory: Callable[..., Any] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    snapshot = build_activity_snapshot(data_dir)
    promote_snapshot(
        snapshot,
        connection_factory=connection_factory,
        env=env,
    )
    activities, overrides, metadata = read_backend_documents(
        connection_factory=connection_factory,
        env=env,
    )

    if canonical_hash(activities) != canonical_hash(snapshot["activities_document"]):
        raise RuntimeError("Independent backend activity readback differs from ingest snapshot")
    if canonical_hash(overrides) != canonical_hash(snapshot["overrides_document"]):
        raise RuntimeError("Independent backend override readback differs from ingest snapshot")

    write_json(data_dir / "activities.json", activities)
    write_json(data_dir / "activity_overrides.json", overrides)
    return {
        **metadata,
        "source_hash": snapshot["source_hash"],
        "counts": snapshot["counts"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("promote", "readback"),
        default="promote",
    )
    args = parser.parse_args(argv)
    if args.mode == "promote":
        last_error = None
        for attempt in range(1, 4):
            try:
                result = promote_and_materialize()
                print(
                    "SUPABASE_ACTIVITY_PROMOTE_OK "
                    f"source={result['source']} source_hash={result['source_hash']} "
                    f"counts={result['counts']}"
                )
                return 0
            except Exception as exc:
                last_error = exc
                print(
                    "SUPABASE_ACTIVITY_PROMOTE_RETRY "
                    f"attempt={attempt}/3 error={safe_error_detail(exc)}"
                )
                if attempt < 3:
                    time.sleep(attempt * 5)
        print(
            "SUPABASE_ACTIVITY_BACKEND_FAILED "
            f"{safe_error_detail(last_error)}"
        )
        return 1

    try:
        activities, overrides, result = read_backend_documents()
        print(
            "SUPABASE_ACTIVITY_READBACK_OK "
            f"source={result['source']} activities={len(activities.get('activities') or [])} "
            f"overrides={len(overrides.get('overrides') or {})}"
        )
    except Exception as exc:
        print(
            f"SUPABASE_ACTIVITY_BACKEND_FAILED {safe_error_detail(exc)}"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
