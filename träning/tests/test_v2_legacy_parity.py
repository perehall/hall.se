#!/usr/bin/env python3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from v2_legacy_parity import compare_cutover_contract, legacy_semantic_contract


class LegacyParityTests(unittest.TestCase):
    def _legacy(self, body: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.html"
            path.write_text(body, encoding="utf-8")
            return legacy_semantic_contract(path, today=date(2026, 9, 27))

    def test_extracts_today_and_completed_multi_activity_truth(self):
        legacy = self._legacy(
            '<section class="top-today"><div class="top-today-title">'
            '<svg></svg><span>Löpning · lugn distans</span></div></section>'
            '<div class="day completed" id="dag-2026-09-26">'
            '<div class="completed-day-summary"><div class="completed-day-title">'
            '<span>Enduro</span><span class="completed-day-title-sep">+</span>'
            '<span>Simning</span></div></div></div>'
            '<div class="day" id="dag-2026-09-27"><div>Plan</div>'
            '<div class="next-weather" data-weather-date="2026-09-27" '
            'data-weather-scope="day"><strong>Väder · Oxelösund</strong> · '
            'Klart · 12,0–15,4 °C · nederbördsrisk max 0 % · vind max 4,9 m/s'
            '</div></div>'
        )
        self.assertEqual(legacy["today"]["title"], "Löpning · lugn distans")
        self.assertEqual(
            legacy["week"]["days"][0]["actual_labels"], ["Enduro", "Simning"]
        )
        self.assertEqual(
            legacy["week"]["days"][1]["weather"],
            "Väder · Oxelösund · Klart · 12,0–15,4 °C · "
            "nederbördsrisk max 0 % · vind max 4,9 m/s",
        )

    def test_cutover_contract_accepts_legacy_split_dose_but_not_wrong_activity(self):
        legacy = {
            "today": {"date": "2026-09-27", "title": "Löpning · lugn distans"},
            "week": {
                "days": [
                    {
                        "date": "2026-09-26",
                        "completed": True,
                        "actual_labels": ["Enduro", "Simning"],
                        "weather": "",
                    },
                    {
                        "date": "2026-09-27",
                        "completed": False,
                        "actual_labels": [],
                        "weather": "Väder · Oxelösund · Klart · 12,0 °C",
                    }
                ]
            },
        }
        v2 = {
            "today": {
                "date": "2026-09-27",
                "title": "Löpning · lugn distans · 60 min",
            },
            "week": {
                "days": [
                    {
                        "date": "2026-09-26",
                        "state": "completed",
                        "actual_labels": ["Enduro", "Simning"],
                        "weather": "",
                    },
                    {
                        "date": "2026-09-27",
                        "state": "fixed",
                        "actual_labels": [],
                        "weather": "Väder · Oxelösund · Klart · 12,0 °C",
                    }
                ]
            },
        }
        self.assertEqual(compare_cutover_contract(legacy, v2), [])
        v2["week"]["days"][0]["actual_labels"] = ["EBikeRide"]
        self.assertTrue(compare_cutover_contract(legacy, v2))
        v2["week"]["days"][0]["actual_labels"] = ["Enduro", "Simning"]
        v2["week"]["days"][1]["weather"] = "Fel väder"
        self.assertTrue(compare_cutover_contract(legacy, v2))


if __name__ == "__main__":
    unittest.main()
