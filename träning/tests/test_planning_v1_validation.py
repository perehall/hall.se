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
    DailyAvailability,
    EligibilityKind,
    FixedLoadCommitment,
    LoadCompatibilityPolicy,
    LoadCompatibilityRule,
    LoadBound,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    ObligationContribution,
    ObservedCreditBasis,
    ObservedLoadExposure,
    ObservedObligationCredit,
    OptionEligibility,
    PlanContent,
    PlannedTrainingWorkout,
    PlanningContractError,
    PlanningObligation,
    PlanValidationContext,
    StrategyRevision,
    SameDayOrderRule,
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


def easy_obligation(
    *,
    max_exposures=2,
    accepted_observed_bases=(ObservedCreditBasis.CONFIRMED_STIMULUS,),
):
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
        accepted_observed_bases=accepted_observed_bases,
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


def compatibility_policy():
    return LoadCompatibilityPolicy(
        policy_id="compat-v1",
        rules=(
            LoadCompatibilityRule(
                rule_id="high-cardio-spacing",
                first_dimension="cardiovascular",
                first_min_level=LoadDimensionLevel.HIGH,
                second_dimension="cardiovascular",
                second_min_level=LoadDimensionLevel.HIGH,
                min_calendar_separation_days=2,
                same_day_order=SameDayOrderRule.FORBIDDEN,
                source_refs=("policy:test",),
            ),
            LoadCompatibilityRule(
                rule_id="high-mechanical-to-high-cardio",
                first_dimension="mechanical_leg",
                first_min_level=LoadDimensionLevel.HIGH,
                second_dimension="cardiovascular",
                second_min_level=LoadDimensionLevel.HIGH,
                min_calendar_separation_days=2,
                same_day_order=SameDayOrderRule.FORBIDDEN,
                source_refs=("policy:test",),
            ),
        ),
        source_refs=("policy:test",),
    )


def eligibility_for(options):
    return tuple(
        OptionEligibility(
            recipe_id=option.recipe_id,
            dose_option_id=option.dose_option_id,
            capability=capability,
            kind=EligibilityKind.HOLD,
            source_refs=("athlete_state:eligible",),
        )
        for option in options
        for capability in option.capabilities
    )


def context(
    *,
    strategy_value=None,
    catalog=None,
    fixed=None,
    eligibility=None,
    compatibility=None,
    availability=(),
    closed_dates=(),
    observed_credits=(),
    observed_exposures=(),
    source_revision="source-1",
    history_from=date(2026, 9, 29),
    history_through=date(2026, 10, 4),
    future_context_through=date(2026, 10, 12),
):
    catalog_values = tuple(catalog or (option_easy(), option_threshold(), option_mtb()))
    return PlanValidationContext(
        source_revision=source_revision,
        history_from=history_from,
        history_through=history_through,
        future_context_through=future_context_through,
        strategy=strategy_value or strategy(),
        catalog_options=catalog_values,
        option_eligibility=tuple(
            eligibility if eligibility is not None else eligibility_for(catalog_values)
        ),
        fixed_commitments=tuple(fixed if fixed is not None else (fixed_commitment(),)),
        compatibility_policy=compatibility or compatibility_policy(),
        availability=tuple(availability),
        closed_dates=tuple(closed_dates),
        observed_obligation_credits=tuple(observed_credits),
        observed_load_exposures=tuple(observed_exposures),
    )


