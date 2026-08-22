#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
PLAN = ROOT / "data" / "plan.json"
ICONS = ROOT / "data" / "sport_icons.json"
GOAL = ROOT / "malbild" / "index.html"
GOAL_MIRROR = ROOT / "malbild-2027" / "index.html"

VALID_STATUSES = {"completed", "planned", "preliminary", "conditional", "open"}
VALID_MANUAL_STATUSES = {"completed"}
VALID_CLASSIFICATIONS = {"training", "recreation"}
REQUIRED_ICON_KEYS = {"run", "swim", "bike", "enduro", "strength"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    for path in (INDEX, PLAN, ICONS, GOAL, GOAL_MIRROR):
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

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    days = plan.get("days", [])
    require(len(days) == 7, f"Preflight: aktuell vecka ska ha 7 dagar, fick {len(days)}")
    dates = [day.get("date") for day in days]
    require(len(set(dates)) == len(dates), "Preflight: dubbla datum i plan.json")

    expected_manual = 0
    for day in days:
        status = day.get("status")
        date = day.get("date")
        require(status in VALID_STATUSES, f"Preflight: ogiltig status {status!r} för {date}")
        require(bool((day.get("session") or "").strip()), f"Preflight: tom session för {date}")

        if "sport" in day:
            require(bool((day.get("sport") or "").strip()), f"Preflight: tom sport för {date}")
        if "classification" in day:
            require(
                day.get("classification") in VALID_CLASSIFICATIONS,
                f"Preflight: ogiltig classification {day.get('classification')!r} för {date}",
            )

        for activity in day.get("manual_activities") or []:
            expected_manual += 1
            require(
                activity.get("status") in VALID_MANUAL_STATUSES,
                f"Preflight: manuell aktivitet måste vara completed för {date}",
            )
            require(
                bool((activity.get("sport") or "").strip()),
                f"Preflight: manuell aktivitet saknar sport för {date}",
            )
            require(
                activity.get("classification") in VALID_CLASSIFICATIONS,
                f"Preflight: ogiltig manuell classification för {date}",
            )
            require(
                bool((activity.get("session") or "").strip()),
                f"Preflight: manuell aktivitet saknar session för {date}",
            )

    index = INDEX.read_text(encoding="utf-8")
    require(index.count('class="goal-page-link"') == 1, "Preflight: exakt en Målbild-länk krävs")
    require('href="/träning/malbild-2027/"' in index, "Preflight: Målbild-länk pekar fel")
    require('<nav class="week-nav"' in index, "Preflight: veckonavigering saknas")
    require(
        index.count('class="manual-activity"') == expected_manual,
        "Preflight: renderade manuella aktiviteter matchar inte plan.json",
    )
    if expected_manual:
        require('class="sport-icon icon-enduro' in index, "Preflight: enduroikonen saknas")
        require('data-classification="recreation"' in index, "Preflight: rekreationsklassning saknas")

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
        "Preflight OK: plan, ikonregister, manuella aktiviteter, navigation och "
        "målbildens canonical/mirror-kontrakt är konsistenta."
    )


if __name__ == "__main__":
    main()
