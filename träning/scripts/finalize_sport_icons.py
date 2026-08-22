#!/usr/bin/env python3
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
ICON_FILE = ROOT / "data" / "sport_icons.json"
INDEX_FILE = ROOT / "index.html"

plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
activities_state = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
icon_registry = json.loads(ICON_FILE.read_text(encoding="utf-8"))["icons"]
page = INDEX_FILE.read_text(encoding="utf-8")

activity_dates = {
    (activity.get("start_date_local") or "")[:10]
    for activity in activities_state.get("activities", [])
    if len(activity.get("start_date_local") or "") >= 10
}

SPORT_ICON_KEYS = {
    "run": "run",
    "running": "run",
    "trail": "run",
    "swim": "swim",
    "swimming": "swim",
    "mtb": "bike",
    "xc": "bike",
    "bike": "bike",
    "cycling": "bike",
    "enduro": "enduro",
    "strength": "strength",
    "swimrun": "run",
}

CLASSIFICATION_LABELS = {
    "training": "TRÄNING",
    "recreation": "REKREATION",
}

LINE_ICONS = {
    "activity": '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
    "watch": (
        '<rect x="7" y="5" width="10" height="14" rx="2.2"/>'
        '<path d="M9.5 5V2.5h5V5M9.5 19v2.5h5V19M12 9v3l2 1.5"/>'
    ),
}


def icon(name, extra_class=""):
    cls = "sport-icon icon-" + name + (f" {extra_class}" if extra_class else "")
    solid = icon_registry.get(name)
    if solid:
        return (
            f'<svg class="{cls}" aria-hidden="true" viewBox="{solid["viewBox"]}" '
            'fill="currentColor" xmlns="http://www.w3.org/2000/svg">'
            f'<path d="{solid["path"]}"/></svg>'
        )
    body = LINE_ICONS.get(name, LINE_ICONS["activity"])
    return (
        f'<svg class="{cls}" aria-hidden="true" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'{body}</svg>'
    )


def icon_for_text(value):
    text = (value or "").lower()
    if "sim" in text:
        return "swim"
    if "enduro" in text:
        return "enduro"
    if "mtb" in text or "cykel" in text or "bike" in text:
        return "bike"
    if "styrk" in text or "weight" in text:
        return "strength"
    if "löp" in text or "trail" in text or "run" in text:
        return "run"
    return "activity"


def icon_for_sport(sport, fallback_text=""):
    key = (sport or "").strip().lower()
    if key:
        return SPORT_ICON_KEYS.get(key, "activity")
    return icon_for_text(fallback_text)


def watch_chip():
    return (
        '<span class="watch-sync" title="Strukturerat simpass synkas automatiskt via Intervals.icu till Garmin">'
        f'{icon("watch", "watch-icon")}<span>Klocksync aktiv</span></span>'
    )


def get_day_segment(page_text, date):
    marker = f'<div class="day" id="dag-{html.escape(date)}">'
    start = page_text.find(marker)
    if start < 0:
        return -1, -1, ""
    next_day = page_text.find('<div class="day" id="dag-', start + len(marker))
    next_section = page_text.find('<h2 class="section">', start + len(marker))
    candidates = [pos for pos in (next_day, next_section) if pos >= 0]
    end = min(candidates) if candidates else len(page_text)
    return start, end, page_text[start:end]


def render_manual_activity(activity, index):
    sport_key = icon_for_sport(activity.get("sport"), activity.get("session", ""))
    classification = (activity.get("classification") or "").strip().lower()
    classification_label = CLASSIFICATION_LABELS.get(
        classification,
        classification.upper() if classification else "AKTIVITET",
    )
    reason = (activity.get("reason") or "").strip()
    reason_html = (
        f'<div class="manual-activity-reason">{html.escape(reason)}</div>'
        if reason else ""
    )
    return (
        f'<div class="manual-activity" data-manual-activity-index="{index}" '
        f'data-sport="{html.escape(activity.get("sport", ""))}" '
        f'data-classification="{html.escape(classification)}">'
        '<div class="manual-activity-head">'
        f'{icon(sport_key)}<strong>{html.escape(activity.get("session", ""))}</strong>'
        f'<span class="manual-activity-class">{html.escape(classification_label)}</span>'
        '</div>'
        f'{reason_html}</div>'
    )


# Sport distribution rows come from Strava labels, so text mapping remains the
# appropriate source there.
sport_pattern = re.compile(r'<div class="sport-head"><span>([^<]+)</span><strong>')


