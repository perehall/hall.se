#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.presentation.cutover import (  # noqa: E402
    SURFACES,
    assert_contract_complete,
    blocker_keys,
    cutover_ready,
    surface_map,
)


class CutoverContractTests(unittest.TestCase):
    def test_contract_is_unique_and_explicit(self):
        assert_contract_complete()
        mapping = surface_map()
        self.assertEqual(len(mapping), len(SURFACES))
        self.assertTrue(all(surface.rationale.strip() for surface in SURFACES))

    def test_current_cutover_is_blocked_by_retained_user_surfaces(self):
        self.assertFalse(cutover_ready())
        self.assertEqual(
            set(blocker_keys()),
            {
                "device_sync_status",
                "page_shell",
                "goal_link",
                "system_reference_tools",
            },
        )

    def test_goal_page_and_backend_status_are_explicitly_separate(self):
        mapping = surface_map()
        self.assertEqual(mapping["goal_page"].state, "separate")
        self.assertEqual(mapping["backend_status"].state, "separate")

    def test_legacy_card_layers_are_not_cutover_requirements(self):
        self.assertEqual(surface_map()["legacy_card_layers"].state, "retire")


if __name__ == "__main__":
    unittest.main()
