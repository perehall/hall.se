#!/usr/bin/env python3
from copy import deepcopy
from datetime import date, timedelta

from training_contracts import ACTIVITY_FAMILY, PLAN_SPORT_ACTIVITY_FAMILIES


WEEKDAY_ALIASES = {
    0: ("måndag", "monday"),
    1: ("tisdag", "tuesday"),
    2: ("onsdag", "wednesday"),
    3: ("torsdag", "thursday"),
    4: ("fredag", "friday"),
    5: ("lördag", "saturday"),
    6: ("söndag", "sunday"),
}


def planning_window(plan, upcoming=None):
    """Combine the active calendar week with the contiguous upcoming week.

    Calendar weeks are storage/presentation boundaries, not decision boundaries.
    The returned document is a copy used for near-term reasoning only; callers
    must still persist changes to the source document that owns the target date.
    """
    result = deepcopy(plan)
    upcoming_days = (upcoming or {}).get("days") or []
    if not upcoming_days:
        return result

    active_days = result.get("days") or []
    if not active_days:
        raise RuntimeError("Närtidsplan: aktiv plan saknar dagar")

    try:
        active_end = max(date.fromisoformat(day["date"]) for day in active_days)
        upcoming_start = min(date.fromisoformat(day["date"]) for day in upcoming_days)
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Närtidsplan: ogiltigt datum i planunderlaget") from exc

    if upcoming_start != active_end + timedelta(days=1):
        raise RuntimeError(
            "Närtidsplan: upcoming_week är inte sammanhängande med aktiv plan"
        )

    result["days"] = deepcopy(active_days) + [
        deepcopy(day)
        for day in upcoming_days
        if date.fromisoformat(day["date"]) > active_end
    ]
    return result


def remaining_training_dates(plan, activities, today_local):
    """Return known future training dates, including fixed/manual-lock sessions."""
    fulfilled = fulfilled_plan_dates(plan, activities)
    dates = []
    for day in plan.get("days") or []:
        date_value = str(day.get("date") or "")
        if not date_value or date_value <= today_local:
            continue
        if day.get("status") == "completed" or date_value in fulfilled:
            continue
        if day.get("sport") in {"open", "rest"}:
            continue
        if day.get("classification") == "recreation":
            continue
        dates.append(date_value)
    return dates


def activity_local_date(activity):
    value = activity.get("start_date_local") or activity.get("start_date") or ""
    return value[:10] if len(value) >= 10 else ""


def activity_family(activity):
    return ACTIVITY_FAMILY.get(activity.get("sport_type") or "")


def planned_families(day):
    """Return fulfillment families from explicit machine-readable plan sports."""
    sports = [str(day.get("sport") or "").strip().lower()]
    alternatives = day.get("alternative_sports") or []
    if isinstance(alternatives, list):
        sports.extend(str(item or "").strip().lower() for item in alternatives)

    families = set()
    for sport in sports:
        families.update(PLAN_SPORT_ACTIVITY_FAMILIES.get(sport, set()))
    return families


def planned_family(day):
    """Compatibility helper for single-family sports; never parses session text."""
    families = planned_families(day)
    return next(iter(families)) if len(families) == 1 else None


def matching_activity(day, activities):
    """Resolve the activity that fulfills a planned day.

    Explicitly separate/spontaneous activities still count as training load, but
    must never complete the planned session. Multiple same-family activities on
    the same day are treated as ambiguous unless the plan already carries an
    explicit activity_id.
    """
    date_value = day.get("date") or ""
    if not date_value:
        return None

    explicit_id = day.get("activity_id")
    if explicit_id is not None:
        linked = next(
            (
                activity
                for activity in activities
                if str(activity.get("id")) == str(explicit_id)
                and activity_local_date(activity) == date_value
            ),
            None,
        )
        if linked and linked.get("plan_relation") != "separate":
            return linked
        return None

    families = planned_families(day)
    if not families:
        return None

    candidates = [
        activity
        for activity in activities
        if activity_local_date(activity) == date_value
        and activity_family(activity) in families
        and activity.get("plan_relation") != "separate"
    ]
    return candidates[0] if len(candidates) == 1 else None


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
        date_value = day.get("date") or ""
        if not date_value or date_value < today_local:
            continue
        if day.get("status") in {"completed", "open"}:
            continue
        # A user-confirmed current plan may be locked until its planned activity
        # has actually happened. This prevents stale prior activity from rewriting
        # a decision the user has just made for today.
        if day.get("manual_lock") is True:
            continue
        # Rest/open and recreation are intentional no-auto-prescription states.
        if day.get("sport") in {"open", "rest"}:
            continue
        if day.get("classification") == "recreation":
            continue
        if date_value in fulfilled:
            continue
        allowed.append(date_value)
    return allowed