def sport_repl(match):
    label = match.group(1)
    sport_name = label.split(" (", 1)[0]
    return (
        '<div class="sport-head"><span class="sport-name">'
        f'{icon(icon_for_text(sport_name))}{label}</span><strong>'
    )


page, sport_icon_count = sport_pattern.subn(sport_repl, page)

# Upcoming plan rows use explicit plan.sport when present. Text parsing is only
# a backwards-compatibility fallback for older plan entries.
for day in plan.get("days", []):
    date = day.get("date", "")
    marker = f'<div class="next-item" data-next-date="{html.escape(date)}">'
    start = page.find(marker)
    if start < 0:
        continue
    next_start = page.find('<div class="next-item" data-next-date="', start + len(marker))
    section_end = page.find('</section>', start)
    candidates = [pos for pos in (next_start, section_end) if pos >= 0]
    end = min(candidates) if candidates else len(page)
    segment = page[start:end]

    sport_key = icon_for_sport(day.get("sport"), day.get("session", ""))
    if '<div class="swim-workout compact"><div class="swim-session-head"><strong>' in segment:
        segment = segment.replace(
            '<div class="swim-workout compact"><div class="swim-session-head"><strong>',
            '<div class="swim-workout compact"><div class="swim-session-head"><strong class="session-with-icon">'
            + icon(sport_key),
            1,
        )
    else:
        escaped_session = html.escape(day.get("session", ""))
        needle = f'<div>{escaped_session}</div>'
        if needle in segment:
            segment = segment.replace(
                needle,
                f'<div class="next-session">{icon(sport_key)}<span>{escaped_session}</span></div>',
                1,
            )

    workout = day.get("watch_workout") or {}
    watch_active = (
        workout.get("sync_enabled") is True
        and day.get("status") == "planned"
        and date not in activity_dates
    )
    if watch_active and 'class="swim-session-head"' in segment and 'class="watch-sync"' not in segment:
        segment = re.sub(
            r'(<div class="swim-session-head">.*?)(</div>)',
            lambda m: m.group(1) + watch_chip() + m.group(2),
            segment,
            count=1,
            flags=re.DOTALL,
        )

    page = page[:start] + segment + page[end:]

# Manually reported activities are factual logged context and are rendered
# separately from the remaining plan for the same day.
for day in plan.get("days", []):
    manual_activities = day.get("manual_activities") or []
    if not manual_activities:
        continue

    date = day.get("date", "")
    start, end, segment = get_day_segment(page, date)
    if start < 0:
        raise RuntimeError(f"Sportikoner: detaljkort saknas för manuell aktivitet {date}")

    reason_needle = f'<div class="reason">{html.escape(day.get("reason", ""))}</div>'
    if reason_needle not in segment:
        raise RuntimeError(f"Sportikoner: dagsmotivering saknas för manuell aktivitet {date}")

    blocks = []
    for index, activity in enumerate(manual_activities, start=1):
        if f'data-manual-activity-index="{index}"' in segment:
            continue
        blocks.append(render_manual_activity(activity, index))

    if blocks:
        segment = segment.replace(reason_needle, reason_needle + "\n  " + "".join(blocks), 1)
        page = page[:start] + segment + page[end:]

# Watch-sync chip on detailed structured swim cards.
for day in plan.get("days", []):
    workout = day.get("watch_workout") or {}
    date = day.get("date", "")
    watch_active = (
        workout.get("sync_enabled") is True
        and day.get("status") == "planned"
        and date not in activity_dates
    )
    if not watch_active:
        continue

    start, end, segment = get_day_segment(page, date)
    if start < 0:
        raise RuntimeError(f"Sportikoner: detaljkort saknas för klocksync {date}")
    if 'class="watch-sync"' not in segment:
        if 'class="swim-session-head"' not in segment:
            raise RuntimeError(f"Sportikoner: strukturerad simrubrik saknas för {date}")
        segment = re.sub(
            r'(<div class="swim-session-head">.*?)(</div>)',
            lambda m: m.group(1) + watch_chip() + m.group(2),
            segment,
            count=1,
            flags=re.DOTALL,
        )
        page = page[:start] + segment + page[end:]

