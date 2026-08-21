#!/usr/bin/env python3
import html
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
INDEX_FILE = ROOT / "index.html"

plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
activities_state = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
page = INDEX_FILE.read_text(encoding="utf-8")

tz = ZoneInfo(plan.get("meta", {}).get("timezone", "Europe/Stockholm"))
today = datetime.now(tz).date().isoformat()

activity_dates = {
    (activity.get("start_date_local") or "")[:10]
    for activity in activities_state.get("activities", [])
    if len(activity.get("start_date_local") or "") >= 10
}

# Stable anchors for the detailed day cards.
day_marker = '<div class="day">'
expected_days = plan.get("days", [])
if page.count(day_marker) != len(expected_days):
    raise RuntimeError(
        "Navigations-UI: antal dagkort matchar inte plan.json "
        f"({page.count(day_marker)} != {len(expected_days)})"
    )

for day in expected_days:
    date = day.get("date", "")
    page = page.replace(
        day_marker,
        f'<div class="day" id="dag-{html.escape(date)}">',
        1,
    )

# Match the exact same upcoming-day selection as build.py.
upcoming_days = [
    day
    for day in expected_days
    if day.get("date", "") >= today and day.get("date", "") not in activity_dates
][:3]

next_marker = '<div class="next-item">'
if page.count(next_marker) != len(upcoming_days):
    raise RuntimeError(
        "Navigations-UI: antal Kommande dagar matchar inte planeringen "
        f"({page.count(next_marker)} != {len(upcoming_days)})"
    )

for day in upcoming_days:
    date = day.get("date", "")
    label = day.get("label", date)
    jump = (
        f'<div class="next-item">'
        f'<a class="next-jump" href="#dag-{html.escape(date)}" '
        f'aria-label="Visa detaljer för {html.escape(label)}"></a>'
    )
    page = page.replace(next_marker, jump, 1)

css_marker = "/* upcoming-day-links-v1 */"
if css_marker not in page:
    css = r'''
/* upcoming-day-links-v1 */
.next-item{position:relative;cursor:pointer;transition:background-color .15s ease}.next-item:hover{background:#f8fafc}.next-jump{position:absolute;inset:0;z-index:2;border-radius:10px}.next-jump:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.day{scroll-margin-top:18px}
@media (prefers-reduced-motion:reduce){.next-item{transition:none}}
'''
    if "</style>" not in page:
        raise RuntimeError("Navigations-UI: kunde inte hitta </style>")
    page = page.replace("</style>", css + "\n</style>", 1)

INDEX_FILE.write_text(page, encoding="utf-8")

rendered = INDEX_FILE.read_text(encoding="utf-8")
required = [css_marker]
for day in expected_days:
    required.append(f'id="dag-{day.get("date", "")}"')
for day in upcoming_days:
    required.append(f'href="#dag-{day.get("date", "")}"')

missing = [snippet for snippet in required if snippet not in rendered]
if missing:
    raise RuntimeError("Navigations-UI-validering misslyckades: " + repr(missing))

print(
    f"Navigations-UI OK: {len(upcoming_days)} Kommande dagar länkar till sina detaljkort."
)
