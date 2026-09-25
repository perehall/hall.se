#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_top_overview_ui import apply_top_overview, validate_page  # noqa: E402


class TopOverviewUiTests(unittest.TestCase):
    def plan(self):
        return {
            "meta": {
                "week": 39,
                "week_start": "2026-09-21",
                "week_end": "2026-09-27",
                "title": "Fortsatt byggblock — prioritet sim + kontrollerad löptröskel · mikrocykel 1 av 4",
                "principle": "Fortsätt utveckla simmens aeroba kapacitet och teknik samtidigt som kontrollerad löptröskel bibehålls.",
                "microcycle_index": 1,
                "microcycle_total": 4,
                "mesocycle_contract": {
                    "primary": ["swim_aerobic", "swim_technique", "run_threshold"],
                    "secondary": ["run_easy_distance", "mtb_technical"],
                    "maintenance": ["swim_threshold"],
                    "protected_capacity": ["strength_unilateral", "strength_core"],
                },
            },
            "days": [
                {
                    "date": "2026-09-25",
                    "label": "Fredag",
                    "sport": "swim",
                    "status": "preliminary",
                    "session": "Simning · 4 000 m · aerob + kontrollerad tröskel",
                    "reason": "Tisdagens 4 × 8 min gav redan mikrocykelns löptröskelstimulus. Veckobeslut: hold.",
                },
                {
                    "date": "2026-09-26",
                    "label": "Lördag",
                    "sport": "open",
                    "status": "open",
                    "session": "Ingen planerad träning",
                },
                {
                    "date": "2026-09-27",
                    "label": "Söndag",
                    "sport": "run",
                    "status": "preliminary",
                    "session": "Löpning · lugn distans · 120 min",
                },
            ],
        }

    def strategy(self):
        return {
            "current_mesocycle": {
                "hypothesis": "Stabil sim- och löpkontinuitet stödjer en konservativ progression.",
            }
        }

    def activities(self):
        return {
            "activities": [
                {
                    "id": 23,
                    "sport_type": "Swim",
                    "start_date_local": "2026-09-23T19:00:00+02:00",
                }
            ]
        }

    def registry(self):
        return {
            "swim": {"viewBox": "0 0 24 24", "path": "M1 1h22v22H1z"},
        }

    def page(self, *, embed_feedback=True):
        embedded = (
            '<div class="completed-day-summary"><div data-feedback-activity-id="23">'
            '<section class="training-input completed-day-inline-input" data-training-input data-activity-id="23"></section>'
            '</div></div>'
            if embed_feedback
            else '<div class="completed-day-summary"></div>'
        )
        return f"""<!doctype html><html><head><style></style></head>
<body class="quiet-performance qp-current"><div class="wrap">
<header><div class="eyebrow">Träningsplan</div><h1>Vecka 39</h1><div class="sub header-meta-line"><span class="week-period">21–27 sep</span><span>·</span><span class="header-updated">uppdaterad 25 sep 08:49</span></div></header>
<div class="goal-page-link"><a href="/träning/malbild-2027/">Målbild 2027 <span>→</span></a></div>
<nav class="week-nav"><a class="prev" href="/träning/vecka/2026-W38/">← Vecka 38</a><div class="week-nav-center"><strong>Vecka 39</strong><span>AKTUELL</span></div><a class="next" href="/träning/vecka/2026-W40/">Vecka 40 →</a></nav>
<!-- training-brain-v1:start -->
<section class="training-brain"><div class="brain-today"><div class="brain-topline"><span class="brain-kicker">Idag · fredag 25 sep</span><span class="brain-status">Kan ändras</span></div><div class="brain-headline">Simning 4 000 m aerob + kontrollerad tröskel</div><details class="brain-why-details"><summary>Motivering</summary><div class="brain-why">Lång text.</div></details><div class="brain-next"><div class="brain-next-label">Nästa · imorgon</div><strong>Lördag · Vilodag</strong></div></div></section>
<!-- training-brain-v1:end -->
<div class="hero week-focus-card"><h2 class="week-focus-title">Fortsatt byggblock — prioritet sim + kontrollerad löptröskel</h2><div class="week-focus-mesocycle-meta">Fortsatt byggblock — prioritet sim + kontrollerad löptröskel · mikrocykel 1 av 4</div><details class="week-focus-details"><summary>Planidé</summary><p>Gammal planidé.</p></details></div>
<!-- training-input-ui-v1:start -->
<section class="training-input" data-training-input data-activity-id="23"><div>Flytande feedback</div></section>
<!-- training-input-ui-v1:end -->
<h2 class="section">Aktuell vecka</h2>
<details class="week-status-expander"><summary>5 pass · 5:33 · 4 träningsdagar</summary><div class="week-status-body"><section class="dashboard" aria-label="Veckoöversikt"></section></div></details>
<div class="day completed-day-simplified" id="dag-2026-09-23">{embedded}</div>
<div class="day future-workout-applied" id="dag-2026-09-25"></div>
</div></body></html>"""

    def test_top_is_one_crisp_hierarchy(self):
        rendered = apply_top_overview(
            self.page(),
            self.plan(),
            self.strategy(),
            self.activities(),
            self.registry(),
            today=date(2026, 9, 25),
        )
        validate_page(rendered)

        self.assertEqual(rendered.count('class="top-overview"'), 1)
        self.assertIn("‹ Vecka 38", rendered)
        self.assertIn("Vecka 39", rendered)
        self.assertIn("21–27 sep", rendered)
        self.assertIn("Vecka 40 ›", rendered)
        self.assertIn("Uppdaterad 25 sep 08:49", rendered)
        self.assertIn("Målbild 2027 →", rendered)

        self.assertIn("Idag · fredag 25 sep", rendered)
        self.assertIn("Kan ändras", rendered)
        self.assertIn("Simning · 4 000 m", rendered)
        self.assertIn("aerob + kontrollerad tröskel", rendered)
        self.assertIn("Imorgon · <strong>Vilodag</strong>", rendered)
        self.assertIn(">Plan och motivering</summary>", rendered)
        self.assertNotIn("Veckobeslut:", rendered)

        self.assertNotIn("Veckofokus", rendered)
        self.assertIn('class="current-week-header"', rendered)
        self.assertIn("Sim aerob/teknik + kontrollerad löptröskel", rendered)
        self.assertIn(
            "Byggblock · mikrocykel 1 av 4 · 5 pass · 5:33 · 4 träningsdagar",
            rendered,
        )
        self.assertIn(">Planidé</summary>", rendered)
        self.assertIn(">Veckostatus</summary>", rendered)
        self.assertIn("Mesocykelhypotes:", rendered)
        self.assertIn("Primärt:", rendered)
        self.assertIn("Skyddat:", rendered)

        # Visual priority: Today is the only surfaced primary block. Week focus
        # is context for Aktuell vecka rather than a competing section.
        self.assertIn("border-radius:18px", rendered)
        self.assertIn("background:rgba(255,255,255,.74)", rendered)
        self.assertIn(".current-week-header{\n  margin-top:42px;", rendered)
        self.assertNotIn('class="top-week-focus"', rendered)

        current = rendered.index('<h2 class="section">Aktuell vecka</h2>')
        prefix = rendered[:current]
        self.assertNotIn("<header>", prefix)
        self.assertNotIn('class="week-nav"', prefix)
        self.assertNotIn('class="training-brain"', prefix)
        self.assertNotIn('class="hero week-focus-card"', prefix)
        self.assertNotIn('class="goal-page-link"', prefix)
        self.assertNotIn("Flytande feedback", prefix)

        # The feedback editor is preserved in its completed workout, not discarded.
        self.assertIn('data-feedback-activity-id="23"', rendered[current:])
        self.assertIn('data-activity-id="23"', rendered[current:])

    def test_fails_closed_before_dropping_unmoved_feedback(self):
        with self.assertRaises(RuntimeError):
            apply_top_overview(
                self.page(embed_feedback=False),
                self.plan(),
                self.strategy(),
                self.activities(),
                self.registry(),
                today=date(2026, 9, 25),
            )

    def test_is_idempotent(self):
        once = apply_top_overview(
            self.page(),
            self.plan(),
            self.strategy(),
            self.activities(),
            self.registry(),
            today=date(2026, 9, 25),
        )
        twice = apply_top_overview(
            once,
            self.plan(),
            self.strategy(),
            self.activities(),
            self.registry(),
            today=date(2026, 9, 25),
        )
        self.assertEqual(once, twice)



    def test_current_week_heading_with_post_workout_anchor_is_supported(self):
        page = self.sample_page().replace(
            '<h2 class="section">Aktuell vecka</h2>',
            '<h2 class="section" id="aktuell-vecka">Aktuell vecka</h2>',
            1,
        )
        rendered = apply_top_overview(
            page,
            self.plan(),
            self.strategy(),
            self.activities(),
            self.registry(),
            today=date(2026, 9, 25),
        )
        self.assertEqual(rendered.count('class="top-overview"'), 1)
        self.assertEqual(rendered.count('class="current-week-header"'), 1)
        self.assertIn('<h2 class="section">Aktuell vecka</h2>', rendered)
        self.assertNotIn('id="aktuell-vecka"', rendered)

if __name__ == "__main__":
    unittest.main()
