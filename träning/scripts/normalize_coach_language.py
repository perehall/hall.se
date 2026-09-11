#!/usr/bin/env python3
import json
import re
from pathlib import Path

from finalize_activity_labels import PUBLIC_ACTIVITY_LABELS

ROOT = Path(__file__).resolve().parents[1]
COACH_FILE = ROOT / "data" / "coach.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
PLAN_FILE = ROOT / "data" / "plan.json"
STRATEGY_FILE = ROOT / "data" / "training_strategy.json"

FORBIDDEN_VISIBLE_TERMS = (
    (re.compile(r"\blapparna\b", re.IGNORECASE), "intervallerna"),
    (re.compile(r"\blappar\b", re.IGNORECASE), "intervaller"),
    (re.compile(r"\blaps\b", re.IGNORECASE), "intervaller"),
    (re.compile(r"\boption\b", re.IGNORECASE), "alternativ"),
)

# Provider/schema field names that may legitimately exist in the internal fact
# model but must never be exposed verbatim in Swedish coaching copy.
INTERNAL_FIELD_LABELS = {
    "session_duration_s": "total passduration",
    "session_duration": "total passduration",
    "moving_time_s": "rörelsetid",
    "moving_time": "rörelsetid",
    "non_moving_time_s": "tid utan registrerad rörelse",
    "non_moving_time": "tid utan registrerad rörelse",
    "elapsed_time_s": "total tid",
    "elapsed_time": "total tid",
    "duration_basis": "tidsgrund",
    "duration_note": "tidsnotering",
    "user_report": "användarrapport",
    "dose_resolution": "valt dosalternativ",
    "dose_option_id": "dosalternativ",
    "auto_coach": "coachen",
    "plan_comparison": "jämförelsen med planen",
    "rolling_load_context": "närbelastningen",
    "rolling_load": "närbelastningen",
    "performance_context": "passjämförelsen",
    "current_strategy": "träningsstrategin",
    "private_wellness_context": "återhämtningsunderlaget",
    "source_laps_near_1km": "kilometervarv",
    "average_pace_s_per_km": "snittfart",
    "average_pace": "snittfart",
}

SYSTEM_LANGUAGE_RULES = (
    (
        re.compile(r"\bnear_term(?:_[a-z0-9]+)*\b", re.IGNORECASE),
        "närtidsplaneringen",
    ),
    (
        re.compile(
            r"Passet\s+räknas\s+som\s+faktisk\s+träningsbelastning\s+mot\s+"
            r"mikrocykelns\s+stimuli\s+för\s+Enduroteknik\s+och\s+påverkar\s+"
            r"möjligheten\s+att\s+genomföra\s+(?P<target>[^.]+?)\s+prioriterade\s+löpstimulus\.",
            re.IGNORECASE,
        ),
        r"Enduropasset är en del av veckans träningsbelastning. Därför vägs det in när \g<target> löppass planeras.",
    ),
    (
        re.compile(r"\bmikrocykelns\s+stimuli\s+för\s+Enduroteknik\b", re.IGNORECASE),
        "den endurotekniska träningen i veckan",
    ),
    (
        re.compile(r"\bprioriterade\s+löpstimulus\b", re.IGNORECASE),
        "prioriterade löppass",
    ),
    (
        re.compile(r"\benligt\s+baseline\b", re.IGNORECASE),
        "enligt planerad grunddos",
    ),
)

INTERNAL_IDENTIFIER_PATTERN = re.compile(
    r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b",
    re.IGNORECASE,
)

STRUCTURE_RE = re.compile(
    r"(?P<sets>\d+)\s*[×xX]\s*(?P<reps>\d+)\s*(?P<kind>backintervaller|backar|intervaller)\b",
    re.IGNORECASE,
)
CONFLICTING_HILL_STRUCTURE_RE = re.compile(
    r"\d+\s*[×xX]\s*\d+(?:\s*[×xX]\s*\d+)?(?:\s*m)?",
    re.IGNORECASE,
)
PAREN_WITH_STRUCTURE_RE = re.compile(
    r"\s*\([^)]*\d+\s*[×xX]\s*\d+[^)]*\)",
    re.IGNORECASE,
)
TOTAL_HILLS_RE = re.compile(r"\b\d+\s+backar\b", re.IGNORECASE)


