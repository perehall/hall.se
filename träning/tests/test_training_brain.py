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

from coach_rules import planning_window  # noqa: E402
from finalize_training_brain_ui import SECTION_START, apply_ui, decorate_focus_card, render_section  # noqa: E402
from strategy_contracts import StrategyContractError, validate_training_strategy  # noqa: E402
from training_brain import resolve_mesocycle, resolve_next_decision, resolve_today, resolve_weather_advice  # noqa: E402


class TrainingBrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.strategy = json.loads((ROOT / "data" / "training_strategy.json").read_text(encoding="utf-8"))
        cls.plan = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))

    def test_current_strategy_contract_is_valid(self):
        self.assertTrue(validate_training_strategy(self.strategy))

    def test_unknown_protected_stimulus_fails_closed(self):
        strategy = deepcopy(self.strategy)
        strategy["current_mesocycle"]["protected_stimuli"].append("invented_stimulus")
        with self.assertRaises(StrategyContractError):
            validate_training_strategy(strategy)

    def test_long_term_goal_is_primary_contract(self):
        hierarchy = self.strategy["planning_hierarchy"]
        self.assertEqual(
            hierarchy["order"],
            ["north_star", "mesocycle", "microcycle", "near_term", "session"],
        )
        self.assertTrue(self.strategy["decision_policy"]["long_term_goal_is_primary"])
        self.assertTrue(self.strategy["decision_policy"]["concrete_near_term_plan_by_default"])
        self.assertFalse(self.strategy["decision_policy"]["defer_open_dose_until_near_load_known"])
        self.assertTrue(
            self.strategy["decision_policy"]["adjust_planned_session_only_when_new_evidence_justifies"]
        )
        self.assertTrue(
            self.strategy["decision_policy"]["near_term_changes_must_serve_long_term_direction"]
        )
        self.assertIn("Kalenderveckan är ett presentations- och navigeringslager", hierarchy["calendar_role"])
        self.assertEqual(self.strategy["current_mesocycle"]["microcycle_structure"]["length_days"], 7)
        self.assertIn("microcycle_template", self.strategy["current_mesocycle"])
        self.assertNotIn("weekly_template", self.strategy["current_mesocycle"])
        for slot in self.strategy["current_mesocycle"]["microcycle_template"]:
            self.assertNotIn("dos öppen", slot["session"].lower())
            self.assertTrue(slot.get("dose_options"), slot["slot"])
            self.assertTrue(slot.get("baseline_option_id"), slot["slot"])
            baseline = next(
                option for option in slot["dose_options"]
                if option["id"] == slot["baseline_option_id"]
            )
            self.assertEqual(slot["session"], baseline["session"])

        broken = deepcopy(self.strategy)
        broken["decision_policy"]["long_term_goal_is_primary"] = False
        with self.assertRaises(StrategyContractError):
            validate_training_strategy(broken)


        stale_goal = deepcopy(self.strategy)
        stale_goal["current_mesocycle"]["goal_basis_hash"] = "0" * 64
        with self.assertRaises(StrategyContractError):
            validate_training_strategy(stale_goal)

    def test_next_decision_crosses_calendar_week_boundary(self):
        active = {
            "days": [
                {
                    "date": "2026-08-30",
                    "label": "Söndag",
                    "status": "completed",
                    "session": "Löpning · lugn distans",
                    "sport": "run",
                    "stimuli": ["run_easy_distance"],
                }
            ]
        }
        upcoming = {
            "days": [
                {
                    "date": "2026-08-31",
                    "label": "Måndag",
                    "status": "planned",
                    "planning_status": "fixed",
                    "session": "Enduroskola · fast tillfälle",
                    "sport": "enduro",
                    "classification": "training",
                    "manual_lock": True,
                    "priority_role": "anchor",
                    "stimuli": ["enduro_technical"],
                },
                {
                    "date": "2026-09-01",
                    "label": "Tisdag",
                    "status": "preliminary",
                    "session": "Löpning · kontrollerad tröskel · 3 × 8 min / 90 s jogg",
                    "sport": "run",
                    "priority_role": "anchor",
                    "stimuli": ["run_threshold"],
                },
            ]
        }

        window = planning_window(active, upcoming)
        decision = resolve_next_decision(window, [], self.strategy, date(2026, 8, 30))

        self.assertEqual(decision["date"], "2026-08-31")
        self.assertEqual(decision["label"], "Måndag")
        self.assertIn("Enduroskola", decision["headline"])

    def test_week_boundary_window_fails_closed_on_gap(self):
        active = {"days": [{"date": "2026-08-30"}]}
        upcoming = {"days": [{"date": "2026-09-01"}]}
        with self.assertRaises(RuntimeError):
            planning_window(active, upcoming)

    def test_today_uses_matching_actual_activity_as_completed(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-26",
                    "status": "planned",
                    "session": "Swimrun · klubbpass",
                    "sport": "swimrun",
                    "priority_role": "flex",
                    "stimuli": ["swim_aerobic"],
                }
            ]
        }
        activities = [
            {
                "id": 1,
                "sport_type": "Swimrun",
                "display_label": "Swimrun · test",
                "start_date_local": "2026-08-26T07:00:00",
            }
        ]
        brief = resolve_today(plan, activities, self.strategy, date(2026, 8, 26))
        self.assertTrue(brief["fulfilled"])
        self.assertEqual(brief["status"], "GENOMFÖRT")
        self.assertIn("Swimrun", brief["why"])
        self.assertIn("Sim aerob kapacitet", brief["stimuli"])


    def test_spontaneous_same_day_workout_stays_separate_from_plan(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-29",
                    "status": "planned",
                    "session": "Simning · planerat tröskelpass",
                    "sport": "swim",
                    "priority_role": "flex",
                    "stimuli": ["swim_aerobic"],
                    "reason": "Planerat pass.",
                }
            ]
        }
        activities = [
            {
                "id": 99,
                "sport_type": "Swim",
                "display_label": "Simning · aerob + tröskel",
                "start_date_local": "2026-08-29T11:00:00",
                "distance_m": 4000,
                "plan_relation": "separate",
            }
        ]
        brief = resolve_today(plan, activities, self.strategy, date(2026, 8, 29))
        self.assertFalse(brief["fulfilled"])
        self.assertEqual(brief["status"], "PLANERAT")
        self.assertIn("planerat tröskelpass", brief["headline"])

        section = render_section(
            plan,
            {"activities": activities},
            self.strategy,
            date(2026, 8, 29),
        )
        self.assertIn('data-separate-workout="true"', section)
        self.assertIn("Spontant pass · registrerat separat", section)
        self.assertIn("Simning · aerob + tröskel · 4 000 m", section)
        self.assertIn("markerar inte dagens planerade pass som genomfört", section)


    def test_legacy_open_flag_does_not_create_user_facing_dose_warning(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-27",
                    "status": "planned",
                    "session": "MTB/XC · 60 min · teknik + lugn aerob stig",
                    "sport": "bike",
                    "dose_open": True,
                    "priority_role": "flex",
                    "stimuli": ["mtb_technical", "mtb_aerobic"],
                }
            ]
        }
        brief = resolve_today(plan, [], self.strategy, date(2026, 8, 27))
        self.assertEqual(brief["status"], "PLANERAT")
        self.assertNotIn("DOSBESLUT", brief["status"])
        self.assertNotIn("dosen är fortfarande öppen", brief["why"])

    def test_resolved_same_day_dose_is_shown_as_normal_plan(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-27",
                    "status": "planned",
                    "session": "MTB/XC · 60 min · teknik + lugn aerob stig",
                    "sport": "bike",
                    "dose_open": False,
                    "priority_role": "flex",
                    "stimuli": ["mtb_technical", "mtb_aerobic"],
                }
            ]
        }
        brief = resolve_today(plan, [], self.strategy, date(2026, 8, 27))
        self.assertEqual(brief["status"], "PLANERAT")
        self.assertIn("60 min", brief["headline"])

    def test_next_session_is_concrete_before_previous_session_is_completed(self):
        decision = resolve_next_decision(self.plan, [], self.strategy, date(2026, 8, 31))
        self.assertEqual(decision["date"], "2026-09-01")
        self.assertIn("3 × 8 min", decision["headline"])
        self.assertIn("Grundplan", decision["note"])

    def test_weather_advice_prefers_trainer_for_wet_mtb_after_run_quality(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-28",
                    "status": "completed",
                    "session": "Löpning · backkvalitet",
                    "sport": "run",
                    "stimuli": ["run_hill_quality"],
                },
                {
                    "date": "2026-08-29",
                    "status": "conditional",
                    "session": "MTB/XC · distans · 75 min · huvudsakligen lugnt",
                    "sport": "bike",
                    "priority_role": "flex",
                    "stimuli": ["mtb_aerobic", "mtb_technical"],
                },
                {
                    "date": "2026-08-30",
                    "status": "planned",
                    "session": "Löpning · lugn distans · 75 min",
                    "sport": "run",
                    "stimuli": ["run_easy_distance"],
                },
            ]
        }
        activities = [
            {
                "id": 77,
                "sport_type": "Run",
                "start_date_local": "2026-08-28T17:00:00",
            }
        ]
        weather = {
            "status": "ok",
            "daily": {
                "2026-08-29": {
                    "symbol_code": 18,
                    "precip_probability_max_pct": 90,
                }
            },
        }
        settings = {
            "indoor_alternatives": {
                "trainer": {"available": True, "bike_type": "gravel", "same_geometry_as_mtb": False},
                "treadmill": {"available": True},
                "swim": {"available": True},
                "gym": {"available": True},
            }
        }

        advice = resolve_weather_advice(
            plan, activities, weather, settings, date(2026, 8, 29)
        )
        self.assertIsNotNone(advice)
        self.assertIn("Trainer på gravel", advice["recommendation"])
        self.assertIn("MTB-teknikdelen ersätts inte", advice["note"])
        self.assertIn("extra löpmekanisk belastning", advice["note"])
        self.assertIn("Löpband är därför inte förstahandsval", advice["note"])

    def test_weather_advice_is_silent_on_non_actionable_weather(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-29",
                    "status": "planned",
                    "session": "MTB/XC · 75 min · lugnt",
                    "sport": "bike",
                    "stimuli": ["mtb_aerobic"],
                }
            ]
        }
        weather = {
            "status": "ok",
            "daily": {
                "2026-08-29": {
                    "symbol_code": 6,
                    "precip_probability_max_pct": 43,
                }
            },
        }
        settings = {"indoor_alternatives": {"trainer": {"available": True}}}
        self.assertIsNone(
            resolve_weather_advice(plan, [], weather, settings, date(2026, 8, 29))
        )

    def test_weather_advice_is_silent_for_already_indoor_session(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-29",
                    "status": "planned",
                    "session": "Cykel · trainer · 60 min lugnt",
                    "sport": "bike",
                    "stimuli": ["mtb_aerobic"],
                }
            ]
        }
        weather = {
            "status": "ok",
            "daily": {
                "2026-08-29": {
                    "symbol_code": 20,
                    "precip_probability_max_pct": 100,
                }
            },
        }
        settings = {"indoor_alternatives": {"trainer": {"available": True}}}
        self.assertIsNone(
            resolve_weather_advice(plan, [], weather, settings, date(2026, 8, 29))
        )

    def test_weather_advice_is_silent_for_stale_weather(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-29",
                    "status": "planned",
                    "session": "MTB/XC · 75 min · lugnt",
                    "sport": "bike",
                    "stimuli": ["mtb_aerobic"],
                }
            ]
        }
        weather = {
            "status": "stale",
            "daily": {
                "2026-08-29": {
                    "symbol_code": 20,
                    "precip_probability_max_pct": 100,
                }
            },
        }
        settings = {"indoor_alternatives": {"trainer": {"available": True}}}
        self.assertIsNone(
            resolve_weather_advice(plan, [], weather, settings, date(2026, 8, 29))
        )

    def test_training_brain_renders_weather_headsup_only_when_advice_exists(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-29",
                    "label": "Lördag",
                    "status": "planned",
                    "session": "MTB/XC · 75 min · lugnt",
                    "reason": "Lugn cykelspecifik uthållighet.",
                    "sport": "bike",
                    "priority_role": "flex",
                    "stimuli": ["mtb_aerobic", "mtb_technical"],
                }
            ]
        }
        weather = {
            "status": "ok",
            "daily": {
                "2026-08-29": {
                    "symbol_code": 18,
                    "precip_probability_max_pct": 90,
                }
            },
        }
        settings = {
            "indoor_alternatives": {
                "trainer": {"available": True},
                "treadmill": {"available": True},
                "swim": {"available": True},
            }
        }
        section = render_section(
            plan,
            {"activities": []},
            self.strategy,
            date(2026, 8, 29),
            weather=weather,
            settings=settings,
        )
        self.assertIn('data-weather-advice="true"', section)
        self.assertIn("Trainer på gravel", section)

        dry = deepcopy(weather)
        dry["daily"]["2026-08-29"]["symbol_code"] = 6
        dry["daily"]["2026-08-29"]["precip_probability_max_pct"] = 20
        dry_section = render_section(
            plan,
            {"activities": []},
            self.strategy,
            date(2026, 8, 29),
            weather=dry,
            settings=settings,
        )
        self.assertNotIn('data-weather-advice="true"', dry_section)

    def test_strategy_v5_has_explicit_contract_progression_and_markers(self):
        self.assertEqual(self.strategy["schema_version"], 5)
        mesocycle = self.strategy["current_mesocycle"]
        self.assertEqual(
            mesocycle["contract"]["primary"],
            ["run_threshold", "run_hill_quality", "run_easy_distance"],
        )
        self.assertIn("strength_unilateral", mesocycle["contract"]["protected_capacity"])
        self.assertTrue(mesocycle["progression_policy"]["progression_requires_explicit_criteria"])
        threshold = next(item for item in mesocycle["microcycle_template"] if item["slot"] == "run_threshold")
        self.assertEqual(threshold["progression_target_option_id"], "run-threshold-3x10")
        self.assertGreaterEqual(len(threshold["progression_criteria"]), 3)
        marker_ids = {item["id"] for item in self.strategy["performance_marker_policy"]["markers"]}
        self.assertIn("run-threshold-control", marker_ids)
        self.assertIn("strength-repeatability", marker_ids)

    def test_mesocycle_exposes_roles_without_changing_primary_dashboard(self):
        mesocycle = resolve_mesocycle(self.strategy, date(2026, 8, 26))
        self.assertIn("Kontrollerad löptröskel", mesocycle["contract"]["primary"])
        self.assertIn("Unilateral benstyrka", mesocycle["contract"]["protected_capacity"])
        self.assertIn("run-threshold-control", mesocycle["performance_markers"])

    def test_current_mesocycle_reports_microcycle_one(self):
        mesocycle = resolve_mesocycle(self.strategy, date(2026, 8, 26))
        self.assertEqual(mesocycle["state"], "mikrocykel 1 av 4")
        self.assertEqual(mesocycle["evaluation_date"], "2026-09-21")
        self.assertIn("Kontrollerad löptröskel", mesocycle["protected_stimuli"])

    def test_today_with_explicit_alternative_uses_calm_status_and_split_title(self):
        plan = {
            "days": [
                {
                    "date": "2026-09-02",
                    "label": "Onsdag",
                    "status": "conditional",
                    "session": "Simning · aerob/teknik · 3 200 m · ca 60 min · alternativ: Swimrun · Jogersö Extreme · 1 varv",
                    "sport": "swim",
                    "alternative_sports": ["swimrun"],
                    "priority_role": "flex",
                    "stimuli": ["swim_aerobic", "swim_technique"],
                    "reason": "Kontrollerad stödträning.",
                },
                {
                    "date": "2026-09-03",
                    "label": "Torsdag",
                    "status": "preliminary",
                    "session": "MTB/XC · 60 min · teknik + lugn aerob stig",
                    "sport": "bike",
                    "priority_role": "flex",
                    "stimuli": ["mtb_technical", "mtb_aerobic"],
                    "decision_note": "Grundplanen ligger kvar.",
                },
            ]
        }
        section = render_section(plan, {"activities": []}, self.strategy, date(2026, 9, 2))
        self.assertIn(">Alternativ finns</span>", section)
        self.assertIn(">Simning 3 200 m aerob/teknik</div>", section)
        self.assertIn("ca 60 min · alternativ: Swimrun, Jogersö Extreme 1 varv", section)
        self.assertIn("Torsdag · MTB/XC 60 min", section)
        self.assertIn("Grundplan: teknik + lugn aerob stig.", section)
        self.assertNotIn(">FLEX<", section)
        self.assertNotIn("Idag · VILLKORAT", section)


    def test_primary_ui_contains_only_today_and_next_session(self):
        section = render_section(self.plan, {"activities": []}, self.strategy, date(2026, 8, 26))
        self.assertIn('class="brain-kicker">Idag</span>', section)
        self.assertIn('class="brain-next-label">Nästa</div>', section)
        self.assertIn("<summary>Motivering</summary>", section)
        self.assertNotIn("brain-role", section)
        self.assertNotIn("Aktuell mesocykel", section)
        self.assertNotIn("Prioritering just nu", section)
        self.assertNotIn("brain-tags", section)

    def test_mesocycle_context_moves_into_week_focus(self):
        page = '<div class="hero week-focus-card"><h2>Veckofokus</h2><details class="week-focus-details"><summary>Planidé</summary><p>Veckoplan.</p></details></div>'
        mesocycle = resolve_mesocycle(self.strategy, date(2026, 8, 26))
        rendered = decorate_focus_card(page, mesocycle)
        self.assertIn('class="week-focus-mesocycle-meta"', rendered)
        self.assertIn("mikrocykel 1 av 4", rendered)
        self.assertIn("Löpning prioriteras denna vecka", rendered)
        self.assertIn("Löptröskel + backkvalitet", rendered)
        self.assertNotIn("utvärdering 21/9", rendered)
        self.assertIn("Mesocykelhypotes:", rendered)

    def test_ui_insertion_is_idempotent(self):
        page = "<html><style></style><body><section class=\"dashboard\"></section></body></html>"
        once = apply_ui(page, f"{SECTION_START}<section>brain</section><!-- training-brain-v1:end -->")
        twice = apply_ui(once, f"{SECTION_START}<section>brain2</section><!-- training-brain-v1:end -->")
        self.assertEqual(twice.count(SECTION_START), 1)
        self.assertEqual(twice.count("/* training-brain-v3 */"), 1)
        self.assertIn("brain2", twice)
        self.assertNotIn(">brain<", twice)


if __name__ == "__main__":
    unittest.main()
