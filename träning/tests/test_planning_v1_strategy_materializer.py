#!/usr/bin/env python3
"""Canonical mesocycle-to-V1 strategy materialization tests."""

from __future__ import annotations

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


def canonical_catalog():
    return {
        "recipes": {
            "run_threshold_short_reps": {
                "sport": "run",
                "stimuli": ["run_threshold"],
            },
            "run_threshold": {
                "sport": "run",
                "stimuli": ["run_threshold"],
            },
            "swim_aerobic_endurance": {
                "sport": "swim",
                "stimuli": ["swim_aerobic", "swim_technique"],
            },
            "swim_aerobic_skills": {
                "sport": "swim",
                "stimuli": ["swim_aerobic", "swim_technique"],
            },
            "strength_core": {
                "sport": "strength",
                "stimuli": ["strength_unilateral", "strength_core"],
                "optional_stimuli": ["plyometric"],
            },
            "run_easy_trail": {
                "sport": "run",
                "stimuli": ["run_easy_distance"],
            },
        }
    }


def canonical_strategy():
    return {
        "goal_contract": {"goal_hash": "goal-test"},
        "current_mesocycle": {
            "id": "meso-test",
            "start_date": "2026-10-05",
            "end_date": "2026-10-25",
            "contract": {
                "primary": [
                    "run_threshold",
                    "swim_aerobic",
                    "swim_technique",
                ],
                "protected_capacity": [
                    "strength_unilateral",
                    "strength_core",
                    "plyometric",
                ],
                "secondary": ["run_easy_distance"],
            },
            "development_blueprint": [
                {
                    "week_start": "2026-10-05",
                    "week_end": "2026-10-11",
                    "planned_variants": [
                        {
                            "role": "primary",
                            "capability": "run_threshold",
                            "recipe_key": "run_threshold_short_reps",
                        },
                        {
                            "role": "primary",
                            "capability": "swim_aerobic",
                            "recipe_key": "swim_aerobic_endurance",
                        },
                        {
                            "role": "primary_companion",
                            "capability": "swim_aerobic",
                            "recipe_key": "swim_aerobic_skills",
                        },
                    ],
                    "protected_variants": [
                        {
                            "role": "protected",
                            "capability": "strength_core",
                            "recipe_key": "strength_core",
                        }
                    ],
                    "supporting_candidates": [
                        {
                            "role": "supporting_candidate",
                            "capability": "run_easy_distance",
                            "recipe_key": "run_easy_trail",
                        }
                    ],
                },
                {
                    "week_start": "2026-10-12",
                    "week_end": "2026-10-18",
                    "planned_variants": [
                        {
                            "role": "primary",
                            "capability": "run_threshold",
                            "recipe_key": "run_threshold",
                        },
                        {
                            "role": "primary",
                            "capability": "swim_aerobic",
                            "recipe_key": "swim_aerobic_skills",
                        },
                        {
                            "role": "primary_companion",
                            "capability": "swim_aerobic",
                            "recipe_key": "swim_aerobic_endurance",
                        },
                    ],
                    "protected_variants": [
                        {
                            "role": "protected",
                            "capability": "strength_core",
                            "recipe_key": "strength_core",
                        }
                    ],
                    "supporting_candidates": [],
                },
            ],
        },
    }


class StrategyMaterializerTests(unittest.TestCase):
    def materialize(self, start, end):
        return materialize_strategy_document(
            canonical_strategy=canonical_strategy(),
            canonical_catalog=canonical_catalog(),
            affected_from=date.fromisoformat(start),
            affected_until=date.fromisoformat(end),
        )

    def test_blueprint_compiles_to_explicit_strategy(self):
        strategy = compile_strategy_revision(
            self.materialize("2026-10-05", "2026-10-11")
        )
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
                "run_easy_distance",
            },
        )
        self.assertEqual(obligations["run_threshold"].min_exposures, 1)
        self.assertEqual(obligations["run_threshold"].max_exposures, 1)
        self.assertEqual(obligations["swim_aerobic"].min_exposures, 2)
        self.assertEqual(obligations["swim_technique"].min_exposures, 2)
        self.assertEqual(obligations["strength_core"].min_exposures, 1)
        self.assertEqual(obligations["strength_unilateral"].min_exposures, 1)
        self.assertEqual(obligations["run_easy_distance"].min_exposures, 0)
        self.assertEqual(obligations["run_easy_distance"].target_exposures, 1)
        self.assertEqual(obligations["run_easy_distance"].max_exposures, 1)
        self.assertEqual(obligations["run_easy_distance"].role, "supporting")

    def test_supporting_candidate_is_soft_target_not_mandatory_obligation(self):
        strategy = compile_strategy_revision(
            self.materialize("2026-10-05", "2026-10-11")
        )
        obligation = next(
            item for item in strategy.obligations
            if item.capability == "run_easy_distance"
        )
        self.assertEqual(obligation.min_exposures, 0)
        self.assertEqual(obligation.target_exposures, 1)

    def test_optional_recipe_stimulus_does_not_become_protected_obligation(self):
        strategy = compile_strategy_revision(
            self.materialize("2026-10-05", "2026-10-11")
        )
        capabilities = {item.capability for item in strategy.obligations}
        self.assertNotIn("plyometric", capabilities)

    def test_blueprint_counts_sessions_not_capability_obligations_for_hard_cap(self):
        strategy = compile_strategy_revision(
            self.materialize("2026-10-05", "2026-10-11")
        )
        bound = strategy.load_envelope.bounds[0]
        self.assertEqual(bound.scope, "planned")
        self.assertEqual(bound.subject, "mutable_training")
        self.assertEqual(bound.metric, "session_count")
        self.assertEqual(bound.unit, "sessions")
        self.assertEqual(bound.window_days, 7)
        self.assertEqual(bound.max_value, 5)

    def test_next_microcycle_uses_its_own_blueprint_recipe_families(self):
        strategy = compile_strategy_revision(
            self.materialize("2026-10-12", "2026-10-18")
        )
        obligations = {
            item.capability: item
            for item in strategy.obligations
        }
        self.assertEqual(
            obligations["run_threshold"].recipe_family,
            ("run_threshold",),
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
        self.assertNotIn("day_index", source)
        self.assertNotIn("plan.json", source)
        self.assertNotIn("upcoming_week", source)


if __name__ == "__main__":
    unittest.main()
