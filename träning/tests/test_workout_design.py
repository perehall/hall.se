#!/usr/bin/env python3
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


def strategy():
    return {
        "current_mesocycle": {
            "id": "meso-test",
            "contract": {
                "primary": ["run_threshold", "run_hill_quality"],
                "secondary": ["mtb_technical", "mtb_aerobic"],
                "maintenance": ["swim_aerobic", "swim_technique"],
                "protected_capacity": ["strength_core"],
                "external_load": ["enduro_technical"],
            },
        }
    }


def swim_day():
    return {
        "date": "2026-09-09",
        "sport": "swim",
        "priority_role": "flex",
        "stimuli": ["swim_aerobic", "swim_technique"],
        "mesocycle_id": "meso-test",
        "microcycle_id": "meso-test:mc3",
        "microcycle_slot": "swim_support",
        "reason": "Aerob simvolym med låg mekanisk kostnad.",
        "development_focus": "Stabil kroppslinje och kontrollerad rotation.",
        "watch_workout": {
            "planned_distance_m": 3200,
            "blocks": [
                {
                    "name": "Insim",
                    "steps": [
                        {
                            "kind": "swim",
                            "text": "Lugn insim",
                            "distance_m": 400,
                            "intensity": "warmup",
                        }
                    ],
                },
                {
                    "name": "Kroppslinje",
                    "repeat": 6,
                    "steps": [
                        {
                            "kind": "swim",
                            "text": "Stabil linje, kontrollerad rotation",
                            "distance_m": 50,
                            "intensity": "active",
                        },
                        {"kind": "rest", "duration_s": 15},
                    ],
                },
                {
                    "name": "Aerob",
                    "repeat": 4,
                    "steps": [
                        {
                            "kind": "swim",
                            "text": "Stadigt aerob med stabil kroppslinje",
                            "distance_m": 500,
                            "intensity": "active",
                        },
                        {"kind": "rest", "duration_s": 30},
                    ],
                },
                {
                    "name": "Frekvens",
                    "repeat": 6,
                    "steps": [
                        {
                            "kind": "swim",
                            "text": "Avslappnad frekvens med bibehållen linje",
                            "distance_m": 50,
                            "intensity": "active",
                        },
                        {"kind": "rest", "duration_s": 15},
                    ],
                },
                {
                    "name": "Nedvarvning",
                    "steps": [
                        {
                            "kind": "swim",
                            "text": "Mycket lugnt",
                            "distance_m": 200,
                            "intensity": "cooldown",
                        }
                    ],
                },
            ],
        },
        "dose_options": [
            {
                "id": "swim-support-3200",
                "kind": "structured",
                "value": 3200,
                "session": "Simning · 3 200 m · aerob/teknik",
                "intent": "Etablerad stöddos.",
            }
        ],
        "baseline_option_id": "swim-support-3200",
        "dose_resolution": {
            "state": "baseline",
            "kind": "structured",
            "value": 3200,
            "option_id": "swim-support-3200",
        },
    }


def threshold_day():
    return {
        "date": "2026-09-08",
        "sport": "run",
        "priority_role": "anchor",
        "stimuli": ["run_threshold"],
        "mesocycle_id": "meso-test",
        "microcycle_id": "meso-test:mc3",
        "microcycle_slot": "run_threshold",
        "reason": "Mesocykelns första prioriterade löpstimulus.",
        "development_focus": "Jämn, kontrollerad tröskel.",
        "dose_options": [
            {
                "id": "run-threshold-3x8",
                "kind": "structured",
                "value": 24,
                "session": "Löpning · kontrollerad tröskel · 3 × 8 min / 90 s jogg",
                "intent": "Demonstrerat golv.",
            },
            {
                "id": "run-threshold-3x10",
                "kind": "structured",
                "value": 30,
                "session": "Löpning · kontrollerad tröskel · 3 × 10 min / 90 s jogg",
                "intent": "Planerat progressionssteg.",
            },
        ],
        "development_progression": {
            "demonstrated_floor_option_id": "run-threshold-3x8",
        },
        "development_step": {
            "microcycle": 3,
            "option_id": "run-threshold-3x10",
            "relation": "progress",
            "reason": "Öka kontrollerad arbetstid från 24 till 30 minuter.",
        },
        "baseline_option_id": "run-threshold-3x10",
        "dose_resolution": {
            "state": "baseline",
            "kind": "structured",
            "value": 30,
            "option_id": "run-threshold-3x10",
        },
    }


