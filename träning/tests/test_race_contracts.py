#!/usr/bin/env python3
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from race_contracts import (  # noqa: E402
    RaceContractError,
    build_competition_context,
    validate_race_goal,
)


class RaceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.goal = json.loads((ROOT / "data" / "goal.json").read_text(encoding="utf-8"))
        cls.policy = json.loads((ROOT / "data" / "planning_policy.json").read_text(encoding="utf-8"))

    def test_aland_profile_matches_verified_source_contract(self):
        self.assertTrue(validate_race_goal(self.goal))
        item = self.goal["performance_goals"][0]
        self.assertEqual(item["event_date"], "2027-08-14")
        self.assertIsNone(item["target_category"])
        profile = item["race_profile"]
        self.assertEqual(profile["total_distance_m"], 46540)
        self.assertEqual(profile["run_distance_m"], 36570)
        self.assertEqual(profile["swim_distance_m"], 9960)
        self.assertEqual(profile["elevation_gain_m"], 391)
        self.assertEqual(profile["avg_air_temp_c"], 21)
        self.assertEqual(profile["avg_water_temp_c"], 17)
        self.assertEqual(profile["source"]["publisher"], "ÖTILLÖ Swimrun")
        self.assertEqual(profile["source"]["verified_on"], "2026-09-21")

    def test_competition_context_counts_down_from_planning_date(self):
        context = build_competition_context(
            self.goal,
            date(2026, 9, 21),
            self.policy["event_horizon_policy"],
        )
        self.assertTrue(context["available"])
        self.assertEqual(context["days_to_event"], 327)
        self.assertEqual(context["weeks_to_event"], 46.7)
        self.assertEqual(context["horizon_stage"], "foundation")
        self.assertEqual(context["derived"]["published_component_delta_m"], 10)
        self.assertEqual(context["race_profile"]["swim_distance_m"], 9960)
        self.assertEqual(context["category_status"], "unspecified")

    def test_review_windows_are_not_load_prescriptions(self):
        policy = self.policy["event_horizon_policy"]
        self.assertIn("inte fasta träningsrecept", policy["principle"])
        self.assertTrue(
            any("får inte ensam" in rule for rule in policy["rules"])
        )

    def test_missing_event_date_fails_closed(self):
        broken = json.loads(json.dumps(self.goal))
        broken["performance_goals"][0].pop("event_date")
        with self.assertRaises(RaceContractError):
            validate_race_goal(broken)

    def test_large_distance_inconsistency_fails_closed(self):
        broken = json.loads(json.dumps(self.goal))
        broken["performance_goals"][0]["race_profile"]["total_distance_m"] = 50000
        with self.assertRaises(RaceContractError):
            validate_race_goal(broken)


if __name__ == "__main__":
    unittest.main()
