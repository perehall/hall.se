#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.presentation import build_presentation_snapshot
from training_core.presentation.navigation import PublishedWeek
from training_core.presentation.renderer import render_snapshot, render_today, render_week
from training_core.domain.weather import DailyWeatherForecast, WeatherSnapshot
from training_core.presentation.today import CompletedActivity, PlannedDay


class FakeRepository:
    def planned_days(self, start, end):
        return [
            PlannedDay(date(2026, 9, 26), "Simning · 4 000 m", "swim", "completed"),
            PlannedDay(
                date(2026, 9, 27),
                "Löpning · lugn distans · 60 min",
                "run",
                "conditional",
                reason="Bygg löptålighet med god kontroll.",
                development_focus="Lugn aerob löpning.",
                payload={
                    "workout_design": {
                        "selected_candidate_id": "easy",
                        "candidates": [
                            {
                                "id": "easy",
                                "prescription": {
                                    "blocks": [
                                        {
                                            "name": "Huvuddel",
                                            "intensity": "Z2",
                                            "instruction": "60 min lugnt",
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                },
            ),
            PlannedDay(
                date(2026, 9, 28),
                "Simning · aerob",
                "swim",
                "preliminary",
            ),
        ]

    def completed_activities(self, start, end):
        return [
            CompletedActivity(
                "1",
                date(2026, 9, 26),
                "Enduro",
                "enduro",
                6062,
                26611.2,
                feedback_event_key="training-input:aaaaaaaaaaaaaaaaaaaaaaaa",
                feedback_text="Kul och kontrollerat.",
                rpe=5,
                feelings=("fresh",),
                coach_summary="Enduron vägdes in som faktisk träningsbelastning.",
                plan_action="keep",
                action_reason="Ingen planändring behövdes.",
                recommendation="Fortsätt enligt nästa planerade pass.",
            ),
            CompletedActivity(
                "2",
                date(2026, 9, 26),
                "Simning",
                "swim",
                3822,
                3000,
            ),
        ]


class FakeArchiveRepository:
    def published_weeks(self):
        return [
            PublishedWeek(
                "2026-W38",
                date(2026, 9, 14),
                date(2026, 9, 20),
                "/träning/vecka/2026-W38/",
            )
        ]


class FakeWeatherRepository:
    def current(self):
        return WeatherSnapshot(
            status="ok",
            source="SMHI Open Data · SNOW1gv1",
            fetched_at_utc="2026-09-27T08:45:00+00:00",
            daily=(
                DailyWeatherForecast(
                    local_date=date(2026, 9, 27),
                    location_name="Oxelösund",
                    temperature_min_c=12.0,
                    temperature_max_c=15.4,
                    wind_max_ms=4.9,
                    precip_probability_max_pct=0,
                    symbol_code=1,
                ),
            ),
        )


class PresentationSliceTests(unittest.TestCase):
    def test_repository_to_read_model_to_html_is_pure_and_semantic(self):
        snapshot = build_presentation_snapshot(
            FakeRepository(), today=date(2026, 9, 26)
        )
        rendered = render_today(snapshot)
        self.assertIn('data-state="completed"', rendered)
        self.assertIn("<span>Enduro + Simning</span></h1>", rendered)
        self.assertIn("Enduro · 26,61 km · 1:41:02", rendered)
        self.assertIn("Simning · 3,00 km · 1:03:42", rendered)
        self.assertIn("Löpning · lugn distans · 60 min", rendered)
        self.assertNotIn("Simning · 4 000 m</h1>", rendered)

    def test_planned_today_renders_multiple_workouts_without_merging_them(self):
        class MultiRepository:
            def planned_days(self, start, end):
                return [
                    PlannedDay(
                        date(2026, 9, 26),
                        "Simning · 3 200 m",
                        "swim",
                        "planned",
                        workout_key="swim-1",
                    ),
                    PlannedDay(
                        date(2026, 9, 26),
                        "Styrka/core · 35 min",
                        "strength",
                        "planned",
                        workout_key="strength-1",
                    ),
                ]

            def completed_activities(self, start, end):
                return []

        snapshot = build_presentation_snapshot(
            MultiRepository(), today=date(2026, 9, 26)
        )
        rendered = render_today(snapshot)
        self.assertIn("2 planerade pass", rendered)
        self.assertIn('data-workout-key="swim-1"', rendered)
        self.assertIn('data-workout-key="strength-1"', rendered)
        self.assertEqual(rendered.count('class="v2-planned-workout"'), 2)

    def test_week_renders_multiple_same_day_workouts_as_independent_cards(self):
        class MultiRepository:
            def planned_days(self, start, end):
                return [
                    PlannedDay(
                        date(2026, 9, 26),
                        "Simning · 3 200 m",
                        "swim",
                        "planned",
                        workout_key="swim-1",
                    ),
                    PlannedDay(
                        date(2026, 9, 26),
                        "Styrka/core · 35 min",
                        "strength",
                        "planned",
                        workout_key="strength-1",
                    ),
                ]

            def completed_activities(self, start, end):
                return []

        snapshot = build_presentation_snapshot(
            MultiRepository(), today=date(2026, 9, 26)
        )
        rendered = render_week(snapshot)
        self.assertEqual(rendered.count('class="v2-week-planned-workout"'), 2)
        self.assertIn('data-workout-key="swim-1"', rendered)
        self.assertIn('data-workout-key="strength-1"', rendered)
        self.assertIn("Simning · 3 200 m", rendered)
        self.assertIn("Styrka/core · 35 min", rendered)
        self.assertNotIn("Simning · 3 200 m + Styrka/core · 35 min", rendered)

    def test_multisport_workout_renders_ordered_components(self):
        class BrickRepository:
            def planned_days(self, start, end):
                return [
                    PlannedDay(
                        date(2026, 9, 26),
                        "Brick · cykel + löpning",
                        "multisport",
                        "planned",
                        payload={
                            "components": [
                                {"order": 1, "sport": "bike"},
                                {"order": 2, "sport": "run"},
                            ]
                        },
                        workout_key="brick-1",
                    )
                ]

            def completed_activities(self, start, end):
                return []

        snapshot = build_presentation_snapshot(
            BrickRepository(), today=date(2026, 9, 26)
        )
        rendered = render_today(snapshot)
        self.assertIn("Cykel → Löpning", rendered)
        self.assertIn("Brick · cykel + löpning", rendered)

    def test_completed_today_renders_feedback_and_coach_outcome_without_finalizer(self):
        snapshot = build_presentation_snapshot(
            FakeRepository(), today=date(2026, 9, 26)
        )
        rendered = render_today(snapshot)
        self.assertIn("Din känsla", rendered)
        self.assertIn("RPE 5 · Pigg", rendered)
        self.assertIn("Kul och kontrollerat.", rendered)
        self.assertIn("Utvärdering", rendered)
        self.assertIn(
            "Enduron vägdes in som faktisk träningsbelastning.", rendered
        )
        self.assertIn("Planpåverkan", rendered)
        self.assertIn("Ingen ändring · Ingen planändring behövdes.", rendered)
        self.assertIn("Nästa steg", rendered)
        self.assertIn("Fortsätt enligt nästa planerade pass.", rendered)
        self.assertIn("Ursprungsplan", rendered)
        self.assertIn("Simning · 4 000 m", rendered)
        self.assertIn("Inte utvärderat", rendered)
        self.assertIn('data-v2-feedback-editor', rendered)
        self.assertIn(
            'data-feedback-event-key="training-input:aaaaaaaaaaaaaaaaaaaaaaaa"',
            rendered,
        )
        self.assertIn('data-v2-feedback-save', rendered)
        self.assertNotIn('training-input-ui-v1', rendered)

    def test_snapshot_carries_v2_feedback_interaction_without_legacy_finalizer(self):
        snapshot = build_presentation_snapshot(
            FakeRepository(), today=date(2026, 9, 26)
        )
        rendered = render_snapshot(snapshot)
        self.assertIn("/* training-v2-feedback */", rendered)
        self.assertIn("/träning/training-api/input", rendered)
        self.assertIn("training-gui-v2", rendered)
        self.assertIn("durable_ack_missing", rendered)
        self.assertNotIn("data-processed-event-keys", rendered)

    def test_snapshot_navigation_uses_archive_and_future_canonical_plan(self):
        snapshot = build_presentation_snapshot(
            FakeRepository(),
            today=date(2026, 9, 26),
            archive_repository=FakeArchiveRepository(),
        )
        rendered = render_snapshot(snapshot)
        self.assertIn("<strong>Vecka 39</strong>", rendered)
        self.assertIn("21–27 sep · aktuell", rendered)
        self.assertIn('href="/träning/vecka/2026-W38/"', rendered)
        self.assertIn('href="/träning/vecka/2026-W40/"', rendered)

    def test_planned_today_renders_prescription_rationale_and_weather_without_finalizer(self):
        snapshot = build_presentation_snapshot(
            FakeRepository(),
            today=date(2026, 9, 27),
            weather_repository=FakeWeatherRepository(),
        )
        rendered = render_today(snapshot)
        self.assertIn("Passupplägg", rendered)
        self.assertIn("Huvuddel · Z2 · 60 min lugnt", rendered)
        self.assertIn("Plan och motivering", rendered)
        self.assertIn("Bygg löptålighet med god kontroll.", rendered)
        self.assertIn("Lugn aerob löpning.", rendered)
        self.assertIn(
            "Väder · Oxelösund · Klart · 12,0–15,4 °C · "
            "nederbördsrisk max 0 % · vind max 4,9 m/s",
            rendered,
        )
        self.assertIn("Väderprognos:", render_snapshot(snapshot))
        self.assertIn(">SMHI</a>", render_snapshot(snapshot))


if __name__ == "__main__":
    unittest.main()
