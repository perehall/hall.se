#!/usr/bin/env python3
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "data" / "plan.json"
ACTIVITIES_FILE = ROOT / "data" / "activities.json"
COACH_FILE = ROOT / "data" / "coach.json"

SPORT_WORDS = {
    "Swim": ("simning", "sim", "swim"),
    "Run": ("löpning", "löp", "run"),
    "TrailRun": ("löpning", "löp", "trail"),
    "VirtualRun": ("löpning", "löp", "run"),
    "MountainBikeRide": ("mtb", "cykel"),
    "Ride": ("cykel",),
    "VirtualRide": ("cykel",),
    "WeightTraining": ("styrka", "core"),
    "Enduro": ("enduro",),
}

# Canonical strategy/stimulus identifiers are valid machine data but must never
# leak into visible coaching copy. Keep a deterministic safety mapping here as
# a guard before the broader language normalizer runs. The sim_* aliases cover
# the hybrid Swedish/English identifiers the model has actually emitted.
VISIBLE_INTERNAL_TERMS = {
    "run_threshold": "kontrollerad löptröskel",
    "run_hill_quality": "backstyrka/löpekonomi",
    "run_easy_distance": "lugn löpdistans",
    "mtb_technical": "MTB-teknik",
    "mtb_aerobic": "aerob MTB/XC",
    "strength_unilateral": "unilateral benstyrka",
    "strength_core": "core",
    "swim_aerobic": "aerob simning",
    "swim_technique": "simteknik",
    "sim_aerobic": "aerob simning",
    "sim_technique": "simteknik",
    "enduro_technical": "enduroteknik",
    "swim_support": "stödjande simpass",
    "mtb_support": "stödjande MTB-pass",
}


def load_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def replace_visible_internal_terms(value):
    text = str(value or "")
    for raw, public in sorted(VISIBLE_INTERNAL_TERMS.items(), key=lambda item: len(item[0]), reverse=True):
        text = re.sub(
            rf"(?<![A-Za-z0-9_-]){re.escape(raw)}(?![A-Za-z0-9_-])",
            public,
            text,
            flags=re.IGNORECASE,
        )
    return text


def all_dose_option_ids(plan):
    return {
        str(option.get("id") or "").strip()
        for day in plan.get("days", [])
        for option in (day.get("dose_options") or [])
        if str(option.get("id") or "").strip()
    }


def replace_visible_dose_terms(value, plan):
    """Remove machine-only dose identifiers from public prose, never machine fields."""
    text = str(value or "")
    text = re.sub(r"\bdose_option_id\b", "passalternativ", text, flags=re.IGNORECASE)
    for option_id in sorted(all_dose_option_ids(plan), key=len, reverse=True):
        text = text.replace(option_id, "det valda passalternativet")
    return text


def contains_internal_dose_terms(value, plan):
    text = str(value or "")
    if re.search(r"\bdose_option_id\b", text, flags=re.IGNORECASE):
        return True
    return any(option_id in text for option_id in all_dose_option_ids(plan))


