#!/usr/bin/env python3
"""Update durable athlete-profile plan generation status from CI."""
from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MICRO = ROOT / "data" / "microcycle_decision.json"


def result_week_key() -> str | None:
    if not MICRO.exists():
        return None
    try:
        payload = json.loads(MICRO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = str(payload.get("week_key") or "").strip()
    return value or None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--status", required=True, choices=("running", "completed", "failed"))
    parser.add_argument("--error", default=None)
    args = parser.parse_args()

    request_id = str(uuid.UUID(args.request_id))
    database_url = str(os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not database_url:
        raise RuntimeError("SUPABASE_DB_URL saknas")

    import psycopg  # type: ignore

    week_key = result_week_key() if args.status == "completed" else None
    with psycopg.connect(database_url, sslmode="require", connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select public.training_set_plan_generation_status(
                  %s::uuid, %s::text, %s::text, %s::text
                )
                """,
                (request_id, args.status, args.error, week_key),
            )
            row = cur.fetchone()
        conn.commit()

    print(
        "PLAN_GENERATION_STATUS "
        + json.dumps(
            {
                "request_id": request_id,
                "status": args.status,
                "result_week_key": week_key,
                "ack": row[0] if row else None,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
