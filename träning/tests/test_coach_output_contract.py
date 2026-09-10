import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "enforce_coach_output_contract.py"
spec = importlib.util.spec_from_file_location("contract", MODULE)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class CoachOutputContractTests(unittest.TestCase):
    def test_swim_without_structured_context_is_evidence_limited_and_does_not_repeat_swim(self):
        coach = {"analyses": [{
            "activity_id": 1,
            "activity_date": "2026-09-05",
            "performance_marker_id": None,
            "assessment": {
                "summary": "Mycket långt, kontrollerat simpass med stigande puls och inga tekniska krascher.",
                "load_interpretation": "Hög kardiovaskulär exponering.",
                "confidence": "medium",
                "facts": ["Swim: 4,00 km"],
                "interpretations": ["Tekniken höll ihop fint."],
                "unknowns": ["RPE saknas."],
            },
            "plan_action": {
                "action": "keep",
                "target_date": "2026-09-05",
                "reason": "Allt ser bra ut.",
                "recommendation": "Genomför simningen 3 200 m och styrka/core 25 min; undvik plyometri.",
                "dose_option_id": "",
                "requires_approval": False,
            },
        }]}
        plan = {"days": [{
            "date": "2026-09-05",
            "session": "Simning · 3 200 m · aerob/teknik + styrka/core · 25 min · styrkemall",
        }]}
        activities = {"activities": [{
            "id": 1,
            "sport_type": "Swim",
            "start_date_local": "2026-09-05T14:48:11",
            "distance_m": 4000.0,
            "elapsed_time_s": 4433,
        }]}
        self.assertTrue(contract.enforce_contract(coach, plan, activities))
        analysis = coach["analyses"][0]
        self.assertEqual(
            analysis["assessment"]["summary"],
            "Simningen blev 4 000 m mot planerade 3 200 m (800 m mer).",
        )
        self.assertEqual(
            analysis["assessment"]["load_interpretation"],
            "Ingen setbaserad slutsats används för planändring.",
        )
        self.assertNotIn("tekniska krascher", analysis["assessment"]["summary"].lower())
        self.assertEqual(analysis["assessment"]["confidence"], "low")
        self.assertEqual(
            analysis["plan_action"]["recommendation"],
            "Simningen är genomförd. Återstår enligt dagens plan: styrka/core · 25 min · styrkemall.",
        )

    def test_structured_swim_context_is_not_overwritten_by_missing_performance_marker(self):
        coach = {"analyses": [{
            "activity_id": 3,
            "activity_date": "2026-09-09",
            "performance_marker_id": None,
            "assessment": {
                "summary": "Fyra 500:or låg inom en sekund per 100 m.",
                "load_interpretation": "Ingen ändring av kommande plan behövs.",
                "confidence": "medium",
                "facts": [],
                "interpretations": ["Farten var stabil i 500-meterssetet."],
                "unknowns": [],
            },
            "plan_action": {
                "action": "keep",
                "target_date": "2026-09-10",
                "reason": "Passet ger inget skäl att ändra nästa pass.",
                "recommendation": "Behåll planen.",
                "dose_option_id": "",
                "requires_approval": False,
            },
        }]}
        activities = {"activities": [{
            "id": 3,
            "sport_type": "Swim",
            "distance_m": 3200.0,
            "workout_analysis_context": {
                "swim": {
                    "structured": True,
                    "repeat_sets": [{"repetitions": 4, "distance_per_rep_m": 500.0}],
                }
            },
        }]}
        self.assertFalse(contract.enforce_contract(coach, {"days": []}, activities))
        assessment = coach["analyses"][0]["assessment"]
        self.assertEqual(assessment["summary"], "Fyra 500:or låg inom en sekund per 100 m.")
        self.assertNotIn("setbaserad slutsats", assessment["load_interpretation"].lower())

    def test_machine_stimulus_ids_are_removed_from_all_visible_fields(self):
        coach = {"analyses": [{
            "activity_id": 4,
            "activity_date": "2026-09-09",
            "performance_marker_id": "swim",
            "assessment": {
                "summary": "Passet gav stöd åt sim_aerobic.",
                "load_interpretation": "sim_aerobic kvarstår som stödjande stimulus.",
                "confidence": "medium",
                "facts": ["Stimulus sim_aerobic verifierat i planen."],
                "interpretations": ["sim_technique stöddes också."],
                "unknowns": [],
            },
            "plan_action": {
                "action": "keep",
                "target_date": "2026-09-10",
                "reason": "sim_aerobic kräver ingen ändring.",
                "recommendation": "Behåll planen efter sim_aerobic.",
                "dose_option_id": "",
                "requires_approval": False,
            },
        }]}
        activities = {"activities": [{"id": 4, "sport_type": "Swim"}]}
        self.assertTrue(contract.enforce_contract(coach, {"days": []}, activities))
        visible = str(coach["analyses"][0])
        self.assertNotIn("sim_aerobic", visible)
        self.assertNotIn("sim_technique", visible)
        self.assertIn("aerob simning", visible)
        self.assertIn("simteknik", visible)

    def test_compacts_free_text(self):
        coach = {"analyses": [{
            "activity_id": 2,
            "activity_date": "2026-09-04",
            "performance_marker_id": "run",
            "assessment": {
                "summary": "Första meningen. Andra meningen som inte ska visas.",
                "load_interpretation": "Kort. Mer text.",
                "confidence": "medium",
                "facts": [],
                "interpretations": ["A. Extra.", "B.", "C."],
                "unknowns": ["U1.", "U2.", "U3."],
            },
            "plan_action": {
                "action": "keep",
                "target_date": "",
                "reason": "R1. R2.",
                "recommendation": "Gör A. Gör B. Gör C.",
                "dose_option_id": "",
                "requires_approval": False,
            },
        }]}
        activities = {"activities": [{
            "id": 2,
            "sport_type": "Run",
            "start_date_local": "2026-09-04T18:00:00",
        }]}
        self.assertTrue(contract.enforce_contract(coach, {"days": []}, activities))
        analysis = coach["analyses"][0]
        self.assertEqual(analysis["assessment"]["summary"], "Första meningen.")
        self.assertEqual(len(analysis["assessment"]["interpretations"]), 2)
        self.assertEqual(len(analysis["assessment"]["unknowns"]), 2)
        self.assertEqual(analysis["plan_action"]["recommendation"], "Gör A. Gör B.")


if __name__ == "__main__":
    unittest.main()