def hill_day():
    return {
        "date": "2026-09-11",
        "sport": "run",
        "priority_role": "anchor",
        "stimuli": ["run_hill_quality"],
        "mesocycle_id": "meso-test",
        "microcycle_id": "meso-test:mc3",
        "microcycle_slot": "run_hill_quality",
        "reason": "Mesocykelns andra prioriterade löpstimulus.",
        "development_focus": "Kraftfull men kontrollerad löpning med bibehållen mekanik.",
        "dose_options": [
            {
                "id": "run-hill-3x6x150",
                "kind": "structured",
                "value": 18,
                "session": "Löpning · backkvalitet · 15 min lugnt + 3 × 6 × 150 m / lugn joggvila + 10 min lugnt",
                "intent": "Demonstrerat volymgolv.",
            },
            {
                "id": "run-hill-3x7x150",
                "kind": "structured",
                "value": 21,
                "session": "Löpning · backkvalitet · 15 min lugnt + 3 × 7 × 150 m / lugn joggvila + 10 min lugnt",
                "intent": "Planerat progressionssteg.",
            },
        ],
        "development_progression": {
            "demonstrated_floor_option_id": "run-hill-3x6x150",
        },
        "development_step": {
            "microcycle": 3,
            "option_id": "run-hill-3x7x150",
            "relation": "progress",
            "reason": "Öka arbetsrepetitionerna från 18 till 21.",
        },
        "baseline_option_id": "run-hill-3x7x150",
        "dose_resolution": {
            "state": "baseline",
            "kind": "structured",
            "value": 21,
            "option_id": "run-hill-3x7x150",
        },
    }


class WorkoutDesignTests(unittest.TestCase):
    def test_swim_is_a_full_executable_3200m_recipe(self):
        day = swim_day()
        document = {"days": [day], "strength_template": []}
        materialized = materialize_document(document, strategy())
        day = materialized["days"][0]
        candidate = selected_candidate(day)
        prescription = candidate["prescription"]

        self.assertEqual(materialized["workout_design_schema_version"], 1)
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
        self.assertTrue(validate_workout_design(day, "simning"))

    def test_threshold_progression_selects_current_microcycle_step(self):
        day = threshold_day()
        design = build_workout_design(day, {"days": [day]}, strategy())
        day["workout_design"] = design
        candidate = selected_candidate(day)
        work = candidate["prescription"]["blocks"][0]["work"]

        self.assertEqual(candidate["id"], "run-threshold-3x10")
        self.assertEqual(work["repetitions"], 3)
        self.assertEqual(work["duration_s"], 600)
        self.assertEqual(work["total_work_s"], 1800)
        self.assertEqual(
            design["progression_from_previous"]["relation"],
            "progress",
        )
        self.assertTrue(validate_workout_design(day, "tröskel"))

    def test_hill_quality_is_executable_not_just_a_focus_sentence(self):
        day = hill_day()
        design = build_workout_design(day, {"days": [day]}, strategy())
        day["workout_design"] = design
        candidate = selected_candidate(day)
        blocks = candidate["prescription"]["blocks"]
        quality = next(block for block in blocks if block["name"] == "Backkvalitet")

        self.assertEqual(candidate["id"], "run-hill-3x7x150")
        self.assertEqual(quality["work"]["sets"], 3)
        self.assertEqual(quality["work"]["repetitions_per_set"], 7)
        self.assertEqual(quality["work"]["distance_m"], 150)
        self.assertEqual(quality["work"]["total_repetitions"], 21)

    def test_near_term_reduction_reselects_only_preapproved_candidate(self):
        day = threshold_day()
        day["session"] = "Löpning · kontrollerad tröskel · 3 × 8 min / 90 s jogg"
        day["dose_resolution"] = {
            "state": "resolved",
            "kind": "structured",
            "value": 24,
            "option_id": "run-threshold-3x8",
            "source": "near_term_ai_revision",
            "basis": "Konservativ reduktion efter faktisk närbelastning.",
        }

        design = build_workout_design(day, {"days": [day]}, strategy())
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

    def test_candidates_keep_same_stimulus_and_ignore_arbitrary_alternative_sport(self):
        day = swim_day()
        day["alternative_sports"] = ["swimrun"]
        design = build_workout_design(day, {"days": [day]}, strategy())

        for candidate in design["candidates"]:
            self.assertEqual(candidate["stimuli"], day["stimuli"])
            self.assertNotIn("swimrun", candidate["stimuli"])

    def test_quality_session_fails_closed_without_executable_prescription(self):
        day = hill_day()
        day["workout_design"] = build_workout_design(day, {"days": [day]}, strategy())
        selected = selected_candidate(day)
        selected["prescription"] = {
            "executable": False,
            "completeness": "partial",
            "blocks": [],
        }
        with self.assertRaises(WorkoutDesignError):
            validate_workout_design(day, "backkvalitet")


if __name__ == "__main__":
    unittest.main()
