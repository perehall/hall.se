#!/usr/bin/env python3
"""Semantic PlanContent tests written before the solver exists."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.planning import (  # noqa: E402
    ContributionKind,
    FixedLoadCommitment,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    ObligationContribution,
    PlanContent,
    PlannedTrainingWorkout,
    PlanningContractError,
    WorkoutComponentIntent,
    plan_content_hash,
)


def dimension(name="mechanical_leg", level=LoadDimensionLevel.MODERATE):
    return LoadDimensionExposure(
        dimension=name,
        level=level,
        provenance_refs=("test:catalog",),
    )


def estimate(
    metric="duration",
    unit="minutes",
    low=60,
    high=60,
    scope="global",
    subject="training_duration",
):
    return LoadEstimate(
        scope=scope,
        subject=subject,
        metric=metric,
        unit=unit,
        min_value=low,
        max_value=high,
        provenance_refs=("test:catalog",),
    )


def workout(
    workout_id,
    *,
    day=date(2026, 10, 2),
    recipe_id="run_easy_distance",
    dose_option_id="run-easy-75",
    obligation_id="easy-distance",
    source_capability="run_easy_distance",
    contribution_kind=ContributionKind.DIRECT,
    credit_numerator=1,
    credit_denominator=1,
    components=(WorkoutComponentIntent("run", 1),),
    within_day_order=None,
    source_refs=("solver:test",),
):
    return PlannedTrainingWorkout(
        workout_id=workout_id,
        local_date=day,
        recipe_id=recipe_id,
        dose_option_id=dose_option_id,
        obligation_contributions=(
            ObligationContribution(
                obligation_id=obligation_id,
                source_capability=source_capability,
                kind=contribution_kind,
                credit_numerator=credit_numerator,
                credit_denominator=credit_denominator,
            ),
        ),
        components=components,
        load_dimensions=(dimension(),),
        quantitative_load=(estimate(low=75, high=75),),
        source_refs=source_refs,
        within_day_order=within_day_order,
    )


def commitment(commitment_id="fixed-1", *, day=date(2026, 10, 5)):
    return FixedLoadCommitment(
        commitment_id=commitment_id,
        local_date=day,
        label="Fast extern belastning",
        load_dimensions=(
            dimension("mechanical_leg", LoadDimensionLevel.HIGH),
            dimension("technical", LoadDimensionLevel.HIGH),
        ),
        quantitative_load=(
            estimate(low=60, high=120),
        ),
        source_refs=("user:confirmed",),
    )


def plan(*, workouts, fixed_commitments=()):
    return PlanContent(
        source_revision="source-42",
        strategy_revision_id="strategy-a",
        affected_from=date(2026, 10, 1),
        affected_until=date(2026, 10, 7),
        workouts=tuple(workouts),
        fixed_commitments=tuple(fixed_commitments),
    )


class PlannedTrainingWorkoutTests(unittest.TestCase):
    def test_multisport_components_require_contiguous_order(self):
        with self.assertRaises(PlanningContractError):
            workout(
                "brick-1",
                components=(
                    WorkoutComponentIntent("bike", 1),
                    WorkoutComponentIntent("run", 3),
                ),
            )

    def test_duplicate_component_order_is_rejected(self):
        with self.assertRaises(PlanningContractError):
            workout(
                "brick-1",
                components=(
                    WorkoutComponentIntent("bike", 1),
                    WorkoutComponentIntent("run", 1),
                ),
            )

    def test_workout_requires_explicit_load_dimensions(self):
        with self.assertRaises(PlanningContractError):
            PlannedTrainingWorkout(
                workout_id="w1",
                local_date=date(2026, 10, 2),
                recipe_id="run_easy_distance",
                dose_option_id="run-easy-75",
                obligation_contributions=(
                    ObligationContribution(
                        obligation_id="easy-distance",
                        source_capability="run_easy_distance",
                        kind=ContributionKind.DIRECT,
                        credit_numerator=1,
                        credit_denominator=1,
                    ),
                ),
                components=(WorkoutComponentIntent("run", 1),),
                load_dimensions=(),
                quantitative_load=(estimate(),),
                source_refs=("solver:test",),
            )


class PlanContentTests(unittest.TestCase):
    def test_multiple_independent_same_day_workouts_remain_separate(self):
        result = plan(
            workouts=(
                workout("swim-1", recipe_id="swim_aerobic", dose_option_id="swim-3200"),
                workout("strength-1", recipe_id="strength_core", dose_option_id="strength-30"),
            )
        )
        self.assertEqual(len(result.workouts), 2)
        self.assertEqual({item.workout_id for item in result.workouts}, {"swim-1", "strength-1"})

    def test_duplicate_workout_identity_is_rejected(self):
        with self.assertRaises(PlanningContractError):
            plan(workouts=(workout("w1"), workout("w1")))

    def test_duplicate_explicit_same_day_order_is_rejected(self):
        with self.assertRaises(PlanningContractError):
            plan(
                workouts=(
                    workout("w1", within_day_order=1),
                    workout("w2", within_day_order=1),
                )
            )

    def test_workout_outside_affected_window_is_rejected(self):
        with self.assertRaises(PlanningContractError):
            plan(workouts=(workout("w1", day=date(2026, 10, 8)),))

    def test_fixed_commitment_outside_affected_window_is_rejected(self):
        with self.assertRaises(PlanningContractError):
            plan(workouts=(), fixed_commitments=(commitment(day=date(2026, 10, 8)),))


class PlanContentHashTests(unittest.TestCase):
    def test_reordering_independent_workouts_does_not_change_hash(self):
        a = workout("a", within_day_order=1)
        b = workout("b", within_day_order=2)
        self.assertEqual(
            plan_content_hash(plan(workouts=(a, b))),
            plan_content_hash(plan(workouts=(b, a))),
        )

    def test_reordering_load_dimensions_does_not_change_hash(self):
        first = PlannedTrainingWorkout(
            workout_id="w1",
            local_date=date(2026, 10, 2),
            recipe_id="run_threshold",
            dose_option_id="run-threshold-4x8",
            obligation_contributions=(
                ObligationContribution(
                    obligation_id="threshold",
                    source_capability="run_threshold",
                    kind=ContributionKind.DIRECT,
                    credit_numerator=1,
                    credit_denominator=1,
                ),
            ),
            components=(WorkoutComponentIntent("run", 1),),
            load_dimensions=(
                dimension("cardiovascular", LoadDimensionLevel.HIGH),
                dimension("mechanical_leg", LoadDimensionLevel.MODERATE),
            ),
            quantitative_load=(estimate("work", "minutes", 32, 32),),
            source_refs=("one",),
        )
        second = PlannedTrainingWorkout(
            workout_id="w1",
            local_date=date(2026, 10, 2),
            recipe_id="run_threshold",
            dose_option_id="run-threshold-4x8",
            obligation_contributions=(
                ObligationContribution(
                    obligation_id="threshold",
                    source_capability="run_threshold",
                    kind=ContributionKind.DIRECT,
                    credit_numerator=1,
                    credit_denominator=1,
                ),
            ),
            components=(WorkoutComponentIntent("run", 1),),
            load_dimensions=tuple(reversed(first.load_dimensions)),
            quantitative_load=(estimate("work", "minutes", 32, 32),),
            source_refs=("two",),
        )
        self.assertEqual(
            plan_content_hash(plan(workouts=(first,))),
            plan_content_hash(plan(workouts=(second,))),
        )

    def test_provenance_change_does_not_change_training_content_hash(self):
        first = workout("w1", source_refs=("solver:a",))
        second = workout("w1", source_refs=("solver:b",))
        self.assertEqual(
            plan_content_hash(plan(workouts=(first,))),
            plan_content_hash(plan(workouts=(second,))),
        )

    def test_dose_change_changes_hash(self):
        first = workout("w1", dose_option_id="run-easy-75")
        second = workout("w1", dose_option_id="run-easy-90")
        self.assertNotEqual(
            plan_content_hash(plan(workouts=(first,))),
            plan_content_hash(plan(workouts=(second,))),
        )

    def test_multisport_component_order_changes_hash(self):
        bike_run = workout(
            "brick",
            recipe_id="brick",
            dose_option_id="brick-base",
            components=(
                WorkoutComponentIntent("bike", 1),
                WorkoutComponentIntent("run", 2),
            ),
        )
        run_bike = workout(
            "brick",
            recipe_id="brick",
            dose_option_id="brick-base",
            components=(
                WorkoutComponentIntent("run", 1),
                WorkoutComponentIntent("bike", 2),
            ),
        )
        self.assertNotEqual(
            plan_content_hash(plan(workouts=(bike_run,))),
            plan_content_hash(plan(workouts=(run_bike,))),
        )

    def test_obligation_credit_change_changes_hash(self):
        full = workout(
            "w1",
            obligation_id="easy-distance",
            source_capability="run_easy_distance",
            contribution_kind=ContributionKind.DIRECT,
            credit_numerator=1,
            credit_denominator=1,
        )
        half = workout(
            "w1",
            obligation_id="easy-distance",
            source_capability="mtb_aerobic",
            contribution_kind=ContributionKind.PARTIAL,
            credit_numerator=1,
            credit_denominator=2,
        )
        self.assertNotEqual(
            plan_content_hash(plan(workouts=(full,))),
            plan_content_hash(plan(workouts=(half,))),
        )

    def test_within_day_order_changes_hash(self):
        first = workout("w1", within_day_order=1)
        second = workout("w1", within_day_order=2)
        self.assertNotEqual(
            plan_content_hash(plan(workouts=(first,))),
            plan_content_hash(plan(workouts=(second,))),
        )

    def test_fixed_load_change_changes_hash(self):
        low = FixedLoadCommitment(
            commitment_id="fixed-1",
            local_date=date(2026, 10, 5),
            label="Fast extern belastning",
            load_dimensions=(dimension("mechanical_leg", LoadDimensionLevel.MODERATE),),
            source_refs=("user:confirmed",),
        )
        high = FixedLoadCommitment(
            commitment_id="fixed-1",
            local_date=date(2026, 10, 5),
            label="Fast extern belastning",
            load_dimensions=(dimension("mechanical_leg", LoadDimensionLevel.HIGH),),
            source_refs=("user:confirmed",),
        )
        self.assertNotEqual(
            plan_content_hash(plan(workouts=(), fixed_commitments=(low,))),
            plan_content_hash(plan(workouts=(), fixed_commitments=(high,))),
        )


if __name__ == "__main__":
    unittest.main()
