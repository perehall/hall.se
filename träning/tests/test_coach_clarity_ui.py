import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "finalize_coach_clarity_ui.py"
spec = importlib.util.spec_from_file_location("clarity", MODULE)
clarity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clarity)


class CoachClarityUiTests(unittest.TestCase):
    def test_motivation_is_one_sentence(self):
        page = (
            '<details class="day-why"><summary>Motivering</summary><div class="reason">'
            'Första meningen förklarar passets roll. Andra meningen utvecklar fysiologin. Tredje meningen behövs inte.'
            '</div></details>'
        )
        rendered = clarity.compact_day_motivations(page)
        self.assertIn('Första meningen förklarar passets roll.', rendered)
        self.assertNotIn('Andra meningen', rendered)
        self.assertNotIn('Tredje meningen', rendered)

    def test_preworkout_adjustment_is_removed_after_activity_and_new_coach_analysis(self):
        page = (
            '<div class="day decision-horizon" id="dag-2026-09-05">'
            '<div class="decision coach-adjust"><strong>Tränings-Yoda · justering</strong>'
            'Gör simningen 3 200 m och styrkan.</div>'
            '<div class="pass">Swim · 4,00 km</div>'
            '<div class="coach yoda-v2">Ny analys</div>'
            '</div>'
            '<div class="day decision-horizon" id="dag-2026-09-06">'
            '<div class="decision coach-adjust"><strong>Tränings-Yoda · justering</strong>Behåll söndagspasset.</div>'
            '</div>'
        )
        activities = {"activities": [{"start_date_local": "2026-09-05T14:48:11"}]}
        coach = {"analyses": [{"activity_date": "2026-09-05"}]}
        rendered = clarity.remove_superseded_preworkout_adjustments(page, activities, coach)
        first_day = rendered.split('id="dag-2026-09-06"', 1)[0]
        self.assertNotIn('coach-adjust', first_day)
        self.assertIn('Behåll söndagspasset.', rendered)


if __name__ == "__main__":
    unittest.main()
