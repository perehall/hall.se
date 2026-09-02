#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_week_activity_insights import apply_week_activity_insights  # noqa: E402


BASE_PAGE = """<!doctype html><html><head><style>.x{}</style></head><body>
<div class="day past-completed" id="dag-2026-08-31"><div class="pass">Enduro</div></div>
<div class="day past-completed" id="dag-2026-09-01"><div class="pass">Löpning</div></div>
<div class="day decision-horizon" id="dag-2026-09-02"><div class="pass">Simning</div></div>
</body></html>"""


def plan():
    return {
        "meta": {
            "week_start": "2026-08-31",
            "week_end": "2026-09-06",
            "timezone": "Europe/Stockholm",
        },
        "days": [
            {"date": "2026-08-31", "session": "Enduroskola"},
            {"date": "2026-09-01", "session": "Löpning · kontrollerad tröskel · 3 × 8 min"},
            {"date": "2026-09-02", "session": "Simning"},
        ],
    }


def activities():
    return {
        "activities": [
            {
                "id": 1,
                "sport_type": "Enduro",
                "display_label": "Enduro",
                "start_date_local": "2026-08-31T18:00:00",
                "elapsed_time_s": 6000,
                "distance_m": 23000,
                "average_heartrate": 111,
            },
            {
                "id": 2,
                "sport_type": "Run",
                "start_date_local": "2026-09-01T19:00:00",
                "elapsed_time_s": 3030,
                "distance_m": 10350,
                "average_heartrate": 145,
            },
            {
                "id": 3,
                "sport_type": "Swim",
                "start_date_local": "2026-09-02T07:00:00",
                "elapsed_time_s": 3600,
                "distance_m": 3200,
                "average_heartrate": 128,
            },
        ]
    }


def coach():
    return {
        "analyses": [
            {
                "activity_id": 1,
                "activity_date": "2026-08-31",
                "generated_at_utc": "2026-08-31T20:00:00Z",
                "assessment": {
                    "summary": "Enduron lämnar nästa dags tröskelpass kvar i planen.",
                    "load_interpretation": "Passet bidrog med teknisk och neuromuskulär belastning.",
                    "facts": ["Enduro: 23,00 km · 1:40:00 · snittpuls 111."],
                    "interpretations": ["Enduron bidrog med teknisk och neuromuskulär belastning utan skäl att ändra planen."],
                    "unknowns": ["Subjektiv benkänsla saknas."],
                },
                "plan_action": {
                    "action": "keep",
                    "recommendation": "Genomför 3 × 8 min kontrollerat nästa dag.",
                },
                "auto_apply": {"applied": False},
            },
            {
                "activity_id": 2,
                "activity_date": "2026-09-01",
                "generated_at_utc": "2026-09-01T21:00:00Z",
                "assessment": {
                    "summary": "Tröskelpasset absorberas utan planändring.",
                    "load_interpretation": "Närbelastningen motiverar inte en hårdare progression.",
                    "facts": ["Run: 10,35 km · 50:30 · snittpuls 145."],
                    "interpretations": ["Tröskelpasset var kontrollerat och följer mikrocykelns plan."],
                    "unknowns": ["Subjektiv benkänsla saknas."],
                },
                "plan_action": {
                    "action": "keep",
                    "recommendation": "Behåll planerad simning som lågmekanisk stödexponering.",
                },
                "auto_apply": {"applied": False},
            },
        ]
    }


class WeekActivityInsightTests(unittest.TestCase):
    def test_previous_week_activities_receive_retroactive_insights(self):
        rendered = apply_week_activity_insights(
            BASE_PAGE,
            plan(),
            activities(),
            coach(),
            {"entries": []},
            "2026-09-02",
        )
        self.assertIn('data-week-activity-insight="1"', rendered)
        self.assertIn('data-week-activity-insight="2"', rendered)
        self.assertNotIn('data-week-activity-insight="3"', rendered)
        self.assertIn("Enduron krävde ingen planändring", rendered)
        self.assertIn("Tröskelpasset krävde ingen planändring", rendered)
        self.assertIn("Planpåverkan", rendered)
        self.assertIn("Ingen ändring", rendered)
        self.assertIn("Visa underlag", rendered)
        self.assertNotIn("Visa passfakta", rendered)
        self.assertNotIn("AI-analys · historik", rendered)
        self.assertNotIn('class="historical-coach"', rendered)
        self.assertIn("1:40:00", rendered)
        self.assertIn("10,35 km", rendered)

    def test_same_protocol_performance_signal_wins_over_generic_coach_summary(self):
        performance = {
            "entries": [
                {
                    "activity_id": 2,
                    "protocol_key": "run_threshold:3x8:90s",
                    "work_intervals": [
                        {"index": 1, "pace_s_per_km": 245.0, "average_heartrate": 150.0},
                        {"index": 2, "pace_s_per_km": 243.0, "average_heartrate": 152.0},
                        {"index": 3, "pace_s_per_km": 242.0, "average_heartrate": 154.0},
                    ],
                    "summary": {
                        "first_to_last_pace_delta_s_per_km": -3.0,
                        "first_to_last_hr_delta": 4.0,
                    },
                    "comparison": {
                        "previous_activity_date": "2026-08-25",
                        "same_protocol": True,
                        "mean_pace_delta_s_per_km": -2.0,
                        "mean_hr_delta": 1.0,
                    },
                }
            ]
        }
        rendered = apply_week_activity_insights(
            BASE_PAGE,
            plan(),
            activities(),
            coach(),
            performance,
            "2026-09-02",
        )
        self.assertIn("Snabbare än senaste jämförbara tröskelpasset", rendered)
        self.assertIn("medeltempo -2,0 s/km", rendered)
        self.assertIn("medelpuls +1,0 bpm", rendered)

    def test_transform_is_idempotent(self):
        once = apply_week_activity_insights(
            BASE_PAGE,
            plan(),
            activities(),
            coach(),
            {"entries": []},
            "2026-09-02",
        )
        twice = apply_week_activity_insights(
            once,
            plan(),
            activities(),
            coach(),
            {"entries": []},
            "2026-09-02",
        )
        self.assertEqual(once, twice)
        self.assertEqual(twice.count('data-week-activity-insight="1"'), 1)
        self.assertEqual(twice.count('data-week-activity-insight="2"'), 1)


if __name__ == "__main__":
    unittest.main()
