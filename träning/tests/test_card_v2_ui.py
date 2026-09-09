#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_card_v2_ui import apply_card_v2, validate_page  # noqa: E402


class CardV2UiTests(unittest.TestCase):
    def sample_page(self):
        return '''<html><head><style></style></head><body>
<div class="day decision-horizon" id="dag-2026-09-09">
  <div class="daytop"><div class="day-date-line"><span class="dow">Onsdag</span><span class="date">9 sep</span></div><div class="badge conditional">Alternativ finns</div></div>
  <div class="session"><span class="session-text"><strong class="session-title">Simning 3 200 m aerob/teknik</strong><span class="session-meta">ca 60 min</span></span></div>
  <div class="device-sync-state synced"><svg></svg><span>Klocksync skickad</span></div>
  <div class="workout-prescription"><div class="workout-prescription-head">Passupplägg</div><div class="workout-prescription-row"><span class="workout-prescription-dose">4×500 m</span><span class="workout-prescription-text">Stabil aerob · vila 30 s</span></div></div>
  <details class="day-why"><summary>Motivering</summary><div class="reason">Mesocykelns aeroba simstimulus.</div></details>
  <div class="development-focus"><strong>Passfokus</strong><span>Stabil kroppslinje och avslappnad rotation.</span></div>
</div>
<div class="day future-compact" id="dag-2026-09-13"><div class="daytop"></div><div class="session">Löpning</div><div class="development-focus"><strong>Utvecklingsfokus</strong><span>Lugnt.</span></div></div>
</body></html>'''

    def test_card_v2_flattens_inner_cards_and_moves_footer_metadata(self):
        rendered = apply_card_v2(self.sample_page(), today_text="2026-09-09")
        validate_page(rendered)
        self.assertIn('class="day decision-horizon workout-card-v2 card-v2-today"', rendered)
        self.assertIn('class="card-v2-footer"', rendered)
        self.assertIn('<strong>Fokus:</strong>', rendered)
        self.assertNotIn('<strong>Passfokus</strong>', rendered)
        card = rendered.split('id="dag-2026-09-09"', 1)[1].split('id="dag-2026-09-13"', 1)[0]
        self.assertGreater(card.find('class="card-v2-footer"'), card.find('class="workout-prescription"'))
        self.assertGreater(card.find('class="device-sync-state synced"'), card.find('class="workout-prescription"'))
        self.assertIn('.workout-card-v2 .workout-prescription{margin:13px 0 3px;padding:0;border:0', rendered)
        self.assertIn('.workout-card-v2 .development-focus{display:flex', rendered)
        self.assertIn('.card-v2-footer .device-sync-state{margin:0 0 0 auto;padding:0;border:0', rendered)

    def test_card_v2_is_idempotent_and_keeps_compact_cards_compact(self):
        once = apply_card_v2(self.sample_page(), today_text="2026-09-09")
        twice = apply_card_v2(once, today_text="2026-09-09")
        self.assertEqual(once, twice)
        self.assertIn('class="day future-compact workout-card-v2" id="dag-2026-09-13"', twice)
        self.assertIn('.day.workout-card-v2.past-completed,.day.workout-card-v2.future-compact{padding:11px 12px', twice)
        self.assertIn('.past-completed .card-v2-footer,.future-compact .card-v2-footer,.today-completed .card-v2-footer{display:none}', twice)


if __name__ == "__main__":
    unittest.main()
