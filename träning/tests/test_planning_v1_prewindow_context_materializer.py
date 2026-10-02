#!/usr/bin/env python3
"""Pre-window load-context materialization tests for Planning Engine v1."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_prewindow_context_materializer import (  # noqa: E402
    PrewindowContextMaterializationError,
    materialize_prewindow_load_context_document,
)


def catalog():
    return {
        "planning_engine_v1": {
            "schema_version": 1,
            "catalog_revision": {
                "revision_id": "catalog-test",
                "options": [
                    {
                        "recipe_id": "run_easy_distance",
                        "dose_option_id": "run-easy-75",
                        "load_dimensions": [
                            {
                                "dimension": "cardiovascular",
                                "level": "low",
                                "provenance_refs": ["catalog:test"],
                            }
                        ],
                        "quantitative_load": [
                            {
                                "scope": "global",
                                "subject": "training_duration",
                                "metric": "duration",
                                "unit": "minutes",
                                "min_value": 75,
                                "max_value": 75,
                                "provenance_refs": ["catalog:test"],
                            }
                        ],
                    }
                ],
            },
        },
    }


def fixed():
    return {
        "planning_engine_v1": {
            "schema_version": 1,
            "fixed_commitments_revision": {
                "revision_id": "fixed-test",
                "source_refs": ["fixed:test"],
                "commitments": [
                    {
                        "commitment_id": "fixed-enduro",
                        "local_date": "2026-10-04",
                        "label": "Enduroskola",
                        "load_dimensions": [],
                        "quantitative_load": [],
                        "source_refs": ["fixed:test"],
                    }
                ],
            },
        },
    }


def planned_row():
    return {
        "workout_key": "mc1:2026-10-02:run_easy",
        "date": "2026-10-02",
        "planning_status": None,
        "manual_lock": False,
        "last_seen_source_hash": "snapshot-1",
        "payload": {
            "date": "2026-10-02",
            "session": "Löpning · lugn distans · 75 min",
            "recipe_key": "run_easy_distance",
            "dose_resolution": {"option_id": "run-easy-75"},
            "same_day_order": 0,
        },
    }


class PrewindowContextMaterializerTests(unittest.TestCase):
    def materialize(self, rows):
        return materialize_prewindow_load_context_document(
            canonical_planned_workouts=rows,
            canonical_catalog=catalog(),
            canonical_fixed_commitments=fixed(),
            coverage_from=date(2026, 10, 2),
            coverage_through=date(2026, 10, 4),
        )

    def test_structured_identity_gets_load_only_from_v1_catalog(self):
        result = self.materialize([planned_row()])
        revision = result["planning_engine_v1"][
            "prewindow_load_context_revision"
        ]
        self.assertEqual(revision["coverage_from"], "2026-10-02")
        self.assertEqual(revision["coverage_through"], "2026-10-04")
        self.assertEqual(len(revision["commitments"]), 1)
        commitment = revision["commitments"][0]
        self.assertEqual(
            commitment["commitment_id"],
            "current-plan:mc1:2026-10-02:run_easy",
        )
        self.assertEqual(
            commitment["quantitative_load"][0]["max_value"],
            75,
        )
        self.assertEqual(commitment["within_day_order"], 1)
        self.assertIn(
            "v1_catalog:run_easy_distance/run-easy-75",
            commitment["source_refs"],
        )

    def test_unknown_catalog_option_fails_closed(self):
        row = planned_row()
        row["payload"]["dose_resolution"]["option_id"] = "not-approved"
        with self.assertRaises(PrewindowContextMaterializationError) as raised:
            self.materialize([row])
        self.assertEqual(
            raised.exception.code,
            "PREWINDOW_OPTION_NOT_IN_V1_CATALOG",
        )

    def test_missing_structured_identity_is_not_inferred_from_session_text(self):
        row = planned_row()
        del row["payload"]["recipe_key"]
        with self.assertRaises(PrewindowContextMaterializationError) as raised:
            self.materialize([row])
        self.assertEqual(
            raised.exception.code,
            "PREWINDOW_STRUCTURED_IDENTITY_MISSING",
        )

    def test_typed_fixed_row_is_not_duplicated_as_current_plan_load(self):
        row = {
            "workout_key": "mc1:2026-10-04:enduro",
            "date": "2026-10-04",
            "planning_status": "fixed",
            "manual_lock": True,
            "payload": {
                "date": "2026-10-04",
                "session": "Enduroskola",
                "planning_status": "fixed",
                "manual_lock": True,
            },
            "last_seen_source_hash": "snapshot-1",
        }
        result = self.materialize([row])
        commitments = result["planning_engine_v1"][
            "prewindow_load_context_revision"
        ]["commitments"]
        self.assertEqual(commitments, [])


if __name__ == "__main__":
    unittest.main()
