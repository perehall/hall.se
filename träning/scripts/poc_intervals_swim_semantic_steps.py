#!/usr/bin/env python3
import base64
import json
import os
import sys
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API_BASE = "https://intervals.icu/api/v1/athlete/0"
TZ = ZoneInfo("Europe/Stockholm")


def auth_header():
    api_key = os.environ.get("INTERVALS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("INTERVALS_API_KEY saknas")
    token = base64.b64encode(f"API_KEY:{api_key}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def request_json(url, *, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": auth_header(),
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "hall-training-swim-semantic-steps-poc/1.0",
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
    """Return workout structure only; no athlete or wellness values."""
    if isinstance(node, list):
        return [safe_structure(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {"_keys": sorted(node.keys())}
    for key, value in node.items():
        if isinstance(value, (dict, list)):
            out[key] = safe_structure(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
    return out


def semantic_hits(node, path="workout_doc"):
    hits = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}"
            if not isinstance(value, (dict, list)):
                hits.append((child, value))
            hits.extend(semantic_hits(value, child))
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            hits.extend(semantic_hits(value, f"{path}[{idx}]"))
    return hits


def intensity_found(hits, expected):
    return any(
        path.lower().endswith(".intensity")
        and str(value).strip().lower() == expected
        for path, value in hits
    )


def main():
    # Deliberately schedule on the current Europe/Stockholm date.
    date = datetime.now(TZ).date().isoformat()
    external_id = f"hall-swim-semantic-steps-poc:{date}"
    description = """Uppvärmning
- Lugn 100mtr intensity=warmup

Huvudset 2x
- Aktiv 50mtr intensity=active
- Vila 20s intensity=rest

- Press lap Setvila 1m intensity=rest

Nedvarvning
- Mycket lugn 100mtr intensity=cooldown"""

    event = {
        "category": "WORKOUT",
        "start_date_local": f"{date}T00:00:00",
        "type": "Swim",
        "name": "SEMANTIC POC · warmup/rest/cooldown",
        "description": description,
        "external_id": external_id,
    }

    print("POC workout=100m_warmup + 2x(50m_active+20s_rest) + press_lap_set_rest + 100m_cooldown")
    print(f"POC date={date} planned_distance_m=300")

    created = request_json(f"{API_BASE}/events/bulk?upsert=true", method="POST", payload=[event])
    if not isinstance(created, list) or len(created) != 1 or not isinstance(created[0], dict):
        raise RuntimeError("Intervals.icu bulk-upsert gav oväntat svar")
    event_id = created[0].get("id")
    if not event_id:
        raise RuntimeError("Intervals.icu svar saknar event-id")

    # Read the server-stored event back; do not rely only on the POST response.
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

    warmup = intensity_found(hits, "warmup")
    active = intensity_found(hits, "active") or intensity_found(hits, "interval")
    rest = intensity_found(hits, "rest")
    cooldown = intensity_found(hits, "cooldown")

    set_rest = any(
        path.lower().endswith((".text", ".name"))
        and "setvila" in str(value).lower()
        for path, value in hits
    )
    lap_hits = []
    for path, value in hits:
        p = path.lower()
        v = str(value).strip().lower()
        if "lap" in p and (value is True or "lap" in v or v in {"manual", "button"}):
            lap_hits.append((path, value))
        elif p.endswith((".duration_type", ".end_condition", ".end_type", ".condition")) and "lap" in v:
            lap_hits.append((path, value))

    print(f"WARMUP_SEMANTIC_FOUND={'yes' if warmup else 'no'}")
    print(f"ACTIVE_SEMANTIC_FOUND={'yes' if active else 'no'}")
    print(f"REST_SEMANTIC_FOUND={'yes' if rest else 'no'}")
    print(f"COOLDOWN_SEMANTIC_FOUND={'yes' if cooldown else 'no'}")
    print(f"SET_REST_STEP_FOUND={'yes' if set_rest else 'no'}")
    print(f"PRESS_LAP_SEMANTIC_FOUND={'yes' if lap_hits else 'no'}")

    distance = doc.get("distance")
    if isinstance(distance, (int, float)) and abs(distance - 300) > 1:
        raise RuntimeError(f"Intervals.icu distansavvikelse: {distance} mot 300")

    print("POC_RESULT=inspect_garmin_step_labels_and_pages")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
