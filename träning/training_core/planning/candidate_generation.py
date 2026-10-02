"""Complete bounded candidate generation for Planning Engine v1.

The generator is deliberately ignorant of UI, providers and persistence. It
enumerates only workouts that can reduce an unsatisfied StrategyRevision
obligation. Because anti-filler outranks every calendar/stability preference,
a workout that cannot reduce a minimum obligation deficit cannot belong to the
lexicographically optimal plan.

The final independent validator remains authoritative for hard constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from fractions import Fraction
from hashlib import sha256
from itertools import combinations, permutations, product
from math import ceil

from .models import (
    ApprovedWorkoutOption,
    ContributionKind,
    FixedLoadCommitment,
    LoadDimensionLevel,
    ObligationContribution,
    PlanContent,
    PlannedTrainingWorkout,
    PlanningObligation,
    SameDayOrderRule,
)
from .validation import PlanValidationContext, validate_plan_content


_LEVEL_RANK = {
    LoadDimensionLevel.LOW: 1,
    LoadDimensionLevel.MODERATE: 2,
    LoadDimensionLevel.HIGH: 3,
    LoadDimensionLevel.UNKNOWN: 4,
}


@dataclass(frozen=True)
class CandidateAtom:
    local_date: date
    option: ApprovedWorkoutOption
    contributions: tuple[ObligationContribution, ...]
    constraint_ids: tuple[str, ...] = ()
    instance_index: int = 1

    @property
    def key(self) -> tuple:
        return (
            self.local_date.isoformat(),
            self.option.planning_priority,
            self.option.recipe_id,
            self.option.dose_option_id,
            self.instance_index,
            self.constraint_ids,
            tuple(
                (
                    item.obligation_id,
                    item.source_capability,
                    item.kind.value,
                    item.credit_numerator,
                    item.credit_denominator,
                )
                for item in self.contributions
            ),
        )


@dataclass(frozen=True)
class CandidateGenerationStats:
    atoms: int
    terminal_selections: int
    plan_variants: int


@dataclass(frozen=True)
class CandidateGenerationLimits:
    """Deterministic resource guard for exhaustive candidate generation.

    Hitting a limit is never permission to return an approximate plan. The
    caller must fail closed because lexicographic optimality has not been proven.
    """

    max_search_states: int = 100_000
    max_terminal_selections: int = 50_000
    max_plan_variants: int = 100_000

    def __post_init__(self) -> None:
        for field in (
            "max_search_states",
            "max_terminal_selections",
            "max_plan_variants",
        ):
            value = getattr(self, field)
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field} must be a positive integer")


class CandidateSearchLimitExceeded(RuntimeError):
    """Raised before an incomplete search could masquerade as a valid solve."""

    def __init__(
        self,
        *,
        stage: str,
        observed: int,
        limit: int,
        generation: CandidateGenerationStats,
    ) -> None:
        self.stage = stage
        self.observed = observed
        self.limit = limit
        self.generation = generation
        super().__init__(
            f"candidate search limit exceeded at {stage}: "
            f"observed={observed} limit={limit}"
        )


def _credit(value) -> Fraction:
    return Fraction(value.credit_numerator, value.credit_denominator)


def _duration_upper_bound_minutes(item) -> float | None:
    matches = [
        estimate
        for estimate in item.quantitative_load
        if (
            estimate.scope,
            estimate.subject,
            estimate.metric,
            estimate.unit,
        )
        == ("global", "training_duration", "duration", "minutes")
    ]
    if not matches:
        return None
    return sum(float(estimate.max_value) for estimate in matches)


def _date_range(first: date, last: date):
    current = first
    while current <= last:
        yield current
        current += timedelta(days=1)


def _eligibility_keys(context: PlanValidationContext) -> set[tuple[str, str, str]]:
    return {
        (item.recipe_id, item.dose_option_id, item.capability)
        for item in context.option_eligibility
    }


def _option_fully_eligible(
    option: ApprovedWorkoutOption,
    eligibility: set[tuple[str, str, str]],
) -> bool:
    return all(
        (option.recipe_id, option.dose_option_id, capability) in eligibility
        for capability in option.capabilities
    )


def _contribution_for_obligation(
    option: ApprovedWorkoutOption,
    obligation: PlanningObligation,
    eligibility: set[tuple[str, str, str]],
) -> ObligationContribution | None:
    option_key = (option.recipe_id, option.dose_option_id)

    # Multi-capability options are indivisible physical prescriptions. A
    # workout cannot bypass athlete eligibility or the StrategyRevision's
    # explicit dose domain through either direct or partial credit.
    if not _option_fully_eligible(option, eligibility):
        return None
    if (
        obligation.allowed_dose_option_ids
        and option.dose_option_id not in obligation.allowed_dose_option_ids
    ):
        return None

    if (
        obligation.capability in option.capabilities
        and option.recipe_id in obligation.recipe_family
        and (*option_key, obligation.capability) in eligibility
    ):
        return ObligationContribution(
            obligation_id=obligation.obligation_id,
            source_capability=obligation.capability,
            kind=ContributionKind.DIRECT,
            credit_numerator=1,
            credit_denominator=1,
        )

    partial = []
    for rule in obligation.partial_coverage:
        if rule.source_capability not in option.capabilities:
            continue
        if (*option_key, rule.source_capability) not in eligibility:
            continue
        partial.append(rule)

    if not partial:
        return None

    # One physical workout earns at most one contribution toward one obligation.
    # If several explicitly approved source capabilities are present, use the
    # strongest exact mapping; tie-break by stable capability id.
    rule = sorted(
        partial,
        key=lambda item: (
            -Fraction(item.credit_numerator, item.credit_denominator),
            item.source_capability,
        ),
    )[0]
    return ObligationContribution(
        obligation_id=obligation.obligation_id,
        source_capability=rule.source_capability,
        kind=ContributionKind.PARTIAL,
        credit_numerator=rule.credit_numerator,
        credit_denominator=rule.credit_denominator,
    )


def generate_candidate_atoms(
    context: PlanValidationContext,
    affected_from: date,
    affected_until: date,
) -> tuple[CandidateAtom, ...]:
    eligibility = _eligibility_keys(context)
    closed = set(context.closed_dates)
    availability = {item.local_date: item for item in context.availability}

    atoms = []
    for day in _date_range(affected_from, affected_until):
        if day in closed:
            continue
        rule = availability.get(day)
        if rule is not None and (
            not rule.available
            or rule.max_sessions == 0
            or rule.max_duration_minutes == 0
        ):
            continue

        for option in sorted(
            context.catalog_options,
            key=lambda item: (
                item.planning_priority,
                item.recipe_id,
                item.dose_option_id,
            ),
        ):
            contributions = []
            for obligation in sorted(
                context.strategy.obligations,
                key=lambda item: (item.priority_tier, item.obligation_id),
            ):
                if not obligation.active_on(day):
                    continue
                contribution = _contribution_for_obligation(
                    option,
                    obligation,
                    eligibility,
                )
                if contribution is not None:
                    contributions.append(contribution)

            contribution_ids = tuple(
                sorted(item.obligation_id for item in contributions)
            )
            placement_constraints = tuple(
                item
                for item in context.placement_constraints
                if item.local_date == day
                and item.option_key == option.option_key
                and (
                    not item.obligation_ids
                    or item.obligation_ids == contribution_ids
                )
            )
            required_placement = any(
                item.min_occurrences > 0
                for item in placement_constraints
            )
            option_is_eligible = _option_fully_eligible(
                option,
                eligibility,
            )

            if not contributions and not required_placement:
                continue
            if not contributions and not option_is_eligible:
                # An explicit add cannot bypass athlete-specific dose
                # eligibility. The final placement minimum will then make every
                # candidate invalid and the solver returns BLOCKED.
                continue

            obligation_by_id = {
                item.obligation_id: item
                for item in context.strategy.obligations
            }
            multiplicity = 1
            for contribution in contributions:
                obligation = obligation_by_id[contribution.obligation_id]
                credit = _credit(contribution)
                # Bound identical same-day instances from the obligation ceiling
                # and exact per-workout credit. This preserves arbitrary 0..N
                # multipass semantics without creating an unbounded domain.
                needed_int = ceil(
                    Fraction(obligation.max_exposures, 1) / credit
                )
                multiplicity = max(multiplicity, needed_int)

            for placement in placement_constraints:
                multiplicity = max(
                    multiplicity,
                    placement.min_occurrences,
                )

            day_commitments = tuple(
                commitment
                for commitment in context.fixed_commitments
                if commitment.local_date == day
            )
            if rule is not None and rule.max_sessions is not None:
                multiplicity = min(
                    multiplicity,
                    max(0, rule.max_sessions - len(day_commitments)),
                )

            if rule is not None and rule.max_duration_minutes is not None:
                option_duration = _duration_upper_bound_minutes(option)
                fixed_durations = tuple(
                    _duration_upper_bound_minutes(commitment)
                    for commitment in day_commitments
                )
                if (
                    option_duration is not None
                    and option_duration > 0
                    and all(value is not None for value in fixed_durations)
                ):
                    remaining_minutes = max(
                        0.0,
                        float(rule.max_duration_minutes)
                        - sum(float(value) for value in fixed_durations),
                    )
                    multiplicity = min(
                        multiplicity,
                        int(remaining_minutes // option_duration),
                    )

            for instance_index in range(1, multiplicity + 1):
                constraint_ids = tuple(
                    sorted(
                        item.constraint_id
                        for item in placement_constraints
                        if 0 < instance_index <= item.min_occurrences
                    )
                )
                atoms.append(
                    CandidateAtom(
                        local_date=day,
                        option=option,
                        contributions=tuple(contributions),
                        constraint_ids=constraint_ids,
                        instance_index=instance_index,
                    )
                )

    return tuple(sorted(atoms, key=lambda item: item.key))


def _observed_credits(context: PlanValidationContext) -> dict[str, Fraction]:
    result = {
        item.obligation_id: Fraction(0, 1)
        for item in context.strategy.obligations
    }
    obligations = {
        item.obligation_id: item
        for item in context.strategy.obligations
    }
    for observed in context.observed_obligation_credits:
        obligation = obligations.get(observed.contribution.obligation_id)
        if obligation is None or not obligation.active_on(observed.local_date):
            continue
        if not obligation.accepts_observed_basis(observed.basis):
            continue
        result[obligation.obligation_id] += _credit(observed.contribution)
    return result


def _selection_credits(
    selected: tuple[int, ...],
    atoms: tuple[CandidateAtom, ...],
    base: dict[str, Fraction],
) -> dict[str, Fraction]:
    result = dict(base)
    for index in selected:
        for contribution in atoms[index].contributions:
            result[contribution.obligation_id] = (
                result.get(contribution.obligation_id, Fraction(0, 1))
                + _credit(contribution)
            )
    return result


def enumerate_terminal_selections(
    context: PlanValidationContext,
    atoms: tuple[CandidateAtom, ...],
    affected_from: date,
    affected_until: date,
    limits: CandidateGenerationLimits | None = None,
) -> tuple[tuple[int, ...], ...]:
    """Enumerate the complete bounded strategy-target search domain.

    A branch either adds a workout that reduces the currently selected strategy
    target deficit or explicitly declines that target. Required minima remain
    higher-priority objective deficits, while target_exposures allows optional
    support work to compete only when hard constraints and higher objectives
    permit it. Work above a target is never enumerated merely to fill time.
    """

    limits = limits or CandidateGenerationLimits()
    base = _observed_credits(context)
    obligations = tuple(
        sorted(
            (
                item
                for item in context.strategy.obligations
                if item.valid_from <= affected_until
                and item.valid_until >= affected_from
            ),
            key=lambda item: (item.priority_tier, item.obligation_id),
        )
    )
    atom_indexes_by_obligation = {
        obligation.obligation_id: tuple(
            index
            for index, atom in enumerate(atoms)
            if any(
                contribution.obligation_id == obligation.obligation_id
                for contribution in atom.contributions
            )
        )
        for obligation in obligations
    }

    terminals: set[tuple[int, ...]] = set()
    seen: set[tuple[tuple[int, ...], tuple[str, ...]]] = set()
    viable_states: set[tuple[tuple[int, ...], tuple[str, ...]]] = set()

    inside_commitments = tuple(
        item
        for item in context.fixed_commitments
        if affected_from <= item.local_date <= affected_until
    )
    baseline_plan = PlanContent(
        source_revision=context.source_revision,
        strategy_revision_id=context.strategy.revision_id,
        affected_from=affected_from,
        affected_until=affected_until,
        workouts=(),
        fixed_commitments=inside_commitments,
    )
    baseline_issues = frozenset(
        validate_plan_content(baseline_plan, context).issues
    )
    prefix_repairable_codes = frozenset(
        {
            "LOAD_COMPATIBILITY_ORDER_UNKNOWN",
            "LOAD_COMPATIBILITY_ORDER_VIOLATION",
            "PLACEMENT_MIN_UNSATISFIED",
            "PLACEMENT_REQUIRED_PROVENANCE_MISSING",
        }
    )

    def monotonic_issues(selection: tuple[int, ...]):
        partial_plan = PlanContent(
            source_revision=context.source_revision,
            strategy_revision_id=context.strategy.revision_id,
            affected_from=affected_from,
            affected_until=affected_until,
            workouts=_base_workouts(selection, atoms),
            fixed_commitments=inside_commitments,
        )
        return tuple(
            issue
            for issue in validate_plan_content(partial_plan, context).issues
            if issue not in baseline_issues
            and issue.code not in prefix_repairable_codes
        )

    # Hard compatibility, per-session availability and most max constraints are
    # unary or pairwise. Prove those conflicts once, then reuse the result in
    # the exhaustive search instead of running the full validator at every node.
    invalid_singletons = {
        index
        for index in range(len(atoms))
        if monotonic_issues((index,))
    }
    incompatible_pairs = {
        (first, second)
        for first, second in combinations(range(len(atoms)), 2)
        if first not in invalid_singletons
        and second not in invalid_singletons
        and monotonic_issues((first, second))
    }

    availability_by_day = {
        item.local_date: item
        for item in context.availability
    }
    fixed_by_day = {
        day: tuple(
            item
            for item in inside_commitments
            if item.local_date == day
        )
        for day in _date_range(affected_from, affected_until)
    }

    def selection_has_monotonic_conflict(
        selected: tuple[int, ...],
        credits: dict[str, Fraction],
    ) -> bool:
        selected_set = set(selected)
        if selected_set & invalid_singletons:
            return True
        if any(
            first in selected_set and second in selected_set
            for first, second in incompatible_pairs
        ):
            return True

        obligations_by_id = {
            item.obligation_id: item
            for item in obligations
        }
        for obligation_id, credit in credits.items():
            obligation = obligations_by_id.get(obligation_id)
            if obligation is not None and credit > Fraction(
                obligation.max_exposures,
                1,
            ):
                return True

        selected_by_day: dict[date, list[CandidateAtom]] = {}
        for index in selected:
            selected_by_day.setdefault(
                atoms[index].local_date,
                [],
            ).append(atoms[index])
        for day, selected_atoms in selected_by_day.items():
            rule = availability_by_day.get(day)
            if rule is None:
                continue
            fixed = fixed_by_day.get(day, ())
            if (
                rule.max_sessions is not None
                and len(fixed) + len(selected_atoms) > rule.max_sessions
            ):
                return True
            if rule.max_duration_minutes is None:
                continue
            fixed_durations = tuple(
                _duration_upper_bound_minutes(item)
                for item in fixed
            )
            selected_durations = tuple(
                _duration_upper_bound_minutes(item.option)
                for item in selected_atoms
            )
            if all(
                value is not None
                for value in (*fixed_durations, *selected_durations)
            ):
                total = sum(
                    float(value)
                    for value in (*fixed_durations, *selected_durations)
                )
                if total > float(rule.max_duration_minutes):
                    return True
        return False

    def add_rejected_terminal(selected: tuple[int, ...]) -> None:
        terminals.add(selected)
        if len(terminals) > limits.max_terminal_selections:
            raise CandidateSearchLimitExceeded(
                stage="terminal_selections",
                observed=len(terminals),
                limit=limits.max_terminal_selections,
                generation=CandidateGenerationStats(
                    atoms=len(atoms),
                    terminal_selections=len(terminals),
                    plan_variants=0,
                ),
            )

    def walk(selected: tuple[int, ...], declined: frozenset[str]) -> None:
        selected = tuple(sorted(selected))
        state_key = (selected, tuple(sorted(declined)))
        if state_key in seen:
            return
        seen.add(state_key)

        credits = _selection_credits(selected, atoms, base)
        if selection_has_monotonic_conflict(selected, credits):
            # Keep one minimal invalid representative so solver diagnostics
            # still report the hard reason that caused the branch to be cut.
            add_rejected_terminal(selected)
            return

        viable_states.add(state_key)
        if len(viable_states) > limits.max_search_states:
            raise CandidateSearchLimitExceeded(
                stage="search_states",
                observed=len(viable_states),
                limit=limits.max_search_states,
                generation=CandidateGenerationStats(
                    atoms=len(atoms),
                    terminal_selections=len(terminals),
                    plan_variants=0,
                ),
            )

        target = next(
            (
                obligation
                for obligation in obligations
                if obligation.obligation_id not in declined
                and credits.get(obligation.obligation_id, Fraction(0, 1))
                < Fraction(obligation.target_exposures, 1)
            ),
            None,
        )
        if target is None:
            terminals.add(selected)
            if len(terminals) > limits.max_terminal_selections:
                raise CandidateSearchLimitExceeded(
                    stage="terminal_selections",
                    observed=len(terminals),
                    limit=limits.max_terminal_selections,
                    generation=CandidateGenerationStats(
                        atoms=len(atoms),
                        terminal_selections=len(terminals),
                        plan_variants=0,
                    ),
                )
            return

        selected_set = set(selected)
        current_credit = credits.get(target.obligation_id, Fraction(0, 1))
        branches = []
        for index in atom_indexes_by_obligation[target.obligation_id]:
            if index in selected_set:
                continue
            predecessor = _duplicate_predecessor_index(atoms, index)
            if predecessor is not None and predecessor not in selected_set:
                # Identical instances are symmetric. Requiring prefix selection
                # keeps the search complete while removing duplicate permutations.
                continue
            contribution = next(
                item
                for item in atoms[index].contributions
                if item.obligation_id == target.obligation_id
            )
            if _credit(contribution) <= 0:
                continue
            # The atom must improve the strategy target. Required minima are
            # still enforced/ranked independently; target_exposures lets the
            # domain represent support-if-absorbable work without making it
            # mandatory.
            if current_credit >= Fraction(target.target_exposures, 1):
                continue
            branches.append(index)

        def unresolved_after(
            selected_value: tuple[int, ...],
            declined_value: frozenset[str],
        ) -> bool:
            future_credits = _selection_credits(
                tuple(sorted(selected_value)),
                atoms,
                base,
            )
            return any(
                obligation.obligation_id not in declined_value
                and future_credits.get(
                    obligation.obligation_id,
                    Fraction(0, 1),
                )
                < Fraction(obligation.target_exposures, 1)
                for obligation in obligations
            )

        def finish_or_walk(
            selected_value: tuple[int, ...],
            declined_value: frozenset[str],
        ) -> None:
            normalized = tuple(sorted(selected_value))
            if unresolved_after(normalized, declined_value):
                walk(normalized, declined_value)
                return

            # A terminal leaf is a result, not another planning decision.
            # Validate monotonic conflicts directly and record the complete
            # selection without consuming one more search-state slot. This
            # preserves the exact candidate domain while avoiding a duplicate
            # DFS state for every completed week.
            final_credits = _selection_credits(normalized, atoms, base)
            if selection_has_monotonic_conflict(normalized, final_credits):
                add_rejected_terminal(normalized)
                return
            terminals.add(normalized)
            if len(terminals) > limits.max_terminal_selections:
                raise CandidateSearchLimitExceeded(
                    stage="terminal_selections",
                    observed=len(terminals),
                    limit=limits.max_terminal_selections,
                    generation=CandidateGenerationStats(
                        atoms=len(atoms),
                        terminal_selections=len(terminals),
                        plan_variants=0,
                    ),
                )

        for index in branches:
            finish_or_walk(tuple((*selected, index)), declined)

        # An unmet obligation is allowed as a soft deficit. This branch is
        # required for completeness when hard constraints make fulfilment
        # impossible or when a lower-priority combination is otherwise better.
        declined_next = frozenset((*declined, target.obligation_id))
        finish_or_walk(selected, declined_next)

    mandatory = tuple(
        index
        for index, atom in enumerate(atoms)
        if atom.constraint_ids
    )
    walk(mandatory, frozenset())
    return tuple(sorted(terminals))


def _dimension_at_least(exposure, dimension: str, minimum: LoadDimensionLevel) -> bool:
    item = next(
        (entry for entry in exposure if entry.dimension == dimension),
        None,
    )
    if item is None:
        return False
    return _LEVEL_RANK[item.level] >= _LEVEL_RANK[minimum]


def _directional_rule_applies(first, second, policy) -> bool:
    for rule in policy.rules:
        if rule.same_day_order not in {
            SameDayOrderRule.FIRST_BEFORE_SECOND,
            SameDayOrderRule.SECOND_BEFORE_FIRST,
        }:
            continue
        direct = (
            _dimension_at_least(first, rule.first_dimension, rule.first_min_level)
            and _dimension_at_least(second, rule.second_dimension, rule.second_min_level)
        )
        reverse = (
            _dimension_at_least(second, rule.first_dimension, rule.first_min_level)
            and _dimension_at_least(first, rule.second_dimension, rule.second_min_level)
        )
        if direct or reverse:
            return True
    return False


def _day_requires_order(workouts, commitments, policy) -> bool:
    rows = [
        item.load_dimensions
        for item in (*workouts, *commitments)
    ]
    for index, first in enumerate(rows):
        for second in rows[index + 1 :]:
            if _directional_rule_applies(first, second, policy):
                return True
    return False


def _workout_id(atom: CandidateAtom) -> str:
    raw = repr(atom.key).encode("utf-8")
    return "pv1-" + sha256(raw).hexdigest()[:20]


def _duplicate_predecessor_index(
    atoms: tuple[CandidateAtom, ...],
    index: int,
) -> int | None:
    atom = atoms[index]
    if atom.instance_index <= 1:
        return None
    predecessor_key = (
        atom.local_date,
        atom.option.recipe_id,
        atom.option.dose_option_id,
        atom.instance_index - 1,
    )
    for candidate_index, candidate in enumerate(atoms):
        key = (
            candidate.local_date,
            candidate.option.recipe_id,
            candidate.option.dose_option_id,
            candidate.instance_index,
        )
        if key == predecessor_key:
            return candidate_index
    return None


def _base_workouts(
    selection: tuple[int, ...],
    atoms: tuple[CandidateAtom, ...],
) -> tuple[PlannedTrainingWorkout, ...]:
    rows = []
    for index in selection:
        atom = atoms[index]
        rows.append(
            PlannedTrainingWorkout(
                workout_id=_workout_id(atom),
                local_date=atom.local_date,
                recipe_id=atom.option.recipe_id,
                dose_option_id=atom.option.dose_option_id,
                obligation_contributions=atom.contributions,
                components=atom.option.components,
                load_dimensions=atom.option.load_dimensions,
                quantitative_load=atom.option.quantitative_load,
                source_refs=("planning_v1:candidate_generation",),
                constraint_ids=atom.constraint_ids,
            )
        )
    return tuple(
        sorted(
            rows,
            key=lambda item: (
                item.local_date,
                item.recipe_id,
                item.dose_option_id,
                item.workout_id,
            ),
        )
    )


def _day_order_variants(
    workouts: tuple[PlannedTrainingWorkout, ...],
    commitments: tuple[FixedLoadCommitment, ...],
    policy,
) -> tuple[tuple[PlannedTrainingWorkout, ...], ...]:
    if not workouts:
        return ((),)
    if not _day_requires_order(workouts, commitments, policy):
        return (workouts,)

    fixed_orders = {
        item.within_day_order
        for item in commitments
        if item.within_day_order is not None
    }
    max_fixed = max(fixed_orders, default=0)
    max_slot = max(len(workouts) + len(commitments), max_fixed + len(workouts))
    available = tuple(
        value for value in range(1, max_slot + 1)
        if value not in fixed_orders
    )
    if len(available) < len(workouts):
        return ()

    variants = []
    for assignment in permutations(available, len(workouts)):
        variants.append(
            tuple(
                replace(workout, within_day_order=order)
                for workout, order in zip(workouts, assignment)
            )
        )
    return tuple(variants)


def _ordered_plan_variants(
    base_workouts: tuple[PlannedTrainingWorkout, ...],
    context: PlanValidationContext,
    affected_from: date,
    affected_until: date,
) -> tuple[tuple[PlannedTrainingWorkout, ...], ...]:
    inside_commitments = tuple(
        item for item in context.fixed_commitments
        if affected_from <= item.local_date <= affected_until
    )
    days = sorted(
        {
            item.local_date for item in base_workouts
        }
        | {
            item.local_date for item in inside_commitments
        }
    )

    day_variants = []
    for day in days:
        workouts = tuple(item for item in base_workouts if item.local_date == day)
        commitments = tuple(
            item for item in inside_commitments
            if item.local_date == day
        )
        day_variants.append(
            _day_order_variants(
                workouts,
                commitments,
                context.compatibility_policy,
            )
        )

    if any(not variants for variants in day_variants):
        return ()

    if not day_variants:
        return ((),)

    result = []
    for choices in product(*day_variants):
        merged = tuple(
            sorted(
                (item for group in choices for item in group),
                key=lambda item: (
                    item.local_date,
                    item.within_day_order
                    if item.within_day_order is not None
                    else 999,
                    item.recipe_id,
                    item.dose_option_id,
                    item.workout_id,
                ),
            )
        )
        result.append(merged)
    return tuple(result)


def enumerate_candidate_plans(
    context: PlanValidationContext,
    affected_from: date,
    affected_until: date,
    limits: CandidateGenerationLimits | None = None,
) -> tuple[tuple[PlanContent, ...], CandidateGenerationStats]:
    limits = limits or CandidateGenerationLimits()
    atoms = generate_candidate_atoms(context, affected_from, affected_until)
    selections = enumerate_terminal_selections(
        context,
        atoms,
        affected_from,
        affected_until,
        limits,
    )
    inside_commitments = tuple(
        item for item in context.fixed_commitments
        if affected_from <= item.local_date <= affected_until
    )

    plans = []
    semantic_seen = set()
    for selection in selections:
        base = _base_workouts(selection, atoms)
        for workouts in _ordered_plan_variants(
            base,
            context,
            affected_from,
            affected_until,
        ):
            plan = PlanContent(
                source_revision=context.source_revision,
                strategy_revision_id=context.strategy.revision_id,
                affected_from=affected_from,
                affected_until=affected_until,
                workouts=workouts,
                fixed_commitments=inside_commitments,
            )
            semantic = (
                tuple(
                    (
                        item.workout_id,
                        item.local_date,
                        item.within_day_order,
                        item.recipe_id,
                        item.dose_option_id,
                    )
                    for item in plan.workouts
                ),
                tuple(item.commitment_id for item in plan.fixed_commitments),
            )
            if semantic in semantic_seen:
                continue
            semantic_seen.add(semantic)
            plans.append(plan)
            if len(plans) > limits.max_plan_variants:
                raise CandidateSearchLimitExceeded(
                    stage="plan_variants",
                    observed=len(plans),
                    limit=limits.max_plan_variants,
                    generation=CandidateGenerationStats(
                        atoms=len(atoms),
                        terminal_selections=len(selections),
                        plan_variants=len(plans),
                    ),
                )

    plans = tuple(
        sorted(
            plans,
            key=lambda plan: tuple(
                (
                    item.local_date.isoformat(),
                    item.within_day_order
                    if item.within_day_order is not None
                    else 999,
                    item.recipe_id,
                    item.dose_option_id,
                    item.workout_id,
                )
                for item in plan.workouts
            ),
        )
    )
    return (
        plans,
        CandidateGenerationStats(
            atoms=len(atoms),
            terminal_selections=len(selections),
            plan_variants=len(plans),
        ),
    )
