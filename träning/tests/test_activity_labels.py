#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_activity_labels import render_activity_line  # noqa: E402


class ActivityLabelTests(unittest.TestCase):
    def test_normalized_display_label_is_rendered_exactly(self):
        activity = {
            "sport_type": "Run",
            "display_label": "Löpning · grus/asfalt",
            "distance_m": 17158.0,
            "elapsed_time_s": 5459,
            "average_heartrate": 138.9,
            "max_heartrate": 157.0,
        }
        rendered = render_activity_line(activity, activity["display_label"])
        self.assertIn("<strong>Löpning · grus/asfalt</strong>", rendered)
        self.assertIn("17,16 km · 1:30:59 · snittpuls 139 · max 157", rendered)

    def test_raw_sport_label_remains_available_for_exact_replacement(self):
        activity = {
            "sport_type": "Run",
            "distance_m": 5000.0,
            "elapsed_time_s": 1500,
        }
        self.assertIn("<strong>Run</strong>", render_activity_line(activity))


if __name__ == "__main__":
    unittest.main()
