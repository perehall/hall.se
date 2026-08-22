#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
GOAL_PAGES = [
    ROOT / "malbild" / "index.html",
    ROOT / "malbild-2027" / "index.html",
]

WEEK_CSS = r'''
/* goal-link-layout-v1 */
.goal-page-link{display:flex;justify-content:flex-end;margin:0 0 8px}.goal-page-link a{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #ddd6fe;border-radius:12px;background:#faf5ff;color:#5b21b6;text-decoration:none;font-size:.78rem;font-weight:900;box-shadow:0 5px 14px rgba(76,29,149,.05)}
'''.strip()

GOAL_CSS = r'''
/* goal-back-layout-v1 */
.goal-back-row{display:flex;justify-content:flex-end;margin:12px 0 4px}.goal-back-row a{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #e2e8f0;border-radius:12px;background:#fff;color:#475569;text-decoration:none;font-size:.78rem;font-weight:900;box-shadow:0 5px 14px rgba(15,23,42,.04)}
'''.strip()

OLD_TRAIL = "M104 250 C157 246 203 236 245 219 C286 202 310 186 328 166 C345 147 367 150 383 132 C400 113 389 96 372 90 C357 85 360 70 378 61 C401 50 425 42 470 28"
NEW_TRAIL = "M104 250 C145 245 180 238 214 226 C248 214 278 199 306 184 C332 171 352 164 373 155 C394 146 413 140 430 133 C444 127 456 121 468 113"
OLD_FLAG = '<circle cx="470" cy="28" r="17" fill="#ecebff" opacity=".82"/><line x1="470" y1="18" x2="470" y2="47" stroke="#4938ee" stroke-width="3"/><path d="M470 18 L493 26 L470 34Z" fill="#4938ee"/>'
NEW_FLAG = '<circle cx="468" cy="113" r="15" fill="#ecebff" opacity=".72"/><line x1="468" y1="86" x2="468" y2="113" stroke="#4938ee" stroke-width="3"/><path d="M468 86 L490 94 L468 101Z" fill="#4938ee"/>'


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
    link = '<div class="goal-page-link"><a href="/träning/malbild-2027/">Målbild 2027 <span>→</span></a></div>'
    nav = page.find('<nav class="week-nav"')
    if nav < 0:
        raise RuntimeError("Länklayout: veckonavigering saknas på huvudsidan")
    page = page[:nav] + link + "\n" + page[nav:]
    INDEX.write_text(page, encoding="utf-8")


def patch_goal_page(path):
    if not path.exists():
        return
    page = path.read_text(encoding="utf-8")
    page = re.sub(r'<a class="back" href="/träning/">← Veckoplan</a>', '', page)
    page = re.sub(r'<div class="goal-back-row">.*?</div>', '', page, flags=re.S)
    page = add_css(page, "/* goal-back-layout-v1 */", GOAL_CSS)
    link = '<div class="goal-back-row"><a href="/träning/">← Veckoplan</a></div>'
    card = page.find('<section class="card goal">')
    if card < 0:
        raise RuntimeError(f"Länklayout: kortet Övergripande mål saknas i {path}")
    page = page[:card] + link + "\n" + page[card:]

    trail_count = page.count(OLD_TRAIL)
    if trail_count == 2:
        page = page.replace(OLD_TRAIL, NEW_TRAIL)
    elif page.count(NEW_TRAIL) != 2:
        raise RuntimeError(f"Målbild: förväntade två route-paths i {path}, hittade {trail_count}")

    if OLD_FLAG in page:
        page = page.replace(OLD_FLAG, NEW_FLAG, 1)
    elif NEW_FLAG not in page:
        raise RuntimeError(f"Målbild: flaggmarkering kunde inte identifieras i {path}")

    path.write_text(page, encoding="utf-8")


def main():
    patch_week()
    for path in GOAL_PAGES:
        patch_goal_page(path)

    current = INDEX.read_text(encoding="utf-8")
    if current.find('class="goal-page-link"') > current.find('<nav class="week-nav"'):
        raise RuntimeError("Länklayout: Målbild 2027 ligger inte ovanför veckonavigeringen")

    checked = 0
    for path in GOAL_PAGES:
        if not path.exists():
            continue
        checked += 1
        goal = path.read_text(encoding="utf-8")
        if goal.find('class="goal-back-row"') > goal.find('<section class="card goal">'):
            raise RuntimeError(f"Länklayout: Veckoplan-länken ligger inte ovanför Övergripande mål i {path}")
        if goal.count(NEW_TRAIL) != 2:
            raise RuntimeError(f"Målbild: nya bergsrutten saknas eller är duplicerad fel i {path}")
        if NEW_FLAG not in goal:
            raise RuntimeError(f"Målbild: nya flaggpositionen saknas i {path}")

    if checked == 0:
        raise RuntimeError("Målbild: ingen målbildssida hittades att validera")
    print("Målbild OK: rutt följer bergsmassan och flaggan sitter på bergsryggen.")


if __name__ == "__main__":
    main()
