#!/usr/bin/env python3
import json
from pathlib import Path

from training_contracts import ACTIVITIES_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES = ROOT / "data" / "activities.json"
OVERRIDES = ROOT / "data" / "activity_overrides.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(state):
    ACTIVITIES.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    if not ACTIVITIES.exists():
        raise RuntimeError("Aktivitetsnormalisering: activities.json saknas")

    state = load(ACTIVITIES)
    state["schema_version"] = ACTIVITIES_SCHEMA_VERSION

    if not OVERRIDES.exists():
        write_state(state)
        print("Aktivitetsnormalisering: inga overrides; schemaversion satt och Strava-data lämnad oförändrad.")
        return

    config = load(OVERRIDES)
    overrides = config.get("overrides") or {}
    activities = state.get("activities") or []

    applied = 0
    seen = set()
    for activity in activities:
        activity_id = activity.get("id")
        key = str(activity_id) if activity_id is not None else ""
        override = overrides.get(key)
        if not override:
            continue

        seen.add(key)
        raw_sport = activity.get("source_sport_type") or activity.get("sport_type") or ""
        expected_raw = override.get("source_sport_type") or ""
        if expected_raw and raw_sport != expected_raw:
            raise RuntimeError(
                f"Aktivitetsnormalisering: aktivitet {key} har rå sport {raw_sport!r}, "
                f"men override förväntar {expected_raw!r}"
            )

        effective_sport = (override.get("sport") or "").strip()
        classification = (override.get("classification") or "").strip()
        if not effective_sport:
            raise RuntimeError(f"Aktivitetsnormalisering: override {key} saknar sport")
        if classification not in {"training", "recreation"}:
            raise RuntimeError(
                f"Aktivitetsnormalisering: override {key} har ogiltig classification {classification!r}"
            )

        activity["source_sport_type"] = raw_sport
        activity["sport_type"] = effective_sport
        activity["classification"] = classification
        activity["display_label"] = override.get("display_label") or effective_sport
        if override.get("garmin_activity_type"):
            activity["garmin_activity_type"] = override["garmin_activity_type"]
        if override.get("user_report"):
            activity["user_report"] = override["user_report"]
        if override.get("reason"):
            activity["classification_reason"] = override["reason"]
        applied += 1

    state["activity_semantics"] = {
        "schema_version": config.get("schema_version", 1),
        "overrides_applied": applied,
        "override_ids_present": sorted(seen),
    }
    write_state(state)

    rendered = load(ACTIVITIES)
    if rendered.get("schema_version") != ACTIVITIES_SCHEMA_VERSION:
        raise RuntimeError("Aktivitetsnormalisering: schemaversion verifierades inte")
    by_id = {str(a.get("id")): a for a in rendered.get("activities", [])}
    for key in seen:
        override = overrides[key]
        activity = by_id[key]
        if activity.get("sport_type") != override.get("sport"):
            raise RuntimeError(f"Aktivitetsnormalisering: effektiv sport verifierades inte för {key}")
        if activity.get("classification") != override.get("classification"):
            raise RuntimeError(f"Aktivitetsnormalisering: classification verifierades inte för {key}")

    print(f"Aktivitetsnormalisering OK: schema v{ACTIVITIES_SCHEMA_VERSION}, {applied} explicit override(s) applicerade.")


if __name__ == "__main__":
    main()
