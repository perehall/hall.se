#!/usr/bin/env python3
import argparse
import base64
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STRAVA_FILE = ROOT / "data" / "activities.json"
API_BASE = "https://intervals.icu/api/v1/athlete/0/activities"

FIELD_CANDIDATES = {
    "distance": ("distance",),
    "moving_time": ("moving_time",),
    "elapsed_time": ("elapsed_time",),
    "elevation": ("total_elevation_gain", "total_elevation_gain_m"),
    "average_hr": ("average_heartrate",),
    "max_hr": ("max_heartrate",),
    "average_watts": ("average_watts",),
    "weighted_watts": ("weighted_average_watts",),
    "calories": ("calories",),
    "device": ("device_name", "device"),
    "file_type": ("file_type",),
}


def api_key():
    value = os.environ.get("INTERVALS_API_KEY", "").strip()
    if not value:
        raise RuntimeError("INTERVALS_API_KEY saknas")
    return value


def fetch_intervals(oldest, newest):
    query = urlencode({"oldest": oldest.isoformat(), "newest": newest.isoformat()})
    url = f"{API_BASE}?{query}"
    auth = base64.b64encode(f"API_KEY:{api_key()}".encode()).decode()
    request = Request(
        url,
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "User-Agent": "hall-training-intervals-activity-poc/1.0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Intervals.icu HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Intervals.icu kunde inte nås: {exc.reason}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Intervals.icu returnerade inte giltig JSON") from exc
    if not isinstance(data, list):
        raise RuntimeError("Intervals.icu activities-svar är inte en lista")
    return [row for row in data if isinstance(row, dict)]


def load_strava(oldest, newest):
    payload = json.loads(STRAVA_FILE.read_text(encoding="utf-8"))
    rows = payload.get("activities") or []
    selected = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        dt = parse_time(row.get("start_date"))
        if dt is None:
            continue
        d = dt.date()
        if oldest <= d <= newest:
            selected.append(row)
    return selected


def parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def first_value(row, names):
    for name in names:
        if row.get(name) is not None:
            return row.get(name)
    return None


def present_fields(rows):
    result = []
    for label, names in FIELD_CANDIDATES.items():
        if any(first_value(row, names) is not None for row in rows):
            result.append(label)
    return result


def source_types(rows):
    values = set()
    for row in rows:
        value = row.get("source")
        if isinstance(value, str) and value.strip():
            values.add(value.strip().upper())
    return sorted(values)


def closest_unmatched(strava_row, intervals_rows, used):
    target = parse_time(strava_row.get("start_date"))
    if target is None:
        return None
    best = None
    best_delta = None
    for idx, row in enumerate(intervals_rows):
        if idx in used:
            continue
        candidate = parse_time(row.get("start_date"))
        if candidate is None:
            continue
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=timezone.utc)
        delta = abs((candidate.astimezone(timezone.utc) - target.astimezone(timezone.utc)).total_seconds())
        if delta <= 600 and (best_delta is None or delta < best_delta):
            best = idx
            best_delta = delta
    return best


def match_rows(strava_rows, intervals_rows):
    used = set()
    pairs = []
    unmatched = []
    for srow in strava_rows:
        idx = closest_unmatched(srow, intervals_rows, used)
        if idx is None:
            unmatched.append(srow)
            continue
        used.add(idx)
        pairs.append((srow, intervals_rows[idx]))
    extras = [row for idx, row in enumerate(intervals_rows) if idx not in used]
    return pairs, unmatched, extras


def presence_comparison(pairs):
    status = {}
    for label, interval_names in FIELD_CANDIDATES.items():
        relevant = 0
        interval_present = 0
        for srow, irow in pairs:
            strava_names = {
                "distance": ("distance_m",),
                "moving_time": ("moving_time_s",),
                "elapsed_time": ("elapsed_time_s",),
                "elevation": ("total_elevation_gain_m",),
                "average_hr": ("average_heartrate",),
                "max_hr": ("max_heartrate",),
                "average_watts": ("average_watts",),
                "weighted_watts": ("weighted_average_watts",),
                "calories": ("calories",),
                "device": ("device_name",),
                "file_type": (),
            }[label]
            if strava_names and first_value(srow, strava_names) is not None:
                relevant += 1
                if first_value(irow, interval_names) is not None:
                    interval_present += 1
        if relevant == 0:
            status[label] = "not_comparable"
        elif interval_present == relevant:
            status[label] = "complete"
        elif interval_present == 0:
            status[label] = "missing"
        else:
            status[label] = "partial"
    return status


def main():
    parser = argparse.ArgumentParser(description="Read-only POC: compare Intervals/Garmin activities with current Strava import")
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()
    if args.days < 1 or args.days > 31:
        raise RuntimeError("--days måste vara 1..31")

    newest = datetime.now(timezone.utc).date()
    oldest = newest - timedelta(days=args.days - 1)
    intervals_rows = fetch_intervals(oldest, newest)
    strava_rows = load_strava(oldest, newest)

    pairs, unmatched, extras = match_rows(strava_rows, intervals_rows)
    comparison = presence_comparison(pairs)

    # Privacy: only schema/source labels and qualitative verdicts are printed.
    # No activity names, timestamps, distances, HR, power, IDs or counts are emitted.
    print("Intervals.icu activity POC")
    print("privacy=aggregate_only")
    print("intervals_sources=" + (",".join(source_types(intervals_rows)) or "none"))
    print("intervals_fields_present=" + (",".join(present_fields(intervals_rows)) or "none"))
    print("strava_activity_match=" + ("complete" if not unmatched else "incomplete"))
    print("intervals_has_additional_activities=" + ("yes" if extras else "no"))
    print("metric_presence_vs_strava:")
    for key in FIELD_CANDIDATES:
        print(f"  {key}={comparison[key]}")

    # Fail only for API/schema problems. Coverage differences are the result of the POC,
    # not an execution error, and must be evaluated before migration.
    if not intervals_rows:
        print("WARNING: no Intervals activities returned in test window", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
