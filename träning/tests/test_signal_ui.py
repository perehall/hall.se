#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_signal_ui import apply_signal_ui, compact_text  # noqa: E402


class SignalUiTests(unittest.TestCase):
    def test_compact_text_keeps_first_short_sentence(self):
        text = "Gör det lugnt. Detta är en mycket längre förklaring som inte behöver ligga i huvudvyn."
        self.assertEqual(compact_text(text, 25), "Gör det lugnt.")

    def test_strength_moves_to_bottom_sheet_and_reasons_collapse(self):
        page = '''<html><style></style><body>
<section class="training-brain">
<div class="brain-why"><strong>Varför:</strong> Låg mekanisk belastning.</div>
<div class="brain-note">Beslutet väntar på torsdagens faktiska belastning innan fredagens dos låses.</div>
<div class="brain-hypothesis">En längre blockidé som ska finnas kvar men inte dominera huvudvyn.</div>
<div class="brain-meta">Utvärdering: 2026-09-21 · skyddade stimuli: run_threshold · run_hill_quality</div>
</section>
<div class="day"><div class="reason">Det här är passets längre motivering.</div>
<div class="development-focus"><strong>Utvecklingsfokus</strong><span>Jämn teknik och kontroll.</span></div></div>
<div class="coach yoda-v2"><div class="coach-summary">Sammanfattning.</div><div class="coach-next"><span class="coach-next-label">Nästa steg</span><div>Behåll dagens simning lugn och teknisk. Den andra meningen är onödigt lång och ska inte ta huvudytan.</div></div><div class="coach-apply">Ingen automatisk ändring.</div></div>
<h2 class="section">Styrkemall framåt</h2><div class="principles"><div class="principle">Bulgarian split squat.</div></div>
<footer>Footer</footer></body></html>'''
        rendered = apply_signal_ui(page, ["Bulgarian split squat.", "Vad + soleus."])
        self.assertIn('class="reference-chip"', rendered)
        self.assertIn('id="strengthSheet"', rendered)
        self.assertNotIn("Styrkemall framåt", rendered)
        self.assertIn('class="day-why"', rendered)
        self.assertIn('<summary>Varför?</summary>', rendered)
        self.assertIn('<strong>Fokus</strong>', rendered)
        self.assertIn('class="brain-why-details"', rendered)
        self.assertIn('class="brain-block-why"', rendered)
        self.assertNotIn("skyddade stimuli:", rendered)
        self.assertIn('.yoda-v2 .coach-summary,.yoda-v2 .coach-apply{display:none}', rendered)


if __name__ == "__main__":
    unittest.main()
