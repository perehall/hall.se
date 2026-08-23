#!/usr/bin/env python3
from copy import deepcopy


ACTIVITY_FAMILY = {
    "Run": "run",
    "TrailRun": "run",
    "VirtualRun": "run",
    "Swim": "swim",
    "MountainBikeRide": "bike",
    "Ride": "bike",
    "VirtualRide": "bike",
    "WeightTraining": "strength",
    "Enduro": "enduro",
}


def activity_local_date(activity):
    value = activity.get("start_date_local") or activity.get("start_date") or ""
    return value[:10] if len(value) >= 10 else ""


def activity_family(activity):
    return ACTIVITY_FAMILY.get(activity.get("sport_type") or "")


def planned_family(day):
    explicit = str(day.get("sport") or "").strip().lower()
    session = str(day.get("session") or "").strip().lower()
    text = f"{explicit} {session}"

    if "swimrun" in text:
        return "swimrun"
    if "enduro" in text:
        return "enduro"
    if "simning" in text or "swim" in text:
        return "swim"
    if "styrka" in text or "strength" in text:
        return "strength"
    if "mtb" in text or "xc" in text or "cykel" in text or "bike" in text:
        return "bike"
    if "trail" in text or "löp" in text or "run" in text:
        return "run"
    return None


def matching_activity(day, activities):
    family = planned_family(day)
    date = day.get("date") or ""
    if not family or not date:
        return None

    for activity in activities:
        if activity_local_date(activity) != date:
            continue
        if activity_family(activity) == family:
            return activity
    return None


def fulfilled_plan_dates(plan, activities):
    fulfilled = {}
    for day in plan.get("days", []):
        activity = matching_activity(day, activities)
        if activity:
            fulfilled[day["date"]] = activity.get("id")
    return fulfilled


def allowed_target_dates(plan, activities, today_local):
    fulfilled = fulfilled_plan_dates(plan, activities)
    allowed = []
    for day in plan.get("days", []):
        date = day.get("date") or ""
        if not date or date < today_local:
            continue
        if day.get("status") == "completed":
            continue
        if date in fulfilled:
            continue
        allowed.append(date)
    return allowed


def plan_for_coach(plan, activities):
    result = deepcopy(plan)
    fulfilled = fulfilled_plan_dates(result, activities)
    by_id = {
        activity.get("id"): activity
        for activity in activities
        if activity.get("id") is not None
    }

    for day in result.get("days", []):
        activity_id = fulfilled.get(day.get("date"))
        if activity_id is None:
            continue
        activity = by_id.get(activity_id) or {}
        day["status"] = "completed"
        day["coach_fulfilled_by_activity"] = {
            "id": activity_id,
            "sport_type": activity.get("sport_type"),
            "display_label": activity.get("display_label"),
        }
    return result, fulfilled


def validate_plan_action(action, allowed_dates):
    target = str(action.get("target_date") or "").strip()
    kind = action.get("action")
    allowed = set(allowed_dates)

    if target and target not in allowed:
        raise RuntimeError(
            f"AI coach: förbjudet target_date {target!r}; tillåtna datum är {sorted(allowed)!r}"
        )
    if kind in {"reduce", "rest"} and not target:
        raise RuntimeError(f"AI coach: action {kind!r} kräver ett tillåtet target_date")
    return action


def normalize_no_remaining_plan(action, allowed_dates, latest_date, fulfilled_dates):
    if allowed_dates or latest_date not in fulfilled_dates:
        return action

    normalized = dict(action)
    normalized["target_date"] = ""
    if normalized.get("action") in {"reduce", "rest"}:
        normalized["action"] = "review"
    normalized["recommendation"] = (
        "Ingen ytterligare träning ordineras idag; dagens planerade pass är redan genomfört. "
        "Nästa planerade pass saknas i aktuellt underlag."
    )
    return normalized


def normalize_assessment_confidence(assessment):
    """En icke-tom unknowns-lista är per prompt beslutspåverkande osäkerhet.

    Då får confidence inte vara high. Vi ändrar aldrig medium/low uppåt och
    låter high stå kvar när modellen inte själv anger några beslutspåverkande
    okända faktorer.
    """
    normalized = deepcopy(assessment)
    unknowns = normalized.get("unknowns") or []
    if normalized.get("confidence") == "high" and unknowns:
        normalized["confidence"] = "medium"
    return normalized
