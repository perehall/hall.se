#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.presentation import (  # noqa: E402
    build_historical_presentation_snapshot,
    build_presentation_snapshot,
)
from training_core.presentation.renderer import (  # noqa: E402
    render_document,
    render_historical_snapshot,
    render_snapshot,
)
from training_core.presentation.sport_identity import (  # noqa: E402
    activity_icon_key,
    planned_icon_keys,
)
from training_core.presentation.today import CompletedActivity, PlannedDay  # noqa: E402
from training_core.repositories.archive import ManifestWeekArchiveRepository  # noqa: E402
from training_core.repositories.icons import FileSportIconRepository  # noqa: E402


class CurrentRepository:
    def planned_days(self, start, end):
        return [
            PlannedDay(
                date(2026, 9, 27),
                "Simning + styrka/core",
                "swim",
                "fixed",
                payload={
                    "stimuli": [
                        "swim_aerobic",
                        "swim_technique",
                        "strength_unilateral",
                        "strength_core",
                    ]
                },
            )
        ]

    def completed_activities(self, start, end):
        return []


class CompletedRepository:
    def planned_days(self, start, end):
        return [
            PlannedDay(
                date(2026, 9, 27),
                "Enduro + styrka",
                "enduro",
                "fixed",
                payload={"stimuli": ["enduro_technical", "strength_core"]},
            )
        ]

    def completed_activities(self, start, end):
        return [
            CompletedActivity("1", date(2026, 9, 27), "Enduro", "enduro", 3600),
            CompletedActivity("2", date(2026, 9, 27), "Styrka", "strength", 1200),
        ]


class SportIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.icons = FileSportIconRepository(ROOT / "data" / "sport_icons.json")

    def test_real_icon_registry_contains_every_required_training_icon(self):
        registry = self.icons.current()
        for key in ("run", "swim", "bike", "enduro", "strength"):
            icon = registry.require(key)
            self.assertTrue(icon.solid)
            self.assertTrue(icon.view_box)
            self.assertTrue(icon.path)
        self.assertFalse(registry.require("activity").solid)

    def test_structured_plan_stimuli_produce_combo_icons_without_title_parsing(self):
        keys = planned_icon_keys(
            sport="swim",
            payload={
                "stimuli": [
                    "swim_aerobic",
                    "strength_unilateral",
                    "strength_core",
                ]
            },
        )
        self.assertEqual(keys, ("swim", "strength"))

    def test_provider_sports_normalize_to_stable_icon_identity(self):
        self.assertEqual(activity_icon_key("run"), "run")
        self.assertEqual(activity_icon_key("MountainBikeRide"), "bike")
        self.assertEqual(activity_icon_key("WeightTraining"), "strength")
        self.assertEqual(activity_icon_key("Enduro"), "enduro")

    def test_planned_combo_renders_both_svg_icons_in_today_and_week(self):
        snapshot = build_presentation_snapshot(
            CurrentRepository(),
            today=date(2026, 9, 27),
            icon_repository=self.icons,
        )
        self.assertEqual(snapshot.today.icon_keys, ("swim", "strength"))
        sunday = next(
            day for day in snapshot.week.days
            if day.local_date == date(2026, 9, 27)
        )
        self.assertEqual(sunday.icon_keys, ("swim", "strength"))

        rendered = render_snapshot(snapshot)
        self.assertIn('data-sport-icons="swim,strength"', rendered)
        self.assertIn('data-sport-icon="swim"', rendered)
        self.assertIn('data-sport-icon="strength"', rendered)

    def test_completed_multi_activity_truth_owns_visible_icons(self):
        snapshot = build_presentation_snapshot(
            CompletedRepository(),
            today=date(2026, 9, 27),
            icon_repository=self.icons,
        )
        self.assertEqual(snapshot.today.icon_keys, ("enduro", "strength"))
        sunday = next(
            day for day in snapshot.week.days
            if day.local_date == date(2026, 9, 27)
        )
        self.assertEqual(sunday.icon_keys, ("enduro", "strength"))
        rendered = render_snapshot(snapshot)
        self.assertIn('data-sport-icons="enduro,strength"', rendered)

    def test_document_constrains_sport_icons_to_text_scale(self):
        snapshot = build_presentation_snapshot(
            CurrentRepository(),
            today=date(2026, 9, 27),
            icon_repository=self.icons,
        )
        rendered = render_document(snapshot)
        self.assertIn(".v2-sport-icon{display:inline-block;width:1.25em;height:1.25em", rendered)
        self.assertIn(".v2-sport-icons{display:inline-flex;align-items:center", rendered)

    def test_historical_page_renders_activity_and_original_plan_icons(self):
        archive = ManifestWeekArchiveRepository(ROOT / "data" / "weeks" / "index.json")
        snapshot = build_historical_presentation_snapshot(
            archive,
            week_key="2026-W38",
            icon_repository=self.icons,
        )
        rendered = render_historical_snapshot(snapshot)
        self.assertIn('data-sport-icon="run"', rendered)
        self.assertIn('data-sport-icon="swim"', rendered)
        self.assertIn('data-sport-icon="bike"', rendered)
        self.assertIn('data-sport-icon="enduro"', rendered)
        self.assertIn('data-sport-icon="strength"', rendered)


if __name__ == "__main__":
    unittest.main()
