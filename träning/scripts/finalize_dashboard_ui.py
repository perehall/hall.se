#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
SUMMARY_FILE = ROOT / "data" / "dashboard_summary.json"
INDEX_FILE = ROOT / "index.html"

SPORT_GROUPS = {
    "Run": "Löpning",
    "TrailRun": "Löpning",
    "VirtualRun": "Löpning",
    "Swim": "Simning",
    "MountainBikeRide": "MTB/XC",
    "Ride": "Cykel",
    "VirtualRide": "Cykel",
    "WeightTraining": "Styrka",
}

DOSE_PATTERN = re.compile(
    r"\b\d+(?:[.,]\d+)?(?:\s*[–-]\s*\d+(?:[.,]\d+)?)?\s*(?:min|h|km|m)\b",
    re.IGNORECASE,
)
CLOCK_DURATION_PATTERN = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")


def local_date(activity):
    value = activity.get("start_date_local") or ""
    return value[:10] if len(value) >= 10 else ""


def distance_m(activity):
    value = activity.get("distance_m")
    if value is None:
        return 0.0
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return value if value > 0 else 0.0


def fmt_km(meters):
    return f"{meters / 1000:.1f}".replace(".", ",")


def has_explicit_dose(session):
    return bool(DOSE_PATTERN.search(session) or CLOCK_DURATION_PATTERN.search(session))


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
    text = re.sub(
        r"\((\d+(?:–\d+)?\s*s) vila,\s*RPE ca ([^)]+)\)",
        r"@ \1 · RPE \2",
        text,
    )
    text = re.sub(r"\((\d+(?:–\d+)?\s*s) vila\)", r"@ \1", text)
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


def swim_header_html(session):
    parts = [part.strip() for part in session.split(" · ")]
    focus = parts[1] if len(parts) > 1 else ""
    meta = []
    for part in parts[2:]:
        part = re.sub(r"^(ca|cirka)\s+", "≈ ", part, flags=re.IGNORECASE)
        meta.append(part)
    title = "Simning" + (f" · {focus}" if focus else "")
    meta_html = (
        f'<span class="swim-meta">{" · ".join(html.escape(x) for x in meta)}</span>'
        if meta else ""
    )
    return f'<div class="swim-session-head"><strong>{html.escape(title)}</strong>{meta_html}</div>'


def render_swim_compact(day):
    _, sets, _ = split_swim_reason(day.get("reason", ""))
    return (
        '<div class="swim-workout compact">'
        + swim_header_html(day["session"])
        + swim_set_html(sets, compact=True)
        + '</div>'
    )


def render_swim_day(day):
    prefix, sets, suffix = split_swim_reason(day.get("reason", ""))
    reason_parts = [part for part in (prefix, suffix) if part]
    reason_html = (
        f'<div class="reason">{html.escape(" ".join(reason_parts))}</div>'
        if reason_parts else ""
    )
    return (
        '<div class="swim-workout">'
        + swim_header_html(day["session"])
        + swim_set_html(sets)
        + '</div>\n  '
        + reason_html
    )


plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
state = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
page = INDEX_FILE.read_text(encoding="utf-8")
summary = json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))
tz = ZoneInfo(plan.get("meta", {}).get("timezone", "Europe/Stockholm"))
today = datetime.now(tz).date().isoformat()

# Planned training should be usable even while preliminary. A future planned,
# preliminary or conditional training session therefore needs an explicit dose
# (time and/or distance). Explicit rest/open states and recreation are exempt.
missing_plan_dose = []
for day in plan.get("days", []):
    if day.get("date", "") < today:
        continue
    if day.get("status") not in {"planned", "preliminary", "conditional"}:
        continue
    if day.get("sport") in {"rest", "open"}:
        continue
    if day.get("classification") == "recreation":
        continue
    session = (day.get("session") or "").strip()
    if not has_explicit_dose(session):
        missing_plan_dose.append(f'{day.get("date", "?")} {session or "<tomt pass>"}')

