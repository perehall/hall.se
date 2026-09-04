#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_coach_language import assert_no_forbidden_visible_terms, normalize_state  # noqa: E402


class NormalizeCoachLanguageTests(unittest.TestCase):
    def test_user_reported_hill_structure_overrides_conflicting_lap_interpretation(self):
        coach = {
            "analyses": [
                {
                    "activity_id": 42,
                    "activity_date": "2026-09-04",
                    "assessment": {
                        "summary": "Backintervaller genomförda som rapporterat: 2×6×150 (reducerad plan); stabilt utan försämring i lapparna.",
                        "load_interpretation": "Lapparna såg jämna ut.",
                        "facts": ["18 lappar registrerades som arbetsdelar."],
                        "interpretations": ["Ingen tydlig försämring mellan lapparna."],
                        "unknowns": [],
                    },
                    "plan_action": {
                        "reason": "Fredagens reducerade backdos genomförd; behåll lördagens stödpass.",
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
        plan = {
            "days": [
                {
                    "date": "2026-09-04",
                    "dose_resolution": {"kind": "structured", "value": 12},
                }
            ]
        }

        changed = normalize_state(coach, activities, plan)
        assert_no_forbidden_visible_terms(coach)

        self.assertEqual(changed, 1)
        summary = coach["analyses"][0]["assessment"]["summary"]
        reason = coach["analyses"][0]["plan_action"]["reason"]
        self.assertEqual(
            summary,
            "Genomfört: 3 × 6 backintervaller (18 totalt). Stabilt utan försämring i intervallerna",
        )
        self.assertNotIn("2×6×150", summary)
        self.assertIn("18 totalt", reason)
        self.assertIn("planerade omfattningen före passet (12 arbetsintervaller)", reason)
        self.assertNotIn("reducerade backdos genomförd", reason)
        self.assertNotIn("lapparna", str(coach).lower())
        self.assertNotIn("lappar", str(coach).lower())
        self.assertIn("intervallerna", str(coach).lower())
        self.assertIn("18 intervaller", str(coach).lower())


if __name__ == "__main__":
    unittest.main()
