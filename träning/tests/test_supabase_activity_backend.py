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
    overlay_feedback_document,
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

    def test_duplicate_source_lap_indexes_get_unique_ordinals(self):
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            activities = {
                "activities": [
                    {
                        "id": 123,
                        "name": "Historical run",
                        "sport_type": "Run",
                        "start_date": "2026-09-24T14:00:00Z",
                        "start_date_local": "2026-09-24T16:00:00Z",
                        "laps": [
                            {"lap_index": 1, "distance_m": 1000.0},
                            {"lap_index": 1, "distance_m": 2000.0},
                            {"lap_index": 2, "distance_m": 3000.0},
                        ],
                    }
                ]
            }
            (data / "activities.json").write_text(
                json.dumps(activities),
                encoding="utf-8",
            )
            (data / "activity_overrides.json").write_text(
                json.dumps({"schema_version": 1, "overrides": {}}),
                encoding="utf-8",
            )

            snapshot = build_activity_snapshot(data)

            self.assertEqual(
                [row["lap_ordinal"] for row in snapshot["activity_laps"]],
                [1, 2, 3],
            )
            self.assertEqual(
                [row["lap_index"] for row in snapshot["activity_laps"]],
                [1, 1, 2],
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

        activities, overrides, meta = _documents_from_relational_cursor(
            cursor,
            include_feedback_overlay=False,
        )

        self.assertEqual(activities, activities_doc)
        self.assertEqual(overrides, overrides_doc)
        self.assertEqual(meta["source"], "supabase_db")
        self.assertTrue(meta["verified"])

    def test_append_only_feedback_overlays_stale_override_projection(self):
        activities = {
            "activities": [
                {
                    "id": 123,
                    "sport_type": "Run",
                    "source_sport_type": "Run",
                    "display_label": "Löpning",
                    "classification": "training",
                }
            ]
        }
        overrides = {"schema_version": 1, "overrides": {}}
        feedback_rows = [
            {
                "provider_activity_id": "123",
                "operation": "ADD_FEEDBACK",
                "feedback_text": "Första.",
                "rpe": 6,
                "feeling": ["fresh"],
                "event_key": "training-input:" + "a" * 24,
                "submitted_at": "2026-09-25T05:00:00+00:00",
                "created_at": "2026-09-25T05:00:01+00:00",
            },
            {
                "provider_activity_id": "123",
                "operation": "ADD_FEEDBACK",
                "feedback_text": "Senaste.",
                "rpe": 4,
                "feeling": ["fresh", "could_do_more"],
                "event_key": "training-input:" + "b" * 24,
                "submitted_at": "2026-09-25T05:10:00+00:00",
                "created_at": "2026-09-25T05:10:01+00:00",
            },
        ]

        effective = overlay_feedback_document(activities, overrides, feedback_rows)
        row = effective["overrides"]["123"]
        self.assertEqual(row["sport"], "Run")
        self.assertEqual(row["classification"], "training")
        self.assertEqual(row["training_feedback"]["text"], "Senaste.")
        self.assertEqual(row["training_feedback"]["rpe"], 4)
        self.assertEqual(
            row["training_input_event_keys"],
            [
                "training-input:" + "a" * 24,
                "training-input:" + "b" * 24,
            ],
        )
        self.assertEqual(
            row["last_training_input_event_key"],
            "training-input:" + "b" * 24,
        )

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
