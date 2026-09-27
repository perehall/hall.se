#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.presentation import build_presentation_snapshot
from training_core.presentation.renderer import render_today
from training_core.presentation.today import CompletedActivity, PlannedDay


class FakeRepository:
    def planned_days(self, start, end):
        return [
            PlannedDay(date(2026,9,26), "Simning · 4 000 m", "swim", "completed"),
            PlannedDay(
                date(2026,9,27), "Löpning · lugn distans · 60 min", "run", "conditional",
                reason="Bygg löptålighet med god kontroll.",
                development_focus="Lugn aerob löpning.",
                payload={"workout_design":{"selected_candidate_id":"easy","candidates":[
                    {"id":"easy","prescription":{"blocks":[
                        {"name":"Huvuddel","intensity":"Z2","instruction":"60 min lugnt"}
                    ]}}
                ]}},
            ),
        ]

    def completed_activities(self, start, end):
        return [
            CompletedActivity("1", date(2026,9,26), "Enduro", "enduro", 6062, 26611.2),
            CompletedActivity("2", date(2026,9,26), "Simning", "swim", 3822, 3000),
        ]


class PresentationSliceTests(unittest.TestCase):
    def test_repository_to_read_model_to_html_is_pure_and_semantic(self):
        snapshot = build_presentation_snapshot(FakeRepository(), today=date(2026,9,26))
        rendered = render_today(snapshot)
        self.assertIn('data-state="completed"', rendered)
        self.assertIn("<h1>Enduro + Simning</h1>", rendered)
        self.assertIn("Enduro · 26,61 km · 1:41:02", rendered)
        self.assertIn("Simning · 3,00 km · 1:03:42", rendered)
        self.assertIn("Löpning · lugn distans · 60 min", rendered)
        self.assertNotIn("Simning · 4 000 m</h1>", rendered)

    def test_planned_today_renders_prescription_and_rationale_without_finalizer(self):
        snapshot = build_presentation_snapshot(FakeRepository(), today=date(2026,9,27))
        rendered = render_today(snapshot)
        self.assertIn("Passupplägg", rendered)
        self.assertIn("Huvuddel · Z2 · 60 min lugnt", rendered)
        self.assertIn("Plan och motivering", rendered)
        self.assertIn("Bygg löptålighet med god kontroll.", rendered)
        self.assertIn("Lugn aerob löpning.", rendered)


if __name__ == "__main__":
    unittest.main()
