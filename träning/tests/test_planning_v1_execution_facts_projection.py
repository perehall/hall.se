#!/usr/bin/env python3
"""Strict future execution-facts tests for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_execution_facts_projection import (  # noqa: E402
    ExecutionFactsProjectionError,
    compile_execution_facts_projection,
)
from training_core.planning.models import LoadDimensionLevel  # noqa: E402


def explicit_facts():
    return {
        "constraints": {
            "fixed_commitments": "Enduro måndag",
        },
        "planning_engine_v1": {
            "schema_version": 1,
            "execution_facts_revision": {
                "revision_id": "facts-v1",
                "source_refs": ["user:confirmed-facts"],
                "fixed_commitments": [
                    {
                        "commitment_id": "enduro-school-2026-10-12",
                        "local_date": "2026-10-12",
                        "label": "Fast extern belastning",
                        "load_dimensions": [
                            {
                                "dimension": "mechanical_leg",
                                "level": "unknown",
                                "provenance_refs": [
                                    "user:fixed-enduro",
                                    "load-level:unknown",
                                ],
                            },
                            {
                                "dimension": "technical",
                                "level": "unknown",
                                "provenance_refs": [
                                    "user:fixed-enduro",
                                    "load-level:unknown",
                                ],
                            },
                        ],
                        "quantitative_load": [],
                        "source_refs": ["user:fixed-enduro"],
                    }
                ],
                "availability": [
                    {
                        "local_date": "2026-10-10",
                        "available": False,
                        "max_sessions": 0,
                        "max_duration_minutes": 0,
                        "source_refs": ["user:availability"],
                    }
                ],
                "closed_dates": ["2026-10-05", "2026-10-06"],
            },
        },
    }


class V1ExecutionFactsProjectionTests(unittest.TestCase):
    def test_explicit_facts_compile_without_parsing_profile_text(self):
        result = compile_execution_facts_projection(explicit_facts())
        self.assertEqual(result.revision_id, "facts-v1")
        self.assertEqual(len(result.fixed_commitments), 1)
        self.assertEqual(
            result.fixed_commitments[0].load_dimensions[0].level,
            LoadDimensionLevel.UNKNOWN,
        )
        self.assertFalse(result.availability[0].available)
        self.assertEqual(len(result.closed_dates), 2)

    def test_legacy_fixed_commitment_text_cannot_substitute_for_v1_facts(self):
        document = explicit_facts()
        document.pop("planning_engine_v1")
        with self.assertRaises(ExecutionFactsProjectionError) as raised:
            compile_execution_facts_projection(document)
        self.assertEqual(
            raised.exception.code,
            "MISSING_V1_EXECUTION_FACTS",
        )

    def test_fixed_commitment_requires_explicit_load_dimensions(self):
        document = explicit_facts()
        commitment = (
            document["planning_engine_v1"]["execution_facts_revision"]
            ["fixed_commitments"][0]
        )
        commitment["load_dimensions"] = []
        with self.assertRaises(ExecutionFactsProjectionError) as raised:
            compile_execution_facts_projection(document)
        self.assertEqual(
            raised.exception.code,
            "INVALID_V1_EXECUTION_FACTS",
        )

    def test_execution_projection_contains_no_legacy_calendar_parser(self):
        import training_core.application.planning_execution_facts_projection as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("forward_horizon", source)
        self.assertNotIn("fixed_commitments = str", source)
        self.assertNotIn("planned_workouts", source)


if __name__ == "__main__":
    unittest.main()
