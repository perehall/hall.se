#!/usr/bin/env python3
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_home import LINK_CSS, render_decision_principles, render_hierarchy, render_mesocycle  # noqa: E402


class GoalSystemPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.strategy = json.loads((ROOT / "data" / "training_strategy.json").read_text(encoding="utf-8"))

    def test_goal_hierarchy_matches_actual_planning_layers(self):
        rendered = render_hierarchy(self.strategy)
        for label in ("Målbild", "Mesocykel", "Mikrocykel", "Närtid · 3 dagar", "Pass"):
            self.assertIn(label, rendered)
        self.assertIn('data-goal-hierarchy="true"', rendered)
        self.assertIn("Återkoppling", rendered)
        self.assertIn("Kalenderveckan är ett presentations- och navigeringslager", rendered)
        self.assertNotIn("Faser och periodisering", rendered)
        self.assertNotIn("mountain-phase-point", rendered)

    def test_current_mesocycle_is_derived_from_strategy(self):
        rendered = render_mesocycle(self.strategy, date(2026, 9, 2))
        self.assertIn('data-current-mesocycle="true"', rendered)
        self.assertIn("Löptröskel + backkvalitet", rendered)
        self.assertIn("mikrocykel 2 av 4", rendered)
        self.assertIn("utvärderas 21 sep", rendered)
        self.assertIn("Kontrollerad löptröskel", rendered)
        self.assertIn("Sim aerob kapacitet", rendered)
        self.assertIn("Unilateral benstyrka", rendered)
        self.assertIn("Enduroteknik", rendered)

    def test_decision_rules_reflect_strategy_policy(self):
        rendered = render_decision_principles(self.strategy)
        self.assertIn("Konkret grundplan", rendered)
        self.assertIn("Ändra på faktisk information", rendered)
        self.assertIn("Kontinuitet före maxinnehåll", rendered)
        self.assertIn("Normal variation absorberas", rendered)

    def test_goal_link_uses_same_neutral_visual_language_as_back_link(self):
        self.assertIn("color:#475569", LINK_CSS)
        self.assertIn("background:#fff", LINK_CSS)
        self.assertIn("border:1px solid #e2e8f0", LINK_CSS)
        self.assertNotIn("#5b21b6", LINK_CSS)
        self.assertNotIn("#faf5ff", LINK_CSS)


if __name__ == "__main__":
    unittest.main()
