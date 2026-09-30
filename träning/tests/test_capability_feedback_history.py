#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_athlete_state import archived_planned_workouts, build_state  # noqa: E402


class CapabilityFeedbackHistoryTests(unittest.TestCase):
    def test_archived_plan_can_recover_verified_historical_capability_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            weeks = Path(tmp)
            document = {
                "schema_version": 3,
                "planned_workouts": [
                    {
                        "date": "2026-09-25",
                        "sport": "swim",
                        "workout_key": "archive:swim:1",
                        "session": "Simning · 3 200 m · aerob uthållighet",
                        "stimuli": ["swim_aerobic"],
                    }
                ],
            }
            (weeks / "2026-W39.json").write_text(
                json.dumps(document),
                encoding="utf-8",
            )
            planned = archived_planned_workouts(
                today=date(2026, 9, 30),
                lookback_days=10,
                weeks_dir=weeks,
            )
            self.assertEqual(len(planned), 1)

            activities = {
                "activities": [
                    {
                        "id": 700,
                        "start_date_local": "2026-09-25T18:00:00",
                        "sport_type": "Swim",
                        "classification": "training",
                        "elapsed_time_s": 3600,
                        "distance_m": 3200,
                        "user_report": "Bra kontroll. RPE 6/10.",
                    }
                ]
            }
            state = build_state(
                activities,
                {"entries": []},
                today=date(2026, 9, 30),
                lookback_days=10,
                planned_workouts=planned,
            )
            session = state["recent_sessions"][0]
            self.assertEqual(
                session["training_profile"]["planning_credits"],
                ["swim_aerobic"],
            )
            capability = state["capability_states"]["by_capability"]["swim_aerobic"]
            self.assertEqual(capability["verified_exposure_count"], 1)
            self.assertEqual(capability["evidence_state"], "tolerated")

    def test_archive_reader_ignores_workouts_outside_fact_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            weeks = Path(tmp)
            (weeks / "2026-W30.json").write_text(
                json.dumps(
                    {
                        "planned_workouts": [
                            {
                                "date": "2026-07-22",
                                "sport": "swim",
                                "workout_key": "old",
                                "session": "Simning · 3 200 m · aerob uthållighet",
                                "stimuli": ["swim_aerobic"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            planned = archived_planned_workouts(
                today=date(2026, 9, 30),
                lookback_days=56,
                weeks_dir=weeks,
            )
            self.assertEqual(planned, [])


if __name__ == "__main__":
    unittest.main()
