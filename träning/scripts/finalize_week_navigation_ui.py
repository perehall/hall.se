#!/usr/bin/env python3
"""Normalize week navigation across current, historical and upcoming pages."""

from __future__ import annotations

import html
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
PLAN = ROOT / "data" / "plan.json"
WEEKS = ROOT / "vecka"

CSS_MARKER = "/* unified-week-navigation-v1 */"
NAV_RE = re.compile(r'<nav class="(?:top-week-nav|week-nav)[^"]*"[^>]*>.*?</nav>', re.S)

MONTHS = {
    1:"jan",2:"feb",3:"mar",4:"apr",5:"maj",6:"jun",
    7:"jul",8:"aug",9:"sep",10:"okt",11:"nov",12:"dec"
}

CSS = r"""
/* unified-week-navigation-v1 */
.top-week-nav{
  display:grid;
  grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);
  align-items:center;
  gap:14px;
  margin:0;
  padding:2px 0 12px;
  border-bottom:1px solid var(--qp-line,#e2e8f0);
}
.top-week-link{
  color:var(--qp-secondary,#59636f);
  font-size:.78rem;
  font-weight:650;
  text-decoration:none;
  white-space:nowrap;
}
.top-week-link.next{text-align:right}
.top-week-link:hover{color:var(--qp-text,#111827)}
.top-week-link.disabled{color:var(--qp-tertiary,#94a3b8);font-weight:550}
.top-week-current{
  display:flex;
  align-items:baseline;
  justify-content:center;
  gap:6px;
  min-width:0;
  text-align:center;
}
.top-week-current strong{font-size:.92rem;font-weight:780;letter-spacing:-.01em}
.top-week-current span{color:var(--qp-tertiary,#64748b);font-size:.73rem;white-space:nowrap}
@media(max-width:620px){
  .top-week-nav{gap:8px}
  .top-week-link{font-size:.72rem}
  .top-week-current{display:grid;gap:0}
  .top-week-current strong{font-size:.86rem}
  .top-week-current span{font-size:.67rem}
}
""".strip()


def load_json(path: Path) -> dict:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def week_key_from_date(value: date) -> str:
    iso = value.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_date(key: str) -> date:
    year, week = key.split("-W")
    return date.fromisocalendar(int(year), int(week), 1)


def shift_week(key: str, delta: int) -> str:
    return week_key_from_date(week_date(key) + timedelta(days=7 * delta))


def week_number(key: str) -> int:
    return int(key.split("-W",1)[1])


def period(key: str) -> str:
    start = week_date(key)
    end = start + timedelta(days=6)
    if start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS[start.month]}"
    return f"{start.day} {MONTHS[start.month]}–{end.day} {MONTHS[end.month]}"


def available_week_keys(current_key: str) -> set[str]:
    keys = {current_key}
    if WEEKS.exists():
        for p in WEEKS.iterdir():
            if p.is_dir() and re.fullmatch(r"\d{4}-W\d{2}", p.name) and (p/"index.html").exists():
                keys.add(p.name)
    return keys


def href_for(key: str, current_key: str, available: set[str]) -> str | None:
    if key == current_key:
        return "/träning/"
    if key in available:
        return f"/träning/vecka/{key}/"
    return None


def state_for(key: str, current_key: str) -> str:
    if key == current_key:
        return "aktuell"
    return "historik" if week_date(key) < week_date(current_key) else "preliminär"


def nav_html(key: str, current_key: str, available: set[str]) -> str:
    previous_key = shift_week(key, -1)
    next_key = shift_week(key, 1)
    previous_href = href_for(previous_key, current_key, available)
    next_href = href_for(next_key, current_key, available)

    previous = (
        f'<a class="top-week-link prev" href="{html.escape(previous_href)}">‹ Vecka {week_number(previous_key)}</a>'
        if previous_href else
        f'<span class="top-week-link prev disabled">‹ Vecka {week_number(previous_key)}</span>'
    )
    next_item = (
        f'<a class="top-week-link next" href="{html.escape(next_href)}">Vecka {week_number(next_key)} ›</a>'
        if next_href else
        f'<span class="top-week-link next disabled">Vecka {week_number(next_key)} ›</span>'
    )

    state = state_for(key, current_key)
    middle = period(key)
    if state != "aktuell":
        middle += f" · {state}"

    return (
        '<nav class="top-week-nav" aria-label="Veckonavigering">'
        + previous
        + '<div class="top-week-current">'
        + f'<strong>Vecka {week_number(key)}</strong><span>{html.escape(middle)}</span>'
        + '</div>'
        + next_item
        + '</nav>'
    )


def install_css(page: str) -> str:
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Veckonavigation: </style> saknas")
    return page.replace("</style>", CSS + "\n</style>", 1)


def replace_nav(page: str, key: str, current_key: str, available: set[str]) -> str:
    rendered = nav_html(key, current_key, available)
    if NAV_RE.search(page):
        page = NAV_RE.sub(rendered, page, count=1)
    else:
        header_end = page.find("</header>")
        top_overview = page.find('<section class="top-overview"')
        if top_overview >= 0:
            insert = page.find(">", top_overview) + 1
            page = page[:insert] + rendered + page[insert:]
        elif header_end >= 0:
            insert = header_end + len("</header>")
            page = page[:insert] + "\n" + rendered + page[insert:]
        else:
            raise RuntimeError(f"Veckonavigation: kunde inte placera nav för {key}")
    return install_css(page)


def main() -> int:
    plan = load_json(PLAN)
    meta = plan.get("meta") or {}
    current_start = date.fromisoformat(str(meta["week_start"]))
    current_key = week_key_from_date(current_start)
    available = available_week_keys(current_key)

    pages = [(INDEX, current_key)]
    for key in sorted(available):
        if key == current_key:
            continue
        path = WEEKS / key / "index.html"
        if path.exists():
            pages.append((path,key))

    for path,key in pages:
        page = path.read_text(encoding="utf-8")
        page = replace_nav(page,key,current_key,available)
        path.write_text(page,encoding="utf-8")

    # navigation contract: adjacent semantics are identical on every page
    for path,key in pages:
        page = path.read_text(encoding="utf-8")
        if page.count('class="top-week-nav"') != 1:
            raise RuntimeError(f"Veckonavigation: exakt en nav krävs för {key}")
        if f"<strong>Vecka {week_number(key)}</strong>" not in page:
            raise RuntimeError(f"Veckonavigation: fel centrerad vecka för {key}")
        prev = shift_week(key,-1)
        nxt = shift_week(key,1)
        if f"Vecka {week_number(prev)}" not in page or f"Vecka {week_number(nxt)}" not in page:
            raise RuntimeError(f"Veckonavigation: föregående/nästa saknas för {key}")

    print(f"Veckonavigation OK: {len(pages)} sida/sidor delar samma föregående–aktuell–nästa-kontrakt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
