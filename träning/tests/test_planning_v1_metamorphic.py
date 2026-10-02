#!/usr/bin/env python3
"""Metamorphic semantic-identity tests for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.planning.input_hash import planning_input_hash  # noqa: E402
from training_core.planning.models import (  # noqa: E402
    AggregateLoadEnvelope,
    ApprovedWorkoutOption,
    EligibilityKind,
    LoadBound,
    LoadCompatibilityPolicy,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    ObservedLoadExposure,
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
from training_core.planning.solver import PlanningSolveRequest, solve_planning_window  # noqa: E402
from training_core.planning.validation import PlanValidationContext  # noqa: E402


START = date(2026, 10, 5)
END = date(2026, 10, 11)


def duration(minutes):
    return LoadEstimate(
        scope="global",
        subject="training_duration",
        metric="duration",
        unit="minutes",
        min_value=minutes,
        max_value=minutes,
        provenance_refs=("test",),
    )


def option(recipe, dose, minutes):
    return ApprovedWorkoutOption(
        recipe_id=recipe,
        dose_option_id=dose,
        capabilities=("run_easy_distance",),
        components=(WorkoutComponentIntent("run", 1),),
        load_dimensions=(
            LoadDimensionExposure(
                dimension="cardiovascular",
                level=LoadDimensionLevel.LOW,
                provenance_refs=("test",),
            ),
        ),
        quantitative_load=(duration(minutes),),
        source_refs=("test",),
        planning_priority=minutes,
    )


OPTIONS = (
    option("run_easy_distance", "easy-60", 60),
    option("run_easy_trail", "trail-60", 60),
)


def strategy():
    return StrategyRevision(
        revision_id="strategy-meta",
        goal_set_hash="goal-meta",
        valid_from=START,
        valid_until=END,
        obligations=(
            PlanningObligation(
                obligation_id="easy",
                capability="run_easy_distance",
                role="primary",
                priority_tier=1,
                min_exposures=1,
                max_exposures=1,
                recipe_family=("run_easy_distance", "run_easy_trail"),
                valid_from=START,
                valid_until=END,
                source_refs=("test",),
            ),
        ),
        load_envelope=AggregateLoadEnvelope(
            envelope_id="env-meta",
            bounds=(
                LoadBound(
                    bound_id="duration-7d",
                    scope="global",
                    subject="training_duration",
                    metric="duration",
                    unit="minutes",
                    window_days=7,
                    max_value=300,
                    provenance_refs=("test",),
                ),
            ),
            unknown_policy=UnknownAggregatePolicy.BLOCK_INCREASE,
            established_baseline_ref="baseline:test",
            source_refs=("test",),
        ),
        source_refs=("test",),
        accepted_by="test-fixture",
    )


def eligibility(options):
    return tuple(
        OptionEligibility(
            recipe_id=item.recipe_id,
            dose_option_id=item.dose_option_id,
            capability="run_easy_distance",
            kind=EligibilityKind.HOLD,
            source_refs=("test",),
        )
        for item in options
    )


def context(
    *,
    source_revision="rev-a",
    options=OPTIONS,
    observed=(),
    history_from=START - timedelta(days=6),
):
    return PlanValidationContext(
        source_revision=source_revision,
        history_from=history_from,
        history_through=START - timedelta(days=1),
        future_context_through=END,
        strategy=strategy(),
        catalog_options=tuple(options),
        option_eligibility=eligibility(tuple(options)),
        fixed_commitments=(),
        compatibility_policy=LoadCompatibilityPolicy(
            policy_id="none",
            rules=(),
            source_refs=("test",),
        ),
        observed_load_exposures=tuple(observed),
    )


POLICY = ObjectivePolicy(
    schedule=SchedulePreferences(
        preferred_active_days=1,
        min_active_days=0,
        max_active_days=7,
        double_sessions=DoubleSessionPreference.SOMETIMES,
    )
)


def input_hash(ctx):
    return planning_input_hash(ctx, POLICY, START, END)


class PlanningMetamorphicTests(unittest.TestCase):
    def test_source_revision_is_concurrency_identity_not_semantic_plan_identity(self):
        self.assertEqual(
            input_hash(context(source_revision="rev-a")),
            input_hash(context(source_revision="rev-b")),
        )

    def test_option_order_does_not_change_semantic_input_or_plan(self):
        first = context(options=OPTIONS)
        second = context(options=tuple(reversed(OPTIONS)))
        self.assertEqual(input_hash(first), input_hash(second))

        first_result = solve_planning_window(
            PlanningSolveRequest(START, END, first, POLICY)
        )
        second_result = solve_planning_window(
            PlanningSolveRequest(START, END, second, POLICY)
        )
        self.assertEqual(
            first_result.objective_vector.sort_key,
            second_result.objective_vector.sort_key,
        )
        self.assertEqual(
            [(w.local_date, w.recipe_id, w.dose_option_id) for w in first_result.plan.workouts],
            [(w.local_date, w.recipe_id, w.dose_option_id) for w in second_result.plan.workouts],
        )

    def test_irrelevant_old_load_outside_evidence_horizon_does_not_change_hash_or_plan(self):
        irrelevant = ObservedLoadExposure(
            exposure_id="very-old",
            local_date=START - timedelta(days=30),
            load_dimensions=(
                LoadDimensionExposure(
                    dimension="mechanical_leg",
                    level=LoadDimensionLevel.HIGH,
                    provenance_refs=("old",),
                ),
            ),
            quantitative_load=(duration(999),),
            source_refs=("old",),
        )
        base = context()
        extended = context(
            observed=(irrelevant,),
            history_from=START - timedelta(days=60),
        )
        self.assertEqual(input_hash(base), input_hash(extended))

        base_result = solve_planning_window(
            PlanningSolveRequest(START, END, base, POLICY)
        )
        extended_result = solve_planning_window(
            PlanningSolveRequest(START, END, extended, POLICY)
        )
        self.assertEqual(
            base_result.objective_vector.sort_key,
            extended_result.objective_vector.sort_key,
        )
        self.assertEqual(
            [(w.local_date, w.recipe_id, w.dose_option_id) for w in base_result.plan.workouts],
            [(w.local_date, w.recipe_id, w.dose_option_id) for w in extended_result.plan.workouts],
        )

    def test_relevant_recent_load_changes_semantic_identity(self):
        recent = ObservedLoadExposure(
            exposure_id="recent",
            local_date=START - timedelta(days=1),
            load_dimensions=(
                LoadDimensionExposure(
                    dimension="cardiovascular",
                    level=LoadDimensionLevel.LOW,
                    provenance_refs=("recent",),
                ),
            ),
            quantitative_load=(duration(60),),
            source_refs=("recent",),
        )
        self.assertNotEqual(
            input_hash(context()),
            input_hash(context(observed=(recent,))),
        )


if __name__ == "__main__":
    unittest.main()
