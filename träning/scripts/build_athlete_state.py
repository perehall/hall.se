#!/usr/bin/env python3
"""Build a deterministic athlete-state fact layer from recorded training.

This file deliberately contains no coaching decisions. It summarizes only
observable training facts and explicit user reports so downstream planners can
reason without reconstructing or inventing history.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from canonical_plan import planned_workouts as canonical_planned_workouts
from capability_registry import CAPABILITY_REGISTRY
from capability_state import build_capability_states
from coach_rules import activity_family, activity_local_date
from dose_response import build_dose_response, build_load_windows
from supabase_activity_backend import load_activities_for_runtime
from training_profile import build_training_profile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ACTIVITIES_FILE = DATA / "activities.json"
PERFORMANCE_FILE = DATA / "performance_history.json"
REVIEWS_DIR = DATA / "week_reviews"
OUTPUT_FILE = DATA / "athlete_state.json"
PLAN_FILE = DATA / "plan.json"
UPCOMING_FILE = DATA / "upcoming_week.json"
WEEKS_DIR = DATA / "weeks"
SCHEMA_VERSION = 1
LOOKBACK_DAYS = 56

INTERVAL_RE = re.compile(r"(?P<sets>\d+)\s*[x×]\s*(?P<minutes>\d+(?:[.,]\d+)?)\s*min", re.IGNORECASE)
HILL_RE = re.compile(r"(?P<sets>\d+)\s*[x×]\s*(?P<reps>\d+)\s*(?:backar|backintervaller|intervaller)\b", re.IGNORECASE)
SWIM_DISTANCE_RE = re.compile(r"(?P<distance>\d[\d ]*)\s*m\b|(?P<km>\d+(?:[.,]\d+)?)\s*k\b", re.IGNORECASE)


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def duration_s(activity):
    value = activity.get("elapsed_time_s")
    if value is None:
        value = activity.get("moving_time_s")
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def explicit_report_evidence(activity):
    report = str(activity.get("user_report") or "").strip()
    if not report:
        return []

    evidence = []
    lower = report.lower()
    interval = INTERVAL_RE.search(report)
    if interval and any(word in lower for word in ("trösk", "tempo", "threshold")):
        sets = int(interval.group("sets"))
        minutes = float(interval.group("minutes").replace(",", "."))
        evidence.append(
            {
                "capability": "run_threshold",
                "kind": "explicit_user_report",
                "protocol": f"{sets}x{minutes:g}min",
                "work_minutes": round(sets * minutes, 1),
                "text": report,
            }
        )

    sport = str(activity.get("sport_type") or activity.get("display_label") or "").lower()
    if "swim" in sport or "sim" in sport:
        if "trösk" in lower or "threshold" in lower:
            distance_m = None
            distance_match = SWIM_DISTANCE_RE.search(report)
            if distance_match:
                if distance_match.group("distance"):
                    distance_m = int(distance_match.group("distance").replace(" ", ""))
                elif distance_match.group("km"):
                    distance_m = int(round(float(distance_match.group("km").replace(",", ".")) * 1000))
            evidence.append(
                {
                    "capability": "swim_threshold",
                    "kind": "explicit_user_report",
                    "protocol": "aerob+threshold" if ("aerob" in lower or "aerobic" in lower) else "threshold",
                    "distance_m": distance_m,
                    "text": report,
                }
            )

    hill = HILL_RE.search(report)
    if hill and "back" in lower:
        sets = int(hill.group("sets"))
        reps = int(hill.group("reps"))
        evidence.append(
            {
                "capability": "run_hill_quality",
                "kind": "explicit_user_report",
                "protocol": f"{sets}x{reps}",
                "repetitions": sets * reps,
                "text": report,
            }
        )
    return evidence


def archived_planned_workouts(*, today=None, lookback_days=LOOKBACK_DAYS, weeks_dir=WEEKS_DIR):
    today = today or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    start = today - timedelta(days=lookback_days - 1)
    rows = []
    if not weeks_dir.exists():
        return rows

    for path in sorted(weeks_dir.glob("????-W??.json")):
        document = load_json(path, {})
        try:
            workouts = canonical_planned_workouts(
                document,
                context=f"athlete-state archive {path.name}",
            )
        except Exception:
            continue
        for workout in workouts:
            try:
                day = date.fromisoformat(str(workout.get("date") or ""))
            except (TypeError, ValueError):
                continue
            if start <= day <= today:
                rows.append(workout)

    deduped = {}
    for workout in rows:
        identity = str(workout.get("workout_key") or "").strip()
        if not identity:
            identity = "|".join(
                [
                    str(workout.get("date") or ""),
                    str(workout.get("microcycle_slot") or ""),
                    str(workout.get("session") or ""),
                ]
            )
        deduped[identity] = workout
    return list(deduped.values())


def recent_reviews(limit=6):
    rows = []
    if not REVIEWS_DIR.exists():
        return rows
    for path in sorted(REVIEWS_DIR.glob("????-W??.json"), reverse=True):
        doc = load_json(path, {})
        assessment = doc.get("assessment") or {}
        if not assessment:
            continue
        rows.append(
            {
                "week_key": doc.get("week_key"),
                "week_start": doc.get("week_start"),
                "week_end": doc.get("week_end"),
                "summary": assessment.get("summary"),
                "load_continuity": assessment.get("load_continuity"),
                "key_lesson": assessment.get("key_lesson"),
                "next_week_implication": assessment.get("next_week_implication"),
                "uncertainties": assessment.get("uncertainties") or [],
            }
        )
        if len(rows) >= limit:
            break
    return rows


def build_state(
    activities_state,
    performance_history,
    *,
    today=None,
    lookback_days=LOOKBACK_DAYS,
    planned_workouts=None,
    previous_state=None,
):
    today = today or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    start = today - timedelta(days=lookback_days - 1)

    planned_workouts = list(planned_workouts or [])
    previous_profiles = {
        str(row.get("id")): row.get("training_profile")
        for row in ((previous_state or {}).get("recent_sessions") or [])
        if row.get("id") is not None and isinstance(row.get("training_profile"), dict)
    }

    selected = []
    for activity in activities_state.get("activities") or []:
        local = activity_local_date(activity)
        if not local:
            continue
        try:
            day = date.fromisoformat(local)
        except ValueError:
            continue
        if start <= day <= today:
            selected.append((day, activity))
    selected.sort(key=lambda pair: (pair[0], str(pair[1].get("id") or "")))

    summary = defaultdict(lambda: {"activity_count": 0, "time_s": 0, "distance_m": 0.0, "active_days": set()})
    recent_sessions = []
    activity_by_id = {}
    evidence = []
    for day, activity in selected:
        family = activity_family(activity) or str(activity.get("sport_type") or "other").lower()
        classification = activity.get("classification") or "training"
        row = summary[family]
        row["activity_count"] += 1
        row["time_s"] += duration_s(activity)
        distance = number(activity.get("distance_m"))
        if distance is not None and distance >= 0:
            row["distance_m"] += distance
        row["active_days"].add(day.isoformat())

        activity_by_id[str(activity.get("id"))] = activity
        recent_sessions.append(
            {
                "id": activity.get("id"),
                "date": day.isoformat(),
                "family": family,
                "label": activity.get("display_label") or activity.get("sport_type"),
                "classification": classification,
                "elapsed_time_s": duration_s(activity),
                "distance_m": activity.get("distance_m"),
                "elevation_gain_m": activity.get("total_elevation_gain_m"),
                "average_heartrate": activity.get("average_heartrate"),
                "max_heartrate": activity.get("max_heartrate"),
                "user_report": activity.get("user_report"),
            }
        )
        evidence.extend(
            {
                **item,
                "activity_id": activity.get("id"),
                "date": day.isoformat(),
            }
            for item in explicit_report_evidence(activity)
        )

    # Performance fingerprints are deterministic and only included when their
    # source activity is within the same lookback horizon.
    performance = []
    for entry in performance_history.get("entries") or []:
        text = entry.get("activity_date")
        try:
            day = date.fromisoformat(text)
        except (TypeError, ValueError):
            continue
        if start <= day <= today:
            performance.append(entry)
            if entry.get("marker_id") == "run-threshold-control":
                total_work = number((entry.get("summary") or {}).get("total_work_s"))
                evidence.append(
                    {
                        "capability": "run_threshold",
                        "kind": "performance_fingerprint",
                        "activity_id": entry.get("activity_id"),
                        "date": text,
                        "protocol": entry.get("protocol_key"),
                        "work_minutes": round(total_work / 60.0, 1) if total_work is not None else None,
                        "summary": entry.get("summary"),
                        "comparison": entry.get("comparison"),
                    }
                )

    performance_by_activity = {
        str(entry.get("activity_id")): entry
        for entry in performance
        if entry.get("activity_id") is not None
    }
    for row in recent_sessions:
        activity_id = str(row.get("id") or "")
        activity = activity_by_id.get(activity_id)
        if not activity:
            continue
        row["training_profile"] = build_training_profile(
            activity,
            planned_workouts=planned_workouts,
            performance_entry=performance_by_activity.get(activity_id),
            previous_profile=previous_profiles.get(activity_id),
        )

    # Sport-specific observed ranges. These are facts, not prescriptions.
    run_sessions = [row for row in recent_sessions if row["family"] == "run" and row["classification"] != "recreation"]
    swim_sessions = [row for row in recent_sessions if row["family"] == "swim" and row["classification"] != "recreation"]
    bike_sessions = [row for row in recent_sessions if row["family"] == "bike" and row["classification"] != "recreation"]
    strength_sessions = [row for row in recent_sessions if row["family"] == "strength" and row["classification"] != "recreation"]

    def max_fact(rows, field):
        usable = [row for row in rows if isinstance(row.get(field), (int, float))]
        if not usable:
            return None
        best = max(usable, key=lambda row: row[field])
        return {"activity_id": best.get("id"), "date": best.get("date"), field: best.get(field)}

    by_family = {}
    for family, row in sorted(summary.items()):
        by_family[family] = {
            "activity_count": row["activity_count"],
            "time_s": row["time_s"],
            "distance_m": round(row["distance_m"], 1),
            "active_days": len(row["active_days"]),
        }

    capability_facts = {
        "run_threshold": {
            "evidence": [item for item in evidence if item.get("capability") == "run_threshold"],
        },
        "run_hill_quality": {
            "evidence": [item for item in evidence if item.get("capability") == "run_hill_quality"],
        },
        "run_easy_distance": {
            "longest_distance": max_fact(run_sessions, "distance_m"),
            "longest_duration": max_fact(run_sessions, "elapsed_time_s"),
        },
        "swim_aerobic": {
            "longest_distance": max_fact(swim_sessions, "distance_m"),
            "session_count": len(swim_sessions),
        },
        "swim_threshold": {
            "evidence": [item for item in evidence if item.get("capability") == "swim_threshold"],
        },
        "mtb_technical": {
            "longest_duration": max_fact(bike_sessions, "elapsed_time_s"),
            "session_count": len(bike_sessions),
        },
        "strength_unilateral": {
            "longest_duration": max_fact(strength_sessions, "elapsed_time_s"),
            "session_count": len(strength_sessions),
        },
    }

    profile_exposures = {key: [] for key in CAPABILITY_REGISTRY}
    for row in recent_sessions:
        profile = row.get("training_profile") or {}
        confirmed = {
            str(item.get("key"))
            for item in (profile.get("stimuli") or [])
            if isinstance(item, dict)
            and item.get("status") == "confirmed"
            and str(item.get("key") or "")
        }
        credits = {
            str(value)
            for value in (profile.get("planning_credits") or [])
            if str(value or "")
        }
        for capability in sorted((confirmed | credits).intersection(CAPABILITY_REGISTRY)):
            profile_exposures[capability].append(
                {
                    "activity_id": row.get("id"),
                    "date": row.get("date"),
                    "source": (
                        "confirmed_stimulus"
                        if capability in confirmed
                        else "plan_matched"
                    ),
                    "family": row.get("family"),
                }
            )

    for capability in CAPABILITY_REGISTRY:
        fact = capability_facts.setdefault(capability, {})
        fact["verified_exposures"] = profile_exposures.get(capability, [])[-12:]
        fact["verified_exposure_count"] = len(profile_exposures.get(capability, []))

    dose_response = build_dose_response(recent_sessions, evidence, today=today)
    capability_states = build_capability_states(recent_sessions, dose_response)
    load_windows = build_load_windows(recent_sessions, today=today)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "fact_window": {
            "start": start.isoformat(),
            "end": today.isoformat(),
            "lookback_days": lookback_days,
        },
        "by_family": by_family,
        "recent_sessions": recent_sessions[-24:],
        "capability_facts": capability_facts,
        "dose_response": dose_response,
        "capability_states": capability_states,
        "load_windows": load_windows,
        "performance_fingerprints": performance[-12:],
        "recent_week_reviews": recent_reviews(),
        "interpretation_boundary": (
            "Dokumentet innehåller observerade fakta, uttryckliga användarrapporter och en konservativ "
            "klassificering av demonstrerad/tolererad/absorberad dos samt verifierad capability-state. 24–72 h-signaler är kontext och "
            "tillskrivs inte kausalt ett tidigare pass. Dokumentet anger inte optimal belastning, "
            "återhämtning, skaderisk eller framtida träningsdos."
        ),
    }


def main():
    activities, activity_source = load_activities_for_runtime(ACTIVITIES_FILE)
    performance = load_json(PERFORMANCE_FILE, {"entries": []})
    previous_state = load_json(OUTPUT_FILE, {})
    plan = load_json(PLAN_FILE, {})
    upcoming = load_json(UPCOMING_FILE, {})
    today = date.today()
    planned = [
        *archived_planned_workouts(today=today),
        *canonical_planned_workouts(plan, context="athlete-state current plan"),
        *canonical_planned_workouts(upcoming, context="athlete-state upcoming plan"),
    ]
    state = build_state(
        activities,
        performance,
        planned_workouts=planned,
        previous_state=previous_state,
        today=today,
    )
    write_json(OUTPUT_FILE, state)
    print(
        "Athlete state OK: "
        f"window={state['fact_window']['start']}..{state['fact_window']['end']} "
        f"sessions={len(state['recent_sessions'])} "
        f"activities_source={activity_source['source']} "
        f"verified={bool(activity_source.get('verified'))}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
