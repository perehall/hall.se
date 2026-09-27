#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.presentation.public_copy import (  # noqa: E402
    assert_public_copy,
    public_reason,
)


class PublicCopyTests(unittest.TestCase):
    def test_live_style_planner_provenance_is_removed_without_inventing_copy(self):
        raw = (
            "Långt lugnt löppass för löptålighet; placerat ≥48 h efter tröskel "
            "för återhämtning och kvalitet. Valet utgår från ett observerat "
            "värde 119.767 i athlete_state för receptets dosvariabel; värdet "
            "används som kapacitetsfakta, inte som bevis för optimal framtida "
            "belastning. Veckobeslut: establish; materialiserad relation: hold."
        )
        public = public_reason(raw)
        self.assertEqual(
            public,
            "Långt lugnt löppass för löptålighet; placerat ≥48 h efter tröskel "
            "för återhämtning och kvalitet.",
        )
        assert_public_copy(public)

    def test_internal_only_reason_fails_open_to_empty_instead_of_inventing_text(self):
        raw = "athlete_state selected_candidate_id deterministic_constraint"
        self.assertEqual(public_reason(raw), "")

    def test_normal_public_reason_is_preserved(self):
        raw = (
            "Mesocykelns tredje löpstimulus bygger tålighet och kontinuitet. "
            "75 minuter lugnt är grundplan."
        )
        self.assertEqual(public_reason(raw), raw)
        assert_public_copy(public_reason(raw))

    def test_public_reason_is_bounded_for_calm_ui(self):
        raw = " ".join(["Kontrollerad aerob utveckling"] * 30) + "."
        public = public_reason(raw, max_chars=100)
        self.assertLessEqual(len(public), 100)
        self.assertTrue(public.endswith("…"))


if __name__ == "__main__":
    unittest.main()
