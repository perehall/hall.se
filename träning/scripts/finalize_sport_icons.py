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


def icon(name, extra_class=""):
    paths = {
        "swim": (
            '<circle cx="6.2" cy="6.8" r="1.7"/>'
            '<path d="M7.8 9.2l3.3 1.4 2.6-2.4M10.9 10.6l-2.2 3.2"/>'
            '<path d="M2.5 15.7c1.8-1.2 3.5-1.2 5.2 0s3.5 1.2 5.2 0 3.5-1.2 5.2 0 2.6 1.2 3.4.5"/>'
            '<path d="M2.5 19c1.8-1.2 3.5-1.2 5.2 0s3.5 1.2 5.2 0 3.5-1.2 5.2 0 2.6 1.2 3.4.5"/>'
        ),
        "run": (
            '<circle cx="8.2" cy="5.1" r="1.6"/>'
            '<path d="M9.3 8.1l3 2.1 2.8-.8M10.8 9.2l-1.6 4.2-3.4 2.8M9.2 13.4l3.6 2.1 1.5 3.3M12.2 10.2l-1 3.2"/>'
        ),
        "bike": (
            '<circle cx="5.5" cy="17" r="3.2"/><circle cx="18.5" cy="17" r="3.2"/>'
            '<path d="M5.5 17l4-7h4l5 7M9.5 10l3 7H5.5M12.5 17h6M14 7.5h3"/>'
        ),
        "strength": (
            '<path d="M3 9v6M6 7.5v9M18 7.5v9M21 9v6M6 12h12"/>'
        ),
        "activity": (
            '<path d="M3 12h4l2-5 4 10 2-5h6"/>'
        ),
        "watch": (
            '<rect x="7" y="5" width="10" height="14" rx="2.2"/>'
            '<path d="M9.5 5V2.5h5V5M9.5 19v2.5h5V19M12 9v3l2 1.5"/>'
        ),
    }
    body = paths.get(name, paths["activity"])
    cls = "sport-icon" + (f" {extra_class}" if extra_class else "")
    return (
        f'<svg class="{cls}" aria-hidden="true" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.7" '
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


# Grenfördelning: dekorera bara de faktiska sport-raderna.
sport_pattern = re.compile(r'<div class="sport-head"><span>([^<]+)</span><strong>')


def sport_repl(match):
    label = match.group(1)
    sport_name = label.split(" (", 1)[0]
    return (
        '<div class="sport-head"><span class="sport-name">'
        f'{icon(icon_for_text(sport_name))}{label}</span><strong>'
    )


page, sport_icon_count = sport_pattern.subn(sport_repl, page)

# Kommande dagar: varje rad får ikon utifrån planerad gren.
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

# Detaljkort: klocksync visas endast medan passet verkligen är export-aktuellt.
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
.sport-name,.next-session,.session-with-icon{display:inline-flex;align-items:center;gap:7px;min-width:0}.sport-icon{width:17px;height:17px;flex:0 0 auto;color:#64748b}.sport-name .sport-icon{width:16px;height:16px}.next-session{font-weight:600}.session-with-icon{font-weight:800}.watch-sync{display:inline-flex;align-items:center;gap:4px;width:max-content;padding:3px 7px;border:1px solid #cbd5e1;border-radius:999px;background:#f8fafc;color:#475569;font-size:.68rem;font-weight:800;line-height:1.2;white-space:nowrap}.watch-sync .watch-icon{width:13px;height:13px;color:#475569}.swim-session-head{row-gap:6px}.next-item .sport-icon{position:relative;z-index:1}
@media (max-width:520px){.sport-icon{width:16px;height:16px}.watch-sync{font-size:.64rem;padding:3px 6px}}
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
