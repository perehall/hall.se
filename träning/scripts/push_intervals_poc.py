#!/usr/bin/env python3
import argparse
import base64
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "intervals_poc_workout.json"
API_URL = "https://intervals.icu/api/v1/athlete/0/events/bulk?upsert=true"


def load_workout():
    workout = json.loads(FIXTURE.read_text(encoding="utf-8"))
    required = [
        "date",
        "category",
        "type",
        "name",
        "external_id",
        "description",
        "planned_distance_m",
        "calculated_set_distance_m",
    ]
    missing = [key for key in required if workout.get(key) is None or workout.get(key) == ""]
    if missing:
        raise RuntimeError(f"Intervals POC: saknade fält i fixture: {missing!r}")
    if workout["category"] != "WORKOUT":
        raise RuntimeError("Intervals POC: category måste vara WORKOUT")
    if workout["type"] != "Swim":
        raise RuntimeError("Intervals POC: denna POC är avsiktligt låst till Swim")
    return workout


def validate_workout(workout):
    declared = int(workout["planned_distance_m"])
    calculated = int(workout["calculated_set_distance_m"])
    if declared != calculated:
        raise RuntimeError(
            "Intervals POC blockerad: deklarerad distans "
            f"{declared} m men seten summerar till {calculated} m. "
            "Lös träningsplanens distansskillnad innan workout skickas."
        )


def event_payload(workout):
    return {
        "category": workout["category"],
        "start_date_local": f'{workout["date"]}T00:00:00',
        "type": workout["type"],
        "name": workout["name"],
        "description": workout["description"],
        "external_id": workout["external_id"],
    }


def safe_preview(payload, workout):
    print("Intervals.icu POC payload:")
    print(json.dumps([payload], ensure_ascii=False, indent=2))
    print(
        "\nDistanskontroll: "
        f'deklarerat {workout.get("planned_distance_m")} m · '
        f'setsumma {workout.get("calculated_set_distance_m")} m'
    )
    notes = workout.get("normalization_notes") or []
    if notes:
        print("\nPOC-normalisering:")
        for note in notes:
            print(f"- {note}")


def send(payload):
    api_key = os.environ.get("INTERVALS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "INTERVALS_API_KEY saknas. Lägg den som GitHub Actions repository secret innan riktig POC-körning."
        )

    auth = base64.b64encode(f"API_KEY:{api_key}".encode("utf-8")).decode("ascii")
    body = json.dumps([payload], ensure_ascii=False).encode("utf-8")
    request = Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "hall-training-intervals-poc/1.0",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            status = response.status
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Intervals.icu HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Intervals.icu kunde inte nås: {exc.reason}") from exc

    if status < 200 or status >= 300:
        raise RuntimeError(f"Intervals.icu oväntad HTTP-status: {status}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Intervals.icu returnerade inte giltig JSON") from exc

    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise RuntimeError(f"Intervals.icu oväntat svarformat: {type(data).__name__}")

    event = data[0]
    if event.get("category") != "WORKOUT" or not event.get("id"):
        raise RuntimeError("Intervals.icu skapade inte ett verifierbart WORKOUT-event")

    workout_doc = event.get("workout_doc")
    steps = workout_doc.get("steps") if isinstance(workout_doc, dict) else None
    if not isinstance(steps, list) or not steps:
        raise RuntimeError(
            "Intervals.icu accepterade eventet men workout_doc.steps saknas. "
            "POC:n räknas därför inte som ett strukturerat workout."
        )

    print("Intervals.icu POC OK")
    print(f'event_id={event.get("id")}')
    print(f'name={event.get("name")}')
    print(f'parsed_steps={len(steps)}')
    if workout_doc.get("distance") is not None:
        print(f'parsed_distance={workout_doc.get("distance")}')
    if workout_doc.get("duration") is not None:
        print(f'parsed_duration={workout_doc.get("duration")}')


def main():
    parser = argparse.ArgumentParser(description="POC: skicka ett strukturerat simpass till Intervals.icu")
    parser.add_argument("--dry-run", action="store_true", help="Visa payload utan API-anrop")
    args = parser.parse_args()

    workout = load_workout()
    payload = event_payload(workout)
    safe_preview(payload, workout)
    validate_workout(workout)

    if args.dry_run:
        print("\nDry-run: inget skickades till Intervals.icu.")
        return 0

    send(payload)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
