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

    def test_renderer_shows_plan_actual_and_missing_future_horizon(self):
        model = self.build()
        document = render_overview_document(
            model,
            current_date=self.current,
            sport_icons=None,
        )
        self.assertIn('class="overview-calendar"', document)
        self.assertIn("Löpning · 4×8 min tröskel", document)
        self.assertIn("Simning · aerob/teknik", document)
        self.assertIn("Planeringshorisont", document)
        self.assertIn("Blockrytm", document)
        self.assertIn("Progressionslogik", document)
        self.assertIn("1 primär progression", document)
        self.assertIn("Etablera", document)
        self.assertIn("Utveckla", document)
        self.assertIn("Konsolidera", document)
        self.assertIn("Preliminär grundplan", document)
        self.assertIn("Löptröskel · längre repetitioner", document)
        self.assertIn("Sim · grepp/teknik + aerob", document)
        self.assertIn("Planerad progression om responsen stödjer", document)
        self.assertIn("Villkorat mål:", document)
        self.assertIn("4 × 9 min", document)
        self.assertIn("Grundplan finns · detaljdagar ej materialiserade", document)
        self.assertNotIn("7 planerade vilodagar", document)
        self.assertIn("ÖTILLÖ Åland World Series · Topp-10", document)
        self.assertIn("Granska plan", document)


if __name__ == "__main__":
    unittest.main()
