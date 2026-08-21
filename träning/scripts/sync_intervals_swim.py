#!/usr/bin/env python3
import argparse
import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
API_URL = "https://intervals.icu/api/v1/athlete/0/events/bulk?upsert=true"


def load_plan():
    return json.loads(PLAN_FILE.read_text(encoding="utf-8"))


def workout_distance(blocks):
    total = 0
    for block in blocks:
        repeat = int(block.get("repeat", 1))
        if repeat < 1:
            raise RuntimeError("watch_workout: repeat måste vara >= 1")
        block_distance = 0
        steps = block.get("steps")
        if not isinstance(steps, list) or not steps:
            raise RuntimeError("watch_workout: varje block måste ha steps")
        for step in steps:
            kind = step.get("kind")
            if kind == "swim":
                distance = int(step.get("distance_m") or 0)
                if distance <= 0:
                    raise RuntimeError("watch_workout: swim-step måste ha distance_m > 0")
                if not str(step.get("text") or "").strip():
                    raise RuntimeError("watch_workout: swim-step måste ha text")
                block_distance += distance
            elif kind == "rest":
                duration = int(step.get("duration_s") or 0)
                if duration <= 0:
                    raise RuntimeError("watch_workout: rest-step måste ha duration_s > 0")
            else:
                raise RuntimeError(f"watch_workout: okänd step-kind {kind!r}")
        total += repeat * block_distance
    return total


def render_description(blocks):
    sections = []
    for block in blocks:
        name = str(block.get("name") or "").strip()
        if not name:
            raise RuntimeError("watch_workout: block saknar name")
        repeat = int(block.get("repeat", 1))
        heading = f"{name} {repeat}x" if repeat > 1 else name
        lines = [heading]
        for step in block["steps"]:
            if step["kind"] == "swim":
                lines.append(f'- {step["text"]} {int(step["distance_m"])}mtr')
            else:
                lines.append(f'- Vila {int(step["duration_s"])}s intensity=rest')
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def eligible_workouts(plan):
    tz = ZoneInfo(plan.get("meta", {}).get("timezone", "Europe/Stockholm"))
    today = datetime.now(tz).date().isoformat()
    result = []
    seen_ids = set()
    seen_external_ids = set()

    for day in plan.get("days", []):
        workout = day.get("watch_workout")
        if not isinstance(workout, dict) or workout.get("sync_enabled") is not True:
            continue
        if day.get("status") != "planned" or str(day.get("date") or "") < today:
            continue

        required = ["id", "name", "type", "planned_distance_m", "blocks"]
        missing = [key for key in required if workout.get(key) in (None, "", [])]
        if missing:
            raise RuntimeError(f"watch_workout {day.get('date')}: saknade fält {missing}")
        if workout["type"] != "Swim":
            raise RuntimeError("watch_workout: produktionsexporten är låst till Swim")

        workout_id = str(workout["id"])
        external_id = str(workout.get("external_id") or f"hall-training:{workout_id}")
        if workout_id in seen_ids:
            raise RuntimeError(f"watch_workout: duplicerat id {workout_id!r}")
        if external_id in seen_external_ids:
            raise RuntimeError(f"watch_workout: duplicerat external_id {external_id!r}")
        seen_ids.add(workout_id)
        seen_external_ids.add(external_id)

        declared = int(workout["planned_distance_m"])
        calculated = workout_distance(workout["blocks"])
        if declared != calculated:
            raise RuntimeError(
                f"watch_workout {workout_id}: deklarerat {declared} m men seten summerar till {calculated} m"
            )

        result.append(
            {
                "id": workout_id,
                "date": day["date"],
                "name": workout["name"],
                "type": workout["type"],
                "planned_distance_m": declared,
                "description": render_description(workout["blocks"]),
                "external_id": external_id,
            }
        )
    return result


def payload(workouts):
    return [
        {
            "category": "WORKOUT",
            "start_date_local": f'{w["date"]}T00:00:00',
            "type": w["type"],
            "name": w["name"],
            "description": w["description"],
            "external_id": w["external_id"],
        }
        for w in workouts
    ]


def find_returned_event(data, workout):
    direct = [
        row for row in data
        if isinstance(row, dict) and row.get("external_id") == workout["external_id"]
    ]
    if len(direct) == 1:
        return direct[0]

    fallback = [
        row for row in data
        if isinstance(row, dict)
        and row.get("name") == workout["name"]
        and str(row.get("start_date_local") or "").startswith(workout["date"])
    ]
    return fallback[0] if len(fallback) == 1 else None


def send(events, workouts):
    api_key = os.environ.get("INTERVALS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("INTERVALS_API_KEY saknas")

    auth = base64.b64encode(f"API_KEY:{api_key}".encode("utf-8")).decode("ascii")
    request = Request(
        API_URL,
        data=json.dumps(events, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "hall-training-swim-sync/1.0",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            status = response.status
    except HTTPError as exc:
        raise RuntimeError(f"Intervals.icu HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Intervals.icu kunde inte nås: {exc.reason}") from exc

    if not 200 <= status < 300:
        raise RuntimeError(f"Intervals.icu oväntad HTTP-status: {status}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Intervals.icu returnerade inte giltig JSON") from exc
    if not isinstance(data, list):
        raise RuntimeError("Intervals.icu returnerade oväntat svarformat")

    for workout in workouts:
        event = find_returned_event(data, workout)
        if not event or event.get("category") != "WORKOUT" or not event.get("id"):
            raise RuntimeError(f'Intervals.icu verifierade inte {workout["id"]}')
        workout_doc = event.get("workout_doc")
        steps = workout_doc.get("steps") if isinstance(workout_doc, dict) else None
        if not isinstance(steps, list) or not steps:
            raise RuntimeError(f'Intervals.icu skapade inte strukturerade steg för {workout["id"]}')
        parsed_distance = workout_doc.get("distance")
        if isinstance(parsed_distance, (int, float)) and abs(parsed_distance - workout["planned_distance_m"]) > 1:
            raise RuntimeError(
                f'Intervals.icu distansavvikelse för {workout["id"]}: {parsed_distance} mot {workout["planned_distance_m"]}'
            )
        print(
            f'SYNC_OK workout={workout["id"]} date={workout["date"]} '
            f'distance_m={workout["planned_distance_m"]} parsed_steps={len(steps)}'
        )


def main():
    parser = argparse.ArgumentParser(description="Synka planerade strukturerade simpass till Intervals.icu/Garmin")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workouts = eligible_workouts(load_plan())
    if not workouts:
        print("Intervals swim sync: inga kvalificerade planerade simpass.")
        return 0

    events = payload(workouts)
    for workout in workouts:
        print(
            f'VALID workout={workout["id"]} date={workout["date"]} '
            f'distance_m={workout["planned_distance_m"]}'
        )

    if args.dry_run:
        print("Dry-run: inget skickades.")
        return 0

    send(events, workouts)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
