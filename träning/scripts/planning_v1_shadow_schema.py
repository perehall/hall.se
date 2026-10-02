#!/usr/bin/env python3
"""Bootstrap/verify the non-authoritative Planning Engine v1 shadow audit schema.

This utility has exactly one write scope: the append-only
training.planning_v1_shadow_runs audit relation defined by the checked-in
migration. It never reads or writes authoritative planned workout state.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20261001114500_planning_v1_shadow_runs.sql"
RELATION = "training.planning_v1_shadow_runs"


def _database_url() -> str:
    value = str(os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not value:
        raise RuntimeError("SUPABASE_DB_URL is missing")
    return value


def _validate_migration_scope(sql_text: str) -> None:
    lowered = sql_text.lower()
    forbidden = (
        "planned_workout",
        "planned_workouts",
        "plan_generation",
        "training.activities",
        "training.activity",
        "training.current",
        "delete from",
        "update ",
        "insert into",
        "truncate ",
        "drop table",
        "alter table training.planned",
    )
    for token in forbidden:
        if token in lowered:
            raise RuntimeError(
                f"shadow audit migration contains forbidden authoritative token: {token}"
            )

    required = (
        "create table training.planning_v1_shadow_runs",
        "alter table training.planning_v1_shadow_runs enable row level security",
    )
    for token in required:
        if token not in lowered:
            raise RuntimeError(f"shadow audit migration missing required token: {token}")


def relation_exists(cur) -> bool:
    cur.execute("select to_regclass(%s)", (RELATION,))
    return cur.fetchone()[0] is not None


def bootstrap(*, apply: bool) -> str:
    import psycopg  # type: ignore

    sql_text = MIGRATION.read_text(encoding="utf-8")
    _validate_migration_scope(sql_text)

    with psycopg.connect(
        _database_url(),
        sslmode="require",
        connect_timeout=15,
    ) as conn:
        with conn.cursor() as cur:
            if relation_exists(cur):
                conn.rollback()
                return "already_present"
            if not apply:
                conn.rollback()
                return "missing"

            # The migration is executed in one transaction. Any error rolls the
            # entire audit-schema bootstrap back.
            cur.execute(sql_text)
            if not relation_exists(cur):
                raise RuntimeError("shadow audit relation absent after migration")
            conn.commit()
            return "created"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create the shadow audit relation when missing.",
    )
    args = parser.parse_args(argv)

    status = bootstrap(apply=args.apply)
    print(f"PLANNING_V1_SHADOW_SCHEMA status={status}")
    return 0 if status in {"already_present", "created"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
