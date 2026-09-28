#!/usr/bin/env python3
from copy import deepcopy
from datetime import date, timedelta

from activity_labels import public_activity_label
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

    if result.get("planned_workouts") is not None or (upcoming or {}).get("planned_workouts") is not None:
        active_workouts = deepcopy(result.get("planned_workouts") or [])
        upcoming_workouts = deepcopy((upcoming or {}).get("planned_workouts") or [])
        result["planned_workouts"] = active_workouts + [
            workout
            for workout in upcoming_workouts
            if date.fromisoformat(workout["date"]) > active_end
        ]

    result["near_term_window"] = {
        "active_week_end": active_end.isoformat(),
        "upcoming_week_start": upcoming_start.isoformat(),
        "window_end": max(
            date.fromisoformat(day["date"]) for day in result["days"]
        ).isoformat(),
        "calendar_week_is_presentation": True,
    }
    return result


def workout_key(workout, meta=None):
    """Return a stable identity for one physical planned workout."""
    meta = meta or {}
    explicit = str(workout.get("workout_key") or "").strip()
    if explicit:
        return explicit
    date_value = str(workout.get("date") or "").strip()
    microcycle_id = str(
        workout.get("microcycle_id") or meta.get("microcycle_id") or ""
    ).strip()
    slot = str(workout.get("microcycle_slot") or "").strip()
    if microcycle_id and date_value and slot:
        return f"{microcycle_id}:{date_value}:{slot}"
    # Legacy plans contain at most one physical workout per date. This fallback
    # is only a compatibility identity; new multi-session plans always carry a
    # microcycle slot / relational workout key.
    if date_value:
        return f"legacy:{date_value}"
    return ""


def planned_workouts(plan):
    """Return the physical-workout collection, never the 7-row calendar projection."""
    if plan.get("planned_workouts") is not None:
        rows = plan.get("planned_workouts") or []
    else:
        rows = plan.get("days") or []
    meta = plan.get("meta") or {}
    result = []
    for workout in rows:
        if not isinstance(workout, dict):
            continue
        if workout.get("sport") in {"open", "rest"}:
            continue
        item = workout
        key = workout_key(item, meta)
        if key and not item.get("workout_key"):
            item["workout_key"] = key
        result.append(item)
    return result


def workout_components(workout):
    raw = workout.get("components") or workout.get("workout_components")
    if raw is None and isinstance(workout.get("payload"), dict):
        raw = (
            workout["payload"].get("components")
            or workout["payload"].get("workout_components")
        )
    if not isinstance(raw, list):
        return ()
    components = []
    for index, component in enumerate(raw):
        if not isinstance(component, dict):
            continue
        sport = str(component.get("sport") or "").strip().lower()
        if not sport:
            continue
        components.append(
            (
                int(component.get("order") or index + 1),
                sport,
            )
        )
    return tuple(sport for _, sport in sorted(components))


def workout_required_families(workout):
    """Families that must be represented for the workout to be complete.

    A normal workout has one required family. A structured multisport workout
    has one requirement per ordered component. Matching remains fail-closed
    whenever two planned workouts compete for the same unlinked activity.
    """
    components = workout_components(workout)
    if components:
        requirements = []
        for sport in components:
            families = PLAN_SPORT_ACTIVITY_FAMILIES.get(sport, set())
            if not families:
                return ()
            requirements.append(frozenset(families))
        return tuple(requirements)

    families = planned_families(workout)
    return (frozenset(families),) if families else ()


def _activity_candidates_for_requirement(requirement, activities, date_value, used_ids):
    return [
        activity
        for activity in activities
        if activity_local_date(activity) == date_value
        and activity_family(activity) in requirement
        and activity.get("plan_relation") != "separate"
        and str(activity.get("id")) not in used_ids
    ]


