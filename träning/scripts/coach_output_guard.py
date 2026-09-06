#!/usr/bin/env python3
"""Post-AI invariants for public workout coaching text.

The model may interpret verified evidence, but these guards prevent recurrent
classes of unsupported claims from being published.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from workout_plan_context import build_plan_comparison


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
LOAD_MAGNITUDE_PATTERN = re.compile(
    r"\b(?:betydande|stor(?:t|a)?|påtaglig(?:t|a)?|avsevärd(?:t|a)?)\s+"
    r"(?=[^.,;]{0,48}\b(?:belastning|exponering)\b)",
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
UNVERIFIED_HR_PATTERN = re.compile(
    r"\b(?:stabil|jämn)\s+puls\b|"
    r"\bpuls(?:en)?\s+(?:var|är|hölls|förblev)\s+(?:stabil|jämn)\b|"
    r"\b(?:ingen|låg|liten)\s+pulsdrift\b",
    re.IGNORECASE,
)
ABSORPTION_PATTERN = re.compile(
    r"\babsorber(?:bar(?:t)?|ad(?:e|t)?|as|ades|ats)\b",
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
    value = LOAD_MAGNITUDE_PATTERN.sub("", value)
    return re.sub(r"[ \t]{2,}", " ", value).strip()


def _neutralize_unverified_hr_characterization(text):
    value = str(text or "")
    value = re.sub(
        r"\s+med\s+(?:stabil|jämn)\s+puls\s+och\s+",
        " med ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\s+med\s+(?:stabil|jämn)\s+puls\b",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\bpuls(?:en)?\s+(?:var|är|hölls|förblev)\s+(?:stabil|jämn)\b",
        "pulsstabilitet är inte deterministiskt verifierad",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\b(?:ingen|låg|liten)\s+pulsdrift\b",
        "pulsdrift är inte deterministiskt verifierad",
        value,
        flags=re.IGNORECASE,
    )
    return re.sub(r"[ \t]{2,}", " ", value).strip()


def _neutralize_same_day_absorption(text, *, latest_date, local_date):
    value = str(text or "")
    if latest_date != local_date or not ABSORPTION_PATTERN.search(value):
        return value

    # Preserve a supported observation that follows the unsupported absorption
    # claim, e.g. "visar att dagens dos var absorberbar och att sen fartökning...".
    value = re.sub(
        r"dagens\s+(?:dos|belastning)\s+(?:var|är)\s+absorberbar(?:t)?\s+och\s+att\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"(?:passet|belastningen|dosen)\s+(?:var|är|bedöms\s+som)\s+"
        r"absorber(?:bar(?:t)?|ad(?:e|t)?|as|ades|ats)",
        "full återhämtning från passet är ännu inte verifierad",
        value,
        flags=re.IGNORECASE,
    )
    if ABSORPTION_PATTERN.search(value):
        return "Full återhämtning från dagens pass är ännu inte verifierad."
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


def _sanitize_assessment_text(text, *, latest_date, local_date):
    value = _neutralize_near_load_level(text)
    value = _neutralize_unverified_hr_characterization(value)
    value = _neutralize_same_day_absorption(
        value,
        latest_date=latest_date,
        local_date=local_date,
    )
    if latest_date == local_date and _has_future_certainty(value):
        return _neutral_future_sentence()
    return value


def guard_result(result, *, latest_date, local_date, plan_comparison=None):
    guarded = copy.deepcopy(result)
    assessment = guarded.get("assessment") or {}

    for field in ("summary", "load_interpretation"):
        if isinstance(assessment.get(field), str):
            assessment[field] = _sanitize_assessment_text(
                assessment[field],
                latest_date=latest_date,
                local_date=local_date,
            )

    for field in ("interpretations", "unknowns"):
        values = assessment.get(field)
        if not isinstance(values, list):
            continue
        assessment[field] = [
            _sanitize_assessment_text(
                item,
                latest_date=latest_date,
                local_date=local_date,
            )
            if isinstance(item, str)
            else item
            for item in values
        ]

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
        actual = plan_comparison.get("actual_duration_minutes")
        actual_token = str(int(round(actual))) if isinstance(actual, (int, float)) else ""
        if not actual_token or actual_token not in combined or "tidsdos" not in combined.lower():
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
    if any(LOAD_MAGNITUDE_PATTERN.search(text) for text in texts):
        raise RuntimeError("Coach output guard: unsupported load magnitude claim remained")
    if any(UNVERIFIED_HR_PATTERN.search(text) for text in texts):
        raise RuntimeError("Coach output guard: unsupported heart-rate stability claim remained")
    if latest_date == local_date and any(ABSORPTION_PATTERN.search(text) for text in texts):
        raise RuntimeError("Coach output guard: unsupported same-day absorption claim remained")
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
    if not COACH_FILE.exists() or not ACTIVITIES_FILE.exists() or not PLAN_FILE.exists():
        return 0
    coach = _load(COACH_FILE)
    analyses = coach.get("analyses") or []
    if not analyses:
        return 0
    activities = _load(ACTIVITIES_FILE).get("activities") or []
    plan = _load(PLAN_FILE)
    entry = analyses[0]
    activity = next(
        (row for row in activities if str(row.get("id")) == str(entry.get("activity_id"))),
        None,
    )
    if not activity:
        raise RuntimeError("Coach output guard: latest analysis activity not found")

    latest_date = entry.get("activity_date") or ""
    timezone_name = (plan.get("meta") or {}).get("timezone") or "Europe/Stockholm"
    local_date = datetime.now(ZoneInfo(timezone_name)).date().isoformat()
    plan_comparison = build_plan_comparison(plan, activity, latest_date)
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
