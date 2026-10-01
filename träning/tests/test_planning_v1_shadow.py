#!/usr/bin/env python3
"""Application-level shadow gate tests: missing projections never reach solver."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_shadow import (  # noqa: E402
    ShadowPlanningRunInput,
    run_shadow_planning,
)
from training_core.planning.models import (  # noqa: E402
    AggregateLoadEnvelope,
    ApprovedWorkoutOption,
    EligibilityKind,
    LoadBound,
    LoadCompatibilityPolicy,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    OptionEligibility,
    PlanningObligation,
    StrategyRevision,
    UnknownAggregatePolicy,
    WorkoutComponentIntent,
)
from training_core.planning.objectives import (  # noqa: E402
    DoubleSessionPreference,
    ObjectivePolicy,
    SchedulePreferences,
)
from training_core.planning.projections import ShadowProjectionBundle  # noqa: E402


START = date(2026, 10, 5)
END = date(2026, 10, 11)


def explicit_bundle():
    option = ApprovedWorkoutOption(
        recipe_id="run_easy_distance",
        dose_option_id="easy-60",
        capabilities=("run_easy_distance",),
        components=(WorkoutComponentIntent("run", 1),),
        load_dimensions=(
            LoadDimensionExposure(
                dimension="cardiovascular",
                level=LoadDimensionLevel.LOW,
                provenance_refs=("catalog:v1",),
            ),
        ),
        quantitative_load=(
            LoadEstimate(
                scope="global",
                subject="training_duration",
                metric="duration",
                unit="minutes",
                min_value=60,
                max_value=60,
                provenance_refs=("catalog:v1",),
            ),
        ),
        source_refs=("catalog:v1",),
    )
    obligation = PlanningObligation(
        obligation_id="easy",
        capability="run_easy_distance",
        role="primary",
        priority_tier=1,
        min_exposures=1,
        max_exposures=1,
        recipe_family=("run_easy_distance",),
        valid_from=START,
        valid_until=END,
        source_refs=("strategy:v1",),
    )
    strategy = StrategyRevision(
        revision_id="strategy-v1",
        goal_set_hash="goal",
        valid_from=START,
        valid_until=END,
        obligations=(obligation,),
        load_envelope=AggregateLoadEnvelope(
            envelope_id="env-v1",
            bounds=(
                LoadBound(
                    bound_id="duration",
                    scope="global",
                    subject="training_duration",
                    metric="duration",
                    unit="minutes",
                    window_days=7,
                    max_value=300,
                    provenance_refs=("athlete:baseline",),
                ),
            ),
            unknown_policy=UnknownAggregatePolicy.BLOCK_INCREASE,
            established_baseline_ref="athlete:baseline",
            source_refs=("strategy:v1",),
        ),
        source_refs=("strategy:v1",),
        accepted_by="user_review",
    )
    return ShadowProjectionBundle(
        source_revision="source-v1",
        strategy=strategy,
        workout_options=(option,),
        option_eligibility=(
            OptionEligibility(
                recipe_id=option.recipe_id,
                dose_option_id=option.dose_option_id,
                capability="run_easy_distance",
                kind=EligibilityKind.HOLD,
                source_refs=("athlete:v1",),
            ),
        ),
        observed_credits=(),
        observed_load=(),
        fixed_commitments=(),
        availability=(),
        compatibility_policy=LoadCompatibilityPolicy(
            policy_id="compat-v1",
            rules=(),
            source_refs=("policy:v1",),
        ),
        objective_policy=ObjectivePolicy(
            schedule=SchedulePreferences(
                preferred_active_days=1,
                min_active_days=0,
                max_active_days=7,
                double_sessions=DoubleSessionPreference.SOMETIMES,
            )
        ),
    )


def run_input(bundle):
    return ShadowPlanningRunInput(
        affected_from=START,
        affected_until=END,
        history_from=START - date.resolution * 6,
        history_through=START - date.resolution,
        future_context_through=END,
        projections=bundle,
    )


class ShadowPlanningApplicationTests(unittest.TestCase):
    def test_missing_projection_bundle_never_runs_solver(self):
        result = run_shadow_planning(
            run_input(ShadowProjectionBundle(source_revision="source-v1"))
        )
        self.assertFalse(result.readiness.ready)
        self.assertFalse(result.ran_solver)
        self.assertIsNone(result.solve_result)

    def test_complete_explicit_bundle_runs_pure_solver(self):
        result = run_shadow_planning(run_input(explicit_bundle()))
        self.assertTrue(result.readiness.ready, result.readiness.blockers)
        self.assertTrue(result.ran_solver)
        self.assertIsNotNone(result.solve_result)
        self.assertFalse(result.solve_result.blocked)
        self.assertEqual(len(result.solve_result.plan.workouts), 1)

    def test_shadow_service_has_no_repository_or_commit_dependency(self):
        import training_core.application.planning_shadow as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("commit_solve_result", source)
        self.assertNotIn("supabase", source.lower())
        self.assertNotIn("device_sync", source.lower())
        self.assertNotIn("adaptive_planner", source)


if __name__ == "__main__":
    unittest.main()
