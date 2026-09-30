#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.domain.workouts import PlannedWorkout
from training_core.presentation.overview import build_training_overview
from training_core.presentation.overview_renderer import render_overview_document
from training_core.presentation.today import CompletedActivity


class TrainingOverviewTests(unittest.TestCase):
    def setUp(self):
        self.start = date(2026, 9, 14)
        self.end = date(2026, 11, 8)
        self.current = date(2026, 9, 30)
        self.plan = (
            PlannedWorkout(
                local_date=date(2026, 9, 30),
                session="Löpning · 4×8 min tröskel",
                sport="run",
                status="planned",
                workout_key="run-threshold",
                development_focus="Kontrollerad löptröskel",
                payload={
                    "stimuli": ["run_threshold"],
                    "recipe_key": "run_threshold",
                    "priority_role": "anchor",
                    "block_intent": "establish",
                    "development_character": "controlled_threshold",
                    "development_step": {
                        "relation": "hold",
                        "reason": "Etableringsvecka på absorberad nivå.",
                    },
                },
            ),
            PlannedWorkout(
                local_date=date(2026, 9, 30),
                session="Simning · aerob/teknik",
                sport="swim",
                status="planned",
                workout_key="swim-aerobic",
                development_focus="Sim aerob kapacitet",
                payload={
                    "stimuli": ["swim_aerobic", "swim_technique"],
                    "recipe_key": "swim_aerobic_technique",
                    "priority_role": "anchor",
                    "block_intent": "establish",
                    "development_character": "technique_aerobic",
                    "development_step": {
                        "relation": "establish",
                        "reason": "Etablera simstimulus.",
                    },
                },
            ),
            PlannedWorkout(
                local_date=date(2026, 10, 3),
                session="Enduro · fast tillfälle",
                sport="enduro",
                status="planned",
                planning_status="fixed",
                manual_lock=True,
                workout_key="enduro-fixed",
                payload={"stimuli": ["enduro_technical"]},
            ),
            PlannedWorkout(
                local_date=date(2026, 10, 6),
                session="Styrka/core",
                sport="strength",
                status="planned",
                workout_key="strength",
                payload={
                    "stimuli": ["strength_core"],
                    "recipe_key": "strength_core",
                    "priority_role": "protected_support",
                    "block_intent": "develop",
                },
            ),
            PlannedWorkout(
                local_date=date(2026, 10, 7),
                session="Löpning · tröskelprogression",
                sport="run",
                status="planned",
                workout_key="run-threshold-progress",
                development_focus="Kontrollerad löptröskel",
                payload={
                    "stimuli": ["run_threshold"],
                    "recipe_key": "run_threshold",
                    "priority_role": "anchor",
                    "block_intent": "develop",
                    "development_character": "controlled_threshold",
                    "development_step": {
                        "relation": "progress",
                        "reason": "Dose-response stödjer ett förgodkänt steg.",
                    },
                },
            ),
            PlannedWorkout(
                local_date=date(2026, 10, 9),
                session="Simning · aerob/teknik",
                sport="swim",
                status="planned",
                workout_key="swim-develop",
                development_focus="Sim aerob kapacitet",
                payload={
                    "stimuli": ["swim_aerobic", "swim_technique"],
                    "recipe_key": "swim_aerobic_technique",
                    "priority_role": "anchor",
                    "block_intent": "develop",
                    "development_character": "technique_aerobic",
                    "development_step": {
                        "relation": "hold",
                        "reason": "Teknisk kvalitet konsolideras medan löptröskeln progressas.",
                    },
                },
            ),
        )
        self.activities = (
            CompletedActivity(
                provider_activity_id="1",
                local_date=date(2026, 9, 22),
                label="Löpning",
                sport_family="run",
                elapsed_time_s=3600,
                distance_m=12000,
            ),
            CompletedActivity(
                provider_activity_id="2",
                local_date=date(2026, 9, 30),
                label="Löpning",
                sport_family="run",
                elapsed_time_s=3300,
                distance_m=11000,
            ),
        )
        self.roadmap = {
            "interpretation_boundary": "Framtida utveckling bedöms vid checkpoints.",
            "capabilities": [
                {"key": "run_threshold", "label": "Kontrollerad löptröskel"},
                {"key": "swim_aerobic", "label": "Sim aerob kapacitet"},
            ],
            "canonical_goals": [
                {
                    "label": "ÖTILLÖ Åland World Series · Topp-10",
                    "target": "Topp-10",
                    "target_date": "2027-08-14",
                }
            ],
            "active_block": {
                "title": "Konservativ konsolidering",
                "start_date": "2026-09-28",
                "end_date": "2026-10-25",
                "evaluation_date": "2026-10-26",
                "primary_capabilities": ["run_threshold", "swim_aerobic"],
                "secondary_capabilities": [],
                "protected_capabilities": [],
                "progression_axes": [
                    {
                        "capability": "run_threshold",
                        "axis": "work_duration",
                        "objective": "Öka arbetstid stegvis när responsen stödjer det.",
                    },
                    {
                        "capability": "swim_aerobic",
                        "axis": "consistency",
                        "objective": "Bygg stabil aerob simkapacitet.",
                    },
                ],
                "microcycle_intents": [
                    {
                        "index": 1,
                        "intent": "establish",
                        "definition": "Etablera nyckelstimuli.",
                        "start_date": "2026-09-28",
                        "end_date": "2026-10-04",
                    },
                    {
                        "index": 2,
                        "intent": "develop",
                        "definition": "Utveckla primär kapacitet.",
                        "start_date": "2026-10-05",
                        "end_date": "2026-10-11",
                    },
                    {
                        "index": 3,
                        "intent": "develop",
                        "definition": "Utveckla primär kapacitet.",
                        "start_date": "2026-10-12",
                        "end_date": "2026-10-18",
                    },
                    {
                        "index": 4,
                        "intent": "consolidate",
                        "definition": "Stabilisera blockets vinster.",
                        "start_date": "2026-10-19",
                        "end_date": "2026-10-25",
                    },
                ],
                "development_blueprint": [
                    {
                        "microcycle_index": 1,
                        "week_start": "2026-09-28",
                        "week_end": "2026-10-04",
                        "block_intent": "establish",
                        "planned_variants": [
                            {
                                "role": "primary",
                                "capability": "run_threshold",
                                "recipe_key": "run_threshold",
                                "development_character": "threshold_long_reps",
                                "label": "Löptröskel · längre repetitioner",
                                "progression_intent": "establish",
                            }
                        ],
                        "supporting_candidates": [],
                        "protected_variants": [],
                        "principle": "test",
                    },
                    {
                        "microcycle_index": 2,
                        "week_start": "2026-10-05",
                        "week_end": "2026-10-11",
                        "block_intent": "develop",
                        "planned_variants": [
                            {
                                "role": "primary",
                                "capability": "run_threshold",
                                "recipe_key": "run_threshold_short_reps",
                                "development_character": "threshold_short_reps",
                                "label": "Löptröskel · kortare repetitioner",
                                "progression_intent": "vary_structure",
                            }
                        ],
                        "supporting_candidates": [],
                        "protected_variants": [],
                        "principle": "test",
                    },
                    {
                        "microcycle_index": 3,
                        "week_start": "2026-10-12",
                        "week_end": "2026-10-18",
                        "block_intent": "develop",
                        "planned_variants": [
                            {
                                "role": "primary",
                                "capability": "run_threshold",
                                "recipe_key": "run_threshold",
                                "development_character": "threshold_long_reps",
                                "label": "Löptröskel · längre repetitioner",
                                "progression_intent": "progress_if_ready",
                                "baseline_session": "Löpning · kontrollerad tröskel · 4 × 8 min / 90 s jogg",
                                "conditional_target_session": "Löpning · kontrollerad tröskel · 4 × 9 min / 90 s jogg",
                                "target_condition": "progression_ready_and_absorbable_context",
                            },
                            {
                                "role": "primary",
                                "capability": "swim_aerobic",
                                "recipe_key": "swim_aerobic_skills",
                                "development_character": "technique_catch_aerobic",
                                "label": "Sim · grepp/teknik + aerob",
                                "progression_intent": "progress_if_ready",
                            },
                        ],
                        "supporting_candidates": [
                            {
                                "role": "supporting_candidate",
                                "capability": "run_easy_distance",
                                "recipe_key": "run_easy_trail",
                                "development_character": "easy_trail",
                                "label": "Lugn löpdistans · stig/grus",
                                "progression_intent": "support_if_absorbable",
                            }
                        ],
                        "protected_variants": [
                            {
                                "role": "protected",
                                "capability": "strength_core",
                                "recipe_key": "strength_core",
                                "development_character": "unilateral_core",
                                "label": "Styrka/core · unilateral + bål",
                                "progression_intent": "protect",
                            }
                        ],
                        "principle": "test",
                    },
                    {
                        "microcycle_index": 4,
                        "week_start": "2026-10-19",
                        "week_end": "2026-10-25",
                        "block_intent": "consolidate",
                        "planned_variants": [
                            {
                                "role": "primary",
                                "capability": "run_threshold",
                                "recipe_key": "run_threshold",
                                "development_character": "threshold_long_reps",
                                "label": "Löptröskel · längre repetitioner",
                                "progression_intent": "consolidate",
                            }
                        ],
                        "supporting_candidates": [],
                        "protected_variants": [],
                        "principle": "test",
                    },
                ],
                "forward_horizon": [
                    {
                        "week_start": "2026-10-12",
                        "week_end": "2026-10-18",
                        "planning_level": "preliminary",
                        "planning_label": "Preliminär",
                        "day_precision": "provisional",
                        "block_intent": "develop",
                        "title": "Preliminär mikrocykel 3 av 4",
                        "slots": [
                            {
                                "day_index": 2,
                                "role": "primary",
                                "sport": "run",
                                "recipe_key": "run_threshold",
                                "label": "Löptröskel · längre repetitioner",
                                "progression_intent": "progress_if_ready",
                                "baseline_session": "Löpning · kontrollerad tröskel · 4 × 8 min / 90 s jogg",
                                "conditional_target_session": "Löpning · kontrollerad tröskel · 4 × 9 min / 90 s jogg",
                            },
                            {
                                "day_index": 4,
                                "role": "primary",
                                "sport": "swim",
                                "recipe_key": "swim_aerobic_skills",
                                "label": "Sim · grepp/teknik + aerob",
                                "progression_intent": "progress_if_ready",
                                "baseline_session": "Simning · 3 200 m · grepp/teknik + aerob",
                                "conditional_target_session": "Simning · 3 600 m · grepp/teknik + aerob",
                            },
                        ],
                        "capability_directions": [],
                        "support_candidates": [],
                        "protected_capabilities": [],
                        "decision_gate": "Exakta dagar och doser är preliminära.",
                        "source": "active_mesocycle_projection",
                    },
                    {
                        "week_start": "2026-10-19",
                        "week_end": "2026-10-25",
                        "planning_level": "preliminary",
                        "planning_label": "Preliminär",
                        "day_precision": "provisional",
                        "block_intent": "consolidate",
                        "title": "Preliminär mikrocykel 4 av 4",
                        "slots": [
                            {
                                "day_index": 3,
                                "role": "primary",
                                "sport": "run",
                                "recipe_key": "run_threshold",
                                "label": "Löptröskel · längre repetitioner",
                                "progression_intent": "consolidate",
                                "baseline_session": "Löpning · kontrollerad tröskel · 4 × 8 min / 90 s jogg",
                                "conditional_target_session": "",
                            }
                        ],
                        "capability_directions": [],
                        "support_candidates": [],
                        "protected_capabilities": [],
                        "decision_gate": "Konsolidera före blockreview.",
                        "source": "active_mesocycle_projection",
                    },
                    {
                        "week_start": "2026-10-26",
                        "week_end": "2026-11-01",
                        "planning_level": "block_sketch",
                        "planning_label": "Blockskiss",
                        "day_precision": "none",
                        "block_intent": "review",
                        "title": "Blockreview · besluta nästa riktning",
                        "slots": [],
                        "capability_directions": [
                            {
                                "capability": "run_threshold",
                                "label": "Kontrollerad löptröskel",
                                "direction": "Fortsätt eller konsolidera tills blockreview visar stöd för progression.",
                                "candidate_recipe_characters": [
                                    "Löptröskel · längre repetitioner",
                                    "Löptröskel · kortare repetitioner"
                                ],
                                "progression_ready_now": False,
                                "evidence_state_now": "absorbed",
                            }
                        ],
                        "support_candidates": [
                            {
                                "capability": "run_easy_distance",
                                "label": "Lugn löpdistans / tålighet",
                                "direction": "",
                                "candidate_recipe_characters": ["Lugn löpdistans · stig/grus"],
                                "progression_ready_now": False,
                                "evidence_state_now": "",
                            }
                        ],
                        "protected_capabilities": [
                            {"capability": "strength_core", "label": "Core"}
                        ],
                        "decision_gate": "Ny mesocykel beslutas vid checkpoint 2026-10-26.",
                        "source": "post_mesocycle_conditional_sketch",
                    },
                    {
                        "week_start": "2026-11-02",
                        "week_end": "2026-11-08",
                        "planning_level": "block_sketch",
                        "planning_label": "Blockskiss",
                        "day_precision": "none",
                        "block_intent": "conditional_build",
                        "title": "Nästa block · villkorad riktning",
                        "slots": [],
                        "capability_directions": [
                            {
                                "capability": "swim_aerobic",
                                "label": "Sim aerob kapacitet",
                                "direction": "Fortsätt eller konsolidera tills blockreview visar stöd för progression.",
                                "candidate_recipe_characters": ["Sim · aerob uthållighet"],
                                "progression_ready_now": False,
                                "evidence_state_now": "demonstrated",
                            }
                        ],
                        "support_candidates": [],
                        "protected_capabilities": [
                            {"capability": "strength_core", "label": "Core"}
                        ],
                        "decision_gate": "Ingen dag eller dos låses före review.",
                        "source": "post_mesocycle_conditional_sketch",
                    },
                ],
            },
        }

    def build(self):
        return build_training_overview(
            start=self.start,
            end=self.end,
            current_date=self.current,
            plan=self.plan,
            activities=self.activities,
            roadmap=self.roadmap,
        )

    def test_eight_complete_weeks_and_multipass_are_preserved(self):
        model = self.build()
        self.assertEqual(len(model.weeks), 8)
        self.assertEqual(model.current_week_start, date(2026, 9, 28))

        current_week = next(week for week in model.weeks if week.start == date(2026, 9, 28))
        current_day = next(day for day in current_week.days if day.local_date == self.current)
        self.assertEqual(current_day.planned_count, 2)
        self.assertEqual(current_day.actual_count, 1)
        self.assertEqual(current_day.state, "completed")
        self.assertEqual(current_week.fixed_count, 1)

    def test_week_facts_do_not_invent_planned_load(self):
        model = self.build()
        past_week = next(week for week in model.weeks if week.start == date(2026, 9, 21))
        self.assertEqual(past_week.completed_count, 1)
        self.assertEqual(past_week.actual_duration_s, 3600)
        self.assertEqual(past_week.actual_distance_m, 12000)
        self.assertFalse(hasattr(past_week, "planned_duration_s"))

    def test_goal_and_block_context_is_typed(self):
        model = self.build()
        self.assertIsNotNone(model.context)
        self.assertEqual(model.context.active_block.title, "Konservativ konsolidering")
        self.assertEqual(
            model.context.active_block.primary_capabilities,
            ("Kontrollerad löptröskel", "Sim aerob kapacitet"),
        )
        self.assertEqual(model.context.goals[0].target_date, "2027-08-14")
        self.assertEqual(
            [item.intent for item in model.context.active_block.microcycle_intents],
            ["establish", "develop", "develop", "consolidate"],
        )
        self.assertEqual(
            model.context.active_block.progression_axes[0].axis,
            "work_duration",
        )

    def test_renderer_applies_compact_scan_first_ui_contract(self):
        model = self.build()
        document = render_overview_document(
            model,
            current_date=self.current,
            sport_icons=None,
        )
        self.assertIn('class="overview-calendar"', document)
        self.assertIn('class="overview-planbar"', document)
        self.assertIn("2 veckor bakåt · aktuell vecka · 5 veckor framåt", document)

        # One explicit planning-status chip per visible semantic level.
        self.assertIn(">AKTUELL</span>", document)
        self.assertIn(">PLANERAD</span>", document)
        self.assertIn(">PRELIMINÄR</span>", document)
        self.assertIn(">BLOCKSKISS</span>", document)

        # Calendar cards use compact display titles and one small role/progression chip.
        self.assertIn("Tröskel · 4×8", document)
        self.assertIn("↑ Progression", document)
        self.assertIn("~ Variation", document)
        self.assertIn("= Konsolidera", document)
        self.assertIn("◇ Skyddad", document)

        # Explanatory payload is retained for on-demand detail, not rendered as open prose.
        self.assertIn('id="overview-detail"', document)
        self.assertIn('data-baseline="Löpning · kontrollerad tröskel · 4 × 8 min / 90 s jogg"', document)
        self.assertIn('data-target="Löpning · kontrollerad tröskel · 4 × 9 min / 90 s jogg"', document)
        self.assertNotIn("<small><b>Bas:</b>", document)
        self.assertNotIn("Villkorat mål:", document)
        self.assertNotIn("Preliminär dagstruktur · exakta dagar/doser ej låsta", document)
        self.assertNotIn("planerade vilodagar", document)

        # Block sketches are roadmap/chip based rather than paragraph-heavy.
        self.assertIn('class="overview-sketch-groups"', document)
        self.assertIn('class="overview-sketch-chip sketch-primary"', document)
        self.assertIn('class="overview-sketch-chip sketch-support"', document)
        self.assertIn("Blockreview", document)
        self.assertIn("Nästa block", document)

        # Review remains available but secondary/collapsed.
        self.assertIn("Granska plan", document)
        self.assertIn("Planeringshorisont", document)
        self.assertIn("5 av 5 kommande veckor har planeringsinnehåll", document)


if __name__ == "__main__":
    unittest.main()
