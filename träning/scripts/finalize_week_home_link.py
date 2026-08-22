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
CSS_MARKER = "/* goal-page-link-v1 */"
CSS = '.goal-page-link{display:flex;justify-content:flex-end;margin:0 0 8px}.goal-page-link a{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #ddd6fe;border-radius:12px;background:#faf5ff;color:#5b21b6;text-decoration:none;font-size:.78rem;font-weight:900;box-shadow:0 5px 14px rgba(76,29,149,.05)}'


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

    # Remove obsolete earlier variants to avoid duplicate goal links.
    page = re.sub(r'<div class="goal-home-link">.*?</div>', '', page, flags=re.S)
    page = re.sub(r'<div class="goal-page-link">.*?</div>', '', page, flags=re.S)

    if CSS_MARKER not in page:
        page = page.replace("</style>", CSS_MARKER + CSS + "</style>", 1)

    link = '<div class="goal-page-link"><a href="/träning/malbild/">Målbild 2027 <span>→</span></a></div>'
    pos = page.find('<nav class="week-nav"')
    if pos >= 0:
        page = page[:pos] + link + "\n" + page[pos:]
    else:
        pos = page.find("</header>")
        if pos >= 0:
            pos += len("</header>")
            page = page[:pos] + "\n" + link + page[pos:]

    path.write_text(page, encoding="utf-8")


def main():
    plan = load(PLAN)
    current_key = key(plan["meta"])
    patch(INDEX)
    if UPCOMING.exists():
        upcoming = load(UPCOMING)
        up_key = upcoming.get("week_key") or key(upcoming["meta"])
        patch(WEEK_DIR / up_key / "index.html")
    print(f"Veckonavigation OK: Målbild 2027 ligger högerjusterad ovanför veckonavigeringen för {current_key} och kommande vecka.")


if __name__ == "__main__":
    main()
