#!/usr/bin/env python3
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workout_design import (  # noqa: E402
    MAX_CANDIDATES,
    WorkoutDesignError,
    build_workout_design,
    materialize_document,
    selected_candidate,
    validate_workout_design,
)


class WorkoutDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))
        cls.strategy = json.loads(
            (ROOT / "data" / "training_strategy.json").read_text(encoding="utf-8")
        )
        cls.materialized = materialize_document(cls.plan, cls.strategy)

    def day(self, date):
        return next(day for day in self.materialized["days"] if day["date"] == date)

    def test_current_swim_is_a_full_executable_3200m_recipe(self):
        day = self.day("2026-09-09")
        candidate = selected_candidate(day)
        prescription = candidate["prescription"]

        self.assertEqual(day["workout_design"]["objective"]["mesocycle_role"], "maintenance")
        self.assertEqual(candidate["id"], "swim-support-3200")
        self.assertTrue(prescription["executable"])
        self.assertEqual(prescription["completeness"], "full")
        self.assertEqual(prescription["total_distance_m"], 3200)
        self.assertEqual(len(prescription["blocks"]), 5)
        self.assertEqual(prescription["blocks"][1]["work"]["repetitions"], 6)
        self.assertEqual(prescription["blocks"][1]["work"]["distance_m"], 50)
        self.assertEqual(prescription["blocks"][2]["work"]["repetitions"], 4)
        self.assertEqual(prescription["blocks"][2]["work"]["distance_m"], 500)
        self.assertTrue(validate_workout_design(day, "onsdag"))

    def test_threshold_progression_selects_current_microcycle_step(self):
        day = self.day("2026-09-08")
        candidate = selected_candidate(day)
        work = candidate["prescription"]["blocks"][0]["work"]

        self.assertEqual(candidate["id"], "run-threshold-3x10")
        self.assertEqual(work["repetitions"], 3)
        self.assertEqual(work["duration_s"], 600)
        self.assertEqual(work["total_work_s"], 1800)
        self.assertEqual(
            day["workout_design"]["progression_from_previous"]["relation"],
            "progress",
        )

    def test_hill_quality_is_executable_not_just_a_focus_sentence(self):
        day = self.day("2026-09-11")
        candidate = selected_candidate(day)
        blocks = candidate["prescription"]["blocks"]
        quality = next(block for block in blocks if block["name"] == "Backkvalitet")

        self.assertEqual(candidate["id"], "run-hill-3x7x150")
        self.assertEqual(quality["work"]["sets"], 3)
        self.assertEqual(quality["work"]["repetitions_per_set"], 7)
        self.assertEqual(quality["work"]["distance_m"], 150)
        self.assertEqual(quality["work"]["total_repetitions"], 21)

    def test_near_term_reduction_reselects_only_preapproved_candidate(self):
        source_day = next(day for day in self.plan["days"] if day["date"] == "2026-09-08")
        day = copy.deepcopy(source_day)
        day["session"] = "Löpning · kontrollerad tröskel · 3 × 8 min / 90 s jogg"
        day["dose_resolution"] = {
            "state": "resolved",
            "kind": "structured",
            "value": 24,
            "option_id": "run-threshold-3x8",
            "source": "near_term_ai_revision",
            "basis": "Konservativ reduktion efter faktisk närbelastning.",
        }

        design = build_workout_design(day, self.plan, self.strategy)
        self.assertEqual(design["selected_candidate_id"], "run-threshold-3x8")
        self.assertEqual(
            design["selection"]["reason_for_today"],
            "Konservativ reduktion efter faktisk närbelastning.",
        )
        self.assertLessEqual(len(design["candidates"]), MAX_CANDIDATES)
        self.assertTrue(
            all(
                candidate["dose_option_id"]
                in {option["id"] for option in day["dose_options"]}
                for candidate in design["candidates"]
            )
        )

    def test_candidates_are_same_day_stimulus_not_arbitrary_alternative_sports(self):
        day = self.day("2026-09-09")
        design = day["workout_design"]
        for candidate in design["candidates"]:
            self.assertEqual(candidate["stimuli"], day["stimuli"])
            self.assertNotIn("swimrun", candidate["stimuli"])

    def test_quality_session_fails_closed_without_executable_prescription(self):
        day = copy.deepcopy(self.day("2026-09-11"))
        selected = selected_candidate(day)
        selected["prescription"] = {
            "executable": False,
            "completeness": "partial",
            "blocks": [],
        }
        with self.assertRaises(WorkoutDesignError):
            validate_workout_design(day, "fredag")


if __name__ == "__main__":
    unittest.main()
