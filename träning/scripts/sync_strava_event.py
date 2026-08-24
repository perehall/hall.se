#!/usr/bin/env python3
import json
import os
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import sync_strava

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
COACH_FILE = ROOT / "data" / "coach.json"
VALID_ASPECT_TYPES = {"create", "update", "delete"}


def parse_event(env):
    object_type = str(env.get("STRAVA_WEBHOOK_OBJECT_TYPE") or "").strip()
    aspect_type = str(env.get("STRAVA_WEBHOOK_ASPECT_TYPE") or "").strip()
    object_id = str(env.get("STRAVA_WEBHOOK_OBJECT_ID") or "").strip()
    event_time = str(env.get("STRAVA_WEBHOOK_EVENT_TIME") or "").strip()
    event_key = str(env.get("STRAVA_WEBHOOK_EVENT_KEY") or "").strip()

    if object_type != "activity":
        raise RuntimeError(f"Strava webhook: object_type måste vara 'activity', fick {object_type!r}")
    if aspect_type not in VALID_ASPECT_TYPES:
        raise RuntimeError(f"Strava webhook: ogiltig aspect_type {aspect_type!r}")
    if not object_id.isdigit():
        raise RuntimeError("Strava webhook: object_id måste vara positivt heltal")
    if not event_time.isdigit():
        raise RuntimeError("Strava webhook: event_time måste vara unix-tid")
    if not event_key:
        raise RuntimeError("Strava webhook: event_key saknas")

    return {
        "object_type": object_type,
        "aspect_type": aspect_type,
        "object_id": int(object_id),
        "event_time": int(event_time),
        "event_key": event_key,
    }


def _validated_activities(state):
    if not isinstance(state, dict):
        raise RuntimeError("Strava webhook: activities-state måste vara objekt")
    activities = state.get("activities")
    if not isinstance(activities, list):
        raise RuntimeError("Strava webhook: activities måste vara lista")
    seen = set()
    for activity in activities:
        activity_id = activity.get("id")
        if activity_id is None:
            raise RuntimeError("Strava webhook: befintlig aktivitet saknar id")
        key = int(activity_id)
        if key in seen:
            raise RuntimeError(f"Strava webhook: dubbelt aktivitets-id {key}")
        seen.add(key)
    return activities


def upsert_raw_activity(state, activity_id, detail):
    activities = _validated_activities(state)
    raw = sync_strava.activity_from_detail(activity_id, detail)
    replaced = False
    updated = []
    for activity in activities:
        if int(activity.get("id")) == int(activity_id):
            updated.append(raw)
            replaced = True
        else:
            updated.append(activity)
    if not replaced:
        updated.append(raw)
    state["activities"] = sorted(
        updated,
        key=lambda item: item.get("start_date") or "",
        reverse=True,
    )
    return "updated" if replaced else "created"


def delete_activity(state, activity_id):
    activities = _validated_activities(state)
    kept = [activity for activity in activities if int(activity.get("id")) != int(activity_id)]
    removed = len(activities) - len(kept)
    state["activities"] = kept
    return bool(removed)


def fetch_detail_with_retry(activity_id, access_token, *, attempts=3, sleep_fn=time.sleep):
    delays = [2, 5]
    for attempt in range(attempts):
        try:
            return sync_strava.get_json(f"{sync_strava.ACTIVITY_URL}/{activity_id}", access_token)
        except urllib.error.HTTPError as exc:
            retryable = exc.code in {404, 429, 500, 502, 503, 504}
            if not retryable or attempt >= attempts - 1:
                raise
        except urllib.error.URLError:
            if attempt >= attempts - 1:
                raise
        sleep_fn(delays[min(attempt, len(delays) - 1)])
    raise RuntimeError("Strava webhook: detaljhämtning misslyckades efter retries")


def process_event(state, event, fetch_detail, *, now=None):
    previous = state.get("last_webhook_event") or {}
    if previous.get("event_key") == event["event_key"]:
        return "duplicate"

    activity_id = event["object_id"]
    aspect_type = event["aspect_type"]
    if aspect_type in {"create", "update"}:
        action = upsert_raw_activity(state, activity_id, fetch_detail(activity_id))
    else:
        action = "deleted" if delete_activity(state, activity_id) else "delete_missing"

    now = now or datetime.now(timezone.utc)
    state["last_sync_utc"] = now.isoformat()
    state["last_webhook_event"] = {
        "event_key": event["event_key"],
        "object_id": activity_id,
        "aspect_type": aspect_type,
        "event_time": event["event_time"],
        "processed_at_utc": now.isoformat(),
    }
    return action


def invalidate_coach_activity(path, activity_id):
    if not path.exists():
        return False
    coach = json.loads(path.read_text(encoding="utf-8"))
    analyses = coach.get("analyses") or []
    filtered = [entry for entry in analyses if int(entry.get("activity_id", -1)) != int(activity_id)]
    changed = len(filtered) != len(analyses)
    if changed:
        coach["analyses"] = filtered
    if coach.get("last_trigger_hash") is not None:
        coach["last_trigger_hash"] = None
        changed = True
    if changed:
        path.write_text(json.dumps(coach, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main():
    event = parse_event(os.environ)
    token_file = Path(os.environ.get("STRAVA_REFRESH_TOKEN_FILE", str(sync_strava.DEFAULT_TOKEN_FILE)))
    access_token, refresh_token = sync_strava.exchange_tokens(os.environ)
    sync_strava.write_refresh_token(token_file, refresh_token)

    if not ACTIVITIES_FILE.exists():
        raise RuntimeError("Strava webhook: activities.json saknas")
    state = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))

    def fetch_detail(activity_id):
        return fetch_detail_with_retry(activity_id, access_token)

    action = process_event(state, event, fetch_detail)
    if action != "duplicate":
        ACTIVITIES_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        invalidate_coach_activity(COACH_FILE, event["object_id"])

    print(
        f"Strava webhook sync: event={event['event_key']} "
        f"activity={event['object_id']} aspect={event['aspect_type']} action={action}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
