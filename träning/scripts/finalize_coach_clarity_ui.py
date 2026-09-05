#!/usr/bin/env python3
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "index.html"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
COACH_FILE = ROOT / "data" / "coach.json"


def compact_text(value, max_chars=180):
    text = html.unescape(re.sub(r"\s+", " ", str(value or ""))).strip()
    if not text:
        return ""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    compact = sentences[0] if sentences else text
    if len(compact) <= max_chars:
        return compact
    clipped = compact[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return (clipped or compact[: max_chars - 1]).rstrip() + "…"


def compact_day_motivations(page):
    pattern = re.compile(
        r'(<details class="day-why"><summary>Motivering</summary><div class="reason">)(.*?)(</div></details>)',
        re.S,
    )

    def replace(match):
        return match.group(1) + html.escape(compact_text(match.group(2))) + match.group(3)

    return pattern.sub(replace, page)


def activity_dates(activities_state):
    dates = set()
    for activity in (activities_state or {}).get("activities") or []:
        local = str(activity.get("start_date_local") or "")
        if len(local) >= 10:
            dates.add(local[:10])
    return dates


def coach_dates(coach_state):
    return {
        str(item.get("activity_date"))
        for item in (coach_state or {}).get("analyses") or []
        if item.get("activity_date")
    }


def day_card_ranges(page):
    pattern = re.compile(r'<div class="day[^"]*" id="dag-(?P<date>\d{4}-\d{2}-\d{2})">')
    matches = list(pattern.finditer(page))
    ranges = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page)
        ranges.append((match.start(), end, match.group("date")))
    return ranges


def remove_superseded_preworkout_adjustments(page, activities_state, coach_state):
    superseded_dates = activity_dates(activities_state) & coach_dates(coach_state)
    if not superseded_dates:
        return page

    for start, end, day_text in reversed(day_card_ranges(page)):
        if day_text not in superseded_dates:
            continue
        block = page[start:end]
        block = re.sub(
            r'<div class="decision coach-adjust"><strong>.*?</strong>.*?</div>',
            "",
            block,
            flags=re.S,
        )
        page = page[:start] + block + page[end:]
    return page


def apply_clarity_contract(page, activities_state, coach_state):
    page = compact_day_motivations(page)
    page = remove_superseded_preworkout_adjustments(page, activities_state, coach_state)
    return page


def main():
    page = INDEX_FILE.read_text(encoding="utf-8")
    activities = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
    coach = json.loads(COACH_FILE.read_text(encoding="utf-8")) if COACH_FILE.exists() else {"analyses": []}
    updated = apply_clarity_contract(page, activities, coach)
    INDEX_FILE.write_text(updated, encoding="utf-8")
    print("Coach clarity UI: kort passmotivering och inga stale för-pass-justeringar efter ny passanalys.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
