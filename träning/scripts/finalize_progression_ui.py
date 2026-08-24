#!/usr/bin/env python3
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
CURRENT_INDEX = ROOT / "index.html"
PAGES_DIR = ROOT / "vecka"

CSS_MARKER = "/* development-focus-v1 */"
CSS = r'''
/* development-focus-v1 */
.development-focus{margin-top:11px;padding:10px 12px;border:1px solid #c7d2fe;border-radius:12px;background:#f8faff;display:grid;gap:3px}.development-focus strong{color:#4338ca;font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.07em}.development-focus span{color:#312e81;font-size:.88rem;line-height:1.42}
/* development-focus-v1 */
'''.strip()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def split_swim_reason(reason):
    if "Förslag:" not in reason:
        return reason.strip(), [], ""
    prefix, remainder = reason.split("Förslag:", 1)
    remainder = remainder.strip()
    if ". " in remainder:
        set_text, suffix = remainder.split(". ", 1)
    else:
        set_text, suffix = remainder.rstrip("."), ""
    sets = [item.strip() for item in set_text.split(" + ") if item.strip()]
    return prefix.strip(), sets, suffix.strip()


def normalize_swim_set(text):
    text = text.strip().rstrip(".")
    text = re.sub(r"\s*×\s*", "×", text)
    return text


def swim_set_html(sets):
    rows = []
    for item in sets:
        normalized = normalize_swim_set(item)
        match = re.match(r"^(\d+(?:×\d+)?\s*m)\s*(.*)$", normalized)
        if match:
            dose, description = match.groups()
            rows.append(
                '<div class="swim-set-row">'
                f'<span class="swim-dose">{html.escape(dose)}</span>'
                f'<span>{html.escape(description)}</span>'
                '</div>'
            )
        else:
            rows.append(
                '<div class="swim-set-row">'
                f'<span>{html.escape(normalized)}</span>'
                '</div>'
            )
    return f'<div class="swim-set-list">{"".join(rows)}</div>'


def add_css(page):
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Progressions-UI: sidan saknar </style>")
    return page.replace("</style>", CSS + "\n</style>", 1)


def card_bounds(page, date):
    marker = f'<div class="day" id="dag-{html.escape(date)}">'
    start = page.find(marker)
    if start < 0:
        raise RuntimeError(f"Progressions-UI: dagkort saknas för {date}")
    next_start = page.find('<div class="day" id="dag-', start + len(marker))
    if next_start < 0:
        section_end = page.find('<h2 class="section">', start + len(marker))
        footer = page.find("<footer", start + len(marker))
        candidates = [value for value in (section_end, footer) if value >= 0]
        next_start = min(candidates) if candidates else len(page)
    return start, next_start


def inject_focus(page, day):
    sport = day.get("sport")
    if sport in {"open", "rest"}:
        return page
    focus = str(day.get("development_focus") or "").strip()
    if not focus:
        raise RuntimeError(
            f"Progressions-UI: {day.get('date')} {sport} saknar development_focus"
        )
    start, end = card_bounds(page, day["date"])
    segment = page[start:end]
    if 'class="development-focus"' in segment:
        return page
    closing = segment.rfind("</div>")
    if closing < 0:
        raise RuntimeError(f"Progressions-UI: kunde inte avsluta dagkort {day['date']}")
    block = (
        '<div class="development-focus"><strong>Utvecklingsfokus</strong>'
        f'<span>{html.escape(focus)}</span></div>'
    )
    segment = segment[:closing] + block + segment[closing:]
    return page[:start] + segment + page[end:]


def render_preview_swim(page, day):
    if day.get("sport") != "swim":
        return page
    prefix, sets, suffix = split_swim_reason(str(day.get("reason") or ""))
    if not sets:
        raise RuntimeError(
            f"Progressions-UI: preliminärt simpass {day.get('date')} saknar utskrivet Förslag-set"
        )
    start, end = card_bounds(page, day["date"])
    segment = page[start:end]
    escaped_reason = html.escape(str(day.get("reason") or ""))
    needle = f'<div class="reason">{escaped_reason}</div>'
    if needle not in segment:
        if 'class="swim-set-list"' in segment:
            return page
        raise RuntimeError(
            f"Progressions-UI: kunde inte hitta simmotivering för {day.get('date')}"
        )
    parts = []
    if prefix:
        parts.append(f'<div class="reason">{html.escape(prefix)}</div>')
    parts.append(swim_set_html(sets))
    if suffix:
        parts.append(f'<div class="reason">{html.escape(suffix)}</div>')
    segment = segment.replace(needle, "".join(parts), 1)
    return page[:start] + segment + page[end:]


def validate_page(page, document, *, preview=False):
    for day in document.get("days", []):
        sport = day.get("sport")
        if sport not in {"open", "rest"}:
            start, end = card_bounds(page, day["date"])
            segment = page[start:end]
            if 'class="development-focus"' not in segment:
                raise RuntimeError(
                    f"Progressions-UI: utvecklingsfokus renderades inte för {day['date']}"
                )
        if preview and sport == "swim":
            start, end = card_bounds(page, day["date"])
            segment = page[start:end]
            if 'class="swim-set-list"' not in segment:
                raise RuntimeError(
                    f"Progressions-UI: simset renderades inte för {day['date']}"
                )
            if "Hjälpmedel:" not in segment:
                raise RuntimeError(
                    f"Progressions-UI: hjälpmedel saknas för simpass {day['date']}"
                )


def patch_page(path, document, *, preview=False):
    page = add_css(path.read_text(encoding="utf-8"))
    if preview:
        for day in document.get("days", []):
            page = render_preview_swim(page, day)
    for day in document.get("days", []):
        page = inject_focus(page, day)
    validate_page(page, document, preview=preview)
    path.write_text(page, encoding="utf-8")


def main():
    plan = load_json(PLAN_FILE)
    upcoming = load_json(UPCOMING_FILE)
    patch_page(CURRENT_INDEX, plan, preview=False)

    upcoming_key = str(upcoming.get("week_key") or "").strip()
    if not upcoming_key:
        raise RuntimeError("Progressions-UI: upcoming_week.week_key saknas")
    upcoming_page = PAGES_DIR / upcoming_key / "index.html"
    if not upcoming_page.exists():
        raise RuntimeError(f"Progressions-UI: framtidssida saknas: {upcoming_key}")
    patch_page(upcoming_page, upcoming, preview=True)

    current_focuses = sum(
        1 for day in plan.get("days", []) if day.get("sport") not in {"open", "rest"}
    )
    preview_swims = sum(1 for day in upcoming.get("days", []) if day.get("sport") == "swim")
    print(
        f"Progressions-UI OK: {current_focuses} aktuella pass med utvecklingsfokus, "
        f"{preview_swims} preliminära simpass fullt utskrivna."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
