#!/usr/bin/env python3
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from openai_usage import log_openai_usage  # noqa: E402


class OpenAiUsageTests(unittest.TestCase):
    def test_logs_only_usage_counters_not_prompt_content(self):
        response = {
            "model": "gpt-5-mini",
            "usage": {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 400},
                "output_tokens": 120,
                "output_tokens_details": {"reasoning_tokens": 80},
                "total_tokens": 1120,
            },
        }
        request = {"input": [{"role": "user", "content": "DO-NOT-LOG-THIS"}]}

        output = io.StringIO()
        with redirect_stdout(output):
            log_openai_usage("coach", response, request)

        line = output.getvalue()
        self.assertIn("OPENAI_USAGE stage=coach model=gpt-5-mini", line)
        self.assertIn("input_tokens=1000", line)
        self.assertIn("cached_tokens=400", line)
        self.assertIn("output_tokens=120", line)
        self.assertIn("reasoning_tokens=80", line)
        self.assertIn("total_tokens=1120", line)
        self.assertIn("request_chars=", line)
        self.assertIn("payload_field_chars=none", line)
        self.assertNotIn("DO-NOT-LOG-THIS", line)

    def test_payload_field_sizes_are_logged_without_values(self):
        response = {
            "model": "gpt-5-mini",
            "usage": {"input_tokens": 10, "total_tokens": 10},
        }
        payload = {
            "current_plan": {"secret_text": "PLAN-CONTENT-MUST-NOT-LOG"},
            "recent_activities": [{"id": 1}],
        }
        request = {
            "input": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": __import__("json").dumps(payload)},
            ]
        }

        output = io.StringIO()
        with redirect_stdout(output):
            log_openai_usage("coach", response, request)

        line = output.getvalue()
        self.assertIn("payload_field_chars=", line)
        self.assertIn("current_plan:", line)
        self.assertIn("recent_activities:", line)
        self.assertNotIn("PLAN-CONTENT-MUST-NOT-LOG", line)


if __name__ == "__main__":
    unittest.main()
