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


if __name__ == "__main__":
    unittest.main()
