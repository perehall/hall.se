#!/usr/bin/env python3
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from training_job_runner import build_stages, cleanup_private_context  # noqa: E402
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

    def test_update_pipeline_keeps_wellness_private_and_ephemeral(self):
        repo_root = SCRIPTS.parents[1]
        workflow = (repo_root / ".github" / "workflows" / "update-training.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("WELLNESS_CONTEXT_FILE: /tmp/training_wellness_context.json", workflow)
        tracked_block = workflow.split("TRACKED=(", 1)[1].split(")", 1)[0]
        self.assertNotIn("wellness", tracked_block.lower())

        stages = build_stages("reconcile")
        keys = [stage.key for stage in stages]
        self.assertLess(keys.index("load_wellness_context"), keys.index("coach_analysis"))
        wellness_stage = next(stage for stage in stages if stage.key == "load_wellness_context")
        self.assertTrue(wellness_stage.optional)
        self.assertIn(str(SCRIPTS / "wellness_context.py"), wellness_stage.command)
        self.assertEqual(wellness_stage.command[-2:], ("--days", "28"))

        with tempfile.TemporaryDirectory() as tmp:
            private_path = Path(tmp) / "wellness.json"
            private_path.write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"WELLNESS_CONTEXT_FILE": str(private_path)}):
                cleanup_private_context()
            self.assertFalse(private_path.exists())


if __name__ == "__main__":
    unittest.main()
