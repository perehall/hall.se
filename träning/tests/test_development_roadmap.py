import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from development_roadmap import build_development_roadmap  # noqa: E402
from build_development_page import render_page  # noqa: E402


class DevelopmentRoadmapTests(unittest.TestCase):
    def setUp(self):
        self.strategy = {
            "goal_contract": {
                "goal_hash": "abc",
                "goal_set": [
                    {
                        "id": "allround",
                        "label": "Allroundatlet",
                        "role": "enduring",
                        "type": "development",
                        "horizon": "ongoing",
                    },
                    {
                        "id": "race",
                        "event": "Testlopp",
                        "role": "primary_performance_goal",
                        "type": "performance",
                        "target": "Topp-10",
                        "event_date": "2027-08-14",
                    },
                ],
                "declared_profile_goals": [
                    {"text": "Bli starkare i MTB", "target_date": None, "importance": "equal"}
                ],
                "competition_context": {
                    "goal_id": "race",
                    "event": "Testlopp",
                    "target": "Topp-10",
                    "event_date": "2027-08-14",
                },
            },
            "capability_portfolio": [
                {"key": "run_threshold", "label": "Kontrollerad löptröskel", "mode": "develop"},
                {"key": "strength_core", "label": "Core", "mode": "maintain_develop"},
            ],
            "current_mesocycle": {
                "id": "meso-1",
                "title": "Kontrollerat byggblock",
                "start_date": "2026-09-28",
                "end_date": "2026-10-25",
                "evaluation_date": "2026-10-26",
                "duration_weeks": 4,
                "hypothesis": "Stabil kontinuitet före större progression.",
                "progression_axes": [
                    {
                        "capability": "run_threshold",
                        "axis": "work_duration",
                        "objective": "Öka arbetstid stegvis när responsen stödjer det.",
                    }
                ],
                "goal_contribution": "Utveckla relevant kapacitet utan att tappa bredd.",
                "goal_contributions": [
                    {"goal_id": "allround", "contribution": "Behåll bredd.", "tradeoff": "Ingen."},
                    {"goal_id": "race", "contribution": "Bygg löpkapacitet.", "tradeoff": "Specificitet senare."},
                ],
                "contract": {
                    "primary": ["run_threshold"],
                    "secondary": [],
                    "maintenance": [],
                    "protected_capacity": ["strength_core"],
                    "external_load": [],
                },
                "success_signals": ["Jämförbara pass stödjer fortsatt utveckling."],
                "review_questions": ["Fungerar blocket?"],
            },
        }
        self.policy = {
            "periodization_policy": {
                "microcycle_wave_by_duration": {
                    "4": ["establish", "develop", "develop", "consolidate"]
                },
                "intent_definitions": {
                    "establish": "Etablera.",
                    "develop": "Utveckla.",
                    "consolidate": "Konsolidera.",
                },
            },
            "event_horizon_policy": {
                "specificity_build_review_days": 168,
                "race_specific_review_days": 84,
                "taper_review_days": 21,
                "principle": "Datum är beslutspunkter, inte dosregler.",
                "stages": {
                    "specificity_build": "Bygg specificitet när data stödjer det.",
                    "race_specific": "Öka tävlingsspecificiteten när data stödjer det.",
                    "taper_review": "Ompröva belastningen inför loppet.",
                },
            }
        }
        self.athlete_state = {
            "fact_window": {"end": "2026-09-29"},
            "capability_facts": {
                "run_threshold": {"evidence": [{"date": "2026-09-29"}]}
            },
            "dose_response": {
                "by_capability": {
                    "run_threshold": {
                        "demonstrated_value": 32,
                        "absorbed_value": None,
                        "tolerated_value": None,
                    }
                }
            },
        }

    def test_event_horizon_dates_are_derived_from_policy(self):
        roadmap = build_development_roadmap(self.strategy, self.policy, self.athlete_state)
        items = {row["id"]: row for row in roadmap["timeline"]}
        event = date.fromisoformat("2027-08-14")
        self.assertEqual(items["specificity_build-review"]["date"], (event - timedelta(days=168)).isoformat())
        self.assertEqual(items["race_specific-review"]["date"], (event - timedelta(days=84)).isoformat())
        self.assertEqual(items["taper_review-review"]["date"], (event - timedelta(days=21)).isoformat())
        self.assertEqual(items["goal-event"]["date"], "2027-08-14")

    def test_roadmap_never_turns_review_dates_into_achievement_predictions(self):
        roadmap = build_development_roadmap(self.strategy, self.policy, self.athlete_state)
        self.assertIn("förutsäger inte", roadmap["interpretation_boundary"])
        for item in roadmap["timeline"]:
            if item["kind"] == "decision_window":
                self.assertEqual(item["certainty"], "policy_review_date")

    def test_evidence_distinguishes_demonstrated_from_absorbed(self):
        roadmap = build_development_roadmap(self.strategy, self.policy, self.athlete_state)
        run = next(row for row in roadmap["capabilities"] if row["key"] == "run_threshold")
        self.assertEqual(run["evidence_state"], "demonstrated")
        self.assertIn("inte samma sak", run["evidence_summary"])

    def test_active_block_exposes_progression_wave_and_axes(self):
        roadmap = build_development_roadmap(self.strategy, self.policy, self.athlete_state)
        block = roadmap["active_block"]
        self.assertEqual(
            [row["intent"] for row in block["microcycle_intents"]],
            ["establish", "develop", "develop", "consolidate"],
        )
        self.assertEqual(block["microcycle_intents"][1]["start_date"], "2026-10-05")
        self.assertEqual(block["progression_axes"][0]["axis"], "work_duration")

    def test_declared_profile_goals_remain_visible(self):
        roadmap = build_development_roadmap(self.strategy, self.policy, self.athlete_state)
        self.assertEqual(roadmap["declared_profile_goals"][0]["label"], "Bli starkare i MTB")

    def test_page_explains_statuses_and_keeps_week_plan_separate(self):
        page = render_page(self.strategy, self.policy, self.athlete_state)
        self.assertIn("Mål & utveckling", page)
        self.assertIn("Preliminär beslutspunkt", page)
        self.assertIn("Kapacitetskarta", page)
        self.assertIn("Bli starkare i MTB", page)
        self.assertNotIn('class="v2-week"', page)


if __name__ == "__main__":
    unittest.main()
