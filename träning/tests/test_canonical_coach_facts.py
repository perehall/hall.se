#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach_rules import canonical_activity_fact  # noqa: E402
from finalize_canonical_coach_facts import enforce_canonical_facts  # noqa: E402


class CanonicalCoachFactsTests(unittest.TestCase):
    def test_first_fact_is_rebuilt_from_activity_without_touching_interpretive_facts(self):
        activity = {
            "id": 20120769386,
            "sport_type": "MountainBikeRide",
            "display_label": "MTB/XC",
            "distance_m": 17158.0,
            "elapsed_time_s": 5459,
            "average_heartrate": 131.6,
        }
        coach = {
            "analyses": [
                {
                    "activity_id": 20120769386,
                    "assessment": {
                        "facts": [
                            "MTB: humaniserad men inte längre canonical.",
                            "Planstatus: genomfört.",
                        ]
                    },
                }
            ]
        }

        changed = enforce_canonical_facts(coach, {"activities": [activity]})

        self.assertEqual(changed, 1)
        self.assertEqual(
            coach["analyses"][0]["assessment"]["facts"][0],
            canonical_activity_fact(activity),
        )
        self.assertEqual(
            coach["analyses"][0]["assessment"]["facts"][1],
            "Planstatus: genomfört.",
        )

    def test_already_canonical_fact_is_idempotent(self):
        activity = {
            "id": 1,
            "sport_type": "Run",
            "distance_m": 5000.0,
            "elapsed_time_s": 1500,
        }
        fact = canonical_activity_fact(activity)
        coach = {"analyses": [{"activity_id": 1, "assessment": {"facts": [fact]}}]}

        self.assertEqual(enforce_canonical_facts(coach, {"activities": [activity]}), 0)
        self.assertEqual(coach["analyses"][0]["assessment"]["facts"][0], fact)


if __name__ == "__main__":
    unittest.main()
