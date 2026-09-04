#!/usr/bin/env python3
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COACH_FILE = ROOT / "data" / "coach.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"

FORBIDDEN_VISIBLE_TERMS = (
    (re.compile(r"\blapparna\b", re.IGNORECASE), "intervallerna"),
    (re.compile(r"\blappar\b", re.IGNORECASE), "intervaller"),
    (re.compile(r"\blaps\b", re.IGNORECASE), "intervaller"),
)

STRUCTURE_RE = re.compile(
    r"(?P<sets>\d+)\s*[×xX]\s*(?P<reps>\d+)\s*(?P<kind>backintervaller|backar|intervaller)\b",
    re.IGNORECASE,
)
CONFLICTING_HILL_STRUCTURE_RE = re.compile(
    r"\d+\s*[×xX]\s*\d+(?:\s*[×xX]\s*\d+)?(?:\s*m)?",
    re.IGNORECASE,
)
TOTAL_HILLS_RE = re.compile(r"\b\d+\s+backar\b", re.IGNORECASE)


def load(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def visible_training_language(text):
    value = str(text or "")
    for pattern, replacement in FORBIDDEN_VISIBLE_TERMS:
        value = pattern.sub(replacement, value)
    return value


def explicit_interval_structure(user_report):
    report = str(user_report or "").strip()
    match = STRUCTURE_RE.search(report)
    if not match:
        return None
    sets = int(match.group("sets"))
    reps = int(match.group("reps"))
    kind = match.group("kind").lower()
    if kind.startswith("back"):
        label = "backintervaller"
    else:
        label = "intervaller"
    return {
        "sets": sets,
        "reps": reps,
        "total": sets * reps,
        "label": label,
        "text": f"{sets} × {reps} {label}",
    }


def enforce_reported_structure(text, structure):
    value = visible_training_language(text)
    if not structure or not value:
        return value
    if not re.search(r"\bback|intervall", value, re.IGNORECASE):
        return value

    normalized = structure["text"]
    if CONFLICTING_HILL_STRUCTURE_RE.search(value):
        return CONFLICTING_HILL_STRUCTURE_RE.sub(normalized, value, count=1)
    if TOTAL_HILLS_RE.search(value):
        return TOTAL_HILLS_RE.sub(normalized, value, count=1)
    return value


def normalize_analysis(entry, activity):
    changed = False
    structure = explicit_interval_structure((activity or {}).get("user_report"))
    assessment = entry.get("assessment") or {}

    summary = assessment.get("summary")
    if isinstance(summary, str):
        normalized = enforce_reported_structure(summary, structure)
        if normalized != summary:
            assessment["summary"] = normalized
            changed = True

    for field in ("load_interpretation",):
        value = assessment.get(field)
        if isinstance(value, str):
            normalized = visible_training_language(value)
            if normalized != value:
                assessment[field] = normalized
                changed = True

    for field in ("interpretations", "unknowns"):
        values = assessment.get(field)
        if not isinstance(values, list):
            continue
        normalized_values = [
            visible_training_language(item) if isinstance(item, str) else item
            for item in values
        ]
        if normalized_values != values:
            assessment[field] = normalized_values
            changed = True

    action = entry.get("plan_action") or {}
    for field in ("reason", "recommendation"):
        value = action.get(field)
        if isinstance(value, str):
            normalized = visible_training_language(value)
            if normalized != value:
                action[field] = normalized
                changed = True

    return changed


def normalize_state(coach, activities_state):
    by_id = {
        str(activity.get("id")): activity
        for activity in (activities_state.get("activities") or [])
        if activity.get("id") is not None
    }
    changed = 0
    for entry in coach.get("analyses") or []:
        activity = by_id.get(str(entry.get("activity_id")))
        if normalize_analysis(entry, activity):
            changed += 1
    return changed


def assert_no_forbidden_visible_terms(coach):
    raw = json.dumps(coach.get("analyses") or [], ensure_ascii=False)
    forbidden = re.search(r"\blappar(?:na)?\b|\blaps\b", raw, re.IGNORECASE)
    if forbidden:
        raise RuntimeError(
            f"Coachspråk: förbjuden plattformsterm kvar i synlig analys: {forbidden.group(0)!r}"
        )


def main():
    coach = load(COACH_FILE, {"analyses": []})
    activities = load(ACTIVITIES_FILE, {"activities": []})
    changed = normalize_state(coach, activities)
    assert_no_forbidden_visible_terms(coach)
    if changed:
        COACH_FILE.write_text(
            json.dumps(coach, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Coachspråk OK: {changed} analys(er) humaniserade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
