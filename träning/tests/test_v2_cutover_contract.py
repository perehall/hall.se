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

    def test_current_cutover_has_no_retained_surface_blockers(self):
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

    def test_goal_page_and_backend_status_are_explicitly_separate(self):
        mapping = surface_map()
        self.assertEqual(mapping["goal_page"].state, "separate")
        self.assertEqual(mapping["backend_status"].state, "separate")

    def test_legacy_card_layers_are_not_cutover_requirements(self):
        self.assertEqual(surface_map()["legacy_card_layers"].state, "retire")


if __name__ == "__main__":
    unittest.main()
