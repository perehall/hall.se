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


def load_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def first_sentences(value, count=1, max_chars=None):
    text = re.sub(r"\s+", " ", str(value or "").strip())
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


def compact_list(values, limit, max_chars):
    result = []
    for item in values or []:
        text = first_sentences(item, 1, max_chars=max_chars)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
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
    assessment["load_interpretation"] = (
        "Set-/intervallnivå saknas i det strukturerade analyslagret; teknik, fartstabilitet och intensitetsutveckling går därför inte att bedöma säkert."
    )
    interpretations = []
    if isinstance(actual_m, (int, float)) and planned_m and actual_m != planned_m:
        interpretations.append(
            "Distansavvikelsen är ett faktum; dess träningsmässiga betydelse kan inte avgöras utan setstruktur och subjektiv känsla."
        )
    assessment["interpretations"] = interpretations
    assessment["unknowns"] = ["Set-/intervallstruktur och subjektiv känsla efter simningen saknas."]
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

        assessment["summary"] = first_sentences(assessment.get("summary"), 1, 180)
        assessment["load_interpretation"] = first_sentences(
            assessment.get("load_interpretation"), 1, 170
        )
        assessment["interpretations"] = compact_list(
            assessment.get("interpretations"), 2, 190
        )
        assessment["unknowns"] = compact_list(assessment.get("unknowns"), 2, 190)

        action = analysis.setdefault("plan_action", {})
        action["reason"] = first_sentences(action.get("reason"), 1, 180)
        action["recommendation"] = first_sentences(
            action.get("recommendation"), 2, 260
        )

        # Raw pool laps/rests are not a validated set analysis. Without a
        # dedicated performance context, do not infer technique or within-pass
        # progression from total distance, total heart rate or raw lap rows.
        if activity.get("sport_type") == "Swim" and not analysis.get("performance_marker_id"):
            swim_without_structured_analysis(analysis, activity, day)

        prevent_repeat_of_completed_component(analysis, activity, day)

        after = json.dumps(analysis, ensure_ascii=False, sort_keys=True)
        changed = changed or before != after

    return changed


def main():
    plan = load_json(PLAN_FILE, {})
    activities = load_json(ACTIVITIES_FILE, {"activities": []})
    coach = load_json(COACH_FILE, {"analyses": []})
    changed = enforce_contract(coach, plan, activities)
    if changed:
        coach["output_contract_version"] = 16
        COACH_FILE.write_text(
            json.dumps(coach, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("Coach output contract v16: analysen kompakterad och evidensgrindar applicerade.")
    else:
        print("Coach output contract v16: inga korrigeringar behövdes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
