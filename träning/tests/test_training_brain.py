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
from training_brain import resolve_block, resolve_next_decision, resolve_today  # noqa: E402


class TrainingBrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.strategy = json.loads((ROOT / "data" / "training_strategy.json").read_text(encoding="utf-8"))
        cls.plan = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))

    def test_current_strategy_contract_is_valid(self):
        self.assertTrue(validate_training_strategy(self.strategy))

    def test_unknown_protected_stimulus_fails_closed(self):
        strategy = deepcopy(self.strategy)
        strategy["current_block"]["protected_stimuli"].append("invented_stimulus")
        with self.assertRaises(StrategyContractError):
            validate_training_strategy(strategy)

    def test_today_uses_matching_actual_activity_as_completed(self):
        activities = [
            {
                "id": 1,
                "sport_type": "Swim",
                "display_label": "Simning",
                "start_date_local": "2026-08-26T07:00:00",
            }
        ]
        brief = resolve_today(self.plan, activities, self.strategy, date(2026, 8, 26))
        self.assertTrue(brief["fulfilled"])
        self.assertEqual(brief["status"], "GENOMFÖRT")
        self.assertIn("Simning", brief["why"])
        self.assertIn("Sim aerob kapacitet", brief["stimuli"])

    def test_explicit_next_decision_wins_inside_72_hour_horizon(self):
        decision = resolve_next_decision(self.plan, [], self.strategy, date(2026, 8, 26))
        self.assertEqual(decision["date"], "2026-08-28")
        self.assertIn("Backdosen", decision["note"])

    def test_current_block_reports_week_one(self):
        block = resolve_block(self.strategy, date(2026, 8, 26))
        self.assertEqual(block["state"], "vecka 1 av 4")
        self.assertEqual(block["evaluation_date"], "2026-09-21")
        self.assertIn("Kontrollerad löptröskel", block["protected_stimuli"])

    def test_primary_ui_contains_only_today_and_next_decision(self):
        section = render_section(self.plan, {"activities": []}, self.strategy, date(2026, 8, 26))
        self.assertIn("Idag ·", section)
        self.assertIn("Nästa beslut", section)
        self.assertNotIn("Aktuellt block", section)
        self.assertNotIn("Prioritering just nu", section)
        self.assertNotIn("brain-tags", section)

    def test_block_context_moves_into_week_focus(self):
        page = '<div class="hero week-focus-card"><h2>Veckofokus</h2><details class="week-focus-details"><summary>Planidé</summary><p>Veckoplan.</p></details></div>'
        block = resolve_block(self.strategy, date(2026, 8, 26))
        rendered = decorate_focus_card(page, block)
        self.assertIn('class="week-focus-block-meta"', rendered)
        self.assertIn("vecka 1 av 4", rendered)
        self.assertIn("utvärdering 21/9", rendered)
        self.assertIn("Blockhypotes:", rendered)

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
