#!/usr/bin/env python3
"""Run Planning Engine v1 in non-authoritative shadow mode from live canonical sources.

The only permitted database write is an append-only row in
training.planning_v1_shadow_runs, and even that occurs only when the audit
table is already deployed. Planning authority, planned workouts, rendering and
device synchronization are outside this process.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from planning_v1_readiness import DEFAULT_DATA, build_readiness_report
from training_core.application.planning_shadow import (
    ShadowPlanningRunInput,
    run_shadow_planning,
)
from training_core.application.planning_shadow_audit import (
    ShadowRunAuditRecord,
    build_shadow_audit_record,
)


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def _database_url() -> str:
    value = str(os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not value:
        raise RuntimeError("SUPABASE_DB_URL is missing")
    return value


def _audit_row_values(record: ShadowRunAuditRecord, Jsonb: Any) -> dict[str, Any]:
    row = record.as_db_row()
    for key in (
        "semantic_input",
        "plan_content",
        "objective_vector",
        "decision_trace",
    ):
        if row[key] is not None:
            row[key] = Jsonb(row[key])
    return row


def append_audit_if_available(record: ShadowRunAuditRecord) -> str:
    """Append shadow evidence only when its dedicated table is already deployed."""

    import psycopg  # type: ignore
    from psycopg import sql  # type: ignore
    from psycopg.types.json import Jsonb  # type: ignore

    with psycopg.connect(
        _database_url(),
        sslmode="require",
        connect_timeout=15,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select to_regclass('training.planning_v1_shadow_runs')"
            )
            if cur.fetchone()[0] is None:
                conn.rollback()
                return "table_missing"

            row = _audit_row_values(record, Jsonb)
            columns = tuple(row)
            query = sql.SQL(
                "insert into training.planning_v1_shadow_runs ({}) "
                "values ({}) on conflict do nothing"
            ).format(
                sql.SQL(", ").join(map(sql.Identifier, columns)),
                sql.SQL(", ").join(sql.Placeholder() for _ in columns),
            )
            cur.execute(query, tuple(row[column] for column in columns))
            inserted = cur.rowcount
            conn.commit()
            return "appended" if inserted == 1 else "already_exists"


def _workout_summary(result) -> list[dict[str, Any]]:
    if result.solve_result is None or result.solve_result.plan is None:
        return []
    return [
        {
            "date": item.local_date.isoformat(),
            "recipe_id": item.recipe_id,
            "dose_option_id": item.dose_option_id,
            "obligations": [
                contribution.obligation_id
                for contribution in item.obligation_contributions
            ],
        }
        for item in result.solve_result.plan.workouts
    ]


def run_live_shadow(
    *,
    data_dir: Path,
    affected_from: date,
    affected_until: date,
    planning_date: date,
    future_context_through: date,
    event_key: str,
    trigger_source: str,
    microcycle_key: str | None,
    audit_if_available: bool,
) -> tuple[int, dict[str, Any]]:
    readiness = build_readiness_report(
        data_dir,
        affected_from=affected_from,
        affected_until=affected_until,
        planning_date=planning_date,
        future_context_through=future_context_through,
        include_internal=True,
    )
    assembly = readiness.pop("_assembly_result")
    history_from = readiness.pop("_history_from")
    history_through = readiness.pop("_history_through")
    readiness.pop("_future_context_through")

    if not readiness["ready"]:
        return 2, {
            "readiness": readiness,
            "solver_ran": False,
            "planning_state_mutated": False,
            "audit_status": "not_attempted",
        }

    if assembly.bundle is None or history_from is None or history_through is None:
        raise RuntimeError(
            "ready source assembly lacks bundle/history coverage"
        )

    request = ShadowPlanningRunInput(
        affected_from=affected_from,
        affected_until=affected_until,
        history_from=history_from,
        history_through=history_through,
        future_context_through=future_context_through,
        projections=assembly.bundle,
    )
    result = run_shadow_planning(request)
    if not result.ran_solver or result.solve_result is None:
        raise RuntimeError("ready canonical assembly did not run shadow solver")

    record = build_shadow_audit_record(
        request,
        result,
        event_key=event_key,
        trigger_source=trigger_source,
        microcycle_key=microcycle_key,
    )
    audit_status = (
        append_audit_if_available(record)
        if audit_if_available
        else "skipped"
    )
    solved = result.solve_result
    return 0, {
        "readiness": {
            "ready": True,
            "source_revision": readiness["source_revision"],
            "component_revisions": readiness["component_revisions"],
            "blockers": [],
        },
        "solver_ran": True,
        "solver_status": solved.authority_state.status.value,
        "blocked_reason_codes": list(
            solved.authority_state.blocked_reason_codes
        ),
        "semantic_input_hash": solved.authority_state.semantic_input_hash,
        "plan_content_hash": solved.authority_state.plan_content_hash,
        "workouts": _workout_summary(result),
        "planning_state_mutated": False,
        "audit_status": audit_status,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--affected-from", type=_iso_date, required=True)
    parser.add_argument("--affected-until", type=_iso_date, required=True)
    parser.add_argument("--planning-date", type=_iso_date, required=True)
    parser.add_argument("--future-context-through", type=_iso_date, required=True)
    parser.add_argument("--event-key", required=True)
    parser.add_argument(
        "--trigger-source",
        default="github_actions_shadow",
    )
    parser.add_argument("--microcycle-key")
    parser.add_argument(
        "--audit-if-available",
        action="store_true",
    )
    args = parser.parse_args(argv)

    code, summary = run_live_shadow(
        data_dir=args.data_dir,
        affected_from=args.affected_from,
        affected_until=args.affected_until,
        planning_date=args.planning_date,
        future_context_through=args.future_context_through,
        event_key=args.event_key,
        trigger_source=args.trigger_source,
        microcycle_key=args.microcycle_key,
        audit_if_available=args.audit_if_available,
    )
    print(
        "PLANNING_V1_SHADOW_RESULT "
        + json.dumps(summary, ensure_ascii=False, sort_keys=True)
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
