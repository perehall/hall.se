#!/usr/bin/env python3
"""Fail-closed readiness tests for Planning Engine v1 shadow inputs."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.planning.models import (  # noqa: E402
    AggregateLoadEnvelope,
    ApprovedWorkoutOption,
    EligibilityKind,
    LoadBound,
    LoadCompatibilityPolicy,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    OptionEligibility,
    PlanningObligation,
    StrategyRevision,
    UnknownAggregatePolicy,
    WorkoutComponentIntent,
)
from training_core.planning.projections import (  # noqa: E402
    ShadowProjectionBundle,
    assess_shadow_readiness,
)


START = date(2026, 10, 5)
END = date(2026, 10, 11)


def explicit_strategy():
    obligation = PlanningObligation(
        obligation_id="run-threshold",
        capability="run_threshold",
        role="primary",
        priority_tier=1,
        min_exposures=1,
        max_exposures=1,
        recipe_family=("run_threshold",),
        valid_from=START,
        valid_until=END,
        source_refs=("strategy:v1",),
    )
    envelope = AggregateLoadEnvelope(
        envelope_id="env-v1",
        bounds=(
            LoadBound(
                bound_id="duration-7d",
                scope="global",
                subject="training_duration",
                metric="duration",
                unit="minutes",
                window_days=7,
                max_value=420,
                provenance_refs=("athlete:accepted-baseline",),
            ),
        ),
        unknown_policy=UnknownAggregatePolicy.BLOCK_INCREASE,
        established_baseline_ref="athlete:accepted-baseline",
        source_refs=("strategy:v1",),
    )
    return StrategyRevision(
        revision_id="strategy-v1",
        goal_set_hash="goal-hash",
        valid_from=START,
        valid_until=END,
        obligations=(obligation,),
        load_envelope=envelope,
        source_refs=("strategy:v1",),
        accepted_by="user_review",
    )


def explicit_option():
    return ApprovedWorkoutOption(
        recipe_id="run_threshold",
        dose_option_id="run-threshold-32",
        capabilities=("run_threshold",),
        components=(WorkoutComponentIntent("run", 1),),
        load_dimensions=(
            LoadDimensionExposure(
                dimension="cardiovascular",
                level=LoadDimensionLevel.HIGH,
                provenance_refs=("catalog:v1",),
            ),
        ),
        quantitative_load=(
            LoadEstimate(
                scope="global",
                subject="training_duration",
                metric="duration",
                unit="minutes",
                min_value=50,
                max_value=50,
                provenance_refs=("catalog:v1",),
            ),
        ),
        source_refs=("catalog:v1",),
        development_character="controlled_threshold",
    )


class ShadowProjectionReadinessTests(unittest.TestCase):
    def test_missing_projections_block_shadow_mode(self):
        report = assess_shadow_readiness(
            ShadowProjectionBundle(source_revision="rev-1")
        )
        self.assertFalse(report.ready)
        self.assertIn("MISSING_STRATEGY_REVISION", report.blocker_codes)
        self.assertIn(
            "MISSING_APPROVED_WORKOUT_OPTIONS",
            report.blocker_codes,
        )
        self.assertIn("MISSING_OPTION_ELIGIBILITY", report.blocker_codes)
        self.assertIn("MISSING_OBSERVED_LOAD_EXPOSURES", report.blocker_codes)

    def test_empty_is_distinct_from_missing_for_fact_collections(self):
        option = explicit_option()
        report = assess_shadow_readiness(
            ShadowProjectionBundle(
                source_revision="rev-1",
                strategy=explicit_strategy(),
                workout_options=(option,),
                option_eligibility=(
                    OptionEligibility(
                        recipe_id=option.recipe_id,
                        dose_option_id=option.dose_option_id,
                        capability="run_threshold",
                        kind=EligibilityKind.HOLD,
                        source_refs=("athlete:v1",),
                    ),
                ),
                observed_credits=(),
                observed_load=(),
                fixed_commitments=(),
                availability=(),
                compatibility_policy=LoadCompatibilityPolicy(
                    policy_id="compat-v1",
                    rules=(),
                    source_refs=("policy:v1",),
                ),
            )
        )
        self.assertTrue(report.ready, report.blockers)

    def test_missing_load_envelope_cannot_be_replaced_by_legacy_recent_total(self):
        # AggregateLoadEnvelope is mandatory in StrategyRevision construction.
        # The readiness layer has no legacy-plan/recent-total argument by design.
        bundle_fields = ShadowProjectionBundle.__dataclass_fields__
        self.assertNotIn("legacy_plan", bundle_fields)
        self.assertNotIn("recent_total", bundle_fields)
        self.assertNotIn("adaptive_planner", bundle_fields)


if __name__ == "__main__":
    unittest.main()
