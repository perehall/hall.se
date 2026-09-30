#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.application.presentation import build_presentation_snapshot
from training_core.presentation.navigation import PublishedWeek
from training_core.presentation.renderer import (
    render_document,
    render_snapshot,
    render_today,
    render_week,
    render_week_context,
    render_week_status,
)
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

    def test_planned_today_preserves_synced_device_status_on_overview(self):
        source_hash = "abc123"
        class SyncedRepository:
            def planned_days(self, start, end):
                return [
                    PlannedDay(
                        date(2026, 9, 30),
                        "Simning · 3 200 m · grepp/teknik + aerob",
                        "swim",
                        "planned",
                        workout_key="swim-synced",
                        payload={
                            "device_workout": {"source_hash": source_hash},
                            "device_sync": {
                                "status": "synced",
                                "transport": "intervals_icu",
                                "source_hash": source_hash,
                                "device_delivery": "unverified",
                            },
                        },
                    )
                ]

            def completed_activities(self, start, end):
                return []

        snapshot = build_presentation_snapshot(
            SyncedRepository(), today=date(2026, 9, 30)
        )
        rendered = render_today(snapshot)
        self.assertIn('data-device-sync="synced"', rendered)
        self.assertIn('class="v2-watch-icon"', rendered)
        self.assertIn("Verifierad i Intervals", rendered)

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

    def test_completed_week_day_renders_day_totals_and_per_activity_details(self):
        snapshot = build_presentation_snapshot(
            FakeRepository(), today=date(2026, 9, 26)
        )
        rendered = render_week(snapshot)
        self.assertIn("Enduro + Simning", rendered)
        self.assertIn(
            '<div class="v2-week-actual-summary">2 pass · 2:44:44 · 29,61 km</div>',
            rendered,
        )
        self.assertIn(
            '<div>Enduro · 26,61 km · 1:41:02</div>',
            rendered,
        )
        self.assertIn(
            '<div>Simning · 3,00 km · 1:03:42</div>',
            rendered,
        )

    def test_week_timeline_preserves_date_axis_status_and_rest_semantics(self):
        snapshot = build_presentation_snapshot(
            FakeRepository(), today=date(2026, 9, 26)
        )
        rendered = render_week(snapshot)
        self.assertIn('class="v2-week-day v2-week-card"', rendered)
        self.assertIn('class="v2-week-dayhead"', rendered)
        self.assertIn('class="v2-week-dow">Måndag</span>', rendered)
        self.assertIn('class="v2-week-date">21 sep</span>', rendered)
        self.assertIn('class="v2-week-state">Vilodag</span>', rendered)
        self.assertIn(
            '<strong class="v2-week-session v2-rest-day">Vilodag</strong>',
            rendered,
        )
        self.assertNotIn("Ingen planerad träning", rendered)

    def test_strength_template_source_labels_are_not_repeated_in_prescription(self):
        class StrengthRepository:
            def planned_days(self, start, end):
                return [
                    PlannedDay(
                        date(2026, 9, 26),
                        "Styrka/core · ca 35 min · styrkemall",
                        "strength",
                        "planned",
                        workout_key="strength-1",
                        payload={
                            "workout_design": {
                                "selected_candidate_id": "strength-35",
                                "candidates": [
                                    {
                                        "id": "strength-35",
                                        "prescription": {
                                            "blocks": [
                                                {
                                                    "name": "Tidsram",
                                                    "intensity": "kontrollerad",
                                                    "instruction": "Styrka/core inom vald tidsram",
                                                },
                                                {
                                                    "name": "Styrkemall",
                                                    "intensity": "enligt styrkemall",
                                                    "instruction": "Bulgarian split squat som huvudalternativ för unilateral benstyrka.",
                                                },
                                                {
                                                    "name": "Styrkemall",
                                                    "intensity": "enligt styrkemall",
                                                    "instruction": "Marklyft eller RDL som normal höftdominant huvudövning.",
                                                },
                                            ]
                                        },
                                    }
                                ],
                            }
                        },
                    )
                ]

            def completed_activities(self, start, end):
                return []

        snapshot = build_presentation_snapshot(
            StrengthRepository(), today=date(2026, 9, 26)
        )
        rendered = render_week(snapshot)
        self.assertIn(
            "Bulgarian split squat som huvudalternativ för unilateral benstyrka.",
            rendered,
        )
        self.assertIn(
            "Marklyft eller RDL som normal höftdominant huvudövning.",
            rendered,
        )
        self.assertNotIn("Styrkemall · enligt styrkemall", rendered)

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

    def test_week_status_includes_total_and_per_sport_distance(self):
        snapshot = build_presentation_snapshot(
            FakeRepository(), today=date(2026, 9, 26)
        )
        rendered = render_week_status(snapshot)
        self.assertIn("<summary>Veckostatus</summary>", rendered)
        self.assertIn("<strong>2</strong> pass", rendered)
        self.assertIn("<strong>2:44:44</strong> passtid", rendered)
        self.assertIn("<strong>29,61 km</strong> distans", rendered)
        self.assertIn("<strong>1</strong> träningsdag", rendered)
        self.assertIn("Enduro</span><strong>1:41:02 · 26,61 km</strong>", rendered)
        self.assertIn("Simning</span><strong>1:03:42 · 3,00 km</strong>", rendered)

    def test_current_week_context_keeps_week_totals_visible_without_opening_status(self):
        class WeekContext:
            focus = "Sim + kontrollerad löptröskel"
            meta_line = "Byggblock · mikrocykel 2 av 4"
            principle = ""
            hypothesis = ""
            primary = ()
            secondary = ()
            maintenance = ()
            protected = ()

        class Week:
            status_summary = "2 pass · 2:44:44 · 29,61 km · 1 träningsdag"

        class Snapshot:
            week_context = WeekContext()
            week = Week()

        rendered = render_week_context(Snapshot())
        self.assertIn(
            "Byggblock · mikrocykel 2 av 4 · 2 pass · 2:44:44 · "
            "29,61 km · 1 träningsdag",
            rendered,
        )

    def test_current_week_card_primitive_has_card_visual_contract(self):
        snapshot = build_presentation_snapshot(
            FakeRepository(), today=date(2026, 9, 26)
        )
        rendered = render_document(snapshot)
        self.assertIn('class="v2-week-day v2-week-card"', rendered)
        self.assertIn(
            ".v2-week-card{position:relative;display:block;margin:0;padding:16px 17px;"
            "border:1px solid #e5eaf1;border-radius:15px;background:var(--elevated);"
            "box-shadow:0 1px 2px rgba(15,23,42,.035),0 6px 16px rgba(15,23,42,.025)}",
            rendered,
        )

    def test_week_uses_structured_dose_recovery_and_swim_equipment_layout(self):
        class StructuredRepository:
            def planned_days(self, start, end):
                return [
                    PlannedDay(
                        date(2026, 9, 26),
                        "Simning · 3 200 m · aerob/teknik",
                        "swim",
                        "planned",
                        workout_key="swim-structured",
                        payload={
                            "workout_design": {
                                "selected_candidate_id": "swim-3200",
                                "candidates": [
                                    {
                                        "id": "swim-3200",
                                        "prescription": {
                                            "completeness": "full",
                                            "blocks": [
                                                {
                                                    "name": "Insim",
                                                    "work": {
                                                        "distance_m": 400,
                                                        "repetitions": 1,
                                                    },
                                                    "equipment": [],
                                                    "instruction": "Lugn insim",
                                                },
                                                {
                                                    "name": "Teknik",
                                                    "work": {
                                                        "distance_m": 50,
                                                        "repetitions": 6,
                                                    },
                                                    "recovery": {"duration_s": 15},
                                                    "equipment": [],
                                                    "instruction": "Stabil linje",
                                                },
                                            ],
                                        },
                                    }
                                ],
                            }
                        },
                    )
                ]

            def completed_activities(self, start, end):
                return []

        snapshot = build_presentation_snapshot(
            StructuredRepository(), today=date(2026, 9, 26)
        )
        rendered = render_week(snapshot)
        self.assertIn('class="v2-prescription-dose">400 m</span>', rendered)
        self.assertIn('class="v2-prescription-dose">6×50 m</span>', rendered)
        self.assertIn("Lugn insim · utan redskap", rendered)
        self.assertIn("Stabil linje · utan redskap · v 15 s", rendered)

    def test_feedback_without_coach_result_is_explicitly_pending(self):
        class PendingRepository:
            def planned_days(self, start, end):
                return [
                    PlannedDay(
                        date(2026, 9, 26),
                        "Enduro",
                        "enduro",
                        "completed",
                        workout_key="enduro-1",
                    )
                ]

            def completed_activities(self, start, end):
                return [
                    CompletedActivity(
                        "99",
                        date(2026, 9, 26),
                        "Enduro",
                        "enduro",
                        3600,
                        10000,
                        feedback_event_key="training-input:bbbbbbbbbbbbbbbbbbbbbbbb",
                        feedback_text="Kontrollerat.",
                        rpe=4,
                        feelings=("fresh",),
                    )
                ]

        snapshot = build_presentation_snapshot(
            PendingRepository(), today=date(2026, 9, 26)
        )
        rendered = render_today(snapshot)
        self.assertIn("Utvärdering", rendered)
        self.assertIn("Coachanalys väntar.", rendered)

    def test_snapshot_carries_v2_feedback_interaction_without_legacy_finalizer(self):
        snapshot = build_presentation_snapshot(
            FakeRepository(), today=date(2026, 9, 26)
        )
        rendered = render_snapshot(snapshot)
        self.assertIn("/* training-v2-feedback */", rendered)
        self.assertIn("/träning/training-api/input", rendered)
        self.assertIn("training-gui-v2", rendered)
        self.assertIn("durable_ack_missing", rendered)
        self.assertIn("Sparningen kunde inte verifieras som beständigt lagrad.", rendered)
        self.assertIn("persistence_not_configured", rendered)
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



    def test_future_week_uses_current_week_as_navigation_anchor_and_has_no_today_card(self):
        snapshot = build_presentation_snapshot(
            FakeRepository(),
            today=date(2026, 9, 28),
            current_date=date(2026, 9, 26),
        )
        self.assertEqual(snapshot.navigation.state, "kommande")
        rendered = render_snapshot(snapshot)
        self.assertIn("· kommande", rendered)
        self.assertIn('aria-label="Kommande veckas pass"', rendered)
        self.assertIn('href="/träning/"', rendered)
        self.assertIn("Simning · aerob", rendered)
        self.assertNotIn('class="v2-today"', rendered)


if __name__ == "__main__":
    unittest.main()
