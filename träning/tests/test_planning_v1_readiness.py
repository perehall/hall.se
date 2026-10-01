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
        (self.data / "training_strategy.json").write_text(
            json.dumps(
                {
                    "goal_contract": {"goal_hash": "goal-test"},
                    "current_mesocycle": {
                        "id": "meso-test",
                        "start_date": "2026-10-05",
                        "end_date": "2026-10-11",
                        "contract": {
                            "primary": ["run_easy_distance"],
                            "protected_capacity": [],
                        },
                        "development_blueprint": [
                            {
                                "week_start": "2026-10-05",
                                "week_end": "2026-10-11",
                                "planned_variants": [
                                    {
                                        "role": "primary",
                                        "capability": "run_easy_distance",
                                        "recipe_key": "run_easy_distance",
                                    }
                                ],
                                "protected_variants": [],
                                "supporting_candidates": [],
                            }
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        (self.data / "planning_policy.json").write_text(
            json.dumps(
                {
                    "planning_engine_v1": {
                        "schema_version": 1,
                        "policy_revision": {
                            "revision_id": "policy-test",
                            "source_refs": ["policy:test"],
                            "compatibility_policy": {
                                "policy_id": "compat-test",
                                "source_refs": ["policy:test"],
                                "rules": [],
                            },
                            "spacing_preferences": [],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        (self.data / "athlete_state.json").write_text(
            json.dumps(
                {
                    "fact_window": {
                        "start": "2026-09-28",
                        "end": "2026-10-01",
                        "lookback_days": 4,
                    },
                    "recent_sessions": [],
                    "capability_states": {
                        "model": "test",
                        "by_capability": {},
                    },
                }
            ),
            encoding="utf-8",
        )
        (self.data / "workout_catalog.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "recipes": {
                        "run_easy_distance": {
                            "sport": "run",
                            "stimuli": ["run_easy_distance"],
                            "load_dimensions": ["cardiovascular"],
                            "development_character": "easy",
                            "options": [
                                {
                                    "id": "run-easy-60",
                                    "value": 60,
                                }
                            ],
                            "planning_v1": {
                                "eligibility_basis": {
                                    "run_easy_distance": {
                                        "mode": "numeric",
                                        "metric": "duration_minutes",
                                    }
                                }
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def activity_loader(coverage_from, coverage_through):
        return [
            {
                "id": "run-1",
                "date": "2026-09-29",
                "sport_family": "run",
                "classification": "training",
                "elapsed_time_s": 3600.0,
                "distance_m": 12000.0,
            }
        ], {
            "source": "supabase_db",
            "verified": True,
            "coverage_from": coverage_from.isoformat(),
            "coverage_through": coverage_through.isoformat(),
            "training_activity_count": 1,
        }

    def report(self, loader):
        return build_readiness_report(
            self.data,
            affected_from=START,
            affected_until=END,
            planning_date=date(2026, 10, 8),
            profile_loader=loader,
            activity_loader=self.activity_loader,
        )

    def test_profile_and_execution_facts_are_built_from_owned_sources(self):
        report = self.report(verified_profile_loader())
        self.assertTrue(report["ready"], report["blockers"])
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
        self.assertEqual(report["blockers"], [])
        self.assertEqual(
            report["source_status"]["strategy"],
            "materialized_from_mesocycle_blueprint",
        )
        self.assertEqual(
            report["source_status"]["catalog"],
            "materialized_from_owned_source",
        )
        self.assertEqual(
            report["source_status"]["observed_training"]["status"],
            "materialized_from_canonical_activities",
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
