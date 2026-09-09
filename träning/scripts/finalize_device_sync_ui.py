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
CSS_MARKER = "/* device-sync-ui-v1 */"
CSS = r'''
/* device-sync-ui-v1 */
.device-sync-state{display:flex;align-items:center;gap:6px;width:max-content;max-width:100%;margin:7px 0 4px;padding:4px 8px;border:1px solid #d8dee8;border-radius:999px;background:#f8fafc;color:#475569;font-size:.68rem;font-weight:800;line-height:1.2}.device-sync-state svg{width:13px;height:13px;flex:0 0 auto}.device-sync-state.pending{color:#64748b}.device-sync-state.error{border-color:#f1c7c7;background:#fffafa;color:#991b1b}.future-compact .device-sync-state,.past-completed .device-sync-state,.today-completed .device-sync-state{display:none}
'''.strip()

WATCH_ICON = (
    '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="7" y="5" width="10" height="14" rx="2.2"/>'
    '<path d="M9.5 5V2.5h5V5M9.5 19v2.5h5V19M12 9v3l2 1.5"/></svg>'
)

STATUS_COPY = {
    "synced": "Klocksync skickad",
    "pending": "Klocksync väntar",
    "error": "Klocksync fel",
}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def card_bounds(page, date):
    pattern = re.compile(rf'<div class="day[^"]*" id="dag-{re.escape(date)}">')
    match = pattern.search(page)
    if not match:
        return None
    next_match = re.search(r'<div class="day[^"]*" id="dag-\d{{4}}-\d{{2}}-\d{{2}}">', page[match.end():])
    end = match.end() + next_match.start() if next_match else len(page)
    return match.start(), end


def chip(day):
    sync = day.get("device_sync") or {}
    status = sync.get("status")
    label = STATUS_COPY.get(status)
    if not label:
        return ""
    title = (
        "Passet är verifierat i Intervals.icu och kan därifrån skickas vidare till Garmin; "
        "leverans till själva klockan kan inte verifieras av träningssystemet."
        if status == "synced"
        else "Strukturerat pass väntar på transport via Intervals.icu till Garmin."
        if status == "pending"
        else "Transporten via Intervals.icu misslyckades senast och försöks igen i nästa träningsjobb."
    )
    return (
        f'<div class="device-sync-state {html.escape(status)}" title="{html.escape(title)}">'
        f'{WATCH_ICON}<span>{html.escape(label)}</span></div>'
    )


def patch_page(path, document):
    if not path.exists():
        return 0
    page = path.read_text(encoding="utf-8")
    if CSS_MARKER not in page:
        if "</style>" not in page:
            raise RuntimeError(f"Device-sync UI: {path} saknar </style>")
        page = page.replace("</style>", CSS + "\n</style>", 1)

    inserted = 0
    for day in document.get("days") or []:
        block = chip(day)
        if not block:
            continue
        bounds = card_bounds(page, str(day.get("date") or ""))
        if bounds is None:
            continue
        start, end = bounds
        segment = page[start:end]
        if 'class="device-sync-state ' in segment:
            continue
        anchors = [
            segment.find('<div class="workout-prescription">'),
            segment.find('<details class="day-why">'),
            segment.find('<div class="reason">'),
        ]
        anchors = [position for position in anchors if position >= 0]
        if not anchors:
            raise RuntimeError(f"Device-sync UI: saknar placeringspunkt för {day.get('date')}")
        position = min(anchors)
        segment = segment[:position] + block + segment[position:]
        page = page[:start] + segment + page[end:]
        inserted += 1

    path.write_text(page, encoding="utf-8")
    return inserted


def main():
    plan = load_json(PLAN_FILE)
    upcoming = load_json(UPCOMING_FILE)
    count = patch_page(CURRENT_INDEX, plan)
    week_key = str(upcoming.get("week_key") or "").strip()
    if week_key:
        count += patch_page(PAGES_DIR / week_key / "index.html", upcoming)

    rendered = CURRENT_INDEX.read_text(encoding="utf-8")
    if CSS_MARKER not in rendered:
        raise RuntimeError("Device-sync UI: CSS-marker saknas")
    expected = sum(
        1
        for day in plan.get("days") or []
        if (day.get("device_sync") or {}).get("status") in STATUS_COPY
    )
    actual = rendered.count('class="device-sync-state ')
    if actual < expected:
        raise RuntimeError(f"Device-sync UI: saknar statuschip ({actual} < {expected})")
    print(f"Device-sync UI OK: {count} statuschip renderade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
