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

        # Regression: the GUI-generated override must be directly consumable by
        # the canonical semantic normalizer; this is the next pipeline stage.
        state = self.activities()
        apply_semantics(state, updated, prompt_signature="x" * 64)
        activity = state["activities"][0]
        self.assertEqual(activity["classification"], "training")
        self.assertEqual(activity["user_report"], report)

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
