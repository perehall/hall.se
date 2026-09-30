#!/usr/bin/env python3
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
    MICRO_PLANNER_REVISION,
    align_fallback_progression_with_block_intent,
    build_upcoming_strategy_after_active_replan,
    choose_option,
    completed_context_signature,
    completed_microcycle_context,
    fallback_mesocycle,
    fallback_microcycle,
    generate_mesocycle,
    generate_microcycle,
    goal_hash,
    goal_runtime_source_label,
    materialize_strategy,
    mesocycle_schema,
    mesocycle_is_valid,
    microcycle_guard_failures,
    microcycle_is_valid,
    microcycle_layout_failures,
    profile_planning_contract,
    reconcile_unaffected_future_workouts,
    resolve_planning_target,
    target_week,
    validate_and_normalize_micro,
)
from build_athlete_state import build_state  # noqa: E402
from goal_contracts import planning_goal_set  # noqa: E402
from strategy_contracts import validate_training_strategy  # noqa: E402


class AdaptivePlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.goal = json.loads((ROOT / "data" / "goal.json").read_text(encoding="utf-8"))
        cls.policy = json.loads((ROOT / "data" / "planning_policy.json").read_text(encoding="utf-8"))
        cls.catalog = json.loads((ROOT / "data" / "workout_catalog.json").read_text(encoding="utf-8"))

    def test_goal_runtime_source_label_tracks_all_supabase_read_paths(self):
        self.assertEqual(
            goal_runtime_source_label({"source": "supabase_db"}),
            "supabase:training_goal_document",
        )
        self.assertEqual(
            goal_runtime_source_label({"source": "supabase_rpc"}),
            "supabase:training_goal_document",
        )
        self.assertEqual(
            goal_runtime_source_label({"source": "json_fallback"}),
            "data/goal.json",
        )

    def test_structured_output_schema_avoids_unsupported_unique_items_keyword(self):
        schema = mesocycle_schema(
            [item["key"] for item in self.policy["strategy_base"]["capability_portfolio"]]
        )
        encoded = json.dumps(schema, sort_keys=True)
        self.assertNotIn("uniqueItems", encoded)
        self.assertIn('"goal_contributions"', encoded)

    def test_active_replan_builds_upcoming_week_with_its_own_empty_completed_context(self):
        meso = json.loads(
            (ROOT / "data" / "mesocycle_decision.json").read_text(encoding="utf-8")
        )
        # This unit test deliberately omits the persisted athlete-profile/start-state
        # documents. Keep the mesocycle authority consistent with that fixture;
        # production passes the actual hashes on both sides.
        meso["athlete_profile_hash"] = None
        meso["starting_state_hash"] = None
        athlete_state = {
            "recent_sessions": [
                {
                    "id": "threshold-current",
                    "date": "2026-09-29",
                    "family": "run",
                    "classification": "training",
                },
                {
                    "id": "strength-current",
                    "date": "2026-09-28",
                    "family": "strength",
                    "classification": "training",
                },
            ],
            "capability_facts": {
                "run_threshold": {
                    "evidence": [
                        {
                            "activity_id": "threshold-current",
                            "date": "2026-09-29",
                            "work_minutes": 32,
                        }
                    ]
                },
                "strength_unilateral": {
                    "evidence": [
                        {
                            "activity_id": "strength-current",
                            "date": "2026-09-28",
                        }
                    ]
                },
            },
            "dose_response": {},
        }

        def fail_model(_body):
            raise RuntimeError("offline test")

        future_strategy, trace = build_upcoming_strategy_after_active_replan(
            goal=self.goal,
            policy=self.policy,
            meso=meso,
            catalog=self.catalog,
            athlete_state=athlete_state,
            target_start=date(2026, 9, 28),
            goal_runtime_source={"source": "json_fallback"},
            request_fn=fail_model,
        )

        self.assertIsNotNone(future_strategy)
        self.assertEqual(trace["week_start"], "2026-10-05")
        self.assertEqual(trace["completed_context"]["activity_refs"], [])
        self.assertEqual(trace["completed_context"]["direct_capabilities"], [])
        self.assertEqual(trace["completed_context"]["planning_credits"], [])
        protected = future_strategy["current_mesocycle"]["capacity_protection"]
        self.assertEqual(protected["completed_current_microcycle"], [])

        recipes = {
            row["recipe_key"]
            for row in future_strategy["current_mesocycle"]["microcycle_template"]
        }
        self.assertTrue(
            {"run_threshold", "run_threshold_short_reps"} & recipes
        )
        self.assertIn("strength_core", recipes)
        self.assertTrue(
            {"swim_aerobic_technique", "swim_aerobic_endurance", "swim_aerobic_threshold"}
            & recipes
        )

    def test_active_mesocycle_targets_upcoming_week_not_current_copy(self):
        plan = {
            "meta": {
                "week_start": "2026-09-21",
                "week_end": "2026-09-27",
                "mesocycle_id": "meso-live",
                "requires_mesocycle_review": False,
            }
        }
        upcoming = {"meta": {"week_start": "2026-09-28", "week_end": "2026-10-04"}}
        target, active_replan = target_week(plan, upcoming, date(2026, 9, 21))
        self.assertEqual(target, date(2026, 9, 28))
        self.assertFalse(active_replan)

        micro = {
            "schema_version": 1,
            "week_start": "2026-09-21",
            "mesocycle_id": "meso-live",
            "slots": [{"day_index": 2, "recipe_key": "run_threshold"}],
            "source_hash": "old",
        }
        meso = {"id": "meso-live"}
        self.assertFalse(
            microcycle_is_valid(micro, meso, date(2026, 9, 28), source_hash_value="new")
        )

    def test_stranded_past_workout_reopens_live_week_for_rehoming(self):
        plan = {
            "meta": {
                "week_start": "2026-09-28",
                "week_end": "2026-10-04",
                "mesocycle_id": "meso-live",
                "microcycle_index": 1,
                "microcycle_total": 4,
                "requires_mesocycle_review": False,
            },
            "planned_workouts": [
                {
                    "date": "2026-09-29",
                    "sport": "swim",
                    "recipe_key": "swim_aerobic_technique",
                    "planning_status": "preliminary",
                }
            ],
        }
        upcoming = {"meta": {"week_start": "2026-10-05", "week_end": "2026-10-11"}}
        meso = {
            "id": "meso-live",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
            "goal_hash": goal_hash(self.goal),
        }
        target, active_replan = resolve_planning_target(
            plan,
            upcoming,
            meso,
            date(2026, 9, 30),
            goal=self.goal,
            current_completed_context={},
        )
        self.assertEqual(target, date(2026, 9, 28))
        self.assertTrue(active_replan)

    def test_first_day_goal_change_replans_current_week(self):
        plan = {
            "meta": {
                "week_start": "2026-09-21",
                "week_end": "2026-09-27",
                "mesocycle_id": "meso-live",
                "microcycle_index": 1,
                "microcycle_total": 4,
                "requires_mesocycle_review": False,
            }
        }
        upcoming = {"meta": {"week_start": "2026-09-28", "week_end": "2026-10-04"}}
        stale = {
            "id": "meso-live",
            "start_date": "2026-09-21",
            "end_date": "2026-10-18",
            "goal_hash": "0" * 64,
        }
        target, active_replan = resolve_planning_target(
            plan, upcoming, stale, date(2026, 9, 21), goal=self.goal
        )
        self.assertEqual(target, date(2026, 9, 21))
        self.assertTrue(active_replan)

    def test_midweek_goal_change_does_not_rewrite_elapsed_days(self):
        plan = {
            "meta": {
                "week_start": "2026-09-21",
                "week_end": "2026-09-27",
                "mesocycle_id": "meso-live",
                "microcycle_index": 1,
                "microcycle_total": 4,
                "requires_mesocycle_review": False,
            }
        }
        upcoming = {"meta": {"week_start": "2026-09-28", "week_end": "2026-10-04"}}
        stale = {
            "id": "meso-live",
            "start_date": "2026-09-21",
            "end_date": "2026-10-18",
            "goal_hash": "0" * 64,
        }
        target, active_replan = resolve_planning_target(
            plan, upcoming, stale, date(2026, 9, 23), goal=self.goal
        )
        self.assertEqual(target, date(2026, 9, 28))
        self.assertFalse(active_replan)

    def test_later_conflicting_mesocycle_cannot_orphan_midflight_block(self):
        plan = {
            "meta": {
                "week_start": "2026-09-21",
                "week_end": "2026-09-27",
                "mesocycle_id": "meso-live",
                "microcycle_index": 1,
                "microcycle_total": 4,
                "requires_mesocycle_review": False,
            }
        }
        upcoming = {"meta": {"week_start": "2026-09-28", "week_end": "2026-10-04"}}
        later = {
            "id": "meso-later",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
        }
        target, active_replan = resolve_planning_target(
            plan, upcoming, later, date(2026, 9, 21)
        )
        self.assertEqual(target, date(2026, 9, 21))
        self.assertTrue(active_replan)

    def test_completed_block_may_hand_authority_to_next_mesocycle(self):
        plan = {
            "meta": {
                "week_start": "2026-09-21",
                "week_end": "2026-09-27",
                "mesocycle_id": "meso-live",
                "microcycle_index": 4,
                "microcycle_total": 4,
                "requires_mesocycle_review": False,
            }
        }
        upcoming = {"meta": {"week_start": "2026-09-28", "week_end": "2026-10-04"}}
        later = {
            "id": "meso-later",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
        }
        target, active_replan = resolve_planning_target(
            plan, upcoming, later, date(2026, 9, 21)
        )
        self.assertEqual(target, date(2026, 9, 28))
        self.assertFalse(active_replan)

    def test_fixed_policy_contains_no_dynamic_goal_or_current_plan(self):
        self.assertNotIn("current_mesocycle", self.policy)
        self.assertNotIn("current_mesocycle", self.policy["strategy_base"])
        self.assertNotIn("north_star", self.policy["strategy_base"])
        self.assertNotIn("goal_contract", self.policy["strategy_base"])
        self.assertNotIn("current_priorities", self.policy["strategy_base"])
        self.assertIn("mesocycle_policy", self.policy)
        self.assertIn("microcycle_policy", self.policy)
        self.assertIn("event_horizon_policy", self.policy)

    def test_model_cannot_reclassify_hard_protected_capacity_as_secondary(self):
        payload = {
            "decision": "modify",
            "title": "test",
            "duration_weeks": 4,
            "goal_contribution": "test",
            "hypothesis": "test",
            "primary_capabilities": ["run_threshold", "mtb_technical"],
            "secondary_capabilities": ["run_hill_quality", "strength_unilateral", "strength_core"],
            "progression_axes": [
                {"capability": "run_threshold", "axis": "work_duration", "objective": "test"}
            ],
            "success_signals": ["a", "b"],
            "guardrails": ["a", "b"],
            "evidence_refs": ["goal.goal"],
            "uncertainties": [],
        }

        def fake_request(body):
            return {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps(payload, ensure_ascii=False)}
                        ],
                    }
                ],
            }

        result = generate_mesocycle(
            self.goal,
            self.policy,
            {"capability_facts": {}},
            {},
            date(2026, 9, 21),
            request_fn=fake_request,
        )
        self.assertEqual(result["secondary_capabilities"], ["run_hill_quality"])
        joined = " ".join(result["uncertainties"])
        self.assertIn("strength_unilateral", joined)
        self.assertIn("strength_core", joined)

    def test_goal_portfolio_keeps_allround_identity_separate_from_a_goal(self):
        rows = planning_goal_set(self.goal)
        by_id = {row["id"]: row for row in rows}
        self.assertEqual(by_id["allround-athlete"]["type"], "development")
        self.assertEqual(by_id["allround-athlete"]["role"], "enduring")
        self.assertEqual(by_id["otillo-aland-2027-top10"]["type"], "performance")
        self.assertEqual(by_id["otillo-aland-2027-top10"]["priority_class"], "A")

    def test_active_swimrun_goal_biases_fallback_without_erasing_allround_goal(self):
        meso = fallback_mesocycle(self.goal, self.policy, {}, date(2026, 9, 21))
        self.assertEqual(
            meso["primary_capabilities"],
            ["run_threshold", "swim_aerobic", "run_easy_distance"],
        )
        self.assertNotIn("mtb_technical", meso["primary_capabilities"])
        self.assertTrue(
            {"mtb_technical", "mtb_aerobic"}.intersection(meso["secondary_capabilities"])
        )
        self.assertTrue(
            any("performance_goals" in ref for ref in meso["evidence_refs"])
        )
        self.assertEqual(
            {row["goal_id"] for row in meso["goal_contributions"]},
            {"allround-athlete", "otillo-aland-2027-top10"},
        )

    def test_performance_goal_change_invalidates_goal_hash(self):
        altered = deepcopy(self.goal)
        altered["performance_goals"][0]["target"] = "Topp-5"
        self.assertNotEqual(goal_hash(self.goal), goal_hash(altered))

    def test_race_date_or_profile_change_invalidates_goal_hash(self):
        moved = deepcopy(self.goal)
        moved["performance_goals"][0]["event_date"] = "2027-08-15"
        self.assertNotEqual(goal_hash(self.goal), goal_hash(moved))

        changed_course = deepcopy(self.goal)
        changed_course["performance_goals"][0]["race_profile"]["swim_distance_m"] = 10000
        self.assertNotEqual(goal_hash(self.goal), goal_hash(changed_course))

    def test_generated_mesocycle_carries_verified_competition_context(self):
        payload = {
            "decision": "modify",
            "title": "race aware",
            "duration_weeks": 4,
            "goal_contribution": "Bygger relevant kapacitet mot Åland.",
            "hypothesis": "Kontrollerad utveckling.",
            "primary_capabilities": ["swim_aerobic", "run_threshold", "run_easy_distance"],
            "secondary_capabilities": ["run_hill_quality"],
            "progression_axes": [
                {"capability": "swim_aerobic", "axis": "consistency", "objective": "Bygg simuthållighet."}
            ],
            "success_signals": ["a", "b"],
            "guardrails": ["a", "b"],
            "evidence_refs": ["competition_context.race_profile", "athlete_state.capability_facts"],
            "uncertainties": [],
        }

        def fake_request(body):
            return {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps(payload, ensure_ascii=False)}
                        ],
                    }
                ],
            }

        result = generate_mesocycle(
            self.goal,
            self.policy,
            {"capability_facts": {}},
            {},
            date(2026, 9, 21),
            request_fn=fake_request,
        )
        context = result["competition_context"]
        self.assertEqual(
            {row["goal_id"] for row in result["goal_contributions"]},
            {"allround-athlete", "otillo-aland-2027-top10"},
        )
        self.assertEqual(context["event_date"], "2027-08-14")
        self.assertEqual(context["days_to_event"], 327)
        self.assertEqual(context["race_profile"]["total_distance_m"], 46540)
        self.assertEqual(context["race_profile"]["run_distance_m"], 36570)
        self.assertEqual(context["race_profile"]["swim_distance_m"], 9960)
        self.assertEqual(context["race_profile"]["elevation_gain_m"], 391)

    def test_athlete_state_extracts_explicit_threshold_and_hill_evidence(self):
        activities = {
            "activities": [
                {
                    "id": 1,
                    "start_date_local": "2026-09-15T18:00:00",
                    "sport_type": "Run",
                    "classification": "training",
                    "elapsed_time_s": 3600,
                    "distance_m": 11000,
                    "user_report": "4x8 min tempo, kontrollerat och pigg efteråt",
                },
                {
                    "id": 2,
                    "start_date_local": "2026-09-18T18:00:00",
                    "sport_type": "Run",
                    "classification": "training",
                    "elapsed_time_s": 3300,
                    "distance_m": 9000,
                    "user_report": "3x8 backar, superpigg",
                },
            ]
        }
        state = build_state(activities, {"entries": []}, today=date(2026, 9, 21))
        threshold = state["capability_facts"]["run_threshold"]["evidence"]
        hills = state["capability_facts"]["run_hill_quality"]["evidence"]
        self.assertEqual(threshold[0]["work_minutes"], 32.0)
        self.assertEqual(threshold[0]["protocol"], "4x8min")
        self.assertEqual(hills[0]["repetitions"], 24)
        self.assertEqual(hills[0]["protocol"], "3x8")

    def test_athlete_state_extracts_explicit_swim_threshold_evidence(self):
        activities = {
            "activities": [
                {
                    "id": 10,
                    "start_date_local": "2026-08-29T12:00:00",
                    "sport_type": "Swim",
                    "classification": "training",
                    "elapsed_time_s": 4500,
                    "distance_m": 4000,
                    "user_report": "Spontant simpass: Aerob+tröskel 4K, 4 000 m.",
                }
            ]
        }
        state = build_state(activities, {"entries": []}, today=date(2026, 9, 21))
        threshold = state["capability_facts"]["swim_threshold"]["evidence"]
        self.assertEqual(len(threshold), 1)
        self.assertEqual(threshold[0]["distance_m"], 4000)
        self.assertEqual(threshold[0]["protocol"], "aerob+threshold")

    def test_dose_response_distinguishes_absorbed_from_latest_caution(self):
        activities = {
            "activities": [
                {
                    "id": 100,
                    "start_date_local": "2026-09-16T18:00:00",
                    "sport_type": "Swim",
                    "classification": "training",
                    "elapsed_time_s": 3600,
                    "distance_m": 3200,
                    "user_report": "Bra kontroll. RPE 6/10. Känsla: Pigg.",
                },
                {
                    "id": 101,
                    "start_date_local": "2026-09-23T18:00:00",
                    "sport_type": "Swim",
                    "classification": "training",
                    "elapsed_time_s": 3550,
                    "distance_m": 3200,
                    "user_report": "Väldigt bra kontroll. RPE 6/10. Känsla: Kunde gjort mer.",
                },
                {
                    "id": 102,
                    "start_date_local": "2026-09-24T18:00:00",
                    "sport_type": "MountainBikeRide",
                    "classification": "training",
                    "elapsed_time_s": 4800,
                    "distance_m": 18000,
                    "user_report": "Känsla: Pigg.",
                },
                {
                    "id": 103,
                    "start_date_local": "2026-09-26T18:00:00",
                    "sport_type": "Swim",
                    "classification": "training",
                    "elapsed_time_s": 3800,
                    "distance_m": 3000,
                    "user_report": "RPE 8/10. Känsla: Trött.",
                },
            ]
        }
        planned = [
            {
                "date": "2026-09-16",
                "sport": "swim",
                "workout_key": "swim-100",
                "session": "Simning · 3 200 m · aerob uthållighet",
                "stimuli": ["swim_aerobic"],
            },
            {
                "date": "2026-09-23",
                "sport": "swim",
                "workout_key": "swim-101",
                "session": "Simning · 3 200 m · aerob uthållighet",
                "stimuli": ["swim_aerobic"],
            },
            {
                "date": "2026-09-26",
                "sport": "swim",
                "workout_key": "swim-103",
                "session": "Simning · 3 000 m · aerob uthållighet",
                "stimuli": ["swim_aerobic"],
            },
        ]
        state = build_state(
            activities,
            {"entries": []},
            today=date(2026, 9, 29),
            planned_workouts=planned,
        )
        profile = state["dose_response"]["by_capability"]["swim_aerobic"]
        self.assertEqual(profile["absorbed_value"], 3200.0)
        self.assertEqual(profile["latest_exposure"]["direct_response"]["signal"], "caution")
        self.assertFalse(profile["progression_ready"])

        recipe = self.catalog["recipes"]["swim_aerobic_endurance"]
        selected, floor, _, relation, evidence = choose_option(
            "swim_aerobic_endurance", recipe, "progress", state
        )
        self.assertEqual(floor["id"], "swim-aerobic-endurance-3200")
        self.assertEqual(selected["id"], "swim-aerobic-endurance-3200")
        self.assertEqual(relation, "hold")
        self.assertIn("absorberad nivå 3200", evidence)

    def test_missing_feedback_is_demonstrated_not_tolerated(self):
        activities = {
            "activities": [
                {
                    "id": 104,
                    "start_date_local": "2026-09-10T18:00:00",
                    "sport_type": "Swim",
                    "classification": "training",
                    "elapsed_time_s": 3550,
                    "distance_m": 3200,
                    "user_report": "Bra kontroll. RPE 6/10. Känsla: Pigg.",
                },
                {
                    "id": 105,
                    "start_date_local": "2026-09-17T18:00:00",
                    "sport_type": "Swim",
                    "classification": "training",
                    "elapsed_time_s": 3560,
                    "distance_m": 3200,
                    "user_report": "God kontroll. RPE 6/10. Känsla: Kunde gjort mer.",
                },
                {
                    "id": 106,
                    "start_date_local": "2026-09-24T18:00:00",
                    "sport_type": "Swim",
                    "classification": "training",
                    "elapsed_time_s": 4700,
                    "distance_m": 4000,
                    "user_report": None,
                },
            ]
        }
        planned = [
            {
                "date": "2026-09-10",
                "sport": "swim",
                "workout_key": "swim-104",
                "session": "Simning · 3 200 m · aerob uthållighet",
                "stimuli": ["swim_aerobic"],
            },
            {
                "date": "2026-09-17",
                "sport": "swim",
                "workout_key": "swim-105",
                "session": "Simning · 3 200 m · aerob uthållighet",
                "stimuli": ["swim_aerobic"],
            },
            {
                "date": "2026-09-24",
                "sport": "swim",
                "workout_key": "swim-106",
                "session": "Simning · 4 000 m · aerob uthållighet",
                "stimuli": ["swim_aerobic"],
            },
        ]
        state = build_state(
            activities,
            {"entries": []},
            today=date(2026, 9, 29),
            planned_workouts=planned,
        )
        profile = state["dose_response"]["by_capability"]["swim_aerobic"]
        self.assertEqual(profile["demonstrated_value"], 4000.0)
        self.assertEqual(profile["tolerated_value"], 3200.0)
        self.assertEqual(profile["absorbed_value"], 3200.0)
        self.assertEqual(profile["latest_exposure"]["response_status"], "demonstrated")
        self.assertFalse(profile["progression_ready"])

        recipe = self.catalog["recipes"]["swim_aerobic_endurance"]
        selected, floor, _, relation, evidence = choose_option(
            "swim_aerobic_endurance", recipe, "progress", state
        )
        self.assertEqual(floor["id"], "swim-aerobic-endurance-3200")
        self.assertEqual(selected["id"], "swim-aerobic-endurance-3200")
        self.assertEqual(relation, "hold")
        self.assertIn("absorberad nivå 3200", evidence)

    def test_demonstrated_max_without_feedback_cannot_raise_dose_floor(self):
        state = {
            "capability_facts": {
                "swim_aerobic": {
                    "longest_distance": {"distance_m": 4000}
                }
            },
            "dose_response": {
                "by_capability": {
                    "swim_aerobic": {
                        "demonstrated_value": 4000.0,
                        "tolerated_value": None,
                        "absorbed_value": None,
                        "progression_ready": False,
                        "progression_reason": "No feedback evidence.",
                    }
                }
            },
        }
        recipe = self.catalog["recipes"]["swim_aerobic_endurance"]
        selected, floor, _, relation, evidence = choose_option(
            "swim_aerobic_endurance", recipe, "consolidate", state
        )
        self.assertEqual(floor["id"], "swim-aerobic-endurance-3200")
        self.assertEqual(selected["id"], "swim-aerobic-endurance-3200")
        self.assertEqual(relation, "hold")
        self.assertIn("saknar verifierad tolererad/absorberad nivå", evidence)

    def test_recent_supportive_repeat_waits_for_complete_72h_window(self):
        activities = {
            "activities": [
                {
                    "id": 107,
                    "start_date_local": "2026-09-20T18:00:00",
                    "sport_type": "WeightTraining",
                    "classification": "training",
                    "elapsed_time_s": 2100,
                    "user_report": "RPE 5/10. Känsla: Pigg.",
                },
                {
                    "id": 108,
                    "start_date_local": "2026-09-28T18:00:00",
                    "sport_type": "WeightTraining",
                    "classification": "training",
                    "elapsed_time_s": 2150,
                    "user_report": "RPE 5/10. Känsla: Pigg.",
                },
            ]
        }
        planned = [
            {
                "date": "2026-09-20",
                "sport": "strength",
                "workout_key": "strength-107",
                "session": "Styrka/core · ca 35 min · styrkemall",
                "stimuli": ["strength_unilateral", "strength_core"],
            },
            {
                "date": "2026-09-28",
                "sport": "strength",
                "workout_key": "strength-108",
                "session": "Styrka/core · ca 35 min · styrkemall",
                "stimuli": ["strength_unilateral", "strength_core"],
            },
        ]
        state = build_state(
            activities,
            {"entries": []},
            today=date(2026, 9, 29),
            planned_workouts=planned,
        )
        profile = state["dose_response"]["by_capability"]["strength_unilateral"]
        self.assertEqual(
            profile["latest_exposure"]["response_status"],
            "tolerated_pending_recovery",
        )
        self.assertFalse(profile["progression_ready"])

    def test_repeated_supportive_threshold_response_becomes_absorbed(self):
        activities = {
            "activities": [
                {
                    "id": 110,
                    "start_date_local": "2026-09-08T18:00:00",
                    "sport_type": "Run",
                    "classification": "training",
                    "elapsed_time_s": 3700,
                    "distance_m": 12000,
                    "user_report": "4x8 min tröskel. RPE 6/10. Känsla: Pigg.",
                },
                {
                    "id": 111,
                    "start_date_local": "2026-09-09T18:00:00",
                    "sport_type": "Swim",
                    "classification": "training",
                    "elapsed_time_s": 3400,
                    "distance_m": 3000,
                    "user_report": "Känsla: Pigg.",
                },
                {
                    "id": 112,
                    "start_date_local": "2026-09-22T18:00:00",
                    "sport_type": "Run",
                    "classification": "training",
                    "elapsed_time_s": 3680,
                    "distance_m": 12800,
                    "user_report": "4x8 min tröskel. Bra kontroll. RPE 6/10. Känsla: Kunde gjort mer.",
                },
                {
                    "id": 113,
                    "start_date_local": "2026-09-23T18:00:00",
                    "sport_type": "Swim",
                    "classification": "training",
                    "elapsed_time_s": 3500,
                    "distance_m": 3200,
                    "user_report": "Känsla: Pigg.",
                },
            ]
        }
        state = build_state(activities, {"entries": []}, today=date(2026, 9, 29))
        profile = state["dose_response"]["by_capability"]["run_threshold"]
        self.assertEqual(profile["absorbed_value"], 32.0)
        self.assertTrue(profile["progression_ready"])
        self.assertIn("recent_7d", state["load_windows"]["windows"])

    def test_swim_threshold_recipe_uses_explicit_threshold_evidence(self):
        state = {
            "capability_facts": {
                "swim_threshold": {
                    "evidence": [
                        {"distance_m": 4000, "kind": "explicit_user_report"}
                    ]
                }
            }
        }
        recipe = self.catalog["recipes"]["swim_aerobic_threshold"]
        selected, floor, next_option, relation, _ = choose_option(
            "swim_aerobic_threshold", recipe, "consolidate", state
        )
        self.assertEqual(selected["id"], "swim-aerobic-threshold-4000")
        self.assertEqual(floor["id"], "swim-aerobic-threshold-4000")
        self.assertIsNone(next_option)
        self.assertEqual(relation, "hold")

    def test_threshold_recipe_uses_observed_history_not_old_baseline(self):
        state = {
            "capability_facts": {
                "run_threshold": {
                    "evidence": [
                        {"work_minutes": 32.0, "kind": "explicit_user_report"}
                    ]
                }
            }
        }
        recipe = self.catalog["recipes"]["run_threshold"]
        selected, floor, next_option, relation, _ = choose_option(
            "run_threshold", recipe, "consolidate", state
        )
        self.assertEqual(floor["id"], "run-threshold-4x8")
        self.assertEqual(selected["id"], "run-threshold-4x8")
        self.assertEqual(next_option["id"], "run-threshold-4x9")
        self.assertEqual(relation, "hold")

    def test_progression_can_move_beyond_absorbed_four_by_eight(self):
        state = {
            "capability_facts": {
                "run_threshold": {
                    "evidence": [
                        {"work_minutes": 32.0, "kind": "explicit_user_report"}
                    ]
                }
            },
            "dose_response": {
                "by_capability": {
                    "run_threshold": {
                        "absorbed_value": 32.0,
                        "tolerated_value": 32.0,
                        "progression_ready": True,
                        "progression_reason": "Repeated supportive response.",
                    }
                }
            },
        }
        recipe = self.catalog["recipes"]["run_threshold"]
        selected, floor, _, relation, _ = choose_option(
            "run_threshold", recipe, "progress", state
        )
        self.assertEqual(floor["id"], "run-threshold-4x8")
        self.assertEqual(selected["id"], "run-threshold-4x9")
        self.assertEqual(relation, "progress")

    def test_progression_moves_one_catalog_step_from_absorbed_floor(self):
        state = {
            "capability_facts": {
                "run_threshold": {
                    "evidence": [
                        {"work_minutes": 24.0, "kind": "performance_fingerprint"}
                    ]
                }
            },
            "dose_response": {
                "by_capability": {
                    "run_threshold": {
                        "absorbed_value": 24.0,
                        "tolerated_value": 24.0,
                        "progression_ready": True,
                        "progression_reason": "Repeated supportive response.",
                    }
                }
            },
        }
        recipe = self.catalog["recipes"]["run_threshold"]
        selected, floor, _, relation, _ = choose_option(
            "run_threshold", recipe, "progress", state
        )
        self.assertEqual(floor["id"], "run-threshold-3x8")
        self.assertEqual(selected["id"], "run-threshold-3x10")
        self.assertEqual(relation, "progress")

    def test_progression_is_blocked_when_only_demonstrated_or_tolerated(self):
        state = {
            "capability_facts": {
                "run_threshold": {
                    "evidence": [
                        {"work_minutes": 32.0, "kind": "explicit_user_report"}
                    ]
                }
            },
            "dose_response": {
                "by_capability": {
                    "run_threshold": {
                        "absorbed_value": None,
                        "tolerated_value": 32.0,
                        "progression_ready": False,
                        "progression_reason": "Dose completed but not yet absorbed.",
                    }
                }
            },
        }
        recipe = self.catalog["recipes"]["run_threshold"]
        selected, floor, _, relation, evidence = choose_option(
            "run_threshold", recipe, "progress", state
        )
        self.assertEqual(floor["id"], "run-threshold-4x8")
        self.assertEqual(selected["id"], "run-threshold-4x8")
        self.assertEqual(relation, "hold")
        self.assertIn("blockeras", evidence)

    def test_manual_starting_level_sets_conservative_first_dose_without_progression(self):
        state = {"capability_facts": {}, "dose_response": {"by_capability": {}}}
        starting_state = {
            "schema_version": 1,
            "status": "confirmed",
            "source_mode": "manual",
            "manual_state": {
                "disciplines": {
                    "run": {
                        "sessions_per_week": 3,
                        "long_run_minutes": 100,
                    }
                }
            },
            "confirmation": {"observed_representative": False},
        }
        recipe = self.catalog["recipes"]["run_easy_distance"]
        selected, floor, _, relation, evidence = choose_option(
            "run_easy_distance", recipe, "progress", state, starting_state
        )
        self.assertEqual(floor["id"], "run-easy-90")
        self.assertEqual(selected["id"], "run-easy-90")
        self.assertEqual(relation, "hold")
        self.assertIn("startläge", evidence)
        self.assertIn("inte som tolererad eller absorberad", evidence)

    def test_completed_threshold_is_credited_only_from_dated_capability_evidence(self):
        state = {
            "recent_sessions": [
                {
                    "id": 20284663236,
                    "date": "2026-09-22",
                    "family": "run",
                    "classification": "training",
                },
                {
                    "id": 20272196080,
                    "date": "2026-09-21",
                    "family": "strength",
                    "classification": "training",
                },
            ],
            "capability_facts": {
                "run_threshold": {
                    "evidence": [
                        {
                            "activity_id": 20284663236,
                            "date": "2026-09-22",
                            "work_minutes": 32,
                        }
                    ]
                }
            },
        }
        context = completed_microcycle_context(state, date(2026, 9, 21))
        self.assertEqual(context["strength_exposures"], 1)
        self.assertEqual(context["completed_slot_days"], 1)
        self.assertIn("run_threshold", context["direct_capabilities"])
        self.assertEqual(
            context["capability_refs"]["run_threshold"],
            ["20284663236"],
        )

    def test_structural_intent_match_gets_planning_credit_without_direct_capability_claim(self):
        state = {
            "recent_sessions": [
                {
                    "id": 77,
                    "date": "2026-09-29",
                    "family": "run",
                    "classification": "training",
                    "training_profile": {
                        "planning_credits": ["run_threshold"],
                        "stimuli": [],
                        "intent_matches": [
                            {
                                "relation": "fulfills_planned_dose",
                                "confidence": "high",
                                "stimuli": ["run_threshold"],
                            }
                        ],
                    },
                }
            ],
            "capability_facts": {},
        }
        context = completed_microcycle_context(state, date(2026, 9, 28))
        self.assertNotIn("run_threshold", context["direct_capabilities"])
        self.assertIn("run_threshold", context["planning_credits"])
        self.assertEqual(context["planning_credit_refs"]["run_threshold"], ["77"])

        meso = {
            "primary_capabilities": ["run_threshold", "swim_aerobic", "swim_technique"],
            "secondary_capabilities": ["run_easy_distance"],
        }
        result = fallback_microcycle(
            meso,
            self.policy,
            self.catalog,
            date(2026, 9, 28),
            completed_context=context,
        )
        self.assertNotIn(
            "run_threshold",
            [row["recipe_key"] for row in result["slots"]],
        )

    def test_fallback_mesocycle_primary_long_run_counts_as_supporting_breadth(self):
        meso = fallback_mesocycle(
            self.goal,
            self.policy,
            {},
            date(2026, 9, 28),
        )
        self.assertIn("run_easy_distance", meso["primary_capabilities"])
        result = fallback_microcycle(
            meso,
            self.policy,
            self.catalog,
            date(2026, 10, 5),
            completed_context={},
        )
        recipes = [row["recipe_key"] for row in result["slots"]]
        self.assertIn("run_easy_distance", recipes)
        self.assertNotIn(
            "run_hill_quality",
            recipes,
            msg="Primärt långpass ska inte tvinga fram extra backkvalitet bara för att fylla secondary-taxonomin.",
        )
        self.assertFalse(
            microcycle_guard_failures(
                result,
                meso,
                self.policy,
                self.catalog,
                date(2026, 10, 5),
                completed_context={},
            ),
            msg=json.dumps(result, ensure_ascii=False, indent=2),
        )

    def test_develop_fallback_progresses_one_primary_when_absorption_supports_it(self):
        meso = {
            "id": "meso-test",
            "start_date": "2026-09-28",
            "duration_weeks": 4,
            "primary_capabilities": ["run_threshold", "swim_aerobic", "swim_technique"],
            "secondary_capabilities": ["run_easy_distance"],
        }
        athlete_state = {
            "capability_facts": {
                "run_threshold": {
                    "evidence": [{"work_minutes": 32.0, "kind": "explicit_user_report"}]
                }
            },
            "dose_response": {
                "by_capability": {
                    "run_threshold": {
                        "absorbed_value": 32.0,
                        "tolerated_value": 32.0,
                        "progression_ready": True,
                        "progression_reason": "Repeated supportive response.",
                    }
                }
            },
        }
        result = fallback_microcycle(
            meso,
            self.policy,
            self.catalog,
            date(2026, 10, 5),
            completed_context={},
            athlete_state=athlete_state,
        )
        primary_progressions = [
            row for row in result["slots"]
            if row["action"] == "progress"
        ]
        self.assertEqual(len(primary_progressions), 1)
        self.assertEqual(
            primary_progressions[0]["recipe_key"],
            "run_threshold_short_reps",
        )
        self.assertTrue(
            any("progression_ready=true" in ref for ref in primary_progressions[0]["evidence_refs"])
        )

    def test_develop_fallback_records_data_backed_hold_when_progression_is_not_ready(self):
        meso = {
            "id": "meso-test",
            "start_date": "2026-09-28",
            "duration_weeks": 4,
            "primary_capabilities": ["run_threshold", "swim_aerobic", "swim_technique"],
            "secondary_capabilities": ["run_easy_distance"],
        }
        athlete_state = {
            "capability_facts": {
                "run_threshold": {
                    "evidence": [{"work_minutes": 32.0, "kind": "explicit_user_report"}]
                }
            },
            "dose_response": {
                "by_capability": {
                    "run_threshold": {
                        "absorbed_value": 32.0,
                        "tolerated_value": 32.0,
                        "progression_ready": False,
                        "progression_reason": "Senaste jämförbara exponeringen innehåller en varningssignal.",
                    }
                }
            },
        }
        result = fallback_microcycle(
            meso,
            self.policy,
            self.catalog,
            date(2026, 10, 5),
            completed_context={},
            athlete_state=athlete_state,
        )
        self.assertFalse(any(row["action"] == "progress" for row in result["slots"]))
        threshold = next(
            row for row in result["slots"]
            if row["recipe_key"] in {"run_threshold", "run_threshold_short_reps"}
        )
        self.assertIn("Develop-vecka konsolideras", threshold["rationale"])
        self.assertIn("varningssignal", threshold["rationale"])
        self.assertTrue(
            any(ref.endswith(":hold") for ref in threshold["evidence_refs"])
        )

    def test_develop_hold_alignment_is_idempotent_across_normalization_passes(self):
        meso = {
            "id": "meso-test",
            "start_date": "2026-09-28",
            "duration_weeks": 4,
            "primary_capabilities": ["run_threshold", "swim_aerobic", "swim_technique"],
            "secondary_capabilities": ["run_easy_distance"],
        }
        athlete_state = {
            "capability_facts": {
                "run_threshold": {
                    "evidence": [{"work_minutes": 32.0, "kind": "explicit_user_report"}]
                }
            },
            "dose_response": {
                "by_capability": {
                    "run_threshold": {
                        "absorbed_value": 32.0,
                        "tolerated_value": 32.0,
                        "progression_ready": False,
                        "progression_reason": "72 h-observationsfönstret är ännu inte komplett.",
                    }
                }
            },
        }
        once = fallback_microcycle(
            meso,
            self.policy,
            self.catalog,
            date(2026, 10, 5),
            completed_context={},
            athlete_state=athlete_state,
        )
        twice = align_fallback_progression_with_block_intent(
            once,
            meso,
            self.policy,
            self.catalog,
            athlete_state,
            date(2026, 10, 5),
        )
        threshold = next(
            row for row in twice["slots"]
            if row["recipe_key"] in {"run_threshold", "run_threshold_short_reps"}
        )
        self.assertEqual(
            threshold["rationale"].count("Develop-vecka konsolideras för detta primära stimulus"),
            1,
        )
        self.assertEqual(
            threshold["evidence_refs"].count(
                f"athlete_state.dose_response:{threshold['recipe_key']}:hold"
            ),
            1,
        )

    def test_future_develop_fallback_satisfies_its_own_structural_guards(self):
        meso = json.loads(
            (ROOT / "data" / "mesocycle_decision.json").read_text(encoding="utf-8")
        )
        result = fallback_microcycle(
            meso,
            self.policy,
            self.catalog,
            date(2026, 10, 5),
            completed_context={},
        )
        failures = microcycle_guard_failures(
            result,
            meso,
            self.policy,
            self.catalog,
            date(2026, 10, 5),
            completed_context={},
        )
        self.assertFalse(failures, msg=json.dumps(result, ensure_ascii=False, indent=2))

    def test_future_enduro_develop_week_requires_one_but_not_two_secondary_sessions(self):
        meso = json.loads(
            (ROOT / "data" / "mesocycle_decision.json").read_text(encoding="utf-8")
        )
        required_only = {
            "slots": [
                {"day_index": 2, "recipe_key": "swim_aerobic_technique", "action": "consolidate"},
                {"day_index": 3, "recipe_key": "run_threshold", "action": "consolidate"},
                {"day_index": 4, "recipe_key": "strength_core", "action": "establish"},
                {"day_index": 6, "recipe_key": "swim_aerobic_endurance", "action": "establish"},
            ]
        }
        failures = microcycle_guard_failures(
            required_only,
            meso,
            self.policy,
            self.catalog,
            date(2026, 10, 5),
            completed_context={},
        )
        self.assertTrue(
            any("saknar stödjande breddsexponering" in failure for failure in failures)
        )

        one_secondary = deepcopy(required_only)
        one_secondary["slots"].append(
            {"day_index": 6, "recipe_key": "run_easy_distance", "action": "consolidate"}
        )
        failures = microcycle_guard_failures(
            one_secondary,
            meso,
            self.policy,
            self.catalog,
            date(2026, 10, 5),
            completed_context={},
        )
        self.assertFalse(
            any("saknar stödjande breddsexponering" in failure for failure in failures)
        )
        self.assertFalse(
            any("begränsar sekundär belastning" in failure for failure in failures)
        )

        two_secondary = deepcopy(one_secondary)
        two_secondary["slots"].append(
            {"day_index": 5, "recipe_key": "mtb_technical", "action": "consolidate"}
        )
        failures = microcycle_guard_failures(
            two_secondary,
            meso,
            self.policy,
            self.catalog,
            date(2026, 10, 5),
            completed_context={},
        )
        self.assertTrue(
            any("begränsar sekundär belastning" in failure for failure in failures)
        )

    def test_heavy_sunday_is_rejected_before_next_fixed_enduro(self):
        failures = microcycle_layout_failures(
            [{"day_index": 7, "recipe_key": "run_easy_distance"}],
            self.catalog,
            date(2026, 10, 5),
        )
        self.assertTrue(
            any("söndagen direkt före nästa fasta enduro" in failure for failure in failures)
        )

        swim_only = microcycle_layout_failures(
            [{"day_index": 7, "recipe_key": "swim_aerobic_endurance"}],
            self.catalog,
            date(2026, 10, 5),
        )
        self.assertFalse(
            any("söndagen direkt före nästa fasta enduro" in failure for failure in swim_only)
        )

    def test_future_fixed_enduro_reserves_one_run_quality_slot_until_completed(self):
        meso = json.loads(
            (ROOT / "data" / "mesocycle_decision.json").read_text(encoding="utf-8")
        )
        proposal = {
            "slots": [
                {"day_index": 2, "recipe_key": "swim_aerobic_technique", "action": "consolidate"},
                {"day_index": 3, "recipe_key": "run_threshold", "action": "consolidate"},
                {"day_index": 4, "recipe_key": "strength_core", "action": "establish"},
                {"day_index": 5, "recipe_key": "run_hill_quality", "action": "consolidate"},
                {"day_index": 6, "recipe_key": "swim_aerobic_endurance", "action": "establish"},
                {"day_index": 7, "recipe_key": "run_easy_distance", "action": "consolidate"},
            ]
        }
        future_failures = microcycle_guard_failures(
            proposal,
            meso,
            self.policy,
            self.catalog,
            date(2026, 10, 5),
            completed_context={},
        )
        self.assertTrue(
            any("reserverad fast enduro" in failure for failure in future_failures)
        )

        completed_enduro_failures = microcycle_guard_failures(
            proposal,
            meso,
            self.policy,
            self.catalog,
            date(2026, 10, 5),
            completed_context={"enduro_exposures": 1},
        )
        self.assertFalse(
            any("reserverad fast enduro" in failure for failure in completed_enduro_failures)
        )

    def test_generic_run_without_capability_evidence_is_not_credited_as_threshold(self):
        state = {
            "recent_sessions": [
                {
                    "id": 7,
                    "date": "2026-09-22",
                    "family": "run",
                    "classification": "training",
                }
            ],
            "capability_facts": {},
        }
        context = completed_microcycle_context(state, date(2026, 9, 21))
        self.assertNotIn("run_threshold", context["direct_capabilities"])

    def test_completed_threshold_blocks_redundant_future_threshold(self):
        meso = {
            "primary_capabilities": ["swim_aerobic", "swim_technique", "run_threshold"],
            "secondary_capabilities": ["run_easy_distance"],
        }
        proposal = {
            "rationale": "duplicate threshold",
            "slots": [
                {"day_index": 3, "recipe_key": "swim_aerobic_technique", "action": "consolidate", "rationale": "swim", "evidence_refs": []},
                {"day_index": 5, "recipe_key": "run_threshold", "action": "consolidate", "rationale": "threshold", "evidence_refs": []},
                {"day_index": 6, "recipe_key": "swim_aerobic_technique", "action": "consolidate", "rationale": "swim", "evidence_refs": []},
                {"day_index": 7, "recipe_key": "run_easy_distance", "action": "consolidate", "rationale": "distance", "evidence_refs": []},
            ],
        }
        failures = microcycle_guard_failures(
            proposal,
            meso,
            self.policy,
            self.catalog,
            date(2026, 9, 21),
            completed_context={
                "strength_exposures": 1,
                "swim_exposures": 0,
                "completed_slot_days": 1,
                "direct_capabilities": ["run_threshold"],
            },
        )
        self.assertTrue(any("redundant" in item and "run_threshold" in item for item in failures))

    def test_live_fallback_rehomes_workouts_to_today_or_future(self):
        meso = {
            "primary_capabilities": ["swim_aerobic", "swim_technique", "run_threshold"],
            "secondary_capabilities": ["run_easy_distance"],
        }
        context = {
            "strength_exposures": 1,
            "swim_exposures": 0,
            "enduro_exposures": 1,
            "completed_slot_days": 1,
            "completed_day_indexes": [2],
            "direct_capabilities": ["run_threshold"],
            "planning_credits": ["run_threshold", "strength_unilateral"],
        }
        result = fallback_microcycle(
            meso,
            self.policy,
            self.catalog,
            date(2026, 9, 28),
            completed_context=context,
            planning_date=date(2026, 9, 30),
        )
        days = [row["day_index"] for row in result["slots"]]
        recipes = [row["recipe_key"] for row in result["slots"]]
        self.assertTrue(all(day >= 3 for day in days))
        self.assertIn("swim_aerobic_technique", recipes)
        self.assertIn("swim_aerobic_endurance", recipes)
        self.assertIn("run_easy_distance", recipes)

    def test_guard_rejects_new_workout_on_elapsed_live_day(self):
        meso = {
            "primary_capabilities": ["swim_aerobic", "swim_technique"],
            "secondary_capabilities": [],
        }
        proposal = {
            "rationale": "past slot",
            "slots": [
                {"day_index": 2, "recipe_key": "swim_aerobic_technique", "action": "consolidate"},
                {"day_index": 3, "recipe_key": "swim_aerobic_endurance", "action": "consolidate"},
                {"day_index": 5, "recipe_key": "strength_core", "action": "establish"},
                {"day_index": 6, "recipe_key": "run_easy_distance", "action": "consolidate"},
            ],
        }
        failures = microcycle_guard_failures(
            proposal,
            meso,
            self.policy,
            self.catalog,
            date(2026, 9, 28),
            completed_context={},
            planning_date=date(2026, 9, 30),
        )
        self.assertTrue(any("redan passerat" in item for item in failures))

    def test_fallback_credits_completed_threshold_and_strength(self):
        meso = {
            "primary_capabilities": ["swim_aerobic", "swim_technique", "run_threshold"],
            "secondary_capabilities": ["run_easy_distance"],
        }
        context = {
            "strength_exposures": 1,
            "swim_exposures": 0,
            "enduro_exposures": 1,
            "completed_slot_days": 1,
            "direct_capabilities": ["run_threshold"],
        }
        result = fallback_microcycle(
            meso,
            self.policy,
            self.catalog,
            date(2026, 9, 21),
            completed_context=context,
        )
        recipes = [row["recipe_key"] for row in result["slots"]]
        self.assertNotIn("run_threshold", recipes)
        self.assertEqual(recipes.count("swim_aerobic_technique"), 1)
        self.assertIn("swim_aerobic_endurance", recipes)
        self.assertIn("run_easy_distance", recipes)
        self.assertFalse(
            microcycle_guard_failures(
                result,
                meso,
                self.policy,
                self.catalog,
                date(2026, 9, 21),
                completed_context=context,
            )
        )

    def test_multiple_independent_slots_may_share_a_calendar_day(self):
        meso = {
            "primary_capabilities": ["swim_aerobic", "swim_technique"],
            "secondary_capabilities": [],
        }
        proposal = {
            "rationale": "separata pass samma dag",
            "slots": [
                {"day_index": 3, "recipe_key": "swim_aerobic_technique", "action": "establish", "rationale": "sim", "evidence_refs": []},
                {"day_index": 3, "recipe_key": "strength_core", "action": "establish", "rationale": "styrka", "evidence_refs": []},
                {"day_index": 5, "recipe_key": "swim_aerobic_technique", "action": "establish", "rationale": "sim 2", "evidence_refs": []},
                {"day_index": 7, "recipe_key": "run_easy_distance", "action": "consolidate", "rationale": "distans", "evidence_refs": []},
            ],
        }
        failures = microcycle_guard_failures(
            proposal,
            meso,
            self.policy,
            self.catalog,
            date(2026, 9, 21),
        )
        self.assertFalse(any("flera pass" in item for item in failures))

    def test_unknown_recipe_is_rejected_generically(self):
        meso = {
            "primary_capabilities": ["swim_aerobic", "swim_technique"],
            "secondary_capabilities": [],
        }
        proposal = {
            "rationale": "invalid recipe",
            "slots": [
                {"day_index": 3, "recipe_key": "unknown_recipe", "action": "establish", "rationale": "invalid", "evidence_refs": []},
                {"day_index": 5, "recipe_key": "swim_aerobic_technique", "action": "establish", "rationale": "sim", "evidence_refs": []},
                {"day_index": 6, "recipe_key": "run_easy_distance", "action": "consolidate", "rationale": "distans", "evidence_refs": []},
                {"day_index": 7, "recipe_key": "strength_core", "action": "establish", "rationale": "styrka", "evidence_refs": []},
            ],
        }
        failures = microcycle_guard_failures(
            proposal,
            meso,
            self.policy,
            self.catalog,
            date(2026, 9, 21),
        )
        self.assertTrue(any("okänt recipe_key" in item for item in failures))

    def test_day_after_fixed_enduro_rejects_run_or_mtb_load(self):
        rows = [
            {"day_index": 2, "recipe_key": "run_hill_quality"},
            {"day_index": 4, "recipe_key": "swim_aerobic_technique"},
        ]
        failures = microcycle_layout_failures(
            rows, self.catalog, date(2026, 9, 28)
        )
        self.assertTrue(any("dagen efter fast enduro" in item for item in failures))

    def test_adjacent_run_stressors_are_rejected(self):
        rows = [
            {"day_index": 4, "recipe_key": "run_threshold"},
            {"day_index": 5, "recipe_key": "run_easy_distance"},
        ]
        failures = microcycle_layout_failures(
            rows, self.catalog, date(2026, 10, 5)
        )
        self.assertTrue(any("två på varandra följande dagar" in item for item in failures))

    def test_run_quality_cannot_be_adjacent_to_mtb(self):
        rows = [
            {"day_index": 4, "recipe_key": "mtb_technical"},
            {"day_index": 5, "recipe_key": "run_threshold"},
        ]
        failures = microcycle_layout_failures(
            rows, self.catalog, date(2026, 10, 5)
        )
        self.assertTrue(any("direkt intill löpkvalitet" in item for item in failures))

    def test_long_run_cannot_be_adjacent_to_mtb(self):
        rows = [
            {"day_index": 6, "recipe_key": "mtb_technical"},
            {"day_index": 7, "recipe_key": "run_easy_distance"},
        ]
        failures = microcycle_layout_failures(
            rows, self.catalog, date(2026, 10, 5)
        )
        self.assertTrue(any("direkt intill MTB/XC" in item for item in failures))

    def test_mesocycle_profile_hash_must_match_activation_boundary(self):
        from adaptive_planner import mesocycle_is_valid

        decision = {
            "schema_version": 1,
            "planner_revision": 6,
            "goal_hash": goal_hash(self.goal),
            "athlete_profile_hash": "a" * 64,
            "start_date": "2026-10-05",
            "end_date": "2026-11-01",
            "primary_capabilities": ["run_threshold"],
        }
        self.assertTrue(
            mesocycle_is_valid(
                decision, self.goal, date(2026, 10, 5), "a" * 64
            )
        )
        self.assertFalse(
            mesocycle_is_valid(
                decision, self.goal, date(2026, 10, 5), None
            )
        )
        decision["athlete_profile_hash"] = None
        self.assertTrue(
            mesocycle_is_valid(
                decision, self.goal, date(2026, 10, 5), None
            )
        )

    def test_starting_state_hash_invalidates_mesocycle_authority(self):
        decision = {
            "schema_version": 1,
            "planner_revision": 6,
            "goal_hash": goal_hash(self.goal),
            "athlete_profile_hash": "a" * 64,
            "starting_state_hash": "b" * 64,
            "start_date": "2026-10-05",
            "end_date": "2026-11-01",
            "primary_capabilities": ["run_threshold"],
        }
        self.assertTrue(
            mesocycle_is_valid(
                decision,
                self.goal,
                date(2026, 10, 5),
                "a" * 64,
                "b" * 64,
            )
        )
        self.assertFalse(
            mesocycle_is_valid(
                decision,
                self.goal,
                date(2026, 10, 5),
                "a" * 64,
                "c" * 64,
            )
        )

    def test_profile_contract_keeps_declared_inputs_separate(self):
        profile = {
            "schema_version": 1,
            "status": "complete",
            "goals": [{"text": "Bli bättre på MTB", "target_date": None, "importance": "equal"}],
            "availability": {
                "monday": {"available": True, "minutes": 90},
                "tuesday": {"available": False, "minutes": None},
            },
            "preferences": {
                "frequency": {"preferred_days": 7, "min_days": 5, "max_days": 7},
                "double_sessions": "sometimes",
                "rest_days": "load_driven",
                "facilities": ["mtb", "indoor_bike"],
            },
            "constraints": {"fixed_commitments": "Enduro måndag", "other": ""},
            "coach_autonomy": "week_auto",
        }
        contract = profile_planning_contract(profile)
        self.assertEqual(contract["preferred_active_days"], 7)
        self.assertIn(2, contract["unavailable_days"])
        self.assertIn("indoor_bike", contract["facilities"])
        self.assertNotIn("capacity", contract)

    def test_declared_unavailable_day_is_hard_constraint(self):
        profile = {
            "availability": {"thursday": {"available": False, "minutes": None}},
            "preferences": {"frequency": {}, "double_sessions": "sometimes", "rest_days": "load_driven"},
            "constraints": {},
        }
        rows = [{"day_index": 4, "recipe_key": "swim_aerobic_technique"}]
        failures = microcycle_layout_failures(
            rows, self.catalog, date(2026, 10, 19), athlete_profile=profile
        )
        self.assertTrue(any("otillgänglig" in item for item in failures))

    def test_occasional_double_is_rejected_when_available_day_is_unused(self):
        profile = {
            "availability": {
                key: {"available": True, "minutes": None}
                for key in ("monday","tuesday","wednesday","thursday","friday","saturday","sunday")
            },
            "preferences": {
                "frequency": {"preferred_days": 7, "min_days": 5, "max_days": 7},
                "double_sessions": "sometimes",
                "rest_days": "load_driven",
            },
            "constraints": {},
        }
        rows = [
            {"day_index": 2, "recipe_key": "swim_aerobic_technique"},
            {"day_index": 2, "recipe_key": "strength_core"},
            {"day_index": 4, "recipe_key": "run_threshold"},
        ]
        failures = microcycle_layout_failures(
            rows, self.catalog, date(2026, 10, 19), athlete_profile=profile
        )
        self.assertTrue(any("dubbelpass klustras" in item for item in failures))

    def test_no_global_rule_requires_a_rest_day(self):
        rows = [
            {"day_index": day, "recipe_key": "swim_aerobic_technique"}
            for day in range(1, 8)
        ]
        failures = microcycle_layout_failures(
            rows, self.catalog, date(2026, 10, 19)
        )
        self.assertFalse(any("sju dagar" in item or "vilodag" in item for item in failures))

    def test_fallback_with_fixed_enduro_respects_mechanical_guards(self):
        meso = {
            "primary_capabilities": [
                "swim_aerobic",
                "swim_technique",
                "run_threshold",
            ],
            "secondary_capabilities": [
                "run_hill_quality",
                "run_easy_distance",
                "mtb_technical",
            ],
        }
        result = fallback_microcycle(
            meso, self.policy, self.catalog, date(2026, 9, 28)
        )
        slots = result["slots"]
        self.assertLessEqual(len(slots), 5)
        self.assertFalse(
            microcycle_layout_failures(
                slots, self.catalog, date(2026, 9, 28)
            )
        )
        day2 = next(row for row in slots if row["day_index"] == 2)
        self.assertEqual(day2["recipe_key"], "swim_aerobic_technique")
        self.assertNotIn("mtb_technical", [row["recipe_key"] for row in slots])

    def test_legacy_completed_context_signature_treats_missing_planning_credits_as_direct_capabilities(self):
        legacy = {
            "activity_refs": ["1"],
            "direct_capabilities": ["run_threshold"],
            "capability_refs": {"run_threshold": ["1"]},
        }
        current = {
            "activity_refs": ["1"],
            "direct_capabilities": ["run_threshold"],
            "planning_credits": ["run_threshold"],
            "capability_refs": {"run_threshold": ["1"]},
        }
        self.assertEqual(
            completed_context_signature(legacy),
            completed_context_signature(current),
        )

    def test_changed_completed_semantics_reopen_started_current_week(self):
        plan = {
            "meta": {
                "week_start": "2026-09-28",
                "week_end": "2026-10-04",
                "mesocycle_id": "meso-live",
                "microcycle_index": 1,
                "microcycle_total": 4,
                "requires_mesocycle_review": False,
            }
        }
        upcoming = {"meta": {"week_start": "2026-10-05", "week_end": "2026-10-11"}}
        meso = {
            "id": "meso-live",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
            "goal_hash": goal_hash(self.goal),
        }
        micro = {
            "week_start": "2026-09-28",
            "mesocycle_id": "meso-live",
            "completed_microcycle_context": {
                "activity_refs": ["20381137043"],
                "direct_capabilities": [],
                "capability_refs": {},
            },
        }
        current_context = {
            "activity_refs": ["20381137043"],
            "direct_capabilities": ["run_threshold"],
            "capability_refs": {"run_threshold": ["20381137043"]},
        }

        target, active_replan = resolve_planning_target(
            plan,
            upcoming,
            meso,
            date(2026, 9, 29),
            goal=self.goal,
            microcycle_decision=micro,
            current_completed_context=current_context,
        )

        self.assertEqual(target, date(2026, 9, 28))
        self.assertTrue(active_replan)

    def test_new_completed_activity_reopens_started_current_week(self):
        plan = {
            "meta": {
                "week_start": "2026-09-28",
                "week_end": "2026-10-04",
                "mesocycle_id": "meso-live",
                "microcycle_index": 1,
                "microcycle_total": 4,
                "requires_mesocycle_review": False,
            }
        }
        upcoming = {"meta": {"week_start": "2026-10-05", "week_end": "2026-10-11"}}
        meso = {
            "id": "meso-live",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
            "goal_hash": goal_hash(self.goal),
        }
        micro = {
            "week_start": "2026-09-28",
            "mesocycle_id": "meso-live",
            "completed_microcycle_context": {
                "activity_refs": ["20367593813"],
                "direct_capabilities": [],
                "capability_refs": {},
                "enduro_exposures": 1,
            },
        }
        current_context = {
            "activity_refs": ["20367593813", "20381137043"],
            "direct_capabilities": [],
            "capability_refs": {},
            "enduro_exposures": 1,
        }

        target, active_replan = resolve_planning_target(
            plan,
            upcoming,
            meso,
            date(2026, 9, 29),
            goal=self.goal,
            microcycle_decision=micro,
            current_completed_context=current_context,
        )

        self.assertEqual(target, date(2026, 9, 28))
        self.assertTrue(active_replan)

    def test_unchanged_completed_context_keeps_started_week_stable(self):
        plan = {
            "meta": {
                "week_start": "2026-09-28",
                "week_end": "2026-10-04",
                "mesocycle_id": "meso-live",
                "microcycle_index": 1,
                "microcycle_total": 4,
                "requires_mesocycle_review": False,
            }
        }
        upcoming = {"meta": {"week_start": "2026-10-05", "week_end": "2026-10-11"}}
        meso = {
            "id": "meso-live",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
            "goal_hash": goal_hash(self.goal),
        }
        context = {
            "activity_refs": ["20367593813"],
            "direct_capabilities": [],
            "capability_refs": {},
            "enduro_exposures": 1,
        }
        micro = {
            "week_start": "2026-09-28",
            "mesocycle_id": "meso-live",
            "completed_microcycle_context": context,
        }

        target, active_replan = resolve_planning_target(
            plan,
            upcoming,
            meso,
            date(2026, 9, 29),
            goal=self.goal,
            microcycle_decision=micro,
            current_completed_context=context,
        )

        self.assertEqual(target, date(2026, 10, 5))
        self.assertFalse(active_replan)

    def test_upcoming_micro_file_does_not_reopen_unchanged_live_week(self):
        context = {
            "activity_refs": ["20367593813", "20381137043"],
            "direct_capabilities": ["run_threshold"],
            "capability_refs": {"run_threshold": ["20381137043"]},
            "enduro_exposures": 1,
        }
        plan = {
            "meta": {
                "week_start": "2026-09-28",
                "week_end": "2026-10-04",
                "mesocycle_id": "meso-live",
                "microcycle_index": 1,
                "microcycle_total": 4,
                "requires_mesocycle_review": False,
                "capacity_protection": {"completed_context": context},
            }
        }
        upcoming = {"meta": {"week_start": "2026-10-05", "week_end": "2026-10-11"}}
        meso = {
            "id": "meso-live",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
            "goal_hash": goal_hash(self.goal),
        }
        upcoming_micro = {
            "week_start": "2026-10-05",
            "mesocycle_id": "meso-live",
            "completed_microcycle_context": {},
        }

        target, active_replan = resolve_planning_target(
            plan,
            upcoming,
            meso,
            date(2026, 9, 29),
            goal=self.goal,
            microcycle_decision=upcoming_micro,
            current_completed_context=context,
        )

        self.assertEqual(target, date(2026, 10, 5))
        self.assertFalse(active_replan)

    def test_live_plan_context_reopens_when_capability_semantics_change(self):
        previous_context = {
            "activity_refs": ["20367593813", "20381137043"],
            "direct_capabilities": [],
            "capability_refs": {},
            "enduro_exposures": 1,
        }
        current_context = {
            "activity_refs": ["20367593813", "20381137043"],
            "direct_capabilities": ["run_threshold"],
            "capability_refs": {"run_threshold": ["20381137043"]},
            "enduro_exposures": 1,
        }
        plan = {
            "meta": {
                "week_start": "2026-09-28",
                "week_end": "2026-10-04",
                "mesocycle_id": "meso-live",
                "microcycle_index": 1,
                "microcycle_total": 4,
                "requires_mesocycle_review": False,
                "capacity_protection": {"completed_context": previous_context},
            }
        }
        upcoming = {"meta": {"week_start": "2026-10-05", "week_end": "2026-10-11"}}
        meso = {
            "id": "meso-live",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
            "goal_hash": goal_hash(self.goal),
        }
        upcoming_micro = {
            "week_start": "2026-10-05",
            "mesocycle_id": "meso-live",
            "completed_microcycle_context": {},
        }

        target, active_replan = resolve_planning_target(
            plan,
            upcoming,
            meso,
            date(2026, 9, 29),
            goal=self.goal,
            microcycle_decision=upcoming_micro,
            current_completed_context=current_context,
        )

        self.assertEqual(target, date(2026, 9, 28))
        self.assertTrue(active_replan)

    def test_actual_driven_replan_preserves_unrelated_future_swim_and_removes_fulfilled_threshold(self):
        previous_context = {
            "activity_refs": ["enduro"],
            "direct_capabilities": [],
            "planning_credits": [],
            "capability_refs": {},
            "capability_day_indexes": {},
            "enduro_exposures": 1,
        }
        current = {
            "meta": {
                "week_start": "2026-09-28",
                "week_end": "2026-10-04",
                "capacity_protection": {"completed_context": previous_context},
            },
            "planned_workouts": [
                {
                    "date": "2026-09-30",
                    "sport": "run",
                    "recipe_key": "run_threshold",
                    "microcycle_slot": "run_threshold_1",
                    "stimuli": ["run_threshold"],
                    "session": "4 x 8",
                },
                {
                    "date": "2026-10-01",
                    "sport": "swim",
                    "recipe_key": "swim_aerobic_technique",
                    "microcycle_slot": "swim_1",
                    "stimuli": ["swim_aerobic", "swim_technique"],
                    "session": "Simning",
                },
                {
                    "date": "2026-10-02",
                    "sport": "run",
                    "recipe_key": "run_hill_quality",
                    "microcycle_slot": "hill_1",
                    "stimuli": ["run_hill_quality"],
                    "session": "Backe",
                },
            ],
        }
        rebuilt = {
            "meta": {"week_start": "2026-09-28", "week_end": "2026-10-04"},
            "planned_workouts": [
                {
                    "date": "2026-10-04",
                    "sport": "run",
                    "recipe_key": "run_easy_distance",
                    "microcycle_slot": "long_1",
                    "stimuli": ["run_easy_distance"],
                    "session": "Lugn distans",
                }
            ],
        }
        completed = {
            "activity_refs": ["enduro", "actual-threshold"],
            "direct_capabilities": ["run_threshold"],
            "planning_credits": ["run_threshold"],
            "capability_refs": {"run_threshold": ["actual-threshold"]},
            "capability_day_indexes": {"run_threshold": [2]},
            "enduro_exposures": 1,
            "completed_day_indexes": [2],
        }

        result = reconcile_unaffected_future_workouts(
            current,
            rebuilt,
            target_start=date(2026, 9, 28),
            today=date(2026, 9, 29),
            completed_context=completed,
        )
        rows = {
            (row.get("date"), row.get("recipe_key"))
            for row in result["planned_workouts"]
        }
        self.assertNotIn(("2026-09-30", "run_threshold"), rows)
        self.assertIn(("2026-10-01", "swim_aerobic_technique"), rows)
        self.assertIn(("2026-10-02", "run_hill_quality"), rows)
        self.assertIn(("2026-10-04", "run_easy_distance"), rows)

    def test_actual_driven_replan_does_not_preserve_adjacent_run_stressor(self):
        previous_context = {
            "activity_refs": [],
            "direct_capabilities": [],
            "planning_credits": [],
            "capability_refs": {},
            "capability_day_indexes": {},
        }
        current = {
            "meta": {
                "week_start": "2026-09-28",
                "week_end": "2026-10-04",
                "capacity_protection": {"completed_context": previous_context},
            },
            "planned_workouts": [
                {
                    "date": "2026-09-30",
                    "sport": "run",
                    "recipe_key": "run_hill_quality",
                    "microcycle_slot": "hill_1",
                    "stimuli": ["run_hill_quality"],
                    "session": "Backe",
                },
                {
                    "date": "2026-09-30",
                    "sport": "swim",
                    "recipe_key": "swim_aerobic_technique",
                    "microcycle_slot": "swim_1",
                    "stimuli": ["swim_aerobic", "swim_technique"],
                    "session": "Simning",
                },
            ],
        }
        rebuilt = {
            "meta": {"week_start": "2026-09-28", "week_end": "2026-10-04"},
            "planned_workouts": [],
        }
        completed = {
            "activity_refs": ["actual-threshold"],
            "direct_capabilities": ["run_threshold"],
            "planning_credits": ["run_threshold"],
            "capability_refs": {"run_threshold": ["actual-threshold"]},
            "capability_day_indexes": {"run_threshold": [2]},
            "completed_day_indexes": [2],
        }

        result = reconcile_unaffected_future_workouts(
            current,
            rebuilt,
            target_start=date(2026, 9, 28),
            today=date(2026, 9, 29),
            completed_context=completed,
        )
        recipes = [row.get("recipe_key") for row in result["planned_workouts"]]
        self.assertNotIn("run_hill_quality", recipes)
        self.assertIn("swim_aerobic_technique", recipes)

    def test_micro_planner_revision_does_not_rebuild_started_current_week(self):
        plan = {
            "meta": {
                "week_start": "2026-09-21",
                "week_end": "2026-09-27",
                "mesocycle_id": "meso-live",
                "microcycle_index": 1,
                "microcycle_total": 4,
                "requires_mesocycle_review": False,
            }
        }
        upcoming = {"meta": {"week_start": "2026-09-28", "week_end": "2026-10-04"}}
        meso = {
            "id": "meso-live",
            "start_date": "2026-09-21",
            "end_date": "2026-10-18",
            "goal_hash": goal_hash(self.goal),
        }
        self.assertEqual(MICRO_PLANNER_REVISION, 17)
        stale_micro = {
            "planner_revision": 6,
            "week_start": "2026-09-28",
            "mesocycle_id": "meso-live",
        }
        target, active_replan = resolve_planning_target(
            plan,
            upcoming,
            meso,
            date(2026, 9, 21),
            goal=self.goal,
            microcycle_decision=stale_micro,
        )
        self.assertEqual(target, date(2026, 9, 28))
        self.assertFalse(active_replan)

    def test_microcycle_guard_explains_missing_protected_capacity(self):
        meso = fallback_mesocycle(self.goal, self.policy, {})
        bad = {
            "rationale": "bad",
            "slots": [
                {"day_index": 2, "recipe_key": "run_threshold", "action": "consolidate", "rationale": "x", "evidence_refs": []},
                {"day_index": 4, "recipe_key": "mtb_technical", "action": "consolidate", "rationale": "x", "evidence_refs": []},
                {"day_index": 5, "recipe_key": "run_hill_quality", "action": "consolidate", "rationale": "x", "evidence_refs": []},
                {"day_index": 7, "recipe_key": "run_easy_distance", "action": "consolidate", "rationale": "x", "evidence_refs": []},
            ],
        }
        failures = microcycle_guard_failures(
            bad, meso, self.policy, self.catalog, date(2026, 9, 28)
        )
        self.assertTrue(any("simexponeringar" in item for item in failures))
        self.assertTrue(any("styrka/core" in item for item in failures))

    def test_rejected_model_microcycle_is_repaired_before_fallback(self):
        meso = fallback_mesocycle(self.goal, self.policy, {})
        meso.update(
            {
                "id": "meso-repair",
                "start_date": "2026-09-28",
                "end_date": "2026-10-25",
                "evaluation_date": "2026-10-26",
            }
        )
        invalid = {
            "rationale": "missar skyddad kapacitet",
            "slots": [
                {"day_index": 2, "recipe_key": "run_threshold", "action": "consolidate", "rationale": "threshold", "evidence_refs": []},
                {"day_index": 4, "recipe_key": "mtb_technical", "action": "consolidate", "rationale": "mtb", "evidence_refs": []},
                {"day_index": 5, "recipe_key": "run_hill_quality", "action": "consolidate", "rationale": "hill", "evidence_refs": []},
                {"day_index": 7, "recipe_key": "run_easy_distance", "action": "consolidate", "rationale": "distance", "evidence_refs": []},
            ],
        }
        repaired = {
            "rationale": "reparerad mot alla hårda krav och belastningsavstånd",
            "slots": [
                {"day_index": 2, "recipe_key": "swim_aerobic_technique", "action": "establish", "rationale": "låg benbelastning efter enduro", "evidence_refs": []},
                {"day_index": 3, "recipe_key": "run_threshold", "action": "consolidate", "rationale": "threshold med marginal efter enduro", "evidence_refs": []},
                {"day_index": 5, "recipe_key": "swim_aerobic_technique", "action": "establish", "rationale": "andra simexponeringen", "evidence_refs": []},
                {"day_index": 5, "recipe_key": "strength_core", "action": "establish", "rationale": "separat styrkepass samma dag", "evidence_refs": []},
                {"day_index": 6, "recipe_key": "run_easy_distance", "action": "consolidate", "rationale": "distance separerad från löpkvalitet och från nästa fasta enduro", "evidence_refs": []},
            ],
        }
        replies = [invalid, repaired]
        calls = []

        def fake_request(body):
            calls.append(body)
            payload = replies.pop(0)
            return {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps(payload, ensure_ascii=False)}
                        ],
                    }
                ],
            }

        result = generate_microcycle(
            meso,
            self.goal,
            self.policy,
            self.catalog,
            {"capability_facts": {}},
            date(2026, 9, 28),
            request_fn=fake_request,
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["source"], "openai_repaired")
        self.assertEqual(result["guard_repair"]["result"], "accepted")
        self.assertTrue(result["guard_repair"]["initial_failures"])
        self.assertEqual(result["rationale"], repaired["rationale"])
        self.assertFalse(
            microcycle_guard_failures(
                result, meso, self.policy, self.catalog, date(2026, 9, 28)
            )
        )

    def test_microcycle_guard_rejects_calendar_fill_without_protected_capacity(self):
        meso = fallback_mesocycle(self.goal, self.policy, {})
        bad = {
            "rationale": "bad",
            "slots": [
                {"day_index": 2, "recipe_key": "run_threshold", "action": "progress", "rationale": "x", "evidence_refs": []},
                {"day_index": 4, "recipe_key": "mtb_technical", "action": "progress", "rationale": "x", "evidence_refs": []},
                {"day_index": 5, "recipe_key": "run_hill_quality", "action": "consolidate", "rationale": "x", "evidence_refs": []},
                {"day_index": 7, "recipe_key": "run_easy_distance", "action": "consolidate", "rationale": "x", "evidence_refs": []},
            ],
        }
        normalized, model_valid = validate_and_normalize_micro(
            bad, meso, self.policy, self.catalog, date(2026, 9, 21)
        )
        self.assertFalse(model_valid)
        recipes = [row["recipe_key"] for row in normalized["slots"]]
        self.assertIn("swim_aerobic_technique", recipes)
        self.assertIn("strength_core", recipes)

    def test_generated_strategy_is_contract_valid_and_traceable(self):
        meso = fallback_mesocycle(self.goal, self.policy, {})
        meso.update(
            {
                "id": "20260921-test",
                "source": "deterministic_test",
                "source_hash": "a" * 64,
                "start_date": "2026-09-21",
                "end_date": "2026-10-18",
                "evaluation_date": "2026-10-19",
            }
        )
        micro = fallback_microcycle(meso, self.policy, self.catalog, date(2026, 9, 21))
        micro.update(
            {
                "schema_version": 1,
                "source": "deterministic_test",
                "source_hash": "b" * 64,
                "generated_at_utc": "2026-09-21T08:00:00+00:00",
                "week_start": "2026-09-21",
                "week_key": "2026-W39",
                "mesocycle_id": meso["id"],
            }
        )
        athlete = {
            "capability_facts": {
                "run_threshold": {"evidence": [{"work_minutes": 32.0}]},
                "run_hill_quality": {"evidence": [{"repetitions": 24}]},
                "run_easy_distance": {"longest_duration": {"elapsed_time_s": 7186}},
                "swim_aerobic": {"longest_distance": {"distance_m": 4000}},
                "mtb_technical": {"longest_duration": {"elapsed_time_s": 5400}},
                "strength_unilateral": {"longest_duration": {"elapsed_time_s": 2160}},
            }
        }
        strategy = materialize_strategy(
            self.goal, self.policy, meso, micro, self.catalog, athlete
        )
        validate_training_strategy(strategy)
        self.assertEqual(strategy["goal_contract"]["source_schema_version"], 3)
        self.assertEqual(
            {row["id"] for row in strategy["goal_contract"]["goal_set"]},
            {"allround-athlete", "otillo-aland-2027-top10"},
        )
        self.assertEqual(
            {row["goal_id"] for row in strategy["current_mesocycle"]["goal_contributions"]},
            {"allround-athlete", "otillo-aland-2027-top10"},
        )
        self.assertEqual(
            strategy["generated_planning"]["source_mesocycle_decision"],
            "data/mesocycle_decision.json",
        )
        self.assertEqual(
            next(
                item["state"]
                for item in strategy["strategic_readiness"]
                if item["key"] == "swimrun"
            ),
            "active_focus",
        )
        priority_keys = [item["key"] for item in strategy["current_priorities"]]
        self.assertEqual(len(priority_keys), len(set(priority_keys)))
        self.assertNotEqual(
            strategy["current_priorities"],
            self.policy["strategy_base"].get("current_priorities"),
        )
        self.assertEqual(
            strategy["current_mesocycle"]["decision_trace"]["microcycle_week_key"],
            "2026-W39",
        )
        threshold = next(
            slot
            for slot in strategy["current_mesocycle"]["microcycle_template"]
            if "run_threshold" in slot["stimuli"]
        )
        self.assertEqual(threshold["baseline_option_id"], "run-threshold-4x8")
        self.assertEqual(
            threshold["progression_target_option_id"],
            "run-threshold-4x9",
        )
        self.assertNotIn("progression_ceiling_reason", threshold)

        swim_slots = [
            slot
            for slot in strategy["current_mesocycle"]["microcycle_template"]
            if "swim_aerobic" in slot["stimuli"]
        ]
        strength = next(
            slot
            for slot in strategy["current_mesocycle"]["microcycle_template"]
            if "strength_core" in slot["stimuli"]
        )
        self.assertEqual(strength["priority_role"], "protected_support")
        self.assertNotIn("development_progression", strength)
        self.assertGreaterEqual(len(swim_slots), 1)
        self.assertFalse(
            any(
                "swim_aerobic" in slot["stimuli"] and "strength_core" in slot["stimuli"]
                for slot in strategy["current_mesocycle"]["microcycle_template"]
            )
        )

        self.assertFalse(
            any(
                "run_hill_quality" in slot["stimuli"]
                for slot in strategy["current_mesocycle"]["microcycle_template"]
            ),
            "Sekundär backkvalitet ska inte tvingas in när primära stimuli, skyddad kapacitet och återhämtningsutrymme redan fyller mikrocykeln.",
        )


if __name__ == "__main__":
    unittest.main()