def workout_fulfillment(plan, activities):
    """Resolve complete planned workouts without guessing ambiguous links.

    Returns workout_key -> tuple(activity_ids). One activity is never consumed
    by two workouts. Explicit activity_id linkage wins. For unlinked work,
    every required sport component must have exactly one candidate and that
    candidate must not also be eligible for another unresolved workout.
    """
    workouts = planned_workouts(plan)
    by_date = {}
    for workout in workouts:
        by_date.setdefault(str(workout.get("date") or ""), []).append(workout)

    fulfilled = {}
    for date_value, date_workouts in by_date.items():
        used_ids = set()

        # First honor explicit canonical linkage.
        unresolved = []
        for workout in date_workouts:
            key = workout_key(workout, plan.get("meta") or {})
            explicit_id = workout.get("activity_id")
            if explicit_id is None:
                unresolved.append(workout)
                continue
            linked = next(
                (
                    activity
                    for activity in activities
                    if str(activity.get("id")) == str(explicit_id)
                    and activity_local_date(activity) == date_value
                    and activity.get("plan_relation") != "separate"
                ),
                None,
            )
            if linked is not None:
                fulfilled[key] = (linked.get("id"),)
                used_ids.add(str(linked.get("id")))
            else:
                unresolved.append(workout)

        # Candidate map is calculated before consuming any inferred activity so
        # competing same-family sessions remain ambiguous rather than order-dependent.
        requirement_candidates = {}
        candidate_owners = {}
        for workout in unresolved:
            key = workout_key(workout, plan.get("meta") or {})
            requirements = workout_required_families(workout)
            per_requirement = []
            for requirement in requirements:
                candidates = _activity_candidates_for_requirement(
                    requirement, activities, date_value, used_ids
                )
                ids = tuple(str(activity.get("id")) for activity in candidates)
                per_requirement.append((requirement, candidates))
                for candidate_id in ids:
                    candidate_owners.setdefault(candidate_id, set()).add(key)
            requirement_candidates[key] = per_requirement

        for workout in unresolved:
            key = workout_key(workout, plan.get("meta") or {})
            requirements = requirement_candidates.get(key) or []
            matched = []
            local_used = set()
            complete = bool(requirements)
            for _requirement, candidates in requirements:
                unique = [
                    activity
                    for activity in candidates
                    if str(activity.get("id")) not in local_used
                    and len(candidate_owners.get(str(activity.get("id")), set())) == 1
                ]
                if len(unique) != 1:
                    complete = False
                    break
                activity = unique[0]
                local_used.add(str(activity.get("id")))
                matched.append(activity.get("id"))
            if complete:
                fulfilled[key] = tuple(matched)
                used_ids.update(str(activity_id) for activity_id in matched)

    return fulfilled


def fulfilled_plan_workouts(plan, activities):
    return workout_fulfillment(plan, activities)


def _workouts_by_date(plan):
    result = {}
    for workout in planned_workouts(plan):
        result.setdefault(str(workout.get("date") or ""), []).append(workout)
    return result


def unresolved_plan_workout_keys(plan, activities):
    fulfilled = fulfilled_plan_workouts(plan, activities)
    return tuple(
        workout_key(workout, plan.get("meta") or {})
        for workout in planned_workouts(plan)
        if workout_key(workout, plan.get("meta") or {}) not in fulfilled
        and workout.get("status") != "completed"
    )


def allowed_target_workouts(plan, activities, today_local):
    fulfilled = fulfilled_plan_workouts(plan, activities)
    result = []
    for workout in planned_workouts(plan):
        date_value = str(workout.get("date") or "")
        key = workout_key(workout, plan.get("meta") or {})
        if not date_value or date_value < today_local:
            continue
        if workout.get("status") == "completed" or key in fulfilled:
            continue
        if workout.get("manual_lock") is True:
            continue
        if workout.get("classification") == "recreation":
            continue
        result.append(
            {
                "workout_key": key,
                "date": date_value,
                "session": str(workout.get("session") or ""),
                "sport": str(workout.get("sport") or ""),
            }
        )
    return result


def _date_is_resolved(plan, activities, date_value):
    date_workouts = _workouts_by_date(plan).get(date_value, [])
    if not date_workouts:
        # A calendar day without physical workouts is resolved by definition.
        return True
    fulfilled = fulfilled_plan_workouts(plan, activities)
    return all(
        workout.get("status") == "completed"
        or workout_key(workout, plan.get("meta") or {}) in fulfilled
        for workout in date_workouts
    )


