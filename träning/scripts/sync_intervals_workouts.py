#!/usr/bin/env python3
"""Reconcile device-neutral workouts with Intervals.icu.

Intervals.icu is the transport adapter. The training prescription is compiled
upstream in device_workout.py. This module only serializes, upserts, removes
stale owned events, reads the stored structured workout back and records
transport status. It never claims that Garmin-device delivery was verified.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from device_workout import validate_device_workout


ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
API_BASE = "https://intervals.icu/api/v1/athlete/0"
BULK_UPSERT_URL = f"{API_BASE}/events/bulk?upsert=true"
BULK_DELETE_URL = f"{API_BASE}/events/bulk-delete"
OWNED_PREFIXES = ("hall-device:", "hall-training:")


class IntervalsSyncError(RuntimeError):
    pass


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def duration_token(duration):
    kind = duration.get("kind")
    if kind == "distance":
        return f'{int(duration["meters"])}mtr'
    seconds = int(duration.get("seconds") or 0)
    if seconds <= 0:
        raise IntervalsSyncError("Intervals-adapter: tidssteg måste vara > 0")
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def clean_prompt(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().replace("- ", "")


def render_target(target):
    if not target:
        return ""
    target_type = target.get("type")
    value = target.get("value")
    start = target.get("start")
    end = target.get("end")
    unit = str(target.get("unit") or "").strip()

    if target_type == "pace":
        if value is not None:
            body = str(value)
        else:
            body = f"{start}-{end}"
        return f"{body} Pace"
    if target_type == "heart_rate":
        if value is not None and isinstance(value, str) and value.upper().startswith("Z"):
            return f"{value} HR"
        if value is not None and unit.lower() in {"bpm", "beats/min"}:
            return f"{value}bpm HR"
        raise IntervalsSyncError(
            "Intervals-adapter: puls-target måste anges explicit som zon eller bpm"
        )
    if target_type == "power":
        if value is not None and unit.lower() in {"%ftp", "%"}:
            return f"{value}%"
        if value is not None and unit.lower() in {"w", "watt", "watts"}:
            return f"{value}w"
        raise IntervalsSyncError(
            "Intervals-adapter: power-target måste ange %FTP eller watt"
        )
    raise IntervalsSyncError(f"Intervals-adapter: okänd target {target_type!r}")


def render_step(step):
    prompt = clean_prompt(step.get("instruction"))
    token = duration_token(step.get("duration") or {})
    press_lap = "Press lap " if step.get("press_lap") else ""
    target = render_target(step.get("target"))
    intensity = str(step.get("intensity_class") or "active").strip().lower()
    if intensity == "recovery":
        intensity = "rest"
    parts = [f"- {prompt} {press_lap}{token}".strip()]
    if target:
        parts.append(target)
    parts.append(f"intensity={intensity}")
    return " ".join(parts)


def render_description(workout):
    validate_device_workout(workout, workout.get("external_id") or "device_workout")
    sections = []
    for block in workout["blocks"]:
        sets = int(block.get("sets") or 1)
        reps = int(block.get("repetitions_per_set") or 1)
        for set_index in range(sets):
            name = clean_prompt(block.get("name")) or "Passdel"
            if sets > 1:
                name = f"{name} set {set_index + 1}"
            if reps > 1:
                name = f"{name} {reps}x"
            lines = [name]
            lines.extend(render_step(step) for step in block.get("steps") or [])
            sections.append("\n".join(lines))
    return "\n\n".join(sections)


def semantic_expectations(workout):
    counts = Counter()
    press_lap_labels = []
    for block in workout.get("blocks") or []:
        for step in block.get("steps") or []:
            intensity = str(step.get("intensity_class") or "active").lower()
            if intensity == "recovery":
                intensity = "rest"
            counts[intensity] += 1
            if step.get("press_lap"):
                press_lap_labels.append(clean_prompt(step.get("instruction")))
    return {"counts": dict(counts), "press_lap_labels": press_lap_labels}


def payload_for(workout):
    return {
        "category": "WORKOUT",
        "start_date_local": f'{workout["date"]}T00:00:00',
        "type": workout["provider_type"],
        "name": workout["name"],
        "description": render_description(workout),
        "external_id": workout["external_id"],
    }


def request_json(url, auth, *, method="GET", payload_data=None):
    request = Request(
        url,
        data=payload_data,
        method=method,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "hall-device-workout-sync/1.0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            status = response.status
    except HTTPError as exc:
        raise IntervalsSyncError(f"Intervals.icu HTTP {exc.code}") from exc
    except URLError as exc:
        raise IntervalsSyncError(f"Intervals.icu kunde inte nås: {exc.reason}") from exc
    if not 200 <= status < 300:
        raise IntervalsSyncError(f"Intervals.icu oväntad HTTP-status: {status}")
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IntervalsSyncError("Intervals.icu returnerade inte giltig JSON") from exc


def list_events(auth, oldest, newest):
    query = urlencode({"oldest": oldest, "newest": newest})
    data = request_json(f"{API_BASE}/events?{query}", auth)
    if not isinstance(data, list):
        raise IntervalsSyncError("Intervals.icu list-events gav oväntat svarformat")
    return data


def semantic_nodes(node):
    if isinstance(node, dict):
        if "intensity" in node or "text" in node or "duration" in node or "distance" in node:
            yield node
        for value in node.values():
            yield from semantic_nodes(value)
    elif isinstance(node, list):
        for value in node:
            yield from semantic_nodes(value)


def verify_semantics(stored, workout):
    workout_doc = stored.get("workout_doc")
    steps = workout_doc.get("steps") if isinstance(workout_doc, dict) else None
    if not isinstance(steps, list) or not steps:
        raise IntervalsSyncError(
            f'Intervals.icu skapade inte strukturerade steg för {workout["external_id"]}'
        )
    nodes = list(semantic_nodes(workout_doc))
    parsed = Counter(
        str(node.get("intensity") or "").strip().lower()
        for node in nodes
        if node.get("intensity") is not None
    )
    expected = semantic_expectations(workout)
    for intensity, count in expected["counts"].items():
        if intensity == "interval":
            actual = parsed["interval"] + parsed["active"]
        elif intensity == "active":
            actual = parsed["active"] + parsed["interval"]
        elif intensity == "rest":
            actual = parsed["rest"] + parsed["recovery"]
        else:
            actual = parsed[intensity]
        if actual < count:
            raise IntervalsSyncError(
                f'{workout["external_id"]}: {intensity} väntat minst {count}, fick {actual}'
            )
    for label in expected["press_lap_labels"]:
        label_lower = label.lower()
        if not any(label_lower in str(node.get("text") or "").lower() for node in nodes):
            raise IntervalsSyncError(
                f'{workout["external_id"]}: Press-lap-text {label!r} saknas efter readback'
            )
    if workout["sport"] == "swim":
        expected_distance = sum(
            int(step["duration"]["meters"])
            * int(block.get("repetitions_per_set") or 1)
            * int(block.get("sets") or 1)
            for block in workout["blocks"]
            for step in block["steps"]
            if step.get("kind") == "work" and step.get("duration", {}).get("kind") == "distance"
        )
        parsed_distance = workout_doc.get("distance")
        if isinstance(parsed_distance, (int, float)) and abs(parsed_distance - expected_distance) > 1:
            raise IntervalsSyncError(
                f'{workout["external_id"]}: simdistans {parsed_distance} != {expected_distance}'
            )
    return True


def load_documents():
    return {"plan": load_json(PLAN_FILE), "upcoming": load_json(UPCOMING_FILE)}


def horizon(documents):
    plan = documents["plan"]
    timezone_name = (plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    today_date = datetime.now(ZoneInfo(timezone_name)).date()
    return today_date.isoformat(), (today_date + timedelta(days=6)).isoformat()


def desired_workouts(documents, oldest, newest):
    result = []
    seen = set()
    for document in documents.values():
        for day in document.get("days") or []:
            date_text = str(day.get("date") or "")
            workout = day.get("device_workout")
            sync = day.get("device_sync") or {}
            if not isinstance(workout, dict) or not oldest <= date_text <= newest:
                continue
            if sync.get("status") == "deferred":
                continue
            validate_device_workout(workout, f"device_sync:{date_text}")
            external_id = workout["external_id"]
            if external_id in seen:
                raise IntervalsSyncError(f"duplicerat device external_id {external_id}")
            seen.add(external_id)
            result.append(workout)
    return result


def mark_status(documents, workout, *, status, event_id=None, error=None):
    now = datetime.now(timezone.utc).isoformat()
    for document in documents.values():
        for day in document.get("days") or []:
            candidate = day.get("device_workout") or {}
            if candidate.get("external_id") != workout.get("external_id"):
                continue
            sync = {
                "status": status,
                "transport": "intervals_icu",
                "source_hash": workout["source_hash"],
                "device_delivery": "unverified",
                "updated_at_utc": now,
            }
            if event_id is not None:
                sync["provider_event_id"] = event_id
            if status == "synced":
                sync["verified_at_utc"] = now
            if error:
                sync["error"] = str(error)[:240]
            day["device_sync"] = sync


def persist_documents(documents):
    write_json(PLAN_FILE, documents["plan"])
    write_json(UPCOMING_FILE, documents["upcoming"])


def event_matches(event, desired_payload):
    return (
        isinstance(event, dict)
        and event.get("category") == "WORKOUT"
        and event.get("type") == desired_payload["type"]
        and event.get("name") == desired_payload["name"]
        and event.get("description") == desired_payload["description"]
        and str(event.get("start_date_local") or "").startswith(
            desired_payload["start_date_local"][:10]
        )
    )


def reconcile(documents, auth, oldest, newest):
    desired = desired_workouts(documents, oldest, newest)
    desired_payloads = {workout["external_id"]: payload_for(workout) for workout in desired}
    existing_events = list_events(auth, oldest, newest)
    existing_owned = {
        str(event.get("external_id")): event
        for event in existing_events
        if isinstance(event, dict)
        and any(str(event.get("external_id") or "").startswith(prefix) for prefix in OWNED_PREFIXES)
    }

    stale_ids = sorted(set(existing_owned) - set(desired_payloads))
    if stale_ids:
        delete_payload = [{"external_id": external_id} for external_id in stale_ids]
        request_json(
            BULK_DELETE_URL,
            auth,
            method="PUT",
            payload_data=json.dumps(delete_payload).encode("utf-8"),
        )
        print(f"DEVICE_SYNC_DELETE stale={len(stale_ids)}")

    upserts = [
        payload
        for external_id, payload in desired_payloads.items()
        if not event_matches(existing_owned.get(external_id), payload)
    ]
    if upserts:
        data = request_json(
            BULK_UPSERT_URL,
            auth,
            method="POST",
            payload_data=json.dumps(upserts, ensure_ascii=False).encode("utf-8"),
        )
        if not isinstance(data, list):
            raise IntervalsSyncError("Intervals.icu bulk-upsert gav oväntat svarformat")
        print(f"DEVICE_SYNC_UPSERT count={len(upserts)}")
    else:
        print("DEVICE_SYNC_UPSERT count=0")

    refreshed = list_events(auth, oldest, newest)
    by_external = {
        str(event.get("external_id")): event
        for event in refreshed
        if isinstance(event, dict) and event.get("external_id")
    }

    errors = []
    for workout in desired:
        event = by_external.get(workout["external_id"])
        if not event or event.get("category") != "WORKOUT" or not event.get("id"):
            error = IntervalsSyncError(
                f'Intervals.icu saknar verifierbar event för {workout["external_id"]}'
            )
            mark_status(documents, workout, status="error", error=error)
            errors.append(str(error))
            continue
        try:
            stored = request_json(f'{API_BASE}/events/{event["id"]}', auth)
            if not isinstance(stored, dict):
                raise IntervalsSyncError("readback gav oväntat svarformat")
            verify_semantics(stored, workout)
            mark_status(documents, workout, status="synced", event_id=event["id"])
            print(
                f'DEVICE_SYNC_OK date={workout["date"]} sport={workout["sport"]} '
                f'external_id={workout["external_id"]}'
            )
        except Exception as exc:
            mark_status(documents, workout, status="error", event_id=event.get("id"), error=exc)
            errors.append(f'{workout["external_id"]}: {exc}')

    if errors:
        raise IntervalsSyncError("; ".join(errors))
    return len(desired), len(stale_ids), len(upserts)


def main():
    parser = argparse.ArgumentParser(description="Synka strukturerade pass via Intervals.icu till Garmin")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    documents = load_documents()
    oldest, newest = horizon(documents)
    desired = desired_workouts(documents, oldest, newest)
    if args.dry_run:
        for workout in desired:
            payload = payload_for(workout)
            print(
                f'DRY_RUN date={workout["date"]} sport={workout["sport"]} '
                f'external_id={workout["external_id"]}\n{payload["description"]}\n'
            )
        print(f"Dry-run: {len(desired)} pass inom {oldest}–{newest}; inget skickades.")
        return 0

    api_key = os.environ.get("INTERVALS_API_KEY", "").strip()
    if not api_key:
        raise IntervalsSyncError("INTERVALS_API_KEY saknas; device_sync lämnas pending")
    auth = base64.b64encode(f"API_KEY:{api_key}".encode("utf-8")).decode("ascii")

    try:
        synced, deleted, upserted = reconcile(documents, auth, oldest, newest)
    except Exception:
        persist_documents(documents)
        raise
    persist_documents(documents)
    print(
        f"Device sync OK: {synced} verifierade Intervals-pass, {upserted} upsert, "
        f"{deleted} stale borttagna; Garmin-leverans lämnas explicit overifierad."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
