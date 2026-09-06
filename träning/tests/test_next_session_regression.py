#!/usr/bin/env python3
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach_rules import planning_window  # noqa: E402
from training_brain import resolve_next_decision  # noqa: E402


class NextSessionRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.strategy = json.loads(
            (ROOT / "data" / "training_strategy.json").read_text(encoding="utf-8")
        )

    def test_later_decision_note_never_skips_earlier_planned_session(self):
        active = {
            "days": [
                {
                    "date": "2026-09-06",
                    "label": "Söndag",
                    "status": "planned",
                    "session": "Löpning · lugn distans · 75 min",
                    "sport": "run",
                }
            ]
        }
        upcoming = {
            "days": [
                {
                    "date": "2026-09-07",
                    "label": "Måndag",
                    "status": "planned",
                    "session": "Enduroskola · fast tillfälle",
                    "sport": "enduro",
                    "priority_role": "flex",
                },
                {
                    "date": "2026-09-08",
                    "label": "Tisdag",
                    "status": "preliminary",
                    "session": "Löpning · kontrollerad tröskel · 3 × 10 min / 90 s jogg",
                    "sport": "run",
                    "priority_role": "anchor",
                },
                {
                    "date": "2026-09-09",
                    "label": "Onsdag",
                    "status": "preliminary",
                    "session": "Simning · 3 200 m · aerob/teknik",
                    "sport": "swim",
                    "decision_note": "Senare pass med uttrycklig notering.",
                },
            ]
        }

        decision = resolve_next_decision(
            planning_window(active, upcoming),
            [],
            self.strategy,
            date(2026, 9, 6),
        )

        self.assertEqual(decision["date"], "2026-09-07")
        self.assertEqual(decision["label"], "Måndag")
        self.assertIn("Enduroskola", decision["headline"])
        self.assertNotIn("Senare pass", decision["note"])

    def test_next_session_order_is_independent_of_input_order(self):
        plan = {
            "days": [
                {
                    "date": "2026-09-09",
                    "label": "Onsdag",
                    "status": "conditional",
                    "session": "Simning · 3 200 m",
                    "decision_note": "Explicit senare notering.",
                },
                {
                    "date": "2026-09-07",
                    "label": "Måndag",
                    "status": "planned",
                    "session": "Enduroskola · fast tillfälle",
                },
                {
                    "date": "2026-09-08",
                    "label": "Tisdag",
                    "status": "preliminary",
                    "session": "Löpning · tröskel",
                    "priority_role": "anchor",
                },
            ]
        }

        decision = resolve_next_decision(plan, [], self.strategy, date(2026, 9, 6))
        self.assertEqual(decision["date"], "2026-09-07")
        self.assertIn("Enduroskola", decision["headline"])


if __name__ == "__main__":
    unittest.main()
