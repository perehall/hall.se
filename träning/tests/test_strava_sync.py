#!/usr/bin/env python3
import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_strava  # noqa: E402


class StravaSyncTests(unittest.TestCase):
    def detail(self, activity_id=2, start="2026-08-23T08:00:00Z"):
        return {
            "id": activity_id,
            "name": "Testpass",
            "sport_type": "Run",
            "start_date": start,
            "start_date_local": start,
            "distance": 12345.6,
            "moving_time": 3600,
            "elapsed_time": 3660,
            "total_elevation_gain": 123.4,
            "average_heartrate": 140.2,
            "max_heartrate": 166.0,
            "average_watts": 270.5,
            "weighted_average_watts": 276,
            "calories": 750.0,
            "device_name": "Garmin Forerunner 970",
        }

    def test_detail_mapping_is_exact_and_source_is_explicit(self):
        mapped = sync_strava.activity_from_detail(2, self.detail())
        self.assertEqual(mapped["id"], 2)
        self.assertEqual(mapped["sport_type"], "Run")
        self.assertEqual(mapped["distance_m"], 12345.6)
        self.assertEqual(mapped["elapsed_time_s"], 3660)
        self.assertEqual(mapped["device_name"], "Garmin Forerunner 970")
        self.assertEqual(mapped["source"], "Strava API")

    def test_mismatched_detail_id_fails_closed(self):
        detail = self.detail(activity_id=999)
        with self.assertRaises(RuntimeError):
            sync_strava.activity_from_detail(2, detail)

    def test_existing_normalized_activity_is_not_fetched_or_overwritten(self):
        existing = {
            "id": 1,
            "sport_type": "Enduro",
            "source_sport_type": "MountainBikeRide",
            "classification": "recreation",
            "display_label": "Enduro",
            "start_date": "2026-08-22T09:30:31Z",
            "start_date_local": "2026-08-22T11:30:31Z",
        }
        state = {"activities": [existing.copy()]}
        fetched = []

        def fetch_detail(activity_id):
            fetched.append(activity_id)
            return self.detail(activity_id)

        new_items = sync_strava.merge_new_activities(state, [{"id": 1}], fetch_detail)
        self.assertEqual(new_items, [])
        self.assertEqual(fetched, [])
        self.assertEqual(state["activities"][0]["sport_type"], "Enduro")
        self.assertEqual(state["activities"][0]["classification"], "recreation")

    def test_new_activities_are_deduplicated_and_sorted_newest_first(self):
        state = {
            "activities": [
                {
                    "id": 1,
                    "sport_type": "Run",
                    "start_date": "2026-08-20T08:00:00Z",
                    "start_date_local": "2026-08-20T10:00:00Z",
                }
            ]
        }
        details = {
            2: self.detail(2, "2026-08-21T08:00:00Z"),
            3: self.detail(3, "2026-08-23T08:00:00Z"),
        }
        fetched = []

        def fetch_detail(activity_id):
            fetched.append(activity_id)
            return details[activity_id]

        new_items = sync_strava.merge_new_activities(
            state,
            [{"id": 3}, {"id": 2}, {"id": 3}, {"id": 1}],
            fetch_detail,
        )
        self.assertEqual(fetched, [3, 2])
        self.assertEqual([item["id"] for item in new_items], [3, 2])
        self.assertEqual([item["id"] for item in state["activities"]], [3, 2, 1])

    def test_duplicate_existing_ids_fail_before_network_fetch(self):
        base = {
            "id": 1,
            "sport_type": "Run",
            "start_date": "2026-08-20T08:00:00Z",
            "start_date_local": "2026-08-20T10:00:00Z",
        }
        state = {"activities": [base.copy(), base.copy()]}
        with self.assertRaises(RuntimeError):
            sync_strava.merge_new_activities(state, [], lambda activity_id: None)

    def test_refresh_token_file_is_mode_0600(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "token"
            sync_strava.write_refresh_token(path, "rotated-secret")
            self.assertEqual(path.read_text(encoding="utf-8"), "rotated-secret")
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, 0o600)

    def test_exchange_tokens_validates_response_without_logging_secret(self):
        env = {
            "STRAVA_CLIENT_ID": "id",
            "STRAVA_CLIENT_SECRET": "secret",
            "STRAVA_REFRESH_TOKEN": "old-refresh",
        }
        with patch.object(
            sync_strava,
            "post_form",
            return_value={"access_token": "access", "refresh_token": "new-refresh"},
        ) as post:
            access, refresh = sync_strava.exchange_tokens(env)
        self.assertEqual((access, refresh), ("access", "new-refresh"))
        self.assertEqual(post.call_args.args[0], sync_strava.TOKEN_URL)
        self.assertEqual(post.call_args.args[1]["grant_type"], "refresh_token")

    def test_sync_state_uses_14_day_window_and_detail_endpoint(self):
        state = {"activities": []}
        now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
        detail = self.detail(2)
        calls = []

        def fake_get_json(url, token):
            calls.append((url, token))
            if url.startswith(sync_strava.ACTIVITIES_URL + "?"):
                return [{"id": 2}]
            if url == f"{sync_strava.ACTIVITY_URL}/2":
                return detail
            raise AssertionError(url)

        with patch.object(sync_strava, "get_json", side_effect=fake_get_json):
            new_items = sync_strava.sync_state(state, "access-token", now=now)

        expected_after = int((now - sync_strava.timedelta(days=14)).timestamp())
        self.assertIn(f"after={expected_after}", calls[0][0])
        self.assertEqual(calls[1][0], f"{sync_strava.ACTIVITY_URL}/2")
        self.assertEqual(new_items[0]["id"], 2)
        self.assertEqual(state["last_sync_utc"], now.isoformat())

    def test_main_can_run_fully_mocked_without_network(self):
        initial_state = {"schema_version": 2, "activities": []}
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            activities_file = tmp_path / "activities.json"
            token_file = tmp_path / "refresh"
            activities_file.write_text(json.dumps(initial_state), encoding="utf-8")

            env = {
                "STRAVA_CLIENT_ID": "id",
                "STRAVA_CLIENT_SECRET": "secret",
                "STRAVA_REFRESH_TOKEN": "old",
                "STRAVA_REFRESH_TOKEN_FILE": str(token_file),
            }
            with patch.dict(os.environ, env, clear=False), \
                 patch.object(sync_strava, "ACTIVITIES_FILE", activities_file), \
                 patch.object(sync_strava, "exchange_tokens", return_value=("access", "rotated")), \
                 patch.object(sync_strava, "sync_state") as sync_state:
                def mutate(state, access_token):
                    state["activities"] = [
                        {
                            "id": 7,
                            "sport_type": "Run",
                            "start_date": "2026-08-23T08:00:00Z",
                            "start_date_local": "2026-08-23T10:00:00Z",
                        }
                    ]
                    state["last_sync_utc"] = "2026-08-23T12:00:00+00:00"
                    return state["activities"]
                sync_state.side_effect = mutate
                self.assertEqual(sync_strava.main(), 0)

            rendered = json.loads(activities_file.read_text(encoding="utf-8"))
            self.assertEqual(rendered["activities"][0]["id"], 7)
            self.assertEqual(token_file.read_text(encoding="utf-8"), "rotated")
            self.assertEqual(stat.S_IMODE(token_file.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
