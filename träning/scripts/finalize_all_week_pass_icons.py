#!/usr/bin/env python3
"""Enforce sport icons on every rendered week page.

This runs after current/history/future week pages have reached their final
layout. It uses structured plan data for each week and decorates the visible
workout title on that page. Rest/open days are intentionally iconless.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from finalize_day_session_icons import SPORT_ICON_KEYS, icon

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
WEEKS_DATA = ROOT / "data" / "weeks"
WEEKS_PAGES = ROOT / "vecka"
ICON_FILE = ROOT / "data" / "sport_icons.json"

CSS_MARKER = "/* all-week-pass-icons-v1 */"
DIV_RE = re.compile(r"<div\b[^>]*>|</div>", re.I)
OPEN_DIV_RE = re.compile(r'<div\b[^>]*class="([^"]*)"[^>]*>', re.I)

CSS = r"""
/* all-week-pass-icons-v1 */
.week-pass-session{
  display:flex!important;
  align-items:flex-start!important;
  gap:8px!important;
}
.week-pass-icon-group{
  display:inline-flex;
  align-items:center;
  gap:4px;
  flex:0 0 auto;
  padding-top:1px;
  color:var(--qp-secondary,#64748b);
}
.week-pass-icon-group .sport-icon{
  width:19px;
  height:19px;
  flex:0 0 auto;
}
.week-pass-icon-group .icon-swim,
.week-pass-icon-group .icon-bike,
.week-pass-icon-group .icon-enduro,
.week-pass-icon-group .icon-strength{width:21px}
.week-pass-session-text{min-width:0}
@media(max-width:620px){
  .week-pass-icon-group .sport-icon{width:18px;height:18px}
  .week-pass-icon-group .icon-swim,
  .week-pass-icon-group .icon-bike,
  .week-pass-icon-group .icon-enduro,
  .week-pass-icon-group .icon-strength{width:20px}
}
""".strip()


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def week_key_from_plan(plan: dict) -> str:
    meta = plan.get("meta") or {}
    start = str(meta.get("week_start") or "")
    if len(start) < 10:
        raise RuntimeError("Alla veckikoner: plan.meta.week_start saknas")
    from datetime import date
    value = date.fromisoformat(start[:10])
    iso = value.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def balanced_div_end(text: str, start: int) -> int:
    depth = 0
    for match in DIV_RE.finditer(text, start):
        if match.group(0).lower().startswith("</div"):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    raise RuntimeError("Alla veckikoner: obalanserad div-struktur")


def day_blocks(page: str) -> list[tuple[int, int, str]]:
    blocks = []
    for match in OPEN_DIV_RE.finditer(page):
        classes = match.group(1).split()
        if "day" not in classes:
            continue
        start = match.start()
        end = balanced_div_end(page, start)
        blocks.append((start, end, page[start:end]))
    return blocks


def explicit_icon_keys(day: dict) -> list[str]:
    sport = str(day.get("sport") or "").strip().lower()
    session = str(day.get("session") or "").strip().lower()

    keys: list[str] = []

    def add(key: str | None) -> None:
        if key and key not in keys:
            keys.append(key)

    if sport:
        if sport not in SPORT_ICON_KEYS:
            raise RuntimeError(
                f"Alla veckikoner: okänd explicit sport {sport!r} för {day.get('date')}"
            )
        add(SPORT_ICON_KEYS[sport])

    # Multi-sport/combo days should show every sport that is explicitly named
    # in the actual session title, not only the primary planning sport.
    if "swimrun" in session:
        add("swim")
        add("run")
    else:
        if "simning" in session or "sim " in session:
            add("swim")
        if "löpning" in session or "trail" in session:
            add("run")
    if "mtb" in session or "xc" in session or "cykel" in session:
        add("bike")
    if "enduro" in session:
        add("enduro")
    if "styrka" in session or "core" in session:
        add("strength")

    return keys


def render_icon_group(keys: list[str], registry: dict) -> str:
    joined = ",".join(keys)
    icons = "".join(icon(key, registry) for key in keys)
    return (
        f'<span class="week-pass-icon-group" data-week-pass-icons="{html.escape(joined)}">'
        + icons
        + "</span>"
    )


def add_css(page: str) -> str:
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Alla veckikoner: </style> saknas")
    return page.replace("</style>", CSS + "\n</style>", 1)


def visible_target_has_icon(block: str) -> bool:
    targets = (
        r'<div class="completed-day-title">(.*?)</div>',
        r'<div class="future-workout-title">(.*?)</div>',
        r'<div class="session(?: [^"]*)?">(.*?)</div>',
    )
    for pattern in targets:
        match = re.search(pattern, block, re.S | re.I)
        if match:
            return 'class="sport-icon ' in match.group(1)
    return False


def decorate_raw_session(block: str, keys: list[str], registry: dict) -> str:
    match = re.search(
        r'<div class="session(?P<classes>[^"]*)">(?P<body>.*?)</div>',
        block,
        re.S | re.I,
    )
    if not match:
        return block

    body = match.group("body")
    if 'class="sport-icon ' in body:
        return block

    classes = match.group("classes").split()
    if "week-pass-session" not in classes:
        classes.append("week-pass-session")
    class_text = " ".join(["session"] + classes).strip()
    replacement = (
        f'<div class="{html.escape(class_text)}">'
        + render_icon_group(keys, registry)
        + f'<span class="week-pass-session-text">{body}</span></div>'
    )
    return block[:match.start()] + replacement + block[match.end():]


def decorate_visible_title(block: str, keys: list[str], registry: dict) -> str:
    if not keys:
        return block
    if visible_target_has_icon(block):
        return block

    # History and the standalone upcoming-week preview use a plain .session.
    decorated = decorate_raw_session(block, keys, registry)
    if decorated != block:
        return decorated

    # Fail closed rather than silently publishing a sport pass without an icon.
    raise RuntimeError("Alla veckikoner: hittade inget synligt passnamn att dekorera")


def map_days_to_blocks(page: str, days: list[dict]) -> list[tuple[dict, int, int, str]]:
    blocks = day_blocks(page)
    if len(blocks) < len(days):
        raise RuntimeError(
            f"Alla veckikoner: sidan har {len(blocks)} dagkort men planen {len(days)} dagar"
        )

    by_id = {}
    for start, end, block in blocks:
        match = re.search(r'id="dag-(\d{4}-\d{2}-\d{2})"', block[:300])
        if match:
            by_id[match.group(1)] = (start, end, block)

    mapped = []
    if all(str(day.get("date") or "") in by_id for day in days):
        for day in days:
            start, end, block = by_id[str(day.get("date"))]
            mapped.append((day, start, end, block))
        return mapped

    # Historical pages intentionally predate stable day IDs. Their seven day
    # cards are generated in plan order from the archived snapshot.
    plan_days = [day for day in days if day.get("date")]
    if len(blocks) != len(plan_days):
        raise RuntimeError(
            "Alla veckikoner: historiksidan kan inte mappas säkert mot snapshot-planen"
        )
    return [
        (day, start, end, block)
        for day, (start, end, block) in zip(plan_days, blocks)
    ]


def decorate_page(page: str, days: list[dict], registry: dict) -> tuple[str, int]:
    mapped = map_days_to_blocks(page, days)
    changed = 0

    for day, start, end, block in reversed(mapped):
        keys = explicit_icon_keys(day)
        if not keys:
            continue

        # Current-page completed/future shells already own their visible icon
        # placement. This final stage verifies them and decorates only pages that
        # still expose the raw session row.
        if visible_target_has_icon(block):
            continue

        updated = decorate_visible_title(block, keys, registry)
        if updated == block:
            continue
        page = page[:start] + updated + page[end:]
        changed += 1

    return add_css(page), changed


def verify_page(page: str, days: list[dict]) -> None:
    mapped = map_days_to_blocks(page, days)
    for day, _, _, block in mapped:
        keys = explicit_icon_keys(day)
        if not keys:
            continue
        if not visible_target_has_icon(block):
            raise RuntimeError(
                f"Alla veckikoner: synlig grenikon saknas för {day.get('date')}"
            )


def snapshot_plan(key: str) -> dict:
    path = WEEKS_DATA / f"{key}.json"
    state = load_json(path, {})
    plan = state.get("plan") or {}
    if not plan:
        raise RuntimeError(f"Alla veckikoner: snapshot-plan saknas för {key}")
    return plan


def main() -> int:
    plan = load_json(PLAN_FILE, {"days": [], "meta": {}})
    upcoming = load_json(UPCOMING_FILE, {})
    registry = load_json(ICON_FILE, {"icons": {}}).get("icons") or {}
    current_key = week_key_from_plan(plan)
    upcoming_key = str(upcoming.get("week_key") or "")

    pages: list[tuple[Path, list[dict], str]] = [
        (INDEX, list(plan.get("days") or []), current_key)
    ]

    if WEEKS_PAGES.exists():
        for folder in sorted(WEEKS_PAGES.iterdir()):
            if not folder.is_dir() or not re.fullmatch(r"\d{4}-W\d{2}", folder.name):
                continue
            path = folder / "index.html"
            if not path.exists():
                continue
            if folder.name == upcoming_key:
                days = list(upcoming.get("days") or [])
            elif folder.name == current_key:
                continue
            else:
                days = list((snapshot_plan(folder.name).get("days") or []))
            pages.append((path, days, folder.name))

    total = 0
    for path, days, _ in pages:
        rendered, changed = decorate_page(path.read_text(encoding="utf-8"), days, registry)
        verify_page(rendered, days)
        path.write_text(rendered, encoding="utf-8")
        total += changed

    print(
        f"Alla veckikoner OK: {len(pages)} vecka/sidor verifierade, "
        f"{total} synliga passrubriker dekorerade."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
