"""Deterministic complete-plan solver for Planning Engine v1 shadow mode.

The solver owns no persistence. It receives frozen canonical planning context,
enumerates the bounded anti-filler candidate domain, validates every exact
candidate through the independent final gate, and selects the lexicographic
optimum among valid plans.

A caller must still perform optimistic-concurrency checking at commit time.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from .candidate_generation import (
    CandidateGenerationLimits,
    CandidateGenerationStats,
    CandidateSearchLimitExceeded,
    enumerate_candidate_plans,
)
from .content import plan_content_hash
from .input_hash import planning_input_hash
from .models import (
    PlanAuthorityState,
    PlanAuthorityStatus,
    PlanContent,
    PlanningContractError,
)
from .objectives import (
    ObjectiveContext,
    ObjectivePolicy,
    ObjectiveVector,
    evaluate_objectives,
)
from .trace import (
    PlanChangeTrace,
    WorkoutDecisionTrace,
    build_plan_changes,
    build_workout_decisions,
)
from .validation import PlanValidationContext, validate_plan_content


ENGINE_VERSION = "planning-v1-solver-0.1"


@dataclass(frozen=True)
class PlanningSolveRequest:
    affected_from: date
    affected_until: date
    validation_context: PlanValidationContext
    objective_policy: ObjectivePolicy
    previous_plan: PlanContent | None = None
    engine_version: str = ENGINE_VERSION
    generation_limits: CandidateGenerationLimits = CandidateGenerationLimits()

    def __post_init__(self) -> None:
        if not isinstance(self.affected_from, date) or not isinstance(
            self.affected_until, date
        ):
            raise PlanningContractError("solve affected window must use dates")
        if self.affected_until < self.affected_from:
            raise PlanningContractError(
                "solve affected_until cannot precede affected_from"
            )
        if not str(self.engine_version or "").strip():
            raise PlanningContractError("engine_version must be non-empty")
        context = self.validation_context
        if self.affected_from < context.strategy.valid_from:
            raise PlanningContractError(
                "solve affected window starts before StrategyRevision"
            )
        if self.affected_until > context.strategy.valid_until:
            raise PlanningContractError(
                "solve affected window ends after StrategyRevision"
            )
        outside_constraints = [
            item.constraint_id
            for item in context.placement_constraints
            if not self.affected_from <= item.local_date <= self.affected_until
        ]
        if outside_constraints:
            raise PlanningContractError(
                "affected window must include every active placement constraint: "
                + ", ".join(sorted(outside_constraints))
            )

    @property
    def semantic_input_hash(self) -> str:
        return planning_input_hash(
            self.validation_context,
            self.objective_policy,
            self.affected_from,
            self.affected_until,
            self.previous_plan,
        )


@dataclass(frozen=True)
class PlanningSolveTrace:
    source_revision: str
    semantic_input_hash: str
    engine_version: str
    generation: CandidateGenerationStats
    candidates_considered: int
    valid_candidates: int
    rejected_candidates: int
    rejection_counts: tuple[tuple[str, int], ...]
    selected_plan_hash: str | None
    search_complete: bool = True
    optimality_proven: bool = True
    validation_contract: str = "planning-v1-final-validator"
    hard_constraint_refs: tuple[str, ...] = ()
    final_validation_codes: tuple[str, ...] = ()
    workout_decisions: tuple[WorkoutDecisionTrace, ...] = ()
    plan_changes: tuple[PlanChangeTrace, ...] = ()


@dataclass(frozen=True)
class PlanningSolveResult:
    authority_state: PlanAuthorityState
    plan: PlanContent | None
    objective_vector: ObjectiveVector | None
    trace: PlanningSolveTrace

    @property
    def blocked(self) -> bool:
        return self.authority_state.status is PlanAuthorityStatus.BLOCKED


def _objective_context(request: PlanningSolveRequest) -> ObjectiveContext:
    context = request.validation_context
    return ObjectiveContext(
        strategy=context.strategy,
        catalog_options=context.catalog_options,
        observed_obligation_credits=context.observed_obligation_credits,
        observed_load_exposures=context.observed_load_exposures,
        fixed_commitments=context.fixed_commitments,
        previous_plan=request.previous_plan,
        policy=request.objective_policy,
    )


def _hard_constraint_refs(context: PlanValidationContext) -> tuple[str, ...]:
    refs = []
    refs.extend(
        f"compatibility:{item.rule_id}"
        for item in context.compatibility_policy.rules
    )
    refs.extend(
        f"load_bound:{item.bound_id}"
        for item in context.strategy.load_envelope.bounds
    )
    refs.extend(
        f"placement:{item.constraint_id}"
        for item in context.placement_constraints
    )
    refs.extend(
        f"availability:{item.local_date.isoformat()}"
        for item in context.availability
    )
    refs.extend(
        f"closed:{item.isoformat()}"
        for item in context.closed_dates
    )
    return tuple(sorted(set(refs)))


def _invalidated_workout_ids(request: PlanningSolveRequest) -> tuple[str, ...]:
    if request.previous_plan is None:
        return ()
    return tuple(
        sorted(
            workout.workout_id
            for workout in request.previous_plan.workouts
            if request.affected_from
            <= workout.local_date
            <= request.affected_until
        )
    )


def solve_planning_window(request: PlanningSolveRequest) -> PlanningSolveResult:
    context = request.validation_context
    try:
        candidates, generation = enumerate_candidate_plans(
            context,
            request.affected_from,
            request.affected_until,
            request.generation_limits,
        )
    except CandidateSearchLimitExceeded as exc:
        authority = PlanAuthorityState(
            status=PlanAuthorityStatus.BLOCKED,
            source_revision=context.source_revision,
            semantic_input_hash=request.semantic_input_hash,
            strategy_revision_id=context.strategy.revision_id,
            engine_version=request.engine_version,
            affected_from=request.affected_from,
            affected_until=request.affected_until,
            previous_valid_plan_hash=(
                plan_content_hash(request.previous_plan)
                if request.previous_plan is not None
                else None
            ),
            blocked_reason_codes=(
                "SEARCH_SPACE_LIMIT_EXCEEDED",
                f"SEARCH_STAGE_{exc.stage.upper()}",
            ),
            invalidated_workout_keys=_invalidated_workout_ids(request),
            requires_user_input=False,
        )
        trace = PlanningSolveTrace(
            source_revision=context.source_revision,
            semantic_input_hash=request.semantic_input_hash,
            engine_version=request.engine_version,
            generation=exc.generation,
            candidates_considered=0,
            valid_candidates=0,
            rejected_candidates=0,
            rejection_counts=(
                (
                    "SEARCH_SPACE_LIMIT_EXCEEDED",
                    exc.observed,
                ),
            ),
            selected_plan_hash=None,
            search_complete=False,
            optimality_proven=False,
            hard_constraint_refs=_hard_constraint_refs(context),
        )
        return PlanningSolveResult(
            authority_state=authority,
            plan=None,
            objective_vector=None,
            trace=trace,
        )

    objective_context = _objective_context(request)

    valid: list[tuple[tuple, PlanContent, ObjectiveVector]] = []
    rejected = Counter()

    for candidate in candidates:
        report = validate_plan_content(candidate, context)
        if not report.valid:
            rejected.update(report.codes())
            continue
        vector = evaluate_objectives(candidate, objective_context)
        valid.append((vector.sort_key, candidate, vector))

    if not valid:
        rejection_counts = tuple(
            sorted(
                rejected.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )
        reason_codes = ["NO_VALID_PLAN"]
        reason_codes.extend(code for code, _ in rejection_counts)
        # Preserve order while satisfying the unique reason-code contract.
        reason_codes = tuple(dict.fromkeys(reason_codes))

        authority = PlanAuthorityState(
            status=PlanAuthorityStatus.BLOCKED,
            source_revision=context.source_revision,
            semantic_input_hash=request.semantic_input_hash,
            strategy_revision_id=context.strategy.revision_id,
            engine_version=request.engine_version,
            affected_from=request.affected_from,
            affected_until=request.affected_until,
            previous_valid_plan_hash=(
                plan_content_hash(request.previous_plan)
                if request.previous_plan is not None
                else None
            ),
            blocked_reason_codes=reason_codes,
            invalidated_workout_keys=_invalidated_workout_ids(request),
            requires_user_input=False,
        )
        trace = PlanningSolveTrace(
            source_revision=context.source_revision,
            semantic_input_hash=request.semantic_input_hash,
            engine_version=request.engine_version,
            generation=generation,
            candidates_considered=len(candidates),
            valid_candidates=0,
            rejected_candidates=len(candidates),
            rejection_counts=rejection_counts,
            selected_plan_hash=None,
            search_complete=True,
            optimality_proven=True,
            hard_constraint_refs=_hard_constraint_refs(context),
        )
        return PlanningSolveResult(
            authority_state=authority,
            plan=None,
            objective_vector=None,
            trace=trace,
        )

    valid.sort(key=lambda item: item[0])
    _, selected, vector = valid[0]

    # Re-run the independent final gate on the exact winning PlanContent.
    # A failure here is a programming defect, never something to repair after
    # selection or publication.
    final_report = validate_plan_content(selected, context)
    if not final_report.valid:
        raise PlanningContractError(
            "selected plan failed final invariant gate after candidate selection: "
            + ", ".join(final_report.codes())
        )

    selected_hash = plan_content_hash(selected)
    valid_plans = tuple(item[1] for item in valid)
    plan_changes = build_plan_changes(selected, request.previous_plan)
    workout_decisions = build_workout_decisions(
        selected,
        valid_plans,
        context,
        request.previous_plan,
    )
    authority = PlanAuthorityState(
        status=PlanAuthorityStatus.CURRENT,
        source_revision=context.source_revision,
        semantic_input_hash=request.semantic_input_hash,
        strategy_revision_id=context.strategy.revision_id,
        engine_version=request.engine_version,
        affected_from=request.affected_from,
        affected_until=request.affected_until,
        plan_content_hash=selected_hash,
    )
    rejection_counts = tuple(
        sorted(
            rejected.items(),
            key=lambda item: (-item[1], item[0]),
        )
    )
    trace = PlanningSolveTrace(
        source_revision=context.source_revision,
        semantic_input_hash=request.semantic_input_hash,
        engine_version=request.engine_version,
        generation=generation,
        candidates_considered=len(candidates),
        valid_candidates=len(valid),
        rejected_candidates=len(candidates) - len(valid),
        rejection_counts=rejection_counts,
        selected_plan_hash=selected_hash,
        search_complete=True,
        optimality_proven=True,
        hard_constraint_refs=_hard_constraint_refs(context),
        final_validation_codes=final_report.codes(),
        workout_decisions=workout_decisions,
        plan_changes=plan_changes,
    )
    return PlanningSolveResult(
        authority_state=authority,
        plan=selected,
        objective_vector=vector,
        trace=trace,
    )
