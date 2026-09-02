#!/usr/bin/env python3
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach_rules import normalize_no_remaining_plan  # noqa: E402

from coach import (  # noqa: E402
    SCHEMA,
    apply_conservative_action,
    build_openai_body,
    call_openai,
    extract_output_text,
    normalize_dose_option_field,
    normalize_resolved_dose_reselection,
    normalize_same_day_open_dose_action,
    neutralize_same_day_absorption_claims,
    neutralize_unbased_load_labels,
    performance_context_for_activity,
    performance_facts,
    scrub_private_wellness_output,
    rolling_load_context,
    stable_hash,
    validate_dose_option_action,
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
            "dose_option_id": "",
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

    def test_rolling_load_context_uses_three_days_back_and_forward(self):
        strategy = {
            "load_model": {
                "lookback_days": 3,
                "lookahead_days": 3,
                "dimensions": [{"key": "mechanical"}],
                "rules": ["Use multi-day context."],
            }
        }
        activities = [
            {"id": 1, "start_date_local": "2026-08-26T08:00:00", "sport_type": "Run"},
            {"id": 2, "start_date_local": "2026-08-27T08:00:00", "sport_type": "Run"},
            {"id": 3, "start_date_local": "2026-08-30T08:00:00", "sport_type": "Run"},
            {"id": 4, "start_date_local": "2026-08-31T08:00:00", "sport_type": "Enduro"},
        ]
        plan = {
            "days": [
                {"date": "2026-08-31", "session": "Enduro"},
                {"date": "2026-09-01", "session": "Threshold"},
                {"date": "2026-09-03", "session": "MTB"},
                {"date": "2026-09-04", "session": "Hills"},
            ]
        }
        context = rolling_load_context(activities, plan, "2026-08-31", strategy)
        self.assertEqual([a["id"] for a in context["actual_activities"]], [3, 4])
        self.assertEqual(
            [d["date"] for d in context["planned_days"]],
            ["2026-08-31", "2026-09-01", "2026-09-03"],
        )
        self.assertEqual(context["lookback_days"], 3)
        self.assertEqual(context["lookahead_days"], 3)

    def test_performance_context_is_selected_by_activity_id(self):
        history = {
            "entries": [
                {"activity_id": 10, "protocol_key": "run_threshold:3x8:90s"},
                {"activity_id": 11, "protocol_key": "run_threshold:3x10:90s"},
            ]
        }
        self.assertEqual(
            performance_context_for_activity(history, 11)["protocol_key"],
            "run_threshold:3x10:90s",
        )
        self.assertEqual(performance_context_for_activity(history, 99), {})

    def test_performance_facts_preserve_interval_and_comparison_numbers(self):
        context = {
            "protocol_key": "run_threshold:3x8:90s",
            "work_intervals": [
                {"pace_s_per_km": 245.0, "average_heartrate": 150.0},
                {"pace_s_per_km": 243.0, "average_heartrate": 152.0},
                {"pace_s_per_km": 242.0, "average_heartrate": 154.0},
            ],
            "summary": {
                "first_to_last_pace_delta_s_per_km": -3.0,
                "first_to_last_hr_delta": 4.0,
            },
            "comparison": {
                "previous_activity_date": "2026-08-25",
                "mean_pace_delta_s_per_km": -2.0,
                "mean_hr_delta": 1.0,
                "mean_watts_delta": 3.0,
            },
        }
        facts = performance_facts(context)
        self.assertIn("4:05/km / 4:03/km / 4:02/km", facts[0])
        self.assertIn("150 / 152 / 154 bpm", facts[0])
        self.assertIn("-3,0 s/km", facts[1])
        self.assertIn("+4,0 bpm", facts[1])
        self.assertIn("2026-08-25", facts[2])
        self.assertIn("-2,0 s/km", facts[2])
        self.assertIn("+1,0 bpm", facts[2])

    def test_performance_context_changes_stable_hash(self):
        base = stable_hash(
            {}, {"id": 1}, "2026-08-31", {}, {}, {}, {"protocol_key": "a"}
        )
        changed = stable_hash(
            {}, {"id": 1}, "2026-08-31", {}, {}, {}, {"protocol_key": "b"}
        )
        self.assertNotEqual(base, changed)

    def test_rolling_context_changes_stable_hash(self):
        base = stable_hash({}, {"id": 1}, "2026-08-31", {}, {}, {"actual_activities": [{"id": 1}]})
        changed = stable_hash({}, {"id": 1}, "2026-08-31", {}, {}, {"actual_activities": [{"id": 2}]})
        self.assertNotEqual(base, changed)

    def test_completed_day_keeps_known_future_fixed_session_visible(self):
        action = {
            "action": "keep",
            "target_date": "",
            "reason": "Dagens pass är genomfört.",
            "recommendation": "Nästa pass är måndagens fasta enduroskola.",
            "dose_option_id": "",
            "requires_approval": False,
        }
        normalized = normalize_no_remaining_plan(
            action,
            allowed_dates=[],
            latest_date="2026-08-30",
            fulfilled_dates={"2026-08-30": 1},
            remaining_dates=["2026-08-31"],
        )
        self.assertEqual(
            normalized["recommendation"],
            "Nästa pass är måndagens fasta enduroskola.",
        )

    def test_completed_day_only_claims_missing_plan_when_window_is_empty(self):
        action = {
            "action": "keep",
            "target_date": "",
            "reason": "Dagens pass är genomfört.",
            "recommendation": "Behåll.",
            "dose_option_id": "",
            "requires_approval": False,
        }
        normalized = normalize_no_remaining_plan(
            action,
            allowed_dates=[],
            latest_date="2026-08-30",
            fulfilled_dates={"2026-08-30": 1},
            remaining_dates=[],
        )
        self.assertIn("Nästa planerade pass saknas", normalized["recommendation"])


    def test_same_day_absorption_claim_requires_post_workout_response(self):
        result = valid_result()
        result["assessment"]["summary"] = "Belastningen är absorberbar."
        result["assessment"]["interpretations"] = [
            "Passet är absorberat och torsdagens plan kan köras utan kontrollpunkt."
        ]
        normalized = neutralize_same_day_absorption_claims(
            result,
            latest_activity={"id": 1, "sport_type": "Swimrun"},
            latest_date="2026-09-02",
            local_date="2026-09-02",
        )
        self.assertIn("går inte att avgöra", normalized["assessment"]["summary"])
        self.assertIn("subjektiv respons", normalized["assessment"]["interpretations"][0])


    def test_unbased_relative_load_labels_are_neutralized_but_facts_are_preserved(self):
        result = valid_result()
        result["assessment"]["summary"] = (
            "Stort löppass ger hög kardiovaskulär volym och låg mekanisk belastning."
        )
        result["assessment"]["load_interpretation"] = (
            "Kardiovaskulär volym är hög de senaste tre dagarna."
        )
        result["assessment"]["facts"] = [
            'Användarrapport: "Lätt och inte det minsta slitsamt."'
        ]
        result["assessment"]["interpretations"] = [
            "Måttlig träningsbelastning kan tala för bibehållen plan."
        ]
        result["assessment"]["unknowns"] = [
            "Det går inte att avgöra om återhämtningsbehovet bedöms som högt."
        ]
        result["plan_action"]["reason"] = "Hög mekanisk belastning skulle motivera reduktion."
        result["plan_action"]["recommendation"] = (
            "Behåll planen om belastningen inte bedöms som hög."
        )

        calibrated = neutralize_unbased_load_labels(result)

        derived = " ".join(
            [
                calibrated["assessment"]["summary"],
                calibrated["assessment"]["load_interpretation"],
                *calibrated["assessment"]["interpretations"],
                *calibrated["assessment"]["unknowns"],
                calibrated["plan_action"]["reason"],
                calibrated["plan_action"]["recommendation"],
            ]
        ).lower()
        self.assertNotIn("hög kardiovaskulär volym", derived)
        self.assertNotIn("låg mekanisk belastning", derived)
        self.assertNotIn("måttlig träningsbelastning", derived)
        self.assertNotIn("volym är hög", derived)
        self.assertNotIn("belastningen inte bedöms som hög", derived)
        self.assertIn("kan inte nivåklassas mot personlig baslinje", derived)
        self.assertEqual(
            calibrated["assessment"]["facts"],
            ['Användarrapport: "Lätt och inte det minsta slitsamt."'],
        )

    def test_private_wellness_terms_are_scrubbed_before_persistence(self):
        result = valid_result()
        result["assessment"]["summary"] = "Garmin HRV 48 och sömnscore 71 visar en normal wellness-trend."
        result["plan_action"]["reason"] = "Vilopuls 52 via Intervals.icu avviker."
        scrubbed = scrub_private_wellness_output(result)
        text = json.dumps(scrubbed, ensure_ascii=False).lower()
        self.assertNotIn("garmin", text)
        self.assertNotIn("hrv", text)
        self.assertNotIn("vilopuls", text)
        self.assertNotIn("intervals.icu", text)
        self.assertNotIn("wellness", text)
        self.assertIn("återhämtningsunderlaget", text)





    def test_reselecting_same_resolved_dose_is_idempotent(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-29",
                    "status": "conditional",
                    "sport": "bike",
                    "session": "MTB/XC · 75 min",
                    "dose_open": False,
                    "dose_resolution": {
                        "state": "resolved",
                        "kind": "duration_minutes",
                        "value": 75,
                        "option_id": "mtb-75",
                    },
                    "dose_options": [
                        {
                            "id": "mtb-75",
                            "kind": "duration_minutes",
                            "value": 75,
                            "session": "MTB/XC · 75 min",
                        },
                        {
                            "id": "mtb-90",
                            "kind": "duration_minutes",
                            "value": 90,
                            "session": "MTB/XC · 90 min",
                        },
                    ],
                }
            ]
        }
        action = {
            "action": "reduce",
            "target_date": "2026-08-29",
            "reason": "Behåll konservativ dos.",
            "recommendation": "Kör 75 min.",
            "dose_option_id": "mtb-75",
            "requires_approval": False,
        }
        normalized = normalize_resolved_dose_reselection(plan, action)
        self.assertEqual(normalized["dose_option_id"], "")
        self.assertTrue(validate_dose_option_action(plan, normalized, "2026-08-28"))

    def test_resolved_dose_can_only_move_downward(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-29",
                    "status": "conditional",
                    "sport": "bike",
                    "session": "MTB/XC · 90 min",
                    "dose_open": False,
                    "dose_resolution": {
                        "state": "resolved",
                        "kind": "duration_minutes",
                        "value": 90,
                        "option_id": "mtb-90",
                    },
                    "dose_options": [
                        {
                            "id": "mtb-60",
                            "kind": "duration_minutes",
                            "value": 60,
                            "session": "MTB/XC · 60 min",
                        },
                        {
                            "id": "mtb-90",
                            "kind": "duration_minutes",
                            "value": 90,
                            "session": "MTB/XC · 90 min",
                        },
                    ],
                }
            ]
        }
        reduce_action = {
            "action": "reduce",
            "target_date": "2026-08-29",
            "reason": "Ny belastning kräver mindre dos.",
            "recommendation": "Kör 60 min.",
            "dose_option_id": "mtb-60",
            "requires_approval": False,
        }
        self.assertTrue(validate_dose_option_action(plan, reduce_action, "2026-08-28"))
        changed, _ = apply_conservative_action(
            plan,
            reduce_action,
            now_utc="2026-08-28T19:40:00+00:00",
        )
        self.assertTrue(changed)
        self.assertEqual(plan["days"][0]["dose_resolution"]["value"], 60)
        self.assertEqual(plan["days"][0]["dose_resolution"]["source"], "near_term_ai_revision")

        increase_action = {
            "action": "reduce",
            "target_date": "2026-08-29",
            "reason": "x",
            "recommendation": "x",
            "dose_option_id": "mtb-90",
            "requires_approval": False,
        }
        with self.assertRaises(RuntimeError):
            validate_dose_option_action(plan, increase_action, "2026-08-28")

    def test_same_day_keep_without_dose_option_becomes_review(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-28",
                    "status": "planned",
                    "sport": "run",
                    "session": "Löpning · backkvalitet · dos öppen",
                    "dose_open": True,
                    "dose_options": [
                        {
                            "id": "hill-6",
                            "kind": "structured",
                            "value": 6,
                            "session": "6 × 150 m",
                        }
                    ],
                }
            ]
        }
        action = {
            "action": "keep",
            "target_date": "2026-08-28",
            "reason": "Behåll kvaliteten.",
            "recommendation": "Välj konservativ dos.",
            "dose_option_id": "",
            "requires_approval": False,
        }
        normalized = normalize_same_day_open_dose_action(plan, action, "2026-08-28")
        self.assertEqual(normalized["action"], "review")
        self.assertEqual(normalized["target_date"], "")
        self.assertEqual(normalized["dose_option_id"], "")
        self.assertIn("öppen dos", normalized["reason"])

    def test_review_clears_stale_dose_option(self):
        action = {
            "action": "review",
            "target_date": "",
            "reason": "Mellanliggande belastning saknas.",
            "recommendation": "Avvakta.",
            "dose_option_id": "mtb-60",
            "requires_approval": False,
        }
        normalized = normalize_dose_option_field(action)
        self.assertEqual(normalized["dose_option_id"], "")

    def test_keep_can_resolve_open_same_day_dose_from_approved_option(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-27",
                    "status": "planned",
                    "sport": "bike",
                    "session": "MTB/XC · teknik + aerob stig · dos öppen",
                    "dose_open": True,
                    "dose_options": [
                        {
                            "id": "mtb-45",
                            "kind": "duration_minutes",
                            "value": 45,
                            "session": "MTB/XC · 45 min · teknik + lugn aerob stig",
                        },
                        {
                            "id": "mtb-60",
                            "kind": "duration_minutes",
                            "value": 60,
                            "session": "MTB/XC · 60 min · teknik + lugn aerob stig",
                        },
                    ],
                }
            ]
        }
        action = {
            "action": "keep",
            "target_date": "2026-08-27",
            "reason": "Närbelastningen medger normal konservativ stöddos.",
            "recommendation": "Kör 60 min lugnt och tekniskt.",
            "dose_option_id": "mtb-60",
            "requires_approval": False,
        }
        self.assertTrue(validate_dose_option_action(plan, action, "2026-08-27"))
        changed, _ = apply_conservative_action(
            plan,
            action,
            now_utc="2026-08-27T16:00:00+00:00",
        )
        day = plan["days"][0]
        self.assertTrue(changed)
        self.assertFalse(day["dose_open"])
        self.assertEqual(day["session"], "MTB/XC · 60 min · teknik + lugn aerob stig")
        self.assertEqual(day["dose_resolution"]["option_id"], "mtb-60")

    def test_same_day_keep_must_choose_approved_dose_when_options_exist(self):
        plan = {
            "days": [
                {
                    "date": "2026-08-27",
                    "status": "planned",
                    "sport": "bike",
                    "session": "MTB/XC · dos öppen",
                    "dose_open": True,
                    "dose_options": [
                        {
                            "id": "mtb-45",
                            "kind": "duration_minutes",
                            "value": 45,
                            "session": "MTB/XC · 45 min",
                        }
                    ],
                }
            ]
        }
        action = {
            "action": "keep",
            "target_date": "2026-08-27",
            "reason": "x",
            "recommendation": "Behåll.",
            "dose_option_id": "",
            "requires_approval": False,
        }
        with self.assertRaises(RuntimeError):
            validate_dose_option_action(plan, action, "2026-08-27")


if __name__ == "__main__":
    unittest.main()
