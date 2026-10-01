"""Application-layer atomic commit gate for Planning Engine v1.

The domain solver is pure. This module defines the only allowed transition from
an in-memory solve result to authoritative state: an optimistic-concurrency
compare-and-commit against the same canonical source revision used by the
solver.

No database/provider implementation lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from training_core.planning.content import plan_content_hash
from training_core.planning.models import PlanAuthorityStatus, PlanContent
from training_core.planning.solver import PlanningSolveResult


class PlanningCommitError(RuntimeError):
    pass


class PlanningCommitConflict(PlanningCommitError):
    pass


class PlanningAuthorityRepository(Protocol):
    """Persistence boundary; implementation must compare+commit atomically."""

    def current_source_revision(self) -> str:
        ...

    def commit_if_source_revision(
        self,
        *,
        expected_source_revision: str,
        authority_state,
        plan: PlanContent | None,
    ) -> bool:
        """Return False when expected revision is stale at atomic commit."""
        ...


@dataclass(frozen=True)
class PlanningCommitReceipt:
    source_revision: str
    status: PlanAuthorityStatus
    plan_content_hash: str | None


def _validate_result_for_commit(result: PlanningSolveResult) -> None:
    state = result.authority_state
    if state.source_revision != result.trace.source_revision:
        raise PlanningCommitError(
            "solve result authority/trace source revisions differ"
        )
    if state.semantic_input_hash != result.trace.semantic_input_hash:
        raise PlanningCommitError(
            "solve result authority/trace semantic input hashes differ"
        )
    if state.engine_version != result.trace.engine_version:
        raise PlanningCommitError(
            "solve result authority/trace engine versions differ"
        )

    if state.status is PlanAuthorityStatus.CURRENT:
        if result.plan is None:
            raise PlanningCommitError("CURRENT solve result requires PlanContent")
        actual_hash = plan_content_hash(result.plan)
        if state.plan_content_hash != actual_hash:
            raise PlanningCommitError(
                "CURRENT authority hash does not match exact PlanContent"
            )
        if result.trace.selected_plan_hash != actual_hash:
            raise PlanningCommitError(
                "solve trace selected hash does not match exact PlanContent"
            )
    else:
        if result.plan is not None:
            raise PlanningCommitError(
                "BLOCKED solve result must not expose mutable PlanContent"
            )
        if result.trace.selected_plan_hash is not None:
            raise PlanningCommitError(
                "BLOCKED solve trace must not expose selected plan hash"
            )


def commit_solve_result(
    result: PlanningSolveResult,
    repository: PlanningAuthorityRepository,
) -> PlanningCommitReceipt:
    """Commit CURRENT or BLOCKED authority with optimistic concurrency.

    A pre-read is used only for an early, explicit conflict. Correctness relies
    on repository.commit_if_source_revision performing the comparison and state
    write atomically; a source change between pre-read and write is therefore
    still rejected.
    """

    _validate_result_for_commit(result)
    expected = result.authority_state.source_revision

    if repository.current_source_revision() != expected:
        raise PlanningCommitConflict(
            "canonical planning source changed before commit"
        )

    committed = repository.commit_if_source_revision(
        expected_source_revision=expected,
        authority_state=result.authority_state,
        plan=result.plan,
    )
    if not committed:
        raise PlanningCommitConflict(
            "canonical planning source changed during commit"
        )

    return PlanningCommitReceipt(
        source_revision=expected,
        status=result.authority_state.status,
        plan_content_hash=result.authority_state.plan_content_hash,
    )
