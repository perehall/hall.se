#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UserReportPersistenceTests(unittest.TestCase):
    def test_sep8_activity_report_is_persisted(self):
        document = json.loads((ROOT / "data" / "activity_overrides.json").read_text(encoding="utf-8"))
        override = document["overrides"]["20092166843"]
        self.assertEqual(override["display_label"], "Löpband · 4 × 8 min Tempo")
        self.assertIn("4 × 8 min", override["user_report"])
        self.assertIn("162 bpm", override["user_report"])

    def test_sep8_last_prescription_is_not_allowed_to_revert_to_3x10(self):
        document = json.loads((ROOT / "data" / "plan_overrides.json").read_text(encoding="utf-8"))
        override = next(item for item in document["overrides"] if item["date"] == "2026-09-08")
        self.assertEqual(override["set"]["session"], "Löpband · 4 × 8 min Tempo (Garmin)")
        self.assertNotIn("3 × 10", override["set"]["session"])
        self.assertTrue(override["set"]["manual_lock"])


if __name__ == "__main__":
    unittest.main()
