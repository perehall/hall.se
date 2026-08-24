#!/usr/bin/env python3
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
PLAN = ROOT / "data" / "plan.json"
ACTIVITIES = ROOT / "data" / "activities.json"
OVERRIDES = ROOT / "data" / "activity_overrides.json"
ICONS = ROOT / "data" / "sport_icons.json"
WEEKS_MANIFEST = ROOT / "data" / "weeks" / "index.json"
WEEK_PAGES = ROOT / "vecka"
GOAL = ROOT / "malbild" / "index.html"
GOAL_MIRROR = ROOT / "malbild-2027" / "index.html"

VALID_STATUSES = {"completed", "planned", "preliminary", "conditional", "open"}
VALID_MANUAL_STATUSES = {"completed"}
VALID_CLASSIFICATIONS = {"training", "recreation"}
REQUIRED_ICON_KEYS = {"run", "swim", "bike", "enduro", "strength"}
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
    "rest": None,
    "open": None,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    for path in (INDEX, PLAN, ACTIVITIES, OVERRIDES, ICONS, WEEKS_MANIFEST, GOAL, GOAL_MIRROR):
        require(path.exists(), f"Preflight: fil saknas: {path}")

    icon_data = json.loads(ICONS.read_text(encoding="utf-8"))
    icons = icon_data.get("icons", {})
    require(
        REQUIRED_ICON_KEYS.issubset(icons),
        f"Preflight: ikonregistret saknar {sorted(REQUIRED_ICON_KEYS - set(icons))}",
    )
    for key in REQUIRED_ICON_KEYS:
        require(bool(icons[key].get("viewBox")), f"Preflight: {key}-ikon saknar viewBox")
        require(bool(icons[key].get("path")), f"Preflight: {key}-ikon saknar path")

    activities_state = json.loads(ACTIVITIES.read_text(encoding="utf-8"))
    activities_by_id = {
        str(activity.get("id")): activity
        for activity in activities_state.get("activities", [])
        if activity.get("id") is not None
    }
    override_data = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    overrides = override_data.get("overrides") or {}
    for activity_id, override in overrides.items():
        activity = activities_by_id.get(str(activity_id))
        if not activity:
            continue
        require(
            activity.get("sport_type") == override.get("sport"),
            f"Preflight: aktivitet {activity_id} är inte normaliserad till {override.get('sport')!r}",
        )
        require(
            activity.get("classification") == override.get("classification"),
            f"Preflight: aktivitet {activity_id} har fel classification",
        )
        require(
            activity.get("source_sport_type") == override.get("source_sport_type"),
            f"Preflight: aktivitet {activity_id} saknar korrekt rå sporttyp",
        )

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    days = plan.get("days", [])
    require(len(days) == 7, f"Preflight: aktuell vecka ska ha 7 dagar, fick {len(days)}")
    dates = [day.get("date") for day in days]
    require(len(set(dates)) == len(dates), "Preflight: dubbla datum i plan.json")

    meta = plan.get("meta") or {}
    week_start = date.fromisoformat(meta.get("week_start"))
    iso = week_start.isocalendar()
    current_key = f"{iso.year}-W{iso.week:02d}"
    duplicate_current_dir = WEEK_PAGES / current_key
    require(
        not duplicate_current_dir.exists(),
        f"Preflight: aktuell vecka får endast publiceras via /träning/; ta bort {duplicate_current_dir}",
    )

    manifest = json.loads(WEEKS_MANIFEST.read_text(encoding="utf-8"))
    require(
        manifest.get("current_week_key") == current_key,
        f"Preflight: veckomanifestets current_week_key matchar inte {current_key}",
    )
    current_records = [row for row in manifest.get("weeks", []) if row.get("key") == current_key]
    require(len(current_records) == 1, "Preflight: exakt en manifestpost krävs för aktuell vecka")
    require(current_records[0].get("is_current") is True, "Preflight: aktuell manifestpost saknar is_current=true")
    require(
        current_records[0].get("url") == "/träning/",
        "Preflight: aktuell vecka måste ha canonical URL /träning/ i veckomanifestet",
    )

    expected_manual = 0
    explicit_sport_days = []
    for day in days:
        status = day.get("status")
        day_date = day.get("date")
        require(status in VALID_STATUSES, f"Preflight: ogiltig status {status!r} för {day_date}")
        require(bool((day.get("session") or "").strip()), f"Preflight: tom session för {day_date}")

        if "sport" in day:
            sport = (day.get("sport") or "").strip().lower()
            require(bool(sport), f"Preflight: tom sport för {day_date}")
            require(sport in SPORT_ICON_KEYS, f"Preflight: okänd explicit sport {sport!r} för {day_date}")
            explicit_sport_days.append((day_date, SPORT_ICON_KEYS[sport]))
        if "classification" in day:
            require(
                day.get("classification") in VALID_CLASSIFICATIONS,
                f"Preflight: ogiltig classification {day.get('classification')!r} för {day_date}",
            )

        for activity in day.get("manual_activities") or []:
            expected_manual += 1
            require(
                activity.get("status") in VALID_MANUAL_STATUSES,
                f"Preflight: manuell aktivitet måste vara completed för {day_date}",
            )
            require(
                bool((activity.get("sport") or "").strip()),
                f"Preflight: manuell aktivitet saknar sport för {day_date}",
            )
            require(
                activity.get("classification") in VALID_CLASSIFICATIONS,
                f"Preflight: ogiltig manuell classification för {day_date}",
            )
            require(
                bool((activity.get("session") or "").strip()),
                f"Preflight: manuell aktivitet saknar session för {day_date}",
            )

    index = INDEX.read_text(encoding="utf-8")
    duplicate_href = f'href="/träning/vecka/{current_key}/"'
    require(duplicate_href not in index, "Preflight: index länkar till en duplicerad aktuell veckosida")
    if WEEK_PAGES.exists():
        for page_path in WEEK_PAGES.glob("*/index.html"):
            page_text = page_path.read_text(encoding="utf-8")
            require(
                duplicate_href not in page_text,
                f"Preflight: {page_path} länkar till duplicerad aktuell vecka i stället för /träning/",
            )

    require(index.count('class="goal-page-link"') == 1, "Preflight: exakt en Målbild-länk krävs")
    require('href="/träning/malbild-2027/"' in index, "Preflight: Målbild-länk pekar fel")
    require('<nav class="week-nav"' in index, "Preflight: veckonavigering saknas")
    require(
        index.count('class="manual-activity"') == expected_manual,
        "Preflight: renderade manuella aktiviteter matchar inte plan.json",
    )

    for day_date, icon_key in explicit_sport_days:
        start = index.find(f'<div class="day" id="dag-{day_date}">')
        require(start >= 0, f"Preflight: dagkort saknas för {day_date}")
        if icon_key is None:
            continue
        end = index.find('<div class="day" id="dag-', start + 1)
        if end < 0:
            end = index.find('<h2 class="section">', start + 1)
        if end < 0:
            end = len(index)
        require(
            f'icon-{icon_key}' in index[start:end],
            f"Preflight: explicit sportikon {icon_key!r} saknas för {day_date}",
        )

    canonical = GOAL.read_text(encoding="utf-8")
    mirror = GOAL_MIRROR.read_text(encoding="utf-8")
    require(canonical == mirror, "Preflight: /malbild/ och /malbild-2027/ är inte identiska")

    require(canonical.count('class="mountain-phase-point') == 5, "Preflight: exakt fem fasmarkörer krävs")
    require(canonical.count('id="phase-trail"') == 1, "Preflight: exakt en phase-trail krävs")
    require(canonical.count('id="phase-trail-underlay"') == 1, "Preflight: exakt en phase-trail-underlay krävs")
    require(canonical.count('data-progress="') == 5, "Preflight: alla fem fasmarkörer måste vara path-bundna")
    require("getPointAtLength" in canonical, "Preflight: path-baserad markörplacering saknas")
    require(canonical.count("<!-- phase-trail-sync-v2 -->") == 2, "Preflight: exakt ett trail-sync-v2-block krävs")
    require("phase-trail-sync-v1" not in canonical, "Preflight: gammal trail-sync-v1 finns kvar")

    print(
        "Preflight OK: normaliserade aktiviteter, plan, ikoner, canonical veckonavigation och "
        "målbildens canonical/mirror-kontrakt är konsistenta."
    )


if __name__ == "__main__":
    main()
