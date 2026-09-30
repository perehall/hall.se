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

    def test_legacy_archive_plan_days_are_used_as_explicit_historical_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            weeks = Path(tmp)
            (weeks / "2026-W39.json").write_text(
                json.dumps(
                    {
                        "legacy_plan_days": [
                            {
                                "date": "2026-09-23",
                                "sport": "swim",
                                "session": "Simning · 3 200 m · aerob/teknik",
                                "stimuli": ["swim_aerobic", "swim_technique"],
                                "status": "preliminary",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            planned = archived_planned_workouts(
                today=date(2026, 9, 30),
                lookback_days=10,
                weeks_dir=weeks,
            )
            self.assertEqual(len(planned), 1)
            self.assertEqual(planned[0]["stimuli"], ["swim_aerobic", "swim_technique"])
            self.assertEqual(planned[0]["archive_evidence_source"], "legacy_plan_days")

            activities = {
                "activities": [
                    {
                        "id": 701,
                        "start_date_local": "2026-09-23T18:00:00",
                        "sport_type": "Swim",
                        "classification": "training",
                        "elapsed_time_s": 3537,
                        "distance_m": 3200,
                        "user_report": "Bra kontroll. RPE 6/10. Kunde gjort mer.",
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
            profile = state["recent_sessions"][0]["training_profile"]
            self.assertEqual(
                profile["planning_credits"],
                ["swim_aerobic", "swim_technique"],
            )
            self.assertEqual(
                state["capability_states"]["by_capability"]["swim_technique"]["evidence_state"],
                "observed",
            )

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
