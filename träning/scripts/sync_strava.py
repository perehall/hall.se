#!/usr/bin/env python3
import json, os, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
TOKEN_FILE = Path(os.environ.get("STRAVA_REFRESH_TOKEN_FILE", "/tmp/strava_refresh_token"))


def post_form(url, payload):
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get_json(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


tokens = post_form("https://www.strava.com/oauth/token", {
    "client_id": os.environ["STRAVA_CLIENT_ID"],
    "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
    "grant_type": "refresh_token",
    "refresh_token": os.environ["STRAVA_REFRESH_TOKEN"],
})

access_token = tokens["access_token"]
new_refresh_token = tokens["refresh_token"]

# Persist the rotated token only on the ephemeral Actions runner.
# The workflow writes this file directly into the GitHub repository secret
# and then removes it. It is never committed or exposed as a workflow output.
TOKEN_FILE.write_text(new_refresh_token, encoding="utf-8")
os.chmod(TOKEN_FILE, 0o600)

state = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
known = {int(a["id"]) for a in state.get("activities", [])}
after = int((datetime.now(timezone.utc) - timedelta(days=14)).timestamp())

url = f"https://www.strava.com/api/v3/athlete/activities?after={after}&page=1&per_page=100"
summary = get_json(url, access_token)

new_items = []
for a in summary:
    aid = int(a["id"])
    if aid in known:
        continue
    d = get_json(f"https://www.strava.com/api/v3/activities/{aid}", access_token)
    new_items.append({
        "id": aid,
        "name": d.get("name"),
        "sport_type": d.get("sport_type") or d.get("type"),
        "start_date": d.get("start_date"),
        "start_date_local": d.get("start_date_local"),
        "distance_m": d.get("distance"),
        "moving_time_s": d.get("moving_time"),
        "elapsed_time_s": d.get("elapsed_time"),
        "total_elevation_gain_m": d.get("total_elevation_gain"),
        "average_heartrate": d.get("average_heartrate"),
        "max_heartrate": d.get("max_heartrate"),
        "average_watts": d.get("average_watts"),
        "weighted_average_watts": d.get("weighted_average_watts"),
        "calories": d.get("calories"),
        "device_name": d.get("device_name"),
        "source": "Strava API"
    })

if new_items:
    state["activities"] = sorted(
        state.get("activities", []) + new_items,
        key=lambda x: x.get("start_date") or "",
        reverse=True
    )

state["last_sync_utc"] = datetime.now(timezone.utc).isoformat()
ACTIVITIES_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"Synced {len(new_items)} new activities.")
