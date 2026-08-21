#!/usr/bin/env python3
import html
import json
from pathlib import Path

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


plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
state = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
page = INDEX_FILE.read_text(encoding="utf-8")
summary = json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))

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
required = [new_title]
for group, meters in distance_by_sport.items():
    required.append(f'{html.escape(group)} ({fmt_km(meters)}km)')

missing = [snippet for snippet in required if snippet not in rendered]
if missing:
    raise RuntimeError("Dashboard UI-validering misslyckades: " + repr(missing))

print(
    "Dashboard UI OK: Kommande dagar + distans för "
    f"{len(distance_by_sport)} gren(ar)."
)
