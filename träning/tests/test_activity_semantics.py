#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_activity_semantics import (  # noqa: E402
    apply_semantics,
    auto_enduro_candidate,
    invalidate_coach_analyses,
)


class ActivitySemanticsTests(unittest.TestCase):
    def test_explicit_enduro_name_reclassifies_raw_mountain_bike(self):
        state = {
            "activities": [
                {
                    "id": 19882521682,
                    "name": "Enduro på kvällen",
                    "sport_type": "MountainBikeRide",
                    "start_date_local": "2026-08-24T18:05:29Z",
                }
            ]
        }
        override_count, auto_count, _ = apply_semantics(state, {"schema_version": 1, "overrides": {}})
        activity = state["activities"][0]
        self.assertEqual(override_count, 0)
        self.assertEqual(auto_count, 1)
        self.assertEqual(activity["source_sport_type"], "MountainBikeRide")
        self.assertEqual(activity["sport_type"], "Enduro")
        self.assertEqual(activity["display_label"], "Enduro")
        self.assertEqual(activity["sport_normalization"]["rule"], "mountainbike-explicit-enduro-name-v1")
        self.assertEqual(state["activity_semantics"]["changed_ids"], ["19882521682"])

    def test_motocross_name_is_equivalent_signal(self):
        activity = {"name": "Motocross kväll", "sport_type": "MountainBikeRide"}
        self.assertTrue(auto_enduro_candidate(activity))

    def test_mtb_enduro_wording_is_ambiguous_and_not_reclassified(self):
        state = {
            "activities": [
                {
                    "id": 1,
                    "name": "MTB Enduro träning",
                    "sport_type": "MountainBikeRide",
                    "start_date_local": "2026-08-24T18:00:00Z",
                }
            ]
        }
        _, auto_count, _ = apply_semantics(state, {"schema_version": 1, "overrides": {}})
        self.assertEqual(auto_count, 0)
        self.assertEqual(state["activities"][0]["sport_type"], "MountainBikeRide")
        self.assertEqual(state["activity_semantics"]["changed_ids"], [])

    def test_plain_mountain_bike_name_stays_mtb(self):
        activity = {"name": "Stigrull på kvällen", "sport_type": "MountainBikeRide"}
        self.assertFalse(auto_enduro_candidate(activity))

    def test_explicit_override_wins_over_auto_rule(self):
        state = {
            "activities": [
                {
                    "id": 7,
                    "name": "Enduro på kvällen",
                    "sport_type": "MountainBikeRide",
                    "start_date_local": "2026-08-24T18:00:00Z",
                }
            ]
        }
        config = {
            "schema_version": 1,
            "overrides": {
                "7": {
                    "sport": "MountainBikeRide",
                    "classification": "training",
                    "display_label": "MTB/XC",
                    "source_sport_type": "MountainBikeRide",
                }
            },
        }
        override_count, auto_count, _ = apply_semantics(state, config)
        self.assertEqual((override_count, auto_count), (1, 0))
        self.assertEqual(state["activities"][0]["sport_type"], "MountainBikeRide")
        self.assertEqual(state["activities"][0]["display_label"], "MTB/XC")

    def test_swimrun_override_is_idempotent_and_marks_change_only_once(self):
        state = {
            "activities": [
                {
                    "id": 11,
                    "name": "SLK Swimrun Jogersö Extreme",
                    "sport_type": "TrailRun",
                    "start_date_local": "2026-08-26T18:00:00Z",
                }
            ]
        }
        config = {
            "schema_version": 1,
            "overrides": {
                "11": {
                    "sport": "Swimrun",
                    "classification": "training",
                    "display_label": "Swimrun · Jogersö Extreme",
                    "source_sport_type": "TrailRun",
                    "user_report": "Pulsbortfall under delar av passet.",
                }
            },
        }
        apply_semantics(state, config)
        self.assertEqual(state["activity_semantics"]["changed_ids"], ["11"])
        self.assertEqual(state["activities"][0]["sport_type"], "Swimrun")

        apply_semantics(state, config)
        self.assertEqual(state["activity_semantics"]["changed_ids"], [])
        self.assertEqual(state["activities"][0]["source_sport_type"], "TrailRun")

    def test_semantic_change_invalidates_only_matching_coach_analysis(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "coach.json"
            path.write_text(
                json.dumps(
                    {
                        "last_trigger_hash": "stale",
                        "analyses": [
                            {"activity_id": 11, "assessment": {}},
                            {"activity_id": 12, "assessment": {}},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            removed = invalidate_coach_analyses(path, {"11"})
            coach = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(removed, 1)
            self.assertEqual([row["activity_id"] for row in coach["analyses"]], [12])
            self.assertIsNone(coach["last_trigger_hash"])


if __name__ == "__main__":
    unittest.main()
