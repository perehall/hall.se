#!/usr/bin/env python3
import json
import re
from pathlib import Path

from training_contracts import ACTIVITIES_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES = ROOT / "data" / "activities.json"
OVERRIDES = ROOT / "data" / "activity_overrides.json"
COACH = ROOT / "data" / "coach.json"

ENDURO_NAME_RE = re.compile(r"\b(?:enduro|motocross)\b", re.IGNORECASE)
MTB_NAME_RE = re.compile(r"\b(?:mtb|xc|mountain\s*bike|cykel)\b", re.IGNORECASE)
SWIMRUN_NAME_RE = re.compile(r"\bswim\s*-?\s*run\b|\bswimrun\b", re.IGNORECASE)
ENDURO_NAME_RULE = "mountainbike-explicit-enduro-name-v1"
SWIMRUN_NAME_RULE = "trailrun-explicit-swimrun-name-v1"
COACH_SEMANTIC_FIELDS = (
    "sport_type",
    "display_label",
    "classification",
    "source_sport_type",
    "user_report",
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(state):
    ACTIVITIES.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def raw_sport(activity):
    return activity.get("source_sport_type") or activity.get("sport_type") or ""


def coach_semantic_fingerprint(activity):
    return tuple(activity.get(field) for field in COACH_SEMANTIC_FIELDS)


def auto_enduro_candidate(activity):
    """Return True only for a strong, explicit Enduro/Motocross name signal.

    Strava exposes Garmin motocross/enduro recordings as MountainBikeRide in
    this dataset. A name that explicitly says Enduro or Motocross is therefore
    a strong user/source signal. Explicit MTB/XC/bike wording blocks automatic
    reclassification because MTB enduro is a legitimate cycling discipline.
    """
    if raw_sport(activity) != "MountainBikeRide":
        return False
    name = str(activity.get("name") or "").strip()
    if not name or not ENDURO_NAME_RE.search(name):
        return False
    if MTB_NAME_RE.search(name):
        return False
    return True


def auto_swimrun_candidate(activity):
    """Return True when a Strava TrailRun explicitly identifies itself as swimrun.

    Garmin/Strava commonly expose multisport swimrun recordings as TrailRun in
    this dataset. The explicit activity name is therefore the strongest
    available semantic signal once the user has named the activity in Strava.
    """
    if raw_sport(activity) != "TrailRun":
        return False
    name = str(activity.get("name") or "").strip()
    return bool(name and SWIMRUN_NAME_RE.search(name))


def apply_auto_semantics(activity):
    if auto_enduro_candidate(activity):
        original = raw_sport(activity)
        activity["source_sport_type"] = original
        activity["sport_type"] = "Enduro"
        activity["display_label"] = "Enduro"
        activity["sport_normalization"] = {
            "rule": ENDURO_NAME_RULE,
            "evidence": ["source_sport_type=MountainBikeRide", "explicit Enduro/Motocross activity name"],
        }
        return True

    if auto_swimrun_candidate(activity):
        original = raw_sport(activity)
        activity["source_sport_type"] = original
        activity["sport_type"] = "Swimrun"
        activity["display_label"] = "Swimrun"
        activity["sport_normalization"] = {
            "rule": SWIMRUN_NAME_RULE,
            "evidence": ["source_sport_type=TrailRun", "explicit Swimrun activity name"],
        }
        return True

    return False


def apply_override(activity, override, key):
    original = raw_sport(activity)
    expected_raw = override.get("source_sport_type") or ""
    if expected_raw and original != expected_raw:
        raise RuntimeError(
            f"Aktivitetsnormalisering: aktivitet {key} har rå sport {original!r}, "
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

    activity["source_sport_type"] = original
    activity["sport_type"] = effective_sport
    activity["classification"] = classification
    activity["display_label"] = override.get("display_label") or effective_sport
    activity.pop("sport_normalization", None)
    if override.get("garmin_activity_type"):
        activity["garmin_activity_type"] = override["garmin_activity_type"]
    if override.get("user_report"):
        activity["user_report"] = override["user_report"]
    if override.get("reason"):
        activity["classification_reason"] = override["reason"]


def invalidate_coach_analyses(path: Path, changed_ids):
    changed = {str(value) for value in changed_ids if str(value)}
    if not changed or not path.exists():
        return 0

    coach = load(path)
    analyses = coach.get("analyses") or []
    kept = [entry for entry in analyses if str(entry.get("activity_id")) not in changed]
    removed = len(analyses) - len(kept)
    if removed:
        coach["analyses"] = kept
    if removed or coach.get("last_trigger_hash") is not None:
        coach["last_trigger_hash"] = None
        path.write_text(json.dumps(coach, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return removed


def apply_semantics(state, config=None):
    if not isinstance(state, dict):
        raise RuntimeError("Aktivitetsnormalisering: state måste vara objekt")
    state["schema_version"] = ACTIVITIES_SCHEMA_VERSION
    config = config or {"schema_version": 1, "overrides": {}}
    overrides = config.get("overrides") or {}
    activities = state.get("activities") or []
    if not isinstance(activities, list):
        raise RuntimeError("Aktivitetsnormalisering: activities måste vara lista")

    override_applied = 0
    auto_applied = 0
    seen = set()
    changed_ids = set()

    for activity in activities:
        activity_id = activity.get("id")
        key = str(activity_id) if activity_id is not None else ""
        before = coach_semantic_fingerprint(activity)
        override = overrides.get(key)
        if override:
            seen.add(key)
            apply_override(activity, override, key)
            override_applied += 1
        elif apply_auto_semantics(activity):
            auto_applied += 1
        after = coach_semantic_fingerprint(activity)
        if key and before != after:
            changed_ids.add(key)

    state["activity_semantics"] = {
        "schema_version": config.get("schema_version", 1),
        "overrides_applied": override_applied,
        "auto_rules_applied": auto_applied,
        "override_ids_present": sorted(seen),
        "changed_ids": sorted(changed_ids),
    }
    return override_applied, auto_applied, seen


def main():
    if not ACTIVITIES.exists():
        raise RuntimeError("Aktivitetsnormalisering: activities.json saknas")

    state = load(ACTIVITIES)
    config = load(OVERRIDES) if OVERRIDES.exists() else {"schema_version": 1, "overrides": {}}
    applied, auto_applied, seen = apply_semantics(state, config)
    changed_ids = state.get("activity_semantics", {}).get("changed_ids") or []
    write_state(state)
    invalidated = invalidate_coach_analyses(COACH, changed_ids)

    rendered = load(ACTIVITIES)
    if rendered.get("schema_version") != ACTIVITIES_SCHEMA_VERSION:
        raise RuntimeError("Aktivitetsnormalisering: schemaversion verifierades inte")
    by_id = {str(a.get("id")): a for a in rendered.get("activities", [])}
    overrides = config.get("overrides") or {}
    for key in seen:
        override = overrides[key]
        activity = by_id[key]
        if activity.get("sport_type") != override.get("sport"):
            raise RuntimeError(f"Aktivitetsnormalisering: effektiv sport verifierades inte för {key}")
        if activity.get("classification") != override.get("classification"):
            raise RuntimeError(f"Aktivitetsnormalisering: classification verifierades inte för {key}")

    print(
        f"Aktivitetsnormalisering OK: schema v{ACTIVITIES_SCHEMA_VERSION}, "
        f"{applied} explicit override(s), {auto_applied} auto-regel(er) applicerade, "
        f"{invalidated} stale coach-analys(er) invaliderade."
    )


if __name__ == "__main__":
    main()