def load(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def strategy_visible_labels(strategy):
    """Collect canonical public labels for strategy keys and named internal IDs."""
    labels = dict(INTERNAL_FIELD_LABELS)

    def visit(value):
        if isinstance(value, dict):
            key = value.get("key")
            label = value.get("label")
            if isinstance(key, str) and key.strip() and isinstance(label, str) and label.strip():
                labels[key.strip()] = label.strip()

            identifier = value.get("id")
            public_name = value.get("session") or value.get("title") or value.get("label")
            if (
                isinstance(identifier, str)
                and identifier.strip()
                and isinstance(public_name, str)
                and public_name.strip()
            ):
                labels[identifier.strip()] = public_name.strip()

            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(strategy or {})
    return labels


def _replace_internal_identifier(text, labels):
    if not labels:
        return text
    value = text
    for key, label in sorted(labels.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_-]){re.escape(key)}(?![A-Za-z0-9_-])",
            re.IGNORECASE,
        )
        value = pattern.sub(label, value)
    return value


def _replace_provider_activity_fact_labels(text):
    value = text
    for raw_label, public_label in sorted(
        PUBLIC_ACTIVITY_LABELS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        value = re.sub(
            rf"\b{re.escape(raw_label)}(?=\s*:)",
            public_label,
            value,
            flags=re.IGNORECASE,
        )
    return value


def visible_training_language(text, strategy_labels=None):
    value = str(text or "")
    for pattern, replacement in FORBIDDEN_VISIBLE_TERMS:
        value = pattern.sub(replacement, value)
    labels = strategy_labels or dict(INTERNAL_FIELD_LABELS)
    value = _replace_internal_identifier(value, labels)
    value = _replace_provider_activity_fact_labels(value)
    for pattern, replacement in SYSTEM_LANGUAGE_RULES:
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
    label = "backintervaller" if kind.startswith("back") else "intervaller"
    return {
        "sets": sets,
        "reps": reps,
        "total": sets * reps,
        "label": label,
        "text": f"{sets} × {reps} {label}",
    }


def canonical_actual_summary(text, structure, strategy_labels=None):
    value = visible_training_language(text, strategy_labels)
    if not structure or not value:
        return value
    if not re.search(r"\bback|intervall", value, re.IGNORECASE):
        return value

    # The actual outcome is authoritative. Planned/reduced structures belong in
    # the separate "Plan före passet" field and must never leak into this sentence.
    tail = ""
    if ";" in value:
        tail = value.split(";", 1)[1].strip()
    else:
        stripped = PAREN_WITH_STRUCTURE_RE.sub("", value)
        stripped = CONFLICTING_HILL_STRUCTURE_RE.sub("", stripped)
        stripped = TOTAL_HILLS_RE.sub("", stripped)
        stripped = re.sub(r"\bbackintervaller\s+backar\b", "backintervaller", stripped, flags=re.IGNORECASE)
        parts = re.split(r"(?<=[.!?])\s+", stripped, maxsplit=1)
        if len(parts) > 1:
            tail = parts[1].strip()

    tail = PAREN_WITH_STRUCTURE_RE.sub("", tail)
    tail = CONFLICTING_HILL_STRUCTURE_RE.sub("", tail)
    tail = TOTAL_HILLS_RE.sub("", tail)
    tail = re.sub(r"\bbackintervaller\s+backar\b", "backintervaller", tail, flags=re.IGNORECASE)
    tail = re.sub(r"\s{2,}", " ", tail).strip(" .;,-")

    prefix = f"Genomfört: {structure['text']} ({structure['total']} totalt)."
    if not tail:
        return prefix
    return f"{prefix} {tail[0].upper() + tail[1:]}"


def normalize_text_list(assessment, field, strategy_labels=None):
    values = assessment.get(field)
    if not isinstance(values, list):
        return False
    normalized_values = [
        visible_training_language(item, strategy_labels) if isinstance(item, str) else item
        for item in values
    ]
    if normalized_values == values:
        return False
    assessment[field] = normalized_values
    return True


def planned_structured_value(plan_day):
    resolution = (plan_day or {}).get("dose_resolution") or {}
    value = resolution.get("value")
    if resolution.get("kind") == "structured" and isinstance(value, (int, float)):
        return value
    return None


def normalize_action_reason(action, structure, plan_day, strategy_labels=None):
    reason = action.get("reason")
    if not isinstance(reason, str):
        return False
    normalized = visible_training_language(reason, strategy_labels)
    planned_value = planned_structured_value(plan_day)
    if structure and planned_value is not None and structure["total"] != planned_value:
        tail = normalized.split(";", 1)[1].strip() if ";" in normalized else ""
        relation = "över" if structure["total"] > planned_value else "under"
        prefix = (
            f"Backpasset genomfördes som {structure['text']} ({structure['total']} totalt), "
            f"alltså {relation} den planerade omfattningen före passet ({int(planned_value)} arbetsintervaller)."
        )
        normalized = f"{prefix} {tail[0].upper() + tail[1:]}" if tail else prefix
    if normalized == reason:
        return False
    action["reason"] = normalized
    return True


def normalize_analysis(entry, activity, plan_day=None, strategy_labels=None):
    changed = False
    structure = explicit_interval_structure((activity or {}).get("user_report"))
    assessment = entry.get("assessment") or {}

    summary = assessment.get("summary")
    if isinstance(summary, str):
        normalized = canonical_actual_summary(summary, structure, strategy_labels)
        if normalized != summary:
            assessment["summary"] = normalized
            changed = True

    value = assessment.get("load_interpretation")
    if isinstance(value, str):
        normalized = visible_training_language(value, strategy_labels)
        if normalized != value:
            assessment["load_interpretation"] = normalized
            changed = True

    for field in ("facts", "interpretations", "unknowns"):
        if normalize_text_list(assessment, field, strategy_labels):
            changed = True

    action = entry.get("plan_action") or {}
    if normalize_action_reason(action, structure, plan_day, strategy_labels):
        changed = True
    recommendation = action.get("recommendation")
    if isinstance(recommendation, str):
        normalized = visible_training_language(recommendation, strategy_labels)
        if normalized != recommendation:
            action["recommendation"] = normalized
            changed = True

    return changed


def normalize_state(coach, activities_state, plan_state=None, strategy=None):
    labels = strategy_visible_labels(strategy or {})
    by_id = {
        str(activity.get("id")): activity
        for activity in (activities_state.get("activities") or [])
        if activity.get("id") is not None
    }
    plan_by_date = {
        str(day.get("date")): day
        for day in ((plan_state or {}).get("days") or [])
        if day.get("date")
    }
    changed = 0
    for entry in coach.get("analyses") or []:
        activity = by_id.get(str(entry.get("activity_id")))
        plan_day = plan_by_date.get(str(entry.get("activity_date")))
        if normalize_analysis(
            entry,
            activity,
            plan_day=plan_day,
            strategy_labels=labels,
        ):
            changed += 1
    return changed


def visible_analysis_texts(entry):
    assessment = entry.get("assessment") or {}
    action = entry.get("plan_action") or {}
    values = []
    for field in ("summary", "load_interpretation"):
        value = assessment.get(field)
        if isinstance(value, str):
            values.append(value)
    for field in ("facts", "interpretations", "unknowns"):
        for value in assessment.get(field) or []:
            if isinstance(value, str):
                values.append(value)
    for field in ("reason", "recommendation"):
        value = action.get(field)
        if isinstance(value, str):
            values.append(value)
    return values


def assert_no_forbidden_visible_terms(coach):
    raw = "\n".join(
        text
        for entry in (coach.get("analyses") or [])
        for text in visible_analysis_texts(entry)
    )
    forbidden = re.search(r"\blappar(?:na)?\b|\blaps\b", raw, re.IGNORECASE)
    if forbidden:
        raise RuntimeError(
            f"Coachspråk: förbjuden plattformsterm kvar i synlig analys: {forbidden.group(0)!r}"
        )
    for raw_label in PUBLIC_ACTIVITY_LABELS:
        provider_fact = re.search(rf"\b{re.escape(raw_label)}\s*:", raw, re.IGNORECASE)
        if provider_fact:
            raise RuntimeError(
                f"Coachspråk: rå aktivitetstyp kvar i synlig analys: {raw_label!r}"
            )
    internal = INTERNAL_IDENTIFIER_PATTERN.search(raw)
    if internal:
        raise RuntimeError(
            f"Coachspråk: internt variabelnamn kvar i synlig analys: {internal.group(0)!r}"
        )


def main():
    coach = load(COACH_FILE, {"analyses": []})
    activities = load(ACTIVITIES_FILE, {"activities": []})
    plan = load(PLAN_FILE, {"days": []})
    strategy = load(STRATEGY_FILE, {})
    changed = normalize_state(coach, activities, plan, strategy)
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
