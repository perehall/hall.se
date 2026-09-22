#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_completed_day_summary_ui import simplify_completed_days  # noqa: E402


class CompletedDaySummaryUiTests(unittest.TestCase):
    def page(self):
        return """<html><head><style></style></head><body>
<!-- training-input-ui-v1:start -->
<section class="training-input" data-training-input data-activity-id="1" data-reviewed="true" data-processed-event-keys="training-input:aaaaaaaaaaaaaaaaaaaaaaaa">
  <div class="training-input-compact"><div><div class="training-input-summary">Sparat · RPE 2 · Pigg</div></div><button type="button" class="training-input-toggle" data-training-input-toggle>Ändra</button></div>
  <div class="training-input-editor" data-training-input-editor hidden><button type="button" data-training-input-save>Spara</button></div>
</section>
<!-- training-input-ui-v1:end -->
<!-- training-input-ui-v1:start -->
<section class="training-input" data-training-input data-activity-id="2" data-reviewed="true" data-processed-event-keys="training-input:bbbbbbbbbbbbbbbbbbbbbbbb">
  <div class="training-input-compact"><div><div class="training-input-summary">Sparat · RPE 4 · Pigg</div></div><button type="button" class="training-input-toggle" data-training-input-toggle>Ändra</button></div>
  <div class="training-input-editor" data-training-input-editor hidden><button type="button" data-training-input-save>Spara</button></div>
</section>
<!-- training-input-ui-v1:end -->
<div class="day past-exception workout-card-v2" id="dag-2026-09-21">
  <div class="daytop"><div class="day-date-line"><span class="dow">Måndag</span><span class="date">21 sep</span></div><div class="badge fixed">Aktuell plan</div></div>
  <div class="session"><span class="session-text"><strong class="session-title">Enduroskola</strong><span class="session-meta">fast tillfälle</span></span></div>
  <div class="pass"><div class="pass-title">Automatiskt från Strava</div><div><strong>WeightTraining</strong> · 33:34</div><div><strong>Enduro</strong> · 1:36:49</div></div>
  <div class="coach yoda-v2">
    <div class="coach-title">Tränings-Yoda (AI)</div>
    <div class="coach-decision"><span>Beslut</span><strong>Behåll planen</strong><span class="coach-target">2026-09-22</span></div>
    <div class="coach-summary">Båda passen tolererades väl. Ytterligare analys behövs inte i huvudvyn.</div>
    <div class="coach-next"><span class="coach-next-label">Nästa steg</span><div>Genomför tisdagens simning lugnt och kontrollerat.</div></div>
  </div>
  <section class="week-activity-insight"><div class="week-activity-insight-kicker">Passinsikt</div></section>
</div>
</body></html>"""

    def activities(self):
        return {
            "activities": [
                {
                    "id": 2,
                    "sport_type": "Enduro",
                    "display_label": "Enduro",
                    "start_date_local": "2026-09-21T17:44:36Z",
                    "elapsed_time_s": 5809,
                },
                {
                    "id": 1,
                    "sport_type": "WeightTraining",
                    "display_label": "WeightTraining",
                    "start_date_local": "2026-09-21T20:47:51Z",
                    "elapsed_time_s": 2014,
                },
            ]
        }

    def overrides(self):
        return {
            "schema_version": 1,
            "overrides": {
                "2": {
                    "training_feedback": {
                        "text": "Teknisk körning.",
                        "rpe": 4,
                        "feeling": ["fresh"],
                    }
                },
                "1": {
                    "training_feedback": {
                        "text": "",
                        "rpe": 2,
                        "feeling": ["fresh"],
                    }
                },
            },
        }

    def test_completed_day_is_outcome_first_and_details_are_secondary(self):
        rendered, changed = simplify_completed_days(
            self.page(), self.activities(), self.overrides(), "2026-09-22"
        )

        self.assertEqual(changed, 1)
        self.assertIn("completed-day-simplified", rendered)
        self.assertIn('<span class="completed-day-kicker">Genomfört</span>', rendered)
        self.assertIn("Enduro 1:36:49 · Styrka 33:34", rendered)
        self.assertIn('data-visible-sport-icons="enduro,strength"', rendered)
        self.assertIn('data-visible-sport-icon="enduro"', rendered)
        self.assertIn('data-visible-sport-icon="strength"', rendered)
        self.assertIn('class="sport-icon icon-enduro"', rendered)
        self.assertIn('class="sport-icon icon-strength"', rendered)

        self.assertIn('<span class="completed-day-label">Planpåverkan</span>', rendered)
        self.assertIn("<strong>Planen ligger kvar</strong>", rendered)
        self.assertIn("Båda passen tolererades väl.", rendered)

        self.assertIn('<span class="completed-day-label">Din känsla</span>', rendered)
        self.assertIn("<strong>Enduro</strong><span> · RPE 4 · Pigg</span>", rendered)
        self.assertIn("<strong>Styrka</strong><span> · RPE 2 · Pigg</span>", rendered)
        self.assertIn('data-feedback-activity-id="2"', rendered)
        self.assertIn('data-feedback-activity-id="1"', rendered)
        self.assertIn('class="training-input completed-day-inline-input"', rendered)
        self.assertEqual(rendered.count('data-training-input '), 2)
        self.assertEqual(rendered.count(">Ändra</button>"), 2)

        day_pos = rendered.index('id="dag-2026-09-21"')
        self.assertNotIn("training-input-ui-v1:start", rendered[:day_pos])

        self.assertIn('<span class="completed-day-label">Nästa</span>', rendered)
        self.assertIn("Genomför tisdagens simning lugnt och kontrollerat.", rendered)

        self.assertIn('<details class="completed-day-details"><summary>Visa detaljer</summary>', rendered)
        self.assertIn("<strong>Planerat</strong> · Enduroskola · fast tillfälle", rendered)
        self.assertIn('<div class="pass-title">Passdata</div>', rendered)
        self.assertIn('<div class="coach-title">Analys</div>', rendered)
        self.assertIn(">Passanalys<", rendered)

        # Provider/implementation language must not survive the user-facing render.
        self.assertNotIn("Automatiskt från Strava", rendered)
        self.assertNotIn("Tränings-Yoda (AI)", rendered)
        self.assertNotIn("WeightTraining", rendered)

    def test_day_without_activity_is_not_changed(self):
        rendered, changed = simplify_completed_days(
            self.page(), {"activities": []}, self.overrides(), "2026-09-22"
        )
        self.assertEqual(changed, 0)
        self.assertEqual(rendered, self.page())

    def test_unreviewed_recent_activity_is_kept_inside_feeling_section(self):
        page = self.page().replace(
            'data-activity-id="2" data-reviewed="true"',
            'data-activity-id="2" data-reviewed="false"',
        )
        overrides = self.overrides()
        del overrides["overrides"]["2"]
        rendered, changed = simplify_completed_days(
            page, self.activities(), overrides, "2026-09-22"
        )
        self.assertEqual(changed, 1)
        self.assertIn(
            '<strong>Enduro</strong><span> · Inte utvärderat</span>',
            rendered,
        )
        self.assertIn(">Ändra</button>", rendered)


if __name__ == "__main__":
    unittest.main()
