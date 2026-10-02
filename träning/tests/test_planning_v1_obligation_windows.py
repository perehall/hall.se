#!/usr/bin/env python3
"""Obligation-window isolation for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.planning.models import (  # noqa: E402
    AggregateLoadEnvelope,
    ApprovedWorkoutOption,
    ContributionKind,
    EligibilityKind,
    LoadBound,
    LoadCompatibilityPolicy,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    ObligationContribution,
    ObservedCreditBasis,
    ObservedObligationCredit,
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
from training_core.planning.solver import (  # noqa: E402
    PlanningSolveRequest,
    solve_planning_window,
)
from training_core.planning.validation import PlanValidationContext  # noqa: E402


W1_START = date(2026, 10, 5)
W1_END = date(2026, 10, 11)
W2_START = date(2026, 10, 12)
W2_END = date(2026, 10, 18)


def option():
    return ApprovedWorkoutOption(
        recipe_id="run_threshold",
        dose_option_id="threshold-32",
        capabilities=("run_threshold",),
        components=(WorkoutComponentIntent("run", 1),),
        load_dimensions=(
            LoadDimensionExposure(
                dimension="cardiovascular",
                level=LoadDimensionLevel.HIGH,
                provenance_refs=("catalog:test",),
            ),
        ),
        quantitative_load=(
            LoadEstimate(
                scope="global",
                subject="training_duration",
                metric="duration",
                unit="minutes",
                min_value=50,
                max_value=50,
                provenance_refs=("catalog:test",),
            ),
        ),
        source_refs=("catalog:test",),
    )


def obligation(obligation_id, start, end):
    return PlanningObligation(
        obligation_id=obligation_id,
        capability="run_threshold",
        role="primary",
        priority_tier=1,
        min_exposures=1,
        max_exposures=1,
        recipe_family=("run_threshold",),
        valid_from=start,
        valid_until=end,
        source_refs=(f"strategy:{obligation_id}",),
        accepted_observed_bases=(ObservedCreditBasis.CONFIRMED_STIMULUS,),
    )


def strategy():
    return StrategyRevision(
        revision_id="strategy-two-weeks",
        goal_set_hash="goal",
        valid_from=W1_START,
        valid_until=W2_END,
        obligations=(
            obligation("threshold-w1", W1_START, W1_END),
            obligation("threshold-w2", W2_START, W2_END),
        ),
        load_envelope=AggregateLoadEnvelope(
            envelope_id="env",
            bounds=(
                LoadBound(
                    bound_id="duration-7d",
                    scope="global",
                    subject="training_duration",
                    metric="duration",
                    unit="minutes",
                    window_days=7,
                    max_value=300,
                    provenance_refs=("baseline:test",),
                ),
            ),
            unknown_policy=UnknownAggregatePolicy.BLOCK_INCREASE,
            established_baseline_ref="baseline:test",
            source_refs=("strategy:test",),
        ),
        source_refs=("strategy:test",),
        accepted_by="review:test",
    )


POLICY = ObjectivePolicy(
    schedule=SchedulePreferences(
        preferred_active_days=1,
        min_active_days=0,
        max_active_days=7,
        double_sessions=DoubleSessionPreference.SOMETIMES,
    )
)


def context(*, source_revision, start, end, observed=()):
    item = option()
    return PlanValidationContext(
        source_revision=source_revision,
        history_from=start - timedelta(days=6),
        history_through=start - timedelta(days=1),
        future_context_through=end,
        strategy=strategy(),
        catalog_options=(item,),
        option_eligibility=(
            OptionEligibility(
                recipe_id=item.recipe_id,
                dose_option_id=item.dose_option_id,
                capability="run_threshold",
                kind=EligibilityKind.HOLD,
                source_refs=("athlete:test",),
            ),
        ),
        fixed_commitments=(),
        compatibility_policy=LoadCompatibilityPolicy(
            policy_id="compat",
            rules=(),
            source_refs=("policy:test",),
        ),
        observed_obligation_credits=tuple(observed),
    )


class ObligationWindowIsolationTests(unittest.TestCase):
    def test_future_week_obligation_does_not_enter_current_week_selection(self):
        result = solve_planning_window(
            PlanningSolveRequest(
                affected_from=W1_START,
                affected_until=W1_END,
                validation_context=context(
                    source_revision="rev-w1",
                    start=W1_START,
                    end=W1_END,
                ),
                objective_policy=POLICY,
            )
        )
        self.assertFalse(result.blocked)
        self.assertEqual(len(result.plan.workouts), 1)
        self.assertEqual(
            result.trace.workout_decisions[0].obligation_ids,
            ("threshold-w1",),
        )
        self.assertEqual(
            result.objective_vector.required_deficit_by_tier,
            (0,),
        )

    def test_week_one_credit_cannot_satisfy_week_two_obligation(self):
        observed_w1 = ObservedObligationCredit(
            local_date=date(2026, 10, 6),
            contribution=ObligationContribution(
                obligation_id="threshold-w1",
                source_capability="run_threshold",
                kind=ContributionKind.DIRECT,
                credit_numerator=1,
                credit_denominator=1,
            ),
            basis=ObservedCreditBasis.CONFIRMED_STIMULUS,
            source_refs=("activity:w1-threshold",),
        )
        result = solve_planning_window(
            PlanningSolveRequest(
                affected_from=W2_START,
                affected_until=W2_END,
                validation_context=context(
                    source_revision="rev-w2",
                    start=W2_START,
                    end=W2_END,
                    observed=(observed_w1,),
                ),
                objective_policy=POLICY,
            )
        )
        self.assertFalse(result.blocked)
        self.assertEqual(len(result.plan.workouts), 1)
        self.assertEqual(
            result.trace.workout_decisions[0].obligation_ids,
            ("threshold-w2",),
        )
        self.assertEqual(
            result.objective_vector.required_deficit_by_tier,
            (0,),
        )


if __name__ == "__main__":
    unittest.main()
