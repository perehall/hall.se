#!/usr/bin/env python3
"""Deterministic comparison between a completed activity and its planned dose."""

from __future__ import annotations

from collections import defaultdict


PLAN_COMPARISON_CONTRACT_VERSION = 2


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _positive(value):
    value = _number(value)
    return value if value is not None and value > 0 else None


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


def _fmt_distance_m(value):
    number = _positive(value)
    if number is None:
        return ""
    return f"{number:g} m"


def _planned_swim_structure(day):
    """Return the machine-readable planned swim structure from watch_workout.

    The comparison intentionally uses only work/swim distance steps. Rest duration,
    instructions and intensity labels are preserved elsewhere in the plan but are
    not needed to determine whether the completed set structure is the same workout.
    """
    workout = day.get("watch_workout") or {}
    blocks = workout.get("blocks") or []
    if not blocks:
        return None

    structure = []
    histogram = defaultdict(int)
    signature_parts = []

    for block in blocks:
        repeat = block.get("repeat", 1)
        if isinstance(repeat, bool) or not isinstance(repeat, (int, float)):
            repeat = 1
        repeat = max(1, int(repeat))
        for step in block.get("steps") or []:
            if step.get("kind") not in {"swim", "work"}:
                continue
            distance = _positive(step.get("distance_m"))
            if distance is None:
                continue
            distance_key = int(round(distance))
            structure.append(
                {
                    "repetitions": repeat,
                    "distance_per_rep_m": distance_key,
                    "total_distance_m": repeat * distance_key,
                }
            )
            histogram[distance_key] += repeat
            signature_parts.append(f"{repeat}x{distance_key}")

    if not structure:
        return None

    total_distance = sum(block["total_distance_m"] for block in structure)
    return {
        "signature": "+".join(signature_parts),
        "structure": structure,
        "histogram": dict(histogram),
        "structure_distance_m": float(total_distance),
    }


def _actual_swim_structure(activity):
    swim = (activity.get("workout_analysis_context") or {}).get("swim") or {}
    source = swim.get("structure") or []
    if not source:
        return None

    structure = []
    histogram = defaultdict(int)
    signature_parts = []
    for block in source:
        repetitions = block.get("repetitions")
        distance = block.get("distance_per_rep_m")
        if (
            isinstance(repetitions, bool)
            or not isinstance(repetitions, (int, float))
            or repetitions <= 0
        ):
            continue
        distance = _positive(distance)
        if distance is None:
            continue
        repetitions = int(repetitions)
        distance_key = int(round(distance))
        structure.append(
            {
                "repetitions": repetitions,
                "distance_per_rep_m": distance_key,
                "total_distance_m": repetitions * distance_key,
            }
        )
        histogram[distance_key] += repetitions
        signature_parts.append(f"{repetitions}x{distance_key}")

    if not structure:
        return None

    total_distance = sum(block["total_distance_m"] for block in structure)
    return {
        "signature": swim.get("structure_signature") or "+".join(signature_parts),
        "structure": structure,
        "histogram": dict(histogram),
        "structure_distance_m": float(total_distance),
    }


def _swim_structure_overlap(planned, actual):
    """Distance-weighted overlap for equal interval lengths.

    This is deliberately conservative: it does not infer that 5x100 equals 1x500.
    It only counts source intervals with the same recorded distance. That prevents
    a very different structured session from being called the planned workout just
    because total distance happens to be similar.
    """
    if not planned or not actual:
        return None

    matched_distance = 0.0
    for distance, planned_reps in planned["histogram"].items():
        actual_reps = actual["histogram"].get(distance, 0)
        matched_distance += min(planned_reps, actual_reps) * distance

    denominator = min(
        planned["structure_distance_m"],
        actual["structure_distance_m"],
    )
    if denominator <= 0:
        return None
    return matched_distance / denominator


def _swim_structure_relation(planned, actual):
    if not planned or not actual:
        return None, None

    if planned["signature"] == actual["signature"]:
        return "exact_match", 1.0

    overlap = _swim_structure_overlap(planned, actual)
    if overlap is None:
        return None, None

    # >=90% means the recorded work is essentially the planned structure with a
    # small omission/addition. <=50% means most of the completed distance came
    # from interval lengths that were not part of the planned set structure.
    if overlap >= 0.90:
        relation = "modified_planned_structure"
    elif overlap <= 0.50:
        relation = "different_structured_session"
    else:
        relation = "structure_deviation"
    return relation, overlap


def _add_swim_comparison(comparison, day, activity):
    if str(day.get("sport") or "").lower() != "swim":
        return

    workout = day.get("watch_workout") or {}
    planned_distance = _positive(workout.get("planned_distance_m"))
    if planned_distance is None:
        resolution = day.get("dose_resolution") or {}
        if resolution.get("kind") == "structured":
            planned_distance = _positive(resolution.get("value"))

    actual_distance = _positive(activity.get("distance_m"))
    if planned_distance is not None:
        comparison["planned_swim_distance_m"] = planned_distance
    if actual_distance is not None:
        comparison["actual_swim_distance_m"] = actual_distance

    if planned_distance is not None and actual_distance is not None:
        delta = actual_distance - planned_distance
        comparison["swim_distance_delta_m"] = round(delta, 1)
        comparison["swim_distance_delta_percent"] = round(
            (delta / planned_distance) * 100.0,
            1,
        )

    planned_structure = _planned_swim_structure(day)
    actual_structure = _actual_swim_structure(activity)
    if planned_structure:
        comparison["planned_swim_structure_signature"] = planned_structure["signature"]
        comparison["planned_swim_structure"] = planned_structure["structure"]
    if actual_structure:
        comparison["actual_swim_structure_signature"] = actual_structure["signature"]
        comparison["actual_swim_structure"] = actual_structure["structure"]

    relation, overlap = _swim_structure_relation(planned_structure, actual_structure)
    if relation:
        comparison["swim_structure_relation"] = relation
    if overlap is not None:
        comparison["swim_structure_overlap_ratio"] = round(overlap, 3)


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

    _add_swim_comparison(comparison, day, activity)
    return comparison


def plan_comparison_fact(comparison):
    if not comparison or not comparison.get("plan_day_found"):
        return ""

    facts = []

    selected = comparison.get("selected_duration_minutes")
    actual = comparison.get("actual_duration_minutes")
    if selected is not None and actual is not None:
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
        facts.append(text + ".")

    planned_swim = comparison.get("planned_swim_distance_m")
    actual_swim = comparison.get("actual_swim_distance_m")
    swim_relation = comparison.get("swim_structure_relation")
    if planned_swim is not None and actual_swim is not None:
        text = (
            f"Planerat simpass {_fmt_distance_m(planned_swim)}; "
            f"genomfört {_fmt_distance_m(actual_swim)}."
        )
        if swim_relation == "different_structured_session":
            text += " Genomförd setstruktur är ett annat strukturerat pass än planens setstruktur."
        elif swim_relation == "modified_planned_structure":
            text += " Genomförd setstruktur motsvarar huvudsakligen planens struktur med mindre avvikelse."
        elif swim_relation == "structure_deviation":
            text += " Genomförd setstruktur avviker från planens struktur."
        elif swim_relation == "exact_match":
            text += " Genomförd setstruktur matchar planens struktur."
        facts.append(text)

    return " ".join(facts)
