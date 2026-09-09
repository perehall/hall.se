#!/usr/bin/env python3
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
CURRENT_INDEX = ROOT / "index.html"
PAGES_DIR = ROOT / "vecka"

CSS_MARKER = "/* workout-card-v2 */"
CSS = r'''
/* workout-card-v2 */
.day.workout-card-v2{border-radius:15px;border-color:#e5eaf1;padding:16px 17px;box-shadow:0 1px 2px rgba(15,23,42,.035),0 6px 16px rgba(15,23,42,.025)}
.day.workout-card-v2.card-v2-today{border-color:#bfdbfe;box-shadow:inset 3px 0 0 #2563eb,0 1px 2px rgba(15,23,42,.035),0 6px 16px rgba(15,23,42,.025)}
.workout-card-v2 .daytop{margin-bottom:10px}.workout-card-v2 .session{margin:0 0 2px}.workout-card-v2 .session-title{letter-spacing:-.012em}
.workout-card-v2 .workout-prescription{margin:13px 0 3px;padding:0;border:0;border-radius:0;background:transparent;display:grid;gap:2px}.workout-card-v2 .workout-prescription-head{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.workout-card-v2 .workout-prescription-row{display:grid;grid-template-columns:minmax(78px,max-content) 1fr;gap:12px;padding:3px 0;border:0;align-items:baseline}.workout-card-v2 .workout-prescription-dose{font-weight:800;color:#0f172a;font-variant-numeric:tabular-nums}.workout-card-v2 .workout-prescription-text{color:#334155;line-height:1.38}
.workout-card-v2 .development-focus{display:flex;align-items:baseline;gap:4px;margin-top:9px;padding:0;border:0;border-radius:0;background:transparent}.workout-card-v2 .development-focus strong{flex:0 0 auto;color:#64748b;font-size:.78rem;font-weight:650;text-transform:none;letter-spacing:0}.workout-card-v2 .development-focus span{color:#475569;font-size:.84rem;line-height:1.42}
.card-v2-footer{display:flex;align-items:center;gap:12px;margin-top:13px;padding-top:9px;border-top:1px solid #eef2f7;min-height:26px}.card-v2-footer .day-why{margin:0}.card-v2-footer .day-why>summary{font-size:.76rem;font-weight:600;color:#64748b}.card-v2-footer .device-sync-state{margin:0 0 0 auto;padding:0;border:0;border-radius:0;background:transparent;color:#64748b;font-size:.68rem;font-weight:650}.card-v2-footer .device-sync-state.pending{color:#64748b}.card-v2-footer .device-sync-state.error{background:transparent;border:0;color:#991b1b}.card-v2-footer .device-sync-state svg{width:12px;height:12px}
.day.workout-card-v2.past-completed,.day.workout-card-v2.future-compact{padding:11px 12px;border-radius:14px;box-shadow:0 1px 2px rgba(15,23,42,.025)}.past-completed .card-v2-footer,.future-compact .card-v2-footer,.today-completed .card-v2-footer{display:none}
@media (max-width:520px){.day.workout-card-v2{padding:14px 15px;border-radius:14px}.day.workout-card-v2.past-completed,.day.workout-card-v2.future-compact{padding:10px 11px}.workout-card-v2 .workout-prescription-row{grid-template-columns:72px 1fr;gap:9px;padding:3px 0}.card-v2-footer{gap:9px;margin-top:11px;padding-top:8px}}
/* workout-card-v2 */
'''.strip()

DAY_OPEN_RE = re.compile(r'<div class="day(?P<classes>[^"]*)" id="dag-(?P<date>\d{4}-\d{2}-\d{2})">')
DIV_TAG_RE = re.compile(r'<div\b[^>]*>|</div>')
WHY_RE = re.compile(r'<details class="day-why">.*?</details>', re.S)
RAW_REASON_RE = re.compile(r'<div class="reason">(.*?)</div>', re.S)
SYNC_START_RE = re.compile(r'<div class="device-sync-state [^"]+"[^>]*>')


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def add_css(page):
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Card v2: sidan saknar </style>")
    return page.replace("</style>", CSS + "\n</style>", 1)


def balanced_div_close(text, start):
    depth = 0
    for match in DIV_TAG_RE.finditer(text, start):
        token = match.group(0)
        if token.startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return match.start(), match.end()
    raise RuntimeError("Card v2: obalanserad div-struktur")


