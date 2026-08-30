#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach_rules import planning_window  # noqa: E402
from finalize_post_workout_ui import apply_post_workout_ui  # noqa: E402


BASE_PAGE = """<!doctype html><html><head><style>.hero{}</style></head><body><div class="wrap">
<div class="hero week-focus-card"><h2>Veckofokus</h2><p>Princip.</p></div>
<!-- training-brain-v1:start -->
<section class="training-brain"><div>Dagens plan</div></section>
<!-- training-brain-v1:end -->
<section class="dashboard"><div class="dashboard-card"><div class="dashboard-title">Kommande dagar</div></div></section>
<h2 class="section">Aktuell vecka</h2>
</div></body></html>"""


def sample_plan():
    return {
        "meta": {"timezone": "Europe/Stockholm"},
        "days": [
            {
                "date": "2026-08-28",
                "label": "Fredag",
                "status": "completed",
                "session": "Löpning · backkvalitet · 12 backar · 9,67 km · 50:36",
                "planned_session": "Löpning · backkvalitet · 15 min lugnt + 6 × 150 m / full lugn nedjogg + 10 min lugnt",
                "development_focus": "Utfall: relativt kontrollerad löpning och pigg känsla. Nästa beslut väger in faktisk dos.",
                "activity_id": 42,
                "actual_session": {
                    "reps": 12,
                    "hill_duration_s_approx": 40,
                    "downhill_recovery_s_approx": 60,
                },
            },
            {
                "date": "2026-08-29",
                "label": "Lördag",
                "status": "conditional",
                "session": "MTB/XC · teknik + aerob stig · 75 min lugnt",
            },
        ],
    }


def sample_activities():
    return {
        "activities": [
            {
                "id": 42,
                "name": "Löpning på kvällen",
                "sport_type": "Run",
                "start_date_local": "2026-08-28T20:09:26Z",
                "distance_m": 9672.9,
                "elapsed_time_s": 3036,
                "average_heartrate": 145.1,
            }
        ]
    }


def sample_coach():
    return {
        "analyses": [
            {
                "activity_id": 42,
                "activity_date": "2026-08-28",
                "generated_at_utc": "2026-08-28T19:45:50Z",
                "assessment": {
                    "summary": "Fredagens backpass blev större än ordinerat och ökar veckobelastningen."
                },
                "plan_action": {
                    "action": "reduce",
                    "target_date": "2026-08-29",
                    "recommendation": "Skala ner lördagens MTB till 75 min lugn körning.",
                },
                "auto_apply": {"applied": True},
            }
        ]
    }


class PostWorkoutUiTests(unittest.TestCase):
    def test_completed_day_switches_home_to_feedback_state(self):
        rendered = apply_post_workout_ui(
            BASE_PAGE,
            sample_plan(),
            sample_activities(),
            sample_coach(),
            "2026-08-28",
        )
        self.assertIn('data-post-workout-state="completed"', rendered)
        self.assertIn('id="todayOutcomeTitle">Genomfört</h2>', rendered)
        self.assertNotIn("<section class=\"training-brain\"><div>Dagens plan</div></section>", rendered)
        self.assertIn("50:36", rendered)
        self.assertIn("9,67 km", rendered)
        self.assertIn(">145</dd>", rendered)
        self.assertIn("6 × 150 m", rendered)
        self.assertIn("12 backar · ca 40 s upp · ca 60 s jogg ned", rendered)
        self.assertIn("Coachens bedömning", rendered)
        self.assertIn("Effekt på planen", rendered)
        self.assertIn("MTB/XC · teknik + aerob stig · 75 min lugnt", rendered)
        self.assertIn("Justerat efter dagens faktiska utfall.", rendered)
        self.assertIn('id="aktuell-vecka"', rendered)

    def test_completed_sunday_shows_monday_session_from_upcoming_week(self):
        active = {
            "days": [
                {
                    "date": "2026-08-30",
                    "label": "Söndag",
                    "status": "completed",
                    "sport": "run",
                    "session": "Löpning · lugn distans",
                    "activity_id": 88,
                }
            ]
        }
        upcoming = {
            "days": [
                {
                    "date": "2026-08-31",
                    "label": "Måndag",
                    "status": "planned",
                    "sport": "enduro",
                    "session": "Enduroskola · fast tillfälle",
                    "dose_open": True,
                    "manual_lock": True,
                }
            ]
        }
        activities = {
            "activities": [
                {
                    "id": 88,
                    "name": "Löpning på morgonen",
                    "sport_type": "Run",
                    "start_date_local": "2026-08-30T08:00:00",
                    "distance_m": 10000,
                    "elapsed_time_s": 3600,
                }
            ]
        }
        window = planning_window(active, upcoming)
        rendered = apply_post_workout_ui(
            BASE_PAGE,
            window,
            activities,
            {"analyses": []},
            "2026-08-30",
        )
        self.assertIn("Nästa pass · Måndag 31 aug", rendered)
        self.assertIn("Enduroskola · fast tillfälle", rendered)

    def test_before_workout_state_is_untouched(self):
        rendered = apply_post_workout_ui(
            BASE_PAGE,
            sample_plan(),
            {"activities": []},
            sample_coach(),
            "2026-08-28",
        )
        self.assertEqual(rendered, BASE_PAGE)
        self.assertNotIn("post-workout-ux-v1", rendered)

    def test_unrelated_same_day_activity_does_not_complete_planned_session(self):
        plan = {
            "meta": {"timezone": "Europe/Stockholm"},
            "days": [
                {
                    "date": "2026-08-29",
                    "label": "Lördag",
                    "status": "conditional",
                    "sport": "bike",
                    "session": "MTB/XC · 75 min lugnt",
                }
            ],
        }
        activities = {
            "activities": [
                {
                    "id": 99,
                    "name": "Simning vid lunch",
                    "sport_type": "Swim",
                    "start_date_local": "2026-08-29T11:00:00Z",
                    "distance_m": 4000,
                    "elapsed_time_s": 4499,
                    "average_heartrate": 130,
                    "plan_relation": "separate",
                }
            ]
        }
        rendered = apply_post_workout_ui(
            BASE_PAGE,
            plan,
            activities,
            {"analyses": []},
            "2026-08-29",
        )
        self.assertEqual(rendered, BASE_PAGE)
        self.assertNotIn('data-post-workout-state="completed"', rendered)


    def test_post_workout_transform_is_idempotent(self):
        once = apply_post_workout_ui(
            BASE_PAGE,
            sample_plan(),
            sample_activities(),
            sample_coach(),
            "2026-08-28",
        )
        twice = apply_post_workout_ui(
            once,
            sample_plan(),
            sample_activities(),
            sample_coach(),
            "2026-08-28",
        )
        self.assertEqual(once, twice)
        self.assertEqual(twice.count('data-post-workout-state="completed"'), 1)
        self.assertEqual(twice.count("/* post-workout-ux-v1 */"), 1)


if __name__ == "__main__":
    unittest.main()