css_marker = "/* sport-icons-v2 */"
if css_marker not in page:
    css = r'''
/* sport-icons-v2 */
.sport-name,.next-session,.session-with-icon{display:inline-flex;align-items:center;gap:8px;min-width:0}.sport-icon{width:18px;height:18px;flex:0 0 auto;color:#64748b}.sport-icon.icon-swim{width:20px}.sport-icon.icon-bike,.sport-icon.icon-enduro,.sport-icon.icon-strength{width:20px}.sport-name .sport-icon{height:18px}.next-session{font-weight:600}.session-with-icon{font-weight:800}.watch-sync{display:inline-flex;align-items:center;gap:4px;width:max-content;padding:3px 7px;border:1px solid #cbd5e1;border-radius:999px;background:#f8fafc;color:#475569;font-size:.68rem;font-weight:800;line-height:1.2;white-space:nowrap}.watch-sync .watch-icon{width:13px;height:13px;color:#475569}.swim-session-head{row-gap:6px}.next-item .sport-icon{position:relative;z-index:1}.manual-activity{margin:10px 0 2px;padding:11px 12px;border:1px solid #e2e8f0;border-radius:13px;background:#f8fafc}.manual-activity-head{display:flex;align-items:center;gap:8px;min-width:0}.manual-activity-head strong{font-size:.9rem;line-height:1.3}.manual-activity-class{margin-left:auto;padding:3px 7px;border:1px solid #d8dee8;border-radius:999px;background:#fff;color:#64748b;font-size:.61rem;font-weight:900;letter-spacing:.06em}.manual-activity-reason{margin-top:6px;color:#64748b;font-size:.79rem;line-height:1.4}
@media (max-width:520px){.sport-icon{width:17px;height:17px}.sport-icon.icon-swim,.sport-icon.icon-bike,.sport-icon.icon-enduro,.sport-icon.icon-strength{width:19px}.watch-sync{font-size:.64rem;padding:3px 6px}.manual-activity-head{align-items:flex-start;flex-wrap:wrap}.manual-activity-class{margin-left:0}}
'''
    if "</style>" not in page:
        raise RuntimeError("Sportikoner: kunde inte hitta </style>")
    page = page.replace("</style>", css + "\n</style>", 1)

INDEX_FILE.write_text(page, encoding="utf-8")
rendered = INDEX_FILE.read_text(encoding="utf-8")

if css_marker not in rendered:
    raise RuntimeError("Sportikoner: CSS-marker saknas efter rendering")
if sport_icon_count and rendered.count('class="sport-name"') < sport_icon_count:
    raise RuntimeError("Sportikoner: alla grenrader fick inte ikon")

for day in plan.get("days", []):
    date = day.get("date", "")
    if f'data-next-date="{date}"' not in rendered:
        continue
    start = rendered.find(f'<div class="next-item" data-next-date="{date}">')
    end = rendered.find('<div class="next-item" data-next-date="', start + 1)
    if end < 0:
        end = rendered.find('</section>', start)
    segment = rendered[start:end]
    if 'class="sport-icon' not in segment:
        raise RuntimeError(f"Sportikoner: Kommande dagar saknar ikon för {date}")

expected_manual = sum(
    len(day.get("manual_activities") or [])
    for day in plan.get("days", [])
)
rendered_manual = rendered.count('class="manual-activity"')
if rendered_manual != expected_manual:
    raise RuntimeError(
        "Sportikoner: antal renderade manuella aktiviteter matchar inte plan.json "
        f"({rendered_manual} != {expected_manual})"
    )

for day in plan.get("days", []):
    for activity in day.get("manual_activities") or []:
        sport_key = icon_for_sport(activity.get("sport"), activity.get("session", ""))
        exact_icon = f'class="sport-icon icon-{sport_key}"'
        if exact_icon not in rendered:
            raise RuntimeError(
                f"Sportikoner: ikon saknas för manuell aktivitet {activity.get('session', '<utan namn>')}"
            )

watch_days = [
    day for day in plan.get("days", [])
    if (day.get("watch_workout") or {}).get("sync_enabled") is True
    and day.get("status") == "planned"
    and day.get("date", "") not in activity_dates
]
for day in watch_days:
    date = day.get("date", "")
    start, end, segment = get_day_segment(rendered, date)
    if start < 0:
        raise RuntimeError(f"Sportikoner: detaljkort saknas för verifiering {date}")
    if 'class="watch-sync"' not in segment:
        raise RuntimeError(f"Sportikoner: klocksync-indikator saknas för {date}")

print(
    f"Sportikoner OK: {sport_icon_count} grenrader, "
    f"{expected_manual} manuella aktiviteter och "
    f"{len(watch_days)} aktiv(a) klocksync-indikator(er)."
)
