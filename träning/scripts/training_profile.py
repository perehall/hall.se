#!/usr/bin/env python3
"""Conservative, durable training-stimulus profiles for completed activities.

The profile separates three concepts that used to be conflated:
- observed structure: what the recorded activity proves,
- confirmed stimulus: physiology/intention supported by explicit evidence,
- planning credit: a completed activity may satisfy a nearby planned intent when
  its recorded structure matches that intent unambiguously.

Structure alone never invents a physiological label. A nearby planned-intent
match is recorded separately with its evidence and can be used to suppress a
redundant future prescription without claiming more than the data supports.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from statistics import mean, median


PROFILE_SCHEMA_VERSION = 2
RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
SWIM_TYPES = {"Swim"}
BIKE_TYPES = {"Ride", "MountainBikeRide", "VirtualRide"}
STRENGTH_TYPES = {"WeightTraining", "Workout"}
STRENGTH_UNILATERAL_WORD = re.compile(
    r"\b(bulgarian|split[ -]?squat|utfall|step[ -]?up)\w*\b",
    re.IGNORECASE,
)
CORE_WORD = re.compile(
    r"\b(pallof|dead[ -]?bug|planka|plank|atomic|trx)\w*\b",
    re.IGNORECASE,
)
MTB_TECHNICAL_WORD = re.compile(
    r"\b(stig|teknisk|teknik|flyt|linjeval|sten|berghäll)\w*\b",
    re.IGNORECASE,
)
EASY_INTENT_WORD = re.compile(
    r"\b(lugn|lugnt|väldigt lugnt|ingen fartjakt|aerob)\b",
    re.IGNORECASE,
)
DURATION_SESSION_RE = re.compile(r"(?<![×x])\b(?P<minutes>\d{2,3})\s*min\b", re.IGNORECASE)
DISTANCE_SESSION_RE = re.compile(r"\b(?P<distance>\d[\d ]{2,})\s*m\b", re.IGNORECASE)
THRESHOLD_WORD = re.compile(
    r"\b(?:[\wåäö]*trösk\w*|threshold|tempo)\b",
    re.IGNORECASE,
)
TIME_INTERVAL_REPORT = re.compile(
    r"(?P<count>\d+)\s*[x×]\s*(?P<minutes>\d+(?:[.,]\d+)?)\s*min",
    re.IGNORECASE,
)
HILL_REPORT = re.compile(
    r"(?P<sets>\d+)\s*[x×]\s*(?P<reps>\d+)\s*(?:backar|backintervaller|intervaller)\b",
    re.IGNORECASE,
)


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _activity_date(activity):
    raw = str(activity.get("start_date_local") or activity.get("start_date") or "")
    try:
        return date.fromisoformat(raw[:10])
    except (TypeError, ValueError):
        return None


def _source_payload(activity):
    laps = []
    for lap in activity.get("laps") or []:
        if not isinstance(lap, dict):
            continue
        laps.append(
            {
                "lap_index": lap.get("lap_index"),
                "distance_m": lap.get("distance_m"),
                "moving_time_s": lap.get("moving_time_s"),
                "elapsed_time_s": lap.get("elapsed_time_s"),
                "average_speed": lap.get("average_speed"),
                "average_heartrate": lap.get("average_heartrate"),
                "average_watts": lap.get("average_watts"),
            }
        )
    return {
        "id": activity.get("id"),
        "sport_type": activity.get("sport_type"),
        "classification": activity.get("classification"),
        "plan_relation": activity.get("plan_relation"),
        "user_report": str(activity.get("user_report") or "").strip(),
        "laps": laps,
    }


def activity_source_hash(activity):
    raw = json.dumps(
        _source_payload(activity),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _lap_rows(activity):
    rows = []
    for source_position, lap in enumerate(activity.get("laps") or []):
        if not isinstance(lap, dict):
            continue
        duration = _num(lap.get("moving_time_s")) or _num(lap.get("elapsed_time_s"))
        distance = _num(lap.get("distance_m"))
        if duration is None or duration <= 0 or distance is None or distance <= 0:
            continue
        speed = _num(lap.get("average_speed"))
        if speed is None or speed <= 0:
            speed = distance / duration
        rows.append(
            {
                "source_position": source_position,
                "lap_index": lap.get("lap_index"),
                "duration_s": float(duration),
                "distance_m": float(distance),
                "speed_m_s": float(speed),
                "average_heartrate": _num(lap.get("average_heartrate")),
                "average_watts": _num(lap.get("average_watts")),
            }
        )
    return rows


def _segment_summary(rows):
    if not rows:
        return None
    duration = sum(row["duration_s"] for row in rows)
    distance = sum(row["distance_m"] for row in rows)
    if duration <= 0 or distance <= 0:
        return None
    hrs = [
        row["average_heartrate"]
        for row in rows
        if isinstance(row.get("average_heartrate"), (int, float))
        and row["average_heartrate"] > 0
    ]
    watts = [
        row["average_watts"]
        for row in rows
        if isinstance(row.get("average_watts"), (int, float))
    ]
    return {
        "duration_s": round(duration, 1),
        "distance_m": round(distance, 1),
        "speed_m_s": round(distance / duration, 3),
        "average_heartrate": round(mean(hrs), 1) if hrs else None,
        "average_watts": round(mean(watts), 1) if watts else None,
        "lap_indices": [row.get("lap_index") for row in rows],
    }


def _best_edge_segment(rows, target_s, *, from_end, recovery_speed):
    if not rows:
        return None
    candidates = []
    iterator = range(len(rows)) if from_end else range(1, len(rows) + 1)
    for index in iterator:
        subset = rows[index:] if from_end else rows[:index]
        summary = _segment_summary(subset)
        if summary is None:
            continue
        tolerance = max(75.0, target_s * 0.18)
        if abs(summary["duration_s"] - target_s) > tolerance:
            continue
        if recovery_speed > 0 and summary["speed_m_s"] < recovery_speed * 1.10:
            continue
        candidates.append((abs(summary["duration_s"] - target_s), len(subset), summary))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def run_time_interval_structure(activity):
    """Detect repeated multi-minute work blocks separated by recovery laps.

    This proves timing/structure only. It deliberately does not call the work
    threshold, tempo, VO2max, or any other physiological label.
    """
    if str(activity.get("sport_type") or "") not in RUN_TYPES:
        return {"structured": False}

    rows = _lap_rows(activity)
    if len(rows) < 5:
        return {"structured": False}

    recovery_positions = []
    for index in range(1, len(rows) - 1):
        row = rows[index]
        if not 45 <= row["duration_s"] <= 180:
            continue
        previous = rows[index - 1]
        following = rows[index + 1]
        if (
            previous["speed_m_s"] >= row["speed_m_s"] * 1.12
            and following["speed_m_s"] >= row["speed_m_s"] * 1.12
        ):
            recovery_positions.append(index)

    if len(recovery_positions) < 2:
        return {"structured": False}

    # Consecutive recovery markers define complete middle work blocks. These
    # blocks establish the target duration before we inspect warm-up/cool-down
    # edges, avoiding a hard-coded 4x8/3x10 parser.
    middle = []
    for left, right in zip(recovery_positions, recovery_positions[1:]):
        segment = _segment_summary(rows[left + 1 : right])
        if segment is None or not 240 <= segment["duration_s"] <= 900:
            continue
        recovery_speed = mean([rows[left]["speed_m_s"], rows[right]["speed_m_s"]])
        if segment["speed_m_s"] < recovery_speed * 1.10:
            continue
        middle.append(segment)

    if not middle:
        return {"structured": False}

    target_s = median(row["duration_s"] for row in middle)
    recovery_rows = [rows[index] for index in recovery_positions]
    recovery_speed = mean(row["speed_m_s"] for row in recovery_rows)

    first = _best_edge_segment(
        rows[: recovery_positions[0]],
        target_s,
        from_end=True,
        recovery_speed=recovery_speed,
    )
    last = _best_edge_segment(
        rows[recovery_positions[-1] + 1 :],
        target_s,
        from_end=False,
        recovery_speed=recovery_speed,
    )
    if first is None or last is None:
        return {"structured": False}

    work = [first, *middle, last]
    if len(work) != len(recovery_positions) + 1 or len(work) < 3:
        return {"structured": False}

    work_target = median(row["duration_s"] for row in work)
    work_tolerance = max(75.0, work_target * 0.18)
    if any(abs(row["duration_s"] - work_target) > work_tolerance for row in work):
        return {"structured": False}

    recovery_durations = [row["duration_s"] for row in recovery_rows]
    recovery_target = median(recovery_durations)
    recovery_tolerance = max(30.0, recovery_target * 0.40)
    if any(abs(value - recovery_target) > recovery_tolerance for value in recovery_durations):
        return {"structured": False}

    return {
        "structured": True,
        "repetitions": len(work),
        "representative_work_duration_s": round(work_target, 1),
        "representative_recovery_duration_s": round(recovery_target, 1),
        "total_work_s": round(sum(row["duration_s"] for row in work), 1),
        "work_blocks": work,
        "recovery_lap_indices": [row.get("lap_index") for row in recovery_rows],
        "detection_basis": (
            "Repeated multi-minute faster blocks separated by locally slower "
            "45–180 s recovery laps; edge blocks are selected against the "
            "duration established by complete middle blocks."
        ),
        "interpretation_limits": [
            "The structure does not by itself establish physiological intensity.",
            "A threshold/tempo/VO2 label requires explicit evidence or an unambiguous nearby planned-intent match.",
        ],
    }


def _planned_time_interval_shape(workout):
    device = workout.get("device_workout") or {}
    blocks = device.get("blocks") or []
    matches = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        repetitions = int(block.get("repetitions_per_set") or 0)
        sets = int(block.get("sets") or 1)
        if repetitions < 2 or sets < 1:
            continue
        work = None
        recovery = None
        for step in block.get("steps") or []:
            if not isinstance(step, dict):
                continue
            duration = step.get("duration") or {}
            if duration.get("kind") != "time":
                continue
            seconds = _num(duration.get("seconds"))
            if seconds is None or seconds <= 0:
                continue
            if step.get("kind") == "work":
                work = seconds
            elif step.get("kind") == "recovery":
                recovery = seconds
        if work and recovery:
            matches.append(
                {
                    "repetitions": repetitions * sets,
                    "work_duration_s": float(work),
                    "recovery_duration_s": float(recovery),
                }
            )
    return matches[0] if len(matches) == 1 else None


def _run_plan_match(activity, workout, observed):
    if str(activity.get("sport_type") or "") not in RUN_TYPES:
        return None
    if str(workout.get("sport") or "").lower() != "run":
        return None
    if not observed.get("structured"):
        return None
    expected = _planned_time_interval_shape(workout)
    if not expected:
        return None

    if observed["repetitions"] != expected["repetitions"]:
        return None
    work_tolerance = max(60.0, expected["work_duration_s"] * 0.12)
    recovery_tolerance = max(30.0, expected["recovery_duration_s"] * 0.35)
    if abs(observed["representative_work_duration_s"] - expected["work_duration_s"]) > work_tolerance:
        return None
    if abs(observed["representative_recovery_duration_s"] - expected["recovery_duration_s"]) > recovery_tolerance:
        return None

    return {
        "expected": expected,
        "observed": {
            "repetitions": observed["repetitions"],
            "representative_work_duration_s": observed["representative_work_duration_s"],
            "representative_recovery_duration_s": observed["representative_recovery_duration_s"],
            "total_work_s": observed["total_work_s"],
        },
    }


def _activity_discipline(activity):
    sport = str(activity.get("sport_type") or "")
    if sport in RUN_TYPES:
        return "run"
    if sport in SWIM_TYPES:
        return "swim"
    if sport in BIKE_TYPES:
        return "bike"
    if sport in STRENGTH_TYPES:
        return "strength"
    if sport == "Enduro":
        return "enduro"
    return ""


def _planned_scalar_target(workout):
    sport = str(workout.get("sport") or "").lower()
    session = str(workout.get("session") or "")
    stimuli = set(str(value) for value in (workout.get("stimuli") or []))

    if sport == "swim":
        match = DISTANCE_SESSION_RE.search(session)
        if match:
            return "distance_m", float(match.group("distance").replace(" ", ""))
        return None

    if sport == "run" and stimuli.intersection({"run_threshold", "run_hill_quality"}):
        return None

    if sport in {"run", "bike", "strength"}:
        matches = list(DURATION_SESSION_RE.finditer(session))
        if len(matches) == 1:
            return "duration_minutes", float(matches[0].group("minutes"))
    return None


def _actual_scalar(activity, metric):
    if metric == "distance_m":
        value = _num(activity.get("distance_m"))
        return value if value is not None and value > 0 else None
    if metric == "duration_minutes":
        value = _num(activity.get("elapsed_time_s"))
        if value is None:
            value = _num(activity.get("moving_time_s"))
        return value / 60.0 if value is not None and value > 0 else None
    return None


def _scalar_plan_match(activity, workout):
    activity_discipline = _activity_discipline(activity)
    workout_discipline = str(workout.get("sport") or "").lower()
    if activity_discipline != workout_discipline:
        return None

    target = _planned_scalar_target(workout)
    if target is None:
        return None
    metric, expected = target
    observed = _actual_scalar(activity, metric)
    if observed is None or expected <= 0:
        return None

    relative_error = abs(observed - expected) / expected
    limit = 0.10 if metric == "distance_m" else 0.22
    absolute_ok = (
        abs(observed - expected) <= 150.0
        if metric == "distance_m"
        else abs(observed - expected) <= 15.0
    )
    if relative_error > limit and not absolute_ok:
        return None

    return {
        "metric": metric,
        "expected_value": round(expected, 2),
        "observed_value": round(observed, 2),
        "relative_error": round(relative_error, 4),
        "matching_basis": "same_discipline_and_comparable_planned_dose",
    }


def _workout_key(workout):
    explicit = str(workout.get("workout_key") or "").strip()
    if explicit:
        return explicit
    micro = str(workout.get("microcycle_id") or "").strip()
    date_value = str(workout.get("date") or "").strip()
    slot = str(workout.get("microcycle_slot") or "").strip()
    return f"{micro}:{date_value}:{slot}" if micro and date_value and slot else ""


def nearby_structural_intent_matches(activity, planned_workouts, observed, confirmed_stimuli=()):
    activity_day = _activity_date(activity)
    if activity_day is None or activity.get("plan_relation") == "separate":
        return []

    candidates = []
    for workout in planned_workouts or []:
        if not isinstance(workout, dict):
            continue
        try:
            workout_day = date.fromisoformat(str(workout.get("date") or ""))
        except ValueError:
            continue
        day_delta = (workout_day - activity_day).days
        if abs(day_delta) > 3:
            continue

        evidence = _run_plan_match(activity, workout, observed)
        basis = "run_interval_structure"
        if evidence is None:
            # Scalar dose alone is weak evidence. It may recover the intent of
            # a same-day planned session, but it must not bridge calendar days.
            # A moved session needs explicit capability evidence or a stronger
            # structural match.
            if day_delta != 0:
                continue
            evidence = _scalar_plan_match(activity, workout)
            basis = "same_day_comparable_scalar_dose"
        if evidence is None:
            continue

        stimuli = [str(value) for value in (workout.get("stimuli") or []) if str(value)]
        if not stimuli:
            continue
        confirmed = {str(value) for value in confirmed_stimuli if str(value)}
        if confirmed and confirmed.isdisjoint(stimuli):
            continue
        dose_error = float(evidence.get("relative_error") or 0.0)
        candidates.append(
            {
                "workout_key": _workout_key(workout),
                "target_date": workout_day.isoformat(),
                "day_delta": day_delta,
                "stimuli": stimuli,
                "relation": "fulfills_planned_dose",
                "confidence": "high",
                "evidence": {**evidence, "basis": basis},
                "_rank": (abs(day_delta), dose_error),
            }
        )

    if not candidates:
        return []

    structural = [
        row for row in candidates
        if (row.get("evidence") or {}).get("basis") == "run_interval_structure"
    ]
    # Repeated interval shapes can be structurally identical across multiple
    # nearby planned days. Calendar proximity alone is not enough to claim
    # which physiological intent the activity fulfilled.
    if len(structural) > 1:
        return []
    if len(structural) == 1:
        result = dict(structural[0])
        result.pop("_rank", None)
        return [result]

    candidates.sort(key=lambda row: (row["_rank"], row["workout_key"]))
    best_rank = candidates[0]["_rank"]
    best = [row for row in candidates if row["_rank"] == best_rank]
    # Scalar dose matching may use date/dose closeness only when exactly one
    # candidate is best. Equal candidates remain ambiguous.
    if len(best) != 1:
        return []
    result = dict(best[0])
    result.pop("_rank", None)
    return [result]


def _explicit_stimuli(activity):
    report = str(activity.get("user_report") or "").strip()
    lower = report.lower()
    sport_type = str(activity.get("sport_type") or "")
    result = []

    def duration_minutes():
        value = _num(activity.get("elapsed_time_s"))
        if value is None:
            value = _num(activity.get("moving_time_s"))
        return round(value / 60.0, 1) if value is not None and value > 0 else None

    if sport_type in RUN_TYPES:
        match = TIME_INTERVAL_REPORT.search(report)
        if match and THRESHOLD_WORD.search(report):
            count = int(match.group("count"))
            minutes = float(match.group("minutes").replace(",", "."))
            result.append(
                {
                    "key": "run_threshold",
                    "status": "confirmed",
                    "confidence": "high",
                    "source": "explicit_user_report",
                    "dose": {
                        "protocol": f"{count}x{minutes:g}min",
                        "work_minutes": round(count * minutes, 1),
                    },
                }
            )
        hill = HILL_REPORT.search(report)
        if hill and "back" in lower:
            sets = int(hill.group("sets"))
            reps = int(hill.group("reps"))
            result.append(
                {
                    "key": "run_hill_quality",
                    "status": "confirmed",
                    "confidence": "high",
                    "source": "explicit_user_report",
                    "dose": {
                        "protocol": f"{sets}x{reps}",
                        "repetitions": sets * reps,
                    },
                }
            )
        if (
            not THRESHOLD_WORD.search(report)
            and "back" not in lower
            and (
                "lugn distans" in lower
                or "väldigt lugnt" in lower
                or "hålla pulsen runt" in lower
            )
        ):
            result.append(
                {
                    "key": "run_easy_distance",
                    "status": "confirmed",
                    "confidence": "high",
                    "source": "explicit_user_report",
                    "dose": {"duration_minutes": duration_minutes()},
                }
            )

    if sport_type in SWIM_TYPES:
        if "trösk" in lower or "threshold" in lower:
            result.append(
                {
                    "key": "swim_threshold",
                    "status": "confirmed",
                    "confidence": "high",
                    "source": "explicit_user_report",
                    "dose": {
                        "distance_m": _num(activity.get("distance_m")),
                    },
                }
            )

    if sport_type in BIKE_TYPES and report:
        if MTB_TECHNICAL_WORD.search(report):
            result.append(
                {
                    "key": "mtb_technical",
                    "status": "confirmed",
                    "confidence": "high",
                    "source": "explicit_user_report",
                    "dose": {"duration_minutes": duration_minutes()},
                }
            )
        if sport_type == "MountainBikeRide" and EASY_INTENT_WORD.search(report):
            result.append(
                {
                    "key": "mtb_aerobic",
                    "status": "confirmed",
                    "confidence": "high",
                    "source": "explicit_user_report",
                    "dose": {"duration_minutes": duration_minutes()},
                }
            )

    if sport_type in STRENGTH_TYPES and report:
        if STRENGTH_UNILATERAL_WORD.search(report):
            result.append(
                {
                    "key": "strength_unilateral",
                    "status": "confirmed",
                    "confidence": "high",
                    "source": "explicit_user_report",
                    "dose": {"duration_minutes": duration_minutes()},
                }
            )
        if CORE_WORD.search(report):
            result.append(
                {
                    "key": "strength_core",
                    "status": "confirmed",
                    "confidence": "high",
                    "source": "explicit_user_report",
                    "dose": {"duration_minutes": duration_minutes()},
                }
            )

    return result


def explicit_confirmed_stimuli(activity):
    """Return only stimuli supported directly by the activity/user report.

    This public boundary deliberately excludes plan matching and performance
    fingerprints so consumers can use fresh canonical feedback without
    importing legacy calendar intent.
    """

    return tuple(dict(item) for item in _explicit_stimuli(activity))


def build_training_profile(
    activity,
    *,
    planned_workouts=(),
    performance_entry=None,
    previous_profile=None,
):
    source_hash = activity_source_hash(activity)
    observed = {
        "run_time_intervals": run_time_interval_structure(activity),
    }

    stimuli = _explicit_stimuli(activity)
    if (
        isinstance(performance_entry, dict)
        and performance_entry.get("marker_id") == "run-threshold-control"
    ):
        if not any(row["key"] == "run_threshold" for row in stimuli):
            summary = performance_entry.get("summary") or {}
            stimuli.append(
                {
                    "key": "run_threshold",
                    "status": "confirmed",
                    "confidence": "high",
                    "source": "performance_fingerprint",
                    "dose": {
                        "protocol": performance_entry.get("protocol_key"),
                        "work_minutes": (
                            round(float(summary["total_work_s"]) / 60.0, 1)
                            if isinstance(summary.get("total_work_s"), (int, float))
                            else None
                        ),
                    },
                }
            )

    durable_matches = []
    if (
        isinstance(previous_profile, dict)
        and previous_profile.get("schema_version") == PROFILE_SCHEMA_VERSION
        and previous_profile.get("source_hash") == source_hash
    ):
        durable_matches = [
            dict(row)
            for row in (previous_profile.get("intent_matches") or [])
            if isinstance(row, dict)
            and row.get("relation") == "fulfills_planned_dose"
            and row.get("confidence") == "high"
        ]

    fresh_matches = nearby_structural_intent_matches(
        activity,
        planned_workouts,
        observed["run_time_intervals"],
        confirmed_stimuli=[
            row["key"]
            for row in stimuli
            if row.get("status") == "confirmed" and row.get("key")
        ],
    )
    keyed = {}
    for row in [*durable_matches, *fresh_matches]:
        identity = (
            str(row.get("workout_key") or ""),
            tuple(sorted(str(value) for value in (row.get("stimuli") or []))),
        )
        keyed[identity] = row
    intent_matches = list(keyed.values())

    confirmed = {row["key"] for row in stimuli if row.get("status") == "confirmed"}
    planning_credits = set(confirmed)
    for row in intent_matches:
        if row.get("confidence") == "high" and row.get("relation") == "fulfills_planned_dose":
            planning_credits.update(str(value) for value in row.get("stimuli") or [])

    uncertainties = []
    if (
        observed["run_time_intervals"].get("structured")
        and not stimuli
        and not intent_matches
    ):
        uncertainties.append(
            "Intervallstruktur observerad men fysiologiskt stimulus kan inte fastställas från tillgänglig evidens."
        )

    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "activity_id": activity.get("id"),
        "source_hash": source_hash,
        "observed_structure": observed,
        "stimuli": stimuli,
        "intent_matches": intent_matches,
        "planning_credits": sorted(planning_credits),
        "uncertainties": uncertainties,
        "interpretation_boundary": (
            "Observerad struktur är mätdata. Fysiologiska stimulus kräver explicit evidens. "
            "Planning credit från strukturell intent-match betyder att den genomförda dosen "
            "kan ersätta ett entydigt närliggande planerat pass; det påstår inte mer om "
            "fysiologisk intensitet än källorna stödjer."
        ),
    }
