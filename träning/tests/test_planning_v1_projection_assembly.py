#!/usr/bin/env python3
"""End-to-end canonical projection assembly tests for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_projection_assembly import (  # noqa: E402
    assemble_canonical_shadow_projections,
)
from training_core.application.planning_shadow import (  # noqa: E402
    ShadowPlanningRunInput,
    run_shadow_planning,
)
from training_core.planning.models import EligibilityKind  # noqa: E402


START = date(2026, 10, 5)
END = date(2026, 10, 11)


def strategy_doc(recipe="run_easy_distance"):
    return {
        "goal_contract": {"goal_hash": "goal-1"},
        "planning_engine_v1": {
            "schema_version": 1,
            "strategy_revision": {
                "revision_id": "strategy-v1",
                "goal_set_hash": "goal-1",
                "valid_from": START.isoformat(),
                "valid_until": END.isoformat(),
                "accepted_by": "review:test",
                "source_refs": ["strategy:test"],
                "obligations": [
                    {
                        "obligation_id": "easy",
                        "capability": "run_easy_distance",
                        "role": "primary",
                        "priority_tier": 1,
                        "min_exposures": 1,
                        "max_exposures": 1,
                        "recipe_family": [recipe],
                        "valid_from": START.isoformat(),
                        "valid_until": END.isoformat(),
                        "source_refs": ["strategy:test"],
                        "progression_axes": ["session_duration"],
                        "partial_coverage": [],
                        "prefer_character_variation": False,
                        "accepted_observed_bases": ["confirmed_stimulus"],
                    }
                ],
                "load_envelope": {
                    "envelope_id": "env-v1",
                    "unknown_policy": "block_increase",
                    "established_baseline_ref": "athlete:baseline",
                    "source_refs": ["strategy:test"],
                    "bounds": [
                        {
                            "bound_id": "duration-7d",
                            "scope": "global",
                            "subject": "training_duration",
                            "metric": "duration",
                            "unit": "minutes",
                            "window_days": 7,
                            "max_value": 300,
                            "provenance_refs": ["athlete:baseline"],
                            "requires_complete_coverage": False,
                        }
                    ],
                },
            },
        },
    }


def catalog_doc():
    return {
        "planning_engine_v1": {
            "schema_version": 1,
            "catalog_revision": {
                "revision_id": "catalog-v1",
                "source_refs": ["catalog:test"],
                "options": [
                    {
                        "recipe_id": "run_easy_distance",
                        "dose_option_id": "easy-60",
                        "capabilities": ["run_easy_distance"],
                        "components": [
                            {"discipline": "run", "order": 1},
                        ],
                        "load_dimensions": [
                            {
                                "dimension": "cardiovascular",
                                "level": "low",
                                "provenance_refs": ["catalog:test"],
                            }
                        ],
                        "quantitative_load": [
                            {
                                "scope": "global",
                                "subject": "training_duration",
                                "metric": "duration",
                                "unit": "minutes",
                                "min_value": 60,
                                "max_value": 60,
                                "provenance_refs": ["catalog:test"],
                            }
                        ],
                        "source_refs": ["catalog:test"],
                        "development_character": "easy_steady",
                        "planning_priority": 10,
                        "eligibility_basis": [
                            {
                                "capability": "run_easy_distance",
                                "mode": "numeric",
                                "metric": "duration_minutes",
                                "value": 60,
                                "source_refs": ["catalog:test"],
                            }
                        ],
                    }
                ],
            },
        },
    }


def athlete_doc():
    return {
        "fact_window": {
            "start": (START - timedelta(days=6)).isoformat(),
            "end": (START - timedelta(days=1)).isoformat(),
        },
        "recent_sessions": [],
        "capability_states": {
            "by_capability": {
                "run_easy_distance": {
                    "metric": "duration_minutes",
                    "evidence_state": "demonstrated",
                    "absorbed_value": None,
                    "tolerated_value": None,
                    "demonstrated_value": 60,
                    "progression_ready": False,
                    "verified_exposures": [
                        {"activity_id": 123},
                    ],
                }
            }
        },
        "planning_engine_v1": {
            "schema_version": 1,
            "observed_training_revision": {
                "revision_id": "observed-v1",
                "coverage_from": (START - timedelta(days=6)).isoformat(),
                "coverage_through": (START - timedelta(days=1)).isoformat(),
                "source_refs": ["activity:test"],
                "capability_evidence": [],
                "load_exposures": [],
            },
        },
    }


def policy_doc():
    return {
        "planning_engine_v1": {
            "schema_version": 1,
            "policy_revision": {
                "revision_id": "policy-v1",
                "source_refs": ["policy:test"],
                "compatibility_policy": {
                    "policy_id": "compat-v1",
                    "rules": [],
                    "source_refs": ["policy:test"],
                },
                "spacing_preferences": [],
            },
        },
    }


def profile_doc():
    return {
        "status": "found",
        "revision": 4,
        "profile": {
            "schema_version": 1,
            "status": "complete",
            "current_step": 12,
            "preferences": {
                "frequency": {
                    "preferred_days": 1,
                    "min_days": 1,
                    "max_days": 7,
                },
                "double_sessions": "sometimes",
                "rest_days": "load_driven",
            },
        },
    }


def execution_doc():
    return {
        "planning_engine_v1": {
            "schema_version": 1,
            "execution_facts_revision": {
                "revision_id": "facts-v1",
                "source_refs": ["facts:test"],
                "fixed_commitments": [],
                "availability": [],
                "closed_dates": [],
            },
        },
    }


def assemble(**overrides):
    values = {
        "source_revision": "source-v1",
        "canonical_strategy": strategy_doc(),
        "canonical_catalog": catalog_doc(),
        "canonical_athlete_state": athlete_doc(),
        "canonical_athlete_profile": profile_doc(),
        "canonical_policy": policy_doc(),
        "canonical_execution_facts": execution_doc(),
    }
    values.update(overrides)
    return assemble_canonical_shadow_projections(**values)


class V1ProjectionAssemblyTests(unittest.TestCase):
    def test_complete_explicit_sources_assemble_one_canonical_bundle(self):
        result = assemble()
        self.assertTrue(result.ready, result.blockers)
        self.assertIsNotNone(result.bundle)
        self.assertEqual(
            result.bundle.option_eligibility[0].kind,
            EligibilityKind.ESTABLISH,
        )
        self.assertEqual(
            dict(result.component_revisions),
            {
                "catalog": "catalog-v1",
                "athlete_profile": "athlete-profile:4",
                "execution_facts": "facts-v1",
                "observed_training": "observed-v1",
                "policy": "policy-v1",
                "strategy": "strategy-v1",
            },
        )

    def test_assembled_bundle_runs_shadow_solver_without_side_inputs(self):
        assembled = assemble()
        run = run_shadow_planning(
            ShadowPlanningRunInput(
                affected_from=START,
                affected_until=END,
                history_from=START - timedelta(days=6),
                history_through=START - timedelta(days=1),
                future_context_through=END,
                projections=assembled.bundle,
            )
        )
        self.assertTrue(run.readiness.ready)
        self.assertFalse(run.solve_result.blocked)
        self.assertEqual(len(run.solve_result.plan.workouts), 1)
        self.assertEqual(
            run.solve_result.plan.workouts[0].dose_option_id,
            "easy-60",
        )

    def test_missing_v1_sources_report_all_projection_blockers(self):
        empty = {"legacy": "present"}
        result = assemble(
            canonical_strategy=empty,
            canonical_catalog=empty,
            canonical_athlete_state=empty,
            canonical_athlete_profile=empty,
            canonical_policy=empty,
            canonical_execution_facts=empty,
        )
        self.assertFalse(result.ready)
        self.assertIsNone(result.bundle)
        self.assertEqual(
            {item.stage for item in result.blockers},
            {
                "strategy",
                "catalog",
                "observed_training",
                "athlete_profile",
                "policy",
                "execution_facts",
            },
        )

    def test_cross_contract_missing_recipe_blocks_before_solver(self):
        result = assemble(
            canonical_strategy=strategy_doc(recipe="not-in-catalog"),
        )
        self.assertFalse(result.ready)
        self.assertIn(
            "STRATEGY_RECIPE_MISSING_FROM_CATALOG",
            {item.code for item in result.blockers},
        )

    def test_source_revision_is_mandatory(self):
        result = assemble(source_revision="")
        self.assertFalse(result.ready)
        self.assertEqual(
            result.blockers[0].code,
            "MISSING_CANONICAL_SOURCE_REVISION",
        )

    def test_assembly_contains_no_legacy_planner_dependency(self):
        import training_core.application.planning_projection_assembly as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("plan.json", source)
        self.assertNotIn("upcoming_week", source)


if __name__ == "__main__":
    unittest.main()
