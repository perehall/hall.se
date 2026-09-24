import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from supabase_shadow_reader import (
    compare_key_sets,
    expected_key_sets,
    normalize_timestamp,
)


class SupabaseShadowReaderTests(unittest.TestCase):
    def test_normalize_timestamp_equates_z_and_utc_datetime(self):
        self.assertEqual(
            normalize_timestamp("2026-09-24T12:34:56Z"),
            normalize_timestamp(
                datetime(2026, 9, 24, 12, 34, 56, tzinfo=timezone.utc)
            ),
        )

    def test_compare_key_sets_rejects_stale_rows(self):
        with self.assertRaisesRegex(RuntimeError, "extra=.*stale"):
            compare_key_sets("activities", {"wanted"}, {"wanted", "stale"}, exact=True)

    def test_compare_key_sets_allows_historical_extra_rows_when_not_exact(self):
        compare_key_sets(
            "activities",
            {"wanted"},
            {"wanted", "historical"},
            exact=False,
        )

    def test_compare_key_sets_rejects_missing_rows(self):
        with self.assertRaisesRegex(RuntimeError, "missing=.*wanted"):
            compare_key_sets("activities", {"wanted"}, set(), exact=False)

    def test_expected_keys_use_external_activity_identity(self):
        payload = {
            "activities": [
                {"provider": "strava", "provider_activity_id": "123"}
            ],
            "activity_laps": [
                {
                    "provider": "strava",
                    "provider_activity_id": "123",
                    "lap_ordinal": 1,
                    "lap_index": 2,
                }
            ],
            "activity_overrides": [
                {"provider": "strava", "provider_activity_id": "123"}
            ],
            "activity_feedback": [{"event_key": "feedback:123"}],
            "training_goals": [{"goal_id": "g1"}],
            "state_documents": [{"document_key": "plan"}],
            "mesocycles": [{"id": "m1"}],
            "microcycles": [{"id": "m1:mc1"}],
            "planned_workouts": [{"workout_key": "m1:mc1:day-1"}],
            "coach_evaluations": [
                {
                    "provider": "strava",
                    "provider_activity_id": "123",
                    "generated_at": "2026-09-24T12:34:56Z",
                }
            ],
        }
        keys = expected_key_sets(payload)
        self.assertEqual(keys["activities"], {("strava", "123")})
        self.assertEqual(keys["activity_laps"], {("strava", "123", 1)})
        self.assertEqual(
            keys["coach_evaluations"],
            {("strava", "123", "2026-09-24T12:34:56.000000+00:00")},
        )


if __name__ == "__main__":
    unittest.main()
