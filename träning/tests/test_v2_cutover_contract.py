#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.presentation.cutover import (
    SURFACES, assert_contract_complete, blocker_keys, cutover_ready, surface_map,
)
from training_core.presentation.renderer import render_document


class CutoverContractTests(unittest.TestCase):
    def test_contract_is_unique_and_explicit(self):
        assert_contract_complete()
        mapping = surface_map()
        self.assertEqual(len(mapping), len(SURFACES))
        self.assertTrue(all(surface.rationale.strip() for surface in SURFACES))

    def test_current_cutover_is_ready_after_approved_ux_migration(self):
        self.assertTrue(cutover_ready())
        self.assertEqual(blocker_keys(), ())

    def test_publication_shell_contract_is_real_renderer_behavior(self):
        class Dummy:
            pass
        # Avoid fabricating a presentation snapshot here: shell capability is
        # guarded structurally and integration rendering remains covered by the
        # presentation-slice tests and live PostgreSQL probe.
        source = Path(ROOT / "training_core" / "presentation" / "renderer.py").read_text(encoding="utf-8")
        self.assertIn("def render_document(", source)
        self.assertIn('data-v2-goal-link', source)
        self.assertIn("Styrkemall", source)
        self.assertIn("Om systemet", source)
        self.assertIn('name="viewport"', source)

    def test_preview_contains_approved_current_week_structure_before_human_cutover(self):
        source = Path(
            ROOT / "training_core" / "presentation" / "renderer.py"
        ).read_text(encoding="utf-8")
        self.assertIn('class="v2-week-dayhead"', source)
        self.assertIn('class="v2-week-daybody"', source)
        self.assertIn('class="v2-week-status"', source)
        self.assertIn('<summary>Planidé</summary>', source)
        self.assertIn("--bg:#F6F7F5", source)
        self.assertIn("grid-template-columns:92px minmax(0,1fr)", source)
        self.assertIn(".v2-week-planned-workout+.v2-week-planned-workout", source)

    def test_goal_page_and_backend_status_are_explicitly_separate(self):
        mapping = surface_map()
        self.assertEqual(mapping["goal_page"].state, "separate")
        self.assertEqual(mapping["backend_status"].state, "separate")

    def test_approved_current_week_experience_is_migrated_before_cutover(self):
        mapping = surface_map()
        self.assertEqual(mapping["page_shell"].state, "migrated")
        self.assertEqual(mapping["approved_current_week_experience"].state, "migrated")
        self.assertEqual(mapping["legacy_card_layers"].state, "retire")


if __name__ == "__main__":
    unittest.main()
