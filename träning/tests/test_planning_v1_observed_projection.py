#!/usr/bin/env python3
"""Strict observed-training projection tests for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_observed_projection import (  # noqa: E402
    ObservedTrainingProjectionError,
    compile_observed_training_projection,
    map_observed_obligation_credits,
)
from training_core.planning.models import (  # noqa: E402
    AggregateLoadEnvelope,
    ContributionKind,
    LoadBound,
    LoadDimensionLevel,
    ObservedCreditBasis,
    PlanningObligation,
    StrategyRevision,
    UnknownAggregatePolicy,
)


START = date(2026, 10, 5)
END = date(2026, 10, 11)


def explicit_state():
    return {
        "fact_window": {
            "start": "2026-10-01",
            "end": "2026-10-11",
        },
        "recent_sessions": [
            {
                "id": 1,
                "date": "2026-10-06",
                "classification": "training",
                "family": "run",
                "average_heartrate": 170,
                "training_profile": {
                    "planning_credits": ["run_threshold"],
                },
            },
            {
                "id": 2,
                "date": "2026-10-07",
                "classification": "training",
                "family": "run",
                "average_heartrate": 130,
                "training_profile": {
                    "planning_credits": ["run_easy_distance"],
                },
            },
        ],
        "planning_engine_v1": {
            "schema_version": 1,
            "observed_training_revision": {
                "revision_id": "observed-v1",
                "coverage_from": "2026-10-06",
                "coverage_through": "2026-10-07",
                "source_refs": ["activity-semantics:v1"],
                "capability_evidence": [
                    {
                        "evidence_id": "activity-1:run-threshold",
                        "exposure_ref": "activity-1",
                        "local_date": "2026-10-06",
                        "capability": "run_threshold",
                        "basis": "confirmed_stimulus",
                        "source_refs": ["activity:1", "classification:confirmed"],
                    },
                    {
                        "evidence_id": "activity-2:easy-match",
                        "exposure_ref": "activity-2",
                        "local_date": "2026-10-07",
                        "capability": "run_easy_distance",
                        "basis": "structural_intent_match",
                        "source_refs": ["activity:2", "intent-match:2"],
                    },
                ],
                "load_exposures": [
                    {
                        "exposure_id": "activity:1",
                        "local_date": "2026-10-06",
                        "load_dimensions": [
                            {
                                "dimension": "mechanical_leg",
                                "level": "unknown",
                                "provenance_refs": ["activity:1", "load-review:unknown"],
                            }
                        ],
                        "quantitative_load": [
                            {
                                "scope": "global",
                                "subject": "training_duration",
                                "metric": "duration",
                                "unit": "minutes",
                                "min_value": 50,
                                "max_value": 50,
                                "provenance_refs": ["activity:1"],
                            }
                        ],
                        "source_refs": ["activity:1"],
                    },
                    {
                        "exposure_id": "activity:2",
                        "local_date": "2026-10-07",
                        "load_dimensions": [
                            {
                                "dimension": "mechanical_leg",
                                "level": "unknown",
                                "provenance_refs": ["activity:2", "load-review:unknown"],
                            }
                        ],
                        "quantitative_load": [
                            {
                                "scope": "global",
                                "subject": "training_duration",
                                "metric": "duration",
                                "unit": "minutes",
                                "min_value": 60,
                                "max_value": 60,
                                "provenance_refs": ["activity:2"],
                            }
                        ],
                        "source_refs": ["activity:2"],
                    }
                ],
            },
        },
    }


def strategy(*, accept_structural=False):
    easy_bases = [ObservedCreditBasis.CONFIRMED_STIMULUS]
    if accept_structural:
        easy_bases.append(ObservedCreditBasis.STRUCTURAL_INTENT_MATCH)
    return StrategyRevision(
        revision_id="strategy-v1",
        goal_set_hash="goal",
        valid_from=START,
        valid_until=END,
        obligations=(
            PlanningObligation(
                obligation_id="threshold",
                capability="run_threshold",
                role="primary",
                priority_tier=1,
                min_exposures=1,
                max_exposures=1,
                recipe_family=("run_threshold",),
                valid_from=START,
                valid_until=END,
                source_refs=("strategy:test",),
            ),
            PlanningObligation(
                obligation_id="easy",
                capability="run_easy_distance",
                role="secondary",
                priority_tier=2,
                min_exposures=1,
                max_exposures=1,
                recipe_family=("run_easy_distance",),
                valid_from=START,
                valid_until=END,
                source_refs=("strategy:test",),
                accepted_observed_bases=tuple(easy_bases),
            ),
        ),
        load_envelope=AggregateLoadEnvelope(
            envelope_id="env",
            bounds=(
                LoadBound(
                    bound_id="duration",
                    scope="global",
                    subject="training_duration",
                    metric="duration",
                    unit="minutes",
                    window_days=7,
                    max_value=600,
                    provenance_refs=("baseline:test",),
                ),
            ),
            unknown_policy=UnknownAggregatePolicy.BLOCK_INCREASE,
            established_baseline_ref="baseline:test",
            source_refs=("strategy:test",),
        ),
        source_refs=("strategy:test",),
        accepted_by="test",
    )


class V1ObservedTrainingProjectionTests(unittest.TestCase):
    def test_explicit_observed_training_compiles_without_interpreting_legacy_fields(self):
        result = compile_observed_training_projection(explicit_state())
        self.assertEqual(result.revision_id, "observed-v1")
        self.assertEqual(len(result.capability_evidence), 2)
        self.assertEqual(len(result.load_exposures), 2)
        self.assertEqual(result.coverage_from, date(2026, 10, 6))
        self.assertEqual(result.coverage_through, date(2026, 10, 7))
        self.assertEqual(
            result.load_exposures[0].load_dimensions[0].level,
            LoadDimensionLevel.UNKNOWN,
        )

    def test_missing_physical_training_activity_blocks_observed_projection(self):
        document = explicit_state()
        document["planning_engine_v1"]["observed_training_revision"]["load_exposures"] = [
            document["planning_engine_v1"]["observed_training_revision"]["load_exposures"][0]
        ]
        with self.assertRaises(ObservedTrainingProjectionError) as raised:
            compile_observed_training_projection(document)
        self.assertEqual(
            raised.exception.code,
            "INCOMPLETE_V1_OBSERVED_LOAD_COVERAGE",
        )

    def test_legacy_planning_credit_and_heart_rate_cannot_substitute_for_v1_evidence(self):
        document = explicit_state()
        document.pop("planning_engine_v1")
        with self.assertRaises(ObservedTrainingProjectionError) as raised:
            compile_observed_training_projection(document)
        self.assertEqual(
            raised.exception.code,
            "MISSING_V1_OBSERVED_TRAINING",
        )

    def test_confirmed_stimulus_maps_to_direct_obligation_credit(self):
        projection = compile_observed_training_projection(explicit_state())
        credits = map_observed_obligation_credits(
            projection,
            strategy(),
        )
        self.assertEqual(len(credits), 1)
        self.assertEqual(
            credits[0].contribution.obligation_id,
            "threshold",
        )
        self.assertEqual(
            credits[0].contribution.kind,
            ContributionKind.DIRECT,
        )
        self.assertEqual(
            credits[0].basis,
            ObservedCreditBasis.CONFIRMED_STIMULUS,
        )

    def test_structural_match_does_not_count_without_strategy_opt_in(self):
        projection = compile_observed_training_projection(explicit_state())
        credits = map_observed_obligation_credits(
            projection,
            strategy(),
        )
        self.assertNotIn(
            "easy",
            {item.contribution.obligation_id for item in credits},
        )

    def test_structural_match_can_count_only_after_explicit_strategy_opt_in(self):
        projection = compile_observed_training_projection(explicit_state())
        credits = map_observed_obligation_credits(
            projection,
            strategy(accept_structural=True),
        )
        by_id = {
            item.contribution.obligation_id: item
            for item in credits
        }
        self.assertIn("easy", by_id)
        self.assertEqual(
            by_id["easy"].basis,
            ObservedCreditBasis.STRUCTURAL_INTENT_MATCH,
        )

    def test_observed_projection_contains_no_legacy_planner_or_physiology_heuristic(self):
        import training_core.application.planning_observed_projection as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("planning_credits", source)
        self.assertNotIn("average_heartrate", source)
        self.assertNotIn("sport_type", source)


if __name__ == "__main__":
    unittest.main()
