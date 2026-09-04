#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_completed_workout_truth import (  # noqa: E402
    assert_completed_truth,
    force_completed_badges,
    replace_current_post_workout_card,
)


class CompletedWorkoutTruthTests(unittest.TestCase):
    def setUp(self):
        self.today = "2026-09-04"
        self.day = {
            "date": self.today,
            "label": "Fredag",
            "status": "conditional",
            "planning_status": "conditional",
            "sport": "run",
            "session": "Löpning · backkvalitet · 15 min lugnt + 2 × 6 × 150 m / lugn joggvila + 10 min lugnt",
            "original_session": "Löpning · backkvalitet · 15 min lugnt + 2 × 7 × 150 m / lugn joggvila + 10 min lugnt",
            "dose_resolution": {
                "state": "resolved",
                "kind": "structured",
                "value": 12,
                "option_id": "run-hill-2x6x150",
            },
        }
        self.plan = {"days": [self.day]}
        self.activity = {
            "id": 42,
            "start_date_local": "2026-09-04T18:00:00",
            "sport_type": "Run",
            "source_sport_type": "Run",
            "display_label": "Löpning · backintervaller",
            "name": "Löpning på kvällen",
            "elapsed_time_s": 3988,
            "distance_m": 12680,
            "average_heartrate": 142.4,
            "max_heartrate": 167,
            "user_report": "3 × 6 backintervaller (18 backar totalt). Tre serier om sex intervaller.",
        }
        self.activities_state = {"activities": [self.activity]}
        self.analysis = {
            "activity_id": 42,
            "activity_date": self.today,
            "generated_at_utc": "2026-09-04T20:44:01+00:00",
            "assessment": {
                "summary": "Genomfört: 3 × 6 backintervaller (18 totalt).",
                "load_interpretation": "Belastningen vägs in i nästa pass.",
                "facts": ["Användarrapport: 3 × 6 backintervaller."],
                "interpretations": ["Nästa normala utvecklingsdos bör ligga över 18 repetitioner."],
                "unknowns": [],
            },
            "plan_action": {
                "action": "keep",
                "target_date": "",
                "reason": "Utfallet är registrerat.",
                "recommendation": "",
            },
            "auto_apply": {"applied": False},
        }
        self.coach_state = {"analyses": [self.analysis]}
        self.performance = {"entries": []}

    def test_completed_badge_overrides_old_conditional_copy(self):
        page = '''<html><body>
<div class="day past-completed today-completed" id="dag-2026-09-04">
<div class="daytop"><div></div><div class="badge fixed">Kan ändras</div></div>
</div><footer></footer></body></html>'''
        rendered = force_completed_badges(page, self.plan, [self.activity])
        self.assertIn('<div class="badge fixed">Genomfört</div>', rendered)
        self.assertNotIn('>Kan ändras<', rendered)

    def test_post_workout_card_is_rebuilt_from_current_sources(self):
        stale = '''<html><body>
<section class="today-outcome" data-post-workout-state="completed">
<div><span class="today-outcome-label">Plan före passet</span><strong>Löpning · 2 × 7 × 150 m</strong></div>
<div><span class="today-outcome-label">Genomfört</span><strong>2 × 6 × 150 m</strong></div>
<div class="today-outcome-evidence"><div>Passet uppfyller dagens ordinerade reducerade dos.</div></div>
</section>
<div class="day past-completed today-completed" id="dag-2026-09-04"><div class="daytop"><div></div><div class="badge fixed">Genomfört</div></div></div>
<footer></footer></body></html>'''

        rendered, context = replace_current_post_workout_card(
            stale,
            self.plan,
            self.activities_state,
            self.coach_state,
            self.performance,
            self.today,
        )
        assert_completed_truth(rendered, self.plan, [self.activity], context)

        self.assertIn("2 × 6 × 150 m / lugn joggvila", rendered)
        self.assertNotIn("2 × 7 × 150 m</strong>", rendered)
        self.assertIn("3 × 6 backintervaller (18 totalt)", rendered)
        self.assertIn("Nästa normala utvecklingsdos bör ligga över 18 repetitioner.", rendered)
        self.assertNotIn("Passet uppfyller dagens ordinerade reducerade dos.", rendered)


if __name__ == "__main__":
    unittest.main()
