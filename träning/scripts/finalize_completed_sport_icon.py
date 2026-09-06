#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from coach_rules import matching_activity, planning_window

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
PLAN_FILE = ROOT / "data" / "plan.json"
UPCOMING_FILE = ROOT / "data" / "upcoming_week.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
ICON_FILE = ROOT / "data" / "sport_icons.json"

CSS_MARKER = "/* completed-sport-icon-v1 */"
CSS = r'''
/* completed-sport-icon-v1 */
.completed-session-with-icon{display:flex;align-items:center;gap:8px;min-width:0}
.completed-session-with-icon .sport-icon{width:19px;height:19px;flex:0 0 auto;color:#64748b}
.completed-session-with-icon .sport-icon.icon-swim,.completed-session-with-icon .sport-icon.icon-bike,.completed-session-with-icon .sport-icon.icon-enduro,.completed-session-with-icon .sport-icon.icon-strength{width:21px}
@media(max-width:620px){.completed-session-with-icon .sport-icon{width:18px;height:18px}.completed-session-with-icon .sport-icon.icon-swim,.completed-session-with-icon .sport-icon.icon-bike,.completed-session-with-icon .sport-icon.icon-enduro,.completed-session-with-icon .sport-icon.icon-strength{width:20px}}
'''.strip()

PLAN_SPORT_ICON_KEYS = {
    "run": "run",
    "running": "run",
    "trail": "run",
    "swim": "swim",
    "swimming": "swim",
    "swimrun": "run",
    "mtb": "bike",
    "xc": "bike",
    "bike": "bike",
    "cycling": "bike",
    "enduro": "enduro",
    "strength": "strength",
}

ACTIVITY_SPORT_ICON_KEYS = {
    "Run": "run",
    "TrailRun": "run",
    "VirtualRun": "run",
    "Swim": "swim",
    "Swimrun": "run",
    "MountainBikeRide": "bike",
    "EMountainBikeRide": "bike",
    "Ride": "bike",
    "VirtualRide": "bike",
    "WeightTraining": "strength",
    "Enduro": "enduro",
}

LINE_ACTIVITY_ICON = '<path d="M3 12h4l2-5 4 10 2-5h6"/>'


def load_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def local_date(activity):
    value = str(activity.get("start_date_local") or activity.get("start_date") or "")
    return value[:10] if len(value) >= 10 else ""


def icon_key(day, activity):
    plan_sport = str((day or {}).get("sport") or "").strip().lower()
    if plan_sport in PLAN_SPORT_ICON_KEYS:
        return PLAN_SPORT_ICON_KEYS[plan_sport]
    activity_sport = str((activity or {}).get("sport_type") or "").strip()
    return ACTIVITY_SPORT_ICON_KEYS.get(activity_sport, "activity")


def render_icon(name, icon_registry):
    solid = (icon_registry or {}).get(name)
    if solid:
        return (
            f'<svg class="sport-icon icon-{html.escape(name)}" aria-hidden="true" '
            f'viewBox="{html.escape(str(solid["viewBox"]))}" fill="currentColor" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<path d="{html.escape(str(solid["path"]))}"/></svg>'
        )
    return (
        f'<svg class="sport-icon icon-{html.escape(name)}" aria-hidden="true" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round">{LINE_ACTIVITY_ICON}</svg>'
    )


def add_css(page):
    if CSS_MARKER in page:
        return page
    if "</style>" not in page:
        raise RuntimeError("Genomfört-ikon: sidan saknar </style>")
    return page.replace("</style>", CSS + "\n</style>", 1)


def decorate_completed_today_icon(page, plan, upcoming, activities_state, today, icon_registry):
    decision_plan = planning_window(plan, upcoming)
    day = next((item for item in decision_plan.get("days") or [] if item.get("date") == today), None)
    if not day:
        return page

    same_day = [
        activity
        for activity in (activities_state.get("activities") or [])
        if local_date(activity) == today
    ]
    activity = matching_activity(day, same_day) if same_day else None
    if not activity:
        return page

    card_match = re.search(
        r'<section class="today-outcome"[^>]*data-post-workout-state="completed"[^>]*>.*?</section>',
        page,
        re.S,
    )
    if not card_match:
        raise RuntimeError("Genomfört-ikon: dagens genomförda efterpasskort saknas")

    key = icon_key(day, activity)
    card = card_match.group(0)
    title_pattern = re.compile(
        r'<h2 class="today-outcome-title(?: completed-session-with-icon)?"(?: data-completed-sport-icon="[^"]+")? id="todayOutcomeTitle">(.*?)</h2>',
        re.S,
    )
    title_match = title_pattern.search(card)
    if not title_match:
        raise RuntimeError("Genomfört-ikon: efterpasskortets huvudrubrik saknas")

    existing_inner = title_match.group(1)
    if 'class="sport-icon ' in existing_inner:
        expected = f'class="sport-icon icon-{key}"'
        if expected not in existing_inner:
            raise RuntimeError(
                f"Genomfört-ikon: fel grenikon i dagens efterpasskort; väntade {key}"
            )
        return add_css(page)

    replacement = (
        f'<h2 class="today-outcome-title completed-session-with-icon" '
        f'data-completed-sport-icon="{html.escape(key)}" id="todayOutcomeTitle">'
        f'{render_icon(key, icon_registry)}<span>{existing_inner}</span></h2>'
    )
    card, count = title_pattern.subn(replacement, card, count=1)
    if count != 1:
        raise RuntimeError("Genomfört-ikon: kunde inte dekorera dagens efterpassrubrik")

    page = page[:card_match.start()] + card + page[card_match.end():]
    page = add_css(page)

    verify = re.search(
        r'<h2 class="today-outcome-title completed-session-with-icon"[^>]*>(.*?)</h2>',
        page,
        re.S,
    )
    if not verify or f'class="sport-icon icon-{key}"' not in verify.group(1):
        raise RuntimeError("Genomfört-ikon: verifiering misslyckades efter rendering")
    return page


def main():
    plan = load_json(PLAN_FILE, {})
    upcoming = load_json(UPCOMING_FILE, {})
    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    icon_registry = load_json(ICON_FILE, {"icons": {}}).get("icons") or {}
    timezone_name = (plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    today = datetime.now(ZoneInfo(timezone_name)).date().isoformat()

    page = INDEX_FILE.read_text(encoding="utf-8")
    rendered = decorate_completed_today_icon(
        page,
        plan,
        upcoming,
        activities,
        today,
        icon_registry,
    )
    INDEX_FILE.write_text(rendered, encoding="utf-8")
    print("Genomfört-ikon OK: dagens genomförda pass använder samma grenikonmodell som planerade pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
