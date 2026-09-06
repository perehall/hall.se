#!/usr/bin/env python3
"""Deterministic workout facts for the AI coach.

The coach should interpret training, not calculate units from raw provider data.
This module converts source measurements into a compact, versioned contract.
"""

from __future__ import annotations

from math import isclose


WORKOUT_ANALYSIS_CONTRACT_VERSION = 1
RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _positive(value):
    value = _number(value)
    return value if value is not None and value > 0 else None


def pace_s_per_km(duration_s, distance_m):
    duration = _positive(duration_s)
    distance = _positive(distance_m)
    if duration is None or distance is None:
        return None
    return duration / (distance / 1000.0)


def fmt_pace(seconds_per_km):
    value = _positive(seconds_per_km)
    if value is None:
        return ""
    total = int(round(value))
    return f"{total // 60}:{total % 60:02d}/km"


def _total_facts(activity):
    distance = _positive(activity.get("distance_m"))
    moving = _positive(activity.get("moving_time_s"))
    elapsed = _positive(activity.get("elapsed_time_s"))
    elevation = _number(activity.get("total_elevation_gain_m"))
    avg_hr = _number(activity.get("average_heartrate"))
    max_hr = _number(activity.get("max_heartrate"))

    return {
        "distance_m": distance,
        "distance_km": round(distance / 1000.0, 3) if distance is not None else None,
        "moving_time_s": moving,
        "elapsed_time_s": elapsed,
        "elevation_gain_m": elevation,
        "average_heartrate": avg_hr,
        "max_heartrate": max_hr,
    }


def _run_context(activity):
    total_pace = pace_s_per_km(activity.get("moving_time_s"), activity.get("distance_m"))
    source_laps = []

    for lap in activity.get("laps") or []:
        distance = _positive(lap.get("distance_m"))
        duration = _positive(lap.get("moving_time_s"))
        lap_pace = pace_s_per_km(duration, distance)
        if distance is None or duration is None or lap_pace is None:
            continue

        # Near-kilometre source laps are useful descriptive measurements for running.
        # They are never labelled as workout intervals here.
        if 900 <= distance <= 1100:
            source_laps.append(
                {
                    "lap_index": lap.get("lap_index"),
                    "distance_m": round(distance, 1),
                    "moving_time_s": int(round(duration)),
                    "pace_s_per_km": round(lap_pace, 2),
                    "pace": fmt_pace(lap_pace),
                    "average_heartrate": _number(lap.get("average_heartrate")),
                }
            )

    fastest = None
    if source_laps:
        fastest = min(source_laps, key=lambda row: row["pace_s_per_km"])

    return {
        "average_pace_s_per_km": round(total_pace, 2) if total_pace is not None else None,
        "average_pace": fmt_pace(total_pace),
        "source_laps_near_1km": source_laps,
        "fastest_source_lap_near_1km": fastest,
        "source_lap_note": (
            "Source laps are descriptive measurements only; do not assume they are workout intervals."
        ),
    }


def build_workout_analysis_context(activity):
    """Build the versioned deterministic analysis contract for one activity."""
    sport_type = str(activity.get("sport_type") or "")
    context = {
        "contract_version": WORKOUT_ANALYSIS_CONTRACT_VERSION,
        "activity_id": activity.get("id"),
        "sport_type": sport_type,
        "display_label": activity.get("display_label") or sport_type,
        "classification": activity.get("classification"),
        "user_report": str(activity.get("user_report") or "").strip(),
        "total": _total_facts(activity),
        "run": _run_context(activity) if sport_type in RUN_TYPES else None,
    }
    validate_workout_analysis_context(activity, context)
    return context


def validate_workout_analysis_context(activity, context):
    """Fail closed if deterministic facts drift from source time/distance."""
    if context.get("contract_version") != WORKOUT_ANALYSIS_CONTRACT_VERSION:
        raise RuntimeError("Workout analysis: wrong contract version")

    source_report = str(activity.get("user_report") or "").strip()
    if context.get("user_report") != source_report:
        raise RuntimeError("Workout analysis: user report mismatch")

    run = context.get("run")
    if run is None:
        return True

    expected = pace_s_per_km(activity.get("moving_time_s"), activity.get("distance_m"))
    actual = run.get("average_pace_s_per_km")
    if expected is None:
        if actual is not None:
            raise RuntimeError("Workout analysis: pace exists without source time/distance")
    elif actual is None or not isclose(float(actual), expected, abs_tol=0.02):
        raise RuntimeError("Workout analysis: total running pace failed arithmetic validation")

    by_index = {lap.get("lap_index"): lap for lap in activity.get("laps") or []}
    for row in run.get("source_laps_near_1km") or []:
        source = by_index.get(row.get("lap_index"))
        expected_lap = pace_s_per_km(
            (source or {}).get("moving_time_s"),
            (source or {}).get("distance_m"),
        )
        if expected_lap is None or not isclose(
            float(row.get("pace_s_per_km")), expected_lap, abs_tol=0.02
        ):
            raise RuntimeError("Workout analysis: lap pace failed arithmetic validation")

    return True
