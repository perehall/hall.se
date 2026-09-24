#!/usr/bin/env python3
"""Build a deterministic relational shadow payload from canonical training JSON.

This module is intentionally database-agnostic. Phase 1 keeps GitHub JSON as
source-of-truth; these functions only map that state into stable relational
records that a later writer can upsert into Supabase/PostgreSQL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from training_contracts import ACTIVITY_FAMILY

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

DOCUMENT_FILES = {
    "goal": "goal.json",
    "planning_policy": "planning_policy.json",
    "athlete_state": "athlete_state.json",
    "training_strategy": "training_strategy.json",
    "plan": "plan.json",
    "upcoming_week": "upcoming_week.json",
    "microcycle_decision": "microcycle_decision.json",
    "mesocycle_decision": "mesocycle_decision.json",
    "coach": "coach.json",
    "activity_overrides": "activity_overrides.json",
    "dashboard_summary": "dashboard_summary.json",
    "settings": "settings.json",
}


def load_json(path: Path, *, optional: bool = False) -> dict[str, Any]:
    if optional and not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def local_date(activity: dict[str, Any]) -> str:
    # start_date_local currently carries a local wall-clock value with a
    # misleading trailing Z. Never parse it as UTC. Only its YYYY-MM-DD part is
    # used; the actual timestamp comes from start_date.
    value = activity.get("start_date_local") or activity.get("start_date")
    if not isinstance(value, str) or len(value) < 10:
        raise RuntimeError(f"Activity {activity.get('id')}: local/start date missing")
    return value[:10]


def activity_family(activity: dict[str, Any]) -> str | None:
    sport = str(activity.get("sport_type") or "")
    return ACTIVITY_FAMILY.get(sport)


def activity_records(activities_doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    activities: list[dict[str, Any]] = []
    laps: list[dict[str, Any]] = []

    for activity in activities_doc.get("activities") or []:
        source_id = str(activity["id"])
        started_at = activity.get("start_date")
        if not started_at:
            raise RuntimeError(f"Activity {source_id}: start_date missing")

        raw = dict(activity)
        raw.pop("laps", None)
        activities.append(
            {
                "provider": "strava",
                "provider_activity_id": source_id,
                "name": activity.get("name"),
                "sport_type": activity.get("sport_type"),
                "source_sport_type": activity.get("source_sport_type"),
                "sport_family": activity_family(activity),
                "display_label": activity.get("display_label"),
                "classification": activity.get("classification"),
                "started_at": started_at,
                "local_date": local_date(activity),
                "timezone": "Europe/Stockholm",
                "distance_m": activity.get("distance_m"),
                "moving_time_s": activity.get("moving_time_s"),
                "elapsed_time_s": activity.get("elapsed_time_s"),
                "total_elevation_gain_m": activity.get("total_elevation_gain_m"),
                "average_heartrate": activity.get("average_heartrate"),
                "max_heartrate": activity.get("max_heartrate"),
                "average_watts": activity.get("average_watts"),
                "weighted_average_watts": activity.get("weighted_average_watts"),
                "calories": activity.get("calories"),
                "device_name": activity.get("device_name"),
                "gear_id": activity.get("gear_id"),
                "gear_name": activity.get("gear_name"),
                "plan_relation": activity.get("plan_relation"),
                "raw": raw,
            }
        )

        for index, lap in enumerate(activity.get("laps") or []):
            laps.append(
                {
                    "provider": "strava",
                    "provider_activity_id": source_id,
                    "lap_ordinal": index + 1,
                    "lap_index": int(lap.get("lap_index", index)),
                    "name": lap.get("name"),
                    "elapsed_time_s": lap.get("elapsed_time_s"),
                    "moving_time_s": lap.get("moving_time_s"),
                    "distance_m": lap.get("distance_m"),
                    "average_speed_mps": lap.get("average_speed"),
                    "average_heartrate": lap.get("average_heartrate"),
                    "max_heartrate": lap.get("max_heartrate"),
                    "average_watts": lap.get("average_watts"),
                    "average_cadence": lap.get("average_cadence"),
                    "raw": dict(lap),
                }
            )
    return activities, laps


def override_and_feedback_records(overrides_doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    overrides: list[dict[str, Any]] = []
    feedback: list[dict[str, Any]] = []

    for activity_id, source in sorted((overrides_doc.get("overrides") or {}).items()):
        user_report = str(source.get("user_report") or "").strip()
        overrides.append(
            {
                "provider": "strava",
                "provider_activity_id": str(activity_id),
                "sport_type": source.get("sport"),
                "classification": source.get("classification"),
                "display_label": source.get("display_label"),
                "source_sport_type": source.get("source_sport_type"),
                "garmin_activity_type": source.get("garmin_activity_type"),
                "plan_relation": source.get("plan_relation"),
                "user_report": user_report or None,
                "reason": source.get("reason"),
                "raw": dict(source),
            }
        )

        structured = source.get("training_feedback")
        if isinstance(structured, dict):
            event_key = str(structured.get("event_key") or "").strip()
            if not event_key:
                event_key = "feedback:" + activity_id + ":" + canonical_hash(structured)[:20]
            feedback.append(
                {
                    "provider": "strava",
                    "provider_activity_id": str(activity_id),
                    "source": "training_gui",
                    "operation": structured.get("operation"),
                    "feedback_text": structured.get("text") or None,
                    "rpe": structured.get("rpe"),
                    "feeling": list(structured.get("feeling") or []),
                    "event_key": event_key,
                    "submitted_at": structured.get("submitted_at") or None,
                    "raw": dict(structured),
                }
            )
        elif user_report:
            feedback.append(
                {
                    "provider": "strava",
                    "provider_activity_id": str(activity_id),
                    "source": "legacy_override",
                    "operation": None,
                    "feedback_text": user_report,
                    "rpe": None,
                    "feeling": [],
                    "event_key": "legacy:" + activity_id + ":" + canonical_hash(user_report)[:20],
                    "submitted_at": None,
                    "raw": {"user_report": user_report},
                }
            )
    return overrides, feedback


def goal_records(goal_doc: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for goal in goal_doc.get("development_goals") or []:
        rows.append(
            {
                "goal_id": goal["id"],
                "goal_type": goal.get("type") or "development",
                "role": goal.get("role"),
                "status": goal.get("status") or "active",
                "title": goal.get("label") or goal["id"],
                "objective": goal.get("objective"),
                "event_name": None,
                "event_date": None,
                "sport": None,
                "target": None,
                "priority_class": None,
                "payload": dict(goal),
            }
        )
    for goal in goal_doc.get("performance_goals") or []:
        rows.append(
            {
                "goal_id": goal["id"],
                "goal_type": "performance",
                "role": goal.get("role"),
                "status": goal.get("status") or "active",
                "title": goal.get("event") or goal["id"],
                "objective": goal.get("principle"),
                "event_name": goal.get("event"),
                "event_date": goal.get("event_date"),
                "sport": goal.get("sport"),
                "target": goal.get("target"),
                "priority_class": goal.get("priority_class"),
                "payload": dict(goal),
            }
        )
    return rows


def generated_at_for_document(key: str, doc: dict[str, Any]) -> str | None:
    if key == "coach":
        return doc.get("last_run_utc")
    if key == "activities":
        return doc.get("last_sync_utc")
    return doc.get("generated_at_utc") or doc.get("generated_at")


def document_records(documents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for key, doc in sorted(documents.items()):
        if not doc:
            continue
        rows.append(
            {
                "document_key": key,
                "schema_version": doc.get("schema_version"),
                "generated_at": generated_at_for_document(key, doc),
                "source_hash": canonical_hash(doc),
                "payload": doc,
            }
        )
    return rows


def mesocycle_record(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "title": doc.get("title") or doc["id"],
        "decision": doc.get("decision"),
        "start_date": doc["start_date"],
        "end_date": doc["end_date"],
        "evaluation_date": doc.get("evaluation_date"),
        "duration_weeks": doc.get("duration_weeks"),
        "goal_contribution": doc.get("goal_contribution"),
        "hypothesis": doc.get("hypothesis"),
        "source": doc.get("source"),
        "source_hash": doc.get("source_hash"),
        "goal_hash": doc.get("goal_hash"),
        "generated_at": doc.get("generated_at_utc"),
        "payload": doc,
    }


def microcycle_records(
    plan_doc: dict[str, Any],
    upcoming_doc: dict[str, Any],
    microcycle_decision: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    decision_week = microcycle_decision.get("week_start")

    for plan in (plan_doc, upcoming_doc):
        meta = plan.get("meta") or {}
        microcycle_id = meta.get("microcycle_id")
        if not microcycle_id:
            continue
        decision = microcycle_decision if meta.get("week_start") == decision_week else {}
        payload = {"plan_meta": meta}
        if decision:
            payload["decision"] = decision
        rows.append(
            {
                "id": microcycle_id,
                "mesocycle_id": meta["mesocycle_id"],
                "microcycle_index": meta.get("microcycle_index"),
                "week_start": meta["week_start"],
                "week_key": plan.get("week_key") or f"{meta['week_start']}",
                "rationale": decision.get("rationale"),
                "planner_revision": decision.get("planner_revision"),
                "source": decision.get("source"),
                "source_hash": decision.get("source_hash"),
                "generated_at": decision.get("generated_at_utc"),
                "payload": payload,
            }
        )
    return rows


def workout_key(day: dict[str, Any], meta: dict[str, Any] | None = None) -> str:
    meta = meta or {}
    microcycle_id = str(day.get("microcycle_id") or meta.get("microcycle_id") or "").strip()
    if not microcycle_id:
        raise RuntimeError(f"Planned day {day.get('date')}: microcycle_id missing in day and plan meta")
    slot = str(day.get("microcycle_slot") or "").strip()
    if not slot:
        slot = f"day-{day.get('microcycle_day') or day.get('date')}"
    return f"{microcycle_id}:{day['date']}:{slot}"


def workout_records(*plans: dict[str, Any]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for plan in plans:
        meta = plan.get("meta") or {}
        for day in plan.get("days") or []:
            key = workout_key(day, meta)
            mesocycle_id = day.get("mesocycle_id") or meta.get("mesocycle_id")
            microcycle_id = day.get("microcycle_id") or meta.get("microcycle_id")
            if not mesocycle_id or not microcycle_id:
                raise RuntimeError(
                    f"Planned day {day.get('date')}: mesocycle/microcycle context missing"
                )
            rows[key] = {
                "workout_key": key,
                "mesocycle_id": mesocycle_id,
                "microcycle_id": microcycle_id,
                "scheduled_date": day["date"],
                "microcycle_day": day.get("microcycle_day"),
                "slot_key": day.get("microcycle_slot"),
                "sport": day.get("sport"),
                "classification": day.get("classification"),
                "status": day.get("status"),
                "planning_status": day.get("planning_status"),
                "session": day["session"],
                "priority_role": day.get("priority_role"),
                "manual_lock": bool(day.get("manual_lock", False)),
                "reason": day.get("reason"),
                "development_focus": day.get("development_focus"),
                "stimuli": list(day.get("stimuli") or []),
                "linked_provider": "strava" if day.get("activity_id") is not None else None,
                "linked_provider_activity_id": str(day["activity_id"]) if day.get("activity_id") is not None else None,
                "payload": day,
            }
    return [rows[key] for key in sorted(rows)]


def coach_records(coach_doc: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in coach_doc.get("analyses") or []:
        assessment = entry.get("assessment") or {}
        action = entry.get("plan_action") or {}
        auto = entry.get("auto_apply") or {}
        rows.append(
            {
                "provider": "strava",
                "provider_activity_id": str(entry["activity_id"]),
                "generated_at": entry["generated_at_utc"],
                "model": entry.get("model"),
                "confidence": assessment.get("confidence"),
                "summary": assessment.get("summary"),
                "load_interpretation": assessment.get("load_interpretation"),
                "plan_action": action.get("action"),
                "target_date": action.get("target_date") or None,
                "action_reason": action.get("reason"),
                "recommendation": action.get("recommendation"),
                "requires_approval": bool(action.get("requires_approval", False)),
                "auto_applied": bool(auto.get("applied", False)),
                "payload": entry,
            }
        )
    return rows


def build_shadow_payload(data_dir: Path = DATA) -> dict[str, Any]:
    activities_doc = load_json(data_dir / "activities.json")
    overrides_doc = load_json(data_dir / "activity_overrides.json")
    goal_doc = load_json(data_dir / "goal.json")
    mesocycle_doc = load_json(data_dir / "mesocycle_decision.json")
    microcycle_doc = load_json(data_dir / "microcycle_decision.json")
    plan_doc = load_json(data_dir / "plan.json")
    upcoming_doc = load_json(data_dir / "upcoming_week.json")
    coach_doc = load_json(data_dir / "coach.json")

    documents = {
        key: load_json(data_dir / filename, optional=True)
        for key, filename in DOCUMENT_FILES.items()
    }
    documents["activities"] = activities_doc

    activities, laps = activity_records(activities_doc)
    overrides, feedback = override_and_feedback_records(overrides_doc)

    activity_keys = {row["provider_activity_id"] for row in activities}
    referenced = {
        row["provider_activity_id"]
        for row in overrides + feedback + coach_records(coach_doc)
    }
    missing = sorted(referenced - activity_keys)
    if missing:
        raise RuntimeError(f"Shadow model references missing activities: {missing[:10]}")

    payload = {
        "contract_version": 1,
        "source_hash": canonical_hash(
            {
                "activities": activities_doc,
                "activity_overrides": overrides_doc,
                "goal": goal_doc,
                "mesocycle": mesocycle_doc,
                "microcycle": microcycle_doc,
                "plan": plan_doc,
                "upcoming_week": upcoming_doc,
                "coach": coach_doc,
            }
        ),
        "activities": activities,
        "activity_laps": laps,
        "activity_overrides": overrides,
        "activity_feedback": feedback,
        "training_goals": goal_records(goal_doc),
        "state_documents": document_records(documents),
        "mesocycles": [mesocycle_record(mesocycle_doc)],
        "microcycles": microcycle_records(plan_doc, upcoming_doc, microcycle_doc),
        "planned_workouts": workout_records(plan_doc, upcoming_doc),
        "coach_evaluations": coach_records(coach_doc),
    }
    payload["counts"] = {
        key: len(value)
        for key, value in payload.items()
        if isinstance(value, list)
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    payload = build_shadow_payload(args.data_dir)
    if args.output:
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"SUPABASE_SHADOW_MODEL_OK output={args.output} counts={payload['counts']}")
    else:
        print(json.dumps({"source_hash": payload["source_hash"], "counts": payload["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
