#!/usr/bin/env python3
"""Canonical mesocycle-to-V1 strategy materialization tests."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_strategy_materializer import (  # noqa: E402
    StrategyMaterializationError,
    materialize_strategy_document,
)
from training_core.application.planning_strategy_projection import (  # noqa: E402
    compile_strategy_revision,
)


STRATEGY = ROOT / "data" / "training_strategy.json"
CATALOG = ROOT / "data" / "workout_catalog.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class StrategyMaterializerTests(unittest.TestCase):
    def materialize(self, start, end):
        return materialize_strategy_document(
            canonical_strategy=load(STRATEGY),
            canonical_catalog=load(CATALOG),
            affected_from=date.fromisoformat(start),
            affected_until=date.fromisoformat(end),
        )

    def test_current_microcycle_blueprint_compiles_to_explicit_strategy(self):
        document = self.materialize("2026-09-28", "2026-10-04")
        strategy = compile_strategy_revision(document)
        obligations = {
            item.capability: item
            for item in strategy.obligations
        }
        self.assertEqual(
            set(obligations),
            {
                "run_threshold",
                "swim_aerobic",
                "swim_technique",
                "strength_core",
                "strength_unilateral",
            },
        )
        self.assertEqual(obligations["run_threshold"].min_exposures, 1)
        self.assertEqual(obligations["run_threshold"].max_exposures, 1)
        self.assertEqual(obligations["swim_aerobic"].min_exposures, 2)
        self.assertEqual(obligations["swim_technique"].min_exposures, 2)
        self.assertEqual(obligations["strength_core"].min_exposures, 1)
        self.assertEqual(obligations["strength_unilateral"].min_exposures, 1)

    def test_supporting_candidate_does_not_become_mandatory_obligation(self):
        strategy = compile_strategy_revision(
            self.materialize("2026-09-28", "2026-10-04")
        )
        capabilities = {item.capability for item in strategy.obligations}
        self.assertNotIn("run_hill_quality", capabilities)

    def test_optional_recipe_stimulus_does_not_become_protected_obligation(self):
        strategy = compile_strategy_revision(
            self.materialize("2026-09-28", "2026-10-04")
        )
        capabilities = {item.capability for item in strategy.obligations}
        self.assertNotIn("plyometric", capabilities)

    def test_blueprint_counts_sessions_not_capability_obligations_for_hard_cap(self):
        strategy = compile_strategy_revision(
            self.materialize("2026-09-28", "2026-10-04")
        )
        bound = strategy.load_envelope.bounds[0]
        self.assertEqual(bound.scope, "planned")
        self.assertEqual(bound.subject, "mutable_training")
        self.assertEqual(bound.metric, "session_count")
        self.assertEqual(bound.unit, "sessions")
        self.assertEqual(bound.window_days, 7)
        self.assertEqual(bound.max_value, 4)

    def test_next_microcycle_uses_its_own_blueprint_recipe_families(self):
        strategy = compile_strategy_revision(
            self.materialize("2026-10-05", "2026-10-11")
        )
        obligations = {
            item.capability: item
            for item in strategy.obligations
        }
        self.assertEqual(
            obligations["run_threshold"].recipe_family,
            ("run_threshold_short_reps",),
        )
        self.assertEqual(
            set(obligations["swim_aerobic"].recipe_family),
            {"swim_aerobic_endurance", "swim_aerobic_skills"},
        )

    def test_non_blueprint_window_blocks_instead_of_interpolating(self):
        with self.assertRaises(StrategyMaterializationError) as raised:
            self.materialize("2026-10-06", "2026-10-12")
        self.assertEqual(
            raised.exception.code,
            "V1_BLUEPRINT_WINDOW_NOT_UNIQUE",
        )

    def test_materializer_has_no_calendar_or_legacy_planner_dependency(self):
        import training_core.application.planning_strategy_materializer as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("forward_horizon", source)
        self.assertNotIn("day_index", source)
        self.assertNotIn("plan.json", source)
        self.assertNotIn("upcoming_week", source)


if __name__ == "__main__":
    unittest.main()
