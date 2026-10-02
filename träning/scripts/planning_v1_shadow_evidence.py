#!/usr/bin/env python3
"""Report accumulated Planning Engine v1 shadow evidence.

This script is read-only. It never publishes or mutates a training plan.
Evidence begins accumulating only after the dedicated append-only audit
relation is available.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from training_core.application.planning_shadow_evidence import (
    ShadowEvidenceRequirements,
    evaluate_shadow_evidence,
)


def _database_url() -> str:
    value = str(os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not value:
        raise RuntimeError("SUPABASE_DB_URL is missing")
    return value


def load_shadow_rows(limit: int) -> tuple[str, list[dict[str, Any]]]:
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore

    with psycopg.connect(
        _database_url(),
        sslmode="require",
        connect_timeout=15,
        row_factory=dict_row,
    ) as conn:
        conn.execute("set transaction read only")
        with conn.cursor() as cur:
            cur.execute(
                "select to_regclass('training.planning_v1_shadow_runs') as relation"
            )
            if cur.fetchone()["relation"] is None:
                return "table_missing", []

            cur.execute(
                """
                select
                    event_key,
                    trigger_source,
                    microcycle_key,
                    readiness_status,
                    solver_status,
                    semantic_input_hash,
                    engine_version,
                    plan_content_hash,
                    objective_vector,
                    created_at
                from training.planning_v1_shadow_runs
                order by created_at desc
                limit %s
                """,
                (limit,),
            )
            return "loaded", list(cur.fetchall())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-microcycles", type=int, default=4)
    parser.add_argument("--min-events", type=int, default=20)
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args(argv)

    if args.limit < 1:
        parser.error("--limit must be >= 1")

    source_status, rows = load_shadow_rows(args.limit)
    report = evaluate_shadow_evidence(
        rows,
        ShadowEvidenceRequirements(
            min_microcycles=args.min_microcycles,
            min_events=args.min_events,
        ),
    )
    report["source_status"] = source_status
    if source_status != "loaded":
        report["ready_for_cutover_review"] = False
        report["blockers"] = [
            {
                "code": "SHADOW_AUDIT_TABLE_UNAVAILABLE",
                "source_status": source_status,
            },
            *report["blockers"],
        ]

    print(
        "PLANNING_V1_SHADOW_EVIDENCE "
        + json.dumps(report, ensure_ascii=False, sort_keys=True, default=str)
    )
    if args.require_ready and not report["ready_for_cutover_review"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
