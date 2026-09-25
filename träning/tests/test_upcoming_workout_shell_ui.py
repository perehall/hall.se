#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_upcoming_workout_shell_ui import apply_shell, validate_page  # noqa: E402


class UpcomingWorkoutShellUiTests(unittest.TestCase):
    def plan(self):
        return {
            "days": [
                {
                    "date": "2026-09-25",
                    "sport": "swim",
                    "status": "preliminary",
                    "session": "Simning · 4 000 m · aerob + kontrollerad tröskel",
                    "development_focus": "Bibehåll teknisk kvalitet genom hela passet.",
                    "reason": "Tisdagens tröskelstimulus är redan genomfört. Simningen bevarar veckans andra simexponering.",
                },
                {
                    "date": "2026-09-26",
                    "sport": "open",
                    "status": "open",
                    "session": "Ingen planerad träning",
                    "reason": "Vilodag.",
                },
                {
                    "date": "2026-09-27",
                    "sport": "run",
                    "status": "preliminary",
                    "session": "Löpning · lugn distans · 120 min",
                    "development_focus": "Lugn hållbar löpning. Tålighet byggs genom kontinuitet och absorberbar tid, inte fartjakt.",
                    "reason": "Långt lugnt löppass för löptålighet; placerat ≥48 h efter tröskel för återhämtning och kvalitet. Valet utgår från ett observerat värde 119.767 i athlete_state.",
                },
            ]
        }

    def page(self):
        return """<html><head><style></style></head><body>
<div class="day decision-horizon workout-card-v2 card-v2-today" id="dag-2026-09-25">
  <div class="daytop"><div class="day-date-line"><span class="dow">Fredag</span><span class="date">25 sep</span></div><div class="badge conditional">Kan ändras</div></div>
  <div class="swim-workout"><div class="swim-session-head"><strong>Simning · 4 000 m</strong><span class="swim-meta">aerob + kontrollerad tröskel</span></div></div>
  <div class="workout-prescription"><div class="workout-prescription-head">Passupplägg</div><div class="workout-prescription-row"><span class="workout-prescription-dose">600 m</span><span class="workout-prescription-text">Insim + teknik · utan redskap</span></div><div class="workout-prescription-row"><span class="workout-prescription-dose">4×200 m</span><span class="workout-prescription-text">Kontrollerad tröskel · paddlar + dolme · v 25 s</span></div></div>
  <div class="development-focus"><strong>Fokus:</strong><span>Bibehåll teknisk kvalitet genom hela passet.</span></div>
  <div class="card-v2-footer"><details class="day-why"><summary>Motivering</summary><div class="reason">Tisdagens tröskelstimulus är redan genomfört.</div></details><div class="device-sync-state synced"><svg></svg><span>Klocksync skickad</span></div></div>
</div>
<div class="day decision-horizon workout-card-v2" id="dag-2026-09-26">
  <div class="daytop"><div class="day-date-line"><span class="dow">Lördag</span><span class="date">26 sep</span></div><div class="badge open">Inte bestämt</div></div>
  <div class="session">Vilodag</div>
  <div class="card-v2-footer"><details class="day-why"><summary>Motivering</summary><div class="reason">Ingen träning är planerad.</div></details></div>
</div>
<div class="day decision-horizon workout-card-v2" id="dag-2026-09-27">
  <div class="daytop"><div class="day-date-line"><span class="dow">Söndag</span><span class="date">27 sep</span></div><div class="badge conditional">Kan ändras</div></div>
  <div class="session session-with-icon"><span class="session-text"><strong class="session-title">Löpning · lugn distans</strong><span class="session-meta">120 min</span></span></div>
  <div class="next-weather" data-weather-date="2026-09-27" style="color:#475569"><span class="weather-label">Väder:</span> Klart · 10–17 °C</div>
  <div class="workout-prescription"><div class="workout-prescription-head">Passupplägg</div><div class="workout-prescription-row"><span class="workout-prescription-dose">120 min</span><span class="workout-prescription-text">Lugn hållbar löpning. Tålighet byggs genom kontinuitet och absorberbar tid, inte fartjakt.</span></div></div>
  <div class="development-focus"><strong>Fokus:</strong><span>Lugn hållbar löpning. Tålighet byggs genom kontinuitet och absorberbar tid, inte fartjakt.</span></div>
  <div class="card-v2-footer"><details class="day-why"><summary>Motivering</summary><div class="reason">Långt lugnt löppass för löptålighet; placerat ≥48 h efter tröskel för återhämtning och kvalitet. Valet utgår från ett observerat värde 119.767 i athlete_state.</div></details></div>
</div>
</body></html>"""

    def registry(self):
        return {
            "swim": {"viewBox": "0 0 24 24", "path": "M1 1h22v22H1z"},
            "run": {"viewBox": "0 0 24 24", "path": "M2 2h20v20H2z"},
        }

    def test_all_upcoming_workouts_share_one_action_first_shell(self):
        rendered, changed = apply_shell(
            self.page(),
            self.plan(),
            today="2026-09-25",
            activity_dates=set(),
            registry=self.registry(),
        )
        validate_page(
            rendered,
            self.plan(),
            today="2026-09-25",
            activity_dates=set(),
        )

        self.assertEqual(changed, 2)
        self.assertEqual(rendered.count('class="future-workout-shell"'), 2)
        self.assertIn('data-future-workout-shell="2026-09-25"', rendered)
        self.assertIn('data-future-workout-shell="2026-09-27"', rendered)
        self.assertNotIn('data-future-workout-shell="2026-09-26"', rendered)

        self.assertIn("Simning · 4 000 m", rendered)
        self.assertIn("aerob + kontrollerad tröskel", rendered)
        self.assertIn('<span class="future-workout-label">Pass</span>', rendered)
        self.assertIn("4×200 m", rendered)
        self.assertIn("paddlar + dolme", rendered)
        self.assertIn('<span class="future-workout-label">Fokus</span>', rendered)
        self.assertIn("Plan och motivering", rendered)
        self.assertIn("Tisdagens tröskelstimulus är redan genomfört.", rendered)
        self.assertIn("Klocksync skickad", rendered)

        self.assertIn("Löpning · lugn distans", rendered)
        self.assertIn('<div class="future-workout-meta">120 min</div>', rendered)
        self.assertIn('class="future-workout-weather"', rendered)
        self.assertIn("Klart · 10–17 °C", rendered)

        # Sunday focus is identical to the prescription and must not be repeated.
        run_shell = rendered.split('data-future-workout-shell="2026-09-27"', 1)[1]
        run_shell = run_shell.split('</div></div></div>', 1)[0]
        self.assertNotIn('<span class="future-workout-label">Fokus</span>', run_shell)

        # Internal planning implementation language is clipped from normal detail copy.
        self.assertNotIn("athlete_state", rendered)

    def test_existing_activity_prevents_future_shell_on_same_date(self):
        rendered, changed = apply_shell(
            self.page(),
            self.plan(),
            today="2026-09-25",
            activity_dates={"2026-09-25"},
            registry=self.registry(),
        )
        self.assertEqual(changed, 1)
        self.assertNotIn('data-future-workout-shell="2026-09-25"', rendered)
        self.assertIn('data-future-workout-shell="2026-09-27"', rendered)

    def test_transform_is_idempotent(self):
        once, changed = apply_shell(
            self.page(),
            self.plan(),
            today="2026-09-25",
            activity_dates=set(),
            registry=self.registry(),
        )
        twice, changed_again = apply_shell(
            once,
            self.plan(),
            today="2026-09-25",
            activity_dates=set(),
            registry=self.registry(),
        )
        self.assertEqual(changed, 2)
        self.assertEqual(changed_again, 0)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
