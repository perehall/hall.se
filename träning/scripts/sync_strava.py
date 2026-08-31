#!/usr/bin/env python3
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
DEFAULT_TOKEN_FILE = Path("/tmp/strava_refresh_token")
TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
ACTIVITY_URL = "https://www.strava.com/api/v3/activities"


def post_form(url, payload):
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def get_json(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def write_refresh_token(path, token):
    token = str(token or "").strip()
    if not token:
        raise RuntimeError("Strava: roterad refresh token saknas")
    path = Path(path)
    path.write_text(token, encoding="utf-8")
    os.chmod(path, 0o600)


def lap_summaries(detail):
    rows = detail.get("laps") if isinstance(detail, dict) else None
    if not isinstance(rows, list):
        return []
    result = []
    for index, lap in enumerate(rows, start=1):
        if not isinstance(lap, dict):
            continue
        result.append(
            {
                "lap_index": lap.get("lap_index") or index,
                "name": lap.get("name"),
                "elapsed_time_s": lap.get("elapsed_time"),
                "moving_time_s": lap.get("moving_time"),
                "distance_m": lap.get("distance"),
                "average_speed": lap.get("average_speed"),
                "average_heartrate": lap.get("average_heartrate"),
                "max_heartrate": lap.get("max_heartrate"),
                "average_watts": lap.get("average_watts"),
                "average_cadence": lap.get("average_cadence"),
            }
        )
    return result


def activity_from_detail(activity_id, detail):
    if not isinstance(detail, dict):
        raise RuntimeError(f"Strava: aktivitet {activity_id} gav oväntat detaljsvar")
    returned_id = detail.get("id")
    if returned_id is not None and int(returned_id) != int(activity_id):
        raise RuntimeError(
            f"Strava: detaljsvar id {returned_id!r} matchar inte begärt id {activity_id!r}"
        )
    sport_type = detail.get("sport_type") or detail.get("type")
    if not sport_type:
        raise RuntimeError(f"Strava: aktivitet {activity_id} saknar sport_type/type")
    start_date = detail.get("start_date")
    start_date_local = detail.get("start_date_local")
    if not start_date or not start_date_local:
        raise RuntimeError(f"Strava: aktivitet {activity_id} saknar startdatum")

    gear = detail.get("gear") if isinstance(detail.get("gear"), dict) else {}
    laps = lap_summaries(detail)
    mapped = {
        "id": int(activity_id),
        "name": detail.get("name"),
        "sport_type": sport_type,
        "start_date": start_date,
        "start_date_local": start_date_local,
        "distance_m": detail.get("distance"),
        "moving_time_s": detail.get("moving_time"),
        "elapsed_time_s": detail.get("elapsed_time"),
        "total_elevation_gain_m": detail.get("total_elevation_gain"),
        "average_heartrate": detail.get("average_heartrate"),
        "max_heartrate": detail.get("max_heartrate"),
        "average_watts": detail.get("average_watts"),
        "weighted_average_watts": detail.get("weighted_average_watts"),
        "calories": detail.get("calories"),
        "device_name": detail.get("device_name"),
        "gear_id": detail.get("gear_id"),
        "gear_name": gear.get("name"),
        "source": "Strava API",
    }
    if laps:
        mapped["laps"] = laps
    return mapped


def merge_new_activities(state, summary, fetch_detail):
    if not isinstance(state, dict):
        raise RuntimeError("Strava: activities-state måste vara objekt")
    if not isinstance(summary, list):
        raise RuntimeError("Strava: aktivitetslistan hade oväntat format")

    existing = state.get("activities") or []
    if not isinstance(existing, list):
        raise RuntimeError("Strava: activities måste vara lista")

    known = set()
    for activity in existing:
        activity_id = activity.get("id")
        if activity_id is None:
            raise RuntimeError("Strava: befintlig aktivitet saknar id")
        key = int(activity_id)
        if key in known:
            raise RuntimeError(f"Strava: dubbelt befintligt aktivitets-id {key}")
        known.add(key)

    new_items = []
    seen_summary = set()
    for row in summary:
        if not isinstance(row, dict) or row.get("id") is None:
            raise RuntimeError("Strava: aktivitetsöversikt innehåller rad utan id")
        activity_id = int(row["id"])
        if activity_id in seen_summary:
            continue
        seen_summary.add(activity_id)
        if activity_id in known:
            # Existing records may contain user-normalized semantics. Never replace
            # them with a fresh raw Strava representation during incremental sync.
            continue
        detail = fetch_detail(activity_id)
        new_items.append(activity_from_detail(activity_id, detail))
        known.add(activity_id)

    if new_items:
        state["activities"] = sorted(
            existing + new_items,
            key=lambda item: item.get("start_date") or "",
            reverse=True,
        )
    else:
        state["activities"] = existing
    return new_items


def exchange_tokens(env):
    required = ["STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN"]
    missing = [key for key in required if not str(env.get(key) or "").strip()]
    if missing:
        raise RuntimeError("Strava: miljövariabler saknas: " + ", ".join(missing))
    tokens = post_form(
        TOKEN_URL,
        {
            "client_id": env["STRAVA_CLIENT_ID"],
            "client_secret": env["STRAVA_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": env["STRAVA_REFRESH_TOKEN"],
        },
    )
    if not isinstance(tokens, dict):
        raise RuntimeError("Strava: token-svar hade oväntat format")
    access_token = str(tokens.get("access_token") or "").strip()
    refresh_token = str(tokens.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        raise RuntimeError("Strava: token-svar saknar access_token eller refresh_token")
    return access_token, refresh_token


def sync_state(state, access_token, *, now=None):
    now = now or datetime.now(timezone.utc)
    after = int((now - timedelta(days=14)).timestamp())
    url = f"{ACTIVITIES_URL}?after={after}&page=1&per_page=100"
    summary = get_json(url, access_token)

    def fetch_detail(activity_id):
        return get_json(f"{ACTIVITY_URL}/{activity_id}", access_token)

    new_items = merge_new_activities(state, summary, fetch_detail)
    state["last_sync_utc"] = now.isoformat()
    return new_items


def main():
    token_file = Path(os.environ.get("STRAVA_REFRESH_TOKEN_FILE", str(DEFAULT_TOKEN_FILE)))
    access_token, refresh_token = exchange_tokens(os.environ)

    # Persist only on the ephemeral Actions runner. The workflow writes this file
    # into the repository secret and then removes it; token contents are never logged.
    write_refresh_token(token_file, refresh_token)

    if not ACTIVITIES_FILE.exists():
        raise RuntimeError("Strava: activities.json saknas")
    state = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
    new_items = sync_state(state, access_token)
    ACTIVITIES_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Synced {len(new_items)} new activities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
