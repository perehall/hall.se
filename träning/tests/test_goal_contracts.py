#!/usr/bin/env python3
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from goal_contracts import (  # noqa: E402
    GoalContractError,
    planning_goal_hash,
    planning_goal_set,
    validate_goal_portfolio,
)


class GoalPortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.goal = json.loads((ROOT / "data" / "goal.json").read_text(encoding="utf-8"))

    def test_goal_portfolio_keeps_enduring_and_performance_goals_separate(self):
        self.assertTrue(validate_goal_portfolio(self.goal))
        rows = planning_goal_set(self.goal)
        by_id = {row["id"]: row for row in rows}

        enduring = by_id["allround-athlete"]
        self.assertEqual(enduring["type"], "development")
        self.assertEqual(enduring["role"], "enduring")
        self.assertEqual(enduring["horizon"], "ongoing")
        self.assertEqual(
            set(enduring["disciplines"]),
            {"run", "mtb", "swim", "strength"},
        )

        race = by_id["otillo-aland-2027-top10"]
        self.assertEqual(race["type"], "performance")
        self.assertEqual(race["priority_class"], "A")
        self.assertEqual(race["event_date"], "2027-08-14")

    def test_enduring_goal_change_invalidates_planning_hash(self):
        altered = deepcopy(self.goal)
        altered["development_goals"][0]["objective"] += " Justerad."
        self.assertNotEqual(planning_goal_hash(self.goal), planning_goal_hash(altered))

    def test_portfolio_requires_an_enduring_development_goal(self):
        broken = deepcopy(self.goal)
        broken["development_goals"] = []
        with self.assertRaises(GoalContractError):
            validate_goal_portfolio(broken)

    def test_goal_ids_are_unique_across_goal_types(self):
        broken = deepcopy(self.goal)
        broken["performance_goals"][0]["id"] = "allround-athlete"
        with self.assertRaises(GoalContractError):
            validate_goal_portfolio(broken)


if __name__ == "__main__":
    unittest.main()
