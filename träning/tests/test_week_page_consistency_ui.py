#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_week_page_consistency_ui import (  # noqa: E402
    install_css,
    normalize_current,
    normalize_future,
    normalize_history,
    validate_page,
)


class WeekPageConsistencyUiTests(unittest.TestCase):
    def current_page(self):
        return """<html><head><style></style></head><body class="quiet-performance qp-current"><div class="wrap">
<nav class="top-week-nav"><span>nav</span></nav>
<section class="top-overview"><section class="top-today"></section></section>
<section class="current-week-header"><h2 class="section">Aktuell vecka</h2><strong class="current-week-focus">Sim aerob/teknik + kontrollerad löptröskel</strong><div class="current-week-meta">Byggblock · mikrocykel 1 av 4 · 5 pass</div></section>
<details class="week-status-expander"><summary>Veckostatus</summary></details>
</div></body></html>"""

    def history_page(self):
        return """<html><head><style></style></head><body class="quiet-performance qp-history"><div class="wrap">
<header><div class="eyebrow">Träningsplan</div><h1>Vecka 38</h1></header>
<nav class="top-week-nav"><span>nav</span></nav>
<div class="hero week-focus-card"><h2 class="week-focus-title">Mesocykel · löptröskel + backkvalitet · mikrocykel 4 av 4</h2><details class="week-focus-details"><summary>Planidé</summary><p>Kontrollerad löpkvalitet.</p></details></div>
<section class="dashboard" aria-label="Veckoöversikt"><div class="metrics"><div class="metric"><strong>8</strong><span>pass</span></div><div class="metric"><strong>10:13:46</strong><span>passtid</span></div><div class="metric"><strong>7</strong><span>träningsdagar</span></div></div></section>
<section class="week-review"><div>Veckoutvärdering</div></section>
<h2 class="section">Aktuell vecka</h2><div class="day"></div>
</div></body></html>"""

    def future_page(self):
        return """<html><head><style></style></head><body class="quiet-performance qp-history"><div class="wrap">
<header><div class="eyebrow">ADAPTIV TRÄNINGSPLANERING</div><h1>Vecka 40</h1></header>
<nav class="top-week-nav"><span>nav</span></nav>
<div class="hero week-focus-card"><h2 class="week-focus-title">Fortsatt byggblock — prioritet sim + kontrollerad löptröskel · mikrocykel 2 av 4</h2><details class="week-focus-details"><summary>Planidé</summary><p>Fortsatt sim- och löputveckling.</p></details></div>
<section class="dashboard" aria-label="Planöversikt nästa vecka"><div class="metrics preview-metrics"><div class="metric"><strong>1</strong><span>fast</span></div><div class="metric"><strong>0</strong><span>planerat</span></div><div class="metric"><strong>4</strong><span>preliminärt</span></div><div class="metric"><strong>2</strong><span>öppet</span></div></div><div class="dashboard-card"><div class="preview-focus">Mikrocykel 2 av 4.</div></div></section>
<h2 class="section">Preliminär vecka</h2><div class="day"></div>
</div></body></html>"""

    def upcoming(self):
        return {
            "week_key": "2026-W40",
            "meta": {
                "microcycle_index": 2,
                "microcycle_total": 4,
                "title": "Fortsatt byggblock — prioritet sim + kontrollerad löptröskel · mikrocykel 2 av 4",
                "mesocycle_contract": {
                    "primary": ["swim_aerobic", "swim_technique", "run_threshold"],
                },
            },
        }

    def test_current_uses_shared_week_context_classes(self):
        rendered = install_css(normalize_current(self.current_page()))
        validate_page(rendered, "current")
        self.assertIn('class="week-context-header current-week-header"', rendered)
        self.assertIn('class="week-context-focus current-week-focus"', rendered)
        self.assertIn('class="week-context-meta current-week-meta"', rendered)
        self.assertIn("Aktuell vecka", rendered)

    def test_history_uses_same_header_emphasis_and_collapsed_status(self):
        rendered = install_css(normalize_history(self.history_page()))
        validate_page(rendered, "history")
        self.assertNotIn("<header>", rendered)
        self.assertNotIn("week-focus-card", rendered)
        self.assertNotIn(">Aktuell vecka<", rendered)
        self.assertIn('<h2 class="section">Historisk vecka</h2>', rendered)
        self.assertIn('<strong class="week-context-focus">löptröskel + backkvalitet</strong>', rendered)
        self.assertIn("Historik · mikrocykel 4 av 4 · 8 pass · 10:13:46 passtid · 7 träningsdagar", rendered)
        self.assertIn("<summary>Veckostatus</summary>", rendered)
        self.assertIn(">Planidé</summary>", rendered)

    def test_future_uses_same_header_emphasis_and_planstatus(self):
        rendered = install_css(normalize_future(self.future_page(), self.upcoming()))
        validate_page(rendered, "future")
        self.assertNotIn("<header>", rendered)
        self.assertNotIn("week-focus-card", rendered)
        self.assertNotIn(">Preliminär vecka<", rendered)
        self.assertIn('<h2 class="section">Kommande vecka</h2>', rendered)
        self.assertIn("Sim aerob/teknik + kontrollerad löptröskel", rendered)
        self.assertIn("Preliminär · mikrocykel 2 av 4", rendered)
        self.assertIn("1 fast · 0 planerat · 4 preliminärt · 2 öppet", rendered)
        self.assertIn("<summary>Planstatus</summary>", rendered)
        self.assertIn(">Planidé</summary>", rendered)


if __name__ == "__main__":
    unittest.main()
