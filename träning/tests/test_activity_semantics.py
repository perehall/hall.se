#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_activity_semantics import apply_semantics, auto_enduro_candidate  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
