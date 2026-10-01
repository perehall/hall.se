#!/usr/bin/env python3
"""Canonical workout-catalog materialization for Planning Engine v1."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_catalog_materializer import (  # noqa: E402
    CatalogMaterializationError,
    materialize_catalog_document,
)
from training_core.application.planning_catalog_projection import (  # noqa: E402
    DoseEvidenceMode,
    compile_catalog_projection,
)
from training_core.planning.models import LoadDimensionLevel  # noqa: E402


CATALOG = ROOT / "data" / "workout_catalog.json"


def canonical_catalog():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


class CatalogMaterializerTests(unittest.TestCase):
    def test_live_catalog_materializes_and_compiles(self):
        document = materialize_catalog_document(canonical_catalog())
        projection = compile_catalog_projection(document)
        self.assertTrue(projection.approved_options)
        self.assertEqual(
            len(projection.eligibility_basis),
            sum(len(item.capabilities) for item in projection.approved_options),
        )

    def test_each_catalog_option_carries_exact_mutable_session_count(self):
        projection = compile_catalog_projection(
            materialize_catalog_document(canonical_catalog())
        )
        self.assertTrue(projection.approved_options)
        for option in projection.approved_options:
            self.assertEqual(len(option.quantitative_load), 1)
            load = option.quantitative_load[0]
            self.assertEqual(load.scope, "planned")
            self.assertEqual(load.subject, "mutable_training")
            self.assertEqual(load.metric, "session_count")
            self.assertEqual(load.unit, "sessions")
            self.assertEqual(load.min_value, 1.0)
            self.assertEqual(load.max_value, 1.0)

    def test_unknown_load_level_is_conservative_not_invented(self):
        projection = compile_catalog_projection(
            materialize_catalog_document(canonical_catalog())
        )
        levels = {
            exposure.level
            for option in projection.approved_options
            for exposure in option.load_dimensions
        }
        self.assertEqual(levels, {LoadDimensionLevel.UNKNOWN})

    def test_explicit_numeric_and_qualitative_dose_semantics_are_preserved(self):
        projection = compile_catalog_projection(
            materialize_catalog_document(canonical_catalog())
        )
        by_key = {
            (item.recipe_id, item.dose_option_id, item.capability): item
            for item in projection.eligibility_basis
        }
        threshold = by_key[
            ("run_threshold", "run-threshold-4x8", "run_threshold")
        ]
        self.assertEqual(threshold.mode, DoseEvidenceMode.NUMERIC)
        self.assertEqual(threshold.metric, "work_minutes")
        self.assertEqual(threshold.value, 32.0)

        technique = by_key[
            ("swim_aerobic_technique", "swim-3200", "swim_technique")
        ]
        self.assertEqual(technique.mode, DoseEvidenceMode.QUALITATIVE)
        self.assertIsNone(technique.metric)
        self.assertIsNone(technique.value)

    def test_optional_stimulus_is_not_claimed_by_every_strength_option(self):
        projection = compile_catalog_projection(
            materialize_catalog_document(canonical_catalog())
        )
        strength = next(
            item
            for item in projection.approved_options
            if item.recipe_id == "strength_core"
        )
        self.assertIn("strength_unilateral", strength.capabilities)
        self.assertIn("strength_core", strength.capabilities)
        self.assertNotIn("plyometric", strength.capabilities)

    def test_missing_explicit_dose_semantics_blocks_recipe(self):
        catalog = copy.deepcopy(canonical_catalog())
        del catalog["recipes"]["run_threshold"]["planning_v1"]
        with self.assertRaises(CatalogMaterializationError) as raised:
            materialize_catalog_document(catalog)
        self.assertEqual(
            raised.exception.code,
            "CATALOG_V1_METADATA_MISSING",
        )

    def test_materializer_contains_no_recipe_or_legacy_planner_special_cases(self):
        import training_core.application.planning_catalog_materializer as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("plan.json", source)
        self.assertNotIn("run_threshold", source)
        self.assertNotIn("swim_aerobic", source)
        self.assertNotIn("enduro", source)


if __name__ == "__main__":
    unittest.main()
