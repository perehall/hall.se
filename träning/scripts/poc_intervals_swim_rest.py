#!/usr/bin/env python3
import base64
import json
import os
import sys
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API_BASE = "https://intervals.icu/api/v1/athlete/0"
TZ = ZoneInfo("Europe/Stockholm")


def auth_header():
    api_key = os.environ.get("INTERVALS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("INTERVALS_API_KEY saknas")
    token = base64.b64encode(f"API_KEY:{api_key}".encode()).decode("ascii")
    return f"Basic {token}"


def request_json(url, *, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": auth_header(),
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "hall-training-swim-rest-poc/1.0",
        },
    )
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            status = response.status
    except HTTPError as exc:
        raise RuntimeError(f"Intervals.icu HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Intervals.icu kunde inte nås: {exc.reason}") from exc
    if not 200 <= status < 300:
        raise RuntimeError(f"Intervals.icu oväntad HTTP-status {status}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Intervals.icu returnerade inte giltig JSON") from exc


def safe_structure(node):
    """Return only workout-structure metadata; never athlete/wellness values."""
    safe_values = {
        "type", "step_type", "intensity", "duration", "duration_type",
        "distance", "distance_m", "repeat", "reps", "repeat_reps",
        "text", "name", "target", "units", "value", "end_condition",
    }
    if isinstance(node, list):
        return [safe_structure(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {"_keys": sorted(node.keys())}
    for key, value in node.items():
        if key in safe_values:
            out[key] = safe_structure(value) if isinstance(value, (dict, list)) else value
        elif isinstance(value, (dict, list)) and key in {"steps", "workout", "step", "children"}:
            out[key] = safe_structure(value)
    return out


def semantic_hits(node, path="workout_doc"):
    hits = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}"
            if key.lower() in {
                "type", "step_type", "intensity", "duration", "duration_type",
                "distance", "distance_m", "repeat", "reps", "repeat_reps", "text",
            } and not isinstance(value, (dict, list)):
                hits.append((child, value))
            hits.extend(semantic_hits(value, child))
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            hits.extend(semantic_hits(value, f"{path}[{idx}]"))
    return hits


def main():
    date = (datetime.now(TZ).date() + timedelta(days=1)).isoformat()
    external_id = f"hall-swim-rest-poc:{date}"
    description = """REST POC 2x
- Lugn 50mtr
- Vila 20s intensity=rest"""

    event = {
        "category": "WORKOUT",
        "start_date_local": f"{date}T00:00:00",
        "type": "Swim",
        "name": "REST POC · 2×50 m + 20 s vila",
        "description": description,
        "external_id": external_id,
    }

    print(f"POC date={date} workout=2x(50m+20s_rest) planned_distance_m=100")
    created = request_json(f"{API_BASE}/events/bulk?upsert=true", method="POST", payload=[event])
    if not isinstance(created, list) or len(created) != 1 or not isinstance(created[0], dict):
        raise RuntimeError("Intervals.icu bulk-upsert gav oväntat svar")
    event_id = created[0].get("id")
    if not event_id:
        raise RuntimeError("Intervals.icu svar saknar event-id")

    # Fetch the server-stored event back instead of trusting only the POST response.
    stored = request_json(f"{API_BASE}/events/{event_id}")
    if not isinstance(stored, dict) or stored.get("category") != "WORKOUT":
        raise RuntimeError("Kunde inte läsa tillbaka POC-workouten")
    doc = stored.get("workout_doc")
    if not isinstance(doc, dict) or not isinstance(doc.get("steps"), list):
        raise RuntimeError("Intervals.icu skapade inget strukturerat workout_doc.steps")

    print("WORKOUT_DOC_SAFE=" + json.dumps(safe_structure(doc), ensure_ascii=False, sort_keys=True))
    hits = semantic_hits(doc)
    for path, value in hits:
        print(f"SEMANTIC {path}={value}")

    rest_hits = [
        (path, value) for path, value in hits
        if path.lower().endswith((".intensity", ".step_type", ".type"))
        and str(value).strip().lower() in {"rest", "recovery"}
    ]
    duration_20 = [(path, value) for path, value in hits if path.lower().endswith(".duration") and value == 20]

    print(f"REST_SEMANTIC_FOUND={'yes' if rest_hits else 'no'}")
    print(f"DURATION_20_FOUND={'yes' if duration_20 else 'no'}")
    print("POC_RESULT=inspect_garmin_after_sync")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
