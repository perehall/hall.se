"""Planning Engine v1 domain boundary.

This package is intentionally independent from the legacy adaptive planner.
Only typed contracts live here until the new solver is implemented.
"""

from .content import plan_content_hash, semantic_plan_payload
from .models import (
    AggregateLoadEnvelope,
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
    PlanAuthorityState,
    PlanAuthorityStatus,
    PlanContent,
    PlannedTrainingWorkout,
    PlanningContractError,
    PlanningObligation,
    StrategyRevision,
    UnknownAggregatePolicy,
    WorkoutComponentIntent,
)

__all__ = [
    "AggregateLoadEnvelope",
    "ContributionKind",
    "CoverageRule",
    "FixedLoadCommitment",
    "LoadBound",
    "LoadDimensionExposure",
    "LoadDimensionLevel",
    "LoadEstimate",
    "ObligationContribution",
    "ObservedLoadSample",
    "ObservedObligationCredit",
    "PlanAuthorityState",
    "PlanAuthorityStatus",
    "PlanContent",
    "PlannedTrainingWorkout",
    "PlanningContractError",
    "PlanningObligation",
    "StrategyRevision",
    "UnknownAggregatePolicy",
    "WorkoutComponentIntent",
    "plan_content_hash",
    "semantic_plan_payload",
]