def unresolved_intervening_dates(plan, activities, today_local, target_date):
    """Return dates whose unknown outcome must be known before changing target_date.

    A coach action may only auto-edit a later session when every calendar day from
    today up to (but not including) the target is already fulfilled/completed or
    explicitly planned as rest. This prevents stale activity data from rewriting a
    session across still-unknown intervening load.
    """
    fulfilled = fulfilled_plan_dates(plan, activities)
    unresolved = []
    for day in plan.get("days", []):
        date_value = day.get("date") or ""
        if not date_value or date_value < today_local or date_value >= target_date:
            continue
        if day.get("status") == "completed" or date_value in fulfilled:
            continue
        if day.get("sport") == "rest":
            continue
        unresolved.append(date_value)
    return unresolved


def decision_ready_target_dates(plan, activities, today_local):
    """Only targets with no unresolved intervening day are safe to change now."""
    candidates = allowed_target_dates(plan, activities, today_local)
    return [
        target
        for target in candidates
        if not unresolved_intervening_dates(plan, activities, today_local, target)
    ]


def _explicit_weekday_references(text):
    lowered = str(text or "").lower()
    return {
        weekday
        for weekday, aliases in WEEKDAY_ALIASES.items()
        if any(alias in lowered for alias in aliases)
    }


def normalize_deferred_future_action(action, candidate_dates, ready_dates):
    """Defer model advice that is not safe to apply to the selected target day."""
    normalized = dict(action)
    target = str(normalized.get("target_date") or "").strip()
    candidates = set(candidate_dates)
    ready = set(ready_dates)

    # Fail closed when the recommendation explicitly talks about another weekday
    # than target_date. This catches structurally valid but semantically crossed
    # responses such as target_date=Wednesday with "reduce Friday's hill session".
    # Mentioning surrounding days is fine as long as the actual target weekday is
    # also explicit in the recommendation.
    if normalized.get("action") in {"reduce", "rest"} and target:
        try:
            target_weekday = date.fromisoformat(target).weekday()
        except ValueError:
            target_weekday = None
        recommendation_weekdays = _explicit_weekday_references(normalized.get("recommendation"))
        if (
            target_weekday is not None
            and recommendation_weekdays
            and target_weekday not in recommendation_weekdays
        ):
            normalized["action"] = "review"
            normalized["target_date"] = ""
            normalized["reason"] = (
                "AI-rådet hänvisar uttryckligen till en annan veckodag än target_date; "
                "ingen automatisk planändring görs."
            )
            normalized["recommendation"] = (
                "Ändra inte planen utifrån detta råd. Bedöm rätt målpass först när det är beslutsmoget."
            )
            normalized["requires_approval"] = False
            return normalized

    deferred = target in candidates and target not in ready
    blocked_change_without_target = (
        normalized.get("action") in {"reduce", "rest"}
        and not target
        and bool(candidates)
        and not ready
    )
    if not deferred and not blocked_change_without_target:
        return normalized

    normalized["action"] = "review"
    normalized["target_date"] = ""
    normalized["reason"] = (
        "Beslutet skjuts upp eftersom mellanliggande planerade dagar ännu inte har ett känt utfall."
    )
    normalized["recommendation"] = (
        "Ändra inte ett senare pass ännu. Bedöm det på nytt när de mellanliggande dagarnas faktiska "
        "belastning och återhämtning finns i underlaget."
    )
    normalized["requires_approval"] = False
    return normalized


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


def normalize_no_remaining_plan(
    action,
    allowed_dates,
    latest_date,
    fulfilled_dates,
    remaining_dates=None,
):
    if allowed_dates or remaining_dates or latest_date not in fulfilled_dates:
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
