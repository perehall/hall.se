#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from finalize_week_shell_ui import CSS_MARKER, apply_week_shell  # noqa: E402


class WeekShellUiTests(unittest.TestCase):
    def test_shell_unifies_width_and_adds_compact_system_info(self):
        page = """<!doctype html><html><head><style>
.wrap{width:min(100%,760px)}.day{padding:18px}.session{font-size:1.2rem}
</style></head><body><div class="wrap">
<header><h1>Vecka 34</h1></header>
<div class="hero"><h2>Veckofokus</h2></div>
<h2 class="section">Aktuell vecka</h2>
<div class="day"><div class="daytop"><div class="dow">Måndag</div></div><div class="session">Löpning</div><div class="reason">Lugnt.</div></div>
<h2 class="section">Styrkemall framåt</h2><div class="principles"><div class="principle">Bulgarian split squat.</div><div class="principle">Vad + soleus.</div></div>
<footer>Footer</footer></div></body></html>"""
        rendered = apply_week_shell(page)
        self.assertIn(CSS_MARKER, rendered)
        self.assertIn("scrollbar-gutter:stable", rendered)
        self.assertIn("width:min(100%,720px)!important", rendered)
        self.assertIn('onclick="openStrengthWindow()"', rendered)
        self.assertIn('onclick="openTrainingSystemInfo()"', rendered)
        self.assertIn('id="trainingSystemSheet"', rendered)
        self.assertIn("målbilden är överordnad", rendered)
        self.assertIn("målbild → utvecklingsblock → vecka → beslut de närmaste 2–3 dagarna", rendered)
        self.assertNotIn("Styrkemall framåt", rendered)

    def test_goal_page_uses_same_shell(self):
        page = """<!doctype html><html><head><style>.wrap{width:min(100%,920px)}h1{font-size:5rem}.card{padding:22px}</style></head>
<body><div class="wrap"><h1>Målbild 2027</h1><section class="card goal"><div class="goal-copy"><div class="title">Övergripande mål</div><p>Mål.</p></div><div class="mountain"></div></section><footer>Footer</footer></div></body></html>"""
        rendered = apply_week_shell(page)
        self.assertIn('<body class="goal-page">', rendered)
        self.assertIn("width:min(100%,720px)!important", rendered)
        self.assertIn(".goal-page .card{border-radius:20px", rendered)
        self.assertIn(".goal-page .goal{grid-template-columns:1fr", rendered)
        self.assertIn('id="trainingSystemSheet"', rendered)
        self.assertIn("den långsiktiga målbilden styr riktningen", rendered)

    def test_shell_is_idempotent(self):
        page = """<html><head><style></style></head><body><div class="wrap"><footer>Footer</footer></div></body></html>"""
        once = apply_week_shell(page)
        twice = apply_week_shell(once)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count(CSS_MARKER), 1)
        self.assertEqual(twice.count('id="trainingSystemSheet"'), 1)


if __name__ == "__main__":
    unittest.main()
