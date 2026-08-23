#!/usr/bin/env python3
import os
import sys
import unittest
from datetime import datetime as RealDateTime
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_intervals_swim as swim_sync  # noqa: E402


class FixedDateTime(RealDateTime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 8, 23, 12, 0, 0, tzinfo=tz)


def blocks_fixture():
    return [
        {
            "name": "Uppvärmning",
            "steps": [
                {"kind": "swim", "text": "Lugnt", "distance_m": 50, "intensity": "warmup"}
            ],
        },
        {
            "name": "Setvila",
            "steps": [
                {"kind": "lap_rest", "text": "Starta main", "duration_s": 60}
            ],
        },
        {
            "name": "Main",
            "steps": [
                {"kind": "swim", "text": "Aerob", "distance_m": 50, "intensity": "active"},
                {"kind": "rest", "duration_s": 20},
            ],
        },
    ]


def workout_fixture():
    blocks = blocks_fixture()
    return {
        "id": "swim-test",
        "date": "2026-08-24",
        "name": "Swim test",
        "type": "Swim",
        "planned_distance_m": 100,
        "description": swim_sync.render_description(blocks),
        "external_id": "hall-training-swim-test",
        "semantic_expectations": swim_sync.semantic_expectations(blocks),
    }


class IntervalsSwimSyncTests(unittest.TestCase):
    def test_description_encodes_fixed_rest_and_press_lap_rest(self):
        description = swim_sync.render_description(blocks_fixture())
        self.assertIn("- Vila 20s intensity=rest", description)
        self.assertIn("- Press lap Starta main 1m intensity=rest", description)
        self.assertIn("- Aerob 50mtr intensity=active", description)

    def test_eligible_workout_uses_structured_plan_and_stable_external_id(self):
        plan = {
            "meta": {"timezone": "Europe/Stockholm"},
            "days": [
                {
                    "date": "2026-08-24",
                    "status": "planned",
                    "sport": "swim",
                    "watch_workout": {
                        "sync_enabled": True,
                        "id": "swim-test",
                        "external_id": "hall-training-swim-test",
                        "name": "Swim test",
                        "type": "Swim",
                        "planned_distance_m": 100,
                        "blocks": blocks_fixture(),
                    },
                }
            ],
        }
        with patch.object(swim_sync, "datetime", FixedDateTime):
            workouts = swim_sync.eligible_workouts(plan)
        self.assertEqual(len(workouts), 1)
        self.assertEqual(workouts[0]["planned_distance_m"], 100)
        self.assertEqual(workouts[0]["external_id"], "hall-training-swim-test")

    def test_payload_is_native_intervals_workout_upsert_shape(self):
        workout = workout_fixture()
        events = swim_sync.payload([workout])
        self.assertEqual(
            events,
            [
                {
                    "category": "WORKOUT",
                    "start_date_local": "2026-08-24T00:00:00",
                    "type": "Swim",
                    "name": "Swim test",
                    "description": workout["description"],
                    "external_id": "hall-training-swim-test",
                }
            ],
        )

    def test_semantic_verifier_accepts_intervals_interval_alias_for_active(self):
        workout = workout_fixture()
        workout_doc = {
            "distance": 100,
            "steps": [
                {"text": "Lugnt", "intensity": "warmup"},
                {"text": "Starta main", "intensity": "rest"},
                {"text": "Aerob", "intensity": "interval"},
                {"text": "Vila", "intensity": "rest"},
            ],
        }
        swim_sync.verify_semantics(workout_doc, workout)

    def test_semantic_verifier_fails_closed_when_lap_rest_disappears(self):
        workout = workout_fixture()
        workout_doc = {
            "distance": 100,
            "steps": [
                {"text": "Lugnt", "intensity": "warmup"},
                {"text": "Aerob", "intensity": "interval"},
                {"text": "Vila", "intensity": "rest"},
            ],
        }
        with self.assertRaises(RuntimeError):
            swim_sync.verify_semantics(workout_doc, workout)

    def test_send_contract_is_verified_without_real_network(self):
        workout = workout_fixture()
        events = swim_sync.payload([workout])
        post_response = [
            {
                "id": 123,
                "category": "WORKOUT",
                "external_id": "hall-training-swim-test",
                "name": "Swim test",
                "start_date_local": "2026-08-24T00:00:00",
            }
        ]
        stored_response = {
            "id": 123,
            "category": "WORKOUT",
            "workout_doc": {
                "distance": 100,
                "steps": [
                    {"text": "Lugnt", "intensity": "warmup"},
                    {"text": "Starta main", "intensity": "rest"},
                    {"text": "Aerob", "intensity": "active"},
                    {"text": "Vila", "intensity": "rest"},
                ],
            },
        }
        with patch.dict(os.environ, {"INTERVALS_API_KEY": "test-secret"}, clear=False):
            with patch.object(swim_sync, "request_json", side_effect=[post_response, stored_response]) as request:
                swim_sync.send(events, [workout])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[0], swim_sync.API_URL)
        self.assertEqual(request.call_args_list[1].args[0], f"{swim_sync.API_BASE}/events/123")

    def test_send_fails_closed_on_unstructured_readback(self):
        workout = workout_fixture()
        events = swim_sync.payload([workout])
        post_response = [{"id": 123, "category": "WORKOUT", "external_id": workout["external_id"]}]
        stored_response = {"id": 123, "category": "WORKOUT", "workout_doc": {"steps": []}}
        with patch.dict(os.environ, {"INTERVALS_API_KEY": "test-secret"}, clear=False):
            with patch.object(swim_sync, "request_json", side_effect=[post_response, stored_response]):
                with self.assertRaises(RuntimeError):
                    swim_sync.send(events, [workout])


if __name__ == "__main__":
    unittest.main()
