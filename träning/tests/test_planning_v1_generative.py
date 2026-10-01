#!/usr/bin/env python3
"""Deterministic generative stress tests for Planning Engine v1.

This is intentionally standard-library-only so the CI contract does not depend
on a property-testing service. The fixed seed makes every failure reproducible.
"""

from __future__ import annotations

import random
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.planning.content import plan_content_hash  # noqa: E402
from training_core.planning.models import (  # noqa: E402
    AggregateLoadEnvelope,
    ApprovedWorkoutOption,
    DailyAvailability,
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
from training_core.planning.solver import PlanningSolveRequest, solve_planning_window  # noqa: E402
from training_core.planning.validation import (  # noqa: E402
    PlanValidationContext,
    validate_plan_content,
)


START = date(2026, 10, 5)
END = date(2026, 10, 11)
DAYS = tuple(START + timedelta(days=index) for index in range(7))


def make_case(case_id: int, rng: random.Random):
    minutes = rng.choice((30, 45, 60, 75, 90))
    ceiling = rng.choice((0, max(0, minutes - 1), minutes, 180, 420))
    availability_mask = rng.randrange(0, 1 << 7)
    preferred_days = rng.randrange(0, 8)

    option = ApprovedWorkoutOption(
        recipe_id="run_easy_distance",
        dose_option_id=f"easy-{minutes}",
        capabilities=("run_easy_distance",),
        components=(WorkoutComponentIntent("run", 1),),
        load_dimensions=(
            LoadDimensionExposure(
                dimension="cardiovascular",
                level=LoadDimensionLevel.LOW,
                provenance_refs=("catalog:generated",),
            ),
        ),
        quantitative_load=(
            LoadEstimate(
                scope="global",
                subject="training_duration",
                metric="duration",
                unit="minutes",
                min_value=minutes,
                max_value=minutes,
                provenance_refs=("catalog:generated",),
            ),
        ),
        source_refs=("catalog:generated",),
        development_character="easy",
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
        source_refs=("strategy:generated",),
        progression_axes=("exposure_count",),
    )
    strategy = StrategyRevision(
        revision_id="strategy-generated",
        goal_set_hash="goal-generated",
        valid_from=START,
        valid_until=END,
        obligations=(obligation,),
        load_envelope=AggregateLoadEnvelope(
            envelope_id="env-generated",
            bounds=(
                LoadBound(
                    bound_id="duration-7d",
                    scope="global",
                    subject="training_duration",
                    metric="duration",
                    unit="minutes",
                    window_days=7,
                    max_value=ceiling,
                    provenance_refs=("athlete:generated-baseline",),
                ),
            ),
            unknown_policy=UnknownAggregatePolicy.BLOCK_INCREASE,
            established_baseline_ref="athlete:generated-baseline",
            source_refs=("strategy:generated",),
        ),
        source_refs=("strategy:generated",),
        accepted_by="test-fixture",
    )
    context = PlanValidationContext(
        source_revision=f"source-{case_id}",
        history_from=START - timedelta(days=6),
        history_through=START - timedelta(days=1),
        future_context_through=END,
        strategy=strategy,
        catalog_options=(option,),
        option_eligibility=(
            OptionEligibility(
                recipe_id=option.recipe_id,
                dose_option_id=option.dose_option_id,
                capability="run_easy_distance",
                kind=EligibilityKind.HOLD,
                source_refs=("athlete:generated",),
            ),
        ),
        fixed_commitments=(),
        compatibility_policy=LoadCompatibilityPolicy(
            policy_id="compat-generated",
            rules=(),
            source_refs=("policy:generated",),
        ),
        availability=tuple(
            DailyAvailability(
                local_date=day,
                available=bool(availability_mask & (1 << index)),
                source_refs=("user:generated-availability",),
            )
            for index, day in enumerate(DAYS)
        ),
    )
    request = PlanningSolveRequest(
        semantic_input_hash=f"input-{case_id}",
        affected_from=START,
        affected_until=END,
        validation_context=context,
        objective_policy=ObjectivePolicy(
            schedule=SchedulePreferences(
                preferred_active_days=preferred_days,
                min_active_days=0,
                max_active_days=7,
                double_sessions=DoubleSessionPreference.SOMETIMES,
            )
        ),
    )
    expected_day = next(
        (
            day
            for index, day in enumerate(DAYS)
            if availability_mask & (1 << index)
        ),
        None,
    )
    can_train = expected_day is not None and ceiling >= minutes
    return request, context, expected_day, can_train


class PlanningGenerativeStressTests(unittest.TestCase):
    def test_ten_thousand_reproducible_planning_cases(self):
        rng = random.Random(20261001)

        for case_id in range(10_000):
            with self.subTest(case_id=case_id):
                request, context, expected_day, can_train = make_case(
                    case_id,
                    rng,
                )
                result = solve_planning_window(request)

                # There are no immutable hard conflicts in this generated
                # family, so inability to satisfy the soft obligation must
                # degrade to a valid empty plan rather than BLOCKED.
                self.assertFalse(result.blocked)
                self.assertIsNotNone(result.plan)

                report = validate_plan_content(result.plan, context)
                self.assertTrue(report.valid, report.issues)
                self.assertEqual(
                    result.authority_state.plan_content_hash,
                    plan_content_hash(result.plan),
                )

                if can_train:
                    self.assertEqual(len(result.plan.workouts), 1)
                    self.assertEqual(
                        result.plan.workouts[0].local_date,
                        expected_day,
                    )
                else:
                    self.assertEqual(result.plan.workouts, ())

                # Re-solving selected cases proves deterministic replay without
                # doubling the total stress-suite cost.
                if case_id % 250 == 0:
                    replay = solve_planning_window(request)
                    self.assertEqual(
                        plan_content_hash(result.plan),
                        plan_content_hash(replay.plan),
                    )
                    self.assertEqual(
                        result.objective_vector.sort_key,
                        replay.objective_vector.sort_key,
                    )


if __name__ == "__main__":
    unittest.main()
