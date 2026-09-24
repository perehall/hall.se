#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from supabase_activity_backend import (  # noqa: E402
    _documents_from_relational_cursor,
    build_activity_snapshot,
    canonical_hash,
    load_activities_for_runtime,
    safe_error_detail,
    strict_structure_difference,
)


class _SequencedCursor:
    def __init__(self, result_sets):
        self.result_sets = list(result_sets)
        self.index = -1

    def execute(self, _query, _params=None):
        self.index += 1

    def fetchall(self):
        return self.result_sets[self.index]


class SupabaseActivityBackendModelTests(unittest.TestCase):
    def test_snapshot_preserves_normalized_activity_and_feedback_documents(self):
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            activities = {
                "schema_version": 4,
                "last_sync_utc": "2026-09-24T16:00:00+00:00",
                "activities": [
                    {
                        "id": 123,
                        "name": "Enduro",
                        "sport_type": "Enduro",
                        "source_sport_type": "EMountainBikeRide",
                        "display_label": "Enduro",
                        "classification": "training",
                        "start_date": "2026-09-24T14:00:00Z",
                        "start_date_local": "2026-09-24T16:00:00Z",
                        "distance_m": 1000.0,
                        "moving_time_s": 3600,
                        "elapsed_time_s": 3700,
                        "total_elevation_gain_m": 50.0,
                        "average_heartrate": 120.0,
                        "max_heartrate": 150.0,
                        "average_watts": None,
                        "weighted_average_watts": None,
                        "calories": 500.0,
                        "device_name": "Garmin",
                        "gear_id": None,
                        "gear_name": None,
                        "plan_relation": "separate",
                        "user_report": "Pigg. RPE 4/10.",
                        "laps": [
                            {
                                "lap_index": 1,
                                "name": "Lap 1",
                                "elapsed_time_s": 3700,
                                "moving_time_s": 3600,
                                "distance_m": 1000.0,
                                "average_speed": 0.27,
                                "average_heartrate": 120.0,
                                "max_heartrate": 150.0,
                                "average_watts": None,
                                "average_cadence": None,
                            }
                        ],
                    }
                ],
            }
            overrides = {
                "schema_version": 1,
                "overrides": {
                    "123": {
                        "sport": "Enduro",
                        "classification": "training",
                        "display_label": "Enduro",
                        "source_sport_type": "EMountainBikeRide",
                        "plan_relation": "separate",
                        "user_report": "Pigg. RPE 4/10.",
                        "training_feedback": {
                            "text": "Pigg.",
                            "rpe": 4,
                            "feeling": ["fresh"],
                            "operation": "ADD_SPONTANEOUS_WORKOUT",
                            "event_key": "training-input:" + "a" * 24,
                            "submitted_at": "2026-09-24T16:10:00+02:00",
                        },
                    }
                },
            }
            (data / "activities.json").write_text(
                json.dumps(activities, ensure_ascii=False),
                encoding="utf-8",
            )
            (data / "activity_overrides.json").write_text(
                json.dumps(overrides, ensure_ascii=False),
                encoding="utf-8",
            )

            snapshot = build_activity_snapshot(data)

            self.assertEqual(snapshot["counts"]["activities"], 1)
            self.assertEqual(snapshot["counts"]["activity_laps"], 1)
            self.assertEqual(snapshot["counts"]["activity_overrides"], 1)
            self.assertEqual(snapshot["counts"]["activity_feedback_current_projection"], 1)
            self.assertEqual(snapshot["activities"][0]["sport_type"], "Enduro")
            self.assertEqual(snapshot["activities"][0]["raw"]["user_report"], "Pigg. RPE 4/10.")
            self.assertEqual(
                snapshot["activity_feedback"][0]["event_key"],
                "training-input:" + "a" * 24,
            )
            docs = {row["document_key"]: row for row in snapshot["state_documents"]}
            self.assertEqual(
                docs["activities"]["source_hash"],
                canonical_hash(activities),
            )
            self.assertEqual(
                docs["activity_overrides"]["source_hash"],
                canonical_hash(overrides),
            )

    def test_relational_readback_reconstructs_exact_promoted_documents(self):
        activity = {
            "id": 123,
            "name": "Run",
            "sport_type": "Run",
            "start_date": "2026-09-24T14:00:00Z",
            "start_date_local": "2026-09-24T16:00:00Z",
            "moving_time_s": 1800,
            "elapsed_time_s": 1800,
            "laps": [
                {
                    "lap_index": 1,
                    "name": "Lap 1",
                    "elapsed_time_s": 1800,
                    "moving_time_s": 1800,
                    "distance_m": 5000.0,
                }
            ],
        }
        activity_raw = dict(activity)
        laps = activity_raw.pop("laps")
        activities_doc = {
            "schema_version": 4,
            "last_sync_utc": "2026-09-24T16:00:00+00:00",
            "activities": [activity],
        }
        overrides_doc = {
            "schema_version": 1,
            "overrides": {
                "123": {
                    "sport": "Run",
                    "classification": "training",
                    "display_label": "Löpning",
                    "source_sport_type": "Run",
                    "user_report": "Kontrollerat.",
                }
            },
        }
        cursor = _SequencedCursor(
            [
                [
                    ("activities", canonical_hash(activities_doc), activities_doc),
                    (
                        "activity_overrides",
                        canonical_hash(overrides_doc),
                        overrides_doc,
                    ),
                ],
                [("123", activity_raw)],
                [("123", 1, laps[0])],
                [("123", overrides_doc["overrides"]["123"])],
            ]
        )

        activities, overrides, meta = _documents_from_relational_cursor(cursor)

        self.assertEqual(activities, activities_doc)
        self.assertEqual(overrides, overrides_doc)
        self.assertEqual(meta["source"], "supabase_db")
        self.assertTrue(meta["verified"])

    def test_runtime_loader_uses_local_only_without_database_configuration(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "activities.json"
            document = {"activities": [{"id": 1}]}
            path.write_text(json.dumps(document), encoding="utf-8")
            loaded, meta = load_activities_for_runtime(path, env={})
            self.assertEqual(loaded, document)
            self.assertEqual(meta["source"], "json_local_dev")
            self.assertFalse(meta["verified"])

    def test_strict_structure_difference_reports_path_and_types_only(self):
        detail = strict_structure_difference(
            {"activities": [{"distance_m": 1000.0}]},
            {"activities": [{"distance_m": 1000}]},
        )
        self.assertEqual(
            detail,
            "$.activities[0].distance_m: expected_type=float actual_type=int",
        )

    def test_safe_error_detail_logs_contracts_but_not_driver_messages(self):
        self.assertEqual(
            safe_error_detail(RuntimeError("Current activity key-set mismatch")),
            "RuntimeError:Current activity key-set mismatch",
        )

        class DriverError(Exception):
            pass

        detail = safe_error_detail(
            DriverError("postgresql://user:secret@example.invalid/db")
        )
        self.assertEqual(detail, "DriverError")
        self.assertNotIn("secret", detail)

    def test_snapshot_rejects_override_for_missing_activity(self):
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            (data / "activities.json").write_text(
                json.dumps({"activities": []}),
                encoding="utf-8",
            )
            (data / "activity_overrides.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "overrides": {
                            "999": {
                                "sport": "Run",
                                "classification": "training",
                                "user_report": "Bra.",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                build_activity_snapshot(data)


if __name__ == "__main__":
    unittest.main()
