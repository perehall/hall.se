#!/usr/bin/env python3
import json
from pathlib import Path

from training_contracts import PLAN_SCHEMA_VERSION, VALID_PLAN_SPORTS

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILES = [ROOT / "data" / "plan.json", ROOT / "data" / "upcoming_week.json"]
COACH_FILE = ROOT / "data" / "coach.json"

# One-time reviewed migration. No sport is inferred from Swedish free text.
# Unknown dates fail closed instead of being guessed.
SPORT_BY_DATE = {
    "2026-08-17": "swim",
    "2026-08-18": "strength",
    "2026-08-19": "swimrun",
    "2026-08-20": "run",
    "2026-08-21": "swim",
    "2026-08-22": "enduro",
    "2026-08-23": "run",
    "2026-08-24": "enduro",
    "2026-08-25": "swim",
    "2026-08-26": "run",
    "2026-08-27": "strength",
    "2026-08-28": "swim",
    "2026-08-29": "bike",
    "2026-08-30": "open",
}


def migrate_plan(path):
    if not path.exists():
        return False
    document = json.loads(path.read_text(encoding="utf-8"))
    version = document.get("schema_version")
    if version == PLAN_SCHEMA_VERSION:
        for day in document.get("days", []):
            if day.get("sport") not in VALID_PLAN_SPORTS:
                raise RuntimeError(f"Migration v3: {path.name} har ogiltig sport för {day.get('date')}")
        return False
    if version not in (None, 2):
        raise RuntimeError(f"Migration v3: stöder inte schema_version {version!r} i {path.name}")

    for day in document.get("days", []):
        day_date = day.get("date")
        expected = SPORT_BY_DATE.get(day_date)
        if not expected:
            raise RuntimeError(
                f"Migration v3: saknar explicit, granskad sportmapping för {day_date!r}; vägrar gissa"
            )
        existing = day.get("sport")
        if existing and existing != expected:
            raise RuntimeError(
                f"Migration v3: {day_date} har sport {existing!r}, men migrationen förväntar {expected!r}"
            )
        day["sport"] = expected

    document["schema_version"] = PLAN_SCHEMA_VERSION
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def migrate_coach_history():
    if not COACH_FILE.exists():
        return False
    document = json.loads(COACH_FILE.read_text(encoding="utf-8"))
    changed = False
    for entry in document.get("analyses") or []:
        assessment = entry.get("assessment") or {}
        if assessment.get("confidence") == "high" and assessment.get("unknowns"):
            assessment["confidence"] = "medium"
            changed = True
    if changed:
        COACH_FILE.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main():
    changed = [path.name for path in PLAN_FILES if migrate_plan(path)]
    if migrate_coach_history():
        changed.append(COACH_FILE.name)
    if changed:
        print("Migration v3 OK: " + ", ".join(changed))
    else:
        print("Migration v3: redan migrerat; inga ändringar.")


if __name__ == "__main__":
    main()