def first_sentences(value, count=1, max_chars=None, plan=None):
    text = replace_visible_internal_terms(value).strip()
    if plan is not None:
        text = replace_visible_dose_terms(text, plan)
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    compact = " ".join(parts[:count]) if parts else text
    if max_chars and len(compact) > max_chars:
        clipped = compact[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
        compact = (clipped or compact[: max_chars - 1]).rstrip() + "…"
    return compact


def fmt_duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return ""
    seconds = int(round(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def fmt_distance_m(meters):
    if not isinstance(meters, (int, float)) or meters <= 0:
        return ""
    return f"{round(meters):,} m".replace(",", " ")


def latest_activity_for_analysis(analysis, activities):
    wanted = str(analysis.get("activity_id"))
    return next((a for a in activities if str(a.get("id")) == wanted), None)


def plan_day(plan, date_text):
    return next((d for d in plan.get("days", []) if d.get("date") == date_text), None)


def planned_swim_distance(day):
    if not day:
        return None
    text = " ".join(
        str(day.get(key) or "") for key in ("session", "original_session", "decision_note")
    )
    match = re.search(r"(?:simning[^+;]*?)(\d[\d\s]{2,})\s*m\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(re.sub(r"\s+", "", match.group(1)))
    except ValueError:
        return None


def has_user_report(activity):
    return bool(str((activity or {}).get("user_report") or "").strip())


def has_structured_swim_analysis(activity):
    context = (activity or {}).get("workout_analysis_context") or {}
    swim = context.get("swim") or {}
    return swim.get("structured") is True and bool(swim.get("repeat_sets"))


def compact_list(values, limit, max_chars, plan=None):
    result = []
    for item in values or []:
        text = first_sentences(item, 1, max_chars=max_chars, plan=plan)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def clean_fact_list(values, plan=None):
    result = []
    for item in values or []:
        if not isinstance(item, str):
            continue
        text = replace_visible_internal_terms(item).strip()
        if plan is not None:
            text = replace_visible_dose_terms(text, plan)
        if text and text not in result:
            result.append(text)
        if len(result) >= 4:
            break
    return result


def swim_without_structured_analysis(analysis, activity, day):
    assessment = analysis.setdefault("assessment", {})
    actual_m = activity.get("distance_m")
    duration = fmt_duration(activity.get("elapsed_time_s") or activity.get("moving_time_s"))
    planned_m = planned_swim_distance(day)

    if isinstance(actual_m, (int, float)) and actual_m > 0 and planned_m:
        delta = round(actual_m - planned_m)
        if delta == 0:
            summary = f"Simningen genomfördes enligt planerad distans: {fmt_distance_m(actual_m)}."
        else:
            direction = "mer" if delta > 0 else "mindre"
            summary = (
                f"Simningen blev {fmt_distance_m(actual_m)} mot planerade {fmt_distance_m(planned_m)} "
                f"({fmt_distance_m(abs(delta))} {direction})."
            )
    elif isinstance(actual_m, (int, float)) and actual_m > 0:
        summary = f"Simningen genomfördes: {fmt_distance_m(actual_m)}"
        if duration:
            summary += f" på {duration}"
        summary += "."
    else:
        summary = "Simpasset är genomfört."

    assessment["summary"] = summary
    assessment["load_interpretation"] = "Ingen setbaserad slutsats används för planändring."
    interpretations = []
    if isinstance(actual_m, (int, float)) and planned_m and actual_m != planned_m:
        interpretations.append(
            "Distansavvikelsen är verifierad; träningsmässig betydelse kräver säkrare setstruktur eller användarrapport."
        )
    assessment["interpretations"] = interpretations
    assessment["unknowns"] = ["Setstruktur kunde inte verifieras från passdata."]
    if not has_user_report(activity):
        assessment["confidence"] = "low"


def same_day_remaining_components(day, activity):
    if not day or not activity:
        return []
    session = str(day.get("session") or "").strip()
    if " + " not in session:
        return []
    words = SPORT_WORDS.get(activity.get("sport_type"), ())
    parts = [p.strip() for p in session.split(" + ") if p.strip()]
    remaining = [p for p in parts if not any(word in p.lower() for word in words)]
    return remaining if len(remaining) < len(parts) else []


def prevent_repeat_of_completed_component(analysis, activity, day):
    action = analysis.setdefault("plan_action", {})
    if action.get("target_date") != analysis.get("activity_date"):
        return
    remaining = same_day_remaining_components(day, activity)
    if remaining:
        done = {
            "Swim": "Simningen",
            "Run": "Löpningen",
            "TrailRun": "Löpningen",
            "VirtualRun": "Löpningen",
            "MountainBikeRide": "MTB-passet",
            "Ride": "Cykelpasset",
            "VirtualRide": "Cykelpasset",
            "WeightTraining": "Styrkan",
            "Enduro": "Enduron",
        }.get(activity.get("sport_type"), "Passdelen")
        action["recommendation"] = f"{done} är genomförd. Återstår enligt dagens plan: {' + '.join(remaining)}."
        action["reason"] = "Den genomförda passdelen ska inte ordineras en gång till."


def canonicalize_target_action_copy(analysis, plan):
    """Use structured plan state, not free model prose, for visible target-action advice."""
    action = analysis.setdefault("plan_action", {})
    kind = action.get("action")
    target = str(action.get("target_date") or "").strip()
    day = plan_day(plan, target) if target else None
    if not day:
        return

    if kind == "reduce":
        action["recommendation"] = "Följ det justerade passupplägget i planen."
    elif kind == "rest":
        action["recommendation"] = "Följ den justerade planen."
    elif kind == "keep" and contains_internal_dose_terms(action.get("recommendation"), plan):
        action["recommendation"] = "Behåll passupplägget i planen."

    if contains_internal_dose_terms(action.get("reason"), plan):
        action["reason"] = "Planbeslutet bygger på den strukturerade planinformationen."


def enforce_plan_copy_contract(plan):
    """Plan fields rendered to the page must be deterministic human copy."""
    changed = False
    for day in plan.get("days", []):
        current = str(day.get("coach_adjustment") or "").strip()
        if not current:
            continue
        action = str((day.get("auto_coach") or {}).get("action") or "").strip()
        original = str(day.get("original_session") or "").strip()
        session = str(day.get("session") or "").strip()

        if action == "reduce":
            if original and session and original != session:
                desired = "Passet är nedjusterat från grundplanen. Följ passupplägget ovan."
            else:
                desired = "Passet är nedjusterat. Följ passupplägget ovan."
        elif action == "rest":
            desired = "Planen är justerad till vila eller mycket lätt träning."
        elif contains_internal_dose_terms(current, plan):
            desired = "Planen är justerad. Följ passupplägget ovan."
        else:
            desired = first_sentences(current, 1, 180, plan=plan)

        if current != desired:
            day["coach_adjustment"] = desired
            changed = True
    return changed


def enforce_contract(coach, plan, activities_state):
    analyses = coach.get("analyses") or []
    activities = activities_state.get("activities") or []
    if not analyses:
        return False

    changed = False
    for analysis in analyses:
        activity = latest_activity_for_analysis(analysis, activities)
        if not activity:
            continue
        before = json.dumps(analysis, ensure_ascii=False, sort_keys=True)
        day = plan_day(plan, analysis.get("activity_date"))
        assessment = analysis.setdefault("assessment", {})

        assessment["summary"] = first_sentences(assessment.get("summary"), 1, 180, plan=plan)
        assessment["load_interpretation"] = first_sentences(
            assessment.get("load_interpretation"), 1, 170, plan=plan
        )
        assessment["facts"] = clean_fact_list(assessment.get("facts"), plan=plan)
        assessment["interpretations"] = compact_list(
            assessment.get("interpretations"), 2, 190, plan=plan
        )
        assessment["unknowns"] = compact_list(
            assessment.get("unknowns"), 2, 190, plan=plan
        )

        action = analysis.setdefault("plan_action", {})
        action["reason"] = first_sentences(action.get("reason"), 1, 180, plan=plan)
        action["recommendation"] = first_sentences(
            action.get("recommendation"), 2, 260, plan=plan
        )

        # A verified workout_analysis_context.swim is a structured, deterministic
        # set layer. Only fall back to evidence-limited totals when neither that
        # context nor the legacy performance marker is available.
        if (
            activity.get("sport_type") == "Swim"
            and not analysis.get("performance_marker_id")
            and not has_structured_swim_analysis(activity)
        ):
            swim_without_structured_analysis(analysis, activity, day)

        prevent_repeat_of_completed_component(analysis, activity, day)
        canonicalize_target_action_copy(analysis, plan)

        after = json.dumps(analysis, ensure_ascii=False, sort_keys=True)
        changed = changed or before != after

    return changed


def main():
    plan = load_json(PLAN_FILE, {})
    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    coach = load_json(COACH_FILE, {"analyses": []})
    coach_changed = enforce_contract(coach, plan, activities)
    plan_changed = enforce_plan_copy_contract(plan)
    version_changed = coach.get("output_contract_version") != 19

    if coach_changed or version_changed:
        coach["output_contract_version"] = 19
        COACH_FILE.write_text(
            json.dumps(coach, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if plan_changed:
        PLAN_FILE.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    if coach_changed or plan_changed or version_changed:
        print("Coach output contract v19: publik coachtext normaliserad och maskinidentifierare spärrade.")
    else:
        print("Coach output contract v19: inga korrigeringar behövdes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())