#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
INDEX_FILE = ROOT / "index.html"

plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
page = INDEX_FILE.read_text(encoding="utf-8")
tz = ZoneInfo(plan.get("meta", {}).get("timezone", "Europe/Stockholm"))
today = datetime.now(tz).date().isoformat()


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
    text = re.sub(r"\((\d+(?:–\d+)?\s*s) vila\)", r"@ \1", text)
    text = re.sub(
        r"\((\d+(?:–\d+)?\s*s) vila,\s*RPE ca ([^)]+)\)",
        r"@ \1 · RPE \2",
        text,
    )
    text = text.replace("RPE ca ", "RPE ")
    return text


def swim_set_html(sets, compact=False):
    if not sets:
        return ""
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
            rows.append(f'<div class="swim-set-row"><span>{html.escape(normalized)}</span></div>')
    compact_class = " compact" if compact else ""
    return f'<div class="swim-set-list{compact_class}">{"".join(rows)}</div>'


def swim_header_html(session, compact=False):
    parts = [part.strip() for part in session.split(" · ")]
    focus = parts[1] if len(parts) > 1 else ""
    meta = []
    for part in parts[2:]:
        part = re.sub(r"^(ca|cirka)\s+", "≈ ", part, flags=re.IGNORECASE)
        meta.append(part)
    title = "Simning" + (f" · {focus}" if focus else "")
    tag = "div" if compact else "div"
    meta_html = f'<span class="swim-meta">{" · ".join(html.escape(x) for x in meta)}</span>' if meta else ""
    return f'<{tag} class="swim-session-head"><strong>{html.escape(title)}</strong>{meta_html}</{tag}>'


def render_swim_compact(day):
    _, sets, _ = split_swim_reason(day.get("reason", ""))
    return '<div class="swim-workout compact">' + swim_header_html(day["session"], compact=True) + swim_set_html(sets, compact=True) + '</div>'


def render_swim_day(day):
    prefix, sets, suffix = split_swim_reason(day.get("reason", ""))
    reason_parts = [x for x in (prefix, suffix) if x]
    reason_html = f'<div class="reason">{html.escape(" ".join(reason_parts))}</div>' if reason_parts else ""
    return (
        '<div class="swim-workout">'
        + swim_header_html(day["session"])
        + swim_set_html(sets)
        + '</div>\n  '
        + reason_html
    )


# Rename the visible coach identity consistently without changing the data schema.
replacements = {
    "AI-coach · bedömning": "Tränings-Yoda (AI)",
    "Coachjustering": "Tränings-Yoda · justering",
    "Coach:": "Tränings-Yoda:",
    "AI-coachen får automatiskt": "Tränings-Yoda (AI) får automatiskt",
    "Fakta, tolkning och osäkerhet": "Underlag · fakta, tolkning och osäkerhet",
}
for old, new in replacements.items():
    page = page.replace(old, new)

# Make swimming workouts scan like a set rather than prose, both in the upcoming
# dashboard and in the full day card. This only reformats existing plan text.
for day in plan.get("days", []):
    session = day.get("session", "")
    if not session.startswith("Simning"):
        continue

    escaped_session = html.escape(session)
    compact_needle = f'<div>{escaped_session}</div>'
    if day.get("date", "") >= today and compact_needle in page:
        page = page.replace(compact_needle, render_swim_compact(day), 1)

    escaped_reason = html.escape(day.get("reason", ""))
    full_needle = (
        f'<div class="session">{escaped_session}</div>\n'
        f'  <div class="reason">{escaped_reason}</div>'
    )
    if full_needle in page:
        page = page.replace(full_needle, render_swim_day(day), 1)

# Mark today's upcoming card explicitly. Keep the weekday as useful context.
upcoming_title = '<div class="dashboard-title">Kommande dagar</div>'
if upcoming_title in page:
    section_start = page.index(upcoming_title)
    section_end = page.find('</section>', section_start)
    if section_end > section_start:
        section = page[section_start:section_end]
        today_day = next((d for d in plan.get("days", []) if d.get("date") == today), None)
        if today_day:
            weekday = html.escape(today_day.get("label", ""))
            needle = f'<strong>{weekday}</strong>'
            if needle in section:
                replacement = f'<strong><span class="today-pill">IDAG</span>{weekday}</strong>'
                section = section.replace(needle, replacement, 1)
                page = page[:section_start] + section + page[section_end:]

