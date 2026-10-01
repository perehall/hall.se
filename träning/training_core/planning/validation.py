"""Final hard-invariant validation for Planning Engine v1.

This module is intentionally independent from candidate generation and plan
selection. The future solver is not trusted: the exact PlanContent proposed for
commit must pass this validator as a separate final gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction

from .models import (
    ApprovedWorkoutOption,
    ContributionKind,
    DailyAvailability,
    FixedLoadCommitment,
    LoadCompatibilityPolicy,
    LoadDimensionLevel,
    LoadEstimate,
    ObservedLoadExposure,
    ObservedObligationCredit,
    OptionEligibility,
    PlanContent,
    PlanningContractError,
    PlanningObligation,
    SameDayOrderRule,
    StrategyRevision,
    WorkoutPlacementConstraint,
)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues

    def codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)


@dataclass(frozen=True)
class PlanValidationContext:
    source_revision: str
    history_from: date
    history_through: date
    future_context_through: date
    strategy: StrategyRevision
    catalog_options: tuple[ApprovedWorkoutOption, ...]
    option_eligibility: tuple[OptionEligibility, ...]
    fixed_commitments: tuple[FixedLoadCommitment, ...]
    compatibility_policy: LoadCompatibilityPolicy
    placement_constraints: tuple[WorkoutPlacementConstraint, ...] = ()
    availability: tuple[DailyAvailability, ...] = ()
    closed_dates: tuple[date, ...] = ()
    observed_obligation_credits: tuple[ObservedObligationCredit, ...] = ()
    observed_load_exposures: tuple[ObservedLoadExposure, ...] = ()

    def __post_init__(self) -> None:
        revision = str(self.source_revision or "").strip()
        if not revision:
            raise PlanningContractError("validation source_revision must be non-empty")
        object.__setattr__(self, "source_revision", revision)

        if not isinstance(self.history_from, date) or not isinstance(self.history_through, date):
            raise PlanningContractError("validation history coverage must use dates")
        if self.history_through < self.history_from:
            raise PlanningContractError("validation history_through cannot precede history_from")
        if not isinstance(self.future_context_through, date):
            raise PlanningContractError("validation future_context_through must be a date")

        options = tuple(self.catalog_options)
        keys = [item.option_key for item in options]
        if len(set(keys)) != len(keys):
            raise PlanningContractError("validation catalog contains duplicate recipe/dose option")
        object.__setattr__(self, "catalog_options", options)

        catalog_recipe_ids = {item.recipe_id for item in options}
        missing_strategy_recipes = sorted(
            {
                recipe_id
                for obligation in self.strategy.obligations
                for recipe_id in obligation.recipe_family
                if recipe_id not in catalog_recipe_ids
            }
        )
        if missing_strategy_recipes:
            raise PlanningContractError(
                "StrategyRevision references recipe families missing from approved catalog: "
                + ", ".join(missing_strategy_recipes)
            )

        eligibility = tuple(self.option_eligibility)
        eligibility_keys = [
            (item.recipe_id, item.dose_option_id, item.capability)
            for item in eligibility
        ]
        if len(set(eligibility_keys)) != len(eligibility_keys):
            raise PlanningContractError("validation context contains duplicate option eligibility")
        catalog_keys = set(keys)
        if any(item.option_key not in catalog_keys for item in eligibility):
            raise PlanningContractError(
                "option eligibility references recipe/dose outside approved catalog"
            )
        catalog_by_key = {item.option_key: item for item in options}
        for item in eligibility:
            option = catalog_by_key[item.option_key]
            if item.capability not in option.capabilities:
                raise PlanningContractError(
                    "option eligibility claims capability not provided by approved option: "
                    f"{item.recipe_id}/{item.dose_option_id}/{item.capability}"
                )
        object.__setattr__(self, "option_eligibility", eligibility)

        commitments = tuple(self.fixed_commitments)
        ids = [item.commitment_id for item in commitments]
        if len(set(ids)) != len(ids):
            raise PlanningContractError("validation context contains duplicate fixed commitment")
        known_orders = [
            (item.local_date, item.within_day_order)
            for item in commitments
            if item.within_day_order is not None
        ]
        if len(set(known_orders)) != len(known_orders):
            raise PlanningContractError(
                "fixed commitments contain duplicate known within-day order"
            )
        object.__setattr__(self, "fixed_commitments", commitments)

        placement = tuple(self.placement_constraints)
        constraint_ids = [item.constraint_id for item in placement]
        if len(set(constraint_ids)) != len(constraint_ids):
            raise PlanningContractError(
                "validation context contains duplicate placement constraint id"
            )
        semantic_keys = [
            (
                item.local_date,
                item.recipe_id,
                item.dose_option_id,
                item.obligation_ids,
            )
            for item in placement
        ]
        if len(set(semantic_keys)) != len(semantic_keys):
            raise PlanningContractError(
                "placement constraints must be compiled to one absolute count constraint per semantic placement"
            )
        for index, first in enumerate(placement):
            for second in placement[index + 1 :]:
                if (
                    first.local_date == second.local_date
                    and first.option_key == second.option_key
                    and (
                        not first.obligation_ids
                        or not second.obligation_ids
                        or first.obligation_ids == second.obligation_ids
                    )
                ):
                    raise PlanningContractError(
                        "overlapping placement constraints must be compiled into one absolute count constraint"
                    )
        for item in placement:
            if item.option_key not in catalog_keys:
                raise PlanningContractError(
                    "placement constraint references recipe/dose outside approved catalog"
                )
            if not self.strategy.valid_from <= item.local_date <= self.strategy.valid_until:
                raise PlanningContractError(
                    "placement constraint lies outside StrategyRevision validity"
                )
            unknown_obligations = set(item.obligation_ids) - {
                obligation.obligation_id
                for obligation in self.strategy.obligations
            }
            if unknown_obligations:
                raise PlanningContractError(
                    "placement constraint references unknown obligations: "
                    + ", ".join(sorted(unknown_obligations))
                )
        object.__setattr__(self, "placement_constraints", placement)

        object.__setattr__(
            self,
            "observed_obligation_credits",
            tuple(self.observed_obligation_credits),
        )
        object.__setattr__(
            self,
            "observed_load_exposures",
            tuple(self.observed_load_exposures),
        )

        availability = tuple(self.availability)
        dates = [item.local_date for item in availability]
        if len(set(dates)) != len(dates):
            raise PlanningContractError("validation context contains duplicate daily availability")
        object.__setattr__(self, "availability", availability)

        closed = tuple(self.closed_dates)
        if len(set(closed)) != len(closed):
            raise PlanningContractError("validation context contains duplicate closed date")
        object.__setattr__(self, "closed_dates", closed)

        if not isinstance(self.compatibility_policy, LoadCompatibilityPolicy):
            raise PlanningContractError(
                "compatibility_policy must be LoadCompatibilityPolicy"
            )


def _component_semantics(items) -> tuple[tuple[str, int], ...]:
    return tuple((item.discipline, item.order) for item in items)


def _dimension_semantics(items) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted((item.dimension, item.level.value) for item in items)
    )


def _estimate_semantics(items) -> tuple[tuple[str, str, str, str, float, float], ...]:
    return tuple(
        sorted(
            (
                item.scope,
                item.subject,
                item.metric,
                item.unit,
                float(item.min_value),
                float(item.max_value),
            )
            for item in items
        )
    )


def _fixed_semantics(item: FixedLoadCommitment) -> tuple:
    return (
        item.commitment_id,
        item.local_date,
        item.within_day_order,
        _dimension_semantics(item.load_dimensions),
        _estimate_semantics(item.quantitative_load),
    )


def _option_matches_workout(option: ApprovedWorkoutOption, workout) -> bool:
    return (
        _component_semantics(option.components)
        == _component_semantics(workout.components)
        and _dimension_semantics(option.load_dimensions)
        == _dimension_semantics(workout.load_dimensions)
        and _estimate_semantics(option.quantitative_load)
        == _estimate_semantics(workout.quantitative_load)
    )


def _credit(contribution) -> Fraction:
    return Fraction(
        contribution.credit_numerator,
        contribution.credit_denominator,
    )


def _obligations_by_id(strategy: StrategyRevision) -> dict[str, PlanningObligation]:
    return {item.obligation_id: item for item in strategy.obligations}


def _catalog_by_key(
    options: tuple[ApprovedWorkoutOption, ...],
) -> dict[tuple[str, str], ApprovedWorkoutOption]:
    return {item.option_key: item for item in options}


def _validate_header(
    plan: PlanContent,
    context: PlanValidationContext,
    issues: list[ValidationIssue],
) -> None:
    if plan.source_revision != context.source_revision:
        issues.append(
            ValidationIssue(
                "STALE_SOURCE_REVISION",
                "PlanContent was solved from a different canonical source revision.",
                (plan.source_revision, context.source_revision),
            )
        )

    if plan.strategy_revision_id != context.strategy.revision_id:
        issues.append(
            ValidationIssue(
                "STRATEGY_REVISION_MISMATCH",
                "PlanContent references a different StrategyRevision.",
                (plan.strategy_revision_id, context.strategy.revision_id),
            )
        )

    if (
        plan.affected_from < context.strategy.valid_from
        or plan.affected_until > context.strategy.valid_until
    ):
        issues.append(
            ValidationIssue(
                "PLAN_OUTSIDE_STRATEGY_WINDOW",
                "Affected PlanContent window lies outside the StrategyRevision validity window.",
                (
                    plan.affected_from.isoformat(),
                    plan.affected_until.isoformat(),
                    context.strategy.valid_from.isoformat(),
                    context.strategy.valid_until.isoformat(),
                ),
            )
        )


def _validate_history_coverage(
    plan: PlanContent,
    context: PlanValidationContext,
    issues: list[ValidationIssue],
) -> None:
    max_window = max(
        (bound.window_days for bound in context.strategy.load_envelope.bounds),
        default=1,
    )
    max_compat_gap = max(
        (
            rule.max_separation_days
            for rule in context.compatibility_policy.rules
        ),
        default=0,
    )
    load_required_from = plan.affected_from - timedelta(days=max_window - 1)
    compatibility_required_from = plan.affected_from - timedelta(
        days=max(0, max_compat_gap - 1)
    )
    obligation_required_from = min(
        (
            obligation.valid_from
            for obligation in context.strategy.obligations
            if obligation.valid_from < plan.affected_from
        ),
        default=plan.affected_from,
    )
    required_from = min(
        load_required_from,
        compatibility_required_from,
        obligation_required_from,
    )
    required_through = plan.affected_from - timedelta(days=1)

    if required_through < required_from:
        return

    if (
        context.history_from > required_from
        or context.history_through < required_through
    ):
        issues.append(
            ValidationIssue(
                "INSUFFICIENT_HISTORY_COVERAGE",
                "Canonical observed history does not fully cover the horizon required by hard validation.",
                (
                    required_from.isoformat(),
                    required_through.isoformat(),
                    context.history_from.isoformat(),
                    context.history_through.isoformat(),
                ),
            )
        )


def _validate_future_context(
    plan: PlanContent,
    context: PlanValidationContext,
    issues: list[ValidationIssue],
) -> None:
    max_gap = max(
        (
            rule.max_separation_days
            for rule in context.compatibility_policy.rules
        ),
        default=0,
    )
    required_through = plan.affected_until + timedelta(
        days=max(0, max_gap - 1)
    )
    if context.future_context_through < required_through:
        issues.append(
            ValidationIssue(
                "INSUFFICIENT_FUTURE_CONTEXT",
                "Future fixed-load context does not cover the horizon required by compatibility rules.",
                (
                    required_through.isoformat(),
                    context.future_context_through.isoformat(),
                ),
            )
        )


def _validate_fixed_commitments(
    plan: PlanContent,
    context: PlanValidationContext,
    issues: list[ValidationIssue],
) -> None:
    expected = {
        item.commitment_id: item
        for item in context.fixed_commitments
        if plan.affected_from <= item.local_date <= plan.affected_until
    }
    actual = {item.commitment_id: item for item in plan.fixed_commitments}

    for commitment_id in sorted(set(expected) - set(actual)):
        issues.append(
            ValidationIssue(
                "FIXED_COMMITMENT_MISSING",
                "A canonical fixed commitment is missing from PlanContent.",
                (commitment_id,),
            )
        )

    for commitment_id in sorted(set(actual) - set(expected)):
        issues.append(
            ValidationIssue(
                "FIXED_COMMITMENT_UNEXPECTED",
                "PlanContent contains a fixed commitment not present in canonical input.",
                (commitment_id,),
            )
        )

    for commitment_id in sorted(set(expected) & set(actual)):
        if _fixed_semantics(expected[commitment_id]) != _fixed_semantics(actual[commitment_id]):
            issues.append(
                ValidationIssue(
                    "FIXED_COMMITMENT_CHANGED",
                    "PlanContent altered the semantics of a canonical fixed commitment.",
                    (commitment_id,),
                )
            )


def _validate_catalog_and_contributions(
    plan: PlanContent,
    context: PlanValidationContext,
    issues: list[ValidationIssue],
) -> None:
    obligations = _obligations_by_id(context.strategy)
    catalog = _catalog_by_key(context.catalog_options)

    for workout in plan.workouts:
        option = catalog.get((workout.recipe_id, workout.dose_option_id))
        if option is None:
            issues.append(
                ValidationIssue(
                    "UNAPPROVED_WORKOUT_OPTION",
                    "Workout recipe/dose is not present in the approved planning catalog.",
                    (workout.workout_id, workout.recipe_id, workout.dose_option_id),
                )
            )
            continue

        if not _option_matches_workout(option, workout):
            issues.append(
                ValidationIssue(
                    "CATALOG_SEMANTICS_MISMATCH",
                    "Workout load/components differ from its approved catalog option.",
                    (workout.workout_id, workout.recipe_id, workout.dose_option_id),
                )
            )

        for contribution in workout.obligation_contributions:
            obligation = obligations.get(contribution.obligation_id)
            if obligation is None:
                issues.append(
                    ValidationIssue(
                        "UNKNOWN_OBLIGATION",
                        "Workout references an obligation not present in StrategyRevision.",
                        (workout.workout_id, contribution.obligation_id),
                    )
                )
                continue

            if not obligation.active_on(workout.local_date):
                issues.append(
                    ValidationIssue(
                        "OBLIGATION_OUTSIDE_WINDOW",
                        "Workout contributes to an obligation outside its validity window.",
                        (
                            workout.workout_id,
                            contribution.obligation_id,
                            workout.local_date.isoformat(),
                        ),
                    )
                )
                continue

            if contribution.source_capability not in option.capabilities:
                issues.append(
                    ValidationIssue(
                        "CONTRIBUTION_CAPABILITY_NOT_IN_RECIPE",
                        "Obligation contribution claims a capability not provided by the approved recipe.",
                        (
                            workout.workout_id,
                            contribution.obligation_id,
                            contribution.source_capability,
                        ),
                    )
                )
                continue

            if contribution.kind is ContributionKind.DIRECT:
                if contribution.source_capability != obligation.capability:
                    issues.append(
                        ValidationIssue(
                            "DIRECT_CONTRIBUTION_CAPABILITY_MISMATCH",
                            "Direct contribution must use the obligation's own capability.",
                            (workout.workout_id, contribution.obligation_id),
                        )
                    )
                if workout.recipe_id not in obligation.recipe_family:
                    issues.append(
                        ValidationIssue(
                            "DIRECT_RECIPE_OUTSIDE_OBLIGATION_FAMILY",
                            "Direct contribution uses a recipe outside the obligation's approved family.",
                            (
                                workout.workout_id,
                                contribution.obligation_id,
                                workout.recipe_id,
                            ),
                        )
                    )
                if _credit(contribution) != Fraction(1, 1):
                    issues.append(
                        ValidationIssue(
                            "DIRECT_CONTRIBUTION_NOT_FULL",
                            "Direct contribution must equal one full exposure.",
                            (workout.workout_id, contribution.obligation_id),
                        )
                    )
            else:
                rule = next(
                    (
                        item
                        for item in obligation.partial_coverage
                        if item.source_capability == contribution.source_capability
                    ),
                    None,
                )
                if rule is None:
                    issues.append(
                        ValidationIssue(
                            "PARTIAL_COVERAGE_NOT_APPROVED",
                            "No partial-coverage rule exists for this source capability.",
                            (
                                workout.workout_id,
                                contribution.obligation_id,
                                contribution.source_capability,
                            ),
                        )
                    )
                elif _credit(contribution) != Fraction(
                    rule.credit_numerator,
                    rule.credit_denominator,
                ):
                    issues.append(
                        ValidationIssue(
                            "PARTIAL_COVERAGE_CREDIT_MISMATCH",
                            "Partial contribution does not match the exact approved coverage rule.",
                            (
                                workout.workout_id,
                                contribution.obligation_id,
                                contribution.source_capability,
                            ),
                        )
                    )


def _validate_option_eligibility(
    plan: PlanContent,
    context: PlanValidationContext,
    issues: list[ValidationIssue],
) -> None:
    allowed = {
        (item.recipe_id, item.dose_option_id, item.capability)
        for item in context.option_eligibility
    }
    catalog = _catalog_by_key(context.catalog_options)
    for workout in plan.workouts:
        if not workout.obligation_contributions:
            option = catalog.get((workout.recipe_id, workout.dose_option_id))
            eligible_caps = {
                capability
                for recipe_id, dose_id, capability in allowed
                if recipe_id == workout.recipe_id
                and dose_id == workout.dose_option_id
            }
            if option is None or not eligible_caps.intersection(option.capabilities):
                issues.append(
                    ValidationIssue(
                        "WORKOUT_OPTION_NOT_ELIGIBLE",
                        "User-constrained workout is not athlete-eligible for any capability supplied by the approved option.",
                        (
                            workout.workout_id,
                            workout.recipe_id,
                            workout.dose_option_id,
                        ),
                    )
                )
            continue

        for contribution in workout.obligation_contributions:
            key = (
                workout.recipe_id,
                workout.dose_option_id,
                contribution.source_capability,
            )
            if key not in allowed:
                issues.append(
                    ValidationIssue(
                        "WORKOUT_OPTION_NOT_ELIGIBLE",
                        "Selected recipe/dose is not athlete-eligible for the claimed source capability.",
                        (
                            workout.workout_id,
                            workout.recipe_id,
                            workout.dose_option_id,
                            contribution.source_capability,
                        ),
                    )
                )


def _duration_minutes(items: tuple[LoadEstimate, ...]) -> float | None:
    matches = [
        item
        for item in items
        if item.scope == "global"
        and item.subject == "training_duration"
        and item.metric == "duration"
        and item.unit == "minutes"
    ]
    if not matches:
        return None
    return sum(float(item.max_value) for item in matches)


def _validate_availability(
    plan: PlanContent,
    context: PlanValidationContext,
    issues: list[ValidationIssue],
) -> None:
    availability = {item.local_date: item for item in context.availability}
    closed = set(context.closed_dates)

    for workout in plan.workouts:
        if workout.local_date in closed:
            issues.append(
                ValidationIssue(
                    "WORKOUT_ON_CLOSED_DATE",
                    "Planner placed mutable training on a closed/immutable date.",
                    (workout.workout_id, workout.local_date.isoformat()),
                )
            )

    for commitment in plan.fixed_commitments:
        if commitment.local_date in closed:
            issues.append(
                ValidationIssue(
                    "FIXED_COMMITMENT_ON_CLOSED_DATE",
                    "PlanContent contains a future fixed commitment on a closed date.",
                    (commitment.commitment_id, commitment.local_date.isoformat()),
                )
            )

    for day, rule in availability.items():
        workouts = [item for item in plan.workouts if item.local_date == day]
        commitments = [
            item for item in plan.fixed_commitments if item.local_date == day
        ]
        sessions = len(workouts) + len(commitments)

        if not rule.available and sessions:
            issues.append(
                ValidationIssue(
                    "TRAINING_ON_UNAVAILABLE_DATE",
                    "Training exists on a date declared unavailable.",
                    (day.isoformat(), str(sessions)),
                )
            )
            continue

        if rule.max_sessions is not None and sessions > rule.max_sessions:
            issues.append(
                ValidationIssue(
                    "AVAILABILITY_SESSION_LIMIT_EXCEEDED",
                    "Planned/fixed session count exceeds declared daily availability.",
                    (day.isoformat(), str(sessions), str(rule.max_sessions)),
                )
            )

        if rule.max_duration_minutes is not None and sessions:
            durations: list[float] = []
            unknown_ids: list[str] = []
            for item in workouts:
                duration = _duration_minutes(item.quantitative_load)
                if duration is None:
                    unknown_ids.append(item.workout_id)
                else:
                    durations.append(duration)
            for item in commitments:
                duration = _duration_minutes(item.quantitative_load)
                if duration is None:
                    unknown_ids.append(item.commitment_id)
                else:
                    durations.append(duration)

            if unknown_ids:
                issues.append(
                    ValidationIssue(
                        "AVAILABILITY_DURATION_UNKNOWN",
                        "Daily duration limit cannot be proven because one or more sessions lack duration semantics.",
                        (day.isoformat(), *sorted(unknown_ids)),
                    )
                )
            elif sum(durations) > float(rule.max_duration_minutes) + 1e-9:
                issues.append(
                    ValidationIssue(
                        "AVAILABILITY_DURATION_EXCEEDED",
                        "Upper-bound session duration exceeds declared daily availability.",
                        (
                            day.isoformat(),
                            str(sum(durations)),
                            str(rule.max_duration_minutes),
                        ),
                    )
                )


_LEVEL_RANK = {
    LoadDimensionLevel.LOW: 1,
    LoadDimensionLevel.MODERATE: 2,
    LoadDimensionLevel.HIGH: 3,
    LoadDimensionLevel.UNKNOWN: 4,
}


def _dimension_at_least(exposure, dimension: str, minimum: LoadDimensionLevel) -> bool:
    match = next(
        (item for item in exposure["dimensions"] if item.dimension == dimension),
        None,
    )
    if match is None:
        return False
    return _LEVEL_RANK[match.level] >= _LEVEL_RANK[minimum]


def _compatibility_orientation(first, second, rule):
    if (
        _dimension_at_least(first, rule.first_dimension, rule.first_min_level)
        and _dimension_at_least(second, rule.second_dimension, rule.second_min_level)
    ):
        return first, second
    if (
        _dimension_at_least(second, rule.first_dimension, rule.first_min_level)
        and _dimension_at_least(first, rule.second_dimension, rule.second_min_level)
    ):
        return second, first
    return None


def _validate_load_compatibility(
    plan: PlanContent,
    context: PlanValidationContext,
    issues: list[ValidationIssue],
) -> None:
    exposures = []

    for item in context.observed_load_exposures:
        exposures.append(
            {
                "id": item.exposure_id,
                "date": item.local_date,
                "dimensions": item.load_dimensions,
                "order": item.within_day_order,
                "kind": "observed",
            }
        )

    for item in context.fixed_commitments:
        if item.local_date < plan.affected_from:
            continue
        if item.local_date > context.future_context_through:
            continue
        exposures.append(
            {
                "id": item.commitment_id,
                "date": item.local_date,
                "dimensions": item.load_dimensions,
                "order": item.within_day_order,
                "kind": "fixed",
            }
        )

    for item in plan.workouts:
        exposures.append(
            {
                "id": item.workout_id,
                "date": item.local_date,
                "dimensions": item.load_dimensions,
                "order": item.within_day_order,
                "kind": "planned",
            }
        )

    emitted: set[tuple[str, str, str]] = set()
    for index, first in enumerate(exposures):
        for second in exposures[index + 1 :]:
            # Purely historical pairs cannot be changed by this solve.
            if first["kind"] == "observed" and second["kind"] == "observed":
                continue

            day_gap = abs((first["date"] - second["date"]).days)
            for rule in context.compatibility_policy.rules:
                oriented = _compatibility_orientation(first, second, rule)
                if oriented is None:
                    continue
                first_role, second_role = oriented
                issue_key = (
                    rule.rule_id,
                    min(first["id"], second["id"]),
                    max(first["id"], second["id"]),
                )
                if issue_key in emitted:
                    continue

                if first_role["date"] < second_role["date"]:
                    required_gap = rule.first_to_second_days
                    direction = "first_to_second"
                elif second_role["date"] < first_role["date"]:
                    required_gap = rule.second_to_first_days
                    direction = "second_to_first"
                else:
                    # Same-day calendar separation is zero. The larger of the
                    # directional day gaps is conservative; an explicitly
                    # permitted same-day ordering only matters when both are 0.
                    required_gap = rule.max_separation_days
                    direction = "same_day"

                if day_gap < required_gap:
                    emitted.add(issue_key)
                    issues.append(
                        ValidationIssue(
                            "LOAD_COMPATIBILITY_GAP_VIOLATION",
                            "Two load exposures violate a generic directional separation rule.",
                            (
                                rule.rule_id,
                                first["id"],
                                second["id"],
                                direction,
                                str(day_gap),
                                str(required_gap),
                            ),
                        )
                    )
                    continue

                if day_gap != 0:
                    continue

                if rule.same_day_order is SameDayOrderRule.FORBIDDEN:
                    emitted.add(issue_key)
                    issues.append(
                        ValidationIssue(
                            "LOAD_COMPATIBILITY_SAME_DAY_FORBIDDEN",
                            "Two load exposures are not permitted on the same day.",
                            (rule.rule_id, first["id"], second["id"]),
                        )
                    )
                    continue

                if rule.same_day_order is SameDayOrderRule.ANY:
                    continue

                first_order = first_role["order"]
                second_order = second_role["order"]
                if first_order is None or second_order is None:
                    emitted.add(issue_key)
                    issues.append(
                        ValidationIssue(
                            "LOAD_COMPATIBILITY_ORDER_UNKNOWN",
                            "Same-day compatibility requires an order that is not known.",
                            (rule.rule_id, first["id"], second["id"]),
                        )
                    )
                    continue

                correct = (
                    first_order < second_order
                    if rule.same_day_order is SameDayOrderRule.FIRST_BEFORE_SECOND
                    else second_order < first_order
                )
                if not correct:
                    emitted.add(issue_key)
                    issues.append(
                        ValidationIssue(
                            "LOAD_COMPATIBILITY_ORDER_VIOLATION",
                            "Same-day load order violates the generic compatibility rule.",
                            (rule.rule_id, first["id"], second["id"]),
                        )
                    )


def _validate_obligation_maxima(
    plan: PlanContent,
    context: PlanValidationContext,
    issues: list[ValidationIssue],
) -> None:
    obligations = _obligations_by_id(context.strategy)
    totals = {key: Fraction(0, 1) for key in obligations}

    for observed in context.observed_obligation_credits:
        contribution = observed.contribution
        obligation = obligations.get(contribution.obligation_id)
        if obligation is None:
            issues.append(
                ValidationIssue(
                    "OBSERVED_CREDIT_UNKNOWN_OBLIGATION",
                    "Observed planning credit references an unknown obligation.",
                    (contribution.obligation_id,),
                )
            )
            continue
        if not obligation.active_on(observed.local_date):
            issues.append(
                ValidationIssue(
                    "OBSERVED_CREDIT_OUTSIDE_OBLIGATION_WINDOW",
                    "Observed planning credit lies outside the obligation validity window.",
                    (
                        contribution.obligation_id,
                        observed.local_date.isoformat(),
                    ),
                )
            )
            continue
        totals[contribution.obligation_id] += _credit(contribution)

    for workout in plan.workouts:
        for contribution in workout.obligation_contributions:
            if contribution.obligation_id in totals:
                totals[contribution.obligation_id] += _credit(contribution)

    for obligation_id, total in sorted(totals.items()):
        maximum = obligations[obligation_id].max_exposures
        if total > maximum:
            issues.append(
                ValidationIssue(
                    "OBLIGATION_MAX_EXCEEDED",
                    "Observed plus planned obligation credit exceeds the bounded maximum.",
                    (
                        obligation_id,
                        str(total),
                        str(maximum),
                    ),
                )
            )


def _validate_placement_constraints(
    plan: PlanContent,
    context: PlanValidationContext,
    issues: list[ValidationIssue],
) -> None:
    constraints = {
        item.constraint_id: item
        for item in context.placement_constraints
    }

    for workout in plan.workouts:
        for constraint_id in workout.constraint_ids:
            constraint = constraints.get(constraint_id)
            if constraint is None:
                issues.append(
                    ValidationIssue(
                        "UNKNOWN_PLACEMENT_CONSTRAINT",
                        "Workout references an unknown planning placement constraint.",
                        (workout.workout_id, constraint_id),
                    )
                )
                continue
            if not constraint.matches(workout):
                issues.append(
                    ValidationIssue(
                        "PLACEMENT_CONSTRAINT_ATTRIBUTION_MISMATCH",
                        "Workout claims a placement constraint whose semantic selector it does not satisfy.",
                        (workout.workout_id, constraint_id),
                    )
                )

    for constraint in context.placement_constraints:
        matches = [
            workout
            for workout in plan.workouts
            if constraint.matches(workout)
        ]
        count = len(matches)
        if count < constraint.min_occurrences:
            issues.append(
                ValidationIssue(
                    "PLACEMENT_MIN_UNSATISFIED",
                    "Resulting plan contains fewer matching workouts than the user planning constraint requires.",
                    (
                        constraint.constraint_id,
                        str(count),
                        str(constraint.min_occurrences),
                    ),
                )
            )
        if (
            constraint.max_occurrences is not None
            and count > constraint.max_occurrences
        ):
            issues.append(
                ValidationIssue(
                    "PLACEMENT_MAX_EXCEEDED",
                    "Resulting plan contains more matching workouts than the user planning constraint permits.",
                    (
                        constraint.constraint_id,
                        str(count),
                        str(constraint.max_occurrences),
                    ),
                )
            )

        if constraint.min_occurrences:
            attributed = sum(
                constraint.constraint_id in workout.constraint_ids
                for workout in matches
            )
            if attributed < constraint.min_occurrences:
                issues.append(
                    ValidationIssue(
                        "PLACEMENT_REQUIRED_PROVENANCE_MISSING",
                        "Required user-planning placement exists but is not explicitly attributed to its constraint.",
                        (
                            constraint.constraint_id,
                            str(attributed),
                            str(constraint.min_occurrences),
                        ),
                    )
                )


def _matching_load(load: LoadEstimate, bound) -> bool:
    return (
        load.scope == bound.scope
        and load.subject == bound.subject
        and load.metric == bound.metric
        and load.unit == bound.unit
    )


def _validate_aggregate_load(
    plan: PlanContent,
    context: PlanValidationContext,
    issues: list[ValidationIssue],
) -> None:
    dated_exposures: list[tuple[date, tuple[LoadEstimate, ...], str, str]] = []

    for exposure in context.observed_load_exposures:
        dated_exposures.append(
            (
                exposure.local_date,
                tuple(exposure.quantitative_load),
                exposure.exposure_id,
                "observed",
            )
        )

    for workout in plan.workouts:
        dated_exposures.append(
            (
                workout.local_date,
                tuple(workout.quantitative_load),
                workout.workout_id,
                "planned",
            )
        )

    for commitment in plan.fixed_commitments:
        dated_exposures.append(
            (
                commitment.local_date,
                tuple(commitment.quantitative_load),
                commitment.commitment_id,
                "fixed",
            )
        )

    envelope = context.strategy.load_envelope
    for bound in envelope.bounds:
        horizon_from = plan.affected_from - timedelta(days=bound.window_days - 1)
        relevant = [
            (local_date, loads, exposure_id, kind)
            for local_date, loads, exposure_id, kind in dated_exposures
            if horizon_from <= local_date <= plan.affected_until
        ]

        if bound.requires_complete_coverage:
            missing = tuple(
                sorted(
                    exposure_id
                    for _, loads, exposure_id, _ in relevant
                    if not any(_matching_load(load, bound) for load in loads)
                )
            )
            if missing and plan.workouts:
                if (
                    envelope.unknown_policy.value
                    == "hold_established_baseline"
                ):
                    code = "AGGREGATE_LOAD_BASELINE_HOLD_UNPROVEN"
                    message = (
                        "Aggregate load coverage is incomplete, so the established "
                        "baseline hold cannot be proven for a plan that adds mutable training."
                    )
                else:
                    code = "AGGREGATE_LOAD_UNKNOWN_BLOCKS_INCREASE"
                    message = (
                        "Aggregate load coverage is incomplete; automatic mutable "
                        "training is blocked rather than treating unknown load as zero."
                    )
                issues.append(
                    ValidationIssue(
                        code,
                        message,
                        (bound.bound_id, *missing),
                    )
                )
                # A numeric total from incomplete coverage is not trustworthy.
                continue

        worst_total = None
        worst_day = None
        end_day = plan.affected_from
        while end_day <= plan.affected_until:
            start_day = end_day - timedelta(days=bound.window_days - 1)
            total = sum(
                float(load.max_value)
                for local_date, loads, _, _ in dated_exposures
                if start_day <= local_date <= end_day
                for load in loads
                if _matching_load(load, bound)
            )
            if worst_total is None or total > worst_total:
                worst_total = total
                worst_day = end_day
            end_day += timedelta(days=1)

        if worst_total is not None and worst_total > float(bound.max_value) + 1e-9:
            issues.append(
                ValidationIssue(
                    "AGGREGATE_LOAD_EXCEEDED",
                    "Observed/fixed/planned load exceeds an aggregate load bound.",
                    (
                        bound.bound_id,
                        worst_day.isoformat() if worst_day else "",
                        str(worst_total),
                        str(bound.max_value),
                        bound.unit,
                    ),
                )
            )

def validate_plan_content(
    plan: PlanContent,
    context: PlanValidationContext,
) -> ValidationReport:
    """Validate the exact PlanContent proposed for authoritative commit."""

    issues: list[ValidationIssue] = []
    _validate_header(plan, context, issues)
    _validate_history_coverage(plan, context, issues)
    _validate_future_context(plan, context, issues)
    _validate_fixed_commitments(plan, context, issues)
    _validate_catalog_and_contributions(plan, context, issues)
    _validate_option_eligibility(plan, context, issues)
    _validate_availability(plan, context, issues)
    _validate_load_compatibility(plan, context, issues)
    _validate_obligation_maxima(plan, context, issues)
    _validate_placement_constraints(plan, context, issues)
    _validate_aggregate_load(plan, context, issues)
    return ValidationReport(tuple(issues))
