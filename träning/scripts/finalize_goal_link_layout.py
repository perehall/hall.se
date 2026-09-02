#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
GOAL_PAGE = ROOT / "malbild" / "index.html"

WEEK_CSS = r'''
/* goal-link-layout-v3 */
.goal-page-link{display:flex;justify-content:flex-end;margin:0 0 8px}.goal-page-link a{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #e2e8f0;border-radius:12px;background:#fff;color:#475569;text-decoration:none;font-size:.78rem;font-weight:700;box-shadow:0 5px 14px rgba(15,23,42,.04)}
'''.strip()

GOAL_CSS = r'''
/* goal-back-layout-v3 */
.goal-back-row{display:flex;justify-content:flex-end;margin:12px 0 4px}.goal-back-row a{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #e2e8f0;border-radius:12px;background:#fff;color:#475569;text-decoration:none;font-size:.78rem;font-weight:700;box-shadow:0 5px 14px rgba(15,23,42,.04)}
'''.strip()


def add_css(page: str, marker: str, css: str) -> str:
    if marker in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Länklayout: </style> saknas")
    return page.replace("</style>", css + "\n</style>", 1)


def patch_week() -> None:
    page = INDEX.read_text(encoding="utf-8")
    page = re.sub(r'<div class="goal-home-link">.*?</div>', '', page, flags=re.S)
    page = re.sub(r'<div class="goal-page-link">.*?</div>', '', page, flags=re.S)
    page = re.sub(r'/\* goal-link-layout-v2 \*/.*?(?=(?:/\*|</style>))', '', page, flags=re.S)
    page = add_css(page, "/* goal-link-layout-v3 */", WEEK_CSS)

    nav = page.find('<nav class="week-nav"')
    if nav < 0:
        raise RuntimeError("Länklayout: veckonavigering saknas på huvudsidan")

    link = '<div class="goal-page-link"><a href="/träning/malbild-2027/">Målbild 2027 <span>→</span></a></div>'
    page = page[:nav] + link + "\n" + page[nav:]
    INDEX.write_text(page, encoding="utf-8")


def patch_goal_page() -> None:
    if not GOAL_PAGE.exists():
        raise RuntimeError("Länklayout: canonical målbildssida saknas")

    page = GOAL_PAGE.read_text(encoding="utf-8")
    page = re.sub(r'<a class="back" href="/träning/">← Veckoplan</a>', '', page)
    page = re.sub(r'<div class="goal-back-row">.*?</div>', '', page, flags=re.S)
    page = re.sub(r'/\* goal-back-layout-v2 \*/.*?(?=(?:/\*|</style>))', '', page, flags=re.S)
    page = add_css(page, "/* goal-back-layout-v3 */", GOAL_CSS)

    card = page.find('<section class="card goal">')
    if card < 0:
        raise RuntimeError("Länklayout: kortet Övergripande mål saknas")

    link = '<div class="goal-back-row"><a href="/träning/">← Veckoplan</a></div>'
    page = page[:card] + link + "\n" + page[card:]
    GOAL_PAGE.write_text(page, encoding="utf-8")


def validate() -> None:
    current = INDEX.read_text(encoding="utf-8")
    if current.count('class="goal-page-link"') != 1:
        raise RuntimeError("Länklayout: huvudsidan ska ha exakt en Målbild-länk")
    if 'href="/träning/malbild-2027/"' not in current:
        raise RuntimeError("Länklayout: Målbild-länken pekar inte på publicerad målbildsväg")
    if current.find('class="goal-page-link"') > current.find('<nav class="week-nav"'):
        raise RuntimeError("Länklayout: Målbild 2027 ligger inte ovanför veckonavigeringen")

    goal = GOAL_PAGE.read_text(encoding="utf-8")
    if goal.count('class="goal-back-row"') != 1:
        raise RuntimeError("Länklayout: målbilden ska ha exakt en Veckoplan-länk")
    if goal.find('class="goal-back-row"') > goal.find('<section class="card goal">'):
        raise RuntimeError("Länklayout: Veckoplan-länken ligger inte ovanför Övergripande mål")
    if goal.count('data-goal-hierarchy="true"') != 1:
        raise RuntimeError("Länklayout: canonical målbild saknar planeringshierarki")
    if goal.count('data-current-mesocycle="true"') != 1:
        raise RuntimeError("Länklayout: canonical målbild saknar aktuell mesocykel")


def main() -> None:
    patch_week()
    patch_goal_page()
    validate()
    print("Målbildslayout OK: fram- och tillbakalänk delar neutral visuell stil.")


if __name__ == "__main__":
    main()
