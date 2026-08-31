#!/usr/bin/env python3
import copy
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from training_contracts import (  # noqa: E402
    ContractError,
    validate_activities_document,
    validate_coach_document,
    validate_plan_document,
    validate_performance_history_document,
    validate_watch_workout,
)


def valid_week(*, upcoming=False):
    start = date(2026, 8, 24)
    sports = ["enduro", "swim", "run", "strength", "swim", "bike", "open"]
    days = []
    for index, sport in enumerate(sports):
        day_date = (start + timedelta(days=index)).isoformat()
        status = "open" if sport == "open" else "planned"
        day = {
            "date": day_date,
            "label": f"Dag {index + 1}",
            "status": status,
            "sport": sport,
            "session": f"Pass {index + 1}",
            "reason": "Testfixture med explicit maskinläsbar sport.",
        }
        if upcoming:
            day["planning_status"] = "open" if sport == "open" else "planned"
        days.append(day)
    document = {
        "schema_version": 3,
        "meta": {
            "timezone": "Europe/Stockholm",
            "week": 35,
            "week_start": "2026-08-24",
            "week_end": "2026-08-30",
            "title": "Testvecka",
            "principle": "Kontrakttest.",
        },
        "days": days,
    }
    if upcoming:
        document["state"] = "preliminary"
        document["week_key"] = "2026-W35"
    return document


def valid_activities():
    return {
        "schema_version": 2,
        "activities": [
            {
                "id": 1,
                "sport_type": "Run",
                "start_date": "2026-08-26T08:00:00Z",
                "start_date_local": "2026-08-26T10:00:00Z",
                "distance_m": 10000.0,
                "moving_time_s": 3000,
                "elapsed_time_s": 3100,
            }
        ],
    }


def valid_performance_history():
    return {
        "schema_version": 1,
        "generated_at_utc": "2026-08-31T09:00:00+00:00",
        "entries": [
            {
                "activity_id": 1,
                "activity_date": "2026-08-26",
                "marker_id": "run-threshold-control",
                "protocol_key": "run_threshold:3x8:90s",
                "work_intervals": [
                    {
                        "index": 1,
                        "duration_s": 480.0,
                        "distance_m": 2000.0,
                        "pace_s_per_km": 240.0,
                        "average_heartrate": 150.0,
                        "max_heartrate": 155.0,
                        "average_watts": 300.0,
                        "average_cadence": 88.0,
                    }
                ],
                "summary": {
                    "work_interval_count": 1,
                    "total_work_s": 480.0,
                    "mean_pace_s_per_km": 240.0,
                    "mean_heartrate": 150.0,
                    "mean_watts": 300.0,
                    "first_to_last_pace_delta_s_per_km": 0.0,
                    "first_to_last_hr_delta": 0.0,
                    "first_to_last_watts_delta": 0.0,
                },
                "comparison": None,
            }
        ],
    }


def valid_coach():
    return {
        "contract_version": 3,
        "analyses": [
            {
                "activity_id": 1,
                "activity_date": "2026-08-26",
                "assessment": {
                    "summary": "Kontrollerat pass.",
                    "load_interpretation": "Tolkning med angiven osäkerhet.",
                    "confidence": "medium",
                    "facts": ["Run: 10,00 km."],
                    "interpretations": ["Belastningen ser absorberbar ut."],
                    "unknowns": ["Subjektiv återhämtning saknas."],
                },
                "plan_action": {
                    "action": "keep",
                    "target_date": "",
                    "reason": "Ingen automatisk ändring.",
                    "recommendation": "Behåll planen.",
                    "requires_approval": False,
                },
            }
        ],
    }


