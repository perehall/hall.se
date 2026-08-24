#!/usr/bin/env python3
from copy import deepcopy

from training_contracts import ACTIVITY_FAMILY, PLAN_SPORT_ACTIVITY_FAMILIES


def activity_local_date(activity):
    value = activity.get("start_date_local") or activity.get("start_date") or ""
    return value[:10] if len(value) >= 10 else ""


def activity_family(activity):
    return ACTIVITY_FAMILY.get(activity.get("sport_type") or "")


def planned_families(day):
    """Return fulfillment families from explicit machine-readable plan sport."""
    sport = str(day.get("sport") or "").strip().lower()
    return set(PLAN_SPORT_ACTIVITY_FAMILIES.get(sport, set()))


def planned_family(day):
    """Compatibility helper for single-family sports; never parses session text."""
    families = planned_families(day)
    return next(iter(families)) if len(families) == 1 else None


def matching_activity(day, activities):
    families = planned_families(day)
    date = day.get("date") or ""
    if not families or not date:
        return None

    for activity in activities:
        if activity_local_date(activity) != date:
            continue
        if activity_family(activity) in families:
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
        if day.get("status") in {"completed", "open"}:
            continue
        # Rest/open and recreation are intentional no-auto-prescription states.
        if day.get("sport") in {"open", "rest"}:
            continue
        if day.get("classification") == "recreation":
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
    """A non-empty unknowns list prevents high confidence."""
    normalized = deepcopy(assessment)
    unknowns = normalized.get("unknowns") or []
    if normalized.get("confidence") == "high" and unknowns:
        normalized["confidence"] = "medium"
    return normalized


def _fmt_duration(seconds):
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _fmt_number_sv(value, decimals=1):
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.{decimals}f}".replace(".", ",")


def canonical_activity_fact(activity):
    """Render exact latest-activity facts from source data, never model prose."""
    label = activity.get("display_label") or activity.get("sport_type") or "Aktivitet"
    bits = []

    distance = activity.get("distance_m")
    if distance is not None and float(distance) > 0:
        bits.append(f"{float(distance) / 1000:.2f} km".replace(".", ","))

    elapsed = activity.get("elapsed_time_s")
    if elapsed is None:
        elapsed = activity.get("moving_time_s")
    if elapsed is not None:
        bits.append(_fmt_duration(elapsed))

    elevation = activity.get("total_elevation_gain_m")
    if elevation is not None and float(elevation) > 0:
        bits.append(f"{_fmt_number_sv(elevation)} m+")

    avg_hr = activity.get("average_heartrate")
    if avg_hr is not None:
        bits.append(f"snittpuls {_fmt_number_sv(avg_hr)}")

    max_hr = activity.get("max_heartrate")
    if max_hr is not None:
        bits.append(f"maxpuls {_fmt_number_sv(max_hr)}")

    detail = " · ".join(bits)
    return f"{label}: {detail}." if detail else f"{label}."


def canonical_facts(latest_activity, latest_date, fulfilled_dates):
    """Facts shown by Yoda are deterministic; AI only owns interpretation."""
    facts = [canonical_activity_fact(latest_activity)]

    user_report = str(latest_activity.get("user_report") or "").strip()
    if user_report:
        facts.append(f"Användarrapport: {user_report.rstrip('.')}.")

    if latest_date in fulfilled_dates:
        facts.append(
            f"Planstatus {latest_date}: dagens planerade pass är genomfört i coachens beslutsunderlag."
        )

    return facts[:4]
