#!/usr/bin/env python3
"""Contract tests written before the Planning Engine v1 solver exists."""

from __future__ import annotations

import ast
import sys
import unittest
from dataclasses import FrozenInstanceError, fields
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.planning.models import (  # noqa: E402
    AggregateLoadEnvelope,
    CoverageRule,
    FixedLoadCommitment,
    LoadBound,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    ObservedCreditBasis,
    PlanAuthorityState,
    PlanAuthorityStatus,
    PlanningContractError,
    PlanningObligation,
    StrategyRevision,
    UnknownAggregatePolicy,
)


def obligation(**overrides):
    payload = {
        "obligation_id": "run-threshold-primary",
        "capability": "run_threshold",
        "role": "primary",
        "priority_tier": 1,
        "min_exposures": 1,
        "max_exposures": 2,
        "recipe_family": ("run_threshold", "run_threshold_short_reps"),
        "valid_from": date(2026, 10, 5),
        "valid_until": date(2026, 10, 11),
        "source_refs": ("strategy:test",),
        "progression_axes": ("session_dose", "exposure_count"),
        "partial_coverage": (),
    }
    payload.update(overrides)
    return PlanningObligation(**payload)


def bound(**overrides):
    payload = {
        "bound_id": "run-quality-7d",
        "scope": "capability",
        "subject": "run_quality",
        "metric": "exposure_count",
        "unit": "count",
        "window_days": 7,
        "max_value": 2,
        "provenance_refs": ("athlete_state:established-baseline",),
    }
    payload.update(overrides)
    return LoadBound(**payload)


def envelope(**overrides):
    payload = {
        "envelope_id": "envelope-v1",
        "bounds": (bound(),),
        "unknown_policy": UnknownAggregatePolicy.BLOCK_INCREASE,
        "established_baseline_ref": "athlete_state:baseline:2026-09",
        "source_refs": ("strategy:test",),
    }
    payload.update(overrides)
    return AggregateLoadEnvelope(**payload)


class CoverageRuleTests(unittest.TestCase):
    def test_exact_rational_credit_is_preserved(self):
        rule = CoverageRule("swim_threshold", 1, 2)
        self.assertEqual(rule.exact_credit, (1, 2))

    def test_credit_cannot_exceed_full_exposure(self):
        with self.assertRaises(PlanningContractError):
            CoverageRule("swim_threshold", 2, 1)

    def test_credit_denominator_must_be_positive(self):
        with self.assertRaises(PlanningContractError):
            CoverageRule("swim_threshold", 1, 0)


class PlanningObligationTests(unittest.TestCase):
    def test_valid_obligation_is_bounded_and_date_scoped(self):
        item = obligation()
        self.assertTrue(item.active_on(date(2026, 10, 5)))
        self.assertTrue(item.active_on(date(2026, 10, 11)))
        self.assertFalse(item.active_on(date(2026, 10, 12)))
        self.assertEqual(item.max_exposures, 2)

    def test_observed_credit_defaults_to_confirmed_stimulus_only(self):
        item = obligation()
        self.assertEqual(
            item.accepted_observed_bases,
            (ObservedCreditBasis.CONFIRMED_STIMULUS,),
        )
        self.assertTrue(
            item.accepts_observed_basis(
                ObservedCreditBasis.CONFIRMED_STIMULUS
            )
        )
        self.assertFalse(
            item.accepts_observed_basis(
                ObservedCreditBasis.STRUCTURAL_INTENT_MATCH
            )
        )

    def test_structural_credit_requires_explicit_obligation_opt_in(self):
        item = obligation(
            accepted_observed_bases=(
                ObservedCreditBasis.CONFIRMED_STIMULUS,
                ObservedCreditBasis.STRUCTURAL_INTENT_MATCH,
            )
        )
        self.assertTrue(
            item.accepts_observed_basis(
                ObservedCreditBasis.STRUCTURAL_INTENT_MATCH
            )
        )

    def test_max_exposures_cannot_be_below_minimum(self):
        with self.assertRaises(PlanningContractError):
            obligation(min_exposures=2, max_exposures=1)

    def test_zero_maximum_is_not_an_obligation(self):
        with self.assertRaises(PlanningContractError):
            obligation(min_exposures=0, max_exposures=0)

    def test_recipe_family_cannot_be_empty(self):
        with self.assertRaises(PlanningContractError):
            obligation(recipe_family=())

    def test_recipe_family_cannot_contain_duplicates(self):
        with self.assertRaises(PlanningContractError):
            obligation(recipe_family=("run_threshold", "run_threshold"))

    def test_validity_window_cannot_run_backwards(self):
        with self.assertRaises(PlanningContractError):
            obligation(
                valid_from=date(2026, 10, 12),
                valid_until=date(2026, 10, 11),
            )

    def test_partial_coverage_cannot_restate_same_capability(self):
        with self.assertRaises(PlanningContractError):
            obligation(
                partial_coverage=(CoverageRule("run_threshold", 1, 2),)
            )

    def test_partial_coverage_sources_must_be_unique(self):
        with self.assertRaises(PlanningContractError):
            obligation(
                partial_coverage=(
                    CoverageRule("run_hill_quality", 1, 2),
                    CoverageRule("run_hill_quality", 1, 1),
                )
            )

    def test_contract_is_immutable(self):
        item = obligation()
        with self.assertRaises(FrozenInstanceError):
            item.max_exposures = 99  # type: ignore[misc]


