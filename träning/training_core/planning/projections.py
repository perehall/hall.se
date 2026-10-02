"""Shadow-input readiness gate for Planning Engine v1.

This module does not derive missing planning semantics. It only verifies that
all canonical V1 projections already exist as explicit typed domain values.
Legacy planner output is intentionally not accepted as a fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .objectives import ObjectivePolicy
from .models import (
    ApprovedWorkoutOption,
    DailyAvailability,
    FixedLoadCommitment,
    LoadCompatibilityPolicy,
    ObservedLoadExposure,
    ObservedObligationCredit,
    OptionEligibility,
    PlanningContractError,
    StrategyRevision,
)


class ProjectionKind(str, Enum):
    STRATEGY = "strategy_revision"
    WORKOUT_OPTIONS = "approved_workout_options"
    OPTION_ELIGIBILITY = "option_eligibility"
    OBSERVED_CREDITS = "observed_obligation_credits"
    OBSERVED_LOAD = "observed_load_exposures"
    FIXED_COMMITMENTS = "fixed_commitments"
    AVAILABILITY = "availability"
    CLOSED_DATES = "closed_dates"
    COMPATIBILITY = "load_compatibility_policy"
    OBJECTIVE_POLICY = "objective_policy"


@dataclass(frozen=True)
class ShadowProjectionBundle:
    """Explicit canonical projections required before a live shadow solve."""

    source_revision: str
    strategy: StrategyRevision | None = None
    workout_options: tuple[ApprovedWorkoutOption, ...] | None = None
    option_eligibility: tuple[OptionEligibility, ...] | None = None
    observed_credits: tuple[ObservedObligationCredit, ...] | None = None
    observed_load: tuple[ObservedLoadExposure, ...] | None = None
    fixed_commitments: tuple[FixedLoadCommitment, ...] | None = None
    availability: tuple[DailyAvailability, ...] | None = None
    closed_dates: tuple[date, ...] | None = None
    compatibility_policy: LoadCompatibilityPolicy | None = None
    objective_policy: ObjectivePolicy | None = None
    prewindow_load_context_from: date | None = None
    prewindow_load_context_through: date | None = None

    def __post_init__(self) -> None:
        revision = str(self.source_revision or "").strip()
        if not revision:
            raise PlanningContractError(
                "shadow projection source_revision must be non-empty"
            )
        object.__setattr__(self, "source_revision", revision)


@dataclass(frozen=True)
class ProjectionBlocker:
    kind: ProjectionKind
    code: str
    message: str


@dataclass(frozen=True)
class ShadowReadinessReport:
    source_revision: str
    ready: bool
    blockers: tuple[ProjectionBlocker, ...]

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.blockers)


def _missing(kind: ProjectionKind, message: str) -> ProjectionBlocker:
    return ProjectionBlocker(
        kind=kind,
        code=f"MISSING_{kind.value.upper()}",
        message=message,
    )


def assess_shadow_readiness(
    bundle: ShadowProjectionBundle,
) -> ShadowReadinessReport:
    blockers: list[ProjectionBlocker] = []

    if bundle.strategy is None:
        blockers.append(
            _missing(
                ProjectionKind.STRATEGY,
                "Accepted StrategyRevision with bounded obligations and aggregate load envelope is missing.",
            )
        )
    else:
        if not bundle.strategy.obligations:
            blockers.append(
                ProjectionBlocker(
                    ProjectionKind.STRATEGY,
                    "STRATEGY_WITHOUT_BOUNDED_OBLIGATIONS",
                    "StrategyRevision must contain explicit bounded obligations.",
                )
            )
        if not bundle.strategy.load_envelope.bounds:
            blockers.append(
                ProjectionBlocker(
                    ProjectionKind.STRATEGY,
                    "STRATEGY_WITHOUT_LOAD_ENVELOPE",
                    "StrategyRevision must contain an explicit aggregate load envelope.",
                )
            )

    if bundle.workout_options is None:
        blockers.append(
            _missing(
                ProjectionKind.WORKOUT_OPTIONS,
                "Approved workout options have not been projected into V1 load/dose semantics.",
            )
        )
    elif not bundle.workout_options:
        blockers.append(
            ProjectionBlocker(
                ProjectionKind.WORKOUT_OPTIONS,
                "EMPTY_APPROVED_WORKOUT_OPTIONS",
                "At least one explicit approved workout option is required for shadow planning.",
            )
        )

    if bundle.option_eligibility is None:
        blockers.append(
            _missing(
                ProjectionKind.OPTION_ELIGIBILITY,
                "Athlete-specific option eligibility has not been materialized from canonical athlete state.",
            )
        )

    # Empty observed/fixed/availability collections are valid facts. Missing
    # projections are represented by None and are not interchangeable with [].
    if bundle.observed_credits is None:
        blockers.append(
            _missing(
                ProjectionKind.OBSERVED_CREDITS,
                "Observed obligation-credit projection is missing.",
            )
        )
    if bundle.observed_load is None:
        blockers.append(
            _missing(
                ProjectionKind.OBSERVED_LOAD,
                "Observed categorical/quantitative load projection is missing.",
            )
        )
    if bundle.fixed_commitments is None:
        blockers.append(
            _missing(
                ProjectionKind.FIXED_COMMITMENTS,
                "Fixed-commitment projection is missing.",
            )
        )
    if bundle.availability is None:
        blockers.append(
            _missing(
                ProjectionKind.AVAILABILITY,
                "Declared availability projection is missing.",
            )
        )
    if bundle.closed_dates is None:
        blockers.append(
            _missing(
                ProjectionKind.CLOSED_DATES,
                "Closed-date projection is missing.",
            )
        )
    if bundle.compatibility_policy is None:
        blockers.append(
            _missing(
                ProjectionKind.COMPATIBILITY,
                "Explicit generic load-compatibility policy is missing.",
            )
        )
    if bundle.objective_policy is None:
        blockers.append(
            _missing(
                ProjectionKind.OBJECTIVE_POLICY,
                "Explicit schedule/spacing objective policy is missing.",
            )
        )

    return ShadowReadinessReport(
        source_revision=bundle.source_revision,
        ready=not blockers,
        blockers=tuple(blockers),
    )