if missing_plan_dose:
    raise RuntimeError(
        "Planvalidering: kommande planerade/preliminära pass saknar dos (tid/distans): "
        + "; ".join(missing_plan_dose)
    )

week_start = plan["meta"]["week_start"]
week_end = plan["meta"]["week_end"]
week_activities = [
    activity
    for activity in state.get("activities", [])
    if local_date(activity) and week_start <= local_date(activity) <= week_end
]

distance_by_sport = {}
for activity in week_activities:
    group = SPORT_GROUPS.get(
        activity.get("sport_type"), activity.get("sport_type") or "Övrigt"
    )
    meters = distance_m(activity)
    if meters:
        distance_by_sport[group] = distance_by_sport.get(group, 0.0) + meters

old_title = '<div class="dashboard-title">Nästa dagar</div>'
new_title = '<div class="dashboard-title">Kommande dagar</div>'
if old_title in page:
    page = page.replace(old_title, new_title, 1)
elif new_title not in page:
    raise RuntimeError("Dashboard UI: rubriken för kommande dagar kunde inte hittas")

for group, meters in distance_by_sport.items():
    escaped_group = html.escape(group)
    plain = f'<div class="sport-head"><span>{escaped_group}</span>'
    labelled = f'<div class="sport-head"><span>{escaped_group} ({fmt_km(meters)}km)</span>'
    if plain in page:
        page = page.replace(plain, labelled, 1)
    elif labelled not in page:
        raise RuntimeError(f"Dashboard UI: grenrad saknas för {group}")

for old, new in {
    "AI-coach · bedömning": "Tränings-Yoda (AI)",
    "Coachjustering": "Tränings-Yoda · justering",
    "Coach:": "Tränings-Yoda:",
    "AI-coachen får automatiskt": "Tränings-Yoda (AI) får automatiskt",
    "Fakta, tolkning och osäkerhet": "Underlag · fakta, tolkning och osäkerhet",
}.items():
    page = page.replace(old, new)

for day in plan.get("days", []):
    if day.get("sport") != "swim":
        continue
    session = day.get("session", "")
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

today_day = next((d for d in plan.get("days", []) if d.get("date") == today), None)
today_has_activity = any(local_date(activity) == today for activity in week_activities)
if today_day and not today_has_activity:
    section_start = page.find(new_title)
    section_end = page.find('</section>', section_start) if section_start >= 0 else -1
    if section_start >= 0 and section_end > section_start:
        section = page[section_start:section_end]
        weekday = html.escape(today_day.get("label", ""))
        needle = f'<strong>{weekday}</strong>'
        if needle in section:
            section = section.replace(
                needle,
                f'<strong><span class="today-pill">IDAG</span>{weekday}</strong>',
                1,
            )
            page = page[:section_start] + section + page[section_end:]

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
        raise RuntimeError("Dashboard UI: kunde inte hitta </style>")
    page = page.replace("</style>", css + "\n</style>", 1)

INDEX_FILE.write_text(page, encoding="utf-8")

summary["distance_definition"] = "summa distance_m per gren; visning i km med en decimal"
summary["by_sport_distance_m"] = {
    group: round(meters, 3)
    for group, meters in sorted(distance_by_sport.items())
}
SUMMARY_FILE.write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

rendered = INDEX_FILE.read_text(encoding="utf-8")
required = [new_title, "Tränings-Yoda (AI)", css_marker]
for group, meters in distance_by_sport.items():
    required.append(f'{html.escape(group)} ({fmt_km(meters)}km)')
if today_day and not today_has_activity:
    required.append('class="today-pill">IDAG</span>')
if any(
    day.get("sport") == "swim" and "Förslag:" in day.get("reason", "")
    for day in plan.get("days", [])
):
    required.append('class="swim-set-list')

missing = [snippet for snippet in required if snippet not in rendered]
if missing:
    raise RuntimeError("Dashboard UI-validering misslyckades: " + repr(missing))

print(
    "Dashboard UI OK: Kommande dagar, idag-markering, gren-distans, "
    "simformat, passdos och Tränings-Yoda."
)
