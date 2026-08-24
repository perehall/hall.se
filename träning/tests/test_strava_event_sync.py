#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_strava_event  # noqa: E402


class StravaEventSyncTests(unittest.TestCase):
    def event(self, *, aspect="create", event_key="sub:activity:7:create:1"):
        return {
            "object_type": "activity",
            "aspect_type": aspect,
            "object_id": 7,
            "event_time": 1,
            "event_key": event_key,
        }

    def detail(self, *, sport="Run", name="Nytt pass"):
        return {
            "id": 7,
            "name": name,
            "sport_type": sport,
            "start_date": "2026-08-24T08:00:00Z",
            "start_date_local": "2026-08-24T10:00:00Z",
            "distance": 10000,
            "moving_time": 3000,
            "elapsed_time": 3060,
            "total_elevation_gain": 90,
        }

    def test_parse_event_fails_closed(self):
        with self.assertRaises(RuntimeError):
            sync_strava_event.parse_event({"STRAVA_WEBHOOK_OBJECT_TYPE": "athlete"})

    def test_create_fetches_source_truth_and_appends(self):
        state = {"schema_version": 2, "activities": []}
        calls = []
        now = datetime(2026, 8, 24, 8, 1, tzinfo=timezone.utc)
        action = sync_strava_event.process_event(
            state,
            self.event(),
            lambda activity_id: calls.append(activity_id) or self.detail(),
            now=now,
        )
        self.assertEqual(action, "created")
        self.assertEqual(calls, [7])
        self.assertEqual(state["activities"][0]["sport_type"], "Run")
        self.assertEqual(state["last_webhook_event"]["event_key"], self.event()["event_key"])

    def test_update_rebuilds_raw_source_record_for_normalizer(self):
        state = {
            "schema_version": 2,
            "activities": [{
                "id": 7,
                "sport_type": "Enduro",
                "source_sport_type": "MountainBikeRide",
                "classification": "recreation",
                "display_label": "Enduro",
                "start_date": "2026-08-24T08:00:00Z",
                "start_date_local": "2026-08-24T10:00:00Z",
            }],
        }
        action = sync_strava_event.process_event(
            state,
            self.event(aspect="update", event_key="sub:activity:7:update:2"),
            lambda activity_id: self.detail(sport="MountainBikeRide", name="Ändrat namn"),
        )
        self.assertEqual(action, "updated")
        activity = state["activities"][0]
        self.assertEqual(activity["sport_type"], "MountainBikeRide")
        self.assertNotIn("classification", activity)
        self.assertNotIn("source_sport_type", activity)

    def test_delete_is_idempotent(self):
        base = {
            "schema_version": 2,
            "activities": [{
                "id": 7,
                "sport_type": "Run",
                "start_date": "2026-08-24T08:00:00Z",
                "start_date_local": "2026-08-24T10:00:00Z",
            }],
        }
        first = sync_strava_event.process_event(
            base,
            self.event(aspect="delete", event_key="sub:activity:7:delete:3"),
            lambda activity_id: self.fail("delete must not fetch detail"),
        )
        self.assertEqual(first, "deleted")
        self.assertEqual(base["activities"], [])

        duplicate = sync_strava_event.process_event(
            base,
            self.event(aspect="delete", event_key="sub:activity:7:delete:3"),
            lambda activity_id: self.fail("duplicate must not fetch detail"),
        )
        self.assertEqual(duplicate, "duplicate")

    def test_invalidate_coach_removes_stale_analysis_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coach.json"
            path.write_text(json.dumps({
                "analyses": [
                    {"activity_id": 7},
                    {"activity_id": 8},
                ],
                "last_trigger_hash": "stale",
            }), encoding="utf-8")
            self.assertTrue(sync_strava_event.invalidate_coach_activity(path, 7))
            coach = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual([entry["activity_id"] for entry in coach["analyses"]], [8])
            self.assertIsNone(coach["last_trigger_hash"])


if __name__ == "__main__":
    unittest.main()
