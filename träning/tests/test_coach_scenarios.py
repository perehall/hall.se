#!/usr/bin/env python3
"""End-to-end coach scenarios.

These tests deliberately cross subsystem boundaries:
activity/profile -> athlete state -> completed microcycle context ->
deterministic planner -> hard guards -> coach decision ledger.

They are not unit tests for individual helpers. Each scenario represents a
real planning situation the coach must handle coherently.
"""

import json
import sys
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from adaptive_planner import (  # noqa: E402
    completed_microcycle_context,
    fallback_microcycle,
    microcycle_guard_failures,
    resolve_planning_target,
)
from build_athlete_state import build_state  # noqa: E402
from coach_decisions import build_coach_decisions  # noqa: E402


class CoachScenarioHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.goal = json.loads((ROOT / "data" / "goal.json").read_text(encoding="utf-8"))
        cls.policy = json.loads(
            (ROOT / "data" / "planning_policy.json").read_text(encoding="utf-8")
        )
        cls.catalog = json.loads(
            (ROOT / "data" / "workout_catalog.json").read_text(encoding="utf-8")
        )
        cls.meso = json.loads(
            (ROOT / "data" / "mesocycle_decision.json").read_text(encoding="utf-8")
        )

    @staticmethod
    def activity(
        activity_id,
        day,
        sport_type,
        *,
        report="",
        elapsed_time_s=3600,
        distance_m=0,
    ):
        return {
            "id": activity_id,
            "start_date_local": f"{day}T18:00:00",
            "sport_type": sport_type,
            "classification": "training",
            "elapsed_time_s": elapsed_time_s,
            "distance_m": distance_m,
            "user_report": report,
            "laps": [],
        }

    @staticmethod
    def plan(*rows):
        return {
            "meta": {
                "week_start": "2026-09-28",
                "week_end": "2026-10-04",
                "mesocycle_id": "scenario-meso",
                "microcycle_index": 1,
                "microcycle_total": 4,
                "requires_mesocycle_review": False,
            },
            "planned_workouts": list(rows),
        }

    @staticmethod
    def workout(day, recipe, session, stimuli, sport="run", slot=None):
        return {
            "date": day,
            "sport": sport,
            "recipe_key": recipe,
            "workout_key": slot or f"{day}:{recipe}",
            "microcycle_slot": slot or recipe,
            "session": session,
            "stimuli": list(stimuli),
            "planning_status": "preliminary",
        }

    def state_from(self, activities, planned_workouts=(), *, today=date(2026, 9, 30)):
        return build_state(
            {"activities": list(activities)},
            {"entries": []},
            today=today,
            lookback_days=56,
            planned_workouts=list(planned_workouts),
        )

    def deterministic_micro(self, state, *, planning_date=date(2026, 9, 30)):
        target = date(2026, 9, 28)
        completed = completed_microcycle_context(state, target)
        micro = fallback_microcycle(
            self.meso,
            self.policy,
            self.catalog,
            target,
            completed_context=completed,
            athlete_state=state,
            planning_date=planning_date,
        )
        failures = microcycle_guard_failures(
            micro,
            self.meso,
            self.policy,
            self.catalog,
            target,
            completed_context=completed,
            planning_date=planning_date,
        )
        return completed, micro, failures

    def test_spontaneous_threshold_fulfills_week_stimulus_and_removes_duplicate_quality(self):
        planned_threshold = self.workout(
            "2026-09-30",
            "run_threshold",
            "Löpning · kontrollerad tröskel · 4 × 8 min / 90 s jogg",
            ["run_threshold"],
            slot="run-threshold-planned",
        )
        spontaneous = self.activity(
            "spont-threshold",
            "2026-09-29",
            "Run",
            report="4 x 8 min tröskel. Bra kontroll. RPE 6/10. Kunde gjort mer.",
            elapsed_time_s=3900,
            distance_m=13000,
        )
        state = self.state_from([spontaneous], [planned_threshold])
        completed, micro, failures = self.deterministic_micro(state)

        self.assertIn("run_threshold", completed["planning_credits"])
        self.assertEqual(failures, [])
        planned_recipes = {row["recipe_key"] for row in micro["slots"]}
        self.assertFalse(
            {"run_threshold", "run_threshold_short_reps"} & planned_recipes,
            "already fulfilled threshold must not be duplicated later in live week",
        )

        after = self.plan()
        decisions = build_coach_decisions(
            today=date(2026, 9, 30),
            target_start=date(2026, 9, 28),
            before_plan=self.plan(planned_threshold),
            after_plan=after,
            micro=micro,
            catalog=self.catalog,
            athlete_state=state,
            completed_context=completed,
            previous_entries=[],
            capability_labels={"run_threshold": "Kontrollerad löptröskel"},
            active_replan=True,
            micro_changed=True,
            generated_at_utc="2026-09-30T10:00:00+00:00",
        )
        threshold = next(row for row in decisions if row["capability"] == "run_threshold")
        self.assertEqual(threshold["decision"], "fulfill")
        self.assertEqual(threshold["trigger"], "completed_training")
        self.assertTrue(
            any(change["change_type"] == "removed" for change in threshold["affected_workouts"])
        )

    def test_stranded_missed_swim_reopens_live_week_instead_of_becoming_silent_rest(self):
        missed = self.workout(
            "2026-09-29",
            "swim_aerobic_technique",
            "Simning · 3 200 m · aerob/teknik",
            ["swim_aerobic", "swim_technique"],
            sport="swim",
            slot="swim-missed",
        )
        plan = self.plan(missed)
        upcoming = {"meta": {"week_start": "2026-10-05", "week_end": "2026-10-11"}}
        target, active = resolve_planning_target(
            plan,
            upcoming,
            self.meso,
            date(2026, 9, 30),
            goal=self.goal,
            current_completed_context={},
        )
        self.assertEqual(target, date(2026, 9, 28))
        self.assertTrue(active)

    def test_enduro_is_real_load_and_blocks_next_day_run_quality(self):
        enduro = self.activity(
            "enduro-mon",
            "2026-09-28",
            "Enduro",
            report="Enduroskola. Teknisk körning.",
            elapsed_time_s=5400,
        )
        state = self.state_from([enduro])
        completed, micro, failures = self.deterministic_micro(state)
        self.assertEqual(completed["enduro_exposures"], 1)
        self.assertEqual(failures, [])
        day2 = {
            row["recipe_key"]
            for row in micro["slots"]
            if row["day_index"] == 2
        }
        self.assertFalse(
            day2.intersection(
                {
                    "run_threshold",
                    "run_threshold_short_reps",
                    "run_hill_quality",
                    "run_hill_continuous",
                    "run_easy_distance",
                    "run_easy_trail",
                }
            )
        )

    def test_completed_swim_is_not_followed_by_another_swim_when_a_spaced_slot_exists(self):
        swim = self.activity(
            "swim-wed",
            "2026-09-30",
            "Swim",
            report="Strukturerat simpass 3 700 m.",
            elapsed_time_s=4080,
            distance_m=3700,
        )
        state = self.state_from([swim], today=date(2026, 10, 1))
        completed, micro, failures = self.deterministic_micro(
            state,
            planning_date=date(2026, 10, 1),
        )

        self.assertEqual(failures, [])
        self.assertEqual(completed["family_day_indexes"]["swim"], [3])
        future_swim_days = [
            row["day_index"]
            for row in micro["slots"]
            if self.catalog["recipes"][row["recipe_key"]].get("sport") == "swim"
        ]
        self.assertTrue(future_swim_days)
        self.assertNotIn(
            4,
            future_swim_days,
            "a completed Wednesday swim must not be followed by Thursday swim when a spaced valid slot exists",
        )

    def test_positive_feedback_does_not_authorize_progression_before_absorption_contract(self):
        session = self.activity(
            "threshold-positive",
            "2026-09-29",
            "Run",
            report="4 x 8 min tröskel. Riktigt bra, stark och kunde gjort mer. RPE 6/10.",
            elapsed_time_s=3900,
        )
        state = self.state_from([session])
        threshold = state["capability_states"]["by_capability"]["run_threshold"]
        self.assertFalse(threshold["progression_ready"])
        self.assertNotEqual(threshold["progression_state"], "ready")

    def test_caution_feedback_keeps_progression_closed(self):
        session = self.activity(
            "threshold-caution",
            "2026-09-29",
            "Run",
            report="4 x 8 min tröskel. Sista intervallen krävde mycket huvud och kändes tung. RPE 8/10.",
            elapsed_time_s=3900,
        )
        state = self.state_from([session])
        threshold = state["capability_states"]["by_capability"]["run_threshold"]
        self.assertFalse(threshold["progression_ready"])
        self.assertIn(
            threshold["progression_reason_code"],
            {"direct_caution", "not_yet_absorbed", "recovery_window_open"},
        )

    def test_missing_feedback_is_not_tolerance(self):
        session = self.activity(
            "threshold-silent",
            "2026-09-29",
            "Run",
            report="4 x 8 min tröskel.",
            elapsed_time_s=3900,
        )
        state = self.state_from([session])
        threshold = state["capability_states"]["by_capability"]["run_threshold"]
        self.assertFalse(threshold["progression_ready"])
        self.assertIn(
            threshold["evidence_state"],
            {"demonstrated", "tolerated"},
        )

    def test_arbitrary_multipass_day_survives_when_structurally_valid(self):
        result = {
            "slots": [
                {
                    "day_index": 3,
                    "recipe_key": "swim_aerobic_technique",
                    "action": "establish",
                },
                {
                    "day_index": 3,
                    "recipe_key": "strength_core",
                    "action": "establish",
                },
                {
                    "day_index": 5,
                    "recipe_key": "run_threshold",
                    "action": "consolidate",
                },
                {
                    "day_index": 7,
                    "recipe_key": "run_easy_distance",
                    "action": "establish",
                },
            ]
        }
        failures = microcycle_guard_failures(
            result,
            self.meso,
            self.policy,
            self.catalog,
            date(2026, 9, 28),
            completed_context={},
            athlete_profile=None,
            planning_date=date(2026, 9, 28),
        )
        self.assertFalse(
            any("dubbelpass" in failure for failure in failures),
            failures,
        )

    def test_spontaneous_easy_training_does_not_remove_unrelated_primary_threshold(self):
        easy = self.activity(
            "easy-spontaneous",
            "2026-09-29",
            "TrailRun",
            report="Väldigt lugnt, höll pulsen runt 130. RPE 4/10.",
            elapsed_time_s=3600,
            distance_m=9000,
        )
        state = self.state_from([easy])
        completed, micro, failures = self.deterministic_micro(state)
        self.assertEqual(failures, [])
        self.assertIn("run_easy_distance", completed["planning_credits"])
        recipes = {row["recipe_key"] for row in micro["slots"]}
        self.assertTrue(
            {"run_threshold", "run_threshold_short_reps"} & recipes,
            "easy spontaneous training must not consume the primary threshold stimulus",
        )


if __name__ == "__main__":
    unittest.main()
