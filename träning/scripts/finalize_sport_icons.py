#!/usr/bin/env python3
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
INDEX_FILE = ROOT / "index.html"

plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
activities_state = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
page = INDEX_FILE.read_text(encoding="utf-8")

activity_dates = {
    (activity.get("start_date_local") or "")[:10]
    for activity in activities_state.get("activities", [])
    if len(activity.get("start_date_local") or "") >= 10
}

# Recognizable sport silhouettes from Font Awesome Free 6.7.2.
# Icons: CC BY 4.0. Copyright 2024 Fonticons, Inc. https://fontawesome.com
SOLID_ICONS = {
    "run": (
        "0 0 448 512",
        "M320 48a48 48 0 1 0-96 0 48 48 0 1 0 96 0zM125.7 175.5c9.9-9.9 23.4-15.5 37.5-15.5 1.9 0 3.8.1 5.6.3L137.6 254c-9.3 28 1.7 58.8 26.8 74.5l86.2 53.9-25.4 88.8c-4.9 17 5 34.7 22 39.6s34.7-5 39.6-22l28.7-100.4c5.9-20.6-2.6-42.6-20.7-53.9L238 299l30.9-82.4 5.1 12.3C289 264.7 323.9 288 362.7 288H384c17.7 0 32-14.3 32-32s-14.3-32-32-32h-21.3c-12.9 0-24.6-7.8-29.5-19.7l-6.3-15c-14.6-35.1-44.1-61.9-80.5-73.1l-48.7-15c-11.1-3.4-22.7-5.2-34.4-5.2-31 0-60.8 12.3-82.7 34.3l-23.2 23.1c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0l23.1-23.1zM91.2 352H32c-17.7 0-32 14.3-32 32s14.3 32 32 32h69.6c19 0 36.2-11.2 43.9-28.5l11.5-25.9-9.5-6c-17.5-10.9-30.5-26.8-37.9-44.9L91.2 352z",
    ),
    "swim": (
        "0 0 576 512",
        "M309.5 178.4 447.9 297.1c-1.6.9-3.2 2-4.8 3-18 12.4-40.1 20.3-59.2 20.3-19.6 0-40.8-7.7-59.2-20.3-22.1-15.5-51.6-15.5-73.7 0-17.1 11.8-38 20.3-59.2 20.3-10.1 0-21.1-2.2-31.9-6.2C163.1 193.2 262.2 96 384 96h64c17.7 0 32 14.3 32 32s-14.3 32-32 32h-64c-26.9 0-52.3 6.6-74.5 18.4zM160 160A64 64 0 1 1 32 160a64 64 0 1 1 128 0zM306.5 325.9C329 341.4 356.5 352 384 352c26.9 0 55.4-10.8 77.4-26.1 11.9-8.5 28.1-7.8 39.2 1.7 14.4 11.9 32.5 21 50.6 25.2 17.2 4 27.9 21.2 23.9 38.4s-21.2 27.9-38.4 23.9c-24.5-5.7-44.9-16.5-58.2-25C449.5 405.7 417 416 384 416c-31.9 0-60.6-9.9-80.4-18.9-5.8-2.7-11.1-5.3-15.6-7.7-4.5 2.4-9.7 5.1-15.6 7.7-19.8 9-48.5 18.9-80.4 18.9-33 0-65.5-10.3-94.5-25.8-13.4 8.4-33.7 19.3-58.2 25-17.2 4-34.4-6.7-38.4-23.9s6.7-34.4 23.9-38.4c18.1-4.2 36.2-13.3 50.6-25.2 11.1-9.4 27.3-10.1 39.2-1.7C136.7 341.2 165.1 352 192 352c27.5 0 55-10.6 77.5-26.1 11.1-7.9 25.9-7.9 37 0z",
    ),
    "bike": (
        "0 0 640 512",
        "M312 32c-13.3 0-24 10.7-24 24s10.7 24 24 24h25.7l34.6 64H222.9l-27.4-38C191 99.7 183.7 96 176 96h-56c-13.3 0-24 10.7-24 24s10.7 24 24 24h43.7l22.1 30.7-26.6 53.1c-10-2.5-20.5-3.8-31.2-3.8C57.3 224 0 281.3 0 352s57.3 128 128 128c65.3 0 119.1-48.9 127-112h49c8.5 0 16.3-4.5 20.7-11.8l84.8-143.5 21.7 40.1C402.4 276.3 384 312 384 352c0 70.7 57.3 128 128 128s128-57.3 128-128-57.3-128-128-128c-13.5 0-26.5 2.1-38.7 6L375.4 48.8C369.8 38.4 359 32 347.2 32H312zM458.6 303.7l32.3 59.7c6.3 11.7 20.9 16 32.5 9.7s16-20.9 9.7-32.5l-32.3-59.7c3.6-.6 7.4-.9 11.2-.9 39.8 0 72 32.2 72 72s-32.2 72-72 72-72-32.2-72-72c0-18.6 7-35.5 18.6-48.3zM133.2 368h65c-7.3 32.1-36 56-70.2 56-39.8 0-72-32.2-72-72s32.2-72 72-72c1.7 0 3.4.1 5.1.2l-24.2 48.5c-9 18.1 4.1 39.4 24.3 39.4zm33.7-48 50.7-101.3 72.9 101.2-.1.1H166.9zm90.6-128H366L317 274.8 257.4 192z",
    ),
    "strength": (
        "0 0 640 512",
        "M96 64c0-17.7 14.3-32 32-32h32c17.7 0 32 14.3 32 32v160 64 160c0 17.7-14.3 32-32 32h-32c-17.7 0-32-14.3-32-32v-64H64c-17.7 0-32-14.3-32-32v-64c-17.7 0-32-14.3-32-32s14.3-32 32-32v-64c0-17.7 14.3-32 32-32h32V64zm448 0v64h32c17.7 0 32 14.3 32 32v64c17.7 0 32 14.3 32 32s-14.3 32-32 32v64c0 17.7-14.3 32-32 32h-32v64c0 17.7-14.3 32-32 32h-32c-17.7 0-32-14.3-32-32V288 224 64c0-17.7 14.3-32 32-32h32c17.7 0 32 14.3 32 32zM416 224v64H224v-64h192z",
    ),
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
    if name in SOLID_ICONS:
        view_box, path = SOLID_ICONS[name]
        return (
            f'<svg class="{cls}" aria-hidden="true" viewBox="{view_box}" '
            'fill="currentColor" xmlns="http://www.w3.org/2000/svg">'
            f'<path d="{path}"/></svg>'
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
    if "mtb" in text or "cykel" in text or "bike" in text or "enduro" in text:
        return "bike"
    if "styrk" in text or "weight" in text:
        return "strength"
    if "löp" in text or "trail" in text or "run" in text:
        return "run"
    return "activity"


def watch_chip():
    return (
        '<span class="watch-sync" title="Strukturerat simpass synkas automatiskt via Intervals.icu till Garmin">'
        f'{icon("watch", "watch-icon")}<span>Klocksync aktiv</span></span>'
    )


sport_pattern = re.compile(r'<div class="sport-head"><span>([^<]+)</span><strong>')


def sport_repl(match):
    label = match.group(1)
    sport_name = label.split(" (", 1)[0]
    return (
        '<div class="sport-head"><span class="sport-name">'
        f'{icon(icon_for_text(sport_name))}{label}</span><strong>'
    )


page, sport_icon_count = sport_pattern.subn(sport_repl, page)

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

    sport = icon_for_text(day.get("session", ""))
    if '<div class="swim-workout compact"><div class="swim-session-head"><strong>' in segment:
        segment = segment.replace(
            '<div class="swim-workout compact"><div class="swim-session-head"><strong>',
            '<div class="swim-workout compact"><div class="swim-session-head"><strong class="session-with-icon">'
            + icon(sport),
            1,
        )
    else:
        escaped_session = html.escape(day.get("session", ""))
        needle = f'<div>{escaped_session}</div>'
        if needle in segment:
            segment = segment.replace(
                needle,
                f'<div class="next-session">{icon(sport)}<span>{escaped_session}</span></div>',
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
    marker = f'<div class="day" id="dag-{html.escape(date)}">'
    start = page.find(marker)
    if start < 0:
        raise RuntimeError(f"Sportikoner: detaljkort saknas för klocksync {date}")
    next_day = page.find('<div class="day" id="dag-', start + len(marker))
    next_section = page.find('<h2 class="section">', start + len(marker))
    candidates = [pos for pos in (next_day, next_section) if pos >= 0]
    end = min(candidates) if candidates else len(page)
    segment = page[start:end]
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

css_marker = "/* sport-icons-v1 */"
if css_marker not in page:
    css = r'''
/* sport-icons-v1 */
.sport-name,.next-session,.session-with-icon{display:inline-flex;align-items:center;gap:8px;min-width:0}.sport-icon{width:18px;height:18px;flex:0 0 auto;color:#64748b}.sport-icon.icon-swim{width:20px}.sport-icon.icon-bike{width:20px}.sport-icon.icon-strength{width:20px}.sport-name .sport-icon{height:18px}.next-session{font-weight:600}.session-with-icon{font-weight:800}.watch-sync{display:inline-flex;align-items:center;gap:4px;width:max-content;padding:3px 7px;border:1px solid #cbd5e1;border-radius:999px;background:#f8fafc;color:#475569;font-size:.68rem;font-weight:800;line-height:1.2;white-space:nowrap}.watch-sync .watch-icon{width:13px;height:13px;color:#475569}.swim-session-head{row-gap:6px}.next-item .sport-icon{position:relative;z-index:1}
@media (max-width:520px){.sport-icon{width:17px;height:17px}.sport-icon.icon-swim,.sport-icon.icon-bike,.sport-icon.icon-strength{width:19px}.watch-sync{font-size:.64rem;padding:3px 6px}}
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
    if f'data-next-date="{date}"' in rendered:
        start = rendered.find(f'<div class="next-item" data-next-date="{date}">')
        end = rendered.find('<div class="next-item" data-next-date="', start + 1)
        if end < 0:
            end = rendered.find('</section>', start)
        segment = rendered[start:end]
        if 'class="sport-icon' not in segment:
            raise RuntimeError(f"Sportikoner: Kommande dagar saknar ikon för {date}")

watch_days = [
    day for day in plan.get("days", [])
    if (day.get("watch_workout") or {}).get("sync_enabled") is True
    and day.get("status") == "planned"
    and day.get("date", "") not in activity_dates
]
for day in watch_days:
    date = day.get("date", "")
    card_start = rendered.find(f'<div class="day" id="dag-{date}">')
    if card_start < 0:
        raise RuntimeError(f"Sportikoner: detaljkort saknas för verifiering {date}")
    card_end = rendered.find('<div class="day" id="dag-', card_start + 1)
    if card_end < 0:
        card_end = rendered.find('<h2 class="section">', card_start + 1)
    if 'class="watch-sync"' not in rendered[card_start:card_end]:
        raise RuntimeError(f"Sportikoner: klocksync-indikator saknas för {date}")

print(
    f"Sportikoner OK: {sport_icon_count} grenrader dekorerade, "
    f"{len(watch_days)} aktiv(a) klocksync-indikator(er)."
)
