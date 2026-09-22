#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_activity_semantics import apply_semantics  # noqa: E402
from training_input import (  # noqa: E402
    apply_to_documents,
    deterministic_operation,
    validate_payload,
)


class TrainingInputTests(unittest.TestCase):
    def activities(self):
        return {
            "activities": [
                {
                    "id": 123,
                    "sport_type": "Run",
                    "display_label": "Löpning · tröskel",
                    "start_date_local": "2026-09-21T18:00:00+02:00",
                }
            ]
        }

    def test_feedback_persists_structured_quick_input_as_user_report(self):
        overrides = {"schema_version": 1, "overrides": {}}
        updated, operation = apply_to_documents(
            {
                "operation": "ADD_FEEDBACK",
                "activity_id": 123,
                "text": "",
                "rpe": 6,
                "feeling": ["fresh", "could_do_more"],
                "event_key": "training-input:0123456789abcdef01234567",
            },
            self.activities(),
            overrides,
        )
        self.assertEqual(operation, "ADD_FEEDBACK")
        override = updated["overrides"]["123"]
        report = override["user_report"]
        self.assertIn("RPE 6/10", report)
        self.assertIn("Pigg", report)
        self.assertIn("Kunde gjort mer", report)
        self.assertEqual(override["sport"], "Run")
        self.assertEqual(override["classification"], "training")
        self.assertEqual(override["source_sport_type"], "Run")
        self.assertEqual(
            override["last_training_input_event_key"],
            "training-input:0123456789abcdef01234567",
        )
        self.assertEqual(
            override["training_input_event_keys"],
            ["training-input:0123456789abcdef01234567"],
        )
        self.assertEqual(
            override["training_feedback"],
            {
                "text": "",
                "rpe": 6,
                "feeling": ["fresh", "could_do_more"],
                "operation": "ADD_FEEDBACK",
                "event_key": "training-input:0123456789abcdef01234567",
                "submitted_at": "",
            },
        )

        # Regression: the GUI-generated override must be directly consumable by
        # the canonical semantic normalizer; this is the next pipeline stage.
        state = self.activities()
        apply_semantics(state, updated, prompt_signature="x" * 64)
        activity = state["activities"][0]
        self.assertEqual(activity["classification"], "training")
        self.assertEqual(activity["user_report"], report)

    def test_feedback_event_history_keeps_recent_keys_without_duplicates(self):
        overrides = {
            "schema_version": 1,
            "overrides": {
                "123": {
                    "training_input_event_keys": [
                        "training-input:aaaaaaaaaaaaaaaaaaaaaaaa"
                    ],
                    "last_training_input_event_key": "training-input:aaaaaaaaaaaaaaaaaaaaaaaa",
                }
            },
        }
        updated, _ = apply_to_documents(
            {
                "operation": "ADD_FEEDBACK",
                "activity_id": 123,
                "text": "Ny feedback.",
                "rpe": None,
                "feeling": [],
                "event_key": "training-input:bbbbbbbbbbbbbbbbbbbbbbbb",
            },
            self.activities(),
            overrides,
        )
        self.assertEqual(
            updated["overrides"]["123"]["training_input_event_keys"],
            [
                "training-input:aaaaaaaaaaaaaaaaaaaaaaaa",
                "training-input:bbbbbbbbbbbbbbbbbbbbbbbb",
            ],
        )

    def test_edit_replaces_previous_gui_feedback_in_user_report(self):
        first, _ = apply_to_documents(
            {
                "operation": "ADD_FEEDBACK",
                "activity_id": 123,
                "text": "Första kommentaren.",
                "rpe": 4,
                "feeling": ["fresh"],
                "event_key": "training-input:aaaaaaaaaaaaaaaaaaaaaaaa",
            },
            self.activities(),
            {"schema_version": 1, "overrides": {}},
        )
        second, _ = apply_to_documents(
            {
                "operation": "ADD_FEEDBACK",
                "activity_id": 123,
                "text": "Korrigerad kommentar.",
                "rpe": 6,
                "feeling": ["heavy_legs"],
                "event_key": "training-input:bbbbbbbbbbbbbbbbbbbbbbbb",
            },
            self.activities(),
            first,
        )
        report = second["overrides"]["123"]["user_report"]
        self.assertNotIn("Första kommentaren.", report)
        self.assertNotIn("RPE 4/10", report)
        self.assertIn("Korrigerad kommentar.", report)
        self.assertIn("RPE 6/10", report)
        self.assertIn("Tunga ben", report)

    def test_legacy_gui_feedback_is_replaced_on_first_edit(self):
        legacy = {
            "schema_version": 1,
            "overrides": {
                "123": {
                    "sport": "Run",
                    "classification": "training",
                    "display_label": "Löpning",
                    "source_sport_type": "Run",
                    "user_report": "Gamla kommentaren. RPE 4/10. Känsla: Pigg.",
                    "last_training_input_event_key": "training-input:aaaaaaaaaaaaaaaaaaaaaaaa",
                }
            },
        }
        updated, _ = apply_to_documents(
            {
                "operation": "ADD_FEEDBACK",
                "activity_id": 123,
                "text": "Ny kommentar.",
                "rpe": 8,
                "feeling": ["tired"],
                "event_key": "training-input:bbbbbbbbbbbbbbbbbbbbbbbb",
            },
            self.activities(),
            legacy,
        )
        report = updated["overrides"]["123"]["user_report"]
        self.assertNotIn("Gamla kommentaren.", report)
        self.assertNotIn("RPE 4/10", report)
        self.assertIn("Ny kommentar.", report)
        self.assertIn("RPE 8/10", report)
        self.assertIn("Trött", report)

    def test_legacy_multiple_gui_submissions_replace_only_current_segment(self):
        legacy = {
            "schema_version": 1,
            "overrides": {
                "123": {
                    "sport": "Run",
                    "classification": "training",
                    "display_label": "Löpning",
                    "source_sport_type": "Run",
                    "user_report": (
                        "Första kommentaren. RPE 4/10. Känsla: Pigg. "
                        "Senaste kommentaren. RPE 6/10."
                    ),
                    "last_training_input_event_key": "training-input:aaaaaaaaaaaaaaaaaaaaaaaa",
                }
            },
        }
        updated, _ = apply_to_documents(
            {
                "operation": "ADD_FEEDBACK",
                "activity_id": 123,
                "text": "Korrigerad senaste kommentar.",
                "rpe": 8,
                "feeling": ["tired"],
                "event_key": "training-input:bbbbbbbbbbbbbbbbbbbbbbbb",
            },
            self.activities(),
            legacy,
        )
        report = updated["overrides"]["123"]["user_report"]
        self.assertIn("Första kommentaren.", report)
        self.assertNotIn("Senaste kommentaren.", report)
        self.assertIn("Korrigerad senaste kommentar.", report)
        self.assertIn("RPE 8/10", report)

    def test_natural_language_can_only_choose_allowlisted_operation_and_raw_text_is_preserved(self):
        raw = "Blev 4 × 8 i stället för 3 × 10. Kändes kontrollerat."
        updated, operation = apply_to_documents(
            {
                "operation": "NATURAL_LANGUAGE",
                "activity_id": 123,
                "text": raw,
                "rpe": None,
                "feeling": [],
            },
            self.activities(),
            {
                "schema_version": 1,
                "overrides": {"123": {"user_report": "Tidigare kommentar."}},
            },
            classify_fn=lambda payload, activity: "UPDATE_COMPLETED_WORKOUT",
        )
        self.assertEqual(operation, "UPDATE_COMPLETED_WORKOUT")
        self.assertIn("Tidigare kommentar.", updated["overrides"]["123"]["user_report"])
        self.assertIn(raw, updated["overrides"]["123"]["user_report"])

    def test_spontaneous_operation_marks_activity_separate_from_plan(self):
        updated, operation = apply_to_documents(
            {
                "operation": "ADD_SPONTANEOUS_WORKOUT",
                "activity_id": 123,
                "text": "Spontant extra pass.",
                "rpe": None,
                "feeling": [],
            },
            self.activities(),
            {"schema_version": 1, "overrides": {}},
        )
        self.assertEqual(operation, "ADD_SPONTANEOUS_WORKOUT")
        self.assertEqual(updated["overrides"]["123"]["plan_relation"], "separate")

    def test_unknown_activity_fails_closed(self):
        with self.assertRaises(RuntimeError):
            apply_to_documents(
                {
                    "operation": "ADD_FEEDBACK",
                    "activity_id": 999,
                    "text": "Pigg.",
                    "rpe": None,
                    "feeling": [],
                },
                self.activities(),
                {"schema_version": 1, "overrides": {}},
            )

    def test_deterministic_fallback_detects_pain_and_completed_workout_change(self):
        self.assertEqual(
            deterministic_operation({"text": "Fick ont i vaden", "feeling": []}),
            "REPORT_PAIN",
        )
        self.assertEqual(
            deterministic_operation({"text": "Blev 4x8 i stället för 3x10", "feeling": []}),
            "UPDATE_COMPLETED_WORKOUT",
        )

    def test_payload_rejects_malformed_event_key(self):
        with self.assertRaises(RuntimeError):
            validate_payload(
                {
                    "operation": "ADD_FEEDBACK",
                    "activity_id": 123,
                    "text": "Bra.",
                    "rpe": 5,
                    "feeling": [],
                    "event_key": "training-input:not-a-valid-key",
                }
            )

    def test_payload_rejects_unknown_fields(self):
        with self.assertRaises(RuntimeError):
            validate_payload(
                {
                    "operation": "ADD_FEEDBACK",
                    "activity_id": 123,
                    "text": "Bra.",
                    "rpe": 5,
                    "feeling": [],
                    "plan_change": "do not allow",
                }
            )


if __name__ == "__main__":
    unittest.main()
