import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from supabase_shadow_model import (
    activity_records,
    canonical_hash,
    local_date,
    microcycle_records,
    override_and_feedback_records,
    workout_records,
)


class SupabaseShadowModelTests(unittest.TestCase):
    def test_local_date_does_not_interpret_misleading_z_as_utc(self):
        activity = {
            "id": 1,
            "start_date": "2026-09-23T17:12:15Z",
            "start_date_local": "2026-09-23T19:12:15Z",
        }
        self.assertEqual(local_date(activity), "2026-09-23")

    def test_activity_laps_are_separate_relational_records(self):
        doc = {
            "activities": [
                {
                    "id": 123,
                    "name": "Test swim",
                    "sport_type": "Swim",
                    "start_date": "2026-09-23T17:12:15Z",
                    "start_date_local": "2026-09-23T19:12:15Z",
                    "distance_m": 100.0,
                    "laps": [
                        {"lap_index": 1, "distance_m": 50.0, "elapsed_time_s": 40},
                        {"lap_index": 2, "distance_m": 50.0, "elapsed_time_s": 41},
                    ],
                }
            ]
        }
        activities, laps = activity_records(doc)
        self.assertEqual(len(activities), 1)
        self.assertEqual(len(laps), 2)
        self.assertEqual(activities[0]["sport_family"], "swim")
        self.assertNotIn("laps", activities[0]["raw"])
        self.assertEqual(laps[1]["provider_activity_id"], "123")

    def test_structured_feedback_keeps_event_key(self):
        overrides, feedback = override_and_feedback_records(
            {
                "overrides": {
                    "99": {
                        "sport": "Run",
                        "classification": "training",
                        "user_report": "Bra kontroll.",
                        "training_feedback": {
                            "text": "Bra kontroll.",
                            "rpe": 6,
                            "feeling": ["could_do_more"],
                            "operation": "ADD_FEEDBACK",
                            "event_key": "training-input:abc",
                            "submitted_at": "2026-09-24T07:47:55Z",
                        },
                    }
                }
            }
        )
        self.assertEqual(len(overrides), 1)
        self.assertEqual(feedback[0]["event_key"], "training-input:abc")
        self.assertEqual(feedback[0]["rpe"], 6)

    def test_legacy_feedback_gets_deterministic_idempotency_key(self):
        doc = {
            "overrides": {
                "99": {
                    "sport": "Run",
                    "classification": "training",
                    "user_report": "Tre gånger åtta.",
                }
            }
        }
        first = override_and_feedback_records(doc)[1][0]
        second = override_and_feedback_records(doc)[1][0]
        self.assertEqual(first["event_key"], second["event_key"])
        self.assertTrue(first["event_key"].startswith("legacy:99:"))

    def test_microcycle_decision_is_attached_only_to_matching_week(self):
        plan = {
            "meta": {
                "mesocycle_id": "m1",
                "microcycle_id": "m1:mc1",
                "microcycle_index": 1,
                "week_start": "2026-09-21",
            }
        }
        upcoming = {
            "week_key": "2026-W40",
            "meta": {
                "mesocycle_id": "m1",
                "microcycle_id": "m1:mc2",
                "microcycle_index": 2,
                "week_start": "2026-09-28",
            },
        }
        decision = {
            "week_start": "2026-09-28",
            "rationale": "next",
            "planner_revision": 7,
            "source": "openai",
            "source_hash": "abc",
        }
        rows = microcycle_records(plan, upcoming, decision)
        by_id = {row["id"]: row for row in rows}
        self.assertIsNone(by_id["m1:mc1"]["rationale"])
        self.assertEqual(by_id["m1:mc2"]["rationale"], "next")
        self.assertIn("decision", by_id["m1:mc2"]["payload"])

    def test_workout_key_is_stable_and_uses_slot(self):
        plan = {
            "days": [
                {
                    "date": "2026-09-22",
                    "session": "4 x 8",
                    "sport": "run",
                    "microcycle_id": "m1:mc1",
                    "mesocycle_id": "m1",
                    "microcycle_day": 2,
                    "microcycle_slot": "run_threshold",
                    "stimuli": ["run_threshold"],
                }
            ]
        }
        rows = workout_records(plan)
        self.assertEqual(
            rows[0]["workout_key"],
            "m1:mc1:2026-09-22:run_threshold",
        )

    def test_canonical_hash_is_order_independent_for_objects(self):
        self.assertEqual(canonical_hash({"a": 1, "b": 2}), canonical_hash({"b": 2, "a": 1}))


if __name__ == "__main__":
    unittest.main()
