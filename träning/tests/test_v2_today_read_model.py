#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.presentation.today import (  # noqa: E402
    CompletedActivity,
    PlannedDay,
    build_today_read_model,
)


class TodayReadModelTests(unittest.TestCase):
    def test_actual_multi_session_truth_overrides_planned_session(self):
        today = date(2026, 9, 26)
        model = build_today_read_model(
            today=today,
            plan=[
                PlannedDay(today, "Simning · 4 000 m", "swim", "planned"),
                PlannedDay(
                    date(2026, 9, 27),
                    "Löpning · lugn distans · 120 min",
                    "run",
                    "planned",
                ),
            ],
            activities=[
                CompletedActivity("1", today, "Enduro", "enduro", 6062, 26611.2),
                CompletedActivity("2", today, "Simning", "swim", 3822, 3000),
            ],
        )

        self.assertEqual(model.state, "completed")
        self.assertEqual(model.title, "Enduro + Simning")
        self.assertEqual(
            model.details,
            ("Enduro · 26,61 km · 1:41:02", "Simning · 3,00 km · 1:03:42"),
        )
        self.assertEqual(model.planned_session, "Simning · 4 000 m")
        self.assertEqual(model.next_session, "Löpning · lugn distans · 120 min")
        self.assertEqual(len(model.outcomes), 2)

    def test_completed_outcome_carries_feedback_and_latest_coach_decision(self):
        today = date(2026, 9, 27)
        activity = CompletedActivity(
            provider_activity_id="42",
            local_date=today,
            label="Löpning",
            sport_family="run",
            elapsed_time_s=3600,
            distance_m=12000,
            feedback_text="Kontrollerat och pigg efteråt.",
            rpe=6,
            feelings=("fresh", "could_do_more"),
            coach_summary="Passet gav avsett stimulus med god kontroll.",
            plan_action="keep",
            action_reason="Ingen konkret belastningssignal motiverar ändring.",
            recommendation="Fortsätt enligt nästa planerade pass.",
        )
        model = build_today_read_model(
            today=today,
            plan=[PlannedDay(today, "Löpning · tröskel", "run", "fixed")],
            activities=[activity],
        )

        outcome = model.outcomes[0]
        self.assertEqual(outcome.feedback_status, "RPE 6 · Pigg · Kunde gjort mer")
        self.assertEqual(outcome.feedback_text, "Kontrollerat och pigg efteråt.")
        self.assertEqual(outcome.coach_summary, "Passet gav avsett stimulus med god kontroll.")
        self.assertEqual(outcome.plan_impact, "Ingen ändring")
        self.assertEqual(
            outcome.action_reason,
            "Ingen konkret belastningssignal motiverar ändring.",
        )
        self.assertEqual(outcome.next_step, "Fortsätt enligt nästa planerade pass.")

    def test_reduce_without_auto_apply_is_a_recommendation_not_a_false_change(self):
        today = date(2026, 9, 27)
        activity = CompletedActivity(
            "42",
            today,
            "Löpning",
            "run",
            plan_action="reduce",
            coach_auto_applied=False,
        )
        model = build_today_read_model(
            today=today,
            plan=[PlannedDay(today, "Löpning", "run", "fixed")],
            activities=[activity],
        )
        self.assertEqual(model.outcomes[0].plan_impact, "Ändring rekommenderades")

    def test_today_reason_never_exposes_internal_planning_provenance(self):
        today = date(2026, 9, 27)
        model = build_today_read_model(
            today=today,
            plan=[
                PlannedDay(
                    today,
                    "Löpning · lugn distans · 60 min",
                    "run",
                    "conditional",
                    reason=(
                        "Långt lugnt löppass för löptålighet. "
                        "Valet utgår från 119.767 i athlete_state. "
                        "Veckobeslut: establish; materialiserad relation: hold."
                    ),
                )
            ],
            activities=[],
        )
        self.assertEqual(model.reason, "Långt lugnt löppass för löptålighet.")
        self.assertNotIn("athlete_state", model.reason)
        self.assertNotIn("materialiserad relation", model.reason)

    def test_plan_is_used_only_when_no_actual_activity_exists(self):
        today = date(2026, 9, 25)
        model = build_today_read_model(
            today=today,
            plan=[PlannedDay(today, "Simning · 4 000 m", "swim", "preliminary")],
            activities=[],
        )
        self.assertEqual(model.state, "preliminary")
        self.assertEqual(model.title, "Simning · 4 000 m")
        self.assertEqual(model.details, ())
        self.assertEqual(model.outcomes, ())


if __name__ == "__main__":
    unittest.main()
