#!/usr/bin/env python3
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "data" / "plan.json"
UPCOMING = ROOT / "data" / "upcoming_week.json"
INDEX = ROOT / "index.html"
WEEK_DIR = ROOT / "vecka"
CSS_MARKER = "/* goal-home-link-v1 */"
CSS = '.goal-home-link{margin:-4px 0 10px}.goal-home-link a{display:inline-flex;align-items:center;gap:6px;color:#4f46e5;text-decoration:none;font-size:.78rem;font-weight:850}.goal-home-link a:hover{text-decoration:underline}'


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def key(meta):
    d = date.fromisoformat(meta["week_start"])
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def patch(path):
    if not path.exists():
        return
    page = path.read_text(encoding="utf-8")
    if CSS_MARKER not in page:
        page = page.replace("</style>", CSS_MARKER + CSS + "</style>", 1)
    if 'class="goal-home-link"' not in page:
        nav = '<div class="goal-home-link"><a href="/träning/">← Målbild 2027</a></div>'
        pos = page.find('<nav class="week-nav"')
        if pos >= 0:
            page = page[:pos] + nav + page[pos:]
        else:
            pos = page.find("</header>")
            if pos >= 0:
                pos += len("</header>")
                page = page[:pos] + nav + page[pos:]
    path.write_text(page, encoding="utf-8")


def main():
    plan = load(PLAN)
    current_key = key(plan["meta"])
    patch(INDEX)
    if UPCOMING.exists():
        upcoming = load(UPCOMING)
        up_key = upcoming.get("week_key") or key(upcoming["meta"])
        patch(WEEK_DIR / up_key / "index.html")
    print(f"Veckonavigation OK: länk till Målbild 2027 tillagd för {current_key} och kommande vecka.")


if __name__ == "__main__":
    main()
