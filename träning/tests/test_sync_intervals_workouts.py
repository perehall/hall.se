#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from device_workout import compile_device_workout  # noqa: E402
import sync_intervals_workouts as sync  # noqa: E402


def run_day(*, hill=False):
    if hill:
        candidate_id = "run-hill-3x7x150"
        blocks = [
            {
                "name": "Backkvalitet",
                "work": {"sets": 3, "repetitions_per_set": 7, "distance_m": 150},
                "instruction": "Kraftfull men kontrollerad",
                "intensity": "kraftfull men kontrollerad",
                "recovery": {"instruction": "Lugn joggvila"},
            }
        ]
        session = "Löpning · backkvalitet · 3 × 7 × 150 m"
    else:
        candidate_id = "run-threshold-3x10"
        blocks = [
            {
                "name": "Arbetsdel",
                "work": {"repetitions": 3, "duration_s": 600},
                "instruction": "Kontrollerad tröskel",
                "intensity": "kontrollerad tröskel",
                "recovery": {"duration_s": 90, "instruction": "Lugn jogg"},
            }
        ]
        session = "Löpning · kontrollerad tröskel · 3 × 10 min / 90 s jogg"
    return {
        "date": "2026-09-15",
        "status": "preliminary",
        "sport": "run",
        "microcycle_slot": "run_hill_quality" if hill else "run_threshold",
        "session": session,
        "workout_design": {
            "selected_candidate_id": candidate_id,
            "candidates": [
                {
                    "id": candidate_id,
                    "session": session,
                    "prescription": {
                        "executable": True,
                        "completeness": "full",
                        "blocks": blocks,
                    },
                }
            ],
        },
    }


def swim_day():
    session = "Simning · 3 200 m · aerob/teknik"
    return {
        "date": "2026-09-15",
        "status": "preliminary",
        "sport": "swim",
        "microcycle_slot": "swim_support",
        "session": session,
        "workout_design": {
            "selected_candidate_id": "swim-3200",
            "candidates": [
                {
                    "id": "swim-3200",
                    "session": session,
                    "prescription": {
                        "executable": True,
                        "completeness": "full",
                        "blocks": [
                            {
                                "name": "Insim",
                                "work": {"repetitions": 1, "distance_m": 400},
                                "instruction": "Lugn insim",
                                "intensity": "warmup",
                            },
                            {
                                "name": "Aerob",
                                "work": {"repetitions": 4, "distance_m": 500},
                                "instruction": "Stadigt aerob",
                                "intensity": "active",
                                "recovery": {"duration_s": 30},
                            },
                        ],
                    },
                }
            ],
        },
    }


class IntervalsWorkoutSyncTests(unittest.TestCase):
    def test_threshold_description_uses_supported_text_syntax(self):
        workout = compile_device_workout(run_day())
        description = sync.render_description(workout)
        self.assertIn("Arbetsdel 3x", description)
        self.assertIn("- Kontrollerad tröskel 10m intensity=interval", description)
        self.assertIn("- Lugn jogg 90s intensity=rest", description)

    def test_hill_recovery_uses_press_lap_transport_placeholder(self):
        workout = compile_device_workout(run_day(hill=True))
        description = sync.render_description(workout)
        self.assertIn("Backkvalitet set 1 7x", description)
        self.assertIn("150mtr intensity=interval", description)
        self.assertIn("Lugn joggvila Press lap 1s intensity=rest", description)

    def test_swim_distance_uses_mtr_not_minute_token(self):
        workout = compile_device_workout(swim_day())
        description = sync.render_description(workout)
        self.assertIn("400mtr", description)
        self.assertIn("500mtr", description)
        self.assertNotIn("400m intensity", description)

    def test_reconcile_upserts_desired_deletes_stale_and_records_verified_transport(self):
        day = run_day()
        workout = compile_device_workout(day)
        day["device_workout"] = workout
        day["device_sync"] = {
            "status": "pending",
            "transport": "intervals_icu",
            "source_hash": workout["source_hash"],
            "device_delivery": "unverified",
        }
        documents = {
            "plan": {"days": [day]},
            "upcoming": {"days": []},
        }
        desired_payload = sync.payload_for(workout)
        initial = [
            {
                "id": 88,
                "category": "WORKOUT",
                "external_id": "hall-training:legacy-swim",
                "type": "Swim",
                "name": "Old",
                "description": "Old",
                "start_date_local": "2026-09-15T00:00:00",
            }
        ]
        refreshed = [
            {
                "id": 99,
                **desired_payload,
            }
        ]
        stored = {
            "id": 99,
            "category": "WORKOUT",
            "workout_doc": {
                "steps": [
                    {
                        "reps": 3,
                        "steps": [
                            {
                                "intensity": "interval",
                                "duration": 600,
                                "text": "Kontrollerad tröskel",
                            },
                            {
                                "intensity": "rest",
                                "duration": 90,
                                "text": "Lugn jogg",
                            },
                        ],
                    }
                ]
            },
        }
        list_calls = 0
        calls = []

        def fake_request(url, auth, *, method="GET", payload_data=None):
            nonlocal list_calls
            calls.append((url, method, payload_data))
            if url.startswith(sync.API_BASE + "/events?"):
                list_calls += 1
                return initial if list_calls == 1 else refreshed
            if url == sync.BULK_DELETE_URL:
                return 1
            if url == sync.BULK_UPSERT_URL:
                return refreshed
            if url == sync.API_BASE + "/events/99":
                return stored
            self.fail(f"Unexpected request: {method} {url}")

        with patch("sync_intervals_workouts.request_json", side_effect=fake_request):
            desired, deleted, upserted = sync.reconcile(
                documents,
                "AUTH",
                "2026-09-15",
                "2026-09-21",
            )

        self.assertEqual((desired, deleted, upserted), (1, 1, 1))
        self.assertEqual(day["device_sync"]["status"], "synced")
        self.assertEqual(day["device_sync"]["provider_event_id"], 99)
        self.assertEqual(day["device_sync"]["device_delivery"], "unverified")
        self.assertTrue(any(url == sync.BULK_DELETE_URL for url, _, _ in calls))
        self.assertTrue(any(url == sync.BULK_UPSERT_URL for url, _, _ in calls))


if __name__ == "__main__":
    unittest.main()
