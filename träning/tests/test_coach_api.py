#!/usr/bin/env python3
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach import (  # noqa: E402
    SCHEMA,
    apply_conservative_action,
    build_openai_body,
    call_openai,
    extract_output_text,
    scrub_private_wellness_output,
    stable_hash,
)


def valid_result():
    return {
        "assessment": {
            "summary": "Kontrollerat pass.",
            "load_interpretation": "Låg till måttlig belastning.",
            "confidence": "medium",
            "facts": [],
            "interpretations": ["Fortsatt kontinuitet."],
            "unknowns": ["Subjektiv återhämtning saknas."],
        },
        "plan_action": {
            "action": "keep",
            "target_date": "",
            "reason": "Ingen ändring.",
            "recommendation": "Behåll planen.",
            "requires_approval": False,
        },
    }


def completed_response(result=None):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(result or valid_result(), ensure_ascii=False),
                    }
                ],
            }
        ],
    }


class CoachApiTests(unittest.TestCase):
    def test_request_body_uses_strict_schema_and_never_contains_api_key(self):
        body = build_openai_body("system", {"x": 1}, 4000, model="test-model")
        self.assertEqual(body["model"], "test-model")
        self.assertFalse(body["store"])
        self.assertEqual(body["reasoning"], {"effort": "minimal"})
        fmt = body["text"]["format"]
        self.assertTrue(fmt["strict"])
        self.assertIs(fmt["schema"], SCHEMA)
        self.assertNotIn("api_key", json.dumps(body).lower())

    def test_completed_mock_response_is_parsed_without_network(self):
        seen = []

        def fake_request(body):
            seen.append(body)
            return completed_response()

        result = call_openai("system", {"today": "2026-08-23"}, request_fn=fake_request)
        self.assertEqual(result["plan_action"]["action"], "keep")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["max_output_tokens"], 4000)

    def test_incomplete_max_tokens_retries_once_with_larger_budget(self):
        calls = []
        responses = [
            {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}},
            completed_response(),
        ]

        def fake_request(body):
            calls.append(body["max_output_tokens"])
            return responses.pop(0)

        result = call_openai("system", {}, request_fn=fake_request)
        self.assertEqual(result["assessment"]["confidence"], "medium")
        self.assertEqual(calls, [4000, 8000])

    def test_http_429_retries_without_real_sleep_or_network(self):
        calls = []
        sleeps = []

        def fake_request(body):
            calls.append(body["max_output_tokens"])
            if len(calls) == 1:
                raise urllib.error.HTTPError(
                    url="https://api.openai.com/v1/responses",
                    code=429,
                    msg="rate limited",
                    hdrs=None,
                    fp=io.BytesIO(b'{"error":"rate limited"}'),
                )
            return completed_response()

        call_openai("system", {}, request_fn=fake_request, sleep_fn=sleeps.append)
        self.assertEqual(calls, [4000, 8000])
        self.assertEqual(sleeps, [4])

    def test_refusal_fails_closed(self):
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "cannot comply"}],
                }
            ]
        }
        with self.assertRaises(RuntimeError):
            extract_output_text(response)

    def test_missing_output_text_fails_closed(self):
        with self.assertRaises(RuntimeError):
            extract_output_text({"output": []})

    def test_rest_action_changes_machine_readable_plan_type(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-25",
                    "status": "planned",
                    "sport": "run",
                    "session": "Löpning · lugnt · 45 min",
                    "reason": "Planerat lugnt pass.",
                }
            ]
        }
        action = {
            "action": "rest",
            "target_date": "2026-08-25",
            "reason": "Återhämtning prioriteras.",
            "recommendation": "Vila.",
        }
        changed, _ = apply_conservative_action(
            plan,
            action,
            now_utc="2026-08-23T18:00:00+00:00",
        )
        day = plan["days"][0]
        self.assertTrue(changed)
        self.assertEqual(day["sport"], "rest")
        self.assertEqual(day["status"], "conditional")
        self.assertEqual(day["original_session"], "Löpning · lugnt · 45 min")
        self.assertEqual(day["auto_coach"]["applied_at_utc"], "2026-08-23T18:00:00+00:00")

    def test_wellness_change_invalidates_coach_but_timestamp_change_does_not(self):
        plan = {"days": []}
        latest = {"id": 1}
        strategy = {"schema_version": 1}
        wellness = {
            "schema_version": 1,
            "source": "Garmin via Intervals.icu",
            "privacy": "ephemeral_private",
            "generated_at_utc": "2026-08-26T06:00:00+00:00",
            "window": {"oldest": "2026-07-30", "newest": "2026-08-26"},
            "latest_date": "2026-08-26",
            "coverage": {},
            "daily": [{"date": "2026-08-26", "hrv": 50}],
        }
        first = stable_hash(plan, latest, "2026-08-26", strategy, wellness)

        timestamp_only = dict(wellness)
        timestamp_only["generated_at_utc"] = "2026-08-26T09:00:00+00:00"
        self.assertEqual(first, stable_hash(plan, latest, "2026-08-26", strategy, timestamp_only))

        changed = dict(wellness)
        changed["daily"] = [{"date": "2026-08-26", "hrv": 51}]
        self.assertNotEqual(first, stable_hash(plan, latest, "2026-08-26", strategy, changed))

    def test_private_wellness_terms_are_scrubbed_before_persistence(self):
        result = valid_result()
        result["assessment"]["summary"] = "Garmin HRV 48 och sömnscore 71 talar för försiktighet."
        result["plan_action"]["reason"] = "Vilopuls 52 via Intervals.icu avviker."
        scrubbed = scrub_private_wellness_output(result)
        text = json.dumps(scrubbed, ensure_ascii=False).lower()
        self.assertNotIn("garmin", text)
        self.assertNotIn("hrv", text)
        self.assertNotIn("vilopuls", text)
        self.assertNotIn("intervals.icu", text)
        self.assertIn("återhämtningsunderlaget", text)


if __name__ == "__main__":
    unittest.main()
