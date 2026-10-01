#!/usr/bin/env python3
"""Safety-boundary tests for the live Planning Engine v1 shadow runner."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class PlanningV1ShadowRunnerSafetyTests(unittest.TestCase):
    def test_shadow_runner_has_single_dedicated_write_target(self):
        import planning_v1_shadow_run as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertIn("training.planning_v1_shadow_runs", source)
        self.assertNotIn("training.planned_workouts", source)
        self.assertNotIn("training.state_documents", source)
        self.assertNotIn("device_sync", source.lower())
        self.assertNotIn("garmin", source.lower())

    def test_missing_audit_table_is_non_mutating_success_path(self):
        import planning_v1_shadow_run as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertIn('return "table_missing"', source)
        self.assertIn("conn.rollback()", source)


if __name__ == "__main__":
    unittest.main()
