#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
GOAL = ROOT / "malbild" / "index.html"

WEEK_CSS = r'''
/* goal-link-layout-v1 */
.goal-page-link{display:flex;justify-content:flex-end;margin:0 0 8px}.goal-page-link a{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #ddd6fe;border-radius:12px;background:#faf5ff;color:#5b21b6;text-decoration:none;font-size:.78rem;font-weight:900;box-shadow:0 5px 14px rgba(76,29,149,.05)}
'''.strip()

GOAL_CSS = r'''
/* goal-back-layout-v1 */
.goal-back-row{display:flex;justify-content:flex-end;margin:12px 0 4px}.goal-back-row a{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #e2e8f0;border-radius:12px;background:#fff;color:#475569;text-decoration:none;font-size:.78rem;font-weight:900;box-shadow:0 5px 14px rgba(15,23,42,.04)}
'''.strip()


def add_css(page, marker, css):
    if marker in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Länklayout: </style> saknas")
    return page.replace("</style>", css + "\n</style>", 1)


def patch_week():
    page = INDEX.read_text(encoding="utf-8")
    page = re.sub(r'<div class="goal-home-link">.*?</div>', '', page, flags=re.S)
    page = re.sub(r'<div class="goal-page-link">.*?</div>', '', page, flags=re.S)
    page = add_css(page, "/* goal-link-layout-v1 */", WEEK_CSS)
    link = '<div class="goal-page-link"><a href="/träning/malbild/">Målbild 2027 <span>→</span></a></div>'
    nav = page.find('<nav class="week-nav"')
    if nav < 0:
        raise RuntimeError("Länklayout: veckonavigering saknas på huvudsidan")
    page = page[:nav] + link + "\n" + page[nav:]
    INDEX.write_text(page, encoding="utf-8")


def patch_goal():
    page = GOAL.read_text(encoding="utf-8")
    # Remove the old back link from the top row but keep the eyebrow/title area.
    page = re.sub(r'<a class="back" href="/träning/">← Veckoplan</a>', '', page)
    page = re.sub(r'<div class="goal-back-row">.*?</div>', '', page, flags=re.S)
    page = add_css(page, "/* goal-back-layout-v1 */", GOAL_CSS)
    link = '<div class="goal-back-row"><a href="/träning/">← Veckoplan</a></div>'
    card = page.find('<section class="card goal">')
    if card < 0:
        raise RuntimeError("Länklayout: kortet Övergripande mål saknas")
    page = page[:card] + link + "\n" + page[card:]
    GOAL.write_text(page, encoding="utf-8")


def main():
    patch_week()
    patch_goal()

    current = INDEX.read_text(encoding="utf-8")
    goal = GOAL.read_text(encoding="utf-8")
    if current.find('class="goal-page-link"') > current.find('<nav class="week-nav"'):
        raise RuntimeError("Länklayout: Målbild 2027 ligger inte ovanför veckonavigeringen")
    if goal.find('class="goal-back-row"') > goal.find('<section class="card goal">'):
        raise RuntimeError("Länklayout: Veckoplan-länken ligger inte ovanför Övergripande mål")
    print("Länklayout OK: båda länkarna högerjusterade på avsedd plats.")


if __name__ == "__main__":
    main()
