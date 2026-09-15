#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from coach_output_guard import guard_result  # noqa: E402


class CoachOutputGuardTests(unittest.TestCase):
    def _result(self):
        return {
            "assessment": {
                "summary": (
                    "22 km distans i 5:16/km med stabil puls och en kontrollerad fartökning."
                ),
                "load_interpretation": (
                    "Passet adderar betydande kardiovaskulär och mekanisk belastning; "
                    "närbelastningen de senaste dagarna är hög."
                ),
                "confidence": "medium",
                "facts": [],
                "interpretations": [
                    (
                        "Ett långt genomfört distanspass visar att dagens dos var absorberbar "
                        "och att sen fartökning var hållbar utan smärta."
                    ),
                    "Inga subjektiva tecken finns som skulle kräva vila i nästa 48–72 h.",
                ],
                "unknowns": [],
            },
            "plan_action": {
                "action": "keep",
                "target_date": "",
                "reason": "Passet var genomfört enligt plan.",
                "recommendation": (
                    "Följ planen men rapportera dagens benkänsla morgon 07–09 om den känns avvikande."
                ),
                "dose_option_id": "",
                "requires_approval": False,
            },
        }

    def _comparison(self):
        return {
            "plan_day_found": True,
            "selected_duration_minutes": 75.0,
            "approved_duration_max_minutes": 90.0,
            "actual_duration_minutes": 116.0,
            "duration_relation_to_approved_options": "above_approved_duration_range",
        }

    def test_known_sep6_failure_modes_are_repaired_before_publish(self):
        guarded = guard_result(
            self._result(),
            latest_date="2026-09-06",
            local_date="2026-09-06",
            plan_comparison=self._comparison(),
        )
        text = str(guarded)
        self.assertNotIn("är hög", text)
        self.assertNotIn("betydande", text)
        self.assertNotIn("absorberbar", text)
        self.assertNotIn("nästa 48–72 h", text)
        self.assertNotIn("genomfört enligt plan", text)
        self.assertNotIn("07–09", text)
        self.assertNotIn("stabil puls", text)
        self.assertIn("med en kontrollerad fartökning", guarded["assessment"]["summary"])
        self.assertIn("sen fartökning var hållbar utan smärta", text)
        self.assertIn("116 min", text)
        self.assertIn("90 min", text)
        self.assertIn("nästa morgon", guarded["plan_action"]["recommendation"])

    def test_future_recovery_claim_is_not_removed_for_historical_analysis(self):
        result = self._result()
        result["assessment"]["summary"] = "Neutral."
        result["assessment"]["load_interpretation"] = "Neutral."
        result["plan_action"]["reason"] = "Neutral."
        result["plan_action"]["recommendation"] = "Behåll planen."
        result["assessment"]["interpretations"] = [
            "Inga subjektiva tecken finns som skulle kräva vila i nästa 48–72 h."
        ]
        guarded = guard_result(
            result,
            latest_date="2026-09-05",
            local_date="2026-09-06",
            plan_comparison={},
        )
        self.assertIn("nästa 48–72 h", guarded["assessment"]["interpretations"][0])

    def test_enduro_public_text_uses_human_duration_and_no_internal_field_names(self):
        result = {
            "assessment": {
                "summary": (
                    "Genomfört 95 min Enduro-session (session_duration 5718s) med 2915s moving time, "
                    "måttlig snittpuls och korta icke-rörelseperioder."
                ),
                "load_interpretation": (
                    "Den långa elapsed_time ger teknisk belastning medan moving_time är kortare."
                ),
                "confidence": "medium",
                "facts": [
                    "Enduro: 14,64 km · 1:35:18 · 508,4 m+ · snittpuls 106,7 · maxpuls 168."
                ],
                "interpretations": [
                    "Passet påverkar nästa prioriterade löpstimulus.",
                    "Den långa elapsed-tiden med non_moving_time 2803s fångas inte av moving_time.",
                ],
                "unknowns": ["Subjektiv benstatus saknas."],
            },
            "plan_action": {
                "action": "keep",
                "target_date": "2026-09-08",
                "reason": "Behåll planen.",
                "recommendation": "Behåll tisdagens planerade tröskelpass.",
            },
        }
        activity = {
            "id": 20078705519,
            "sport_type": "Enduro",
            "total_elevation_gain_m": 508.4,
            "average_heartrate": 106.7,
            "workout_analysis_context": {
                "enduro": {
                    "session_duration_s": 5718.0,
                    "moving_time_s": 2915.0,
                    "non_moving_time_s": 2803.0,
                    "duration_basis": "elapsed_time_s",
                }
            },
        }
        guarded = guard_result(
            result,
            latest_date="2026-09-07",
            local_date="2026-09-07",
            plan_comparison={},
            activity=activity,
        )
        assessment = guarded["assessment"]
        public_text = " ".join(
            [assessment["summary"], assessment["load_interpretation"]]
            + assessment["interpretations"]
        )
        self.assertIn("1:35:18", assessment["summary"])
        self.assertIn("508 m+", assessment["summary"])
        self.assertIn("48:35", assessment["load_interpretation"])
        self.assertIn("snittpuls 107", assessment["load_interpretation"])
        self.assertIn(
            "Strava klassade 48:35 av totalt 1:35:18 som rörelsetid",
            public_text,
        )
        self.assertNotIn("session_duration", public_text)
        self.assertNotIn("moving_time", public_text)
        self.assertNotIn("non_moving_time", public_text)
        self.assertNotIn("elapsed_time", public_text)
        self.assertNotIn("5718s", public_text)
        self.assertNotIn("2915s", public_text)
        self.assertNotIn("korta icke-rörelseperioder", public_text)

    def test_support_activity_text_humanizes_referenced_enduro_provider_fields(self):
        result = {
            "assessment": {
                "summary": "Styrkepass efter Enduro.",
                "load_interpretation": (
                    "Enduron var huvudbelastningen (5718 s session_duration); "
                    "moving_time 2915s beskriver inte hela passet."
                ),
                "confidence": "medium",
                "facts": [],
                "interpretations": [],
                "unknowns": [],
            },
            "plan_action": {
                "action": "keep",
                "target_date": "2026-09-08",
                "reason": "Behåll planen.",
                "recommendation": "Behåll tröskelpasset.",
            },
        }
        guarded = guard_result(
            result,
            latest_date="2026-09-07",
            local_date="2026-09-07",
            plan_comparison={},
            activity={"sport_type": "WeightTraining"},
        )
        text = guarded["assessment"]["load_interpretation"]
        self.assertIn("1:35:18 total tid", text)
        self.assertIn("48:35 rörelsetid", text)
        self.assertNotIn("session_duration", text)
        self.assertNotIn("moving_time", text)
        self.assertNotIn("5718 s", text)
        self.assertNotIn("2915s", text)


if __name__ == "__main__":
    unittest.main()
