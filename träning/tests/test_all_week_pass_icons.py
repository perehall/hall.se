#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_all_week_pass_icons import decorate_page, verify_page  # noqa: E402


class AllWeekPassIconsTests(unittest.TestCase):
    def registry(self):
        return {
            "run": {"viewBox": "0 0 24 24", "path": "M1 1h22v22H1z"},
            "swim": {"viewBox": "0 0 24 24", "path": "M2 2h20v20H2z"},
            "bike": {"viewBox": "0 0 24 24", "path": "M3 3h18v18H3z"},
            "enduro": {"viewBox": "0 0 24 24", "path": "M4 4h16v16H4z"},
            "strength": {"viewBox": "0 0 24 24", "path": "M5 5h14v14H5z"},
        }

    def history_page(self):
        return """<html><head><style></style></head><body>
<div class="day workout-card-v2">
  <div class="daytop"></div>
  <div class="session">Enduroskola + styrka · styrkan efter enduron</div>
</div>
<div class="day workout-card-v2">
  <div class="daytop"></div>
  <div class="session">Löpning · kontrollerad tröskel</div>
</div>
<div class="day workout-card-v2">
  <div class="daytop"></div>
  <div class="session">Vilodag</div>
</div>
</body></html>"""

    def history_days(self):
        return [
            {
                "date": "2026-09-14",
                "sport": "enduro",
                "session": "Enduroskola + styrka · styrkan efter enduron",
            },
            {
                "date": "2026-09-15",
                "sport": "run",
                "session": "Löpning · kontrollerad tröskel",
            },
            {
                "date": "2026-09-16",
                "sport": "open",
                "session": "Vilodag",
            },
        ]

    def future_page(self):
        return """<html><head><style></style></head><body>
<div class="day workout-card-v2" id="dag-2026-09-29">
  <div class="daytop"></div>
  <div class="session">Simning · 3 200 m · aerob/teknik</div>
</div>
<div class="day workout-card-v2" id="dag-2026-09-30">
  <div class="daytop"></div>
  <div class="session">Löpning · kontrollerad tröskel</div>
</div>
</body></html>"""

    def future_days(self):
        return [
            {
                "date": "2026-09-29",
                "sport": "swim",
                "session": "Simning · 3 200 m · aerob/teknik",
            },
            {
                "date": "2026-09-30",
                "sport": "run",
                "session": "Löpning · kontrollerad tröskel",
            },
        ]

    def current_page(self):
        return """<html><head><style></style></head><body>
<div class="day completed-day-simplified" id="dag-2026-09-22">
  <div class="completed-day-title"><span><svg class="sport-icon icon-run"></svg><span>Löpning · tröskel</span></span></div>
</div>
<div class="day future-workout-applied" id="dag-2026-09-25">
  <div class="future-workout-title"><svg class="sport-icon icon-swim"></svg><span>Simning · 4 000 m</span></div>
</div>
</body></html>"""

    def current_days(self):
        return [
            {
                "date": "2026-09-22",
                "sport": "run",
                "session": "Löpning · tröskel",
            },
            {
                "date": "2026-09-25",
                "sport": "swim",
                "session": "Simning · 4 000 m",
            },
        ]

    def test_history_gets_icons_and_combo_gets_both(self):
        rendered, changed = decorate_page(
            self.history_page(),
            self.history_days(),
            self.registry(),
        )
        verify_page(rendered, self.history_days())

        self.assertEqual(changed, 2)
        self.assertIn('data-week-pass-icons="enduro,strength"', rendered)
        self.assertIn('class="sport-icon icon-enduro"', rendered)
        self.assertIn('class="sport-icon icon-strength"', rendered)
        self.assertIn('data-week-pass-icons="run"', rendered)
        self.assertNotIn('data-week-pass-icons="open"', rendered)
        self.assertIn("all-week-pass-icons-v1", rendered)

    def test_future_gets_icons_by_date(self):
        rendered, changed = decorate_page(
            self.future_page(),
            self.future_days(),
            self.registry(),
        )
        verify_page(rendered, self.future_days())

        self.assertEqual(changed, 2)
        self.assertIn('data-week-pass-icons="swim"', rendered)
        self.assertIn('data-week-pass-icons="run"', rendered)

    def test_current_owned_icons_are_verified_not_duplicated(self):
        rendered, changed = decorate_page(
            self.current_page(),
            self.current_days(),
            self.registry(),
        )
        verify_page(rendered, self.current_days())

        self.assertEqual(changed, 0)
        self.assertEqual(rendered.count('class="sport-icon icon-run"'), 1)
        self.assertEqual(rendered.count('class="sport-icon icon-swim"'), 1)

    def test_transform_is_idempotent(self):
        once, changed = decorate_page(
            self.history_page(),
            self.history_days(),
            self.registry(),
        )
        twice, changed_again = decorate_page(
            once,
            self.history_days(),
            self.registry(),
        )
        self.assertEqual(changed, 2)
        self.assertEqual(changed_again, 0)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