class TrainingContractTests(unittest.TestCase):
    def test_valid_current_and_upcoming_week_pass(self):
        self.assertTrue(validate_plan_document(valid_week()))
        self.assertTrue(validate_plan_document(valid_week(upcoming=True), upcoming=True))

    def test_missing_explicit_sport_fails(self):
        plan = valid_week()
        del plan["days"][2]["sport"]
        with self.assertRaises(ContractError):
            validate_plan_document(plan)

    def test_free_text_cannot_replace_explicit_sport(self):
        plan = valid_week()
        del plan["days"][2]["sport"]
        plan["days"][2]["session"] = "Löpning · tröskel"
        with self.assertRaises(ContractError):
            validate_plan_document(plan)

    def test_nonconsecutive_or_duplicate_dates_fail(self):
        plan = valid_week()
        plan["days"][3]["date"] = plan["days"][2]["date"]
        with self.assertRaises(ContractError):
            validate_plan_document(plan)

    def test_wrong_week_end_fails(self):
        plan = valid_week()
        plan["meta"]["week_end"] = "2026-08-31"
        with self.assertRaises(ContractError):
            validate_plan_document(plan)

    def test_structured_swim_distance_must_match(self):
        workout = {
            "sync_enabled": True,
            "id": "test-swim",
            "external_id": "test-swim-2026-08-25",
            "type": "Swim",
            "planned_distance_m": 200,
            "blocks": [
                {
                    "name": "Main",
                    "repeat": 2,
                    "steps": [
                        {"kind": "swim", "distance_m": 50},
                        {"kind": "rest", "duration_s": 20},
                    ],
                }
            ],
        }
        with self.assertRaises(ContractError):
            validate_watch_workout(workout, "fixture")

    def test_lap_rest_is_valid_but_has_no_distance(self):
        workout = {
            "sync_enabled": True,
            "id": "test-swim",
            "external_id": "test-swim-2026-08-25",
            "type": "Swim",
            "planned_distance_m": 100,
            "blocks": [
                {"name": "A", "steps": [{"kind": "swim", "distance_m": 50}]},
                {"name": "Setvila", "steps": [{"kind": "lap_rest", "duration_s": 60}]},
                {"name": "B", "steps": [{"kind": "swim", "distance_m": 50}]},
            ],
        }
        self.assertEqual(validate_watch_workout(workout, "fixture"), 100)

    def test_sync_enabled_workout_requires_external_id(self):
        workout = {
            "sync_enabled": True,
            "id": "test-swim",
            "type": "Swim",
            "blocks": [{"name": "A", "steps": [{"kind": "swim", "distance_m": 50}]}],
        }
        with self.assertRaises(ContractError):
            validate_watch_workout(workout, "fixture")

    def test_duplicate_activity_ids_fail(self):
        state = valid_activities()
        state["activities"].append(copy.deepcopy(state["activities"][0]))
        with self.assertRaises(ContractError):
            validate_activities_document(state)

    def test_negative_activity_duration_fails(self):
        state = valid_activities()
        state["activities"][0]["elapsed_time_s"] = -1
        with self.assertRaises(ContractError):
            validate_activities_document(state)

    def test_valid_performance_history_passes(self):
        self.assertTrue(validate_performance_history_document(valid_performance_history(), activity_ids={"1"}))

    def test_performance_history_requires_known_activity(self):
        with self.assertRaises(ContractError):
            validate_performance_history_document(valid_performance_history(), activity_ids={"2"})

    def test_valid_coach_contract_passes(self):
        self.assertTrue(validate_coach_document(valid_coach(), activity_ids={"1"}))

    def test_high_confidence_with_unknowns_fails_contract(self):
        coach = valid_coach()
        coach["analyses"][0]["assessment"]["confidence"] = "high"
        with self.assertRaises(ContractError):
            validate_coach_document(coach, activity_ids={"1"})

    def test_duplicate_coach_activity_ids_fail(self):
        coach = valid_coach()
        coach["analyses"].append(copy.deepcopy(coach["analyses"][0]))
        with self.assertRaises(ContractError):
            validate_coach_document(coach, activity_ids={"1"})


if __name__ == "__main__":
    unittest.main()