def card_ranges(page):
    matches = list(DAY_OPEN_RE.finditer(page))
    ranges = []
    for match in matches:
        _, end = balanced_div_close(page, match.start())
        ranges.append((match.start(), end, match.group("date")))
    return ranges


def extract_sync(block):
    match = SYNC_START_RE.search(block)
    if not match:
        return block, ""
    _, end = balanced_div_close(block, match.start())
    sync = block[match.start():end]
    return block[:match.start()] + block[end:], sync


def extract_why(block):
    match = WHY_RE.search(block)
    if match:
        return block[:match.start()] + block[match.end():], match.group(0)
    reason = RAW_REASON_RE.search(block)
    if not reason:
        return block, ""
    why = (
        '<details class="day-why"><summary>Motivering</summary>'
        f'<div class="reason">{reason.group(1)}</div></details>'
    )
    return block[:reason.start()] + block[reason.end():], why


def transform_card(block, *, day_text, today_text):
    opening = DAY_OPEN_RE.match(block)
    if not opening:
        raise RuntimeError(f"Card v2: ogiltigt dagkort {day_text}")
    classes = [token for token in (opening.group("classes") or "").split() if token]
    if "workout-card-v2" in classes:
        return block
    classes.append("workout-card-v2")
    if day_text == today_text:
        classes.append("card-v2-today")
    opening_html = f'<div class="day {" ".join(classes)}" id="dag-{day_text}">'
    block = opening_html + block[opening.end():]

    block = block.replace("<strong>Passfokus</strong>", "<strong>Fokus:</strong>")
    block = block.replace("<strong>Utvecklingsfokus</strong>", "<strong>Fokus:</strong>")

    block, sync = extract_sync(block)
    block, why = extract_why(block)
    if sync or why:
        close_start, _ = balanced_div_close(block, 0)
        footer = '<div class="card-v2-footer">' + why + sync + '</div>'
        block = block[:close_start] + footer + block[close_start:]
    return block


def apply_card_v2(page, *, today_text):
    page = add_css(page)
    for start, end, day_text in reversed(card_ranges(page)):
        transformed = transform_card(page[start:end], day_text=day_text, today_text=today_text)
        page = page[:start] + transformed + page[end:]
    return page


def validate_page(page):
    if CSS_MARKER not in page:
        raise RuntimeError("Card v2: CSS-marker saknas")
    ranges = card_ranges(page)
    if not ranges:
        raise RuntimeError("Card v2: inga dagkort hittades")
    for start, end, day_text in ranges:
        block = page[start:end]
        opening = DAY_OPEN_RE.match(block)
        if not opening or "workout-card-v2" not in opening.group("classes"):
            raise RuntimeError(f"Card v2: klass saknas på {day_text}")
        if "<strong>Passfokus</strong>" in block or "<strong>Utvecklingsfokus</strong>" in block:
            raise RuntimeError(f"Card v2: gammal fokuslabel kvar på {day_text}")
        if 'class="device-sync-state ' in block and 'class="card-v2-footer"' not in block:
            raise RuntimeError(f"Card v2: klocksync ligger inte i footer på {day_text}")
        if 'class="day-why"' in block and 'class="card-v2-footer"' not in block:
            raise RuntimeError(f"Card v2: motivering ligger inte i footer på {day_text}")
        if 'class="workout-prescription"' in block and 'class="card-v2-footer"' in block:
            if block.find('class="card-v2-footer"') < block.find('class="workout-prescription"'):
                raise RuntimeError(f"Card v2: footer ligger före passrecept på {day_text}")


def patch_page(path, *, today_text):
    if not path.exists():
        return 0
    page = apply_card_v2(path.read_text(encoding="utf-8"), today_text=today_text)
    validate_page(page)
    path.write_text(page, encoding="utf-8")
    return len(card_ranges(page))


def main():
    plan = load_json(PLAN_FILE)
    timezone = str((plan.get("meta") or {}).get("timezone") or "Europe/Stockholm")
    today_text = datetime.now(ZoneInfo(timezone)).date().isoformat()
    count = patch_page(CURRENT_INDEX, today_text=today_text)

    upcoming = load_json(UPCOMING_FILE)
    week_key = str(upcoming.get("week_key") or "").strip()
    if week_key:
        count += patch_page(PAGES_DIR / week_key / "index.html", today_text=today_text)

    print(f"Card v2 UX OK: {count} dagkort plattade och prioriterade efter passrecept.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
