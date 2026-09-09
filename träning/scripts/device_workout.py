#!/usr/bin/env python3
"""Compile selected workout designs into device-neutral structured workouts.

`workout_design.selected_candidate` is the single source of truth. This module
contains no Garmin/Intervals business logic beyond provider type names: it
creates a stable, transport-neutral workout representation that adapters can
serialize without inventing training targets or doses.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any


DEVICE_WORKOUT_SCHEMA_VERSION = 1
SUPPORTED_SPORTS = {"swim": "Swim", "run": "Run", "bike": "Ride"}
SYNCABLE_STATUSES = {"planned", "preliminary", "conditional"}


class DeviceWorkoutError(RuntimeError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")
    return value or "workout"


def selected_candidate(day: dict) -> dict:
    design = day.get("workout_design") or {}
    selected_id = _text(design.get("selected_candidate_id"))
    return next(
        (
            item
            for item in (design.get("candidates") or [])
            if _text(item.get("id")) == selected_id
        ),
        {},
    )


def _primary_target(block: dict) -> dict | None:
    """Return an explicit single target, never infer one from intensity text."""
    raw = block.get("target") or (block.get("work") or {}).get("target")
    if raw in (None, "", {}):
        return None
    if not isinstance(raw, dict):
        raise DeviceWorkoutError("device_workout: target måste vara objekt")
    target_type = _text(raw.get("type"))
    if target_type not in {"pace", "heart_rate", "power"}:
        raise DeviceWorkoutError(f"device_workout: unsupported target type {target_type!r}")
    value = raw.get("value")
    start = raw.get("start")
    end = raw.get("end")
    if value is None and (start is None or end is None):
        raise DeviceWorkoutError("device_workout: target kräver value eller start/end")
    result = {"type": target_type}
    if value is not None:
        result["value"] = value
    else:
        result["start"] = start
        result["end"] = end
    unit = _text(raw.get("unit"))
    if unit:
        result["unit"] = unit
    return result


def _intensity_class(block: dict, *, recovery: bool = False) -> str:
    if recovery:
        return "recovery"
    raw = _text(block.get("intensity")).lower()
    if raw in {"warmup", "cooldown", "recovery"}:
        return raw
    if raw in {"active", "interval", "kontrollerad tröskel", "kraftfull men kontrollerad"}:
        return "interval"
    if raw in {"lugn", "lugn aerob/teknisk", "enligt passrubrik"}:
        return "active"
    return "active"


def _work_step(block: dict) -> dict:
    work = block.get("work") or {}
    duration_s = work.get("duration_s")
    distance_m = work.get("distance_m")
    if isinstance(duration_s, (int, float)) and duration_s > 0:
        duration = {"kind": "time", "seconds": int(duration_s)}
    elif isinstance(distance_m, (int, float)) and distance_m > 0:
        duration = {"kind": "distance", "meters": int(distance_m)}
    else:
        raise DeviceWorkoutError(
            f"device_workout: block {_text(block.get('name'))!r} saknar tid eller distans"
        )

    step = {
        "kind": "work",
        "duration": duration,
        "instruction": _text(block.get("instruction")) or _text(block.get("name")),
        "intensity_class": _intensity_class(block),
    }
    target = _primary_target(block)
    if target:
        step["target"] = target
    return step


def _recovery_step(block: dict) -> dict | None:
    recovery = block.get("recovery")
    if not isinstance(recovery, dict) or not recovery:
        return None
    duration_s = recovery.get("duration_s")
    instruction = _text(recovery.get("instruction")) or "Vila"
    if isinstance(duration_s, (int, float)) and duration_s > 0:
        duration = {"kind": "time", "seconds": int(duration_s)}
        press_lap = False
        transport_reference_only = False
    else:
        # The prescription explicitly says recovery is self-paced (e.g. jog back
        # down). Garmin represents that naturally as lap-press. Intervals.icu's
        # supported text syntax requires a nominal time token even for Press lap;
        # 1 second is therefore a transport placeholder, not a training dose.
        duration = {"kind": "time", "seconds": 1}
        press_lap = True
        transport_reference_only = True

    return {
        "kind": "recovery",
        "duration": duration,
        "instruction": instruction,
        "intensity_class": "recovery",
        "press_lap": press_lap,
        "transport_reference_only": transport_reference_only,
    }


def _compile_block(block: dict) -> dict:
    work = block.get("work") or {}
    repetitions = int(work.get("repetitions") or 1)
    sets = int(work.get("sets") or 1)
    reps_per_set = int(work.get("repetitions_per_set") or repetitions)
    if repetitions < 1 or sets < 1 or reps_per_set < 1:
        raise DeviceWorkoutError("device_workout: repetitioner/set måste vara >= 1")

    result = {
        "name": _text(block.get("name")) or "Passdel",
        "sets": sets,
        "repetitions_per_set": reps_per_set,
        "steps": [_work_step(block)],
    }
    recovery = _recovery_step(block)
    if recovery:
        result["steps"].append(recovery)
    return result


def _stable_external_id(day: dict) -> str:
    slot = _text(day.get("microcycle_slot")) or _text(day.get("sport"))
    return f"hall-device:{day.get('date')}:{_slug(_text(day.get('sport')))}:{_slug(slot)}"


def _source_hash(day: dict, candidate: dict, blocks: list[dict]) -> str:
    payload = {
        "date": day.get("date"),
        "sport": day.get("sport"),
        "candidate_id": candidate.get("id"),
        "session": candidate.get("session"),
        "blocks": blocks,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def compile_device_workout(day: dict) -> dict:
    sport = _text(day.get("sport"))
    if sport not in SUPPORTED_SPORTS:
        raise DeviceWorkoutError(f"device_workout: sport {sport!r} stöds inte")
    if day.get("status") not in SYNCABLE_STATUSES:
        raise DeviceWorkoutError(
            f"device_workout: status {day.get('status')!r} är inte synkbar"
        )

    candidate = selected_candidate(day)
    if not candidate:
        raise DeviceWorkoutError("device_workout: vald workout-kandidat saknas")
    prescription = candidate.get("prescription") or {}
    if prescription.get("executable") is not True or prescription.get("completeness") != "full":
        raise DeviceWorkoutError("device_workout: vald kandidat saknar full exekverbar prescription")
    source_blocks = prescription.get("blocks") or []
    if not source_blocks:
        raise DeviceWorkoutError("device_workout: vald kandidat saknar block")

    blocks = [_compile_block(block) for block in source_blocks]
    source_hash = _source_hash(day, candidate, blocks)
    session = _text(candidate.get("session")) or _text(day.get("session"))
    return {
        "schema_version": DEVICE_WORKOUT_SCHEMA_VERSION,
        "external_id": _stable_external_id(day),
        "date": day.get("date"),
        "sport": sport,
        "provider_type": SUPPORTED_SPORTS[sport],
        "name": session[:120],
        "source_candidate_id": _text(candidate.get("id")),
        "source_hash": source_hash,
        "blocks": blocks,
        "target_policy": "explicit_single_primary_only",
        "transport": "intervals_icu",
    }


def validate_device_workout(workout: dict, context: str) -> bool:
    if not isinstance(workout, dict):
        raise DeviceWorkoutError(f"{context}: device_workout måste vara objekt")
    if workout.get("schema_version") != DEVICE_WORKOUT_SCHEMA_VERSION:
        raise DeviceWorkoutError(f"{context}: device_workout schema_version ogiltig")
    if workout.get("sport") not in SUPPORTED_SPORTS:
        raise DeviceWorkoutError(f"{context}: unsupported device sport")
    if workout.get("provider_type") != SUPPORTED_SPORTS[workout["sport"]]:
        raise DeviceWorkoutError(f"{context}: provider_type matchar inte sport")
    for key in ("external_id", "date", "name", "source_candidate_id", "source_hash"):
        if not _text(workout.get(key)):
            raise DeviceWorkoutError(f"{context}: {key} saknas")
    if not _text(workout.get("external_id")).startswith("hall-device:"):
        raise DeviceWorkoutError(f"{context}: external_id har fel namespace")
    blocks = workout.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise DeviceWorkoutError(f"{context}: blocks saknas")
    for block_index, block in enumerate(blocks):
        if int(block.get("sets") or 0) < 1 or int(block.get("repetitions_per_set") or 0) < 1:
            raise DeviceWorkoutError(f"{context}.blocks[{block_index}]: ogiltig repetitionsstruktur")
        steps = block.get("steps")
        if not isinstance(steps, list) or not steps:
            raise DeviceWorkoutError(f"{context}.blocks[{block_index}]: steps saknas")
        for step_index, step in enumerate(steps):
            if step.get("kind") not in {"work", "recovery"}:
                raise DeviceWorkoutError(
                    f"{context}.blocks[{block_index}].steps[{step_index}]: ogiltig kind"
                )
            duration = step.get("duration") or {}
            if duration.get("kind") == "time":
                if int(duration.get("seconds") or 0) <= 0:
                    raise DeviceWorkoutError(f"{context}: step time måste vara > 0")
            elif duration.get("kind") == "distance":
                if int(duration.get("meters") or 0) <= 0:
                    raise DeviceWorkoutError(f"{context}: step distance måste vara > 0")
            else:
                raise DeviceWorkoutError(f"{context}: step duration-kind ogiltig")
            target = step.get("target")
            if target is not None:
                if not isinstance(target, dict) or target.get("type") not in {
                    "pace",
                    "heart_rate",
                    "power",
                }:
                    raise DeviceWorkoutError(f"{context}: step target ogiltigt")
    return True


def materialize_day(day: dict, *, in_horizon: bool) -> dict:
    result = copy.deepcopy(day)
    sport = _text(result.get("sport"))
    status = result.get("status")
    if sport not in SUPPORTED_SPORTS or status not in SYNCABLE_STATUSES:
        result.pop("device_workout", None)
        result.pop("device_sync", None)
        return result

    workout = compile_device_workout(result)
    previous_sync = result.get("device_sync") or {}
    same_source = previous_sync.get("source_hash") == workout["source_hash"]
    if not in_horizon:
        sync = {
            "status": "deferred",
            "transport": "intervals_icu",
            "source_hash": workout["source_hash"],
            "device_delivery": "unverified",
        }
    elif same_source and previous_sync.get("status") == "synced":
        sync = copy.deepcopy(previous_sync)
    else:
        sync = {
            "status": "pending",
            "transport": "intervals_icu",
            "source_hash": workout["source_hash"],
            "device_delivery": "unverified",
        }
    result["device_workout"] = workout
    result["device_sync"] = sync
    return result
