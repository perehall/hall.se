#!/usr/bin/env python3
"""Deterministic workout facts for the AI coach.

The coach should interpret training, not calculate units from raw provider data.
This module converts source measurements into a compact, versioned contract.
"""

from __future__ import annotations

from math import isclose
from statistics import mean, median


WORKOUT_ANALYSIS_CONTRACT_VERSION = 3
RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
SWIM_TYPES = {"Swim"}
ENDURO_TYPES = {"Enduro"}


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


def pace_s_per_100m(duration_s, distance_m):
    duration = _positive(duration_s)
    distance = _positive(distance_m)
    if duration is None or distance is None:
        return None
    return duration / (distance / 100.0)


def fmt_pace(seconds_per_km):
    value = _positive(seconds_per_km)
    if value is None:
        return ""
    total = int(round(value))
    return f"{total // 60}:{total % 60:02d}/km"


def fmt_swim_pace(seconds_per_100m):
    value = _positive(seconds_per_100m)
    if value is None:
        return ""
    minutes = int(value // 60)
    seconds = value - minutes * 60
    return f"{minutes}:{seconds:04.1f}/100 m".replace(".", ",")


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


def _run_lap_measurements(activity):
    rows = []
    for source_position, lap in enumerate(activity.get("laps") or []):
        distance = _positive(lap.get("distance_m"))
        duration = _positive(lap.get("moving_time_s")) or _positive(lap.get("elapsed_time_s"))
        if distance is None or duration is None:
            continue
        speed = distance / duration
        rows.append(
            {
                "source_position": source_position,
                "lap_index": lap.get("lap_index"),
                "distance_m": round(distance, 2),
                "moving_time_s": round(duration, 1),
                "speed_m_s": round(speed, 3),
                "pace_s_per_km": round(pace_s_per_km(duration, distance), 2),
                "pace": fmt_pace(pace_s_per_km(duration, distance)),
                "average_heartrate": _number(lap.get("average_heartrate")),
                "max_heartrate": _number(lap.get("max_heartrate")),
            }
        )
    return rows


def _run_short_interval_context(activity):
    """Detect repeated short work laps without inventing terrain or intensity.

    The detector deliberately requires a dominant distance cluster that alternates
    with slower single-lap recoveries. This distinguishes work reps from recovery
    laps and avoids treating ordinary autolaps as intervals.
    """
    rows = _run_lap_measurements(activity)
    candidates = [
        row
        for row in rows
        if 80 <= row["distance_m"] <= 300
        and 15 <= row["moving_time_s"] <= 120
    ]
    if len(candidates) < 6:
        return {"structured": False}

    best = None
    for pivot in candidates:
        tolerance = max(8.0, pivot["distance_m"] * 0.07)
        cluster = [
            row for row in candidates
            if abs(row["distance_m"] - pivot["distance_m"]) <= tolerance
        ]
        spread = (
            max(row["distance_m"] for row in cluster)
            - min(row["distance_m"] for row in cluster)
        )
        score = (len(cluster), -spread)
        if best is None or score > best[0]:
            best = (score, cluster)

    cluster = best[1] if best else []
    if len(cluster) < 6:
        return {"structured": False}

    center = median(row["distance_m"] for row in cluster)
    tolerance = max(8.0, center * 0.07)
    reps = sorted(
        [
            row for row in candidates
            if abs(row["distance_m"] - center) <= tolerance
        ],
        key=lambda row: row["source_position"],
    )
    if len(reps) < 6:
        return {"structured": False}

    by_position = {row["source_position"]: row for row in rows}
    single_recoveries = []
    alternating_gaps = 0
    for previous, current in zip(reps, reps[1:]):
        gap = current["source_position"] - previous["source_position"]
        if gap == 2:
            recovery = by_position.get(previous["source_position"] + 1)
            if recovery:
                single_recoveries.append(recovery)
                alternating_gaps += 1

    required_alternating = max(4, int(round((len(reps) - 1) * 0.60)))
    if alternating_gaps < required_alternating or not single_recoveries:
        return {"structured": False}

    rep_speed = mean(row["speed_m_s"] for row in reps)
    recovery_speed = mean(row["speed_m_s"] for row in single_recoveries)
    if recovery_speed <= 0 or rep_speed < recovery_speed * 1.10:
        return {"structured": False}

    blocks = []
    current_block = []
    for index, rep in enumerate(reps):
        if index == 0:
            current_block = [rep]
            continue
        previous = reps[index - 1]
        if rep["source_position"] - previous["source_position"] == 2:
            current_block.append(rep)
        else:
            blocks.append(current_block)
            current_block = [rep]
    if current_block:
        blocks.append(current_block)

    block_counts = [len(block) for block in blocks]
    if any(count < 2 for count in block_counts):
        return {"structured": False}

    representative_distance = int(round(median(row["distance_m"] for row in reps)))
    if len(block_counts) > 1 and len(set(block_counts)) == 1:
        signature = f"{len(block_counts)}x{block_counts[0]}x{representative_distance}m"
    elif len(block_counts) == 1:
        signature = f"{block_counts[0]}x{representative_distance}m"
    else:
        signature = f"{'+'.join(str(value) for value in block_counts)}x{representative_distance}m"

    public_reps = [
        {key: value for key, value in row.items() if key != "source_position"}
        for row in reps
    ]
    return {
        "structured": True,
        "structure_signature": signature,
        "repetition_count": len(reps),
        "representative_distance_m": round(median(row["distance_m"] for row in reps), 1),
        "work_distance_m": round(sum(row["distance_m"] for row in reps), 1),
        "work_duration_s": round(sum(row["moving_time_s"] for row in reps), 1),
        "block_repetition_counts": block_counts,
        "blocks": [
            {
                "block_index": block_index,
                "repetitions": len(block),
                "lap_indices": [row.get("lap_index") for row in block],
            }
            for block_index, block in enumerate(blocks, 1)
        ],
        "reps": public_reps,
        "mean_rep_speed_m_s": round(rep_speed, 3),
        "mean_single_lap_recovery_speed_m_s": round(recovery_speed, 3),
        "detection_basis": (
            "Dominant short-lap distance cluster with repeated one-lap slower recoveries; "
            "block boundaries are gaps larger than one recovery lap."
        ),
        "interpretation_limits": [
            "The structure proves repeated short work-like laps, not that the terrain was uphill.",
            "Provider laps alone do not establish threshold, tempo, sprint or another physiological intensity label.",
            "Terrain and intended intensity require user report, plan context or another explicit source.",
        ],
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
        "short_intervals": _run_short_interval_context(activity),
        "source_lap_note": (
            "Near-1 km source laps are descriptive measurements only. "
            "Only run.short_intervals may classify a repeated short-lap structure, "
            "and it does not infer terrain or physiological intensity."
        ),
    }


def _swim_source_intervals(activity):
    """Extract source swim intervals without inventing set semantics.

    Positive-distance laps are swim intervals. Zero-distance laps are treated only
    as recorded rest/lap markers. A later grouping step may join equal-distance
    intervals into a repeat set only when such a marker exists between them.
    """
    intervals = []
    rest_before_s = 0.0
    rest_marker_before = False

    for lap in activity.get("laps") or []:
        distance = _positive(lap.get("distance_m"))
        if distance is None:
            rest_marker_before = True
            rest = _positive(lap.get("elapsed_time_s")) or _positive(lap.get("moving_time_s"))
            if rest is not None:
                rest_before_s += rest
            continue

        duration = _positive(lap.get("moving_time_s")) or _positive(lap.get("elapsed_time_s"))
        pace = pace_s_per_100m(duration, distance)
        if duration is None or pace is None:
            rest_before_s = 0.0
            rest_marker_before = False
            continue

        intervals.append(
            {
                "lap_index": lap.get("lap_index"),
                "distance_m": round(distance, 1),
                "moving_time_s": round(duration, 1),
                "pace_s_per_100m": round(pace, 2),
                "pace": fmt_swim_pace(pace),
                "average_heartrate": _number(lap.get("average_heartrate")),
                "max_heartrate": _number(lap.get("max_heartrate")),
                "rest_marker_before": rest_marker_before,
                "recorded_rest_before_s": round(rest_before_s, 1),
            }
        )
        rest_before_s = 0.0
        rest_marker_before = False

    return intervals


def _same_swim_distance(left, right):
    return isclose(float(left), float(right), abs_tol=1.0)


def _swim_repeat_set(group, set_index):
    intervals = group["intervals"]
    paces = [row["pace_s_per_100m"] for row in intervals]
    hrs = [
        row["average_heartrate"]
        for row in intervals
        if isinstance(row.get("average_heartrate"), (int, float))
        and row.get("average_heartrate") > 0
    ]
    rests = [row["recorded_rest_before_s"] for row in intervals[1:]]

    return {
        "set_index": set_index,
        "repetitions": len(intervals),
        "distance_per_rep_m": round(group["distance_m"], 1),
        "total_distance_m": round(sum(row["distance_m"] for row in intervals), 1),
        "lap_indices": [row.get("lap_index") for row in intervals],
        "reps": intervals,
        "pace_mean_s_per_100m": round(mean(paces), 2),
        "pace_fastest_s_per_100m": round(min(paces), 2),
        "pace_slowest_s_per_100m": round(max(paces), 2),
        "pace_range_s_per_100m": round(max(paces) - min(paces), 2),
        "pace_first_to_last_delta_s_per_100m": round(paces[-1] - paces[0], 2),
        "average_heartrate_mean": round(mean(hrs), 1) if hrs else None,
        "recorded_rest_between_reps_s": rests,
    }


def _swim_context(activity):
    intervals = _swim_source_intervals(activity)
    groups = []

    for row in intervals:
        if (
            groups
            and _same_swim_distance(groups[-1]["distance_m"], row["distance_m"])
            and row["rest_marker_before"]
        ):
            groups[-1]["intervals"].append(row)
        else:
            groups.append({"distance_m": row["distance_m"], "intervals": [row]})

    structure = []
    repeat_sets = []
    repeat_index = 0
    for group in groups:
        reps = len(group["intervals"])
        distance = round(group["distance_m"])
        structure.append(
            {
                "repetitions": reps,
                "distance_per_rep_m": distance,
                "total_distance_m": round(sum(row["distance_m"] for row in group["intervals"]), 1),
                "lap_indices": [row.get("lap_index") for row in group["intervals"]],
            }
        )
        if reps >= 2:
            repeat_index += 1
            repeat_sets.append(_swim_repeat_set(group, repeat_index))

    source_distance = round(sum(row["distance_m"] for row in intervals), 1)
    activity_distance = _positive(activity.get("distance_m"))
    structure_signature = "+".join(
        f"{block['repetitions']}x{block['distance_per_rep_m']}"
        for block in structure
    )

    return {
        "structured": bool(repeat_sets),
        "structure_signature": structure_signature,
        "structure": structure,
        "repeat_sets": repeat_sets,
        "source_intervals": intervals,
        "source_lap_distance_sum_m": source_distance,
        "source_lap_distance_matches_activity": (
            isclose(source_distance, activity_distance, abs_tol=5.0)
            if activity_distance is not None and source_distance > 0
            else None
        ),
        "structure_basis": (
            "Equal-distance positive source laps are grouped as a repeat set only when a zero-distance lap/rest marker separates the repetitions."
        ),
        "interpretation_limits": [
            "Pace is derived deterministically from source lap time and distance.",
            "Set structure and pace stability do not by themselves prove stroke-technique quality or physiological intensity.",
            "Swimming heart rate is observed source data and is not an intensity classification by itself.",
        ],
    }


def _enduro_context(activity):
    elapsed = _positive(activity.get("elapsed_time_s"))
    moving = _positive(activity.get("moving_time_s"))
    session_duration = elapsed or moving
    non_moving = None
    if elapsed is not None and moving is not None:
        non_moving = max(0.0, elapsed - moving)

    return {
        "session_duration_s": session_duration,
        "duration_basis": "elapsed_time_s" if elapsed is not None else "moving_time_s_fallback",
        "moving_time_s": moving,
        "non_moving_time_s": non_moving,
        "duration_note": (
            "For Enduro, session_duration_s is the workout duration. Strava moving_time_s only describes time classified as moving and must not replace total session duration."
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
        "swim": _swim_context(activity) if sport_type in SWIM_TYPES else None,
        "enduro": _enduro_context(activity) if sport_type in ENDURO_TYPES else None,
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
    if run is not None:
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

        short_intervals = run.get("short_intervals") or {}
        if short_intervals.get("structured"):
            reps = short_intervals.get("reps") or []
            blocks = short_intervals.get("blocks") or []
            if len(reps) != short_intervals.get("repetition_count"):
                raise RuntimeError("Workout analysis: short-interval repetition count mismatch")
            if sum(int(block.get("repetitions") or 0) for block in blocks) != len(reps):
                raise RuntimeError("Workout analysis: short-interval block count mismatch")
            for rep in reps:
                source = by_index.get(rep.get("lap_index"))
                source_distance = _positive((source or {}).get("distance_m"))
                source_duration = (
                    _positive((source or {}).get("moving_time_s"))
                    or _positive((source or {}).get("elapsed_time_s"))
                )
                if source_distance is None or source_duration is None:
                    raise RuntimeError("Workout analysis: short interval lacks source lap")
                if not isclose(float(rep.get("distance_m")), source_distance, abs_tol=0.02):
                    raise RuntimeError("Workout analysis: short-interval distance mismatch")
                if not isclose(float(rep.get("moving_time_s")), source_duration, abs_tol=0.11):
                    raise RuntimeError("Workout analysis: short-interval duration mismatch")

    swim = context.get("swim")
    if swim is not None:
        by_index = {lap.get("lap_index"): lap for lap in activity.get("laps") or []}
        for row in swim.get("source_intervals") or []:
            source = by_index.get(row.get("lap_index"))
            expected_pace = pace_s_per_100m(
                (source or {}).get("moving_time_s") or (source or {}).get("elapsed_time_s"),
                (source or {}).get("distance_m"),
            )
            if expected_pace is None or not isclose(
                float(row.get("pace_s_per_100m")), expected_pace, abs_tol=0.02
            ):
                raise RuntimeError("Workout analysis: swim interval pace failed arithmetic validation")

        repeat_sets = swim.get("repeat_sets") or []
        if bool(repeat_sets) != bool(swim.get("structured")):
            raise RuntimeError("Workout analysis: swim structured flag mismatch")
        for repeat_set in repeat_sets:
            reps = repeat_set.get("reps") or []
            if len(reps) < 2 or repeat_set.get("repetitions") != len(reps):
                raise RuntimeError("Workout analysis: invalid swim repeat set")
            for rep in reps[1:]:
                if not rep.get("rest_marker_before"):
                    raise RuntimeError("Workout analysis: swim repeat set lacks separating rest marker")

    enduro = context.get("enduro")
    if enduro is not None:
        elapsed = _positive(activity.get("elapsed_time_s"))
        moving = _positive(activity.get("moving_time_s"))
        expected_duration = elapsed or moving
        if expected_duration is None:
            if enduro.get("session_duration_s") is not None:
                raise RuntimeError("Workout analysis: Enduro duration exists without source time")
        elif not isclose(float(enduro.get("session_duration_s")), expected_duration, abs_tol=0.01):
            raise RuntimeError("Workout analysis: Enduro session duration failed arithmetic validation")
        expected_basis = "elapsed_time_s" if elapsed is not None else "moving_time_s_fallback"
        if enduro.get("duration_basis") != expected_basis:
            raise RuntimeError("Workout analysis: Enduro duration basis mismatch")

    return True
