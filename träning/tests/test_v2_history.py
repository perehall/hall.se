#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.presentation import (  # noqa: E402
    build_historical_presentation_snapshot,
)
from training_core.presentation.history import (  # noqa: E402
    build_historical_week_read_model,
)
from training_core.presentation.renderer import (  # noqa: E402
    render_historical_snapshot,
)
from training_core.repositories.archive import (  # noqa: E402
    ManifestWeekArchiveRepository,
)


class HistoricalPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = ManifestWeekArchiveRepository(
            ROOT / "data" / "weeks" / "index.json"
        )

    def test_real_week_38_archive_is_normalized_into_typed_audit_domain(self):
        archived = self.repository.archived_week("2026-W38")

        self.assertEqual(archived.key, "2026-W38")
        self.assertEqual(len(archived.plan_days), 7)
        self.assertEqual(archived.review.activity_count, 8)
        self.assertEqual(archived.review.active_days, 7)
        self.assertIn("löptröskel + backkvalitet", archived.title)

        labels = {activity.label for activity in archived.activities}
        self.assertIn("Enduro", labels)
        self.assertIn("Styrka", labels)
        self.assertIn("Simning", labels)
        self.assertIn("MTB/XC", labels)
        self.assertIn("Löpning · backintervaller", labels)

    def test_history_read_model_preserves_plan_actual_and_uncertainty_layers(self):
        model = build_historical_week_read_model(
            self.repository.archived_week("2026-W38")
        )

        friday = next(
            day for day in model.days if day.local_date.isoformat() == "2026-09-18"
        )
        self.assertIn("backkvalitet", friday.planned_session)
        self.assertEqual(friday.state, "completed")
        self.assertTrue(friday.prescription)
        self.assertEqual(friday.activities[0].label, "Löpning · backintervaller")
        self.assertIn("superpigg", friday.activities[0].user_report.lower())

        self.assertIsNotNone(model.review)
        self.assertTrue(model.review.worked)
        self.assertTrue(model.review.not_as_planned)
        self.assertTrue(model.review.load_continuity)
        self.assertTrue(model.review.key_lesson)
        self.assertTrue(model.review.uncertainties)

    def test_historical_renderer_is_read_only_and_links_back_to_current_week(self):
        snapshot = build_historical_presentation_snapshot(
            self.repository,
            week_key="2026-W38",
        )
        rendered = render_historical_snapshot(snapshot)

        self.assertIn("<strong>Vecka 38</strong>", rendered)
        self.assertIn("14–20 sep · historik", rendered)
        self.assertIn('href="/träning/vecka/2026-W37/"', rendered)
        self.assertIn('href="/träning/"', rendered)
        self.assertIn("Veckosummering", rendered)
        self.assertIn("Det som fungerade", rendered)
        self.assertIn("Inte enligt plan", rendered)
        self.assertIn("Belastning &amp; kontinuitet", rendered)
        self.assertIn("Osäkerheter i underlaget", rendered)
        self.assertIn("Ursprungsplan och motivering", rendered)
        self.assertNotIn("data-v2-feedback-editor", rendered)
        self.assertNotIn("training-v2-feedback", rendered)


if __name__ == "__main__":
    unittest.main()
