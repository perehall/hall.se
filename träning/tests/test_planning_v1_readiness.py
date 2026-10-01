#!/usr/bin/env python3
"""Real-source readiness gate for Planning Engine v1 shadow mode."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from planning_v1_readiness import build_readiness_report  # noqa: E402


START = date(2026, 10, 5)
END = date(2026, 10, 11)


def complete_profile(*, fixed_commitments=""):
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
    return {
        "schema_version": 1,
        "status": "complete",
        "current_step": 12,
        "goals": [{"text": "test", "importance": "primary", "target_date": None}],
        "availability": availability,
        "preferences": {
            "frequency": {
                "preferred_days": 6,
                "min_days": 5,
                "max_days": 7,
            },
            "double_sessions": "sometimes",
            "rest_days": "load_driven",
        },
        "constraints": {
            "fixed_commitments": fixed_commitments,
            "other": "",
        },
        "coach_autonomy": "week_auto",
    }


def verified_profile_loader(*, fixed_commitments=""):
    def load():
        return complete_profile(fixed_commitments=fixed_commitments), {
            "source": "supabase_db",
            "verified": True,
            "reason": "active_profile",
            "revision": 7,
        }
    return load


class PlanningV1ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        for name in (
            "training_strategy.json",
            "workout_catalog.json",
            "athlete_state.json",
            "planning_policy.json",
        ):
            (self.data / name).write_text(
                json.dumps({"legacy": True}),
                encoding="utf-8",
            )

    def tearDown(self):
        self.tmp.cleanup()

    def report(self, loader):
        return build_readiness_report(
            self.data,
            affected_from=START,
            affected_until=END,
            planning_date=date(2026, 10, 8),
            profile_loader=loader,
        )

    def test_profile_and_execution_facts_are_built_from_owned_sources(self):
        report = self.report(verified_profile_loader())
        self.assertFalse(report["ready"])
        self.assertEqual(
            report["source_status"]["athlete_profile"]["source"],
            "supabase_db",
        )
        self.assertEqual(
            report["source_status"]["fixed_commitments"],
            "profile_explicitly_empty",
        )
        self.assertEqual(
            report["source_status"]["execution_facts"],
            "materialized_from_owned_sources",
        )
        codes = {item["code"] for item in report["blockers"]}
        self.assertEqual(
            {
                "MISSING_V1_STRATEGY_REVISION",
                "MISSING_V1_CATALOG_PROJECTION",
                "MISSING_V1_OBSERVED_TRAINING",
                "MISSING_V1_POLICY_PROJECTION",
            },
            codes,
        )
        self.assertFalse(report["solver_ran"])
        self.assertFalse(report["production_mutated"])

    def test_untyped_fixed_commitment_text_blocks_without_parsing(self):
        report = self.report(
            verified_profile_loader(fixed_commitments="Enduro måndag")
        )
        blockers = {
            item["code"]: item
            for item in report["blockers"]
        }
        self.assertIn(
            "UNTYPED_FIXED_COMMITMENTS_REQUIRE_MIGRATION",
            blockers,
        )
        self.assertEqual(
            report["source_status"]["execution_facts"],
            "blocked",
        )
        self.assertNotIn(
            "MISSING_V1_EXECUTION_FACTS",
            blockers,
        )

    def test_missing_active_profile_is_explicit_source_blocker(self):
        def missing_profile():
            return None, {
                "source": "none",
                "verified": False,
                "reason": "database_url_missing",
            }

        report = self.report(missing_profile)
        codes = {item["code"] for item in report["blockers"]}
        self.assertIn(
            "CANONICAL_ATHLETE_PROFILE_UNAVAILABLE",
            codes,
        )
        self.assertEqual(
            report["source_status"]["fixed_commitments"],
            "blocked",
        )
        self.assertEqual(
            report["source_status"]["execution_facts"],
            "blocked",
        )

    def test_readiness_hash_is_stable_for_identical_semantics(self):
        first = self.report(verified_profile_loader())
        second = self.report(verified_profile_loader())
        self.assertEqual(
            first["source_revision"],
            second["source_revision"],
        )

    def test_probe_has_no_materialized_profile_file_or_legacy_planner_dependency(self):
        import planning_v1_readiness as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("planning_athlete_profile.json", source)
        self.assertNotIn("planning_execution_facts.json", source)
        self.assertNotIn("adaptive_planner", source)
        self.assertNotIn("plan.json", source)
        self.assertNotIn("upcoming_week", source)


if __name__ == "__main__":
    unittest.main()