class PlanningInputContractTests(unittest.TestCase):
    def test_strategy_recipe_family_must_exist_in_catalog(self):
        with self.assertRaises(PlanningContractError):
            context(catalog=(option_threshold(), option_mtb()))

    def test_option_eligibility_cannot_claim_missing_capability(self):
        options = (option_easy(), option_threshold(), option_mtb())
        invalid = (
            OptionEligibility(
                recipe_id="run_easy_distance",
                dose_option_id="run-easy-75",
                capability="run_threshold",
                kind=EligibilityKind.HOLD,
                source_refs=("athlete_state:bad",),
            ),
        )
        with self.assertRaises(PlanningContractError):
            context(catalog=options, eligibility=invalid)

    def test_fixed_commitments_cannot_share_known_order_on_same_day(self):
        first = fixed_commitment()
        second = FixedLoadCommitment(
            commitment_id="fixed-external-2",
            local_date=AFFECTED_FROM,
            label="Fast extern belastning 2",
            load_dimensions=(
                dim("mechanical_leg", LoadDimensionLevel.MODERATE),
            ),
            quantitative_load=(
                load("global", "training_duration", "duration", "minutes", 30),
            ),
            source_refs=("user:confirmed-2",),
            within_day_order=first.within_day_order or 1,
        )
        first_ordered = FixedLoadCommitment(
            commitment_id=first.commitment_id,
            local_date=first.local_date,
            label=first.label,
            load_dimensions=first.load_dimensions,
            quantitative_load=first.quantitative_load,
            source_refs=first.source_refs,
            within_day_order=1,
        )
        with self.assertRaises(PlanningContractError):
            context(fixed=(first_ordered, second))


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
            context(
                catalog=(
                    option_easy(),
                    alternate,
                    option_threshold(),
                    option_mtb(),
                )
            ),
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

    def test_structural_observed_credit_is_rejected_without_strategy_opt_in(self):
        observed = ObservedObligationCredit(
            local_date=AFFECTED_FROM,
            contribution=direct("easy-distance", "run_easy_distance"),
            source_refs=("intent-match:1",),
            basis=ObservedCreditBasis.STRUCTURAL_INTENT_MATCH,
        )
        report = validate_plan_content(
            valid_plan(),
            context(observed_credits=(observed,)),
        )
        self.assertIn(
            "OBSERVED_CREDIT_BASIS_NOT_ACCEPTED",
            report.codes(),
        )

    def test_structural_observed_credit_is_valid_when_strategy_explicitly_accepts_it(self):
        observed = ObservedObligationCredit(
            local_date=AFFECTED_FROM,
            contribution=direct("easy-distance", "run_easy_distance"),
            source_refs=("intent-match:1",),
            basis=ObservedCreditBasis.STRUCTURAL_INTENT_MATCH,
        )
        opted_in = StrategyRevision(
            revision_id="strategy-a",
            goal_set_hash="goalhash",
            valid_from=AFFECTED_FROM,
            valid_until=date(2026, 11, 1),
            obligations=(
                easy_obligation(
                    accepted_observed_bases=(
                        ObservedCreditBasis.CONFIRMED_STIMULUS,
                        ObservedCreditBasis.STRUCTURAL_INTENT_MATCH,
                    )
                ),
                threshold_obligation(),
            ),
            load_envelope=envelope(),
            source_refs=("goal:v1", "review:accepted"),
            accepted_by="user_review",
        )
        report = validate_plan_content(
            valid_plan(workouts=()),
            context(
                strategy_value=opted_in,
                observed_credits=(observed,),
            ),
        )
        self.assertNotIn(
            "OBSERVED_CREDIT_BASIS_NOT_ACCEPTED",
            report.codes(),
        )

    def test_observed_credit_must_match_obligation_contribution_semantics(self):
        observed = ObservedObligationCredit(
            local_date=AFFECTED_FROM,
            contribution=ObligationContribution(
                obligation_id="easy-distance",
                source_capability="mtb_aerobic",
                kind=ContributionKind.DIRECT,
                credit_numerator=1,
                credit_denominator=1,
            ),
            source_refs=("activity:bad-credit",),
        )
        report = validate_plan_content(
            valid_plan(),
            context(observed_credits=(observed,)),
        )
        self.assertIn(
            "OBSERVED_CREDIT_SEMANTICS_MISMATCH",
            report.codes(),
        )

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
        observed = ObservedLoadExposure(
            exposure_id="activity-load",
            local_date=date(2026, 10, 4),
            load_dimensions=(
                dim("cardiovascular", LoadDimensionLevel.LOW),
            ),
            quantitative_load=(
                load(
                    "global",
                    "training_duration",
                    "duration",
                    "minutes",
                    100,
                    100,
                ),
            ),
            source_refs=("activity:load",),
        )
        report = validate_plan_content(
            valid_plan(),
            context(observed_exposures=(observed,)),
        )
        # 100 observed + 120 fixed upper bound + 75 easy + 50 threshold = 345 > 300.
        self.assertIn("AGGREGATE_LOAD_EXCEEDED", report.codes())

    def test_unknown_required_aggregate_coverage_blocks_added_training(self):
        strict_envelope = AggregateLoadEnvelope(
            envelope_id="strict-duration",
            bounds=(
                LoadBound(
                    bound_id="duration-complete-7d",
                    scope="global",
                    subject="training_duration",
                    metric="duration",
                    unit="minutes",
                    window_days=7,
                    max_value=600,
                    provenance_refs=("strategy:explicit",),
                    requires_complete_coverage=True,
                ),
            ),
            unknown_policy=UnknownAggregatePolicy.BLOCK_INCREASE,
            established_baseline_ref="athlete:explicit-baseline",
            source_refs=("strategy:explicit",),
        )
        strict_strategy = StrategyRevision(
            revision_id="strategy-a",
            goal_set_hash="goalhash",
            valid_from=AFFECTED_FROM,
            valid_until=date(2026, 11, 1),
            obligations=(easy_obligation(), threshold_obligation()),
            load_envelope=strict_envelope,
            source_refs=("goal:v1", "review:accepted"),
            accepted_by="user_review",
        )
        unknown_observed = ObservedLoadExposure(
            exposure_id="activity-without-duration-semantics",
            local_date=date(2026, 10, 4),
            load_dimensions=(dim("mechanical_leg", LoadDimensionLevel.MODERATE),),
            quantitative_load=(),
            source_refs=("activity:unknown-load",),
        )
        report = validate_plan_content(
            valid_plan(),
            context(
                strategy_value=strict_strategy,
                observed_exposures=(unknown_observed,),
            ),
        )
        self.assertIn(
            "AGGREGATE_LOAD_UNKNOWN_BLOCKS_INCREASE",
            report.codes(),
        )

    def test_unknown_aggregate_coverage_allows_zero_new_mutable_training(self):
        strict_envelope = AggregateLoadEnvelope(
            envelope_id="strict-duration",
            bounds=(
                LoadBound(
                    bound_id="duration-complete-7d",
                    scope="global",
                    subject="training_duration",
                    metric="duration",
                    unit="minutes",
                    window_days=7,
                    max_value=600,
                    provenance_refs=("strategy:explicit",),
                    requires_complete_coverage=True,
                ),
            ),
            unknown_policy=UnknownAggregatePolicy.BLOCK_INCREASE,
            established_baseline_ref="athlete:explicit-baseline",
            source_refs=("strategy:explicit",),
        )
        strict_strategy = StrategyRevision(
            revision_id="strategy-a",
            goal_set_hash="goalhash",
            valid_from=AFFECTED_FROM,
            valid_until=date(2026, 11, 1),
            obligations=(easy_obligation(), threshold_obligation()),
            load_envelope=strict_envelope,
            source_refs=("goal:v1", "review:accepted"),
            accepted_by="user_review",
        )
        unknown_observed = ObservedLoadExposure(
            exposure_id="activity-without-duration-semantics",
            local_date=date(2026, 10, 4),
            load_dimensions=(dim("mechanical_leg", LoadDimensionLevel.MODERATE),),
            quantitative_load=(),
            source_refs=("activity:unknown-load",),
        )
        report = validate_plan_content(
            valid_plan(workouts=()),
            context(
                strategy_value=strict_strategy,
                observed_exposures=(unknown_observed,),
            ),
        )
        self.assertNotIn(
            "AGGREGATE_LOAD_UNKNOWN_BLOCKS_INCREASE",
            report.codes(),
        )

    def test_selected_option_must_be_athlete_eligible(self):
        report = validate_plan_content(
            valid_plan(),
            context(
                eligibility=(
                    OptionEligibility(
                        recipe_id="run_threshold",
                        dose_option_id="run-threshold-4x8",
                        capability="run_threshold",
                        kind=EligibilityKind.HOLD,
                        source_refs=("athlete_state:eligible",),
                    ),
                )
            ),
        )
        self.assertIn("WORKOUT_OPTION_NOT_ELIGIBLE", report.codes())

    def test_closed_date_cannot_receive_mutable_workout(self):
        report = validate_plan_content(
            valid_plan(),
            context(closed_dates=(date(2026, 10, 6),)),
        )
        self.assertIn("WORKOUT_ON_CLOSED_DATE", report.codes())

    def test_unavailable_date_rejects_training(self):
        report = validate_plan_content(
            valid_plan(),
            context(
                availability=(
                    DailyAvailability(
                        local_date=date(2026, 10, 6),
                        available=False,
                        source_refs=("user:availability",),
                    ),
                )
            ),
        )
        self.assertIn("TRAINING_ON_UNAVAILABLE_DATE", report.codes())

    def test_daily_session_limit_includes_fixed_and_planned_sessions(self):
        easy = option_easy()
        row = workout_from_option(
            "easy-on-fixed-day",
            AFFECTED_FROM,
            easy,
            direct("easy-distance", "run_easy_distance"),
        )
        report = validate_plan_content(
            valid_plan(workouts=(row,)),
            context(
                availability=(
                    DailyAvailability(
                        local_date=AFFECTED_FROM,
                        available=True,
                        max_sessions=1,
                        source_refs=("user:availability",),
                    ),
                )
            ),
        )
        self.assertIn("AVAILABILITY_SESSION_LIMIT_EXCEEDED", report.codes())

    def test_daily_duration_limit_uses_upper_bound_load(self):
        report = validate_plan_content(
            valid_plan(),
            context(
                availability=(
                    DailyAvailability(
                        local_date=AFFECTED_FROM,
                        available=True,
                        max_duration_minutes=100,
                        source_refs=("user:availability",),
                    ),
                )
            ),
        )
        # Fixed commitment is explicitly 60-120 min, so 100 min cannot be proven sufficient.
        self.assertIn("AVAILABILITY_DURATION_EXCEEDED", report.codes())

    def test_future_context_must_cover_cross_boundary_compatibility_horizon(self):
        report = validate_plan_content(
            valid_plan(),
            context(future_context_through=AFFECTED_UNTIL),
        )
        self.assertIn("INSUFFICIENT_FUTURE_CONTEXT", report.codes())

    def test_adjacent_high_cardio_exposures_violate_generic_spacing_rule(self):
        threshold = option_threshold()
        rows = (
            workout_from_option(
                "threshold-1",
                date(2026, 10, 8),
                threshold,
                direct("threshold", "run_threshold"),
            ),
            workout_from_option(
                "threshold-2",
                date(2026, 10, 9),
                threshold,
                direct("threshold", "run_threshold"),
            ),
        )
        report = validate_plan_content(
            valid_plan(workouts=rows),
            context(),
        )
        self.assertIn("LOAD_COMPATIBILITY_GAP_VIOLATION", report.codes())

    def test_cross_boundary_future_fixed_load_is_checked(self):
        threshold = option_threshold()
        row = workout_from_option(
            "threshold-sunday",
            AFFECTED_UNTIL,
            threshold,
            direct("threshold", "run_threshold"),
        )
        future_fixed = FixedLoadCommitment(
            commitment_id="future-high-mechanical",
            local_date=date(2026, 10, 12),
            label="Nästa periods fasta belastning",
            load_dimensions=(
                dim("mechanical_leg", LoadDimensionLevel.HIGH),
            ),
            quantitative_load=(
                load("global", "training_duration", "duration", "minutes", 60, 90),
            ),
            source_refs=("user:confirmed",),
        )
        report = validate_plan_content(
            valid_plan(workouts=(row,)),
            context(fixed=(fixed_commitment(), future_fixed)),
        )
        self.assertIn("LOAD_COMPATIBILITY_GAP_VIOLATION", report.codes())

    def test_same_day_order_rule_fails_closed_when_order_unknown(self):
        policy = LoadCompatibilityPolicy(
            policy_id="same-day-order",
            rules=(
                LoadCompatibilityRule(
                    rule_id="mechanical-before-cardio",
                    first_dimension="mechanical_leg",
                    first_min_level=LoadDimensionLevel.HIGH,
                    second_dimension="cardiovascular",
                    second_min_level=LoadDimensionLevel.HIGH,
                    min_calendar_separation_days=0,
                    same_day_order=SameDayOrderRule.FIRST_BEFORE_SECOND,
                    source_refs=("policy:test",),
                ),
            ),
            source_refs=("policy:test",),
        )
        threshold = option_threshold()
        row = workout_from_option(
            "threshold-same-day",
            AFFECTED_FROM,
            threshold,
            direct("threshold", "run_threshold"),
        )
        report = validate_plan_content(
            valid_plan(workouts=(row,)),
            context(compatibility=policy),
        )
        self.assertIn("LOAD_COMPATIBILITY_ORDER_UNKNOWN", report.codes())

    def test_plan_window_cannot_escape_strategy_revision(self):
        plan = valid_plan(affected_until=date(2026, 11, 2), workouts=())
        report = validate_plan_content(
            plan,
            context(strategy_value=strategy(valid_until=date(2026, 11, 1))),
        )
        self.assertIn("PLAN_OUTSIDE_STRATEGY_WINDOW", report.codes())


if __name__ == "__main__":
    unittest.main()
