"""Deterministic lexicographic objectives for Planning Engine v1.

Hard constraints are handled by validation.py. This module only ranks plans that
have already passed the hard-invariant gate. No weighted score is used: each
objective level is compared lexicographically in the normative order.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from itertools import combinations

from .models import (
    ApprovedWorkoutOption,
    FixedLoadCommitment,
    LoadDimensionLevel,
    ObservedLoadExposure,
    ObservedObligationCredit,
    PlanContent,
    PlanningContractError,
    StrategyRevision,
)


class DoubleSessionPreference(str, Enum):
    AVOID = "avoid"
    SOMETIMES = "sometimes"
    ALLOW = "allow"


class SpacingSubjectKind(str, Enum):
    CAPABILITY = "capability"
    LOAD_DIMENSION = "load_dimension"


@dataclass(frozen=True)
class SchedulePreferences:
    preferred_active_days: int
    min_active_days: int
    max_active_days: int
    double_sessions: DoubleSessionPreference

    def __post_init__(self) -> None:
        values = (
            self.preferred_active_days,
            self.min_active_days,
            self.max_active_days,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise PlanningContractError(
                "schedule active-day preferences must be non-negative integers"
            )
        if self.max_active_days < self.min_active_days:
            raise PlanningContractError(
                "schedule max_active_days cannot be lower than min_active_days"
            )
        if not self.min_active_days <= self.preferred_active_days <= self.max_active_days:
            raise PlanningContractError(
                "preferred_active_days must lie inside the declared active-day range"
            )
        if not isinstance(self.double_sessions, DoubleSessionPreference):
            raise PlanningContractError(
                "double_sessions must be DoubleSessionPreference"
            )


@dataclass(frozen=True)
class SpacingPreference:
    subject_kind: SpacingSubjectKind
    subject: str
    desired_min_gap_days: int
    min_level: LoadDimensionLevel = LoadDimensionLevel.LOW

    def __post_init__(self) -> None:
        if not isinstance(self.subject_kind, SpacingSubjectKind):
            raise PlanningContractError(
                "spacing.subject_kind must be SpacingSubjectKind"
            )
        normalized = str(self.subject or "").strip()
        if not normalized:
            raise PlanningContractError("spacing.subject must be non-empty")
        object.__setattr__(self, "subject", normalized)
        if (
            not isinstance(self.desired_min_gap_days, int)
            or self.desired_min_gap_days < 1
        ):
            raise PlanningContractError(
                "spacing.desired_min_gap_days must be >= 1"
            )
        if not isinstance(self.min_level, LoadDimensionLevel):
            raise PlanningContractError("spacing.min_level must be LoadDimensionLevel")


@dataclass(frozen=True)
class ObjectivePolicy:
    schedule: SchedulePreferences
    spacing_preferences: tuple[SpacingPreference, ...] = ()

    def __post_init__(self) -> None:
        prefs = tuple(self.spacing_preferences)
        semantic = [
            (item.subject_kind.value, item.subject, item.min_level.value)
            for item in prefs
        ]
        if len(set(semantic)) != len(semantic):
            raise PlanningContractError("objective policy contains duplicate spacing preference")
        object.__setattr__(self, "spacing_preferences", prefs)


@dataclass(frozen=True)
class ObjectiveContext:
    strategy: StrategyRevision
    catalog_options: tuple[ApprovedWorkoutOption, ...]
    observed_obligation_credits: tuple[ObservedObligationCredit, ...]
    observed_load_exposures: tuple[ObservedLoadExposure, ...]
    fixed_commitments: tuple[FixedLoadCommitment, ...]
    previous_plan: PlanContent | None
    policy: ObjectivePolicy

    def __post_init__(self) -> None:
        options = tuple(self.catalog_options)
        keys = [item.option_key for item in options]
        if len(set(keys)) != len(keys):
            raise PlanningContractError("objective catalog contains duplicate option key")
        object.__setattr__(self, "catalog_options", options)
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
        object.__setattr__(self, "fixed_commitments", tuple(self.fixed_commitments))


@dataclass(frozen=True)
class ObjectiveVector:
    # S1 + S2, interleaved by priority tier so lower tiers can never
    # outrank breadth inside a higher tier.
    required_deficit_by_tier: tuple[Fraction, ...]
    unserved_required_by_tier: tuple[int, ...]
    max_required_deficit_by_tier: tuple[Fraction, ...]
    # S3
    spacing_shortfall_days: int
    spacing_violation_pairs: int
    # S4
    stability_identity_churn: int
    stability_date_moves: int
    stability_prescription_changes: int
    stability_order_changes: int
    # S5
    schedule_range_violation: int
    schedule_preferred_distance: int
    schedule_double_penalty: int
    # S6
    variation_repeat_penalty: int
    # S7
    discretionary_excess_by_tier: tuple[Fraction, ...]
    # S8
    canonical_tie_key: tuple

    @property
    def sort_key(self) -> tuple:
        obligation_priority = tuple(
            (
                self.required_deficit_by_tier[index],
                self.unserved_required_by_tier[index],
                self.max_required_deficit_by_tier[index],
            )
            for index in range(len(self.required_deficit_by_tier))
        )
        return (
            obligation_priority,
            # Anti-filler precedes all calendar/aesthetic preferences. Once
            # required obligations are equally satisfied, a plan with less
            # discretionary exposure always wins. A preferred active-day count
            # can therefore distribute justified training, never create it.
            self.discretionary_excess_by_tier,
            self.spacing_shortfall_days,
            self.spacing_violation_pairs,
            self.stability_identity_churn,
            self.stability_date_moves,
            self.stability_prescription_changes,
            self.stability_order_changes,
            self.schedule_range_violation,
            self.schedule_preferred_distance,
            self.schedule_double_penalty,
            self.variation_repeat_penalty,
            self.canonical_tie_key,
        )


def _credit(contribution) -> Fraction:
    return Fraction(
        contribution.credit_numerator,
        contribution.credit_denominator,
    )


def _obligation_credits(plan: PlanContent, context: ObjectiveContext) -> dict[str, Fraction]:
    obligations = {
        item.obligation_id: item
        for item in context.strategy.obligations
    }
    result = {key: Fraction(0, 1) for key in obligations}

    for observed in context.observed_obligation_credits:
        contribution = observed.contribution
        obligation = obligations.get(contribution.obligation_id)
        if obligation is None or not obligation.active_on(observed.local_date):
            continue
        result[contribution.obligation_id] += _credit(contribution)

    for workout in plan.workouts:
        for contribution in workout.obligation_contributions:
            obligation = obligations.get(contribution.obligation_id)
            if obligation is None or not obligation.active_on(workout.local_date):
                continue
            result[contribution.obligation_id] += _credit(contribution)

    return result


def _tier_vectors(
    strategy: StrategyRevision,
    credits: dict[str, Fraction],
) -> tuple[
    tuple[Fraction, ...],
    tuple[int, ...],
    tuple[Fraction, ...],
    tuple[Fraction, ...],
]:
    tiers = sorted({item.priority_tier for item in strategy.obligations})
    required_deficits: list[Fraction] = []
    unserved_counts: list[int] = []
    max_deficits: list[Fraction] = []
    discretionary_excess: list[Fraction] = []

    for tier in tiers:
        obligations = [
            item for item in strategy.obligations
            if item.priority_tier == tier
        ]
        deficits = []
        unserved = 0
        excess = Fraction(0, 1)

        for obligation in obligations:
            achieved = credits.get(obligation.obligation_id, Fraction(0, 1))
            if obligation.min_exposures > 0:
                deficit = max(
                    Fraction(0, 1),
                    Fraction(obligation.min_exposures, 1) - achieved,
                )
                deficits.append(deficit)
                if achieved <= 0:
                    unserved += 1
            # Exposure above the required minimum is discretionary. The
            # conservative S7 objective prefers not to add it merely because
            # capacity remains below max_exposures.
            excess += max(
                Fraction(0, 1),
                achieved - Fraction(obligation.min_exposures, 1),
            )

        required_deficits.append(sum(deficits, Fraction(0, 1)))
        unserved_counts.append(unserved)
        max_deficits.append(max(deficits, default=Fraction(0, 1)))
        discretionary_excess.append(excess)

    return (
        tuple(required_deficits),
        tuple(unserved_counts),
        tuple(max_deficits),
        tuple(discretionary_excess),
    )


_LEVEL_RANK = {
    LoadDimensionLevel.LOW: 1,
    LoadDimensionLevel.MODERATE: 2,
    LoadDimensionLevel.HIGH: 3,
    LoadDimensionLevel.UNKNOWN: 4,
}


def _spacing_dates(
    plan: PlanContent,
    context: ObjectiveContext,
    preference: SpacingPreference,
) -> list:
    dates = []

    if preference.subject_kind is SpacingSubjectKind.CAPABILITY:
        for observed in context.observed_obligation_credits:
            if observed.contribution.source_capability == preference.subject:
                dates.append(observed.local_date)
        for workout in plan.workouts:
            if any(
                contribution.source_capability == preference.subject
                for contribution in workout.obligation_contributions
            ):
                dates.append(workout.local_date)
        return dates

    for observed in context.observed_load_exposures:
        if any(
            item.dimension == preference.subject
            and _LEVEL_RANK[item.level] >= _LEVEL_RANK[preference.min_level]
            for item in observed.load_dimensions
        ):
            dates.append(observed.local_date)

    for commitment in context.fixed_commitments:
        if any(
            item.dimension == preference.subject
            and _LEVEL_RANK[item.level] >= _LEVEL_RANK[preference.min_level]
            for item in commitment.load_dimensions
        ):
            dates.append(commitment.local_date)

    for workout in plan.workouts:
        if any(
            item.dimension == preference.subject
            and _LEVEL_RANK[item.level] >= _LEVEL_RANK[preference.min_level]
            for item in workout.load_dimensions
        ):
            dates.append(workout.local_date)

    return dates


def _spacing_penalty(
    plan: PlanContent,
    context: ObjectiveContext,
) -> tuple[int, int]:
    total_shortfall = 0
    pairs = 0
    for preference in context.policy.spacing_preferences:
        dates = sorted(_spacing_dates(plan, context, preference))
        for first, second in combinations(dates, 2):
            gap = abs((second - first).days)
            if gap < preference.desired_min_gap_days:
                total_shortfall += preference.desired_min_gap_days - gap
                pairs += 1
    return total_shortfall, pairs


def _intent_signature(workout) -> tuple:
    """Stable semantic planning intent independent of date and generated id.

    Obligation contribution identity is what the strategy asked the workout to
    serve. Components are included so a genuinely different multisport intent
    is not treated as the same logical session.
    """
    contributions = tuple(
        sorted(
            (
                item.obligation_id,
                item.source_capability,
                item.kind.value,
                item.credit_numerator,
                item.credit_denominator,
            )
            for item in workout.obligation_contributions
        )
    )
    components = tuple(
        (item.discipline, item.order)
        for item in workout.components
    )
    return contributions, components


def _prescription_signature(workout) -> tuple:
    return (
        workout.recipe_id,
        workout.dose_option_id,
    )


def _stability_penalty(
    plan: PlanContent,
    previous: PlanContent | None,
) -> tuple[int, int, int, int]:
    """Match old/new workouts by semantic intent, never by incidental ids.

    Within one intent class, chronological pairing minimizes total absolute
    date movement for indistinguishable exposures. This means moving one
    workout remains a date move, while two identical sessions may swap
    incidental generated ids without creating false churn.
    """
    if previous is None:
        return 0, 0, 0, 0

    previous_rows = [
        item
        for item in previous.workouts
        if plan.affected_from <= item.local_date <= plan.affected_until
    ]
    current_rows = list(plan.workouts)

    previous_by_intent: dict[tuple, list] = {}
    current_by_intent: dict[tuple, list] = {}
    for item in previous_rows:
        previous_by_intent.setdefault(_intent_signature(item), []).append(item)
    for item in current_rows:
        current_by_intent.setdefault(_intent_signature(item), []).append(item)

    churn = 0
    date_moves = 0
    prescription_changes = 0
    order_changes = 0

    for intent in sorted(
        set(previous_by_intent) | set(current_by_intent),
        key=repr,
    ):
        before_rows = sorted(
            previous_by_intent.get(intent, []),
            key=lambda item: (
                item.local_date,
                item.within_day_order if item.within_day_order is not None else 999,
                item.recipe_id,
                item.dose_option_id,
            ),
        )
        after_rows = sorted(
            current_by_intent.get(intent, []),
            key=lambda item: (
                item.local_date,
                item.within_day_order if item.within_day_order is not None else 999,
                item.recipe_id,
                item.dose_option_id,
            ),
        )

        paired = min(len(before_rows), len(after_rows))
        churn += abs(len(before_rows) - len(after_rows))
        for index in range(paired):
            before = before_rows[index]
            after = after_rows[index]
            if before.local_date != after.local_date:
                date_moves += 1
            if _prescription_signature(before) != _prescription_signature(after):
                prescription_changes += 1
            if before.within_day_order != after.within_day_order:
                order_changes += 1

    return churn, date_moves, prescription_changes, order_changes


def _schedule_penalty(
    plan: PlanContent,
    preferences: SchedulePreferences,
) -> tuple[int, int, int]:
    per_day: dict = {}
    for workout in plan.workouts:
        per_day[workout.local_date] = per_day.get(workout.local_date, 0) + 1
    for commitment in plan.fixed_commitments:
        per_day[commitment.local_date] = per_day.get(commitment.local_date, 0) + 1

    active_days = sum(1 for count in per_day.values() if count > 0)
    if active_days < preferences.min_active_days:
        range_violation = preferences.min_active_days - active_days
    elif active_days > preferences.max_active_days:
        range_violation = active_days - preferences.max_active_days
    else:
        range_violation = 0

    preferred_distance = abs(active_days - preferences.preferred_active_days)

    if preferences.double_sessions is DoubleSessionPreference.ALLOW:
        double_penalty = 0
    else:
        double_penalty = sum(max(0, count - 1) for count in per_day.values())

    return range_violation, preferred_distance, double_penalty


def _variation_penalty(
    plan: PlanContent,
    context: ObjectiveContext,
) -> int:
    catalog = {item.option_key: item for item in context.catalog_options}
    obligations = {
        item.obligation_id: item
        for item in context.strategy.obligations
    }
    by_obligation: dict[str, list[str]] = {}

    for workout in plan.workouts:
        option = catalog.get((workout.recipe_id, workout.dose_option_id))
        if option is None:
            continue
        character = str(option.development_character or "").strip() or option.recipe_id
        for contribution in workout.obligation_contributions:
            obligation = obligations.get(contribution.obligation_id)
            if not obligation or not obligation.prefer_character_variation:
                continue
            by_obligation.setdefault(
                contribution.obligation_id,
                [],
            ).append(character)

    return sum(
        len(characters) - len(set(characters))
        for characters in by_obligation.values()
    )


def _canonical_tie_key(plan: PlanContent) -> tuple:
    rows = []
    for workout in plan.workouts:
        contributions = tuple(
            sorted(
                (
                    item.obligation_id,
                    item.source_capability,
                    item.kind.value,
                    item.credit_numerator,
                    item.credit_denominator,
                )
                for item in workout.obligation_contributions
            )
        )
        rows.append(
            (
                workout.local_date.isoformat(),
                workout.within_day_order if workout.within_day_order is not None else 999,
                workout.workout_id,
                workout.recipe_id,
                workout.dose_option_id,
                contributions,
            )
        )
    return tuple(sorted(rows))


def evaluate_objectives(
    plan: PlanContent,
    context: ObjectiveContext,
) -> ObjectiveVector:
    credits = _obligation_credits(plan, context)
    required, unserved, max_deficit, discretionary_excess = _tier_vectors(
        context.strategy,
        credits,
    )
    spacing_shortfall, spacing_pairs = _spacing_penalty(plan, context)
    churn, moves, prescription_changes, order_changes = _stability_penalty(
        plan,
        context.previous_plan,
    )
    range_violation, preferred_distance, double_penalty = _schedule_penalty(
        plan,
        context.policy.schedule,
    )
    variation = _variation_penalty(plan, context)

    return ObjectiveVector(
        required_deficit_by_tier=required,
        unserved_required_by_tier=unserved,
        max_required_deficit_by_tier=max_deficit,
        spacing_shortfall_days=spacing_shortfall,
        spacing_violation_pairs=spacing_pairs,
        stability_identity_churn=churn,
        stability_date_moves=moves,
        stability_prescription_changes=prescription_changes,
        stability_order_changes=order_changes,
        schedule_range_violation=range_violation,
        schedule_preferred_distance=preferred_distance,
        schedule_double_penalty=double_penalty,
        variation_repeat_penalty=variation,
        discretionary_excess_by_tier=discretionary_excess,
        canonical_tie_key=_canonical_tie_key(plan),
    )


def select_best_valid_plan(
    plans: tuple[PlanContent, ...] | list[PlanContent],
    context: ObjectiveContext,
) -> PlanContent:
    candidates = tuple(plans)
    if not candidates:
        raise PlanningContractError("cannot select best plan from an empty candidate set")
    return min(
        candidates,
        key=lambda plan: evaluate_objectives(plan, context).sort_key,
    )
