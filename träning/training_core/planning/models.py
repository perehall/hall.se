"""Typed data contracts for Planning Engine v1.

This module deliberately contains no solver, persistence, provider or rendering
logic. It defines the minimum immutable objects that the future planning engine
is allowed to consume and emit.

The contracts are conservative:
- obligations are bounded;
- aggregate load bounds have explicit units and provenance;
- plan authority is either current for one source revision or explicitly blocked;
- strategy revisions are immutable inputs to execution planning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Iterable


class PlanningContractError(ValueError):
    """Raised when a Planning Engine v1 domain contract is internally invalid."""


def _required_text(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise PlanningContractError(f"{field} must be non-empty")
    return normalized


def _unique_text_tuple(values: Iterable[str], field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    normalized = tuple(str(value or "").strip() for value in values)
    if not allow_empty and not normalized:
        raise PlanningContractError(f"{field} must not be empty")
    if any(not value for value in normalized):
        raise PlanningContractError(f"{field} contains an empty value")
    if len(set(normalized)) != len(normalized):
        raise PlanningContractError(f"{field} contains duplicates")
    return normalized


class UnknownAggregatePolicy(str, Enum):
    """Policy when an aggregate load dimension lacks trusted evidence."""

    BLOCK_INCREASE = "block_increase"
    HOLD_ESTABLISHED_BASELINE = "hold_established_baseline"


class PlanAuthorityStatus(str, Enum):
    CURRENT = "current"
    BLOCKED = "blocked"


class LoadDimensionLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNKNOWN = "unknown"


class ContributionKind(str, Enum):
    DIRECT = "direct"
    PARTIAL = "partial"


@dataclass(frozen=True)
class LoadDimensionExposure:
    """Categorical load used for compatibility when precise metrics are unavailable."""

    dimension: str
    level: LoadDimensionLevel
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimension", _required_text(self.dimension, "dimension"))
        if not isinstance(self.level, LoadDimensionLevel):
            raise PlanningContractError("level must be LoadDimensionLevel")
        object.__setattr__(
            self,
            "provenance_refs",
            _unique_text_tuple(self.provenance_refs, "provenance_refs"),
        )


@dataclass(frozen=True)
class LoadEstimate:
    """Quantitative external-load estimate with an explicit uncertainty interval."""

    scope: str
    subject: str
    metric: str
    unit: str
    min_value: float
    max_value: float
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", _required_text(self.scope, "load_estimate.scope"))
        object.__setattr__(self, "subject", _required_text(self.subject, "load_estimate.subject"))
        object.__setattr__(self, "metric", _required_text(self.metric, "load_estimate.metric"))
        object.__setattr__(self, "unit", _required_text(self.unit, "load_estimate.unit"))
        for field in ("min_value", "max_value"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PlanningContractError(f"load_estimate.{field} must be numeric")
            if float(value) < 0:
                raise PlanningContractError(f"load_estimate.{field} must be >= 0")
        if float(self.max_value) < float(self.min_value):
            raise PlanningContractError(
                "load_estimate.max_value cannot be below min_value"
            )
        object.__setattr__(
            self,
            "provenance_refs",
            _unique_text_tuple(self.provenance_refs, "load_estimate.provenance_refs"),
        )


@dataclass(frozen=True)
class FixedLoadCommitment:
    """Immutable user/external training commitment presented to the solver as data."""

    commitment_id: str
    local_date: date
    label: str
    load_dimensions: tuple[LoadDimensionExposure, ...]
    source_refs: tuple[str, ...]
    quantitative_load: tuple[LoadEstimate, ...] = ()
    within_day_order: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "commitment_id",
            _required_text(self.commitment_id, "commitment_id"),
        )
        object.__setattr__(self, "label", _required_text(self.label, "label"))
        if not isinstance(self.local_date, date):
            raise PlanningContractError("fixed commitment local_date must be a date")

        dimensions = tuple(self.load_dimensions)
        if not dimensions:
            raise PlanningContractError("fixed commitment must declare load_dimensions")
        if len({item.dimension for item in dimensions}) != len(dimensions):
            raise PlanningContractError(
                "fixed commitment contains duplicate load dimension"
            )
        object.__setattr__(self, "load_dimensions", dimensions)
        object.__setattr__(
            self,
            "source_refs",
            _unique_text_tuple(self.source_refs, "source_refs"),
        )

        quantitative = tuple(self.quantitative_load)
        semantic_keys = [
            (item.scope, item.subject, item.metric, item.unit)
            for item in quantitative
        ]
        if len(set(semantic_keys)) != len(semantic_keys):
            raise PlanningContractError(
                "fixed commitment contains duplicate quantitative load metric/unit"
            )
        object.__setattr__(self, "quantitative_load", quantitative)

        if self.within_day_order is not None:
            if not isinstance(self.within_day_order, int) or self.within_day_order <= 0:
                raise PlanningContractError(
                    "within_day_order must be a positive integer when supplied"
                )


@dataclass(frozen=True)
class ObligationContribution:
    """Exact contribution of one workout/exposure toward one obligation."""

    obligation_id: str
    source_capability: str
    kind: ContributionKind
    credit_numerator: int
    credit_denominator: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "obligation_id",
            _required_text(self.obligation_id, "contribution.obligation_id"),
        )
        object.__setattr__(
            self,
            "source_capability",
            _required_text(self.source_capability, "contribution.source_capability"),
        )
        if not isinstance(self.kind, ContributionKind):
            raise PlanningContractError("contribution.kind must be ContributionKind")
        if not isinstance(self.credit_numerator, int) or self.credit_numerator <= 0:
            raise PlanningContractError(
                "contribution.credit_numerator must be a positive integer"
            )
        if not isinstance(self.credit_denominator, int) or self.credit_denominator <= 0:
            raise PlanningContractError(
                "contribution.credit_denominator must be a positive integer"
            )
        if self.credit_numerator > self.credit_denominator:
            raise PlanningContractError(
                "obligation contribution cannot exceed one full exposure"
            )

    @property
    def exact_credit(self) -> tuple[int, int]:
        return self.credit_numerator, self.credit_denominator


@dataclass(frozen=True)
class ObservedObligationCredit:
    """Immutable planning credit already earned by completed canonical training."""

    local_date: date
    contribution: ObligationContribution
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.local_date, date):
            raise PlanningContractError("observed obligation credit local_date must be a date")
        object.__setattr__(
            self,
            "source_refs",
            _unique_text_tuple(self.source_refs, "source_refs"),
        )


@dataclass(frozen=True)
class WorkoutComponentIntent:
    """One ordered component of an intentionally multisport workout."""

    discipline: str
    order: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "discipline",
            _required_text(self.discipline, "component.discipline"),
        )
        if not isinstance(self.order, int) or self.order <= 0:
            raise PlanningContractError("component.order must be a positive integer")


@dataclass(frozen=True)
class PlannedTrainingWorkout:
    """Immutable training content selected by the future solver."""

    workout_id: str
    local_date: date
    recipe_id: str
    dose_option_id: str
    obligation_contributions: tuple[ObligationContribution, ...]
    components: tuple[WorkoutComponentIntent, ...]
    load_dimensions: tuple[LoadDimensionExposure, ...]
    quantitative_load: tuple[LoadEstimate, ...]
    source_refs: tuple[str, ...]
    within_day_order: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "workout_id",
            _required_text(self.workout_id, "workout_id"),
        )
        object.__setattr__(self, "recipe_id", _required_text(self.recipe_id, "recipe_id"))
        object.__setattr__(
            self,
            "dose_option_id",
            _required_text(self.dose_option_id, "dose_option_id"),
        )
        if not isinstance(self.local_date, date):
            raise PlanningContractError("workout.local_date must be a date")

        contributions = tuple(self.obligation_contributions)
        if not contributions:
            raise PlanningContractError(
                "workout must declare at least one obligation contribution"
            )
        if len({item.obligation_id for item in contributions}) != len(contributions):
            raise PlanningContractError(
                "workout contains duplicate contribution for one obligation"
            )
        object.__setattr__(self, "obligation_contributions", contributions)
        object.__setattr__(
            self,
            "source_refs",
            _unique_text_tuple(self.source_refs, "source_refs"),
        )

        components = tuple(self.components)
        if not components:
            raise PlanningContractError("workout must contain at least one component")
        orders = [item.order for item in components]
        if len(set(orders)) != len(orders):
            raise PlanningContractError("workout component orders must be unique")
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise PlanningContractError(
                "workout component order must be contiguous starting at 1"
            )
        object.__setattr__(
            self,
            "components",
            tuple(sorted(components, key=lambda item: item.order)),
        )

        dimensions = tuple(self.load_dimensions)
        if not dimensions:
            raise PlanningContractError("workout must declare load_dimensions")
        if len({item.dimension for item in dimensions}) != len(dimensions):
            raise PlanningContractError("workout contains duplicate load dimension")
        object.__setattr__(self, "load_dimensions", dimensions)

        quantitative = tuple(self.quantitative_load)
        semantic_keys = [
            (item.scope, item.subject, item.metric, item.unit)
            for item in quantitative
        ]
        if len(set(semantic_keys)) != len(semantic_keys):
            raise PlanningContractError(
                "workout contains duplicate quantitative load metric/unit"
            )
        object.__setattr__(self, "quantitative_load", quantitative)

        if self.within_day_order is not None:
            if not isinstance(self.within_day_order, int) or self.within_day_order <= 0:
                raise PlanningContractError(
                    "workout.within_day_order must be a positive integer when supplied"
                )


@dataclass(frozen=True)
class ApprovedWorkoutOption:
    """Planning projection of one approved recipe+dose catalog option."""

    recipe_id: str
    dose_option_id: str
    capabilities: tuple[str, ...]
    components: tuple[WorkoutComponentIntent, ...]
    load_dimensions: tuple[LoadDimensionExposure, ...]
    quantitative_load: tuple[LoadEstimate, ...]
    source_refs: tuple[str, ...]
    development_character: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipe_id", _required_text(self.recipe_id, "catalog.recipe_id"))
        object.__setattr__(
            self,
            "dose_option_id",
            _required_text(self.dose_option_id, "catalog.dose_option_id"),
        )
        object.__setattr__(
            self,
            "capabilities",
            _unique_text_tuple(self.capabilities, "catalog.capabilities"),
        )
        object.__setattr__(
            self,
            "source_refs",
            _unique_text_tuple(self.source_refs, "catalog.source_refs"),
        )

        components = tuple(self.components)
        if not components:
            raise PlanningContractError("catalog option must contain components")
        orders = [item.order for item in components]
        if len(set(orders)) != len(orders) or sorted(orders) != list(range(1, len(orders) + 1)):
            raise PlanningContractError(
                "catalog component order must be unique and contiguous starting at 1"
            )
        object.__setattr__(
            self,
            "components",
            tuple(sorted(components, key=lambda item: item.order)),
        )

        dimensions = tuple(self.load_dimensions)
        if not dimensions:
            raise PlanningContractError("catalog option must declare load_dimensions")
        if len({item.dimension for item in dimensions}) != len(dimensions):
            raise PlanningContractError("catalog option contains duplicate load dimension")
        object.__setattr__(self, "load_dimensions", dimensions)

        quantitative = tuple(self.quantitative_load)
        semantic_keys = [
            (item.scope, item.subject, item.metric, item.unit)
            for item in quantitative
        ]
        if len(set(semantic_keys)) != len(semantic_keys):
            raise PlanningContractError(
                "catalog option contains duplicate quantitative load semantic"
            )
        object.__setattr__(self, "quantitative_load", quantitative)

    @property
    def option_key(self) -> tuple[str, str]:
        return self.recipe_id, self.dose_option_id


@dataclass(frozen=True)
class PlanContent:
    """Exact immutable training prescription for one affected planning window."""

    source_revision: str
    strategy_revision_id: str
    affected_from: date
    affected_until: date
    workouts: tuple[PlannedTrainingWorkout, ...]
    fixed_commitments: tuple[FixedLoadCommitment, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_revision",
            _required_text(self.source_revision, "plan.source_revision"),
        )
        object.__setattr__(
            self,
            "strategy_revision_id",
            _required_text(self.strategy_revision_id, "plan.strategy_revision_id"),
        )
        if not isinstance(self.affected_from, date) or not isinstance(self.affected_until, date):
            raise PlanningContractError("plan affected_from and affected_until must be dates")
        if self.affected_until < self.affected_from:
            raise PlanningContractError("plan affected_until cannot precede affected_from")

        workouts = tuple(self.workouts)
        if len({item.workout_id for item in workouts}) != len(workouts):
            raise PlanningContractError("plan contains duplicate workout_id")
        for workout in workouts:
            if not self.affected_from <= workout.local_date <= self.affected_until:
                raise PlanningContractError(
                    f"workout {workout.workout_id} lies outside affected window"
                )

        per_day_orders: dict[date, set[int]] = {}
        for workout in workouts:
            if workout.within_day_order is None:
                continue
            used = per_day_orders.setdefault(workout.local_date, set())
            if workout.within_day_order in used:
                raise PlanningContractError(
                    f"duplicate within_day_order on {workout.local_date.isoformat()}"
                )
            used.add(workout.within_day_order)
        object.__setattr__(self, "workouts", workouts)

        commitments = tuple(self.fixed_commitments)
        if len({item.commitment_id for item in commitments}) != len(commitments):
            raise PlanningContractError("plan contains duplicate fixed commitment_id")
        for commitment in commitments:
            if not self.affected_from <= commitment.local_date <= self.affected_until:
                raise PlanningContractError(
                    f"fixed commitment {commitment.commitment_id} lies outside affected window"
                )
        object.__setattr__(self, "fixed_commitments", commitments)


class EligibilityKind(str, Enum):
    ESTABLISH = "establish"
    HOLD = "hold"
    PROGRESS = "progress"
    REDUCE = "reduce"


class SameDayOrderRule(str, Enum):
    ANY = "any"
    FORBIDDEN = "forbidden"
    FIRST_BEFORE_SECOND = "first_before_second"
    SECOND_BEFORE_FIRST = "second_before_first"


@dataclass(frozen=True)
class OptionEligibility:
    """Athlete-specific permission to use one approved recipe/dose option."""

    recipe_id: str
    dose_option_id: str
    capability: str
    kind: EligibilityKind
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipe_id", _required_text(self.recipe_id, "eligibility.recipe_id"))
        object.__setattr__(
            self,
            "dose_option_id",
            _required_text(self.dose_option_id, "eligibility.dose_option_id"),
        )
        object.__setattr__(
            self,
            "capability",
            _required_text(self.capability, "eligibility.capability"),
        )
        if not isinstance(self.kind, EligibilityKind):
            raise PlanningContractError("eligibility.kind must be EligibilityKind")
        object.__setattr__(
            self,
            "source_refs",
            _unique_text_tuple(self.source_refs, "eligibility.source_refs"),
        )

    @property
    def option_key(self) -> tuple[str, str]:
        return self.recipe_id, self.dose_option_id


@dataclass(frozen=True)
class DailyAvailability:
    """Hard athlete-declared availability for one local date."""

    local_date: date
    available: bool
    source_refs: tuple[str, ...]
    max_sessions: int | None = None
    max_duration_minutes: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.local_date, date):
            raise PlanningContractError("availability.local_date must be a date")
        object.__setattr__(
            self,
            "source_refs",
            _unique_text_tuple(self.source_refs, "availability.source_refs"),
        )
        if self.max_sessions is not None:
            if not isinstance(self.max_sessions, int) or self.max_sessions < 0:
                raise PlanningContractError("availability.max_sessions must be >= 0")
        if self.max_duration_minutes is not None:
            if (
                isinstance(self.max_duration_minutes, bool)
                or not isinstance(self.max_duration_minutes, (int, float))
                or float(self.max_duration_minutes) < 0
            ):
                raise PlanningContractError(
                    "availability.max_duration_minutes must be numeric and >= 0"
                )
        if not self.available:
            if self.max_sessions not in (None, 0):
                raise PlanningContractError(
                    "unavailable day cannot declare positive max_sessions"
                )
            if self.max_duration_minutes not in (None, 0):
                raise PlanningContractError(
                    "unavailable day cannot declare positive max_duration_minutes"
                )


@dataclass(frozen=True)
class ObservedLoadExposure:
    """One canonical completed-load exposure.

    Categorical compatibility load and quantitative aggregate load live on the
    same immutable exposure so history cannot be complete in one load layer and
    silently missing in another.
    """

    exposure_id: str
    local_date: date
    load_dimensions: tuple[LoadDimensionExposure, ...]
    source_refs: tuple[str, ...]
    quantitative_load: tuple[LoadEstimate, ...] = ()
    within_day_order: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "exposure_id",
            _required_text(self.exposure_id, "observed_exposure.exposure_id"),
        )
        if not isinstance(self.local_date, date):
            raise PlanningContractError("observed_exposure.local_date must be a date")
        dimensions = tuple(self.load_dimensions)
        if not dimensions:
            raise PlanningContractError("observed exposure must declare load_dimensions")
        if len({item.dimension for item in dimensions}) != len(dimensions):
            raise PlanningContractError(
                "observed exposure contains duplicate load dimension"
            )
        object.__setattr__(self, "load_dimensions", dimensions)
        quantitative = tuple(self.quantitative_load)
        semantic_keys = [
            (item.scope, item.subject, item.metric, item.unit)
            for item in quantitative
        ]
        if len(set(semantic_keys)) != len(semantic_keys):
            raise PlanningContractError(
                "observed exposure contains duplicate quantitative load semantic"
            )
        object.__setattr__(self, "quantitative_load", quantitative)
        object.__setattr__(
            self,
            "source_refs",
            _unique_text_tuple(self.source_refs, "observed_exposure.source_refs"),
        )
        if self.within_day_order is not None:
            if not isinstance(self.within_day_order, int) or self.within_day_order <= 0:
                raise PlanningContractError(
                    "observed_exposure.within_day_order must be a positive integer"
                )


@dataclass(frozen=True)
class LoadCompatibilityRule:
    """Generic hard interaction rule between two load dimensions.

    min_calendar_separation_days is the symmetric default. Optional directional
    overrides let the model express different recovery interaction depending on
    which load occurs first without introducing sport/day-specific rules.
    """

    rule_id: str
    first_dimension: str
    first_min_level: LoadDimensionLevel
    second_dimension: str
    second_min_level: LoadDimensionLevel
    min_calendar_separation_days: int
    same_day_order: SameDayOrderRule
    source_refs: tuple[str, ...]
    min_first_to_second_days: int | None = None
    min_second_to_first_days: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _required_text(self.rule_id, "compatibility.rule_id"))
        object.__setattr__(
            self,
            "first_dimension",
            _required_text(self.first_dimension, "compatibility.first_dimension"),
        )
        object.__setattr__(
            self,
            "second_dimension",
            _required_text(self.second_dimension, "compatibility.second_dimension"),
        )
        if not isinstance(self.first_min_level, LoadDimensionLevel):
            raise PlanningContractError(
                "compatibility.first_min_level must be LoadDimensionLevel"
            )
        if not isinstance(self.second_min_level, LoadDimensionLevel):
            raise PlanningContractError(
                "compatibility.second_min_level must be LoadDimensionLevel"
            )
        if (
            not isinstance(self.min_calendar_separation_days, int)
            or self.min_calendar_separation_days < 0
        ):
            raise PlanningContractError(
                "compatibility.min_calendar_separation_days must be >= 0"
            )
        if not isinstance(self.same_day_order, SameDayOrderRule):
            raise PlanningContractError(
                "compatibility.same_day_order must be SameDayOrderRule"
            )
        for field in (
            "min_first_to_second_days",
            "min_second_to_first_days",
        ):
            value = getattr(self, field)
            if value is not None and (
                not isinstance(value, int) or value < 0
            ):
                raise PlanningContractError(
                    f"compatibility.{field} must be >= 0 when supplied"
                )
        object.__setattr__(
            self,
            "source_refs",
            _unique_text_tuple(self.source_refs, "compatibility.source_refs"),
        )

    @property
    def first_to_second_days(self) -> int:
        return (
            self.min_calendar_separation_days
            if self.min_first_to_second_days is None
            else self.min_first_to_second_days
        )

    @property
    def second_to_first_days(self) -> int:
        return (
            self.min_calendar_separation_days
            if self.min_second_to_first_days is None
            else self.min_second_to_first_days
        )

    @property
    def max_separation_days(self) -> int:
        return max(self.first_to_second_days, self.second_to_first_days)


@dataclass(frozen=True)
class LoadCompatibilityPolicy:
    """Versioned generic categorical-load interaction policy."""

    policy_id: str
    rules: tuple[LoadCompatibilityRule, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _required_text(self.policy_id, "compatibility.policy_id"))
        rules = tuple(self.rules)
        if len({item.rule_id for item in rules}) != len(rules):
            raise PlanningContractError("compatibility policy contains duplicate rule_id")
        object.__setattr__(self, "rules", rules)
        object.__setattr__(
            self,
            "source_refs",
            _unique_text_tuple(self.source_refs, "compatibility.source_refs"),
        )


@dataclass(frozen=True)
class CoverageRule:
    """Exact partial/full credit from one capability toward an obligation.

    Rational credit avoids hidden floating-point semantics. Examples:
    1/1 = full credit, 1/2 = half exposure credit.
    """

    source_capability: str
    credit_numerator: int
    credit_denominator: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_capability",
            _required_text(self.source_capability, "coverage.source_capability"),
        )
        if not isinstance(self.credit_numerator, int) or self.credit_numerator <= 0:
            raise PlanningContractError("coverage.credit_numerator must be a positive integer")
        if not isinstance(self.credit_denominator, int) or self.credit_denominator <= 0:
            raise PlanningContractError("coverage.credit_denominator must be a positive integer")
        if self.credit_numerator > self.credit_denominator:
            raise PlanningContractError("coverage credit cannot exceed one full exposure")

    @property
    def exact_credit(self) -> tuple[int, int]:
        return self.credit_numerator, self.credit_denominator


@dataclass(frozen=True)
class PlanningObligation:
    """One bounded training obligation from an immutable StrategyRevision."""

    obligation_id: str
    capability: str
    role: str
    priority_tier: int
    min_exposures: int
    max_exposures: int
    recipe_family: tuple[str, ...]
    valid_from: date
    valid_until: date
    source_refs: tuple[str, ...]
    progression_axes: tuple[str, ...] = ()
    partial_coverage: tuple[CoverageRule, ...] = ()
    prefer_character_variation: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "obligation_id", _required_text(self.obligation_id, "obligation_id"))
        object.__setattr__(self, "capability", _required_text(self.capability, "capability"))
        object.__setattr__(self, "role", _required_text(self.role, "role"))

        if not isinstance(self.priority_tier, int) or self.priority_tier < 0:
            raise PlanningContractError("priority_tier must be a non-negative integer")
        if not isinstance(self.min_exposures, int) or self.min_exposures < 0:
            raise PlanningContractError("min_exposures must be a non-negative integer")
        if not isinstance(self.max_exposures, int) or self.max_exposures < 0:
            raise PlanningContractError("max_exposures must be a non-negative integer")
        if self.max_exposures < self.min_exposures:
            raise PlanningContractError("max_exposures cannot be lower than min_exposures")
        if self.max_exposures == 0:
            raise PlanningContractError("an obligation with max_exposures=0 must not exist")

        object.__setattr__(
            self,
            "recipe_family",
            _unique_text_tuple(self.recipe_family, "recipe_family"),
        )
        object.__setattr__(
            self,
            "source_refs",
            _unique_text_tuple(self.source_refs, "source_refs"),
        )
        object.__setattr__(
            self,
            "progression_axes",
            _unique_text_tuple(
                self.progression_axes,
                "progression_axes",
                allow_empty=True,
            ),
        )

        if not isinstance(self.valid_from, date) or not isinstance(self.valid_until, date):
            raise PlanningContractError("valid_from and valid_until must be dates")
        if self.valid_until < self.valid_from:
            raise PlanningContractError("valid_until cannot precede valid_from")

        coverage = tuple(self.partial_coverage)
        if len({rule.source_capability for rule in coverage}) != len(coverage):
            raise PlanningContractError("partial_coverage contains duplicate source_capability")
        if any(rule.source_capability == self.capability for rule in coverage):
            raise PlanningContractError(
                "partial_coverage must not restate the obligation's own capability"
            )
        object.__setattr__(self, "partial_coverage", coverage)

    def active_on(self, day: date) -> bool:
        return self.valid_from <= day <= self.valid_until


@dataclass(frozen=True)
class LoadBound:
    """One aggregate load ceiling with explicit metric, unit and provenance."""

    bound_id: str
    scope: str
    subject: str
    metric: str
    unit: str
    window_days: int
    max_value: float
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bound_id", _required_text(self.bound_id, "bound_id"))
        object.__setattr__(self, "scope", _required_text(self.scope, "scope"))
        object.__setattr__(self, "subject", _required_text(self.subject, "subject"))
        object.__setattr__(self, "metric", _required_text(self.metric, "metric"))
        object.__setattr__(self, "unit", _required_text(self.unit, "unit"))

        if not isinstance(self.window_days, int) or self.window_days <= 0:
            raise PlanningContractError("window_days must be a positive integer")
        if isinstance(self.max_value, bool) or not isinstance(self.max_value, (int, float)):
            raise PlanningContractError("max_value must be numeric")
        if float(self.max_value) < 0:
            raise PlanningContractError("max_value must be >= 0")

        object.__setattr__(
            self,
            "provenance_refs",
            _unique_text_tuple(self.provenance_refs, "provenance_refs"),
        )

    @property
    def semantic_key(self) -> tuple[str, str, str, str, int]:
        return self.scope, self.subject, self.metric, self.unit, self.window_days


@dataclass(frozen=True)
class AggregateLoadEnvelope:
    """Versioned set of aggregate ceilings used by one StrategyRevision."""

    envelope_id: str
    bounds: tuple[LoadBound, ...]
    unknown_policy: UnknownAggregatePolicy
    established_baseline_ref: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "envelope_id", _required_text(self.envelope_id, "envelope_id"))
        object.__setattr__(
            self,
            "established_baseline_ref",
            _required_text(self.established_baseline_ref, "established_baseline_ref"),
        )
        object.__setattr__(
            self,
            "source_refs",
            _unique_text_tuple(self.source_refs, "source_refs"),
        )

        bounds = tuple(self.bounds)
        if not bounds:
            raise PlanningContractError("aggregate load envelope must contain at least one bound")
        if len({bound.bound_id for bound in bounds}) != len(bounds):
            raise PlanningContractError("aggregate load envelope contains duplicate bound_id")
        if len({bound.semantic_key for bound in bounds}) != len(bounds):
            raise PlanningContractError(
                "aggregate load envelope contains duplicate semantic bounds"
            )
        object.__setattr__(self, "bounds", bounds)

        if not isinstance(self.unknown_policy, UnknownAggregatePolicy):
            raise PlanningContractError("unknown_policy must be UnknownAggregatePolicy")


@dataclass(frozen=True)
class StrategyRevision:
    """Immutable strategic input consumed by the execution solver."""

    revision_id: str
    goal_set_hash: str
    valid_from: date
    valid_until: date
    obligations: tuple[PlanningObligation, ...]
    load_envelope: AggregateLoadEnvelope
    source_refs: tuple[str, ...]
    accepted_by: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "revision_id", _required_text(self.revision_id, "revision_id"))
        object.__setattr__(self, "goal_set_hash", _required_text(self.goal_set_hash, "goal_set_hash"))
        object.__setattr__(self, "accepted_by", _required_text(self.accepted_by, "accepted_by"))
        object.__setattr__(
            self,
            "source_refs",
            _unique_text_tuple(self.source_refs, "source_refs"),
        )

        if not isinstance(self.valid_from, date) or not isinstance(self.valid_until, date):
            raise PlanningContractError("strategy valid_from and valid_until must be dates")
        if self.valid_until < self.valid_from:
            raise PlanningContractError("strategy valid_until cannot precede valid_from")

        obligations = tuple(self.obligations)
        if not obligations:
            raise PlanningContractError("strategy revision must contain at least one obligation")
        if len({item.obligation_id for item in obligations}) != len(obligations):
            raise PlanningContractError("strategy revision contains duplicate obligation_id")
        for obligation in obligations:
            if obligation.valid_from < self.valid_from or obligation.valid_until > self.valid_until:
                raise PlanningContractError(
                    f"obligation {obligation.obligation_id} lies outside strategy validity"
                )
        object.__setattr__(self, "obligations", obligations)

        if not isinstance(self.load_envelope, AggregateLoadEnvelope):
            raise PlanningContractError("load_envelope must be AggregateLoadEnvelope")


@dataclass(frozen=True)
class PlanAuthorityState:
    """Authoritative planning-state head for one canonical source revision.

    CURRENT means a validated immutable PlanContent exists for exactly this
    revision. BLOCKED means no mutable future prescription is authoritative for
    the affected window at this revision.
    """

    status: PlanAuthorityStatus
    source_revision: str
    semantic_input_hash: str
    strategy_revision_id: str
    engine_version: str
    affected_from: date
    affected_until: date
    plan_content_hash: str | None = None
    previous_valid_plan_hash: str | None = None
    blocked_reason_codes: tuple[str, ...] = ()
    invalidated_workout_keys: tuple[str, ...] = ()
    requires_user_input: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.status, PlanAuthorityStatus):
            raise PlanningContractError("status must be PlanAuthorityStatus")

        for field in (
            "source_revision",
            "semantic_input_hash",
            "strategy_revision_id",
            "engine_version",
        ):
            object.__setattr__(self, field, _required_text(getattr(self, field), field))

        if not isinstance(self.affected_from, date) or not isinstance(self.affected_until, date):
            raise PlanningContractError("affected_from and affected_until must be dates")
        if self.affected_until < self.affected_from:
            raise PlanningContractError("affected_until cannot precede affected_from")

        reasons = _unique_text_tuple(
            self.blocked_reason_codes,
            "blocked_reason_codes",
            allow_empty=True,
        )
        invalidated = _unique_text_tuple(
            self.invalidated_workout_keys,
            "invalidated_workout_keys",
            allow_empty=True,
        )
        object.__setattr__(self, "blocked_reason_codes", reasons)
        object.__setattr__(self, "invalidated_workout_keys", invalidated)

        if self.previous_valid_plan_hash is not None:
            object.__setattr__(
                self,
                "previous_valid_plan_hash",
                _required_text(self.previous_valid_plan_hash, "previous_valid_plan_hash"),
            )

        if self.status is PlanAuthorityStatus.CURRENT:
            object.__setattr__(
                self,
                "plan_content_hash",
                _required_text(self.plan_content_hash or "", "plan_content_hash"),
            )
            if reasons:
                raise PlanningContractError("CURRENT state cannot have blocked_reason_codes")
            if invalidated:
                raise PlanningContractError("CURRENT state cannot invalidate workout keys")
            if self.requires_user_input:
                raise PlanningContractError("CURRENT state cannot require user input")
        else:
            if self.plan_content_hash is not None:
                raise PlanningContractError("BLOCKED state cannot expose current plan_content_hash")
            if not reasons:
                raise PlanningContractError("BLOCKED state requires blocked_reason_codes")

    def is_fresh_for(self, source_revision: str) -> bool:
        return self.source_revision == str(source_revision or "").strip()

    @property
    def has_current_prescription(self) -> bool:
        return self.status is PlanAuthorityStatus.CURRENT
