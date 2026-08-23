#!/usr/bin/env python3
import json
import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from week_review_contracts import validate_week_review_document  # noqa: E402
from weekly_review import (  # noqa: E402
    REVIEW_SCHEMA,
    build_openai_body,
    build_week_facts,
    call_openai,
    should_process,
    source_hash,
)
from weekly_review_ui import insert_review_after_dashboard  # noqa: E402


def sample_plan():
    return {
        "schema_version": 3,
        "meta": {
            "timezone": "Europe/Stockholm",
            "week": 34,
            "week_start": "2026-08-17",
            "week_end": "2026-08-23",
            "title": "Testvecka",
            "principle": "Kontinuitet.",
        },
        "days": [
            {"date": "2026-08-17", "label": "Måndag", "status": "completed", "sport": "swim", "session": "Simning", "reason": "Genomfört."},
            {"date": "2026-08-18", "label": "Tisdag", "status": "completed", "sport": "strength", "session": "Styrka", "reason": "Genomfört."},
            {"date": "2026-08-19", "label": "Onsdag", "status": "completed", "sport": "swimrun", "session": "Swimrun", "reason": "Genomfört."},
            {"date": "2026-08-20", "label": "Torsdag", "status": "completed", "sport": "run", "session": "Tröskel", "reason": "Kontrollerat."},
            {"date": "2026-08-21", "label": "Fredag", "status": "completed", "sport": "swim", "session": "Simning", "reason": "Genomfört."},
            {"date": "2026-08-22", "label": "Lördag", "status": "completed", "sport": "enduro", "classification": "recreation", "session": "Enduro", "reason": "Lätt rekreation."},
            {"date": "2026-08-23", "label": "Söndag", "status": "preliminary", "sport": "run", "session": "Trail", "reason": "Preliminärt."},
        ],
    }


def sample_activities():
    return [
        {
            "id": 1,
            "display_label": "Simning",
            "sport_type": "Swim",
            "start_date_local": "2026-08-17T18:00:00Z",
            "elapsed_time_s": 3600,
            "moving_time_s": 3500,
        },
        {
            "id": 2,
            "display_label": "Löpning",
            "sport_type": "Run",
            "start_date_local": "2026-08-20T18:00:00Z",
            "elapsed_time_s": 3000,
            "moving_time_s": 3000,
            "distance_m": 10000,
        },
        {
            "id": 3,
            "display_label": "Enduro",
            "sport_type": "Enduro",
            "classification": "recreation",
            "start_date_local": "2026-08-22T11:00:00Z",
            "elapsed_time_s": 4800,
            "moving_time_s": 3900,
            "user_report": "Lätt och inte det minsta slitsamt.",
            "source_sport_type": "MountainBikeRide",
            "garmin_activity_type": "Motocross",
        },
    ]


def valid_assessment():
    return {
        "summary": "Veckan gav kontinuitet med kontrollerad kvalitet.",
        "worked": ["Löpningen genomfördes kontrollerat."],
        "not_as_planned": ["Söndagens utfall saknas i underlaget."],
        "load_continuity": "Flera träningsdagar kombinerades utan att rekreation omtolkades som kvalitet.",
        "key_lesson": "Kontrollerad kvalitet och lågkostnadsdagar fungerade väl tillsammans.",
        "next_week_implication": "Behåll kontinuiteten och låt faktisk återhämtning styra progressionen.",
        "uncertainties": ["Söndagens slutliga utfall saknas."],
    }


def completed_response():
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(valid_assessment(), ensure_ascii=False),
                    }
                ],
            }
        ],
    }


