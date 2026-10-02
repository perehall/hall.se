#!/usr/bin/env python3
"""Concurrency and atomic-authority tests for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_commit import (  # noqa: E402
    PlanningCommitConflict,
    PlanningCommitError,
    commit_solve_result,
)
from training_core.planning.candidate_generation import CandidateGenerationStats  # noqa: E402
from training_core.planning.content import plan_content_hash  # noqa: E402
from training_core.planning.models import (  # noqa: E402
    PlanAuthorityState,
    PlanAuthorityStatus,
    PlanContent,
)
from training_core.planning.solver import (  # noqa: E402
    PlanningSolveResult,
    PlanningSolveTrace,
)


START = date(2026, 10, 5)
END = date(2026, 10, 11)


class FakeRepository:
    def __init__(self, revision="rev-1", *, flip_on_commit=False):
        self.revision = revision
        self.flip_on_commit = flip_on_commit
        self.commits = []

    def current_source_revision(self):
        return self.revision

    def commit_if_source_revision(
        self,
        *,
        expected_source_revision,
        authority_state,
        plan,
    ):
        if self.flip_on_commit:
            self.revision = "rev-raced"
        if self.revision != expected_source_revision:
            return False
        self.commits.append((authority_state, plan))
        return True


def generation():
    return CandidateGenerationStats(
        atoms=0,
        terminal_selections=1,
        plan_variants=1,
    )


def current_result(*, corrupt_hash=False):
    plan = PlanContent(
        source_revision="rev-1",
        strategy_revision_id="strategy-1",
        affected_from=START,
        affected_until=END,
        workouts=(),
        fixed_commitments=(),
    )
    actual = plan_content_hash(plan)
    state = PlanAuthorityState(
        status=PlanAuthorityStatus.CURRENT,
        source_revision="rev-1",
        semantic_input_hash="input-hash",
        strategy_revision_id="strategy-1",
        engine_version="solver-v1",
        affected_from=START,
        affected_until=END,
        plan_content_hash="corrupt" if corrupt_hash else actual,
    )
    trace = PlanningSolveTrace(
        source_revision="rev-1",
        semantic_input_hash="input-hash",
        engine_version="solver-v1",
        generation=generation(),
        candidates_considered=1,
        valid_candidates=1,
        rejected_candidates=0,
        rejection_counts=(),
        selected_plan_hash=actual,
    )
    return PlanningSolveResult(
        authority_state=state,
        plan=plan,
        objective_vector=None,
        trace=trace,
    )


def blocked_result():
    state = PlanAuthorityState(
        status=PlanAuthorityStatus.BLOCKED,
        source_revision="rev-1",
        semantic_input_hash="input-hash",
        strategy_revision_id="strategy-1",
        engine_version="solver-v1",
        affected_from=START,
        affected_until=END,
        previous_valid_plan_hash="previous-hash",
        blocked_reason_codes=("NO_VALID_PLAN",),
        invalidated_workout_keys=("old-workout",),
    )
    trace = PlanningSolveTrace(
        source_revision="rev-1",
        semantic_input_hash="input-hash",
        engine_version="solver-v1",
        generation=generation(),
        candidates_considered=1,
        valid_candidates=0,
        rejected_candidates=1,
        rejection_counts=(("HARD_CONFLICT", 1),),
        selected_plan_hash=None,
    )
    return PlanningSolveResult(
        authority_state=state,
        plan=None,
        objective_vector=None,
        trace=trace,
    )


class PlanningCommitGateTests(unittest.TestCase):
    def test_current_plan_commits_only_at_matching_revision(self):
        repo = FakeRepository()
        receipt = commit_solve_result(current_result(), repo)
        self.assertEqual(receipt.source_revision, "rev-1")
        self.assertEqual(receipt.status, PlanAuthorityStatus.CURRENT)
        self.assertEqual(len(repo.commits), 1)

    def test_stale_before_commit_is_rejected(self):
        repo = FakeRepository(revision="rev-2")
        with self.assertRaises(PlanningCommitConflict):
            commit_solve_result(current_result(), repo)
        self.assertEqual(repo.commits, [])

    def test_race_between_precheck_and_atomic_commit_is_rejected(self):
        repo = FakeRepository(flip_on_commit=True)
        with self.assertRaises(PlanningCommitConflict):
            commit_solve_result(current_result(), repo)
        self.assertEqual(repo.commits, [])

    def test_blocked_state_is_committed_to_invalidate_old_prescription(self):
        repo = FakeRepository()
        receipt = commit_solve_result(blocked_result(), repo)
        self.assertEqual(receipt.status, PlanAuthorityStatus.BLOCKED)
        self.assertEqual(repo.commits[0][1], None)
        self.assertFalse(repo.commits[0][0].has_current_prescription)

    def test_tampered_plan_hash_cannot_reach_repository(self):
        repo = FakeRepository()
        with self.assertRaises(PlanningCommitError):
            commit_solve_result(current_result(corrupt_hash=True), repo)
        self.assertEqual(repo.commits, [])


if __name__ == "__main__":
    unittest.main()
