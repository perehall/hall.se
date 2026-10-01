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
    FixedLoadCommitment,
    LoadEstimate,
    ObservedLoadSample,
    ObservedObligationCredit,
    PlanContent,
    PlanningContractError,
    PlanningObligation,
    StrategyRevision,
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
    strategy: StrategyRevision
    catalog_options: tuple[ApprovedWorkoutOption, ...]
    fixed_commitments: tuple[FixedLoadCommitment, ...]
    observed_obligation_credits: tuple[ObservedObligationCredit, ...] = ()
    observed_load_samples: tuple[ObservedLoadSample, ...] = ()

    def __post_init__(self) -> None:
        revision = str(self.source_revision or "").strip()
        if not revision:
            raise PlanningContractError("validation source_revision must be non-empty")
        object.__setattr__(self, "source_revision", revision)

        options = tuple(self.catalog_options)
        keys = [item.option_key for item in options]
        if len(set(keys)) != len(keys):
            raise PlanningContractError("validation catalog contains duplicate recipe/dose option")
        object.__setattr__(self, "catalog_options", options)

        commitments = tuple(self.fixed_commitments)
        ids = [item.commitment_id for item in commitments]
        if len(set(ids)) != len(ids):
            raise PlanningContractError("validation context contains duplicate fixed commitment")
        object.__setattr__(self, "fixed_commitments", commitments)
        object.__setattr__(
            self,
            "observed_obligation_credits",
            tuple(self.observed_obligation_credits),
        )
        object.__setattr__(
            self,
            "observed_load_samples",
            tuple(self.observed_load_samples),
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
    dated_loads: list[tuple[date, LoadEstimate, str]] = []

    for sample in context.observed_load_samples:
        dated_loads.append((sample.local_date, sample.load, "observed"))

    for workout in plan.workouts:
        for load in workout.quantitative_load:
            dated_loads.append((workout.local_date, load, workout.workout_id))

    for commitment in plan.fixed_commitments:
        for load in commitment.quantitative_load:
            dated_loads.append(
                (commitment.local_date, load, commitment.commitment_id)
            )

    for bound in context.strategy.load_envelope.bounds:
        worst_total = None
        worst_day = None
        end = plan.affected_from
        while end <= plan.affected_until:
            start = end - timedelta(days=bound.window_days - 1)
            total = sum(
                float(load.max_value)
                for local_date, load, _ in dated_loads
                if start <= local_date <= end and _matching_load(load, bound)
            )
            if worst_total is None or total > worst_total:
                worst_total = total
                worst_day = end
            end += timedelta(days=1)

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
    _validate_fixed_commitments(plan, context, issues)
    _validate_catalog_and_contributions(plan, context, issues)
    _validate_obligation_maxima(plan, context, issues)
    _validate_aggregate_load(plan, context, issues)
    return ValidationReport(tuple(issues))
