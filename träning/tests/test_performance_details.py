#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from sync_performance_details import (  # noqa: E402
    add_comparisons,
    infer_threshold_protocol,
    match_activity,
    sync,
)


def interval(seconds, distance, hr, watts=None, kind="WORK"):
    return {
        "type": kind,
        "moving_time": seconds,
        "distance": distance,
        "average_heartrate": hr,
        "max_heartrate": hr + 4,
        "average_watts": watts,
        "average_cadence": 88,
    }


class PerformanceDetailTests(unittest.TestCase):
    def test_utc_start_date_match_survives_missing_intervals_local_time(self):
        activity = {
            "sport_type": "Run",
            "start_date": "2026-08-25T17:34:18Z",
            "start_date_local": "2026-08-25T19:34:18Z",
        }
        rows = [
            {
                "id": "i-utc",
                "type": "Run",
                "source": "GARMIN",
                "start_date": "2026-08-25T17:34:18Z",
            }
        ]
        self.assertEqual(match_activity(activity, rows)["id"], "i-utc")

    def test_prefers_garmin_match_at_same_start_time(self):
        activity = {
            "sport_type": "Run",
            "start_date_local": "2026-08-25T19:34:18Z",
        }
        rows = [
            {"id": "i-strava", "type": "Run", "source": "STRAVA", "start_date_local": "2026-08-25T19:34:18"},
            {"id": "i-garmin", "type": "Run", "source": "GARMIN", "start_date_local": "2026-08-25T19:34:18"},
        ]
        self.assertEqual(match_activity(activity, rows)["id"], "i-garmin")

    def test_explicit_user_report_can_correct_stale_plan_protocol(self):
        activity = {
            "sport_type": "Run",
            "user_report": "3×8 min tröskel. Kontrollerad känsla.",
        }
        detail = {
            "icu_intervals": [
                interval(481, 1990, 151),
                interval(479, 1995, 153),
                interval(482, 2002, 155),
            ]
        }
        detected = infer_threshold_protocol(activity, detail)
        self.assertEqual(detected["marker_id"], "run-threshold-control")
        self.assertEqual(detected["protocol_key"], "run_threshold:3x8")

    def test_four_by_eight_threshold_is_fingerprinted_from_explicit_report(self):
        activity = {
            "sport_type": "Run",
            "user_report": "4×8 min Tempo enligt Garmin. Kontrollerat.",
        }
        detail = {
            "icu_intervals": [
                interval(480, 2010, 150),
                interval(481, 2020, 152),
                interval(479, 2030, 154),
                interval(482, 2040, 155),
            ]
        }
        detected = infer_threshold_protocol(activity, detail)
        self.assertEqual(detected["protocol_key"], "run_threshold:4x8")
        self.assertEqual(len(detected["work_rows"]), 4)

    def test_explicit_four_by_eight_can_disambiguate_extra_provider_work_row(self):
        activity = {
            "sport_type": "Run",
            "user_report": "4×8 min Tempo enligt Garmin.",
        }
        detail = {
            "icu_intervals": [
                interval(480, 2000, 150),
                interval(482, 2010, 151),
                interval(479, 2020, 153),
                interval(481, 2030, 154),
                interval(420, 1700, 145),
            ]
        }
        detected = infer_threshold_protocol(activity, detail)
        self.assertEqual(detected["protocol_key"], "run_threshold:4x8")
        self.assertEqual(len(detected["work_rows"]), 4)
        self.assertTrue(all(row["moving_time"] >= 479 for row in detected["work_rows"]))

    def test_four_by_nine_threshold_is_supported_as_comparable_future_protocol(self):
        activity = {
            "sport_type": "Run",
            "user_report": "4×9 min tröskel, fortsatt kontrollerat.",
        }
        detail = {
            "icu_intervals": [
                interval(540, 2200, 151),
                interval(541, 2210, 153),
                interval(539, 2220, 154),
                interval(542, 2230, 156),
            ]
        }
        detected = infer_threshold_protocol(activity, detail)
        self.assertEqual(detected["protocol_key"], "run_threshold:4x9")
        self.assertEqual(len(detected["work_rows"]), 4)

    def test_nonmatching_work_structure_is_not_invented(self):
        activity = {"sport_type": "Run", "user_report": ""}
        detail = {
            "icu_intervals": [
                interval(240, 1000, 145),
                interval(240, 1002, 147),
                interval(240, 1005, 149),
            ]
        }
        self.assertIsNone(infer_threshold_protocol(activity, detail))

    def test_strava_laps_are_used_when_intervals_activity_is_not_available(self):
        state = {
            "activities": [
                {
                    "id": 11,
                    "sport_type": "Run",
                    "start_date_local": "2026-09-01T18:00:00",
                    "user_report": "3×8 min tröskel.",
                    "laps": [
                        {"lap_index": 1, "moving_time_s": 900, "distance_m": 3000},
                        {"lap_index": 2, "moving_time_s": 480, "distance_m": 2000, "average_heartrate": 150},
                        {"lap_index": 3, "moving_time_s": 90, "distance_m": 250},
                        {"lap_index": 4, "moving_time_s": 481, "distance_m": 2010, "average_heartrate": 152},
                        {"lap_index": 5, "moving_time_s": 90, "distance_m": 250},
                        {"lap_index": 6, "moving_time_s": 479, "distance_m": 2020, "average_heartrate": 154},
                        {"lap_index": 7, "moving_time_s": 600, "distance_m": 1800},
                    ],
                }
            ]
        }
        history = {"schema_version": 1, "entries": []}
        updated, skipped = sync(
            state,
            history,
            [],
            lambda _: self.fail("Intervals detail should not be called"),
            date(2026, 8, 1),
        )
        self.assertEqual((updated, skipped), (1, 0))
        entry = history["entries"][0]
        self.assertEqual(entry["source"], "Strava laps")
        self.assertEqual(entry["protocol_key"], "run_threshold:3x8")
        self.assertEqual(len(entry["work_intervals"]), 3)

    def test_same_protocol_comparison_keeps_raw_deltas(self):
        entries = [
            {
                "activity_id": 1,
                "activity_date": "2026-08-20",
                "protocol_key": "run_threshold:3x8",
                "summary": {
                    "mean_pace_s_per_km": 250.0,
                    "mean_heartrate": 151.0,
                    "mean_watts": 300.0,
                    "total_work_s": 1440.0,
                },
            },
            {
                "activity_id": 2,
                "activity_date": "2026-08-25",
                "protocol_key": "run_threshold:3x8",
                "summary": {
                    "mean_pace_s_per_km": 247.0,
                    "mean_heartrate": 153.0,
                    "mean_watts": 303.0,
                    "total_work_s": 1440.0,
                },
            },
        ]
        add_comparisons(entries)
        comparison = entries[1]["comparison"]
        self.assertEqual(comparison["mean_pace_delta_s_per_km"], -3.0)
        self.assertEqual(comparison["mean_hr_delta"], 2.0)
        self.assertEqual(comparison["mean_watts_delta"], 3.0)
        self.assertEqual(comparison["total_work_delta_s"], 0.0)

    def test_diagnostics_are_aggregate_only_and_explain_protocol_detection(self):
        state = {
            "activities": [
                {
                    "id": 12,
                    "sport_type": "Run",
                    "start_date": "2026-09-01T16:00:00Z",
                    "start_date_local": "2026-09-01T18:00:00",
                    "user_report": "3×8 min tröskel.",
                }
            ]
        }
        rows = [
            {
                "id": "i12",
                "type": "Run",
                "source": "GARMIN",
                "start_date": "2026-09-01T16:00:00Z",
            }
        ]
        detail = {
            "icu_intervals": [
                interval(480, 2000, 150),
                interval(480, 2010, 152),
                interval(480, 2020, 154),
            ]
        }
        history = {"schema_version": 1, "entries": []}
        diagnostics = {}
        sync(
            state,
            history,
            rows,
            lambda _: detail,
            date(2026, 8, 1),
            diagnostics=diagnostics,
        )
        self.assertEqual(diagnostics["candidate_runs"], 1)
        self.assertEqual(diagnostics["intervals_activity_matched"], 1)
        self.assertEqual(diagnostics["detail_with_icu_intervals"], 1)
        self.assertEqual(diagnostics["detected_from_intervals"], 1)
        self.assertEqual(diagnostics["interval_types"]["WORK"], 3)
        self.assertNotIn("activity_id", diagnostics)
        self.assertNotIn("heartrate", str(diagnostics).lower())

    def test_sync_builds_fingerprint_without_raw_streams(self):
        state = {
            "activities": [
                {
                    "id": 10,
                    "sport_type": "Run",
                    "start_date_local": "2026-08-25T19:34:18Z",
                    "user_report": "3×8 min tröskel.",
                }
            ]
        }
        history = {"schema_version": 1, "entries": []}
        rows = [
            {
                "id": "i10",
                "type": "Run",
                "source": "GARMIN",
                "start_date_local": "2026-08-25T19:34:18",
            }
        ]
        detail = {
            "icu_intervals": [
                interval(480, 2000, 150, 300),
                interval(480, 2010, 152, 302),
                interval(480, 2020, 154, 304),
            ],
            "streams": {"heartrate": [1, 2, 3]},
        }

        updated, skipped = sync(
            state,
            history,
            rows,
            lambda _: detail,
            date(2026, 8, 1),
        )
        self.assertEqual(updated, 1)
        self.assertEqual(skipped, 0)
        entry = history["entries"][0]
        self.assertEqual(entry["protocol_key"], "run_threshold:3x8")
        self.assertEqual(len(entry["work_intervals"]), 3)
        self.assertNotIn("streams", entry)
        self.assertIsNotNone(entry["summary"]["mean_pace_s_per_km"])


if __name__ == "__main__":
    unittest.main()
