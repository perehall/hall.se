#!/usr/bin/env python3
"""Strict source-ownership tests for Planning Engine v1 StrategyRevision."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_strategy_projection import (  # noqa: E402
    StrategyProjectionError,
    compile_strategy_revision,
)


def explicit_document():
    return {
        "goal_contract": {"goal_hash": "goal-1"},
        "current_mesocycle": {
            "contract": {
                "primary": ["run_threshold"],
            }
        },
        "planning_engine_v1": {
            "schema_version": 1,
            "strategy_revision": {
                "revision_id": "strategy-v1",
                "goal_set_hash": "goal-1",
                "valid_from": "2026-10-05",
                "valid_until": "2026-10-11",
                "accepted_by": "review:test",
                "source_refs": ["mesocycle:test", "policy:test"],
                "obligations": [
                    {
                        "obligation_id": "run-threshold",
                        "capability": "run_threshold",
                        "role": "primary",
                        "priority_tier": 1,
                        "min_exposures": 1,
                        "max_exposures": 1,
                        "recipe_family": ["run_threshold"],
                        "valid_from": "2026-10-05",
                        "valid_until": "2026-10-11",
                        "source_refs": ["mesocycle:test"],
                        "progression_axes": ["session_dose"],
                        "partial_coverage": [],
                        "prefer_character_variation": False,
                    }
                ],
                "load_envelope": {
                    "envelope_id": "env-v1",
                    "unknown_policy": "block_increase",
                    "established_baseline_ref": "athlete:baseline",
                    "source_refs": ["athlete:baseline", "policy:test"],
                    "bounds": [
                        {
                            "bound_id": "duration-7d",
                            "scope": "global",
                            "subject": "training_duration",
                            "metric": "duration",
                            "unit": "minutes",
                            "window_days": 7,
                            "max_value": 420,
                            "provenance_refs": ["athlete:baseline"],
                            "requires_complete_coverage": True,
                        }
                    ],
                },
            },
        },
    }


class V1StrategyProjectionTests(unittest.TestCase):
    def test_explicit_v1_strategy_compiles_without_legacy_inference(self):
        result = compile_strategy_revision(explicit_document())
        self.assertEqual(result.revision_id, "strategy-v1")
        self.assertEqual(result.goal_set_hash, "goal-1")
        self.assertEqual(len(result.obligations), 1)
        self.assertEqual(result.obligations[0].min_exposures, 1)
        self.assertEqual(result.obligations[0].max_exposures, 1)
        self.assertTrue(
            result.load_envelope.bounds[0].requires_complete_coverage
        )

    def test_legacy_primary_capability_cannot_substitute_for_explicit_bounds(self):
        document = explicit_document()
        document.pop("planning_engine_v1")
        with self.assertRaises(StrategyProjectionError) as raised:
            compile_strategy_revision(document)
        self.assertEqual(
            raised.exception.code,
            "MISSING_V1_STRATEGY_REVISION",
        )

    def test_missing_exposure_bound_blocks_strategy_projection(self):
        document = explicit_document()
        obligation = document["planning_engine_v1"]["strategy_revision"]["obligations"][0]
        obligation.pop("min_exposures")
        with self.assertRaises(StrategyProjectionError) as raised:
            compile_strategy_revision(document)
        self.assertEqual(
            raised.exception.code,
            "INVALID_V1_STRATEGY_CONTRACT",
        )

    def test_goal_change_invalidates_stale_strategy_revision(self):
        document = explicit_document()
        document["goal_contract"]["goal_hash"] = "goal-2"
        with self.assertRaises(StrategyProjectionError) as raised:
            compile_strategy_revision(document)
        self.assertEqual(raised.exception.code, "STALE_V1_GOAL_SET")

    def test_projection_module_contains_no_legacy_planner_dependency(self):
        import training_core.application.planning_strategy_projection as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("microcycle_slot", source)
        self.assertNotIn("forward_horizon", source)


if __name__ == "__main__":
    unittest.main()
