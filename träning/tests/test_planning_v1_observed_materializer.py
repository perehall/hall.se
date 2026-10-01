#!/usr/bin/env python3
"""Observed-history materialization tests for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_observed_materializer import (  # noqa: E402
    materialize_observed_training_document,
)
from training_core.application.planning_observed_projection import (  # noqa: E402
    compile_observed_training_projection,
)
from training_core.planning.models import (  # noqa: E402
    LoadDimensionLevel,
    ObservedCreditBasis,
)


START = date(2026, 9, 28)
END = date(2026, 10, 1)


def catalog():
    return {
        "recipes": {
            "run_recipe": {
                "sport": "run",
                "stimuli": ["run_threshold"],
                "load_dimensions": ["cardiovascular", "mechanical"],
                "options": [],
            },
            "bike_recipe": {
                "sport": "bike",
                "stimuli": ["mtb_aerobic"],
                "load_dimensions": ["cardiovascular", "technical"],
                "options": [],
            },
        }
    }


def athlete_state():
    return {
        "recent_sessions": [
            {
                "id": "run-1",
                "date": "2026-09-29",
                "classification": "training",
                "training_profile": {
                    "stimuli": [
                        {
                            "key": "run_threshold",
                            "status": "confirmed",
                            "confidence": "high",
                            "source": "explicit_user_report",
                        }
                    ],
                    "planning_credits": ["run_threshold"],
                    "intent_matches": [],
                },
            },
            {
                "id": "run-2",
                "date": "2026-09-30",
                "classification": "training",
                "training_profile": {
                    "stimuli": [],
                    "planning_credits": ["run_threshold"],
                    "intent_matches": [
                        {
                            "stimuli": ["run_threshold"],
                            "relation": "fulfills_planned_dose",
                        }
                    ],
                },
            },
        ],
        "capability_states": {
            "model": "test",
            "by_capability": {},
        },
    }


def activities():
    return [
        {
            "id": "run-1",
            "date": "2026-09-29",
            "sport_family": "run",
            "classification": "training",
            "elapsed_time_s": 3600.0,
            "distance_m": 12000.0,
        },
        {
            "id": "run-2",
            "date": "2026-09-30",
            "sport_family": "run",
            "classification": "training",
            "elapsed_time_s": 3000.0,
            "distance_m": 10000.0,
        },
        {
            "id": "enduro-1",
            "date": "2026-10-01",
            "sport_family": "enduro",
            "classification": "training",
            "elapsed_time_s": 5400.0,
            "distance_m": 25000.0,
        },
    ]


class ObservedTrainingMaterializerTests(unittest.TestCase):
    def document(self):
        return materialize_observed_training_document(
            canonical_activities=activities(),
            canonical_athlete_state=athlete_state(),
            canonical_catalog=catalog(),
            coverage_from=START,
            coverage_through=END,
        )

    def test_every_canonical_training_activity_gets_exactly_one_load_exposure(self):
        projection = compile_observed_training_projection(self.document())
        self.assertEqual(
            {item.exposure_id for item in projection.load_exposures},
            {"activity:run-1", "activity:run-2", "activity:enduro-1"},
        )

    def test_all_categorical_load_levels_remain_unknown(self):
        projection = compile_observed_training_projection(self.document())
        levels = {
            item.level
            for exposure in projection.load_exposures
            for item in exposure.load_dimensions
        }
        self.assertEqual(levels, {LoadDimensionLevel.UNKNOWN})

    def test_known_family_uses_catalog_dimensions_and_unmatched_family_uses_universe(self):
        projection = compile_observed_training_projection(self.document())
        by_id = {item.exposure_id: item for item in projection.load_exposures}
        self.assertEqual(
            {item.dimension for item in by_id["activity:run-1"].load_dimensions},
            {"cardiovascular", "mechanical"},
        )
        self.assertEqual(
            {item.dimension for item in by_id["activity:enduro-1"].load_dimensions},
            {"cardiovascular", "mechanical", "technical"},
        )

    def test_only_explicit_confirmed_stimulus_becomes_capability_evidence(self):
        projection = compile_observed_training_projection(self.document())
        self.assertEqual(len(projection.capability_evidence), 1)
        evidence = projection.capability_evidence[0]
        self.assertEqual(evidence.exposure_ref, "activity:run-1")
        self.assertEqual(evidence.capability, "run_threshold")
        self.assertEqual(evidence.basis, ObservedCreditBasis.CONFIRMED_STIMULUS)

    def test_legacy_planning_credit_or_intent_match_never_becomes_v1_evidence(self):
        projection = compile_observed_training_projection(self.document())
        refs = {
            item.exposure_ref
            for item in projection.capability_evidence
        }
        self.assertNotIn("activity:run-2", refs)

    def test_activity_absent_from_athlete_state_still_has_load_but_no_credit(self):
        projection = compile_observed_training_projection(self.document())
        self.assertIn(
            "activity:enduro-1",
            {item.exposure_id for item in projection.load_exposures},
        )
        self.assertNotIn(
            "activity:enduro-1",
            {item.exposure_ref for item in projection.capability_evidence},
        )

    def test_duration_is_exact_canonical_quantitative_load(self):
        projection = compile_observed_training_projection(self.document())
        run = next(
            item
            for item in projection.load_exposures
            if item.exposure_id == "activity:run-1"
        )
        self.assertEqual(len(run.quantitative_load), 1)
        load = run.quantitative_load[0]
        self.assertEqual(load.metric, "duration_minutes")
        self.assertEqual(load.unit, "minutes")
        self.assertEqual(load.min_value, 60.0)
        self.assertEqual(load.max_value, 60.0)

    def test_materializer_has_no_legacy_planner_or_recipe_specific_dependency(self):
        import training_core.application.planning_observed_materializer as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("plan.json", source)
        self.assertNotIn("upcoming_week", source)
        self.assertNotIn("run_threshold", source)
        self.assertNotIn("enduro", source.lower())


if __name__ == "__main__":
    unittest.main()
