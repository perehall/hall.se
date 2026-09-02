#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_signal_ui import annotate_week_days, apply_signal_ui, compact_text, session_display_parts  # noqa: E402


class SignalUiTests(unittest.TestCase):
    def test_session_display_splits_prescription_from_secondary_detail(self):
        swim = {
            "sport": "swim",
            "session": "Simning · aerob/teknik · 3 200 m · ca 60 min · alternativ: Swimrun · Jogersö Extreme · 1 varv",
        }
        self.assertEqual(
            session_display_parts(swim),
            ("Simning 3 200 m aerob/teknik", "ca 60 min · alternativ: Swimrun, Jogersö Extreme 1 varv"),
        )
        hills = {
            "sport": "run",
            "session": "Löpning · backkvalitet · 15 min lugnt + 6 × 150 m / full lugn nedjogg + 10 min lugnt",
        }
        self.assertEqual(
            session_display_parts(hills),
            ("Löpning · backkvalitet", "15 min lugnt + 6 × 150 m / full lugn nedjogg + 10 min lugnt"),
        )

    def test_compact_text_keeps_first_short_sentence(self):
        text = "Gör det lugnt. Detta är en mycket längre förklaring som inte behöver ligga i huvudvyn."
        self.assertEqual(compact_text(text, 25), "Gör det lugnt.")

    def test_signal_hierarchy_moves_stats_down_and_compacts_week(self):
        page = '''<html><style></style><body>
<div class="hero week-focus-card"><h2 class="week-focus-title"><strong>Veckofokus:</strong> Test</h2><details class="week-focus-details"><summary>Planidé</summary><p>Plan.</p></details></div>
<section class="training-brain"><div class="brain-why"><strong>Varför:</strong> Låg mekanisk belastning.</div><div class="brain-note">Beslutet väntar på torsdagens faktiska belastning innan fredagens dos låses.</div></section>
<section class="dashboard" aria-label="Veckoöversikt"><div class="metrics"></div><div class="dashboard-grid"></div><div class="dashboard-card"><div class="dashboard-title">Nästa dagar</div></div></section>
<h2 class="section">Aktuell vecka</h2>
<div class="day" id="dag-2026-08-24"><div class="daytop"><div><div class="dow">Måndag</div><div class="date">2026-08-24</div></div><div class="badge fixed">GENOMFÖRT</div></div><div class="session">Löpning · lugn distans · 75 min</div><div class="reason">Motivering.</div><div class="pass"><div class="pass-title">Automatiskt från Strava</div><div>Data</div></div><div class="coach yoda-v2"><div class="coach-next"><span class="coach-next-label">Nästa steg</span><div>Gammalt råd.</div></div></div><div class="development-focus"><strong>Utvecklingsfokus</strong><span>Fokus.</span></div></div>
<div class="day" id="dag-2026-08-26"><div class="daytop"><div><div class="dow">Onsdag</div><div class="date">2026-08-26</div></div><div class="badge conditional">VILLKORAT</div></div><div class="session">Simning · aerob/teknik · 3 200 m · ca 60 min · alternativ: Swimrun · Jogersö Extreme · 1 varv</div><div class="next-weather"><strong>Väder · Oxelösund</strong> · Halvklart</div><div class="reason">Motivering.</div><div class="development-focus"><strong>Utvecklingsfokus</strong><span>Fokus.</span></div></div>
<div class="day" id="dag-2026-08-30"><div class="daytop"><div><div class="dow">Söndag</div><div class="date">2026-08-30</div></div><div class="badge conditional">PRELIMINÄRT</div></div><div class="session">Löpning · lugn distans · 75 min</div><div class="reason">Motivering.</div><div class="development-focus"><strong>Utvecklingsfokus</strong><span>Fokus.</span></div></div>
<h2 class="section">Styrkemall framåt</h2><div class="principles"><div class="principle">Bulgarian split squat.</div></div>
<footer>Footer</footer></body></html>'''
        plan = {
            "days": [
                {"date": "2026-08-24", "label": "Måndag", "status": "completed", "sport": "run", "session": "Löpning · lugn distans · 75 min"},
                {"date": "2026-08-26", "label": "Onsdag", "status": "conditional", "sport": "swim", "alternative_sports": ["swimrun"], "session": "Simning · aerob/teknik · 3 200 m · ca 60 min · alternativ: Swimrun · Jogersö Extreme · 1 varv"},
                {"date": "2026-08-30", "label": "Söndag", "status": "preliminary", "sport": "run", "session": "Löpning · lugn distans · 75 min"},
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
        self.assertIn('<strong>Passfokus</strong>', rendered)
        self.assertIn('class="brain-why-details"', rendered)
        self.assertIn('class="day past-completed" id="dag-2026-08-24"', rendered)
        self.assertIn('class="day decision-horizon" id="dag-2026-08-26"', rendered)
        self.assertIn('class="day future-compact" id="dag-2026-08-30"', rendered)
        self.assertIn('class="week-state"', rendered)
        self.assertGreater(rendered.find('class="week-state"'), rendered.find('<h2 class="section">Aktuell vecka</h2>'))
        self.assertIn('.week-state .dashboard>.dashboard-card:last-child{display:none}', rendered)
        self.assertIn('.today-completed .session,.today-completed .next-weather', rendered)
        self.assertIn('.today-completed .pass-title{display:none}', rendered)
        self.assertIn('<span class="dow">Onsdag</span><span class="date">26 aug</span>', rendered)
        self.assertIn('<div class="badge conditional">Alternativ finns</div>', rendered)
        self.assertIn('<strong class="session-title">Simning 3 200 m aerob/teknik</strong>', rendered)
        self.assertIn('<span class="session-meta">ca 60 min · alternativ: Swimrun, Jogersö Extreme 1 varv</span>', rendered)
        self.assertIn('<span class="weather-label">Väder i Oxelösund:</span>', rendered)
        self.assertIn('<summary>Motivering</summary>', rendered)
        self.assertNotIn('<summary>Varför?</summary><div class="reason">Motivering.</div>', rendered)


    def test_fulfilled_today_is_rendered_as_completed_not_alternative_open(self):
        page = (
            '<div class="day decision-horizon" id="dag-2026-09-02">'
            '<div class="daytop"><div><div class="dow">Onsdag</div><div class="date">2026-09-02</div></div>'
            '<div class="badge conditional">Alternativ finns</div></div>'
            '<div class="session">Simning · alternativ: Swimrun</div>'
            '</div>'
        )
        plan = {
            "days": [{
                "date": "2026-09-02",
                "status": "conditional",
                "sport": "swim",
                "alternative_sports": ["swimrun"],
                "session": "Simning · alternativ: Swimrun",
            }]
        }
        activities = [{
            "id": 1,
            "sport_type": "Swimrun",
            "start_date_local": "2026-09-02T18:00:00+02:00",
        }]
        rendered = annotate_week_days(page, plan, activities, date(2026, 9, 2))
        self.assertIn('class="day past-completed today-completed" id="dag-2026-09-02"', rendered)
        self.assertIn('<div class="badge fixed">Genomfört</div>', rendered)
        self.assertNotIn("Alternativ finns", rendered)



if __name__ == "__main__":
    unittest.main()
