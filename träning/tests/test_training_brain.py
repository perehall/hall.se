#!/usr/bin/env python3
import json
import sys
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_training_brain_ui import SECTION_START, apply_ui, decorate_focus_card, render_section  # noqa: E402
from strategy_contracts import StrategyContractError, validate_training_strategy  # noqa: E402
from training_brain import resolve_mesocycle, resolve_next_decision, resolve_today  # noqa: E402


class TrainingBrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.strategy = json.loads((ROOT / "data" / "training_strategy.json").read_text(encoding="utf-8"))
        cls.plan = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))

    def test_current_strategy_contract_is_valid(self):
        self.assertTrue(validate_training_strategy(self.strategy))

    def test_unknown_protected_stimulus_fails_closed(self):
        strategy = deepcopy(self.strategy)
        strategy["current_mesocycle"]["protected_stimuli"].append("invented_stimulus")
        with self.assertRaises(StrategyContractError):
            validate_training_strategy(strategy)

    def test_long_term_goal_is_primary_contract(self):
        hierarchy = self.strategy["planning_hierarchy"]
        self.assertEqual(
            hierarchy["order"],
            ["north_star", "mesocycle", "microcycle", "near_term", "session"],
        )
        self.assertTrue(self.strategy["decision_policy"]["long_term_goal_is_primary"])
        self.assertTrue(
            self.strategy["decision_policy"]["near_term_changes_must_serve_long_term_direction"]
        )
        self.assertIn("Kalenderveckan är ett presentations- och navigeringslager", hierarchy["calendar_role"])
        self.assertEqual(self.strategy["current_mesocycle"]["microcycle_structure"]["length_days"], 7)
        self.assertIn("microcycle_template", self.strategy["current_mesocycle"])
        self.assertNotIn("weekly_template", self.strategy["current_mesocycle"])

        broken = deepcopy(self.strategy)
        broken["decision_policy"]["long_term_goal_is_primary"] = False
        with self.assertRaises(StrategyContractError):
            validate_training_strategy(broken)

    def test_today_uses_matching_actual_activity_as_completed(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-26",
                    "status": "planned",
                    "session": "Swimrun · klubbpass",
                    "sport": "swimrun",
                    "priority_role": "flex",
                    "stimuli": ["swim_aerobic"],
                }
            ]
        }
        activities = [
            {
                "id": 1,
                "sport_type": "Swimrun",
                "display_label": "Swimrun · test",
                "start_date_local": "2026-08-26T07:00:00",
            }
        ]
        brief = resolve_today(plan, activities, self.strategy, date(2026, 8, 26))
        self.assertTrue(brief["fulfilled"])
        self.assertEqual(brief["status"], "GENOMFÖRT")
        self.assertIn("Swimrun", brief["why"])
        self.assertIn("Sim aerob kapacitet", brief["stimuli"])

    def test_explicit_next_decision_wins_inside_72_hour_horizon(self):
        decision = resolve_next_decision(self.plan, [], self.strategy, date(2026, 8, 26))
        self.assertEqual(decision["date"], "2026-08-28")
        self.assertIn("Backdosen", decision["note"])

    def test_current_mesocycle_reports_microcycle_one(self):
        mesocycle = resolve_mesocycle(self.strategy, date(2026, 8, 26))
        self.assertEqual(mesocycle["state"], "mikrocykel 1 av 4")
        self.assertEqual(mesocycle["evaluation_date"], "2026-09-21")
        self.assertIn("Kontrollerad löptröskel", mesocycle["protected_stimuli"])

    def test_primary_ui_contains_only_today_and_next_decision(self):
        section = render_section(self.plan, {"activities": []}, self.strategy, date(2026, 8, 26))
        self.assertIn("Idag ·", section)
        self.assertIn("Nästa beslut", section)
        self.assertNotIn("Aktuell mesocykel", section)
        self.assertNotIn("Prioritering just nu", section)
        self.assertNotIn("brain-tags", section)

    def test_mesocycle_context_moves_into_week_focus(self):
        page = '<div class="hero week-focus-card"><h2>Veckofokus</h2><details class="week-focus-details"><summary>Planidé</summary><p>Veckoplan.</p></details></div>'
        mesocycle = resolve_mesocycle(self.strategy, date(2026, 8, 26))
        rendered = decorate_focus_card(page, mesocycle)
        self.assertIn('class="week-focus-mesocycle-meta"', rendered)
        self.assertIn("mikrocykel 1 av 4", rendered)
        self.assertIn("utvärdering 21/9", rendered)
        self.assertIn("Mesocykelhypotes:", rendered)

    def test_ui_insertion_is_idempotent(self):
        page = "<html><style></style><body><section class=\"dashboard\"></section></body></html>"
        once = apply_ui(page, f"{SECTION_START}<section>brain</section><!-- training-brain-v1:end -->")
        twice = apply_ui(once, f"{SECTION_START}<section>brain2</section><!-- training-brain-v1:end -->")
        self.assertEqual(twice.count(SECTION_START), 1)
        self.assertEqual(twice.count("/* training-brain-v2 */"), 1)
        self.assertIn("brain2", twice)
        self.assertNotIn(">brain<", twice)


if __name__ == "__main__":
    unittest.main()
