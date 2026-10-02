"""Assemble all canonical Planning Engine v1 projections fail-closed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from training_core.application.planning_catalog_projection import (
    CatalogProjectionError,
    PlanningCatalogProjection,
    compile_catalog_projection,
)
from training_core.application.planning_eligibility_projection import (
    EligibilityDecision,
    project_option_eligibility,
)
from training_core.application.planning_execution_facts_projection import (
    ExecutionFactsProjection,
    ExecutionFactsProjectionError,
    compile_execution_facts_projection,
)
from training_core.application.planning_observed_projection import (
    ObservedTrainingProjection,
    ObservedTrainingProjectionError,
    compile_observed_training_projection,
    map_observed_obligation_credits,
)
from training_core.application.planning_policy_projection import (
    PlanningPolicyProjection,
    PolicyProjectionError,
    compile_policy_projection,
)
from training_core.application.planning_profile_projection import (
    AthletePlanningPreferencesProjection,
    ProfileProjectionError,
    compile_athlete_planning_preferences,
)
from training_core.application.planning_strategy_projection import (
    StrategyProjectionError,
    compile_strategy_revision,
)
from training_core.planning.objectives import ObjectivePolicy
from training_core.planning.projections import ShadowProjectionBundle


@dataclass(frozen=True)
class ProjectionAssemblyBlocker:
    stage: str
    code: str
    message: str


@dataclass(frozen=True)
class CanonicalProjectionAssemblyResult:
    bundle: ShadowProjectionBundle | None
    blockers: tuple[ProjectionAssemblyBlocker, ...]
    component_revisions: tuple[tuple[str, str], ...] = ()
    eligibility_decisions: tuple[EligibilityDecision, ...] = ()

    @property
    def ready(self) -> bool:
        return self.bundle is not None and not self.blockers


def _blocker(stage: str, exc) -> ProjectionAssemblyBlocker:
    return ProjectionAssemblyBlocker(
        stage=stage,
        code=str(getattr(exc, "code", type(exc).__name__)),
        message=str(exc),
    )


def assemble_canonical_shadow_projections(
    *,
    source_revision: str,
    canonical_strategy: dict[str, Any],
    canonical_catalog: dict[str, Any],
    canonical_athlete_state: dict[str, Any],
    canonical_athlete_profile: dict[str, Any],
    canonical_policy: dict[str, Any],
    canonical_execution_facts: dict[str, Any],
) -> CanonicalProjectionAssemblyResult:
    revision = str(source_revision or "").strip()
    if not revision:
        return CanonicalProjectionAssemblyResult(
            bundle=None,
            blockers=(
                ProjectionAssemblyBlocker(
                    stage="source",
                    code="MISSING_CANONICAL_SOURCE_REVISION",
                    message="canonical source revision must be non-empty",
                ),
            ),
        )

    blockers: list[ProjectionAssemblyBlocker] = []
    revisions: list[tuple[str, str]] = []

    strategy = None
    try:
        strategy = compile_strategy_revision(canonical_strategy)
        revisions.append(("strategy", strategy.revision_id))
    except StrategyProjectionError as exc:
        blockers.append(_blocker("strategy", exc))

    catalog: PlanningCatalogProjection | None = None
    try:
        catalog = compile_catalog_projection(canonical_catalog)
        revisions.append(("catalog", catalog.revision_id))
    except CatalogProjectionError as exc:
        blockers.append(_blocker("catalog", exc))

    observed: ObservedTrainingProjection | None = None
    try:
        observed = compile_observed_training_projection(
            canonical_athlete_state
        )
        revisions.append(("observed_training", observed.revision_id))
    except ObservedTrainingProjectionError as exc:
        blockers.append(_blocker("observed_training", exc))

    policy: PlanningPolicyProjection | None = None
    try:
        policy = compile_policy_projection(canonical_policy)
        revisions.append(("policy", policy.revision_id))
    except PolicyProjectionError as exc:
        blockers.append(_blocker("policy", exc))

    profile: AthletePlanningPreferencesProjection | None = None
    try:
        profile = compile_athlete_planning_preferences(
            canonical_athlete_profile
        )
        revisions.append(("athlete_profile", profile.revision_id))
    except ProfileProjectionError as exc:
        blockers.append(_blocker("athlete_profile", exc))

    execution: ExecutionFactsProjection | None = None
    try:
        execution = compile_execution_facts_projection(
            canonical_execution_facts
        )
        revisions.append(("execution_facts", execution.revision_id))
    except ExecutionFactsProjectionError as exc:
        blockers.append(_blocker("execution_facts", exc))

    eligibility_decisions: tuple[EligibilityDecision, ...] = ()
    option_eligibility = None
    if catalog is not None:
        eligibility = project_option_eligibility(
            catalog,
            canonical_athlete_state,
        )
        eligibility_decisions = eligibility.decisions
        if eligibility.blockers:
            blockers.extend(
                ProjectionAssemblyBlocker(
                    stage="eligibility",
                    code=item.code,
                    message=f"{item.capability}: {item.message}",
                )
                for item in eligibility.blockers
            )
        else:
            option_eligibility = eligibility.option_eligibility

    if strategy is not None and catalog is not None:
        catalog_recipes = {
            item.recipe_id
            for item in catalog.approved_options
        }
        missing = sorted(
            {
                recipe
                for obligation in strategy.obligations
                for recipe in obligation.recipe_family
                if recipe not in catalog_recipes
            }
        )
        if missing:
            blockers.append(
                ProjectionAssemblyBlocker(
                    stage="cross_contract",
                    code="STRATEGY_RECIPE_MISSING_FROM_CATALOG",
                    message=", ".join(missing),
                )
            )

    observed_credits = None
    if observed is not None and strategy is not None:
        observed_credits = map_observed_obligation_credits(
            observed,
            strategy,
        )

    if blockers:
        return CanonicalProjectionAssemblyResult(
            bundle=None,
            blockers=tuple(
                sorted(
                    blockers,
                    key=lambda item: (
                        item.stage,
                        item.code,
                        item.message,
                    ),
                )
            ),
            component_revisions=tuple(sorted(revisions)),
            eligibility_decisions=eligibility_decisions,
        )

    assert strategy is not None
    assert catalog is not None
    assert observed is not None
    assert policy is not None
    assert profile is not None
    assert execution is not None
    assert option_eligibility is not None
    assert observed_credits is not None

    bundle = ShadowProjectionBundle(
        source_revision=revision,
        strategy=strategy,
        workout_options=catalog.approved_options,
        option_eligibility=option_eligibility,
        observed_credits=observed_credits,
        observed_load=observed.load_exposures,
        fixed_commitments=execution.fixed_commitments,
        availability=execution.availability,
        closed_dates=execution.closed_dates,
        compatibility_policy=policy.compatibility_policy,
        objective_policy=ObjectivePolicy(
            schedule=profile.schedule,
            spacing_preferences=policy.spacing_preferences,
        ),
        prewindow_load_context_from=execution.prewindow_load_context_from,
        prewindow_load_context_through=execution.prewindow_load_context_through,
    )
    return CanonicalProjectionAssemblyResult(
        bundle=bundle,
        blockers=(),
        component_revisions=tuple(sorted(revisions)),
        eligibility_decisions=eligibility_decisions,
    )
