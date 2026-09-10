import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "finalize_workout_history.py"
spec = importlib.util.spec_from_file_location("workout_history", MODULE)
workout_history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workout_history)


class WorkoutHistoryTests(unittest.TestCase):
    def test_remove_marked_div_removes_whole_nested_completed_block(self):
        segment = (
            '<div class="day">'
            '<div class="swim-workout">planen visas här</div>'
            '<div class="workout-history" data-workout-history="swim-1">'
            '<div class="workout-history-label">Genomfört simpass · passupplägg</div>'
            '<div class="swim-set-list"><div class="swim-set-row">4 × 500 m</div></div>'
            '</div>'
            '<div class="pass">Simning · 3,20 km</div>'
            '</div>'
        )
        cleaned, changed = workout_history.remove_marked_div(
            segment, 'data-workout-history="swim-1"'
        )
        self.assertTrue(changed)
        self.assertNotIn("workout-history", cleaned)
        self.assertNotIn("Genomfört simpass · passupplägg", cleaned)
        self.assertIn("planen visas här", cleaned)
        self.assertIn("Simning · 3,20 km", cleaned)

    def test_remove_marked_div_is_noop_when_marker_is_absent(self):
        segment = '<div class="day"><div class="pass">Simning</div></div>'
        cleaned, changed = workout_history.remove_marked_div(
            segment, 'data-workout-history="missing"'
        )
        self.assertFalse(changed)
        self.assertEqual(cleaned, segment)


if __name__ == "__main__":
    unittest.main()
