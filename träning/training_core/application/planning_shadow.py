"""Non-authoritative shadow orchestration for Planning Engine v1.

Shadow mode proves that canonical V1 projections are sufficient to run the pure
solver. It has deliberately no persistence, provider, renderer or device-sync
authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from training_core.planning.candidate_generation import CandidateGenerationLimits
from training_core.planning.models import PlanContent
from training_core.planning.projections import (
    ShadowProjectionBundle,
    ShadowReadinessReport,
    assess_shadow_readiness,
)
from training_core.planning.solver import (
    PlanningSolveRequest,
    PlanningSolveResult,
    solve_planning_window,
)
from training_core.planning.validation import PlanValidationContext


@dataclass(frozen=True)
class ShadowPlanningRunInput:
    affected_from: date
    affected_until: date
    history_from: date
    history_through: date
    future_context_through: date
    projections: ShadowProjectionBundle
    closed_dates: tuple[date, ...] = ()
    previous_plan: PlanContent | None = None
    generation_limits: CandidateGenerationLimits = CandidateGenerationLimits()


@dataclass(frozen=True)
class ShadowPlanningRunResult:
    readiness: ShadowReadinessReport
    solve_result: PlanningSolveResult | None

    @property
    def ran_solver(self) -> bool:
        return self.solve_result is not None


def run_shadow_planning(
    request: ShadowPlanningRunInput,
) -> ShadowPlanningRunResult:
    """Run the pure planner only when every canonical V1 projection is explicit."""

    readiness = assess_shadow_readiness(request.projections)
    if not readiness.ready:
        return ShadowPlanningRunResult(
            readiness=readiness,
            solve_result=None,
        )

    bundle = request.projections
    # Readiness above proves these are not None. Keep assertions local so a
    # static/type checker sees the same invariant without adding fallback data.
    assert bundle.strategy is not None
    assert bundle.workout_options is not None
    assert bundle.option_eligibility is not None
    assert bundle.observed_credits is not None
    assert bundle.observed_load is not None
    assert bundle.fixed_commitments is not None
    assert bundle.availability is not None
    assert bundle.compatibility_policy is not None
    assert bundle.objective_policy is not None

    context = PlanValidationContext(
        source_revision=bundle.source_revision,
        history_from=request.history_from,
        history_through=request.history_through,
        future_context_through=request.future_context_through,
        strategy=bundle.strategy,
        catalog_options=bundle.workout_options,
        option_eligibility=bundle.option_eligibility,
        fixed_commitments=bundle.fixed_commitments,
        compatibility_policy=bundle.compatibility_policy,
        availability=bundle.availability,
        closed_dates=request.closed_dates,
        observed_obligation_credits=bundle.observed_credits,
        observed_load_exposures=bundle.observed_load,
    )
    solve_result = solve_planning_window(
        PlanningSolveRequest(
            affected_from=request.affected_from,
            affected_until=request.affected_until,
            validation_context=context,
            objective_policy=bundle.objective_policy,
            previous_plan=request.previous_plan,
            generation_limits=request.generation_limits,
        )
    )
    return ShadowPlanningRunResult(
        readiness=readiness,
        solve_result=solve_result,
    )
