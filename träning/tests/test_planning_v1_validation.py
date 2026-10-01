#!/usr/bin/env python3
"""Hard-invariant tests for the Planning Engine v1 final validator."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.planning import (  # noqa: E402
    AggregateLoadEnvelope,
    ApprovedWorkoutOption,
    ContributionKind,
    CoverageRule,
    FixedLoadCommitment,
    LoadBound,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    ObligationContribution,
    ObservedLoadSample,
    ObservedObligationCredit,
    PlanContent,
    PlannedTrainingWorkout,
    PlanningObligation,
    PlanValidationContext,
    StrategyRevision,
    UnknownAggregatePolicy,
    WorkoutComponentIntent,
    validate_plan_content,
)


AFFECTED_FROM = date(2026, 10, 5)
AFFECTED_UNTIL = date(2026, 10, 11)


def dim(name, level):
    return LoadDimensionExposure(
        dimension=name,
        level=level,
        provenance_refs=("catalog:test",),
    )


def load(scope, subject, metric, unit, low, high=None):
    return LoadEstimate(
        scope=scope,
        subject=subject,
        metric=metric,
        unit=unit,
        min_value=low,
        max_value=low if high is None else high,
        provenance_refs=("catalog:test",),
    )


def run_component():
    return (WorkoutComponentIntent("run", 1),)


def mtb_component():
    return (WorkoutComponentIntent("mtb", 1),)


def option_easy(recipe_id="run_easy_distance", dose_id="run-easy-75", *, capabilities=("run_easy_distance",)):
    return ApprovedWorkoutOption(
        recipe_id=recipe_id,
        dose_option_id=dose_id,
        capabilities=capabilities,
        components=run_component(),
        load_dimensions=(
            dim("mechanical_leg", LoadDimensionLevel.MODERATE),
            dim("cardiovascular", LoadDimensionLevel.MODERATE),
        ),
        quantitative_load=(
            load("global", "training_duration", "duration", "minutes", 75),
            load("capability", "run_easy_distance", "duration", "minutes", 75),
        ),
        source_refs=("catalog:easy",),
    )


def option_threshold():
    return ApprovedWorkoutOption(
        recipe_id="run_threshold",
        dose_option_id="run-threshold-4x8",
        capabilities=("run_threshold",),
        components=run_component(),
        load_dimensions=(
            dim("mechanical_leg", LoadDimensionLevel.MODERATE),
            dim("cardiovascular", LoadDimensionLevel.HIGH),
        ),
        quantitative_load=(
            load("global", "training_duration", "duration", "minutes", 50),
            load("capability", "run_threshold", "work", "minutes", 32),
        ),
        source_refs=("catalog:threshold",),
    )


def option_mtb():
    return ApprovedWorkoutOption(
        recipe_id="mtb_aerobic",
        dose_option_id="mtb-60",
        capabilities=("mtb_aerobic",),
        components=mtb_component(),
        load_dimensions=(
            dim("mechanical_leg", LoadDimensionLevel.MODERATE),
            dim("technical", LoadDimensionLevel.MODERATE),
        ),
        quantitative_load=(
            load("global", "training_duration", "duration", "minutes", 60),
        ),
        source_refs=("catalog:mtb",),
    )


def easy_obligation(*, max_exposures=2):
    return PlanningObligation(
        obligation_id="easy-distance",
        capability="run_easy_distance",
        role="primary",
        priority_tier=1,
        min_exposures=1,
        max_exposures=max_exposures,
        recipe_family=("run_easy_distance",),
        valid_from=AFFECTED_FROM,
        valid_until=AFFECTED_UNTIL,
        source_refs=("strategy:easy",),
        progression_axes=("session_dose", "exposure_count"),
        partial_coverage=(CoverageRule("mtb_aerobic", 1, 2),),
    )


def threshold_obligation():
    return PlanningObligation(
        obligation_id="threshold",
        capability="run_threshold",
        role="primary",
        priority_tier=1,
        min_exposures=1,
        max_exposures=2,
        recipe_family=("run_threshold",),
        valid_from=AFFECTED_FROM,
        valid_until=AFFECTED_UNTIL,
        source_refs=("strategy:threshold",),
        progression_axes=("session_dose", "exposure_count"),
    )


def envelope():
    return AggregateLoadEnvelope(
        envelope_id="env-1",
        bounds=(
            LoadBound(
                bound_id="duration-7d",
                scope="global",
                subject="training_duration",
                metric="duration",
                unit="minutes",
                window_days=7,
                max_value=300,
                provenance_refs=("athlete_state:baseline",),
            ),
            LoadBound(
                bound_id="threshold-work-7d",
                scope="capability",
                subject="run_threshold",
                metric="work",
                unit="minutes",
                window_days=7,
                max_value=64,
                provenance_refs=("athlete_state:threshold",),
            ),
        ),
        unknown_policy=UnknownAggregatePolicy.BLOCK_INCREASE,
        established_baseline_ref="athlete_state:baseline",
        source_refs=("strategy:load",),
    )


def strategy(*, obligations=None, valid_until=date(2026, 11, 1)):
    return StrategyRevision(
        revision_id="strategy-a",
        goal_set_hash="goalhash",
        valid_from=AFFECTED_FROM,
        valid_until=valid_until,
        obligations=tuple(obligations or (easy_obligation(), threshold_obligation())),
        load_envelope=envelope(),
        source_refs=("goal:v1", "review:accepted"),
        accepted_by="user_review",
    )


def fixed_commitment(*, level=LoadDimensionLevel.HIGH):
    return FixedLoadCommitment(
        commitment_id="fixed-external-1",
        local_date=AFFECTED_FROM,
        label="Fast extern belastning",
        load_dimensions=(
            dim("mechanical_leg", level),
            dim("technical", LoadDimensionLevel.HIGH),
        ),
        quantitative_load=(
            load("global", "training_duration", "duration", "minutes", 60, 120),
        ),
        source_refs=("user:confirmed",),
    )


def direct(obligation_id, capability):
    return ObligationContribution(
        obligation_id=obligation_id,
        source_capability=capability,
        kind=ContributionKind.DIRECT,
        credit_numerator=1,
        credit_denominator=1,
    )


def partial(obligation_id, capability, numerator=1, denominator=2):
    return ObligationContribution(
        obligation_id=obligation_id,
        source_capability=capability,
        kind=ContributionKind.PARTIAL,
        credit_numerator=numerator,
        credit_denominator=denominator,
    )


def workout_from_option(workout_id, day, option, contribution):
    return PlannedTrainingWorkout(
        workout_id=workout_id,
        local_date=day,
        recipe_id=option.recipe_id,
        dose_option_id=option.dose_option_id,
        obligation_contributions=(contribution,),
        components=option.components,
        load_dimensions=option.load_dimensions,
        quantitative_load=option.quantitative_load,
        source_refs=("solver:test",),
    )


def valid_plan(*, workouts=None, commitments=None, source_revision="source-1", affected_until=AFFECTED_UNTIL):
    easy = option_easy()
    threshold = option_threshold()
    rows = workouts
    if rows is None:
        rows = (
            workout_from_option(
                "easy-1",
                date(2026, 10, 6),
                easy,
                direct("easy-distance", "run_easy_distance"),
            ),
            workout_from_option(
                "threshold-1",
                date(2026, 10, 8),
                threshold,
                direct("threshold", "run_threshold"),
            ),
        )
    return PlanContent(
        source_revision=source_revision,
        strategy_revision_id="strategy-a",
        affected_from=AFFECTED_FROM,
        affected_until=affected_until,
        workouts=tuple(rows),
        fixed_commitments=tuple(commitments if commitments is not None else (fixed_commitment(),)),
    )


def context(
    *,
    strategy_value=None,
    catalog=None,
    fixed=None,
    observed_credits=(),
    observed_load=(),
    source_revision="source-1",
    history_from=date(2026, 9, 29),
    history_through=date(2026, 10, 4),
):
    return PlanValidationContext(
        source_revision=source_revision,
        history_from=history_from,
        history_through=history_through,
        strategy=strategy_value or strategy(),
        catalog_options=tuple(catalog or (option_easy(), option_threshold(), option_mtb())),
        fixed_commitments=tuple(fixed if fixed is not None else (fixed_commitment(),)),
        observed_obligation_credits=tuple(observed_credits),
        observed_load_samples=tuple(observed_load),
    )


class FinalPlanningValidatorTests(unittest.TestCase):
    def test_valid_plan_passes_independent_final_gate(self):
        report = validate_plan_content(valid_plan(), context())
        self.assertTrue(report.valid, report.issues)

    def test_stale_source_revision_is_rejected(self):
        report = validate_plan_content(
            valid_plan(source_revision="old"),
            context(source_revision="new"),
        )
        self.assertIn("STALE_SOURCE_REVISION", report.codes())

    def test_incomplete_history_horizon_is_rejected(self):
        report = validate_plan_content(
            valid_plan(),
            context(history_from=date(2026, 10, 2)),
        )
        self.assertIn("INSUFFICIENT_HISTORY_COVERAGE", report.codes())

    def test_missing_fixed_commitment_is_rejected(self):
        report = validate_plan_content(
            valid_plan(commitments=()),
            context(),
        )
        self.assertIn("FIXED_COMMITMENT_MISSING", report.codes())

    def test_altered_fixed_commitment_is_rejected(self):
        altered = fixed_commitment(level=LoadDimensionLevel.MODERATE)
        report = validate_plan_content(
            valid_plan(commitments=(altered,)),
            context(),
        )
        self.assertIn("FIXED_COMMITMENT_CHANGED", report.codes())

    def test_unapproved_recipe_dose_is_rejected(self):
        easy = option_easy(dose_id="run-easy-999")
        row = workout_from_option(
            "easy-x",
            date(2026, 10, 6),
            easy,
            direct("easy-distance", "run_easy_distance"),
        )
        report = validate_plan_content(
            valid_plan(workouts=(row,)),
            context(),
        )
        self.assertIn("UNAPPROVED_WORKOUT_OPTION", report.codes())

    def test_solver_cannot_forge_catalog_load_semantics(self):
        approved = option_easy()
        forged = PlannedTrainingWorkout(
            workout_id="easy-forged",
            local_date=date(2026, 10, 6),
            recipe_id=approved.recipe_id,
            dose_option_id=approved.dose_option_id,
            obligation_contributions=(direct("easy-distance", "run_easy_distance"),),
            components=approved.components,
            load_dimensions=(
                dim("mechanical_leg", LoadDimensionLevel.LOW),
                dim("cardiovascular", LoadDimensionLevel.LOW),
            ),
            quantitative_load=approved.quantitative_load,
            source_refs=("solver:forged",),
        )
        report = validate_plan_content(
            valid_plan(workouts=(forged,)),
            context(),
        )
        self.assertIn("CATALOG_SEMANTICS_MISMATCH", report.codes())

    def test_unknown_obligation_reference_is_rejected(self):
        easy = option_easy()
        row = workout_from_option(
            "easy-x",
            date(2026, 10, 6),
            easy,
            direct("invented-obligation", "run_easy_distance"),
        )
        report = validate_plan_content(valid_plan(workouts=(row,)), context())
        self.assertIn("UNKNOWN_OBLIGATION", report.codes())

    def test_direct_credit_requires_obligation_capability(self):
        hybrid_option = option_easy(capabilities=("run_easy_distance", "run_threshold"))
        row = workout_from_option(
            "easy-x",
            date(2026, 10, 6),
            hybrid_option,
            direct("easy-distance", "run_threshold"),
        )
        report = validate_plan_content(
            valid_plan(workouts=(row,)),
            context(catalog=(hybrid_option, option_threshold(), option_mtb())),
        )
        self.assertIn("DIRECT_CONTRIBUTION_CAPABILITY_MISMATCH", report.codes())

    def test_direct_credit_requires_recipe_family_membership(self):
        alternate = option_easy(recipe_id="run_easy_alt", dose_id="run-easy-alt-75")
        row = workout_from_option(
            "easy-alt",
            date(2026, 10, 6),
            alternate,
            direct("easy-distance", "run_easy_distance"),
        )
        report = validate_plan_content(
            valid_plan(workouts=(row,)),
            context(catalog=(alternate, option_threshold(), option_mtb())),
        )
        self.assertIn("DIRECT_RECIPE_OUTSIDE_OBLIGATION_FAMILY", report.codes())

    def test_exact_approved_partial_credit_passes(self):
        mtb = option_mtb()
        row = workout_from_option(
            "mtb-1",
            date(2026, 10, 7),
            mtb,
            partial("easy-distance", "mtb_aerobic", 1, 2),
        )
        report = validate_plan_content(
            valid_plan(workouts=(row,)),
            context(),
        )
        self.assertTrue(report.valid, report.issues)

    def test_wrong_partial_credit_is_rejected(self):
        mtb = option_mtb()
        row = workout_from_option(
            "mtb-1",
            date(2026, 10, 7),
            mtb,
            partial("easy-distance", "mtb_aerobic", 1, 3),
        )
        report = validate_plan_content(valid_plan(workouts=(row,)), context())
        self.assertIn("PARTIAL_COVERAGE_CREDIT_MISMATCH", report.codes())

    def test_observed_plus_planned_credit_cannot_exceed_obligation_max(self):
        easy = option_easy()
        rows = (
            workout_from_option(
                "easy-1",
                date(2026, 10, 6),
                easy,
                direct("easy-distance", "run_easy_distance"),
            ),
            workout_from_option(
                "easy-2",
                date(2026, 10, 9),
                easy,
                direct("easy-distance", "run_easy_distance"),
            ),
        )
        observed = ObservedObligationCredit(
            local_date=AFFECTED_FROM,
            contribution=direct("easy-distance", "run_easy_distance"),
            source_refs=("activity:1",),
        )
        report = validate_plan_content(
            valid_plan(workouts=rows),
            context(observed_credits=(observed,)),
        )
        self.assertIn("OBLIGATION_MAX_EXCEEDED", report.codes())

    def test_observed_credit_outside_obligation_window_is_rejected(self):
        observed = ObservedObligationCredit(
            local_date=date(2026, 10, 4),
            contribution=direct("easy-distance", "run_easy_distance"),
            source_refs=("activity:before-window",),
        )
        report = validate_plan_content(
            valid_plan(),
            context(observed_credits=(observed,)),
        )
        self.assertIn("OBSERVED_CREDIT_OUTSIDE_OBLIGATION_WINDOW", report.codes())

    def test_rolling_aggregate_load_includes_observed_fixed_and_planned(self):
        observed = ObservedLoadSample(
            local_date=date(2026, 10, 4),
            load=load(
                "global",
                "training_duration",
                "duration",
                "minutes",
                100,
                100,
            ),
            source_refs=("activity:load",),
        )
        report = validate_plan_content(
            valid_plan(),
            context(observed_load=(observed,)),
        )
        # 100 observed + 120 fixed upper bound + 75 easy + 50 threshold = 345 > 300.
        self.assertIn("AGGREGATE_LOAD_EXCEEDED", report.codes())

    def test_plan_window_cannot_escape_strategy_revision(self):
        plan = valid_plan(affected_until=date(2026, 11, 2), workouts=())
        report = validate_plan_content(
            plan,
            context(strategy_value=strategy(valid_until=date(2026, 11, 1))),
        )
        self.assertIn("PLAN_OUTSIDE_STRATEGY_WINDOW", report.codes())


if __name__ == "__main__":
    unittest.main()