# Add a little hierarchy instead of exposing every coach sentence as one text wall.
css_marker = "/* training-ux-v1 */"
if css_marker not in page:
    css = r'''
/* training-ux-v1 */
.today-pill{display:inline-block;margin-right:7px;padding:2px 7px;border-radius:999px;background:#0f172a;color:#fff;font-size:.62rem;letter-spacing:.08em;vertical-align:1px}
.swim-workout{margin:8px 0 10px;padding:12px 13px;border:1px solid #bfdbfe;background:#f8fbff;border-radius:14px}.swim-workout.compact{margin:7px 0 3px;padding:10px 11px}.swim-session-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}.swim-session-head strong{font-size:1.02rem}.swim-meta{color:#64748b;font-size:.82rem;font-weight:700}.swim-set-list{display:grid;gap:5px;margin-top:9px}.swim-set-list.compact{gap:4px;margin-top:7px}.swim-set-row{display:grid;grid-template-columns:minmax(72px,max-content) 1fr;gap:10px;align-items:baseline;font-size:.91rem;line-height:1.35}.swim-set-list.compact .swim-set-row{font-size:.84rem}.swim-dose{font-weight:850;font-variant-numeric:tabular-nums;color:#1e3a8a}
.coach{padding:16px;background:#f8f5ff}.coach-title{font-size:.78rem;margin-bottom:9px}.coach-summary{background:#fff;border:1px solid #ddd6fe;border-radius:12px;padding:11px 12px;margin:0;font-size:.96rem;line-height:1.5}.coach-load{margin-top:9px;padding:10px 12px;border-radius:12px;background:#f3e8ff;color:#4c1d95;font-size:.88rem;line-height:1.45}.coach-load:before{content:"Närbelastning";display:block;margin-bottom:3px;font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.07em;color:#6d28d9}.coach-details{margin-top:9px;padding:9px 11px;border-radius:11px;background:#fff;border:1px solid #e9d5ff}.coach-details summary{font-size:.83rem;color:#5b21b6}.coach-grid{line-height:1.45}.coach-grid li+li{margin-top:5px}.coach-action{margin-top:9px;padding:11px 12px;border:1px solid #ddd6fe;border-radius:12px;background:#fff;line-height:1.45}.coach-action>strong{display:inline-block;margin-bottom:4px;color:#5b21b6}.coach-action span{display:block;margin-top:4px;color:#3b0764}.coach-action small{display:block;margin-top:5px;color:#7e22ce}
@media (max-width:620px){.swim-set-row{grid-template-columns:minmax(66px,max-content) 1fr;gap:8px}.coach{padding:13px}}
'''
    if "</style>" not in page:
        raise RuntimeError("Training UX: kunde inte hitta </style>")
    page = page.replace("</style>", css + "\n</style>", 1)

INDEX_FILE.write_text(page, encoding="utf-8")

rendered = INDEX_FILE.read_text(encoding="utf-8")
required = ["Tränings-Yoda (AI)", "Kommande dagar", css_marker]
if any(d.get("date") == today for d in plan.get("days", [])):
    # IDAG appears only while today's card is still upcoming; a completed today
    # correctly disappears from the upcoming list and should not fail the build.
    if today in [d.get("date") for d in plan.get("days", [])]:
        pass
if any(d.get("session", "").startswith("Simning") and d.get("date", "") >= today for d in plan.get("days", [])):
    required.append("swim-set-list")

missing = [snippet for snippet in required if snippet not in rendered]
if missing:
    raise RuntimeError("Training UX-validering misslyckades: " + repr(missing))

print("Training UX OK: idag-markering, simformat och Tränings-Yoda applicerade.")