class LoadBoundCoverageTests(unittest.TestCase):
    def test_complete_coverage_requirement_is_explicit_and_defaults_false(self):
        self.assertFalse(bound().requires_complete_coverage)
        self.assertTrue(
            bound(requires_complete_coverage=True).requires_complete_coverage
        )

    def test_complete_coverage_requirement_must_be_boolean(self):
        with self.assertRaises(PlanningContractError):
            bound(requires_complete_coverage="yes")


class LoadEstimateTests(unittest.TestCase):
    def test_aggregate_coverage_semantics_belong_to_bound_not_estimate(self):
        estimate_fields = {field.name for field in fields(LoadEstimate)}
        bound_fields = {field.name for field in fields(LoadBound)}
        self.assertNotIn("requires_complete_coverage", estimate_fields)
        self.assertIn("requires_complete_coverage", bound_fields)


    def test_quantitative_load_preserves_uncertainty_interval(self):
        estimate = LoadEstimate(
            scope="global",
            subject="training_duration",
            metric="duration",
            unit="minutes",
            min_value=60,
            max_value=120,
            provenance_refs=("user:fixed-commitment",),
        )
        self.assertEqual((estimate.min_value, estimate.max_value), (60, 120))

    def test_quantitative_load_rejects_inverted_interval(self):
        with self.assertRaises(PlanningContractError):
            LoadEstimate(
                scope="global",
                subject="training_duration",
                metric="duration",
                unit="minutes",
                min_value=120,
                max_value=60,
                provenance_refs=("user:fixed-commitment",),
            )

    def test_quantitative_load_requires_provenance(self):
        with self.assertRaises(PlanningContractError):
            LoadEstimate(
                scope="global",
                subject="training_duration",
                metric="duration",
                unit="minutes",
                min_value=60,
                max_value=120,
                provenance_refs=(),
            )


class FixedLoadCommitmentTests(unittest.TestCase):
    def test_fixed_load_is_generic_and_date_scoped(self):
        item = FixedLoadCommitment(
            commitment_id="fixed-1",
            local_date=date(2026, 10, 5),
            label="Fast extern belastning",
            load_dimensions=(
                LoadDimensionExposure(
                    dimension="mechanical_leg",
                    level=LoadDimensionLevel.HIGH,
                    provenance_refs=("user:confirmed",),
                ),
                LoadDimensionExposure(
                    dimension="technical",
                    level=LoadDimensionLevel.HIGH,
                    provenance_refs=("user:confirmed",),
                ),
            ),
            source_refs=("calendar:fixed-1",),
            quantitative_load=(
                LoadEstimate(
                    scope="global",
                    subject="training_duration",
                    metric="duration",
                    unit="minutes",
                    min_value=60,
                    max_value=120,
                    provenance_refs=("user:confirmed",),
                ),
            ),
            within_day_order=1,
        )
        self.assertEqual(item.local_date, date(2026, 10, 5))
        self.assertEqual(item.load_dimensions[0].dimension, "mechanical_leg")

    def test_fixed_load_requires_explicit_load_semantics(self):
        with self.assertRaises(PlanningContractError):
            FixedLoadCommitment(
                commitment_id="fixed-1",
                local_date=date(2026, 10, 5),
                label="Extern belastning",
                load_dimensions=(),
                source_refs=("calendar:fixed-1",),
            )

    def test_fixed_load_rejects_duplicate_dimensions(self):
        exposure = LoadDimensionExposure(
            dimension="mechanical_leg",
            level=LoadDimensionLevel.HIGH,
            provenance_refs=("user:confirmed",),
        )
        with self.assertRaises(PlanningContractError):
            FixedLoadCommitment(
                commitment_id="fixed-1",
                local_date=date(2026, 10, 5),
                label="Extern belastning",
                load_dimensions=(exposure, exposure),
                source_refs=("calendar:fixed-1",),
            )

    def test_fixed_load_order_must_be_positive_when_known(self):
        with self.assertRaises(PlanningContractError):
            FixedLoadCommitment(
                commitment_id="fixed-1",
                local_date=date(2026, 10, 5),
                label="Extern belastning",
                load_dimensions=(
                    LoadDimensionExposure(
                        dimension="mechanical_leg",
                        level=LoadDimensionLevel.MODERATE,
                        provenance_refs=("user:confirmed",),
                    ),
                ),
                source_refs=("calendar:fixed-1",),
                within_day_order=0,
            )