def decision_ready_target_workouts(plan, activities, today_local):
    candidates = allowed_target_workouts(plan, activities, today_local)
    dates = sorted({item["date"] for item in candidates})
    ready_dates = set()
    for target_date in dates:
        unresolved_prior = False
        for day in plan.get("days") or []:
            date_value = str(day.get("date") or "")
            if not date_value or date_value < today_local or date_value >= target_date:
                continue
            if not _date_is_resolved(plan, activities, date_value):
                unresolved_prior = True
                break
        if not unresolved_prior:
            ready_dates.add(target_date)
    return [item for item in candidates if item["date"] in ready_dates]


def remaining_training_dates(plan, activities, today_local):
    """Return future dates with at least one unresolved physical workout."""
    return sorted(
        {
            item["date"]
            for item in allowed_target_workouts(plan, activities, today_local)
            if item["date"] > today_local
        }
    )


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
    """Compatibility date view: a date is fulfilled only when all its workouts are."""
    by_date = _workouts_by_date(plan)
    fulfilled = fulfilled_plan_workouts(plan, activities)
    result = {}
    for date_value, workouts in by_date.items():
        if workouts and all(
            workout.get("status") == "completed"
            or workout_key(workout, plan.get("meta") or {}) in fulfilled
            for workout in workouts
        ):
            ids = [
                activity_id
                for workout in workouts
                for activity_id in fulfilled.get(
                    workout_key(workout, plan.get("meta") or {}), ()
                )
            ]
            result[date_value] = ids[0] if len(ids) == 1 else tuple(ids)
    return result


def allowed_target_dates(plan, activities, today_local):
    return list(
        dict.fromkeys(
            item["date"]
            for item in allowed_target_workouts(plan, activities, today_local)
        )
    )


def unresolved_intervening_dates(plan, activities, today_local, target_date):
    unresolved = []
    for day in plan.get("days", []):
        date_value = day.get("date") or ""
        if not date_value or date_value < today_local or date_value >= target_date:
            continue
        if not _date_is_resolved(plan, activities, date_value):
            unresolved.append(date_value)
    return unresolved


def decision_ready_target_dates(plan, activities, today_local):
    return list(
        dict.fromkeys(
            item["date"]
            for item in decision_ready_target_workouts(
                plan, activities, today_local
            )
        )
    )

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
                "Rådet kunde inte kopplas entydigt till det angivna målpasset och "
                "appliceras därför inte automatiskt."
            )
            normalized["recommendation"] = (
                "Behåll grundplanen tills nästa beslutsmogna pass kan bedömas mot "
                "faktisk närbelastning och återhämtning."
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
    fulfilled_workouts = fulfilled_plan_workouts(result, activities)
    by_id = {
        str(activity.get("id")): activity
        for activity in activities
        if activity.get("id") is not None
    }

    for workout in planned_workouts(result):
        key = workout_key(workout, result.get("meta") or {})
        activity_ids = fulfilled_workouts.get(key)
        if not activity_ids:
            continue
        workout["status"] = "completed"
        workout["coach_fulfilled_by_activities"] = [
            {
                "id": activity_id,
                "sport_type": (by_id.get(str(activity_id)) or {}).get("sport_type"),
                "display_label": (by_id.get(str(activity_id)) or {}).get("display_label"),
            }
            for activity_id in activity_ids
        ]
        if len(activity_ids) == 1:
            workout["coach_fulfilled_by_activity"] = workout[
                "coach_fulfilled_by_activities"
            ][0]

    fulfilled_dates = fulfilled_plan_dates(result, activities)
    for day in result.get("days", []):
        date_value = day.get("date")
        if date_value not in fulfilled_dates:
            continue
        day["status"] = "completed"
        ids = fulfilled_dates[date_value]
        ids = ids if isinstance(ids, tuple) else (ids,)
        if len(ids) == 1:
            activity = by_id.get(str(ids[0])) or {}
            day["coach_fulfilled_by_activity"] = {
                "id": ids[0],
                "sport_type": activity.get("sport_type"),
                "display_label": activity.get("display_label"),
            }
    return result, fulfilled_dates


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
    """Render exact latest-activity facts from source data with canonical public terminology."""
    label = public_activity_label(activity)
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
            f"Planstatus {latest_date}: dagen är markerad genomförd i coachens beslutsunderlag."
        )

    return facts[:4]