class WeeklyReviewTests(unittest.TestCase):
    def test_facts_separate_recreation_from_training(self):
        facts = build_week_facts(sample_plan(), sample_activities())
        self.assertEqual(facts["week_key"], "2026-W34")
        self.assertEqual(facts["activity_count"], 3)
        self.assertEqual(facts["training_activity_count"], 2)
        self.assertEqual(facts["recreation_activity_count"], 1)
        self.assertEqual(facts["total_activity_time_s"], 11400)
        self.assertEqual(facts["training_time_s"], 6600)
        self.assertEqual(facts["recreation_time_s"], 4800)
        enduro = next(item for item in facts["activities"] if item["id"] == 3)
        self.assertEqual(enduro["classification"], "recreation")
        self.assertEqual(enduro["source_sport_type"], "MountainBikeRide")
        self.assertEqual(enduro["garmin_activity_type"], "Motocross")

    def test_plan_outcomes_are_deterministic(self):
        facts = build_week_facts(sample_plan(), sample_activities())
        by_date = {item["date"]: item for item in facts["plan_outcomes"]}
        self.assertEqual(by_date["2026-08-17"]["outcome"], "fulfilled")
        self.assertEqual(by_date["2026-08-20"]["outcome"], "fulfilled")
        self.assertEqual(by_date["2026-08-22"]["outcome"], "fulfilled")
        self.assertEqual(by_date["2026-08-23"]["outcome"], "not_completed")

    def test_initial_review_waits_until_week_is_closed(self):
        self.assertFalse(should_process("2026-08-23", date(2026, 8, 23), False))
        self.assertTrue(should_process("2026-08-23", date(2026, 8, 24), False))
        self.assertTrue(should_process("2026-08-23", date(2026, 8, 26), False))
        self.assertFalse(should_process("2026-08-23", date(2026, 8, 27), False))
        self.assertTrue(should_process("2026-08-23", date(2026, 9, 10), True))

    def test_source_hash_changes_when_source_data_changes(self):
        plan = sample_plan()
        facts = build_week_facts(plan, sample_activities())
        first = source_hash(plan, facts)
        activities = sample_activities()
        activities[0]["elapsed_time_s"] = 3601
        second = source_hash(plan, build_week_facts(plan, activities))
        self.assertNotEqual(first, second)

    def test_openai_body_is_strict_and_week_review_specific(self):
        body = build_openai_body("system", {"week": {}}, 2500, model="test-model")
        self.assertEqual(body["model"], "test-model")
        self.assertFalse(body["store"])
        fmt = body["text"]["format"]
        self.assertTrue(fmt["strict"])
        self.assertEqual(fmt["name"], "training_week_review")
        self.assertIs(fmt["schema"], REVIEW_SCHEMA)

    def test_mocked_openai_review_requires_no_network(self):
        calls = []

        def fake_request(body):
            calls.append(body)
            return completed_response()

        result = call_openai("system", {"week": {}}, request_fn=fake_request)
        self.assertEqual(result["summary"], valid_assessment()["summary"])
        self.assertEqual(len(calls), 1)

    def test_review_document_contract_checks_fact_arithmetic(self):
        plan = sample_plan()
        facts = build_week_facts(plan, sample_activities())
        document = {
            "schema_version": 1,
            "contract_version": 1,
            "week_key": "2026-W34",
            "week_start": "2026-08-17",
            "week_end": "2026-08-23",
            "source_hash": source_hash(plan, facts),
            "generated_at_utc": "2026-08-24T00:20:00+00:00",
            "model": "test-model",
            "facts": facts,
            "assessment": valid_assessment(),
        }
        self.assertTrue(validate_week_review_document(document))
        document["facts"]["total_activity_time_s"] += 1
        with self.assertRaises(RuntimeError):
            validate_week_review_document(document)

    def test_review_ui_contains_no_score_and_is_inserted_after_dashboard(self):
        facts = build_week_facts(sample_plan(), sample_activities())
        review = {
            "week_key": "2026-W34",
            "facts": facts,
            "assessment": valid_assessment(),
        }
        page = (
            '<html><head><style>.x{}</style></head><body>'
            '<section class="dashboard">D</section><h2>Pass</h2></body></html>'
        )
        rendered = insert_review_after_dashboard(page, review)
        self.assertIn('data-week-review="2026-W34"', rendered)
        self.assertIn("Veckoutvärdering", rendered)
        self.assertIn("Till nästa veckas planering", rendered)
        self.assertNotIn("/10", rendered)
        self.assertLess(rendered.index("</section>"), rendered.index('data-week-review="2026-W34"'))
        self.assertLess(rendered.index('data-week-review="2026-W34"'), rendered.index("<h2>Pass</h2>"))


if __name__ == "__main__":
    unittest.main()
