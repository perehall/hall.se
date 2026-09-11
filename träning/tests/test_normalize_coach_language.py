#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_coach_language import (  # noqa: E402
    assert_no_forbidden_visible_terms,
    normalize_state,
    strategy_visible_labels,
    visible_training_language,
)


class NormalizeCoachLanguageTests(unittest.TestCase):
    def test_user_reported_hill_structure_overrides_conflicting_lap_interpretation(self):
        coach = {
            "analyses": [
                {
                    "activity_id": 42,
                    "activity_date": "2026-09-04",
                    "assessment": {
                        "summary": "Backintervaller genomförda som rapporterat: 2×6×150 (reducerad plan); stabilt utan försämring i lapparna.",
                        "load_interpretation": "Lapparna såg jämna ut.",
                        "facts": ["18 lappar registrerades som arbetsdelar."],
                        "interpretations": ["Ingen tydlig försämring mellan lapparna."],
                        "unknowns": [],
                    },
                    "plan_action": {
                        "reason": "Fredagens reducerade backdos genomförd; behåll lördagens stödpass.",
                        "recommendation": "Fortsätt enligt planen.",
                    },
                }
            ]
        }
        activities = {
            "activities": [
                {
                    "id": 42,
                    "user_report": "3 × 6 backintervaller (18 backar totalt).",
                }
            ]
        }
        plan = {
            "days": [
                {
                    "date": "2026-09-04",
                    "dose_resolution": {"kind": "structured", "value": 12},
                }
            ]
        }

        changed = normalize_state(coach, activities, plan)
        assert_no_forbidden_visible_terms(coach)

        self.assertEqual(changed, 1)
        summary = coach["analyses"][0]["assessment"]["summary"]
        reason = coach["analyses"][0]["plan_action"]["reason"]
        self.assertEqual(
            summary,
            "Genomfört: 3 × 6 backintervaller (18 totalt). Stabilt utan försämring i intervallerna",
        )
        self.assertNotIn("2×6×150", summary)
        self.assertIn("18 totalt", reason)
        self.assertIn("planerade omfattningen före passet (12 arbetsintervaller)", reason)
        self.assertNotIn("reducerade backdos genomförd", reason)
        self.assertNotIn("lapparna", str(coach).lower())
        self.assertNotIn("lappar", str(coach).lower())
        self.assertIn("intervallerna", str(coach).lower())
        self.assertIn("18 intervaller", str(coach).lower())

    def test_internal_strategy_key_is_humanized_and_system_phrase_is_rewritten(self):
        strategy = {
            "capability_portfolio": [
                {"key": "enduro_technical", "label": "Enduroteknik"},
                {"key": "run_threshold", "label": "Kontrollerad löptröskel"},
            ]
        }
        labels = strategy_visible_labels(strategy)
        raw = (
            "Passet räknas som faktisk träningsbelastning mot mikrocykelns stimuli för "
            "enduro_technical och påverkar möjligheten att genomföra tisdagens prioriterade "
            "löpstimulus."
        )
        normalized = visible_training_language(raw, labels)
        self.assertEqual(
            normalized,
            "Enduropasset är en del av veckans träningsbelastning. "
            "Därför vägs det in när tisdagens löppass planeras.",
        )
        self.assertNotIn("enduro_technical", normalized)
        self.assertNotIn("löpstimulus", normalized)

    def test_other_strategy_keys_use_canonical_public_label(self):
        labels = strategy_visible_labels(
            {
                "capability_portfolio": [
                    {"key": "run_threshold", "label": "Kontrollerad löptröskel"}
                ]
            }
        )
        self.assertEqual(
            visible_training_language("Nästa fokus är run_threshold.", labels),
            "Nästa fokus är Kontrollerad löptröskel.",
        )

    def test_schema_field_names_are_humanized(self):
        normalized = visible_training_language(
            "session_duration 5718 s, moving_time 2915 s, ingen user_report och dose_resolution vald."
        )
        self.assertEqual(
            normalized,
            "total passduration 5718 s, rörelsetid 2915 s, ingen användarrapport och valt dosalternativ vald.",
        )
        self.assertNotIn("_", normalized)

    def test_rolling_load_alias_is_humanized(self):
        normalized = visible_training_language(
            "rolling_load visar att närbelastningen redan innehåller kvalitet."
        )
        self.assertEqual(
            normalized,
            "närbelastningen visar att närbelastningen redan innehåller kvalitet.",
        )
        self.assertNotIn("rolling_load", normalized)

    def test_provider_activity_type_in_fact_is_humanized(self):
        normalized = visible_training_language(
            "WeightTraining: 27:39 · snittpuls 75,7 · maxpuls 112."
        )
        self.assertEqual(
            normalized,
            "Styrka: 27:39 · snittpuls 75,7 · maxpuls 112.",
        )
        self.assertNotIn("WeightTraining", normalized)

    def test_named_internal_ids_use_public_session_text(self):
        labels = strategy_visible_labels(
            {
                "current_mesocycle": {
                    "id": "run-threshold-hill-4w",
                    "title": "Mesocykel · löptröskel + backkvalitet",
                    "microcycle_template": [
                        {
                            "dose_options": [
                                {
                                    "id": "run-threshold-3x8",
                                    "session": "Löpning · kontrollerad tröskel · 3 × 8 min / 90 s jogg",
                                }
                            ]
                        }
                    ],
                }
            }
        )
        normalized = visible_training_language(
            "Skala ner till alternativ run-threshold-3x8.",
            labels,
        )
        self.assertEqual(
            normalized,
            "Skala ner till alternativ Löpning · kontrollerad tröskel · 3 × 8 min / 90 s jogg.",
        )
        self.assertNotIn("run-threshold-3x8", normalized)

    def test_visible_output_fails_closed_if_unknown_snake_case_remains(self):
        coach = {
            "analyses": [
                {
                    "assessment": {
                        "summary": "Internt unknown_internal_name läckte ut.",
                        "load_interpretation": "",
                        "facts": [],
                        "interpretations": [],
                        "unknowns": [],
                    },
                    "plan_action": {"reason": "", "recommendation": ""},
                }
            ]
        }
        with self.assertRaisesRegex(RuntimeError, "internt variabelnamn"):
            assert_no_forbidden_visible_terms(coach)

    def test_visible_output_fails_closed_if_raw_provider_fact_label_remains(self):
        coach = {
            "analyses": [
                {
                    "assessment": {
                        "summary": "Neutral.",
                        "load_interpretation": "",
                        "facts": ["WeightTraining: 27:39."],
                        "interpretations": [],
                        "unknowns": [],
                    },
                    "plan_action": {"reason": "", "recommendation": ""},
                }
            ]
        }
        with self.assertRaisesRegex(RuntimeError, "rå aktivitetstyp"):
            assert_no_forbidden_visible_terms(coach)


if __name__ == "__main__":
    unittest.main()
