#!/usr/bin/env python3
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from rollover_week import build_mesocycle_next_week  # noqa: E402
from strategy_contracts import StrategyContractError, validate_training_strategy  # noqa: E402


class DevelopmentProgressionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.strategy = json.loads((ROOT / "data" / "training_strategy.json").read_text(encoding="utf-8"))
        cls.plan = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))

    def test_current_strategy_contract_is_valid(self):
        self.assertTrue(validate_training_strategy(self.strategy))

    def test_hill_quality_uses_reported_3x6_floor_and_progresses(self):
        hill = next(item for item in self.strategy["current_mesocycle"]["microcycle_template"] if item["slot"] == "run_hill_quality")
        self.assertEqual(hill["development_progression"]["demonstrated_floor_option_id"], "run-hill-3x6x150")
        self.assertEqual(hill["baseline_option_id"], "run-hill-3x7x150")
        self.assertEqual(hill["progression_target_option_id"], "run-hill-3x8x150")
        floor = next(option for option in hill["dose_options"] if option["id"] == "run-hill-3x6x150")
        self.assertEqual(floor["value"], 18)
        self.assertIn("användarrapport", floor["intent"].lower())
        self.assertIn("inte för att påstå exakt längd", floor["intent"].lower())

    def test_stale_hill_baseline_below_demonstrated_floor_is_rejected(self):
        broken = deepcopy(self.strategy)
        hill = next(item for item in broken["current_mesocycle"]["microcycle_template"] if item["slot"] == "run_hill_quality")
        hill["baseline_option_id"] = "run-hill-6x150"
        hill["session"] = next(option["session"] for option in hill["dose_options"] if option["id"] == "run-hill-6x150")
        with self.assertRaises(StrategyContractError):
            validate_training_strategy(broken)

    def test_same_dose_cannot_be_disguised_as_progress(self):
        broken = deepcopy(self.strategy)
        hill = next(item for item in broken["current_mesocycle"]["microcycle_template"] if item["slot"] == "run_hill_quality")
        hill["development_progression"]["microcycle_plan"][1]["option_id"] = "run-hill-3x6x150"
        hill["development_progression"]["microcycle_plan"][1]["relation"] = "progress"
        with self.assertRaises(StrategyContractError):
            validate_training_strategy(broken)

    def test_existing_today_reduction_preserves_historical_plan_before_pass(self):
        today = next(day for day in self.plan["days"] if day.get("date") == "2026-09-04")
        self.assertEqual(today["baseline_option_id"], "run-hill-2x7x150")
        self.assertEqual(today["dose_resolution"]["option_id"], "run-hill-2x6x150")
        self.assertIn("2 × 6 × 150 m", today["session"])
        self.assertIn("2 × 7 × 150 m", today["original_session"])

    def test_next_microcycle_advances_from_reported_18_interval_floor(self):
        future = build_mesocycle_next_week(self.plan, self.strategy)
        threshold = next(day for day in future["days"] if day.get("microcycle_slot") == "run_threshold")
        hill = next(day for day in future["days"] if day.get("microcycle_slot") == "run_hill_quality")
        self.assertEqual(threshold["microcycle_index"], 3)
        self.assertEqual(threshold["baseline_option_id"], "run-threshold-3x10")
        self.assertEqual(hill["baseline_option_id"], "run-hill-3x7x150")
        self.assertEqual(hill["development_step"]["relation"], "progress")
        self.assertGreater(hill["dose_resolution"]["value"], 18)


if __name__ == "__main__":
    unittest.main()
