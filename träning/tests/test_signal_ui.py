#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_signal_ui import apply_signal_ui, compact_text  # noqa: E402


class SignalUiTests(unittest.TestCase):
    def test_compact_text_keeps_first_short_sentence(self):
        text = "Gör det lugnt. Detta är en mycket längre förklaring som inte behöver ligga i huvudvyn."
        self.assertEqual(compact_text(text, 25), "Gör det lugnt.")

    def test_signal_hierarchy_moves_stats_down_and_compacts_week(self):
        page = '''<html><style></style><body>
<div class="hero week-focus-card"><h2 class="week-focus-title"><strong>Veckofokus:</strong> Test</h2><details class="week-focus-details"><summary>Planidé</summary><p>Plan.</p></details></div>
<section class="training-brain"><div class="brain-why"><strong>Varför:</strong> Låg mekanisk belastning.</div><div class="brain-note">Beslutet väntar på torsdagens faktiska belastning innan fredagens dos låses.</div></section>
<section class="dashboard" aria-label="Veckoöversikt"><div class="metrics"></div><div class="dashboard-grid"></div><div class="dashboard-card"><div class="dashboard-title">Nästa dagar</div></div></section>
<h2 class="section">Aktuell vecka</h2>
<div class="day" id="dag-2026-08-24"><div class="daytop"></div><div class="session">Löpning</div><div class="reason">Motivering.</div><div class="pass"><div class="pass-title">Automatiskt från Strava</div><div>Data</div></div><div class="coach yoda-v2"><div class="coach-next"><span class="coach-next-label">Nästa steg</span><div>Gammalt råd.</div></div></div><div class="development-focus"><strong>Utvecklingsfokus</strong><span>Fokus.</span></div></div>
<div class="day" id="dag-2026-08-26"><div class="daytop"></div><div class="session">Simning</div><div class="reason">Motivering.</div><div class="development-focus"><strong>Utvecklingsfokus</strong><span>Fokus.</span></div></div>
<div class="day" id="dag-2026-08-30"><div class="daytop"></div><div class="session">Distans</div><div class="reason">Motivering.</div><div class="development-focus"><strong>Utvecklingsfokus</strong><span>Fokus.</span></div></div>
<h2 class="section">Styrkemall framåt</h2><div class="principles"><div class="principle">Bulgarian split squat.</div></div>
<footer>Footer</footer></body></html>'''
        plan = {
            "days": [
                {"date": "2026-08-24", "sport": "run", "session": "Löpning"},
                {"date": "2026-08-26", "sport": "swim", "session": "Simning"},
                {"date": "2026-08-30", "sport": "run", "session": "Distans"},
            ]
        }
        activities = [{"sport_type": "Run", "display_label": "Löpning", "start_date_local": "2026-08-24T18:00:00"}]
        rendered = apply_signal_ui(
            page,
            ["Bulgarian split squat.", "Vad + soleus."],
            plan=plan,
            activities=activities,
            today=date(2026, 8, 26),
        )
        self.assertIn('class="reference-chip"', rendered)
        self.assertIn('id="strengthSheet"', rendered)
        self.assertNotIn("Styrkemall framåt", rendered)
        self.assertIn('class="day-why"', rendered)
        self.assertIn('<strong>Fokus</strong>', rendered)
        self.assertIn('class="brain-why-details"', rendered)
        self.assertIn('class="day past-completed" id="dag-2026-08-24"', rendered)
        self.assertIn('class="day decision-horizon" id="dag-2026-08-26"', rendered)
        self.assertIn('class="day future-compact" id="dag-2026-08-30"', rendered)
        self.assertIn('class="week-state"', rendered)
        self.assertGreater(rendered.find('class="week-state"'), rendered.find('<h2 class="section">Aktuell vecka</h2>'))
        self.assertIn('.week-state .dashboard>.dashboard-card:last-child{display:none}', rendered)


if __name__ == "__main__":
    unittest.main()
