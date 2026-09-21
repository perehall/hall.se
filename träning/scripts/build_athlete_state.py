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

from coach_rules import activity_family, activity_local_date

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ACTIVITIES_FILE = DATA / "activities.json"
PERFORMANCE_FILE = DATA / "performance_history.json"
REVIEWS_DIR = DATA / "week_reviews"
OUTPUT_FILE = DATA / "athlete_state.json"
SCHEMA_VERSION = 1
LOOKBACK_DAYS = 56

INTERVAL_RE = re.compile(r"(?P<sets>\d+)\s*[x×]\s*(?P<minutes>\d+(?:[.,]\d+)?)\s*min", re.IGNORECASE)
HILL_RE = re.compile(r"(?P<sets>\d+)\s*[x×]\s*(?P<reps>\d+)\s*(?:backar|backintervaller|intervaller)\b", re.IGNORECASE)


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


def build_state(activities_state, performance_history, *, today=None, lookback_days=LOOKBACK_DAYS):
    today = today or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    start = today - timedelta(days=lookback_days - 1)

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
        "mtb_technical": {
            "longest_duration": max_fact(bike_sessions, "elapsed_time_s"),
            "session_count": len(bike_sessions),
        },
        "strength_unilateral": {
            "longest_duration": max_fact(strength_sessions, "elapsed_time_s"),
            "session_count": len(strength_sessions),
        },
    }

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
        "performance_fingerprints": performance[-12:],
        "recent_week_reviews": recent_reviews(),
        "interpretation_boundary": (
            "Dokumentet innehåller observerade fakta och uttryckliga användarrapporter. "
            "Det anger inte optimal belastning, återhämtning, skaderisk eller framtida träningsdos."
        ),
    }


def main():
    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    performance = load_json(PERFORMANCE_FILE, {"entries": []})
    state = build_state(activities, performance)
    write_json(OUTPUT_FILE, state)
    print(
        "Athlete state OK: "
        f"window={state['fact_window']['start']}..{state['fact_window']['end']} "
        f"sessions={len(state['recent_sessions'])}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