class AggregateLoadEnvelopeTests(unittest.TestCase):
    def test_bound_requires_provenance(self):
        with self.assertRaises(PlanningContractError):
            bound(provenance_refs=())

    def test_bound_requires_explicit_unit(self):
        with self.assertRaises(PlanningContractError):
            bound(unit="")

    def test_bound_requires_positive_window(self):
        with self.assertRaises(PlanningContractError):
            bound(window_days=0)

    def test_bound_allows_zero_ceiling(self):
        result = bound(max_value=0)
        self.assertEqual(result.max_value, 0)

    def test_bound_rejects_negative_ceiling(self):
        with self.assertRaises(PlanningContractError):
            bound(max_value=-1)

    def test_envelope_requires_at_least_one_bound(self):
        with self.assertRaises(PlanningContractError):
            envelope(bounds=())

    def test_duplicate_semantic_bound_is_rejected_even_with_new_id(self):
        first = bound(bound_id="a")
        second = bound(bound_id="b")
        with self.assertRaises(PlanningContractError):
            envelope(bounds=(first, second))

    def test_multiple_windows_for_same_metric_are_distinct(self):
        seven = bound(bound_id="7d", window_days=7, max_value=2)
        fourteen = bound(bound_id="14d", window_days=14, max_value=3)
        result = envelope(bounds=(seven, fourteen))
        self.assertEqual(len(result.bounds), 2)

    def test_unknown_policy_must_be_explicit_enum(self):
        with self.assertRaises(PlanningContractError):
            envelope(unknown_policy="block_increase")  # type: ignore[arg-type]


class StrategyRevisionTests(unittest.TestCase):
    def test_strategy_contains_bounded_obligations_and_envelope(self):
        strategy = StrategyRevision(
            revision_id="strategy-2026-10-01-a",
            goal_set_hash="goalhash",
            valid_from=date(2026, 10, 5),
            valid_until=date(2026, 11, 1),
            obligations=(
                obligation(
                    valid_from=date(2026, 10, 5),
                    valid_until=date(2026, 10, 11),
                ),
            ),
            load_envelope=envelope(),
            source_refs=("goal:v1", "coach-review:accepted"),
            accepted_by="user_review",
        )
        self.assertEqual(strategy.obligations[0].obligation_id, "run-threshold-primary")

    def test_obligation_cannot_extend_outside_strategy_revision(self):
        with self.assertRaises(PlanningContractError):
            StrategyRevision(
                revision_id="strategy-a",
                goal_set_hash="goalhash",
                valid_from=date(2026, 10, 5),
                valid_until=date(2026, 10, 11),
                obligations=(
                    obligation(
                        valid_from=date(2026, 10, 5),
                        valid_until=date(2026, 10, 12),
                    ),
                ),
                load_envelope=envelope(),
                source_refs=("goal:v1",),
                accepted_by="user_review",
            )

    def test_duplicate_obligation_ids_are_rejected(self):
        with self.assertRaises(PlanningContractError):
            StrategyRevision(
                revision_id="strategy-a",
                goal_set_hash="goalhash",
                valid_from=date(2026, 10, 5),
                valid_until=date(2026, 10, 11),
                obligations=(obligation(), obligation()),
                load_envelope=envelope(),
                source_refs=("goal:v1",),
                accepted_by="user_review",
            )


