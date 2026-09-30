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
                payload={"stimuli": ["run_threshold"]},
            ),
            PlannedWorkout(
                local_date=date(2026, 9, 30),
                session="Simning · aerob/teknik",
                sport="swim",
                status="planned",
                workout_key="swim-aerobic",
                development_focus="Sim aerob kapacitet",
                payload={"stimuli": ["swim_aerobic", "swim_technique"]},
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
                payload={"stimuli": ["strength_core"]},
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
        self.assertIn("saknar planerade träningspass", document)
        self.assertIn("ÖTILLÖ Åland World Series · Topp-10", document)
        self.assertIn("Granska plan", document)


if __name__ == "__main__":
    unittest.main()
