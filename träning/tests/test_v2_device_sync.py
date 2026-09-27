#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.presentation import build_presentation_snapshot  # noqa: E402
from training_core.presentation.device_sync import build_device_sync_read_model  # noqa: E402
from training_core.presentation.renderer import render_snapshot  # noqa: E402
from training_core.presentation.today import CompletedActivity, PlannedDay  # noqa: E402


def payload(status="pending", *, delivery="unverified"):
    return {
        "device_workout": {
            "source_hash": "abc123",
            "external_id": "hall-device:test",
        },
        "device_sync": {
            "status": status,
            "source_hash": "abc123",
            "transport": "intervals_icu",
            "device_delivery": delivery,
        },
    }


class PlannedRepository:
    def planned_days(self, start, end):
        return [
            PlannedDay(
                date(2026, 9, 27),
                "Simning · 3 200 m",
                "swim",
                "fixed",
                payload=payload("synced"),
            )
        ]

    def completed_activities(self, start, end):
        return []


class CompletedRepository(PlannedRepository):
    def completed_activities(self, start, end):
        return [
            CompletedActivity(
                "1",
                date(2026, 9, 27),
                "Simning",
                "swim",
                elapsed_time_s=3600,
            )
        ]


class DeviceSyncPresentationTests(unittest.TestCase):
    def test_pending_synced_error_are_public_states(self):
        self.assertEqual(
            build_device_sync_read_model(payload("pending"), completed=False).label,
            "Klocksync väntar",
        )
        self.assertEqual(
            build_device_sync_read_model(payload("synced"), completed=False).label,
            "Klocksync skickad",
        )
        self.assertEqual(
            build_device_sync_read_model(payload("error"), completed=False).label,
            "Klocksync fel",
        )

    def test_deferred_is_not_public_until_within_sync_horizon(self):
        self.assertIsNone(
            build_device_sync_read_model(payload("deferred"), completed=False)
        )

    def test_completed_day_does_not_show_stale_sync_status(self):
        snapshot = build_presentation_snapshot(
            CompletedRepository(),
            today=date(2026, 9, 27),
        )
        self.assertIsNone(snapshot.today.device_sync)
        self.assertIsNone(snapshot.week.days[0].device_sync)
        self.assertNotIn("Klocksync", render_snapshot(snapshot))

    def test_synced_never_claims_verified_physical_watch_delivery(self):
        sync = build_device_sync_read_model(payload("synced"), completed=False)
        self.assertIn("verifierat i Intervals.icu", sync.help_text)
        self.assertIn("kan inte verifieras", sync.help_text)
        with self.assertRaisesRegex(RuntimeError, "physical watch"):
            build_device_sync_read_model(
                payload("synced", delivery="verified"),
                completed=False,
            )

    def test_source_hash_mismatch_fails_closed(self):
        broken = payload("pending")
        broken["device_sync"]["source_hash"] = "different"
        with self.assertRaisesRegex(RuntimeError, "source hash"):
            build_device_sync_read_model(broken, completed=False)

    def test_planned_syncable_workout_renders_status_chip(self):
        snapshot = build_presentation_snapshot(
            PlannedRepository(),
            today=date(2026, 9, 27),
        )
        self.assertEqual(snapshot.today.device_sync.status, "synced")
        self.assertEqual(snapshot.week.days[0].device_sync.label, "Klocksync skickad")
        rendered = render_snapshot(snapshot)
        self.assertIn('data-device-sync="synced"', rendered)
        self.assertIn("Klocksync skickad", rendered)


if __name__ == "__main__":
    unittest.main()
