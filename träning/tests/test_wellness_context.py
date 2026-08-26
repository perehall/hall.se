#!/usr/bin/env python3
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from wellness_context import (  # noqa: E402
    WELLNESS_FIELDS,
    build_context,
    signature_payload,
    validate_context,
    write_private_context,
)


class WellnessContextTests(unittest.TestCase):
    def test_context_keeps_only_whitelisted_numeric_wellness_fields(self):
        rows = [
            {
                "id": "2026-08-24",
                "restingHR": 48,
                "hrv": 52.5,
                "sleepSecs": 25200,
                "sleepScore": 81,
                "sleepQuality": 3,
                "steps": 8123,
                "stress": 17,
                "customFields": {"private": "must not pass"},
            },
            {"id": "not-a-date", "hrv": 999},
        ]
        context = build_context(rows, oldest="2026-08-01", newest="2026-08-24")
        validate_context(context)
        self.assertEqual(len(context["daily"]), 1)
        daily = context["daily"][0]
        self.assertEqual(daily["date"], "2026-08-24")
        self.assertEqual(set(daily) - {"date"}, set(WELLNESS_FIELDS))
        self.assertNotIn("stress", json.dumps(context))
        self.assertNotIn("customFields", json.dumps(context))

    def test_signature_ignores_generation_timestamp_but_changes_with_values(self):
        base = build_context(
            [{"id": "2026-08-24", "hrv": 50}],
            oldest="2026-08-01",
            newest="2026-08-24",
        )
        newer_stamp = dict(base)
        newer_stamp["generated_at_utc"] = "2099-01-01T00:00:00+00:00"
        self.assertEqual(signature_payload(base), signature_payload(newer_stamp))

        changed = build_context(
            [{"id": "2026-08-24", "hrv": 51}],
            oldest="2026-08-01",
            newest="2026-08-24",
        )
        self.assertNotEqual(signature_payload(base), signature_payload(changed))

    def test_private_context_file_is_owner_read_write_only(self):
        context = build_context(
            [{"id": "2026-08-24", "restingHR": 49}],
            oldest="2026-08-01",
            newest="2026-08-24",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wellness.json"
            write_private_context(path, context)
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, stat.S_IRUSR | stat.S_IWUSR)

    def test_update_workflow_uses_tmp_file_and_never_tracks_wellness_data(self):
        repo_root = SCRIPTS.parents[1]
        workflow = (repo_root / ".github" / "workflows" / "update-training.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Load private Garmin wellness context", workflow)
        self.assertIn("WELLNESS_CONTEXT_FILE: /tmp/training_wellness_context.json", workflow)
        self.assertIn('python "träning/scripts/wellness_context.py" --days 28', workflow)
        self.assertIn("Remove private wellness context", workflow)
        tracked_block = workflow.split("TRACKED=(", 1)[1].split(")", 1)[0]
        self.assertNotIn("wellness", tracked_block.lower())
        self.assertLess(
            workflow.index("Load private Garmin wellness context"),
            workflow.index("AI coach analysis"),
        )


if __name__ == "__main__":
    unittest.main()
