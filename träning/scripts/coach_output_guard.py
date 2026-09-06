#!/usr/bin/env python3
"""Post-AI invariants for public workout coaching text.

The model may interpret verified evidence, but these guards prevent recurrent
classes of unsupported claims from being published.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COACH_FILE = ROOT / "data" / "coach.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
PLAN_FILE = ROOT / "data" / "plan.json"

NEAR_LOAD_LEVEL_PATTERN = re.compile(
    r"\bnärbelastning(?:en)?(?:\s+de\s+senaste\s+dagarna)?\s+"
    r"(?:är|var|bedöms\s+som|ser\s+ut\s+att\s+vara)\s+"
    r"(?:ovanligt\s+|relativt\s+)?(?:hög(?:t)?|låg(?:t)?|måttlig(?:t)?)\b",
    re.IGNORECASE,
)
NEAR_LOAD_PREFIX_PATTERN = re.compile(
    r"\b(?:ovanligt\s+|relativt\s+)?(?:hög(?:t)?|låg(?:t)?|måttlig(?:t)?)\s+närbelastning(?:en)?\b",
    re.IGNORECASE,
)
FUTURE_WINDOW_PATTERN = re.compile(
    r"\b(?:nästa|kommande)\s+(?:24|48|72)(?:\s*[–-]\s*(?:24|48|72))?\s*(?:h|timmar)\b",
    re.IGNORECASE,
)
FUTURE_CERTAINTY_PATTERN = re.compile(
    r"\b(?:inga?|inte|utan|problemfri(?:tt)?|återhämtad|"
    r"kräver?\s+(?:ingen|inte)|behöver?\s+(?:ingen|inte))\b",
    re.IGNORECASE,
)
REPORT_CLOCK_WINDOW_PATTERN = re.compile(
    r"\brapportera\b[^.]{0,100}?\b(?:[01]?\d|2[0-3])(?::[0-5]\d)?\s*[–-]\s*"
    r"(?:[01]?\d|2[0-3])(?::[0-5]\d)?\b",
    re.IGNORECASE,
)
PLAN_MATCH_PATTERN = re.compile(
    r"\b(?:genomför(?:t|des)\s+enligt\s+plan(?:en)?|"
    r"ligger\s+i\s+linje\s+med\s+(?:mikrocykelns\s+)?plan(?:en)?)\b",
    re.IGNORECASE,
)


def _outside_planned_duration(comparison):
    return (comparison or {}).get("duration_relation_to_approved_options") in {
        "above_approved_duration_range",
        "below_approved_duration_range",
    }


def _plan_deviation_text(comparison):
    actual = comparison.get("actual_duration_minutes")
    selected = comparison.get("selected_duration_minutes")
    high = comparison.get("approved_duration_max_minutes")
    low = comparison.get("approved_duration_min_minutes")
    relation = comparison.get("duration_relation_to_approved_options")
    if not isinstance(actual, (int, float)) or not isinstance(selected, (int, float)):
        return "Passet avvek från den planerade tidsdosen."
    if relation == "above_approved_duration_range" and isinstance(high, (int, float)):
        return (
            f"Tidsdosen blev {actual:g} min mot valda {selected:g} min och översteg "
            f"även det längsta godkända alternativet {high:g} min."
        )
    if relation == "below_approved_duration_range" and isinstance(low, (int, float)):
        return (
            f"Tidsdosen blev {actual:g} min mot valda {selected:g} min och understeg "
            f"det kortaste godkända alternativet {low:g} min."
        )
    return f"Tidsdosen blev {actual:g} min mot planerade {selected:g} min."


def _neutralize_near_load_level(text):
    value = str(text or "")
    value = NEAR_LOAD_LEVEL_PATTERN.sub(
        "närbelastningen kan inte nivåklassas mot personlig baslinje",
        value,
    )
    value = NEAR_LOAD_PREFIX_PATTERN.sub("närbelastningen", value)
    return re.sub(r"[ \t]{2,}", " ", value).strip()


def _has_future_certainty(text):
    value = str(text or "")
    return bool(FUTURE_WINDOW_PATTERN.search(value) and FUTURE_CERTAINTY_PATTERN.search(value))


def _neutral_future_sentence():
    return "Återhämtningen till nästa pass är ännu inte verifierad av samma-dagsdata."


def _sanitize_reporting_window(text):
    value = str(text or "")
    if not REPORT_CLOCK_WINDOW_PATTERN.search(value):
        return value
    # Exact feedback windows are not training facts. Keep the useful checkpoint,
    # remove the invented clock time.
    value = re.sub(
        r"rapportera\s+(?:dagens\s+)?benkänsla\s+(?:morgon(?:en)?\s*)?"
        r"(?:[01]?\d|2[0-3])(?::[0-5]\d)?\s*[–-]\s*"
        r"(?:[01]?\d|2[0-3])(?::[0-5]\d)?",
        "rapportera benkänslan nästa morgon",
        value,
        flags=re.IGNORECASE,
    )
    if REPORT_CLOCK_WINDOW_PATTERN.search(value):
        return "Följ befintlig plan; rapportera avvikande känsla innan nästa belastande pass."
    return value


def guard_result(result, *, latest_date, local_date, plan_comparison=None):
    guarded = copy.deepcopy(result)
    assessment = guarded.get("assessment") or {}

    for field in ("summary", "load_interpretation"):
        if isinstance(assessment.get(field), str):
            assessment[field] = _neutralize_near_load_level(assessment[field])
            if latest_date == local_date and _has_future_certainty(assessment[field]):
                assessment[field] = _neutral_future_sentence()

    for field in ("interpretations", "unknowns"):
        values = assessment.get(field)
        if not isinstance(values, list):
            continue
        sanitized = []
        for item in values:
            if not isinstance(item, str):
                sanitized.append(item)
                continue
            item = _neutralize_near_load_level(item)
            if latest_date == local_date and _has_future_certainty(item):
                item = _neutral_future_sentence()
            sanitized.append(item)
        assessment[field] = sanitized

    action = guarded.get("plan_action") or {}
    for field in ("reason", "recommendation"):
        if isinstance(action.get(field), str):
            action[field] = _neutralize_near_load_level(action[field])
    if isinstance(action.get("recommendation"), str):
        action["recommendation"] = _sanitize_reporting_window(action["recommendation"])

    if _outside_planned_duration(plan_comparison):
        deviation = _plan_deviation_text(plan_comparison)
        for field in ("summary", "load_interpretation"):
            value = assessment.get(field)
            if isinstance(value, str) and PLAN_MATCH_PATTERN.search(value):
                assessment[field] = PLAN_MATCH_PATTERN.sub("avvek från planerad tidsdos", value)
        values = assessment.get("interpretations") or []
        assessment["interpretations"] = [
            PLAN_MATCH_PATTERN.sub("avvek från planerad tidsdos", value)
            if isinstance(value, str)
            else value
            for value in values
        ]
        reason = action.get("reason")
        if isinstance(reason, str) and PLAN_MATCH_PATTERN.search(reason):
            action["reason"] = deviation

        combined = " ".join(
            [str(assessment.get("summary") or "")]
            + [str(value) for value in assessment.get("interpretations") or []]
        )
        if str(int(round(plan_comparison.get("actual_duration_minutes", 0)))) not in combined or "tidsdos" not in combined.lower():
            interpretations = list(assessment.get("interpretations") or [])
            if interpretations and interpretations[-1] == _neutral_future_sentence():
                interpretations[-1] = deviation
            elif len(interpretations) < 2:
                interpretations.append(deviation)
            else:
                interpretations[-1] = deviation
            assessment["interpretations"] = interpretations

    guarded["assessment"] = assessment
    guarded["plan_action"] = action
    validate_guarded_result(
        guarded,
        latest_date=latest_date,
        local_date=local_date,
        plan_comparison=plan_comparison,
    )
    return guarded


def validate_guarded_result(result, *, latest_date, local_date, plan_comparison=None):
    assessment = result.get("assessment") or {}
    action = result.get("plan_action") or {}
    derived = [
        assessment.get("summary"),
        assessment.get("load_interpretation"),
        *(assessment.get("interpretations") or []),
        *(assessment.get("unknowns") or []),
        action.get("reason"),
        action.get("recommendation"),
    ]
    texts = [str(value or "") for value in derived]

    if any(NEAR_LOAD_LEVEL_PATTERN.search(text) or NEAR_LOAD_PREFIX_PATTERN.search(text) for text in texts):
        raise RuntimeError("Coach output guard: unsupported relative near-load label remained")
    if latest_date == local_date and any(_has_future_certainty(text) for text in texts):
        raise RuntimeError("Coach output guard: unsupported future recovery certainty remained")
    if any(REPORT_CLOCK_WINDOW_PATTERN.search(text) for text in texts):
        raise RuntimeError("Coach output guard: invented feedback clock window remained")
    if _outside_planned_duration(plan_comparison) and any(PLAN_MATCH_PATTERN.search(text) for text in texts):
        raise RuntimeError("Coach output guard: plan-match claim conflicts with deterministic duration comparison")
    return True


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    # CLI guard for workflow use. The richer coach pipeline normally calls the
    # same pure function before writing, while this remains a final safety net.
    if not COACH_FILE.exists() or not ACTIVITIES_FILE.exists():
        return 0
    coach = _load(COACH_FILE)
    analyses = coach.get("analyses") or []
    if not analyses:
        return 0
    activities = _load(ACTIVITIES_FILE).get("activities") or []
    entry = analyses[0]
    activity = next(
        (row for row in activities if str(row.get("id")) == str(entry.get("activity_id"))),
        None,
    )
    if not activity:
        raise RuntimeError("Coach output guard: latest analysis activity not found")

    latest_date = entry.get("activity_date") or ""
    local_date = datetime.now().date().isoformat()
    plan_comparison = ((activity.get("workout_analysis_context") or {}).get("plan_comparison"))
    guarded = guard_result(
        {"assessment": entry.get("assessment") or {}, "plan_action": entry.get("plan_action") or {}},
        latest_date=latest_date,
        local_date=local_date,
        plan_comparison=plan_comparison,
    )
    entry["assessment"] = guarded["assessment"]
    entry["plan_action"] = guarded["plan_action"]
    COACH_FILE.write_text(json.dumps(coach, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Coach output guard: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
