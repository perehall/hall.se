"""Planning Engine v1 domain boundary.

This package is intentionally independent from the legacy adaptive planner.
Contracts, candidate generation, hard validation and deterministic selection
live here without persistence/provider/presentation dependencies.
"""

from .content import plan_content_hash, semantic_plan_payload
from .models import (
    AggregateLoadEnvelope,
    ApprovedWorkoutOption,
    ContributionKind,
    CoverageRule,
    DailyAvailability,
    EligibilityKind,
    FixedLoadCommitment,
    LoadBound,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    LoadCompatibilityPolicy,
    LoadCompatibilityRule,
    ObligationContribution,
    ObservedLoadExposure,
    ObservedObligationCredit,
    OptionEligibility,
    PlanAuthorityState,
    PlanAuthorityStatus,
    PlanContent,
    PlannedTrainingWorkout,
    PlanningContractError,
    PlanningObligation,
    StrategyRevision,
    SameDayOrderRule,
    UnknownAggregatePolicy,
    WorkoutComponentIntent,
    WorkoutPlacementConstraint,
)

__all__ = [
    "AggregateLoadEnvelope",
    "ApprovedWorkoutOption",
    "ContributionKind",
    "CoverageRule",
    "DailyAvailability",
    "EligibilityKind",
    "FixedLoadCommitment",
    "LoadBound",
    "LoadDimensionExposure",
    "LoadDimensionLevel",
    "LoadEstimate",
    "LoadCompatibilityPolicy",
    "LoadCompatibilityRule",
    "ObligationContribution",
    "ObservedLoadExposure",
    "ObservedObligationCredit",
    "OptionEligibility",
    "PlanAuthorityState",
    "PlanAuthorityStatus",
    "PlanContent",
    "PlannedTrainingWorkout",
    "PlanningContractError",
    "PlanningObligation",
    "StrategyRevision",
    "SameDayOrderRule",
    "UnknownAggregatePolicy",
    "WorkoutComponentIntent",
    "WorkoutPlacementConstraint",
    "plan_content_hash",
    "semantic_plan_payload",
    "PlanValidationContext",
    "ValidationIssue",
    "ValidationReport",
    "validate_plan_content",
    "DoubleSessionPreference",
    "ObjectiveContext",
    "ObjectivePolicy",
    "ObjectiveVector",
    "SchedulePreferences",
    "SpacingPreference",
    "SpacingSubjectKind",
    "evaluate_objectives",
    "select_best_valid_plan",
    "CandidateGenerationLimits",
    "CandidateGenerationStats",
    "CandidateSearchLimitExceeded",
    "generate_candidate_atoms",
    "enumerate_candidate_plans",
    "ENGINE_VERSION",
    "PlanningSolveRequest",
    "PlanningSolveTrace",
    "PlanningSolveResult",
    "solve_planning_window",
    "planning_input_hash",
    "semantic_planning_input_payload",
    "PlanChangeKind",
    "UserPlanChange",
    "compile_plan_change",
    "merge_placement_constraints",
]

from .validation import (
    PlanValidationContext,
    ValidationIssue,
    ValidationReport,
    validate_plan_content,
)

from .objectives import (
    DoubleSessionPreference,
    ObjectiveContext,
    ObjectivePolicy,
    ObjectiveVector,
    SchedulePreferences,
    SpacingPreference,
    SpacingSubjectKind,
    evaluate_objectives,
    select_best_valid_plan,
)


from .candidate_generation import (
    CandidateGenerationLimits,
    CandidateGenerationStats,
    CandidateSearchLimitExceeded,
    enumerate_candidate_plans,
    generate_candidate_atoms,
)

from .solver import (
    ENGINE_VERSION,
    PlanningSolveRequest,
    PlanningSolveResult,
    PlanningSolveTrace,
    solve_planning_window,
)


from .input_hash import (
    planning_input_hash,
    semantic_planning_input_payload,
)


from .plan_changes import (
    PlanChangeKind,
    UserPlanChange,
    compile_plan_change,
    merge_placement_constraints,
)
