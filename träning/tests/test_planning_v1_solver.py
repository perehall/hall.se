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
from training_core.planning.candidate_generation import (  # noqa: E402
    CandidateGenerationLimits,
    generate_candidate_atoms,
)
from training_core.planning.models import (  # noqa: E402
    AggregateLoadEnvelope,
    ApprovedWorkoutOption,
    ContributionKind,
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
    ObligationContribution,
    ObservedLoadExposure,
    ObservedObligationCredit,
    OptionEligibility,
    PlanContent,
    PlannedTrainingWorkout,
    PlanningObligation,
    PlanningContractError,
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
from training_core.planning.plan_changes import (  # noqa: E402
    PlanChangeKind,
    UserPlanChange,
    compile_plan_change,
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
    placement=(),
    observed_credits=(),
    observed_exposures=(),
    closed=(),
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
        placement_constraints=tuple(placement),
        availability=tuple(availability),
        observed_obligation_credits=tuple(observed_credits),
        observed_load_exposures=tuple(observed_exposures),
        closed_dates=tuple(closed),
    )


def solve(
    ctx,
    *,
    preferred_days=5,
    doubles=DoubleSessionPreference.SOMETIMES,
    previous_plan=None,
    generation_limits=None,
):
    return solve_planning_window(
        PlanningSolveRequest(
            affected_from=START,
            affected_until=END,
            validation_context=ctx,
            objective_policy=objective_policy(
                preferred_days=preferred_days,
                doubles=doubles,
            ),
            previous_plan=previous_plan,
            generation_limits=(
                generation_limits
                if generation_limits is not None
                else CandidateGenerationLimits()
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
        self.assertTrue(result.trace.search_complete)
        self.assertTrue(result.trace.optimality_proven)
        self.assertEqual(result.trace.final_validation_codes, ())
        self.assertIn("load_bound:duration-7d", result.trace.hard_constraint_refs)
        self.assertEqual(len(result.trace.workout_decisions), 1)
        decision = result.trace.workout_decisions[0]
        self.assertEqual(decision.obligation_ids, ("easy",))
        self.assertEqual(decision.recipe_id, "run_easy_distance")
        self.assertEqual(decision.stability_change, "added")
        self.assertGreater(len(decision.alternative_comparisons), 0)
        self.assertTrue(
            all(
                item.comparison.first_deciding_objective
                == "canonical_tie_break"
                for item in decision.alternative_comparisons
            )
        )

    def test_trace_names_stability_objective_that_defeats_earlier_calendar_choice(self):
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
        target = date(2026, 10, 8)
        previous = solve(
            context(
                obligations,
                (easy,),
                availability=only_day_available(target),
            )
        )
        self.assertFalse(previous.blocked)
        self.assertEqual(previous.plan.workouts[0].local_date, target)

        replanned = solve(
            context(obligations, (easy,)),
            previous_plan=previous.plan,
        )
        self.assertFalse(replanned.blocked)
        self.assertEqual(replanned.plan.workouts[0].local_date, target)

        decision = replanned.trace.workout_decisions[0]
        earlier = next(
            item
            for item in decision.alternative_comparisons
            if item.local_date == START.isoformat()
        )
        self.assertEqual(
            earlier.comparison.first_deciding_objective,
            "stability_date_moves",
        )
        self.assertEqual(earlier.comparison.selected_value, "0")
        self.assertEqual(earlier.comparison.alternative_value, "1")

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

    def test_user_move_is_solved_as_absolute_placement_constraints(self):
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
        base_context = context(obligations, (easy,))
        base = solve(base_context)
        self.assertFalse(base.blocked)
        self.assertEqual(base.plan.workouts[0].local_date, START)

        target = date(2026, 10, 8)
        change = UserPlanChange(
            request_id="move-1",
            kind=PlanChangeKind.MOVE,
            base_plan_hash=plan_content_hash(base.plan),
            target_workout_id=base.plan.workouts[0].workout_id,
            target_date=target,
            source_refs=("user:test",),
        )
        placement = compile_plan_change(change, base.plan)
        replanned = solve(
            context(obligations, (easy,), placement=placement),
            previous_plan=base.plan,
        )
        self.assertFalse(replanned.blocked)
        self.assertEqual(len(replanned.plan.workouts), 1)
        self.assertEqual(replanned.plan.workouts[0].local_date, target)
        self.assertIn(
            "user:move-1:move-to",
            replanned.plan.workouts[0].constraint_ids,
        )
        self.assertEqual(
            tuple(change.kind for change in replanned.trace.plan_changes),
            ("moved",),
        )
        self.assertEqual(
            replanned.trace.workout_decisions[0].stability_change,
            "moved",
        )
        self.assertIn(
            target.isoformat(),
            {
                replanned.trace.workout_decisions[0].local_date,
                *replanned.trace.workout_decisions[0].alternative_dates,
            },
        )

    def test_multi_capability_workout_cannot_bypass_missing_dose_eligibility(self):
        combo = ApprovedWorkoutOption(
            recipe_id="swim_combo",
            dose_option_id="swim-combo-3600",
            capabilities=("swim_aerobic", "swim_technique"),
            components=(WorkoutComponentIntent("swim", 1),),
            load_dimensions=(
                dim("cardiovascular", LoadDimensionLevel.MODERATE),
                dim("technical", LoadDimensionLevel.MODERATE),
            ),
            quantitative_load=(duration(70),),
            source_refs=("catalog:test",),
            development_character="aerobic_technique",
        )
        obligations = (
            obligation(
                "technique",
                "swim_technique",
                "swim_combo",
            ),
        )
        technique_only = (
            OptionEligibility(
                recipe_id=combo.recipe_id,
                dose_option_id=combo.dose_option_id,
                capability="swim_technique",
                kind=EligibilityKind.HOLD,
                source_refs=("athlete:technique-only",),
            ),
        )
        result = solve(
            context(
                obligations,
                (combo,),
                eligibility_values=technique_only,
            )
        )
        self.assertFalse(result.blocked)
        self.assertEqual(result.plan.workouts, ())
        self.assertGreater(
            result.objective_vector.required_deficit_by_tier[0],
            0,
        )

        fully_eligible = technique_only + (
            OptionEligibility(
                recipe_id=combo.recipe_id,
                dose_option_id=combo.dose_option_id,
                capability="swim_aerobic",
                kind=EligibilityKind.ESTABLISH,
                source_refs=("athlete:aerobic-safe-dose",),
            ),
        )
        result = solve(
            context(
                obligations,
                (combo,),
                eligibility_values=fully_eligible,
            )
        )
        self.assertFalse(result.blocked)
        self.assertEqual(len(result.plan.workouts), 1)
        self.assertEqual(result.plan.workouts[0].recipe_id, "swim_combo")

    def test_user_remove_removes_placement_not_strategy_obligation(self):
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
        base = solve(context(obligations, (easy,)))
        change = UserPlanChange(
            request_id="remove-1",
            kind=PlanChangeKind.REMOVE,
            base_plan_hash=plan_content_hash(base.plan),
            target_workout_id=base.plan.workouts[0].workout_id,
            source_refs=("user:test",),
        )
        placement = compile_plan_change(change, base.plan)
        replanned = solve(
            context(obligations, (easy,), placement=placement),
            previous_plan=base.plan,
        )
        self.assertFalse(replanned.blocked)
        self.assertEqual(len(replanned.plan.workouts), 1)
        self.assertNotEqual(replanned.plan.workouts[0].local_date, START)
        self.assertEqual(
            replanned.objective_vector.required_deficit_by_tier[0],
            0,
        )

    def test_user_add_can_require_second_identical_workout_without_calendar_hack(self):
        easy = option(
            "run_easy_distance",
            "easy-60",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
        )
        obligations = (
            obligation(
                "easy",
                "run_easy_distance",
                "run_easy_distance",
                minimum=1,
                maximum=2,
            ),
        )
        base = solve(context(obligations, (easy,), max_minutes=180))
        target = base.plan.workouts[0].local_date
        change = UserPlanChange(
            request_id="add-1",
            kind=PlanChangeKind.ADD,
            base_plan_hash=plan_content_hash(base.plan),
            target_date=target,
            recipe_id="run_easy_distance",
            dose_option_id="easy-60",
            source_refs=("user:test",),
        )
        placement = compile_plan_change(change, base.plan)
        replanned = solve(
            context(
                obligations,
                (easy,),
                max_minutes=180,
                placement=placement,
            ),
            previous_plan=base.plan,
        )
        self.assertFalse(replanned.blocked)
        same_day = [
            item for item in replanned.plan.workouts
            if item.local_date == target
            and item.recipe_id == "run_easy_distance"
            and item.dose_option_id == "easy-60"
        ]
        self.assertEqual(len(same_day), 2)

    def test_user_add_that_breaks_hard_load_envelope_blocks(self):
        easy = option(
            "run_easy_distance",
            "easy-60",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
        )
        obligations = (
            obligation(
                "easy",
                "run_easy_distance",
                "run_easy_distance",
                minimum=1,
                maximum=2,
            ),
        )
        base = solve(context(obligations, (easy,), max_minutes=60))
        change = UserPlanChange(
            request_id="add-too-much",
            kind=PlanChangeKind.ADD,
            base_plan_hash=plan_content_hash(base.plan),
            target_date=base.plan.workouts[0].local_date,
            recipe_id="run_easy_distance",
            dose_option_id="easy-60",
            source_refs=("user:test",),
        )
        placement = compile_plan_change(change, base.plan)
        replanned = solve(
            context(
                obligations,
                (easy,),
                max_minutes=60,
                placement=placement,
            ),
            previous_plan=base.plan,
        )
        self.assertTrue(replanned.blocked)
        self.assertIsNone(replanned.plan)
        self.assertIn(
            "AGGREGATE_LOAD_EXCEEDED",
            replanned.authority_state.blocked_reason_codes,
        )

    def test_stale_user_change_is_rejected_before_solving(self):
        easy = option(
            "run_easy_distance",
            "easy-60",
            "run_easy_distance",
            "run",
            dimensions=(dim("cardiovascular", LoadDimensionLevel.LOW),),
        )
        base = solve(
            context(
                (obligation("easy", "run_easy_distance", "run_easy_distance"),),
                (easy,),
            )
        )
        change = UserPlanChange(
            request_id="stale-remove",
            kind=PlanChangeKind.REMOVE,
            base_plan_hash="not-the-current-plan",
            target_workout_id=base.plan.workouts[0].workout_id,
            source_refs=("user:test",),
        )
        with self.assertRaises(PlanningContractError):
            compile_plan_change(change, base.plan)

    def test_spontaneous_quality_never_allows_stale_future_quality_to_resurrect(self):
        threshold = option(
            "run_threshold",
            "threshold-32",
            "run_threshold",
            "run",
            dimensions=(
                dim("cardiovascular", LoadDimensionLevel.HIGH),
                dim("run_impact", LoadDimensionLevel.MODERATE),
            ),
            minutes=50,
        )
        stale_hill = option(
            "run_hill_quality",
            "hill-24",
            "run_hill_quality",
            "run",
            dimensions=(
                dim("neuromuscular", LoadDimensionLevel.HIGH),
                dim("run_impact", LoadDimensionLevel.HIGH),
            ),
            minutes=45,
        )
        easy = option(
            "run_easy_distance",
            "easy-75",
            "run_easy_distance",
            "run",
            dimensions=(
                dim("cardiovascular", LoadDimensionLevel.LOW),
                dim("run_impact", LoadDimensionLevel.MODERATE),
            ),
            minutes=75,
        )
        swim = option(
            "swim_aerobic",
            "swim-3200",
            "swim_aerobic",
            "swim",
            dimensions=(dim("upper_body", LoadDimensionLevel.MODERATE),),
            minutes=65,
        )

        obligations = (
            obligation("threshold", "run_threshold", "run_threshold"),
            obligation("easy", "run_easy_distance", "run_easy_distance"),
            obligation(
                "swim",
                "swim_aerobic",
                "swim_aerobic",
                minimum=2,
                maximum=2,
            ),
        )

        observed_threshold = ObservedObligationCredit(
            local_date=date(2026, 10, 6),
            contribution=ObligationContribution(
                obligation_id="threshold",
                source_capability="run_threshold",
                kind=ContributionKind.DIRECT,
                credit_numerator=1,
                credit_denominator=1,
            ),
            source_refs=("activity:spontaneous-threshold",),
        )
        observed_swim = ObservedObligationCredit(
            local_date=date(2026, 10, 5),
            contribution=ObligationContribution(
                obligation_id="swim",
                source_capability="swim_aerobic",
                kind=ContributionKind.DIRECT,
                credit_numerator=1,
                credit_denominator=1,
            ),
            source_refs=("activity:completed-swim",),
        )
        observed_load = ObservedLoadExposure(
            exposure_id="spontaneous-threshold-load",
            local_date=date(2026, 10, 6),
            load_dimensions=threshold.load_dimensions,
            quantitative_load=threshold.quantitative_load,
            source_refs=("activity:spontaneous-threshold",),
        )

        next_fixed = FixedLoadCommitment(
            commitment_id="next-fixed-load",
            local_date=date(2026, 10, 12),
            label="Nästa fasta externa belastning",
            load_dimensions=(dim("mechanical_leg", LoadDimensionLevel.HIGH),),
            quantitative_load=(duration(90),),
            source_refs=("user:fixed",),
        )
        compat = policy(
            LoadCompatibilityRule(
                rule_id="run-before-fixed-mechanical",
                first_dimension="run_impact",
                first_min_level=LoadDimensionLevel.MODERATE,
                second_dimension="mechanical_leg",
                second_min_level=LoadDimensionLevel.HIGH,
                min_calendar_separation_days=2,
                same_day_order=SameDayOrderRule.FORBIDDEN,
                source_refs=("policy:test",),
            )
        )

        old_hill_workout = PlannedTrainingWorkout(
            workout_id="old-hill-friday",
            local_date=date(2026, 10, 9),
            recipe_id=stale_hill.recipe_id,
            dose_option_id=stale_hill.dose_option_id,
            obligation_contributions=(
                ObligationContribution(
                    obligation_id="threshold",
                    source_capability="run_threshold",
                    kind=ContributionKind.DIRECT,
                    credit_numerator=1,
                    credit_denominator=1,
                ),
            ),
            components=stale_hill.components,
            load_dimensions=stale_hill.load_dimensions,
            quantitative_load=stale_hill.quantitative_load,
            source_refs=("previous-plan",),
        )
        previous = PlanContent(
            source_revision="old-source",
            strategy_revision_id="strategy-test",
            affected_from=START,
            affected_until=END,
            workouts=(old_hill_workout,),
            fixed_commitments=(),
        )

        result = solve(
            context(
                obligations,
                (threshold, stale_hill, easy, swim),
                fixed=(next_fixed,),
                compatibility=compat,
                observed_credits=(observed_threshold, observed_swim),
                observed_exposures=(observed_load,),
                closed=(date(2026, 10, 5), date(2026, 10, 6)),
            ),
            previous_plan=previous,
        )

        self.assertFalse(result.blocked)
        recipes = [item.recipe_id for item in result.plan.workouts]
        self.assertEqual(sorted(recipes), ["run_easy_distance", "swim_aerobic"])
        self.assertNotIn("run_threshold", recipes)
        self.assertNotIn("run_hill_quality", recipes)
        run_day = next(
            item.local_date
            for item in result.plan.workouts
            if item.recipe_id == "run_easy_distance"
        )
        self.assertNotEqual(run_day, END)
        self.assertIn(
            "removed",
            tuple(change.kind for change in result.trace.plan_changes),
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

    def test_atom_generation_respects_hard_daily_duration_capacity(self):
        swim = option(
            "swim_aerobic",
            "swim-60",
            "swim_aerobic",
            "swim",
            dimensions=(dim("upper_body", LoadDimensionLevel.MODERATE),),
            minutes=60,
        )
        obligations = (
            obligation(
                "swim",
                "swim_aerobic",
                "swim_aerobic",
                minimum=2,
                maximum=2,
            ),
        )
        availability = tuple(
            DailyAvailability(
                local_date=current,
                available=True,
                max_duration_minutes=90,
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
        atoms = generate_candidate_atoms(
            context(
                obligations,
                (swim,),
                availability=availability,
            ),
            START,
            END,
        )
        by_day = {}
        for atom in atoms:
            by_day.setdefault(atom.local_date, []).append(atom)
        self.assertEqual(set(by_day), set(current.local_date for current in availability))
        self.assertTrue(all(len(items) == 1 for items in by_day.values()))
        self.assertTrue(all(items[0].instance_index == 1 for items in by_day.values()))

    def test_search_limit_fails_closed_instead_of_returning_approximate_plan(self):
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
        result = solve(
            context(
                (
                    obligation("easy", "run_easy_distance", "run_easy_distance"),
                    obligation("swim", "swim_aerobic", "swim_aerobic"),
                ),
                (easy, swim),
            ),
            generation_limits=CandidateGenerationLimits(
                max_search_states=1,
                max_terminal_selections=100,
                max_plan_variants=100,
            ),
        )
        self.assertTrue(result.blocked)
        self.assertIsNone(result.plan)
        self.assertIsNone(result.objective_vector)
        self.assertIn(
            "SEARCH_SPACE_LIMIT_EXCEEDED",
            result.authority_state.blocked_reason_codes,
        )
        self.assertIsNone(result.trace.selected_plan_hash)
        self.assertFalse(result.trace.search_complete)
        self.assertFalse(result.trace.optimality_proven)

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
