#!/usr/bin/env python3
"""Semantic stability matching tests for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.planning.models import (  # noqa: E402
    ContributionKind,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    ObligationContribution,
    PlanContent,
    PlannedTrainingWorkout,
    WorkoutComponentIntent,
)
from training_core.planning.objectives import _stability_penalty  # noqa: E402


START = date(2026, 10, 5)
END = date(2026, 10, 11)


def workout(
    workout_id,
    day,
    *,
    recipe="run_threshold",
    dose="threshold-32",
    order=None,
    obligation="threshold",
):
    return PlannedTrainingWorkout(
        workout_id=workout_id,
        local_date=day,
        recipe_id=recipe,
        dose_option_id=dose,
        obligation_contributions=(
            ObligationContribution(
                obligation_id=obligation,
                source_capability="run_threshold",
                kind=ContributionKind.DIRECT,
                credit_numerator=1,
                credit_denominator=1,
            ),
        ),
        components=(WorkoutComponentIntent("run", 1),),
        load_dimensions=(
            LoadDimensionExposure(
                dimension="cardiovascular",
                level=LoadDimensionLevel.HIGH,
                provenance_refs=("test",),
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
                provenance_refs=("test",),
            ),
        ),
        source_refs=("test",),
        within_day_order=order,
    )


def plan(*rows):
    return PlanContent(
        source_revision="source",
        strategy_revision_id="strategy",
        affected_from=START,
        affected_until=END,
        workouts=tuple(rows),
        fixed_commitments=(),
    )


class SemanticStabilityTests(unittest.TestCase):
    def test_changed_generated_id_is_not_false_churn(self):
        before = plan(workout("old-id", date(2026, 10, 7)))
        after = plan(workout("new-id", date(2026, 10, 7)))
        self.assertEqual(_stability_penalty(after, before), (0, 0, 0, 0))

    def test_moving_same_intent_is_a_move_not_remove_plus_add(self):
        before = plan(workout("old-id", date(2026, 10, 7)))
        after = plan(workout("new-id", date(2026, 10, 8)))
        churn, moves, prescription, order = _stability_penalty(after, before)
        self.assertEqual((churn, moves, prescription, order), (0, 1, 0, 0))

    def test_same_intent_new_dose_is_prescription_change(self):
        before = plan(workout("old-id", date(2026, 10, 7), dose="threshold-32"))
        after = plan(workout("new-id", date(2026, 10, 7), dose="threshold-36"))
        self.assertEqual(_stability_penalty(after, before), (0, 0, 1, 0))

    def test_two_identical_exposures_match_chronologically(self):
        before = plan(
            workout("a", date(2026, 10, 6)),
            workout("b", date(2026, 10, 9)),
        )
        after = plan(
            workout("x", date(2026, 10, 7)),
            workout("y", date(2026, 10, 9)),
        )
        self.assertEqual(_stability_penalty(after, before), (0, 1, 0, 0))

    def test_different_obligation_is_real_identity_churn(self):
        before = plan(workout("a", date(2026, 10, 7), obligation="threshold"))
        after = plan(workout("b", date(2026, 10, 7), obligation="different"))
        churn, *_ = _stability_penalty(after, before)
        self.assertEqual(churn, 2)


if __name__ == "__main__":
    unittest.main()
