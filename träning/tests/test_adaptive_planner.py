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
    choose_option,
    fallback_mesocycle,
    fallback_microcycle,
    generate_mesocycle,
    generate_microcycle,
    goal_hash,
    materialize_strategy,
    mesocycle_schema,
    microcycle_guard_failures,
    microcycle_is_valid,
    microcycle_layout_failures,
    resolve_planning_target,
    target_week,
    validate_and_normalize_micro,
)
from build_athlete_state import build_state  # noqa: E402
from strategy_contracts import validate_training_strategy  # noqa: E402


class AdaptivePlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.goal = json.loads((ROOT / "data" / "goal.json").read_text(encoding="utf-8"))
        cls.policy = json.loads((ROOT / "data" / "planning_policy.json").read_text(encoding="utf-8"))
        cls.catalog = json.loads((ROOT / "data" / "workout_catalog.json").read_text(encoding="utf-8"))

    def test_structured_output_schema_avoids_unsupported_unique_items_keyword(self):
        schema = mesocycle_schema(
            [item["key"] for item in self.policy["strategy_base"]["capability_portfolio"]]
        )
        encoded = json.dumps(schema, sort_keys=True)
        self.assertNotIn("uniqueItems", encoded)

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

    def test_active_swimrun_goal_drives_deterministic_fallback(self):
        meso = fallback_mesocycle(self.goal, self.policy, {})
        self.assertEqual(
            meso["primary_capabilities"],
            ["run_threshold", "swim_aerobic", "run_easy_distance"],
        )
        self.assertNotIn("mtb_technical", meso["primary_capabilities"])
        self.assertTrue(
            any("performance_goals" in ref for ref in meso["evidence_refs"])
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

    def test_progression_can_move_beyond_demonstrated_four_by_eight(self):
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
        selected, floor, _, relation, _ = choose_option(
            "run_threshold", recipe, "progress", state
        )
        self.assertEqual(floor["id"], "run-threshold-4x8")
        self.assertEqual(selected["id"], "run-threshold-4x9")
        self.assertEqual(relation, "progress")

    def test_progression_moves_one_catalog_step_from_observed_floor(self):
        state = {
            "capability_facts": {
                "run_threshold": {
                    "evidence": [
                        {"work_minutes": 24.0, "kind": "performance_fingerprint"}
                    ]
                }
            }
        }
        recipe = self.catalog["recipes"]["run_threshold"]
        selected, floor, _, relation, _ = choose_option(
            "run_threshold", recipe, "progress", state
        )
        self.assertEqual(floor["id"], "run-threshold-3x8")
        self.assertEqual(selected["id"], "run-threshold-3x10")
        self.assertEqual(relation, "progress")

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

    def test_fallback_with_fixed_enduro_leaves_recovery_room(self):
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
        occupied = {1} | {row["day_index"] for row in slots}
        self.assertLess(len(occupied), 7)
        self.assertNotIn("mtb_technical", [row["recipe_key"] for row in slots])

    def test_micro_planner_revision_can_rebuild_first_day_current_week(self):
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
        stale_micro = {
            "planner_revision": 4,
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
        self.assertEqual(target, date(2026, 9, 21))
        self.assertTrue(active_replan)

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
                {"day_index": 5, "recipe_key": "swim_strength", "action": "establish", "rationale": "swim+strength", "evidence_refs": []},
                {"day_index": 7, "recipe_key": "run_easy_distance", "action": "consolidate", "rationale": "distance separerad från löpkvalitet", "evidence_refs": []},
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
        self.assertIn("swim_strength", recipes)

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

        combined = next(
            slot
            for slot in strategy["current_mesocycle"]["microcycle_template"]
            if "swim_aerobic" in slot["stimuli"]
            and "strength_core" in slot["stimuli"]
        )
        self.assertEqual(combined["priority_role"], "protected_support")
        self.assertNotIn("development_progression", combined)

        self.assertFalse(
            any(
                "run_hill_quality" in slot["stimuli"]
                for slot in strategy["current_mesocycle"]["microcycle_template"]
            ),
            "Sekundär backkvalitet ska inte tvingas in när primära stimuli, skyddad kapacitet och återhämtningsutrymme redan fyller mikrocykeln.",
        )


if __name__ == "__main__":
    unittest.main()
