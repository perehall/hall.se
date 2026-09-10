#!/usr/bin/env python3
"""Re-materialize immutable coach source facts after language normalization.

The first assessment fact is deterministic source data, not model prose. UI/language
normalizers may change visible interpretation text, but they must not become the
source of truth for this fact. Rebuild it from the normalized activity immediately
before the site is rendered.
"""

from __future__ import annotations

import json
from pathlib import Path

from coach_rules import canonical_activity_fact

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
COACH_FILE = ROOT / "data" / "coach.json"


def load(path: Path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def enforce_canonical_facts(coach, activities_state):
    by_id = {
        str(activity.get("id")): activity
        for activity in (activities_state.get("activities") or [])
        if activity.get("id") is not None
    }
    changed = 0

    for entry in coach.get("analyses") or []:
        activity = by_id.get(str(entry.get("activity_id")))
        if not activity:
            continue

        assessment = entry.setdefault("assessment", {})
        facts = assessment.get("facts")
        if not isinstance(facts, list):
            facts = []

        canonical = canonical_activity_fact(activity)
        if facts and facts[0] == canonical:
            continue

        assessment["facts"] = [canonical] + facts[1:] if facts else [canonical]
        changed += 1

    return changed


def main():
    coach = load(COACH_FILE, {"analyses": []})
    activities = load(ACTIVITIES_FILE, {"activities": []})
    changed = enforce_canonical_facts(coach, activities)
    if changed:
        COACH_FILE.write_text(
            json.dumps(coach, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Canonical coach facts OK: {changed} första faktarad(er) återställda från källdata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
