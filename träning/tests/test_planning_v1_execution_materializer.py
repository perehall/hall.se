#!/usr/bin/env python3
"""Execution-facts materialization from owned canonical sources."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.planning_execution_facts_projection import (  # noqa: E402
    ExecutionFactsProjectionError,
)
from training_core.application.planning_execution_materializer import (  # noqa: E402
    materialize_execution_facts,
)
from training_core.planning.models import LoadDimensionLevel  # noqa: E402


START = date(2026, 10, 5)
END = date(2026, 10, 11)


def profile_record():
    availability = {
        key: {"available": True, "minutes": None}
        for key in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
    }
    availability["thursday"] = {"available": False, "minutes": None}
    availability["saturday"] = {"available": True, "minutes": 120}
    return {
        "status": "found",
        "revision": 9,
        "profile": {
            "schema_version": 1,
            "status": "complete",
            "current_step": 12,
            "availability": availability,
            "preferences": {
                "frequency": {
                    "preferred_days": 6,
                    "min_days": 5,
                    "max_days": 7,
                },
                "double_sessions": "sometimes",
            },
            "constraints": {
                # This must remain inert free text.
                "fixed_commitments": "Enduro måndag",
            },
        },
    }


def fixed_commitments():
    return {
        "planning_engine_v1": {
            "schema_version": 1,
            "fixed_commitments_revision": {
                "revision_id": "fixed-v1",
                "source_refs": ["user-confirmed:typed-commitments"],
                "commitments": [
                    {
                        "commitment_id": "enduro-2026-10-12",
                        "local_date": "2026-10-12",
                        "label": "Enduro",
                        "load_dimensions": [
                            {
                                "dimension": "mechanical_leg",
                                "level": "unknown",
                                "provenance_refs": [
                                    "user-confirmed:enduro-2026-10-12"
                                ],
                            },
                            {
                                "dimension": "cardiovascular",
                                "level": "unknown",
                                "provenance_refs": [
                                    "user-confirmed:enduro-2026-10-12"
                                ],
                            },
                            {
                                "dimension": "technical",
                                "level": "high",
                                "provenance_refs": [
                                    "user-confirmed:enduro-2026-10-12"
                                ],
                            },
                        ],
                        "quantitative_load": [],
                        "source_refs": [
                            "user-confirmed:enduro-2026-10-12"
                        ],
                    }
                ],
            },
        },
    }


class ExecutionFactsMaterializerTests(unittest.TestCase):
    def test_profile_availability_becomes_dated_hard_facts(self):
        result = materialize_execution_facts(
            canonical_profile_record=profile_record(),
            canonical_fixed_commitments=fixed_commitments(),
            affected_from=START,
            affected_until=END,
            future_context_through=date(2026, 10, 14),
            planning_date=date(2026, 10, 8),
        )
        by_day = {item.local_date: item for item in result.availability}
        self.assertEqual(len(by_day), 7)
        self.assertFalse(by_day[date(2026, 10, 8)].available)
        self.assertEqual(
            by_day[date(2026, 10, 10)].max_duration_minutes,
            120,
        )
        self.assertEqual(
            result.closed_dates,
            (
                date(2026, 10, 5),
                date(2026, 10, 6),
                date(2026, 10, 7),
            ),
        )

    def test_typed_future_commitment_is_kept_with_unknown_load(self):
        result = materialize_execution_facts(
            canonical_profile_record=profile_record(),
            canonical_fixed_commitments=fixed_commitments(),
            affected_from=START,
            affected_until=END,
            future_context_through=date(2026, 10, 14),
            planning_date=date(2026, 10, 8),
        )
        self.assertEqual(len(result.fixed_commitments), 1)
        commitment = result.fixed_commitments[0]
        self.assertEqual(commitment.local_date, date(2026, 10, 12))
        by_dimension = {
            item.dimension: item.level
            for item in commitment.load_dimensions
        }
        self.assertEqual(
            by_dimension["mechanical_leg"],
            LoadDimensionLevel.UNKNOWN,
        )
        self.assertEqual(
            by_dimension["cardiovascular"],
            LoadDimensionLevel.UNKNOWN,
        )

    def test_past_commitment_inside_affected_window_is_not_replayed_as_future_fact(self):
        typed = fixed_commitments()
        typed["planning_engine_v1"]["fixed_commitments_revision"]["commitments"].insert(
            0,
            {
                "commitment_id": "enduro-2026-10-06",
                "local_date": "2026-10-06",
                "label": "Enduro",
                "load_dimensions": [
                    {
                        "dimension": "technical",
                        "level": "unknown",
                        "provenance_refs": ["user-confirmed:enduro-2026-10-06"],
                    }
                ],
                "quantitative_load": [],
                "source_refs": ["user-confirmed:enduro-2026-10-06"],
            },
        )
        result = materialize_execution_facts(
            canonical_profile_record=profile_record(),
            canonical_fixed_commitments=typed,
            affected_from=START,
            affected_until=END,
            future_context_through=date(2026, 10, 14),
            planning_date=date(2026, 10, 8),
        )
        self.assertEqual(
            [item.commitment_id for item in result.fixed_commitments],
            ["enduro-2026-10-12"],
        )

    def test_profile_free_text_commitment_is_never_parsed(self):
        typed = fixed_commitments()
        typed["planning_engine_v1"]["fixed_commitments_revision"]["commitments"] = []
        result = materialize_execution_facts(
            canonical_profile_record=profile_record(),
            canonical_fixed_commitments=typed,
            affected_from=START,
            affected_until=END,
            future_context_through=date(2026, 10, 14),
            planning_date=date(2026, 10, 8),
        )
        self.assertEqual(result.fixed_commitments, ())

    def test_missing_weekday_availability_blocks_instead_of_assuming_available(self):
        profile = profile_record()
        del profile["profile"]["availability"]["friday"]
        with self.assertRaises(ExecutionFactsProjectionError) as raised:
            materialize_execution_facts(
                canonical_profile_record=profile,
                canonical_fixed_commitments=fixed_commitments(),
                affected_from=START,
                affected_until=END,
                future_context_through=date(2026, 10, 14),
                planning_date=date(2026, 10, 8),
            )
        self.assertEqual(
            raised.exception.code,
            "INCOMPLETE_PROFILE_AVAILABILITY",
        )

    def test_materializer_has_no_legacy_planner_dependency(self):
        import training_core.application.planning_execution_materializer as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("plan.json", source)
        self.assertNotIn("upcoming_week", source)
        self.assertNotIn('constraints.get("fixed_commitments")', source)


if __name__ == "__main__":
    unittest.main()
