#!/usr/bin/env python3
"""Strict workout-catalog projection tests for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_catalog_projection import (  # noqa: E402
    CatalogProjectionError,
    DoseEvidenceMode,
    compile_catalog_projection,
)


def explicit_catalog():
    return {
        "recipes": {
            "run_threshold": {
                "options": [
                    {"id": "legacy-only", "value": 999},
                ]
            }
        },
        "planning_engine_v1": {
            "schema_version": 1,
            "catalog_revision": {
                "revision_id": "catalog-v1",
                "source_refs": ["catalog:reviewed"],
                "options": [
                    {
                        "recipe_id": "run_threshold",
                        "dose_option_id": "run-threshold-4x8",
                        "capabilities": ["run_threshold"],
                        "components": [
                            {"discipline": "run", "order": 1},
                        ],
                        "load_dimensions": [
                            {
                                "dimension": "cardiovascular",
                                "level": "high",
                                "provenance_refs": ["catalog:reviewed"],
                            },
                            {
                                "dimension": "mechanical_leg",
                                "level": "moderate",
                                "provenance_refs": ["catalog:reviewed"],
                            },
                        ],
                        "quantitative_load": [
                            {
                                "scope": "capability",
                                "subject": "run_threshold",
                                "metric": "work",
                                "unit": "minutes",
                                "min_value": 32,
                                "max_value": 32,
                                "provenance_refs": ["catalog:reviewed"],
                            },
                            {
                                "scope": "global",
                                "subject": "training_duration",
                                "metric": "duration",
                                "unit": "minutes",
                                "min_value": 45,
                                "max_value": 60,
                                "provenance_refs": ["catalog:reviewed"],
                            },
                        ],
                        "source_refs": ["catalog:reviewed"],
                        "development_character": "threshold_long_reps",
                        "planning_priority": 10,
                        "eligibility_basis": [
                            {
                                "capability": "run_threshold",
                                "mode": "numeric",
                                "metric": "work_minutes",
                                "value": 32,
                                "source_refs": ["catalog:reviewed"],
                            }
                        ],
                    }
                ],
            },
        },
    }


class V1CatalogProjectionTests(unittest.TestCase):
    def test_explicit_catalog_compiles_option_and_evidence_basis(self):
        result = compile_catalog_projection(explicit_catalog())
        self.assertEqual(result.revision_id, "catalog-v1")
        self.assertEqual(len(result.approved_options), 1)
        option = result.approved_options[0]
        self.assertEqual(option.option_key, ("run_threshold", "run-threshold-4x8"))
        self.assertEqual(option.planning_priority, 10)
        self.assertEqual(
            [item.level.value for item in option.load_dimensions],
            ["high", "moderate"],
        )
        basis = result.eligibility_basis[0]
        self.assertEqual(basis.mode, DoseEvidenceMode.NUMERIC)
        self.assertEqual(basis.metric, "work_minutes")
        self.assertEqual(basis.value, 32.0)

    def test_legacy_recipe_value_cannot_substitute_for_v1_projection(self):
        document = explicit_catalog()
        document.pop("planning_engine_v1")
        with self.assertRaises(CatalogProjectionError) as raised:
            compile_catalog_projection(document)
        self.assertEqual(
            raised.exception.code,
            "MISSING_V1_CATALOG_PROJECTION",
        )

    def test_every_option_capability_requires_explicit_evidence_basis(self):
        document = explicit_catalog()
        option = document["planning_engine_v1"]["catalog_revision"]["options"][0]
        option["capabilities"].append("run_easy_distance")
        with self.assertRaises(CatalogProjectionError) as raised:
            compile_catalog_projection(document)
        self.assertEqual(
            raised.exception.code,
            "INCOMPLETE_V1_ELIGIBILITY_BASIS",
        )

    def test_qualitative_basis_cannot_hide_numeric_dose_semantics(self):
        document = explicit_catalog()
        basis = (
            document["planning_engine_v1"]["catalog_revision"]["options"][0]
            ["eligibility_basis"][0]
        )
        basis["mode"] = "qualitative"
        with self.assertRaises(CatalogProjectionError) as raised:
            compile_catalog_projection(document)
        self.assertEqual(
            raised.exception.code,
            "INVALID_V1_CATALOG_CONTRACT",
        )

    def test_catalog_projection_contains_no_legacy_planner_dependency(self):
        import training_core.application.planning_catalog_projection as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("choose_option", source)
        self.assertNotIn("forward_horizon", source)


if __name__ == "__main__":
    unittest.main()
