#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_coach_language import normalize_state  # noqa: E402


class NormalizeCoachLanguageTests(unittest.TestCase):
    def test_user_reported_hill_structure_overrides_conflicting_lap_interpretation(self):
        coach = {
            "analyses": [
                {
                    "activity_id": 42,
                    "assessment": {
                        "summary": "Genomfört backkvalitetspass motsvarar 2×6×150; stabilt utan försämring i lapparna.",
                        "load_interpretation": "Lapparna såg jämna ut.",
                        "interpretations": ["Ingen tydlig försämring mellan lapparna."],
                        "unknowns": [],
                    },
                    "plan_action": {
                        "reason": "Behåll planen.",
                        "recommendation": "Fortsätt enligt planen.",
                    },
                }
            ]
        }
        activities = {
            "activities": [
                {
                    "id": 42,
                    "user_report": "3 × 6 backintervaller (18 backar totalt).",
                }
            ]
        }

        changed = normalize_state(coach, activities)

        self.assertEqual(changed, 1)
        summary = coach["analyses"][0]["assessment"]["summary"]
        self.assertIn("3 × 6 backintervaller", summary)
        self.assertNotIn("2×6×150", summary)
        self.assertNotIn("lapparna", str(coach).lower())
        self.assertIn("intervallerna", str(coach).lower())


if __name__ == "__main__":
    unittest.main()
