#!/usr/bin/env python3
"""Black-box tests for the first complete Planning Engine v1 solver slice."""

from __future__ import annotations

import sys
import unittest
from datetime import date

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.planning.content import plan_content_hash  # noqa: E402
from training_core.planning.models import (  # noqa: E402
    AggregateLoadEnvelope,
    ApprovedWorkoutOption,
    CoverageRule,
    DailyAvailability,
    EligibilityKind,
    FixedLoadCommitment,
    LoadBound,
    LoadCompatibilityPolicy,
    LoadCompatibilityRule,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    OptionEligibility,
    PlanningObligation,
    SameDayOrderRule,
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


START = date(2026, 10, 5)
END = date(2026, 10, 11)


def dim(name, level):
    return LoadDimensionExposure(
        dimension=name,
        level=level,
        provenance_refs=("catalog:test",),
    )


def duration(minutes):
    return LoadEstimate(
        scope="global",
        subject="training_duration",
        metric="duration",
        unit="minutes",
        min_value=minutes,
        max_value=minutes,
        provenance_refs=("catalog:test",),
    )


def component(discipline):
    return (WorkoutComponentIntent(discipline=discipline, order=1),)


def option(
    recipe,
    dose,
    capability,
    discipline,
    *,
    dimensions,
    minutes=60,
    planning_priority=100,
):
    return ApprovedWorkoutOption(
        recipe_id=recipe,
        dose_option_id=dose,
        capabilities=(capability,),
        components=component(discipline),
        load_dimensions=tuple(dimensions),
        quantitative_load=(duration(minutes),),
        source_refs=("catalog:test",),
        development_character=recipe,
        planning_priority=planning_priority,
    )


def obligation(
    oid,
    capability,
    recipe,
    *,
    priority=1,
    minimum=1,
    maximum=1,
    partial=(),
):
    return PlanningObligation(
        obligation_id=oid,
        capability=capability,
        role="primary",
        priority_tier=priority,
        min_exposures=minimum,
        max_exposures=maximum,
        recipe_family=(recipe,),
        valid_from=START,
        valid_until=END,
        source_refs=("strategy:test",),
        progression_axes=("exposure_count",),
        partial_coverage=tuple(partial),
    )


def strategy(obligations, *, max_minutes=1000):
    return StrategyRevision(
        revision_id="strategy-test",
        goal_set_hash="goal-test",
        valid_from=START,
        valid_until=END,
        obligations=tuple(obligations),
        load_envelope=AggregateLoadEnvelope(
            envelope_id="load-test",
            bounds=(
                LoadBound(
                    bound_id="duration-7d",
                    scope="global",
                    subject="training_duration",
                    metric="duration",
                    unit="minutes",
                    window_days=7,
                    max_value=max_minutes,
                    provenance_refs=("athlete:established",),
                ),
            ),
            unknown_policy=UnknownAggregatePolicy.BLOCK_INCREASE,
            established_baseline_ref="athlete:established",
            source_refs=("strategy:test",),
        ),
        source_refs=("strategy:test",),
        accepted_by="user_review",
    )


def eligibility(options):
    return tuple(
        OptionEligibility(
            recipe_id=item.recipe_id,
            dose_option_id=item.dose_option_id,
            capability=capability,
            kind=EligibilityKind.HOLD,
            source_refs=("athlete:eligible",),
        )
        for item in options
        for capability in item.capabilities
    )


def policy(*rules):
    return LoadCompatibilityPolicy(
        policy_id="compat-test",
        rules=tuple(rules),
        source_refs=("policy:test",),
    )


def objective_policy(*, preferred_days=5, doubles=DoubleSessionPreference.SOMETIMES):
    return ObjectivePolicy(
        schedule=SchedulePreferences(
            preferred_active_days=preferred_days,
            min_active_days=0,
            max_active_days=7,
            double_sessions=doubles,
        )
    )


def context(
    obligations,
    options,
    *,
    fixed=(),
    compatibility=None,
    availability=(),
    max_minutes=1000,
    eligibility_values=None,
):
    return PlanValidationContext(
        source_revision="source-1",
        history_from=date(2026, 9, 29),
        history_through=date(2026, 10, 4),
        future_context_through=date(2026, 10, 14),
        strategy=strategy(obligations, max_minutes=max_minutes),
        catalog_options=tuple(options),
        option_eligibility=tuple(
            eligibility(options)
            if eligibility_values is None
            else eligibility_values
        ),
        fixed_commitments=tuple(fixed),
        compatibility_policy=compatibility or policy(),
        availability=tuple(availability),
    )


def solve(ctx, *, preferred_days=5, doubles=DoubleSessionPreference.SOMETIMES):
    return solve_planning_window(
        PlanningSolveRequest(
            affected_from=START,
            affected_until=END,
            validation_context=ctx,
            objective_policy=objective_policy(
                preferred_days=preferred_days,
                doubles=doubles,
            ),
        )
    )


def only_day_available(day):
    return tuple(
        DailyAvailability(
            local_date=current,
            available=current == day,
            source_refs=("user:availability",),
        )
        for current in (
            date(2026, 10, 5),
            date(2026, 10, 6),
            date(2026, 10, 7),
            date(2026, 10, 8),
            date(2026, 10, 9),
            date(2026, 10, 10),
            date(2026, 10, 11),
        )
    )


class PlanningSolverV1Tests(unittest.TestCase):
    def test_solver_chooses_canonical_earliest_equivalent_valid_plan(self):
        easy = option(
            "run_easy_distance",
            "easy-60",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
        )
        result = solve(
            context(
                (obligation("easy", "run_easy_distance", "run_easy_distance"),),
                (easy,),
            )
        )
        self.assertFalse(result.blocked)
        self.assertEqual(len(result.plan.workouts), 1)
        self.assertEqual(result.plan.workouts[0].local_date, START)
        self.assertEqual(
            result.authority_state.plan_content_hash,
            plan_content_hash(result.plan),
        )

    def test_fixed_load_and_generic_spacing_move_quality_without_enduro_special_case(self):
        threshold = option(
            "run_threshold",
            "threshold-32",
            "run_threshold",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.HIGH),),
            minutes=50,
        )
        fixed = FixedLoadCommitment(
            commitment_id="external-load",
            local_date=START,
            label="Fast extern belastning",
            load_dimensions=(dim("mechanical_leg", LoadDimensionLevel.HIGH),),
            source_refs=("user:fixed",),
            quantitative_load=(duration(90),),
        )
        compat = policy(
            LoadCompatibilityRule(
                rule_id="high-mechanical-before-high-cardio",
                first_dimension="mechanical_leg",
                first_min_level=LoadDimensionLevel.HIGH,
                second_dimension="cardiovascular",
                second_min_level=LoadDimensionLevel.HIGH,
                min_calendar_separation_days=2,
                same_day_order=SameDayOrderRule.FORBIDDEN,
                source_refs=("policy:test",),
            )
        )
        result = solve(
            context(
                (obligation("threshold", "run_threshold", "run_threshold"),),
                (threshold,),
                fixed=(fixed,),
                compatibility=compat,
            )
        )
        self.assertFalse(result.blocked)
        self.assertEqual(result.plan.workouts[0].local_date, date(2026, 10, 7))
        self.assertGreater(result.trace.rejected_candidates, 0)

    def test_directional_recovery_window_can_differ_by_order(self):
        threshold = option(
            "run_threshold",
            "threshold-32",
            "run_threshold",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.HIGH),),
            minutes=50,
        )
        fixed = FixedLoadCommitment(
            commitment_id="mechanical-fixed",
            local_date=START,
            label="Fast mekanisk belastning",
            load_dimensions=(dim("mechanical_leg", LoadDimensionLevel.HIGH),),
            source_refs=("user:fixed",),
            quantitative_load=(duration(60),),
        )
        compat = policy(
            LoadCompatibilityRule(
                rule_id="asymmetric-mechanical-cardio",
                first_dimension="mechanical_leg",
                first_min_level=LoadDimensionLevel.HIGH,
                second_dimension="cardiovascular",
                second_min_level=LoadDimensionLevel.HIGH,
                min_calendar_separation_days=1,
                min_first_to_second_days=3,
                min_second_to_first_days=1,
                same_day_order=SameDayOrderRule.FORBIDDEN,
                source_refs=("policy:test",),
            )
        )
        result = solve(
            context(
                (obligation("threshold", "run_threshold", "run_threshold"),),
                (threshold,),
                fixed=(fixed,),
                compatibility=compat,
            )
        )
        self.assertFalse(result.blocked)
        self.assertEqual(result.plan.workouts[0].local_date, date(2026, 10, 8))

    def test_reverse_direction_uses_its_own_shorter_window(self):
        threshold = option(
            "run_threshold",
            "threshold-32",
            "run_threshold",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.HIGH),),
            minutes=50,
        )
        sunday = date(2026, 10, 11)
        saturday = date(2026, 10, 10)
        fixed = FixedLoadCommitment(
            commitment_id="mechanical-fixed-sunday",
            local_date=sunday,
            label="Fast mekanisk belastning",
            load_dimensions=(dim("mechanical_leg", LoadDimensionLevel.HIGH),),
            source_refs=("user:fixed",),
            quantitative_load=(duration(60),),
        )
        compat = policy(
            LoadCompatibilityRule(
                rule_id="asymmetric-mechanical-cardio",
                first_dimension="mechanical_leg",
                first_min_level=LoadDimensionLevel.HIGH,
                second_dimension="cardiovascular",
                second_min_level=LoadDimensionLevel.HIGH,
                min_calendar_separation_days=1,
                min_first_to_second_days=3,
                min_second_to_first_days=1,
                same_day_order=SameDayOrderRule.FORBIDDEN,
                source_refs=("policy:test",),
            )
        )
        availability = tuple(
            DailyAvailability(
                local_date=current_day,
                available=current_day in {saturday, sunday},
                source_refs=("user:availability",),
            )
            for current_day in (
                date(2026, 10, 5),
                date(2026, 10, 6),
                date(2026, 10, 7),
                date(2026, 10, 8),
                date(2026, 10, 9),
                saturday,
                sunday,
            )
        )
        result = solve(
            context(
                (obligation("threshold", "run_threshold", "run_threshold"),),
                (threshold,),
                fixed=(fixed,),
                compatibility=compat,
                availability=availability,
            )
        )
        self.assertFalse(result.blocked)
        self.assertEqual(result.plan.workouts[0].local_date, saturday)

    def test_preferred_active_days_cannot_create_filler(self):
        easy = option(
            "run_easy_distance",
            "easy-60",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
        )
        result = solve(
            context(
                (
                    obligation(
                        "easy",
                        "run_easy_distance",
                        "run_easy_distance",
                        minimum=1,
                        maximum=2,
                    ),
                ),
                (easy,),
            ),
            preferred_days=7,
        )
        self.assertFalse(result.blocked)
        self.assertEqual(len(result.plan.workouts), 1)

    def test_two_independent_workouts_can_share_one_available_day(self):
        easy = option(
            "run_easy_distance",
            "easy-60",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
        )
        swim = option(
            "swim_aerobic",
            "swim-3000",
            "swim_aerobic",
            "swim",
            dimensions=(dim("upper_body", LoadDimensionLevel.MODERATE),),
        )
        target = date(2026, 10, 8)
        result = solve(
            context(
                (
                    obligation("easy", "run_easy_distance", "run_easy_distance"),
                    obligation("swim", "swim_aerobic", "swim_aerobic"),
                ),
                (easy, swim),
                availability=only_day_available(target),
            ),
            preferred_days=1,
            doubles=DoubleSessionPreference.ALLOW,
        )
        self.assertFalse(result.blocked)
        self.assertEqual(len(result.plan.workouts), 2)
        self.assertEqual({item.local_date for item in result.plan.workouts}, {target})
        self.assertEqual(len({item.workout_id for item in result.plan.workouts}), 2)

    def test_directional_same_day_rule_gets_explicit_abstract_order(self):
        quality = option(
            "quality",
            "quality-1",
            "quality_cap",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.HIGH),),
        )
        strength = option(
            "strength",
            "strength-1",
            "strength_cap",
            "strength",
            dimensions=(dim("mechanical_leg", LoadDimensionLevel.HIGH),),
        )
        compat = policy(
            LoadCompatibilityRule(
                rule_id="quality-before-strength",
                first_dimension="cardiovascular",
                first_min_level=LoadDimensionLevel.HIGH,
                second_dimension="mechanical_leg",
                second_min_level=LoadDimensionLevel.HIGH,
                min_calendar_separation_days=0,
                same_day_order=SameDayOrderRule.FIRST_BEFORE_SECOND,
                source_refs=("policy:test",),
            )
        )
        target = date(2026, 10, 8)
        result = solve(
            context(
                (
                    obligation("quality-o", "quality_cap", "quality"),
                    obligation("strength-o", "strength_cap", "strength"),
                ),
                (quality, strength),
                compatibility=compat,
                availability=only_day_available(target),
            ),
            preferred_days=1,
            doubles=DoubleSessionPreference.ALLOW,
        )
        self.assertFalse(result.blocked)
        by_recipe = {item.recipe_id: item for item in result.plan.workouts}
        self.assertLess(
            by_recipe["quality"].within_day_order,
            by_recipe["strength"].within_day_order,
        )

    def test_identical_recipe_can_exist_twice_on_same_day_when_strategy_requires_two_exposures(self):
        easy = option(
            "run_easy_distance",
            "easy-60",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
        )
        target = date(2026, 10, 8)
        result = solve(
            context(
                (
                    obligation(
                        "easy",
                        "run_easy_distance",
                        "run_easy_distance",
                        minimum=2,
                        maximum=2,
                    ),
                ),
                (easy,),
                availability=only_day_available(target),
            ),
            preferred_days=1,
            doubles=DoubleSessionPreference.ALLOW,
        )
        self.assertFalse(result.blocked)
        self.assertEqual(len(result.plan.workouts), 2)
        self.assertEqual({item.local_date for item in result.plan.workouts}, {target})
        self.assertEqual(
            {(item.recipe_id, item.dose_option_id) for item in result.plan.workouts},
            {("run_easy_distance", "easy-60")},
        )
        self.assertEqual(len({item.workout_id for item in result.plan.workouts}), 2)

    def test_partial_credit_can_require_two_distinct_exposures(self):
        mtb = option(
            "mtb_aerobic",
            "mtb-60",
            "mtb_aerobic",
            "bike",
            dimensions=(dim("mechanical_leg", LoadDimensionLevel.MODERATE),),
        )
        direct_easy = option(
            "run_easy_distance",
            "easy-60",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
        )
        easy = obligation(
            "easy",
            "run_easy_distance",
            "run_easy_distance",
            minimum=1,
            maximum=1,
            partial=(CoverageRule("mtb_aerobic", 1, 2),),
        )
        mtb_only_eligibility = tuple(
            item
            for item in eligibility((mtb, direct_easy))
            if item.recipe_id == "mtb_aerobic"
        )
        result = solve(
            context(
                (easy,),
                (mtb, direct_easy),
                eligibility_values=mtb_only_eligibility,
            ),
            preferred_days=2,
        )
        self.assertFalse(result.blocked)
        self.assertEqual(len(result.plan.workouts), 2)
        self.assertEqual(
            {item.recipe_id for item in result.plan.workouts},
            {"mtb_aerobic"},
        )

    def test_explicit_catalog_priority_breaks_otherwise_equal_choice(self):
        preferred = option(
            "easy_preferred",
            "easy-60-a",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
            planning_priority=10,
        )
        alternate = option(
            "easy_alternate",
            "easy-60-b",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
            planning_priority=20,
        )
        obligation_value = PlanningObligation(
            obligation_id="easy",
            capability="run_easy_distance",
            role="primary",
            priority_tier=1,
            min_exposures=1,
            max_exposures=1,
            recipe_family=("easy_preferred", "easy_alternate"),
            valid_from=START,
            valid_until=END,
            source_refs=("strategy:test",),
            progression_axes=("exposure_count",),
        )
        result = solve(context((obligation_value,), (alternate, preferred)))
        self.assertFalse(result.blocked)
        self.assertEqual(result.plan.workouts[0].recipe_id, "easy_preferred")

    def test_catalog_input_order_does_not_change_semantic_result(self):
        easy = option(
            "run_easy_distance",
            "easy-60",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
        )
        swim = option(
            "swim_aerobic",
            "swim-3000",
            "swim_aerobic",
            "swim",
            dimensions=(dim("upper_body", LoadDimensionLevel.MODERATE),),
        )
        obligations = (
            obligation("easy", "run_easy_distance", "run_easy_distance"),
            obligation("swim", "swim_aerobic", "swim_aerobic"),
        )
        first = solve(context(obligations, (easy, swim)))
        second = solve(context(obligations, (swim, easy)))
        self.assertFalse(first.blocked)
        self.assertFalse(second.blocked)
        self.assertEqual(plan_content_hash(first.plan), plan_content_hash(second.plan))
        self.assertEqual(
            first.trace.semantic_input_hash,
            second.trace.semantic_input_hash,
        )

    def test_semantic_input_hash_changes_when_availability_changes(self):
        easy = option(
            "run_easy_distance",
            "easy-60",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
        )
        obligations = (
            obligation("easy", "run_easy_distance", "run_easy_distance"),
        )
        open_result = solve(context(obligations, (easy,)))
        constrained_result = solve(
            context(
                obligations,
                (easy,),
                availability=only_day_available(date(2026, 10, 8)),
            )
        )
        self.assertNotEqual(
            open_result.trace.semantic_input_hash,
            constrained_result.trace.semantic_input_hash,
        )

    def test_unavoidable_fixed_conflict_blocks_instead_of_publishing_invalid_plan(self):
        dummy = option(
            "run_easy_distance",
            "easy-60",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
        )
        first = FixedLoadCommitment(
            commitment_id="fixed-a",
            local_date=START,
            label="A",
            load_dimensions=(dim("mechanical_leg", LoadDimensionLevel.HIGH),),
            source_refs=("user:a",),
            quantitative_load=(duration(60),),
        )
        second = FixedLoadCommitment(
            commitment_id="fixed-b",
            local_date=START,
            label="B",
            load_dimensions=(dim("cardiovascular", LoadDimensionLevel.HIGH),),
            source_refs=("user:b",),
            quantitative_load=(duration(60),),
        )
        compat = policy(
            LoadCompatibilityRule(
                rule_id="fixed-conflict",
                first_dimension="mechanical_leg",
                first_min_level=LoadDimensionLevel.HIGH,
                second_dimension="cardiovascular",
                second_min_level=LoadDimensionLevel.HIGH,
                min_calendar_separation_days=1,
                same_day_order=SameDayOrderRule.FORBIDDEN,
                source_refs=("policy:test",),
            )
        )
        result = solve(
            context(
                (obligation("easy", "run_easy_distance", "run_easy_distance"),),
                (dummy,),
                fixed=(first, second),
                compatibility=compat,
            )
        )
        self.assertTrue(result.blocked)
        self.assertIsNone(result.plan)
        self.assertIn("NO_VALID_PLAN", result.authority_state.blocked_reason_codes)
        self.assertIn(
            "LOAD_COMPATIBILITY_GAP_VIOLATION",
            result.authority_state.blocked_reason_codes,
        )

    def test_aggregate_load_gate_can_force_unmet_soft_obligation_without_invalid_commit(self):
        easy = option(
            "run_easy_distance",
            "easy-60",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
            minutes=60,
        )
        result = solve(
            context(
                (obligation("easy", "run_easy_distance", "run_easy_distance"),),
                (easy,),
                max_minutes=0,
            )
        )
        self.assertFalse(result.blocked)
        self.assertEqual(result.plan.workouts, ())
        self.assertGreater(
            result.objective_vector.required_deficit_by_tier[0],
            0,
        )
        self.assertGreater(result.trace.rejected_candidates, 0)


if __name__ == "__main__":
    unittest.main()
