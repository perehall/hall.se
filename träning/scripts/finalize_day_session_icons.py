#!/usr/bin/env python3
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "data" / "plan.json"
ICONS = ROOT / "data" / "sport_icons.json"
INDEX = ROOT / "index.html"

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


def icon(name: str, registry: dict) -> str:
    item = registry.get(name)
    if not item:
        raise RuntimeError(f"Dagikoner: ikon {name!r} saknas i registry")
    view_box = item.get("view_box")
    path = item.get("path")
    if not view_box or not path:
        raise RuntimeError(f"Dagikoner: ikon {name!r} är ofullständig")
    return (
        f'<svg class="sport-icon icon-{name}" aria-hidden="true" viewBox="{view_box}" '
        'fill="currentColor" xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{path}"/></svg>'
    )


def main():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    registry = json.loads(ICONS.read_text(encoding="utf-8")).get("icons") or {}
    page = INDEX.read_text(encoding="utf-8")

    decorated = 0
    for day in plan.get("days", []):
        sport = (day.get("sport") or "").strip().lower()
        if not sport:
            continue
        icon_key = SPORT_ICON_KEYS.get(sport)
        if not icon_key:
            raise RuntimeError(f"Dagikoner: okänd explicit sport {sport!r} för {day.get('date')}")

        date = day.get("date", "")
        card_start = page.find(f'<div class="day" id="dag-{html.escape(date)}">')
        if card_start < 0:
            raise RuntimeError(f"Dagikoner: dagkort saknas för {date}")
        card_end = page.find('<div class="day" id="dag-', card_start + 1)
        if card_end < 0:
            card_end = page.find('<h2 class="section">', card_start + 1)
        if card_end < 0:
            card_end = len(page)
        segment = page[card_start:card_end]

        escaped_session = html.escape(day.get("session", ""))
        plain = f'<div class="session">{escaped_session}</div>'
        already = f'<div class="session session-with-icon">{icon(icon_key, registry)}<span>{escaped_session}</span></div>'
        if already in segment:
            continue
        if plain not in segment:
            raise RuntimeError(f"Dagikoner: sessionsrad saknas för {date}")
        segment = segment.replace(plain, already, 1)
        page = page[:card_start] + segment + page[card_end:]
        decorated += 1

    INDEX.write_text(page, encoding="utf-8")
    rendered = INDEX.read_text(encoding="utf-8")
    for day in plan.get("days", []):
        sport = (day.get("sport") or "").strip().lower()
        if not sport:
            continue
        icon_key = SPORT_ICON_KEYS[sport]
        date = day.get("date", "")
        start = rendered.find(f'<div class="day" id="dag-{date}">')
        end = rendered.find('<div class="day" id="dag-', start + 1)
        if end < 0:
            end = rendered.find('<h2 class="section">', start + 1)
        if f'icon-{icon_key}' not in rendered[start:end]:
            raise RuntimeError(f"Dagikoner: ikon verifierades inte för {date}")

    print(f"Dagikoner OK: {decorated} explicit sportpass dekorerade.")


if __name__ == "__main__":
    main()
