#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach_decisions import (  # noqa: E402
    ALLOWED_DECISIONS,
    append_coach_decisions,
    build_coach_decisions,
    diff_planned_workouts,
    load_coach_decision_ledger,
)


class CoachDecisionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(
            (ROOT / "data" / "workout_catalog.json").read_text(encoding="utf-8")
        )
        self.state = {
            "capability_states": {
                "by_capability": {
                    "run_threshold": {
                        "evidence_state": "tolerated",
                        "progression_state": "hold",
                        "progression_ready": False,
                        "progression_reason_code": "recovery_window_open",
                        "progression_reason": "72 h-observationsfönstret är ännu inte komplett.",
                        "demonstrated_value": 30.0,
                        "tolerated_value": 30.0,
                        "absorbed_value": 32.0,
                    },
                    "swim_aerobic": {
                        "evidence_state": "demonstrated",
                        "progression_state": "hold",
                        "progression_ready": False,
                        "progression_reason_code": "missing_feedback",
                        "progression_reason": "Senaste exponeringen saknar återkoppling.",
                        "demonstrated_value": 3200.0,
                        "tolerated_value": None,
                        "absorbed_value": None,
                    },
                }
            }
        }

    @staticmethod
    def plan(*rows):
        return {"planned_workouts": list(rows)}

    @staticmethod
    def workout(
        *,
        date_value,
        slot,
        recipe,
        session,
        stimuli,
        sport="run",
    ):
        return {
            "date": date_value,
            "microcycle_slot": slot,
            "recipe_key": recipe,
            "session": session,
            "stimuli": list(stimuli),
            "sport": sport,
            "planning_status": "preliminary",
        }

    def test_plan_diff_distinguishes_reschedule_from_replace(self):
        old_threshold = self.workout(
            date_value="2026-10-07",
            slot="run_threshold_short_reps_1",
            recipe="run_threshold_short_reps",
            session="Löpning · kontrollerad tröskel · 5 × 6 min / 60 s jogg",
            stimuli=["run_threshold"],
        )
        moved = dict(old_threshold, date="2026-10-08")
        diff = diff_planned_workouts(
            self.plan(old_threshold),
            self.plan(moved),
        )
        self.assertEqual(len(diff), 1)
        self.assertEqual(diff[0]["change_type"], "rescheduled")

        replacement = self.workout(
            date_value="2026-10-07",
            slot="run_threshold_2",
            recipe="run_threshold",
            session="Löpning · kontrollerad tröskel · 4 × 8 min / 90 s jogg",
            stimuli=["run_threshold"],
        )
        diff = diff_planned_workouts(
            self.plan(old_threshold),
            self.plan(replacement),
        )
        self.assertEqual(len(diff), 1)
        self.assertEqual(diff[0]["change_type"], "replaced")

    def test_completed_threshold_is_recorded_as_fulfill_with_state_and_evidence(self):
        before = self.plan(
            self.workout(
                date_value="2026-10-07",
                slot="run_threshold_short_reps_1",
                recipe="run_threshold_short_reps",
                session="Löpning · kontrollerad tröskel · 5 × 6 min / 60 s jogg",
                stimuli=["run_threshold"],
            )
        )
        after = self.plan()
        micro = {
            "week_key": "2026-W41",
            "source_hash": "micro-hash",
            "slots": [],
        }
        completed_context = {
            "activity_refs": ["activity-900"],
            "direct_capabilities": ["run_threshold"],
            "planning_credits": ["run_threshold"],
            "capability_refs": {"run_threshold": ["activity-900"]},
        }
        rows = build_coach_decisions(
            today=date(2026, 10, 7),
            target_start=date(2026, 10, 5),
            before_plan=before,
            after_plan=after,
            micro=micro,
            catalog=self.catalog,
            athlete_state=self.state,
            completed_context=completed_context,
            previous_entries=[],
            capability_labels={"run_threshold": "Kontrollerad löptröskel"},
            active_replan=True,
            micro_changed=True,
            generated_at_utc="2026-10-07T18:30:00+00:00",
        )
        threshold = next(row for row in rows if row["capability"] == "run_threshold")
        self.assertEqual(threshold["decision"], "fulfill")
        self.assertEqual(threshold["trigger"], "completed_training")
        self.assertEqual(threshold["reason_code"], "completed_capability_credit")
        self.assertEqual(
            threshold["evidence"]["activity_refs"],
            ["activity-900"],
        )
        self.assertEqual(
            threshold["new_state"]["progression_reason_code"],
            "recovery_window_open",
        )
        self.assertEqual(
            threshold["affected_workouts"][0]["change_type"],
            "removed",
        )
        self.assertIn("genomfört stimulus", threshold["summary"])

    def test_hold_uses_capability_reason_code_and_previous_state(self):
        micro = {
            "week_key": "2026-W41",
            "source_hash": "micro-hash",
            "slots": [
                {
                    "day_index": 3,
                    "recipe_key": "run_threshold_short_reps",
                    "action": "consolidate",
                    "rationale": "Håll absorberbar nivå.",
                    "evidence_refs": ["athlete_state:run_threshold"],
                }
            ],
        }
        previous = {
            "schema_version": 1,
            "decision_id": "prior",
            "generated_at_utc": "2026-10-01T00:00:00+00:00",
            "planning_date": "2026-10-01",
            "week_start": "2026-10-05",
            "capability": "run_threshold",
            "trigger": "microcycle_planning",
            "decision": "hold",
            "reason_code": "not_yet_absorbed",
            "previous_state": None,
            "new_state": {
                "evidence_state": "demonstrated",
                "progression_state": "hold",
                "progression_ready": False,
                "progression_reason_code": "not_yet_absorbed",
                "progression_reason": "Tidigare läge.",
                "demonstrated_value": 30.0,
                "tolerated_value": None,
                "absorbed_value": None,
            },
            "evidence": {},
            "affected_workouts": [],
            "summary": "Tidigare",
        }
        rows = build_coach_decisions(
            today=date(2026, 10, 5),
            target_start=date(2026, 10, 5),
            before_plan=self.plan(),
            after_plan=self.plan(),
            micro=micro,
            catalog=self.catalog,
            athlete_state=self.state,
            completed_context={},
            previous_entries=[previous],
            capability_labels={"run_threshold": "Kontrollerad löptröskel"},
            micro_changed=True,
            generated_at_utc="2026-10-05T08:00:00+00:00",
        )
        threshold = next(row for row in rows if row["capability"] == "run_threshold")
        self.assertEqual(threshold["decision"], "hold")
        self.assertEqual(threshold["reason_code"], "recovery_window_open")
        self.assertEqual(threshold["trigger"], "capability_state_update")
        self.assertEqual(
            threshold["previous_state"]["evidence_state"],
            "demonstrated",
        )
        self.assertEqual(threshold["new_state"]["evidence_state"], "tolerated")

    def test_progress_decision_is_never_inferred_without_progress_action(self):
        ready_state = {
            "capability_states": {
                "by_capability": {
                    "run_threshold": {
                        "evidence_state": "absorbed",
                        "progression_state": "ready",
                        "progression_ready": True,
                        "progression_reason_code": "absorbed_supportive_repeat",
                        "progression_reason": "Absorberad.",
                        "demonstrated_value": 32.0,
                        "tolerated_value": 32.0,
                        "absorbed_value": 32.0,
                    }
                }
            }
        }
        micro = {
            "week_key": "2026-W42",
            "source_hash": "micro-progress",
            "slots": [
                {
                    "day_index": 3,
                    "recipe_key": "run_threshold",
                    "action": "progress",
                    "evidence_refs": [
                        "athlete_state.dose_response:run_threshold:progression_ready=true"
                    ],
                }
            ],
        }
        rows = build_coach_decisions(
            today=date(2026, 10, 12),
            target_start=date(2026, 10, 12),
            before_plan=self.plan(),
            after_plan=self.plan(),
            micro=micro,
            catalog=self.catalog,
            athlete_state=ready_state,
            completed_context={},
            previous_entries=[],
            capability_labels={"run_threshold": "Kontrollerad löptröskel"},
            micro_changed=True,
            generated_at_utc="2026-10-12T07:00:00+00:00",
        )
        threshold = next(row for row in rows if row["capability"] == "run_threshold")
        self.assertEqual(threshold["decision"], "progress")
        self.assertTrue(threshold["new_state"]["progression_ready"])

        micro["slots"][0]["action"] = "consolidate"
        held = build_coach_decisions(
            today=date(2026, 10, 12),
            target_start=date(2026, 10, 12),
            before_plan=self.plan(),
            after_plan=self.plan(),
            micro=micro,
            catalog=self.catalog,
            athlete_state=ready_state,
            completed_context={},
            previous_entries=[],
            capability_labels={"run_threshold": "Kontrollerad löptröskel"},
            micro_changed=True,
            generated_at_utc="2026-10-12T07:00:00+00:00",
        )
        threshold = next(row for row in held if row["capability"] == "run_threshold")
        self.assertEqual(threshold["decision"], "hold")

    def test_append_only_ledger_is_idempotent_and_rejects_mutation(self):
        micro = {
            "week_key": "2026-W41",
            "source_hash": "micro-hash",
            "slots": [
                {
                    "day_index": 3,
                    "recipe_key": "run_threshold_short_reps",
                    "action": "consolidate",
                    "evidence_refs": [],
                }
            ],
        }
        rows = build_coach_decisions(
            today=date(2026, 10, 5),
            target_start=date(2026, 10, 5),
            before_plan=self.plan(),
            after_plan=self.plan(),
            micro=micro,
            catalog=self.catalog,
            athlete_state=self.state,
            completed_context={},
            previous_entries=[],
            micro_changed=True,
            generated_at_utc="2026-10-05T08:00:00+00:00",
        )
        self.assertTrue(rows)
        self.assertTrue(all(row["decision"] in ALLOWED_DECISIONS for row in rows))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coach_decisions.json"
            self.assertEqual(append_coach_decisions(path, rows), len(rows))
            self.assertEqual(append_coach_decisions(path, rows), 0)
            ledger = load_coach_decision_ledger(path)
            self.assertTrue(ledger["append_only"])
            self.assertEqual(len(ledger["entries"]), len(rows))

            mutated = [dict(rows[0], summary="Historiken får inte skrivas om.")]
            with self.assertRaises(ValueError):
                append_coach_decisions(path, mutated)


if __name__ == "__main__":
    unittest.main()
