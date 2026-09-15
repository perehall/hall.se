#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from activity_labels import public_activity_label
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
.completed-activity-with-icon{display:flex;align-items:center;gap:8px;min-width:0}
.completed-activity-with-icon .sport-icon{width:16px;height:16px;flex:0 0 auto;color:#64748b}
.completed-activity-with-icon .sport-icon.icon-swim,.completed-activity-with-icon .sport-icon.icon-bike,.completed-activity-with-icon .sport-icon.icon-enduro,.completed-activity-with-icon .sport-icon.icon-strength{width:18px}
@media(max-width:620px){.completed-session-with-icon .sport-icon{width:18px;height:18px}.completed-session-with-icon .sport-icon.icon-swim,.completed-session-with-icon .sport-icon.icon-bike,.completed-session-with-icon .sport-icon.icon-enduro,.completed-session-with-icon .sport-icon.icon-strength{width:20px}.completed-activity-with-icon .sport-icon{width:15px;height:15px}.completed-activity-with-icon .sport-icon.icon-swim,.completed-activity-with-icon .sport-icon.icon-bike,.completed-activity-with-icon .sport-icon.icon-enduro,.completed-activity-with-icon .sport-icon.icon-strength{width:17px}}
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


def fmt_duration(sec):
    if sec is None:
        return ""
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_activity(activity):
    bits = []
    if activity.get("distance_m"):
        bits.append(f'{activity["distance_m"] / 1000:.2f} km'.replace(".", ","))
    if activity.get("elapsed_time_s"):
        bits.append(fmt_duration(activity["elapsed_time_s"]))
    if activity.get("average_heartrate"):
        bits.append(f'snittpuls {round(activity["average_heartrate"])}')
    if activity.get("max_heartrate"):
        bits.append(f'max {round(activity["max_heartrate"])}')
    return " · ".join(bits)


def icon_key(day, activity):
    plan_sport = str((day or {}).get("sport") or "").strip().lower()
    if plan_sport in PLAN_SPORT_ICON_KEYS:
        return PLAN_SPORT_ICON_KEYS[plan_sport]
    activity_sport = str((activity or {}).get("sport_type") or "").strip()
    return ACTIVITY_SPORT_ICON_KEYS.get(activity_sport, "activity")


def activity_icon_key(activity):
    activity_sport = str((activity or {}).get("sport_type") or "").strip()
    mapped = ACTIVITY_SPORT_ICON_KEYS.get(activity_sport)
    if mapped:
        return mapped

    label = public_activity_label(activity).lower()
    if "enduro" in label:
        return "enduro"
    if "sim" in label:
        return "swim"
    if "mtb" in label or "cykel" in label or "bike" in label:
        return "bike"
    if "styrk" in label or "weight" in label:
        return "strength"
    if "löp" in label or "trail" in label or "run" in label:
        return "run"
    return "activity"


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


def plain_activity_row(activity):
    label = public_activity_label(activity)
    return (
        f'<div><strong>{html.escape(label)}</strong> · '
        f'{html.escape(fmt_activity(activity))}</div>'
    )


def decorated_activity_row(activity, icon_registry):
    label = public_activity_label(activity)
    key = activity_icon_key(activity)
    activity_id = html.escape(str(activity.get("id") or ""))
    return (
        f'<div class="completed-activity-with-icon" data-completed-activity-id="{activity_id}" '
        f'data-completed-sport-icon="{html.escape(key)}">'
        f'{render_icon(key, icon_registry)}<span><strong>{html.escape(label)}</strong> · '
        f'{html.escape(fmt_activity(activity))}</span></div>'
    )


def decorate_completed_week_activity_icons(page, activities_state, today, icon_registry):
    same_day = [
        activity
        for activity in (activities_state.get("activities") or [])
        if local_date(activity) == today
    ]
    if not same_day:
        return page

    marker = f'<div class="day" id="dag-{html.escape(today)}">'
    card_start = page.find(marker)
    if card_start < 0:
        return page
    card_end = page.find('<div class="day" id="dag-', card_start + len(marker))
    if card_end < 0:
        card_end = page.find('<h2 class="section">', card_start + len(marker))
    if card_end < 0:
        card_end = len(page)
    card = page[card_start:card_end]

    decorated_ids = []
    for activity in same_day:
        activity_id = html.escape(str(activity.get("id") or ""))
        existing_token = f'data-completed-activity-id="{activity_id}"'
        if activity_id and existing_token in card:
            decorated_ids.append(activity_id)
            continue

        plain = plain_activity_row(activity)
        if plain not in card:
            raise RuntimeError(
                f"Genomfört-ikon: aktivitetsrad saknas i veckoplanen för {activity.get('id')}"
            )
        replacement = decorated_activity_row(activity, icon_registry)
        card = card.replace(plain, replacement, 1)
        decorated_ids.append(activity_id)

    page = page[:card_start] + card + page[card_end:]
    page = add_css(page)

    verify_start = page.find(marker)
    verify_end = page.find('<div class="day" id="dag-', verify_start + len(marker))
    if verify_end < 0:
        verify_end = page.find('<h2 class="section">', verify_start + len(marker))
    if verify_end < 0:
        verify_end = len(page)
    verify_card = page[verify_start:verify_end]
    for activity in same_day:
        key = activity_icon_key(activity)
        activity_id = html.escape(str(activity.get("id") or ""))
        if activity_id and f'data-completed-activity-id="{activity_id}"' not in verify_card:
            raise RuntimeError(
                f"Genomfört-ikon: aktivitetsraden verifierades inte för {activity.get('id')}"
            )
        if f'data-completed-sport-icon="{key}"' not in verify_card:
            raise RuntimeError(
                f"Genomfört-ikon: {key}-ikon saknas i veckoplanens genomförda aktivitetsrad"
            )
    return page


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
    rendered = decorate_completed_week_activity_icons(
        rendered,
        activities,
        today,
        icon_registry,
    )
    INDEX_FILE.write_text(rendered, encoding="utf-8")
    print(
        "Genomfört-ikon OK: efterpasskort och dagens faktiska veckoplansrader använder grenikoner."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
