#!/usr/bin/env python3
import argparse
import base64
import json
import math
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
HISTORY_FILE = ROOT / "data" / "performance_history.json"
ACTIVITIES_API = "https://intervals.icu/api/v1/athlete/0/activities"
ACTIVITY_API = "https://intervals.icu/api/v1/activity"
SCHEMA_VERSION = 1
RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
SOURCE_PREFERENCE = {"GARMIN": 0, "COROS": 1, "SUUNTO": 2, "WAHOO": 3, "STRAVA": 8}
EXPLICIT_3X8 = re.compile(r"\b3\s*[x×]\s*8(?:\s*min)?\b", re.IGNORECASE)
EXPLICIT_3X10 = re.compile(r"\b3\s*[x×]\s*10(?:\s*min)?\b", re.IGNORECASE)


def load_json(path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def authorization():
    key = os.environ.get("INTERVALS_API_KEY", "").strip()
    if not key:
        return None
    token = base64.b64encode(f"API_KEY:{key}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def request_json(url, auth):
    request = Request(
        url,
        headers={
            "Authorization": auth,
            "Accept": "application/json",
            "User-Agent": "hall-training-performance-analysis/1.0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Intervals.icu HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Intervals.icu kunde inte nås: {exc.reason}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Intervals.icu returnerade inte giltig JSON") from exc


def fetch_activity_list(oldest, newest, auth):
    query = urlencode({"oldest": oldest.isoformat(), "newest": newest.isoformat()})
    data = request_json(f"{ACTIVITIES_API}?{query}", auth)
    if not isinstance(data, list):
        raise RuntimeError("Intervals.icu activities-svar är inte en lista")
    return [row for row in data if isinstance(row, dict)]


def fetch_activity_detail(activity_id, auth):
    data = request_json(f"{ACTIVITY_API}/{activity_id}?intervals=true", auth)
    if not isinstance(data, dict):
        raise RuntimeError("Intervals.icu activity-detail är inte ett objekt")
    return data


def utc_dt(row):
    value = row.get("start_date")
    if not isinstance(value, str) or len(value) < 19:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def local_dt(row):
    value = row.get("start_date_local")
    if not isinstance(value, str) or len(value) < 19:
        return None
    try:
        return datetime.fromisoformat(value[:19])
    except ValueError:
        return None


def sport_name(row):
    return str(row.get("sport_type") or row.get("type") or "").strip().lower()


def sport_compatible(left, right):
    a, b = sport_name(left), sport_name(right)
    if not a or not b:
        return True
    if a in {"run", "trailrun", "virtualrun"}:
        return b in {"run", "trailrun", "virtualrun"}
    return a == b


def match_activity(strava_row, intervals_rows, max_delta_s=600):
    target_utc = utc_dt(strava_row)
    target_local = local_dt(strava_row)
    if target_utc is None and target_local is None:
        return None
    candidates = []
    for row in intervals_rows:
        if not sport_compatible(strava_row, row):
            continue
        when_utc = utc_dt(row)
        when_local = local_dt(row)
        if target_utc is not None and when_utc is not None:
            delta = abs((when_utc - target_utc).total_seconds())
        elif target_local is not None and when_local is not None:
            delta = abs((when_local - target_local).total_seconds())
        else:
            continue
        if delta <= max_delta_s:
            source = str(row.get("source") or "").strip().upper()
            candidates.append((delta, SOURCE_PREFERENCE.get(source, 5), str(row.get("id") or ""), row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    best = candidates[0]
    if len(candidates) > 1 and candidates[1][:2] == best[:2]:
        return None
    return best[3]


def num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def interval_duration(row):
    for key in ("moving_time", "elapsed_time"):
        value = num(row.get(key))
        if value and value > 0:
            return value
    start, end = num(row.get("start_time")), num(row.get("end_time"))
    return end - start if start is not None and end is not None and end > start else None


def work_rows(detail):
    rows = detail.get("icu_intervals") or []
    result = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").strip().upper() not in {"WORK", "INTERVAL"}:
            continue
        duration = interval_duration(row)
        if duration is not None:
            result.append((duration, row))
    return result


def infer_threshold_protocol(activity, detail):
    report = str(activity.get("user_report") or "")
    explicit = None
    if EXPLICIT_3X8.search(report):
        explicit = ("run_threshold:3x8:90s", 480.0, 100.0)
    elif EXPLICIT_3X10.search(report):
        explicit = ("run_threshold:3x10:90s", 600.0, 110.0)

    candidates = [(seconds, row) for seconds, row in work_rows(detail) if 330 <= seconds <= 720]
    if len(candidates) != 3:
        return None

    protocols = [
        ("run_threshold:3x8:90s", 480.0, 75.0),
        ("run_threshold:3x10:90s", 600.0, 90.0),
    ]
    if explicit:
        protocols = [explicit] + [item for item in protocols if item[0] != explicit[0]]

    durations = [seconds for seconds, _ in candidates]
    for key, target, tolerance in protocols:
        if all(abs(seconds - target) <= tolerance for seconds in durations):
            return {
                "marker_id": "run-threshold-control",
                "protocol_key": key,
                "work_rows": [row for _, row in candidates],
            }
    return None


def infer_threshold_from_laps(activity):
    laps = activity.get("laps") or []
    if not isinstance(laps, list):
        return None
    report = str(activity.get("user_report") or "")
    protocols = []
    if EXPLICIT_3X8.search(report):
        protocols.append(("run_threshold:3x8:90s", 480.0, 100.0))
    if EXPLICIT_3X10.search(report):
        protocols.append(("run_threshold:3x10:90s", 600.0, 110.0))
    protocols.extend([
        ("run_threshold:3x8:90s", 480.0, 75.0),
        ("run_threshold:3x10:90s", 600.0, 90.0),
    ])

    rows = []
    for lap in laps:
        if not isinstance(lap, dict):
            continue
        mapped = {
            "moving_time": lap.get("moving_time_s"),
            "elapsed_time": lap.get("elapsed_time_s"),
            "distance": lap.get("distance_m"),
            "average_speed": lap.get("average_speed"),
            "average_heartrate": lap.get("average_heartrate"),
            "max_heartrate": lap.get("max_heartrate"),
            "average_watts": lap.get("average_watts"),
            "average_cadence": lap.get("average_cadence"),
        }
        seconds = interval_duration(mapped)
        if seconds is not None:
            rows.append((seconds, mapped))

    seen = set()
    for key, target, tolerance in protocols:
        if key in seen:
            continue
        seen.add(key)
        matching = [
            (seconds, row)
            for seconds, row in rows
            if abs(seconds - target) <= tolerance
        ]
        if len(matching) == 3:
            matching.sort(key=lambda item: rows.index(item))
            return {
                "marker_id": "run-threshold-control",
                "protocol_key": key,
                "work_rows": [row for _, row in matching],
            }
    return None


def pace_s_per_km(row):
    duration, distance = interval_duration(row), num(row.get("distance"))
    if duration is not None and distance is not None and distance > 0:
        return duration / (distance / 1000.0)
    speed = num(row.get("average_speed"))
    return 1000.0 / speed if speed is not None and speed > 0 else None


def rnd(value, digits=1):
    return None if value is None else round(float(value), digits)


def interval_fact(row, index):
    return {
        "index": index,
        "duration_s": rnd(interval_duration(row)),
        "distance_m": rnd(num(row.get("distance"))),
        "pace_s_per_km": rnd(pace_s_per_km(row)),
        "average_heartrate": rnd(num(row.get("average_heartrate"))),
        "max_heartrate": rnd(num(row.get("max_heartrate"))),
        "average_watts": rnd(num(row.get("average_watts"))),
        "average_cadence": rnd(num(row.get("average_cadence"))),
    }


def avg(rows, field):
    values = [num(row.get(field)) for row in rows]
    values = [value for value in values if value is not None]
    return rnd(mean(values)) if values else None


def fingerprint(activity, source_name, source_activity_id, detected):
    work = [interval_fact(row, i) for i, row in enumerate(detected["work_rows"], 1)]
    first, last = work[0], work[-1]
    summary = {
        "work_interval_count": len(work),
        "total_work_s": rnd(sum(row["duration_s"] or 0 for row in work)),
        "mean_pace_s_per_km": avg(work, "pace_s_per_km"),
        "mean_heartrate": avg(work, "average_heartrate"),
        "mean_watts": avg(work, "average_watts"),
        "first_to_last_pace_delta_s_per_km": (
            rnd(last["pace_s_per_km"] - first["pace_s_per_km"])
            if first["pace_s_per_km"] is not None and last["pace_s_per_km"] is not None else None
        ),
        "first_to_last_hr_delta": (
            rnd(last["average_heartrate"] - first["average_heartrate"])
            if first["average_heartrate"] is not None and last["average_heartrate"] is not None else None
        ),
        "first_to_last_watts_delta": (
            rnd(last["average_watts"] - first["average_watts"])
            if first["average_watts"] is not None and last["average_watts"] is not None else None
        ),
    }
    return {
        "activity_id": activity.get("id"),
        "activity_date": str(activity.get("start_date_local") or activity.get("start_date") or "")[:10],
        "sport_type": activity.get("sport_type"),
        "marker_id": detected["marker_id"],
        "protocol_key": detected["protocol_key"],
        "source": source_name,
        "source_activity_id": source_activity_id,
        "work_intervals": work,
        "summary": summary,
        "comparison": None,
        "comparison_limits": [
            "Samma protokoll och faktiska arbetsintervall krävs.",
            "Väder, vind, underlag och subjektiv ansträngning normaliseras inte om de saknas.",
            "En enskild skillnad är inte i sig bevis på kapacitetsförändring.",
        ],
    }


def add_comparisons(entries):
    previous_by_protocol = {}
    for entry in sorted(entries, key=lambda x: (x.get("activity_date") or "", str(x.get("activity_id")))):
        previous = previous_by_protocol.get(entry.get("protocol_key"))
        if previous:
            cur, old = entry.get("summary") or {}, previous.get("summary") or {}

            def delta(field):
                a, b = num(cur.get(field)), num(old.get(field))
                return rnd(a - b) if a is not None and b is not None else None

            entry["comparison"] = {
                "previous_activity_id": previous.get("activity_id"),
                "previous_activity_date": previous.get("activity_date"),
                "same_protocol": True,
                "mean_pace_delta_s_per_km": delta("mean_pace_s_per_km"),
                "mean_hr_delta": delta("mean_heartrate"),
                "mean_watts_delta": delta("mean_watts"),
                "total_work_delta_s": delta("total_work_s"),
            }
        else:
            entry["comparison"] = None
        previous_by_protocol[entry.get("protocol_key")] = entry


def candidates(state, oldest):
    result = []
    for activity in state.get("activities") or []:
        if activity.get("sport_type") not in RUN_TYPES or activity.get("classification") == "recreation":
            continue
        text = activity.get("start_date_local") or activity.get("start_date") or ""
        try:
            day = datetime.fromisoformat(text[:10]).date()
        except (TypeError, ValueError):
            continue
        if day >= oldest:
            result.append(activity)
    return result


def sync(state, history, intervals_rows, fetch_detail, oldest):
    entries = {
        str(item.get("activity_id")): item
        for item in history.get("entries") or []
        if isinstance(item, dict) and item.get("activity_id") is not None
    }
    updated = 0
    skipped = 0
    for activity in candidates(state, oldest):
        detected = None
        source_name = None
        source_activity_id = None

        matched = match_activity(activity, intervals_rows)
        if matched and matched.get("id") not in (None, ""):
            try:
                detail = fetch_detail(matched["id"])
            except Exception:
                detail = None
            if detail:
                detected = infer_threshold_protocol(activity, detail)
                if detected:
                    source_name = "Intervals.icu"
                    source_activity_id = matched.get("id")

        if not detected:
            detected = infer_threshold_from_laps(activity)
            if detected:
                source_name = "Strava laps"
                source_activity_id = activity.get("id")

        if not detected:
            skipped += 1
            continue

        entries[str(activity["id"])] = fingerprint(
            activity,
            source_name,
            source_activity_id,
            detected,
        )
        updated += 1

    ordered = sorted(entries.values(), key=lambda x: (x.get("activity_date") or "", str(x.get("activity_id"))))
    add_comparisons(ordered)
    history.update({
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "entries": ordered,
    })
    return updated, skipped


def main():
    parser = argparse.ArgumentParser(description="Bygg prestationsfingeravtryck från Intervals.icu arbetsintervall.")
    parser.add_argument("--days", type=int, default=60)
    args = parser.parse_args()
    if not 7 <= args.days <= 180:
        raise RuntimeError("--days måste vara 7..180")

    state = load_json(ACTIVITIES_FILE, {"schema_version": 2, "activities": []})
    history = load_json(HISTORY_FILE, {"schema_version": SCHEMA_VERSION, "entries": []})
    newest = datetime.now(timezone.utc).date()
    oldest = newest - timedelta(days=args.days - 1)
    auth = authorization()
    interval_activities = []
    if auth:
        try:
            interval_activities = fetch_activity_list(oldest, newest, auth)
        except Exception as exc:
            print(f"WARNING: Intervals.icu unavailable; using Strava lap fallback: {exc}", file=sys.stderr)

    updated, skipped = sync(
        state,
        history,
        interval_activities,
        (lambda activity_id: fetch_activity_detail(activity_id, auth)) if auth else (lambda _: {}),
        oldest,
    )
    write_json(HISTORY_FILE, history)
    print(
        "Performance sync OK: "
        f"protocol_entries={len(history.get('entries') or [])} "
        f"updated={updated} skipped_or_unmatched={skipped}."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
