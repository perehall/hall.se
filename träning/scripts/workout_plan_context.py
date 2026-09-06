#!/usr/bin/env python3
"""Deterministic comparison between a completed activity and its planned dose."""

from __future__ import annotations


PLAN_COMPARISON_CONTRACT_VERSION = 1


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _find_day(plan, activity_date):
    return next(
        (day for day in (plan.get("days") or []) if day.get("date") == activity_date),
        None,
    )


def _duration_option_minutes(day):
    values = []
    for option in day.get("dose_options") or []:
        if option.get("kind") != "duration_minutes":
            continue
        value = _number(option.get("value"))
        if value is not None and value > 0:
            values.append(value)
    return sorted(set(values))


def build_plan_comparison(plan, activity, activity_date):
    """Return factual plan-vs-actual data without coaching interpretation."""
    day = _find_day(plan, activity_date)
    if not day:
        return {
            "contract_version": PLAN_COMPARISON_CONTRACT_VERSION,
            "plan_day_found": False,
            "activity_date": activity_date,
        }

    comparison = {
        "contract_version": PLAN_COMPARISON_CONTRACT_VERSION,
        "plan_day_found": True,
        "activity_date": activity_date,
        "planned_session": day.get("session") or "",
        "planned_status": day.get("status") or "",
        "planned_sport": day.get("sport") or "",
        "priority_role": day.get("priority_role") or "",
        "stimuli": list(day.get("stimuli") or []),
    }

    resolution = day.get("dose_resolution") or {}
    if resolution.get("kind") == "duration_minutes":
        planned_minutes = _number(resolution.get("value"))
        if planned_minutes is not None and planned_minutes > 0:
            comparison["selected_duration_minutes"] = planned_minutes

    options = _duration_option_minutes(day)
    if options:
        comparison["approved_duration_options_minutes"] = options
        comparison["approved_duration_min_minutes"] = options[0]
        comparison["approved_duration_max_minutes"] = options[-1]

    moving_time_s = _number(activity.get("moving_time_s"))
    if moving_time_s is not None and moving_time_s > 0:
        actual_minutes = moving_time_s / 60.0
        comparison["actual_duration_minutes"] = round(actual_minutes, 2)

        selected = comparison.get("selected_duration_minutes")
        if selected is not None:
            delta = actual_minutes - selected
            comparison["duration_delta_vs_selected_minutes"] = round(delta, 2)
            comparison["duration_delta_vs_selected_percent"] = round(
                (delta / selected) * 100.0,
                1,
            )

        if options:
            tolerance = 2.0
            low = options[0]
            high = options[-1]
            if actual_minutes < low - tolerance:
                relation = "below_approved_duration_range"
                outside_by = low - actual_minutes
            elif actual_minutes > high + tolerance:
                relation = "above_approved_duration_range"
                outside_by = actual_minutes - high
            else:
                relation = "within_approved_duration_range"
                outside_by = 0.0
            comparison["duration_relation_to_approved_options"] = relation
            comparison["duration_outside_approved_range_minutes"] = round(outside_by, 2)

    return comparison


def plan_comparison_fact(comparison):
    if not comparison or not comparison.get("plan_day_found"):
        return ""
    selected = comparison.get("selected_duration_minutes")
    actual = comparison.get("actual_duration_minutes")
    if selected is None or actual is None:
        return ""

    delta = comparison.get("duration_delta_vs_selected_minutes")
    text = f"Planerad tidsdos {selected:g} min; faktisk rörelsetid {actual:g} min"
    if isinstance(delta, (int, float)):
        sign = "+" if delta > 0 else ""
        text += f" ({sign}{delta:g} min mot vald dos)"

    high = comparison.get("approved_duration_max_minutes")
    relation = comparison.get("duration_relation_to_approved_options")
    if relation == "above_approved_duration_range" and isinstance(high, (int, float)):
        text += f"; över längsta godkända alternativet {high:g} min"
    elif relation == "below_approved_duration_range":
        low = comparison.get("approved_duration_min_minutes")
        if isinstance(low, (int, float)):
            text += f"; under kortaste godkända alternativet {low:g} min"
    return text + "."
