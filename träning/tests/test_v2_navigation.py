#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.presentation.navigation import (
    PublishedWeek,
    build_week_navigation,
)
from training_core.repositories.archive import ManifestWeekArchiveRepository


class NavigationReadModelTests(unittest.TestCase):
    def test_current_week_links_history_and_next_planned_week(self):
        model = build_week_navigation(
            viewed_start=date(2026, 9, 21),
            current_start=date(2026, 9, 21),
            planned_days=[
                date(2026, 9, 21),
                date(2026, 9, 28),
            ],
            published_weeks=[
                PublishedWeek(
                    "2026-W38",
                    date(2026, 9, 14),
                    date(2026, 9, 20),
                    "/träning/vecka/2026-W38/",
                )
            ],
        )
        self.assertEqual(model.label, "Vecka 39")
        self.assertEqual(model.period, "21–27 sep")
        self.assertEqual(model.state, "aktuell")
        self.assertEqual(model.previous.key, "2026-W38")
        self.assertEqual(model.previous.url, "/träning/vecka/2026-W38/")
        self.assertEqual(model.next.key, "2026-W40")
        self.assertEqual(model.next.url, "/träning/vecka/2026-W40/")

    def test_historical_week_next_link_targets_current_root(self):
        model = build_week_navigation(
            viewed_start=date(2026, 9, 14),
            current_start=date(2026, 9, 21),
            planned_days=[date(2026, 9, 21)],
            published_weeks=[
                PublishedWeek(
                    "2026-W37",
                    date(2026, 9, 7),
                    date(2026, 9, 13),
                    "/träning/vecka/2026-W37/",
                ),
                PublishedWeek(
                    "2026-W38",
                    date(2026, 9, 14),
                    date(2026, 9, 20),
                    "/träning/vecka/2026-W38/",
                ),
            ],
        )
        self.assertEqual(model.state, "historik")
        self.assertEqual(model.previous.key, "2026-W37")
        self.assertEqual(model.next.key, "2026-W39")
        self.assertEqual(model.next.url, "/träning/")

    def test_manifest_adapter_uses_explicit_records_only(self):
        payload = {
            "schema_version": 2,
            "current_week_key": "2026-W39",
            "weeks": [
                {
                    "key": "2026-W38",
                    "week_start": "2026-09-14",
                    "week_end": "2026-09-20",
                    "url": "/träning/vecka/2026-W38/",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            rows = ManifestWeekArchiveRepository(path).published_weeks()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].key, "2026-W38")
        self.assertEqual(rows[0].url, "/träning/vecka/2026-W38/")


if __name__ == "__main__":
    unittest.main()
