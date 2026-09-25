#!/usr/bin/env python3
"""Apply durable operator-authored semantic corrections after backend hydration.

Supabase is the runtime authority for promoted activity state. The repository
activity_overrides.json is therefore only a compatibility cache and must not be
used as an input authority after hydration. This sidecar applies only explicitly
listed fields onto the freshly hydrated override projection, preserving newer
backend feedback and unrelated semantic state. The merged snapshot is promoted
back to Supabase later in the canonical pipeline.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ACTIVITIES_FILE = DATA / "activities.json"
OVERRIDES_FILE = DATA / "activity_overrides.json"
DIRECTIVES_FILE = DATA / "activity_directives.json"
COACH_FILE = DATA / "coach.json"


class ActivityDirectiveError(RuntimeError):
    pass


def load_json(path: Path, fallback: dict | None = None) -> dict:
    if not path.exists():
        if fallback is None:
            raise ActivityDirectiveError(f"activity directives: fil saknas: {path}")
        return deepcopy(fallback)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ActivityDirectiveError(f"activity directives: objekt krävs: {path}")
    return value


def apply_directives(activities: dict, overrides: dict, config: dict, changed_ids: set[str] | None = None) -> tuple[int, int]:
    if config.get("schema_version") != 1:
        raise ActivityDirectiveError("activity directives: schema_version måste vara 1")
    directives = config.get("directives")
    if not isinstance(directives, list):
        raise ActivityDirectiveError("activity directives: directives måste vara en lista")

    activity_ids = {
        str(row.get("id"))
        for row in (activities.get("activities") or [])
        if row.get("id") is not None
    }
    mapping = overrides.setdefault("overrides", {})
    if not isinstance(mapping, dict):
        raise ActivityDirectiveError("activity directives: overrides.overrides måste vara objekt")

    applied = 0
    skipped = 0
    seen: set[str] = set()
    for index, directive in enumerate(directives):
        context = f"activity directives[{index}]"
        if not isinstance(directive, dict):
            raise ActivityDirectiveError(f"{context}: objekt krävs")
        activity_id = str(directive.get("activity_id") or "").strip()
        if not activity_id:
            raise ActivityDirectiveError(f"{context}: activity_id saknas")
        if activity_id in seen:
            raise ActivityDirectiveError(f"{context}: dubbelt activity_id {activity_id}")
        seen.add(activity_id)

        set_values = directive.get("set") or {}
        remove_fields = directive.get("remove_fields") or []
        if not isinstance(set_values, dict):
            raise ActivityDirectiveError(f"{context}: set måste vara objekt")
        if not isinstance(remove_fields, list) or not all(
            isinstance(field, str) and field for field in remove_fields
        ):
            raise ActivityDirectiveError(f"{context}: remove_fields måste vara stränglista")

        # Current activity snapshots age out by design. A historical directive
        # must not brick future scheduled runs once its activity is no longer current.
        if activity_id not in activity_ids:
            skipped += 1
            continue

        current = deepcopy(mapping.get(activity_id) or {})
        for field in remove_fields:
            current.pop(field, None)
        current.update(deepcopy(set_values))
        previous = mapping.get(activity_id) or {}
        mapping[activity_id] = current
        if changed_ids is not None and previous != current:
            changed_ids.add(activity_id)
        applied += 1

    return applied, skipped


def invalidate_coach_analyses(path: Path, changed_ids: set[str]) -> int:
    if not changed_ids or not path.exists():
        return 0
    coach = load_json(path, {"analyses": []})
    analyses = coach.get("analyses") or []
    kept = [
        entry
        for entry in analyses
        if str(entry.get("activity_id") or "") not in changed_ids
    ]
    removed = len(analyses) - len(kept)
    if removed:
        coach["analyses"] = kept
        coach["last_trigger_hash"] = None
        path.write_text(
            json.dumps(coach, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return removed


def main() -> int:
    if not DIRECTIVES_FILE.exists():
        print("ACTIVITY_DIRECTIVES_OK no-sidecar")
        return 0

    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    overrides = load_json(
        OVERRIDES_FILE,
        {"schema_version": 1, "overrides": {}},
    )
    config = load_json(DIRECTIVES_FILE)
    changed_ids: set[str] = set()
    applied, skipped = apply_directives(activities, overrides, config, changed_ids)
    OVERRIDES_FILE.write_text(
        json.dumps(overrides, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    invalidated = invalidate_coach_analyses(COACH_FILE, changed_ids)
    print(
        f"ACTIVITY_DIRECTIVES_OK applied={applied} skipped_missing={skipped} "
        f"changed={len(changed_ids)} coach_invalidated={invalidated}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