class PlanAuthorityStateTests(unittest.TestCase):
    def test_current_state_requires_content_hash(self):
        with self.assertRaises(PlanningContractError):
            PlanAuthorityState(
                status=PlanAuthorityStatus.CURRENT,
                source_revision="42",
                semantic_input_hash="inputhash",
                strategy_revision_id="strategy-a",
                engine_version="v1",
                affected_from=date(2026, 10, 1),
                affected_until=date(2026, 10, 7),
            )

    def test_current_state_cannot_carry_blocked_semantics(self):
        with self.assertRaises(PlanningContractError):
            PlanAuthorityState(
                status=PlanAuthorityStatus.CURRENT,
                source_revision="42",
                semantic_input_hash="inputhash",
                strategy_revision_id="strategy-a",
                engine_version="v1",
                affected_from=date(2026, 10, 1),
                affected_until=date(2026, 10, 7),
                plan_content_hash="planhash",
                blocked_reason_codes=("NO_VALID_PLAN",),
            )

    def test_blocked_state_has_no_current_plan_content(self):
        state = PlanAuthorityState(
            status=PlanAuthorityStatus.BLOCKED,
            source_revision="43",
            semantic_input_hash="newinput",
            strategy_revision_id="strategy-a",
            engine_version="v1",
            affected_from=date(2026, 10, 1),
            affected_until=date(2026, 10, 7),
            previous_valid_plan_hash="oldplan",
            blocked_reason_codes=("NO_VALID_PLAN",),
            invalidated_workout_keys=("future-run-1",),
        )
        self.assertFalse(state.has_current_prescription)
        self.assertIsNone(state.plan_content_hash)
        self.assertEqual(state.previous_valid_plan_hash, "oldplan")

    def test_blocked_state_requires_reason(self):
        with self.assertRaises(PlanningContractError):
            PlanAuthorityState(
                status=PlanAuthorityStatus.BLOCKED,
                source_revision="43",
                semantic_input_hash="newinput",
                strategy_revision_id="strategy-a",
                engine_version="v1",
                affected_from=date(2026, 10, 1),
                affected_until=date(2026, 10, 7),
            )

    def test_blocked_state_cannot_expose_current_content_hash(self):
        with self.assertRaises(PlanningContractError):
            PlanAuthorityState(
                status=PlanAuthorityStatus.BLOCKED,
                source_revision="43",
                semantic_input_hash="newinput",
                strategy_revision_id="strategy-a",
                engine_version="v1",
                affected_from=date(2026, 10, 1),
                affected_until=date(2026, 10, 7),
                plan_content_hash="stale-plan",
                blocked_reason_codes=("NO_VALID_PLAN",),
            )

    def test_affected_window_cannot_run_backwards(self):
        with self.assertRaises(PlanningContractError):
            PlanAuthorityState(
                status=PlanAuthorityStatus.BLOCKED,
                source_revision="43",
                semantic_input_hash="newinput",
                strategy_revision_id="strategy-a",
                engine_version="v1",
                affected_from=date(2026, 10, 8),
                affected_until=date(2026, 10, 7),
                blocked_reason_codes=("NO_VALID_PLAN",),
            )

    def test_freshness_is_revision_exact(self):
        state = PlanAuthorityState(
            status=PlanAuthorityStatus.CURRENT,
            source_revision="42",
            semantic_input_hash="inputhash",
            strategy_revision_id="strategy-a",
            engine_version="v1",
            affected_from=date(2026, 10, 1),
            affected_until=date(2026, 10, 7),
            plan_content_hash="planhash",
        )
        self.assertTrue(state.is_fresh_for("42"))
        self.assertFalse(state.is_fresh_for("43"))


class PlanningArchitectureBoundaryTests(unittest.TestCase):
    def test_planning_v1_has_no_legacy_or_runtime_side_effect_dependencies(self):
        planning_root = ROOT / "training_core" / "planning"
        forbidden_roots = {
            "subprocess",
            "requests",
            "urllib",
        }
        forbidden_text = (
            "adaptive_planner",
            "träning/data",
            "training/data",
            "finalize_",
            "supabase",
            "github",
            "intervals.icu",
            "strava",
            "garmin",
        )
        violations: list[str] = []

        for path in sorted(planning_root.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {alias.name.split(".", 1)[0] for alias in node.names}
                    bad = roots & forbidden_roots
                    if bad:
                        violations.append(f"{path.name}: imports {sorted(bad)}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".", 1)[0]
                    if root in forbidden_roots:
                        violations.append(f"{path.name}: imports {root}")

            lowered = source.lower()
            for token in forbidden_text:
                if token.lower() in lowered:
                    violations.append(f"{path.name}: contains forbidden dependency {token!r}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
