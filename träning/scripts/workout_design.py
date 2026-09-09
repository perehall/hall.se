#!/usr/bin/env python3
"""Deterministic workout design layer.

The calendar plan decides *which stimulus* belongs on a day. This module turns
that decision into ranked, executable workout candidates and keeps the selected
prescription explicitly linked to goal/mesocycle/microcycle context.

It deliberately does not invent physiological thresholds or recovery claims.
Near-term AI may only move the plan to an already approved dose option; after
that change this module is rerun and materializes the matching prescription.
"""

from __future__ import annotations

import copy
import re
from typing import Any


WORKOUT_DESIGN_SCHEMA_VERSION = 1
MAX_CANDIDATES = 4

ROLE_ORDER = (
    "primary",
    "secondary",
    "maintenance",
    "protected_capacity",
    "external_load",
)

THRESHOLD_RE = re.compile(
    r"(?P<reps>\d+)\s*[×x]\s*(?P<minutes>\d+)\s*min\s*/\s*(?P<rest>\d+)\s*s",
    re.IGNORECASE,
)
HILL_NESTED_RE = re.compile(
    r"(?P<sets>\d+)\s*[×x]\s*(?P<reps>\d+)\s*[×x]\s*(?P<meters>\d+)\s*m",
    re.IGNORECASE,
)
HILL_SIMPLE_RE = re.compile(
    r"(?P<reps>\d+)\s*[×x]\s*(?P<meters>\d+)\s*m",
    re.IGNORECASE,
)
DURATION_RE = re.compile(r"\b(?P<minutes>\d+)\s*min\b", re.IGNORECASE)


class WorkoutDesignError(RuntimeError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mesocycle_role(day: dict, strategy: dict) -> str:
    stimuli = set(day.get("stimuli") or [])
    contract = ((strategy.get("current_mesocycle") or {}).get("contract") or {})
    for role in ROLE_ORDER:
        if stimuli.intersection(contract.get(role) or []):
            return role
    return "unclassified"


def _preferred_option_id(day: dict) -> str:
    resolution = day.get("dose_resolution") or {}
    resolved = _text(resolution.get("option_id"))
    if resolved:
        return resolved
    step = day.get("development_step") or {}
    planned = _text(step.get("option_id"))
    if planned:
        return planned
    return _text(day.get("baseline_option_id"))


def _candidate_options(day: dict) -> list[dict]:
    options = [copy.deepcopy(item) for item in (day.get("dose_options") or [])]
    if not options:
        return [
            {
                "id": "current-session",
                "kind": "external" if day.get("manual_lock") else "structured",
                "value": 1,
                "session": day.get("session") or "",
                "intent": day.get("reason") or "",
            }
        ]

    preferred_id = _preferred_option_id(day)
    preferred = next((item for item in options if item.get("id") == preferred_id), None)
    if preferred is None:
        preferred = options[0]
        preferred_id = _text(preferred.get("id"))

    preferred_value = preferred.get("value")
    if isinstance(preferred_value, (int, float)):
        others = sorted(
            [item for item in options if item.get("id") != preferred_id],
            key=lambda item: (
                abs(float(item.get("value", preferred_value)) - float(preferred_value))
                if isinstance(item.get("value"), (int, float))
                else float("inf"),
                _text(item.get("id")),
            ),
        )
    else:
        others = [item for item in options if item.get("id") != preferred_id]

    return [preferred, *others][:MAX_CANDIDATES]


def _swim_prescription(day: dict, option: dict) -> dict:
    workout = day.get("watch_workout") or {}
    planned_distance = workout.get("planned_distance_m")
    option_value = option.get("value")

    # A structured swim recipe is only valid for the dose it was authored for.
    if not workout or not workout.get("blocks"):
        return {
            "executable": False,
            "completeness": "partial",
            "blocks": [],
            "missing": ["structured_swim_blocks"],
        }
    if isinstance(option_value, (int, float)) and planned_distance is not None:
        if int(option_value) != int(planned_distance):
            return {
                "executable": False,
                "completeness": "partial",
                "blocks": [],
                "missing": ["structured_swim_blocks_for_candidate_dose"],
            }

    blocks = []
    total_distance = 0
    for source_block in workout.get("blocks") or []:
        repeat = int(source_block.get("repeat", 1) or 1)
        steps = source_block.get("steps") or []
        rest_s = next(
            (
                int(step.get("duration_s"))
                for step in steps
                if step.get("kind") == "rest" and step.get("duration_s")
            ),
            None,
        )
        for step in steps:
            if step.get("kind") != "swim":
                continue
            distance_m = int(step.get("distance_m") or 0)
            if distance_m <= 0:
                continue
            total = repeat * distance_m
            total_distance += total
            block = {
                "name": _text(source_block.get("name")) or "Simning",
                "work": {
                    "repetitions": repeat,
                    "distance_m": distance_m,
                    "total_distance_m": total,
                },
                "instruction": _text(step.get("text")) or _text(source_block.get("name")),
                "intensity": _text(step.get("intensity")) or "unspecified",
            }
            if rest_s is not None:
                block["recovery"] = {"duration_s": rest_s}
            blocks.append(block)

    if planned_distance is not None and total_distance != int(planned_distance):
        return {
            "executable": False,
            "completeness": "partial",
            "blocks": blocks,
            "missing": ["distance_consistency"],
        }

    return {
        "executable": bool(blocks),
        "completeness": "full" if blocks else "partial",
        "total_distance_m": total_distance,
        "blocks": blocks,
        "source": "watch_workout",
    }


def _run_prescription(day: dict, option: dict) -> dict:
    session = _text(option.get("session")) or _text(day.get("session"))
    blocks: list[dict] = []

    threshold = THRESHOLD_RE.search(session)
    if threshold:
        reps = int(threshold.group("reps"))
        minutes = int(threshold.group("minutes"))
        rest_s = int(threshold.group("rest"))
        blocks.append(
            {
                "name": "Arbetsdel",
                "work": {
                    "repetitions": reps,
                    "duration_s": minutes * 60,
                    "total_work_s": reps * minutes * 60,
                },
                "instruction": "Kontrollerad tröskel",
                "intensity": "kontrollerad tröskel",
                "recovery": {"duration_s": rest_s, "instruction": "Lugn jogg"},
            }
        )
        return {
            "executable": True,
            "completeness": "full",
            "blocks": blocks,
            "source": "structured_session",
        }

    nested = HILL_NESTED_RE.search(session)
    simple = None if nested else HILL_SIMPLE_RE.search(session)
    hill = nested or simple
    if hill:
        warmup = re.search(r"^\D*(?P<minutes>\d+)\s*min\s+lugnt\s*\+", session, re.IGNORECASE)
        cooldown = re.search(r"\+\s*(?P<minutes>\d+)\s*min\s+lugnt\s*$", session, re.IGNORECASE)
        if warmup:
            blocks.append(
                {
                    "name": "Uppvärmning",
                    "work": {"duration_s": int(warmup.group("minutes")) * 60},
                    "instruction": "Lugnt",
                    "intensity": "lugn",
                }
            )

        if nested:
            sets = int(nested.group("sets"))
            reps_per_set = int(nested.group("reps"))
            meters = int(nested.group("meters"))
            total_reps = sets * reps_per_set
            work = {
                "sets": sets,
                "repetitions_per_set": reps_per_set,
                "total_repetitions": total_reps,
                "distance_m": meters,
                "total_work_distance_m": total_reps * meters,
            }
        else:
            reps = int(simple.group("reps"))
            meters = int(simple.group("meters"))
            work = {
                "repetitions": reps,
                "distance_m": meters,
                "total_work_distance_m": reps * meters,
            }

        recovery_instruction = (
            "Full lugn nedjogg"
            if "full lugn nedjogg" in session.lower()
            else "Lugn joggvila"
        )
        blocks.append(
            {
                "name": "Backkvalitet",
                "work": work,
                "instruction": _text(day.get("development_focus")) or "Kontrollerad backkvalitet",
                "intensity": "kraftfull men kontrollerad",
                "recovery": {"instruction": recovery_instruction},
            }
        )
        if cooldown:
            blocks.append(
                {
                    "name": "Nedjogg",
                    "work": {"duration_s": int(cooldown.group("minutes")) * 60},
                    "instruction": "Lugnt",
                    "intensity": "lugn",
                }
            )
        return {
            "executable": True,
            "completeness": "full",
            "blocks": blocks,
            "source": "structured_session",
        }

    duration = DURATION_RE.search(session)
    if duration:
        minutes = int(duration.group("minutes"))
        blocks.append(
            {
                "name": "Pass",
                "work": {"duration_s": minutes * 60},
                "instruction": _text(day.get("development_focus")) or session,
                "intensity": "lugn" if "lugn" in session.lower() else "enligt passrubrik",
            }
        )
        return {
            "executable": True,
            "completeness": "full",
            "blocks": blocks,
            "source": "duration_session",
        }

    return {
        "executable": False,
        "completeness": "partial",
        "blocks": [],
        "missing": ["structured_run_dose"],
    }


def _bike_prescription(day: dict, option: dict) -> dict:
    session = _text(option.get("session")) or _text(day.get("session"))
    duration = DURATION_RE.search(session)
    if not duration:
        return {
            "executable": False,
            "completeness": "partial",
            "blocks": [],
            "missing": ["duration"],
        }
    minutes = int(duration.group("minutes"))
    return {
        "executable": True,
        "completeness": "full",
        "blocks": [
            {
                "name": "MTB/XC",
                "work": {"duration_s": minutes * 60},
                "instruction": _text(day.get("development_focus")) or session,
                "intensity": "lugn aerob/teknisk" if "lugn" in session.lower() else "enligt passrubrik",
            }
        ],
        "source": "duration_session",
    }


def _strength_prescription(day: dict, option: dict, document: dict) -> dict:
    session = _text(option.get("session")) or _text(day.get("session"))
    duration = DURATION_RE.search(session)
    template = [str(item).strip() for item in (document.get("strength_template") or []) if str(item).strip()]
    blocks = []
    if duration:
        blocks.append(
            {
                "name": "Tidsram",
                "work": {"duration_s": int(duration.group("minutes")) * 60},
                "instruction": "Styrka/core inom vald tidsram",
                "intensity": "kontrollerad",
            }
        )
    for item in template:
        blocks.append(
            {
                "name": "Styrkemall",
                "work": {},
                "instruction": item,
                "intensity": "enligt styrkemall",
            }
        )
    return {
        "executable": bool(duration and template),
        # The global strength template does not yet encode sets/reps/load.
        "completeness": "partial",
        "blocks": blocks,
        "missing": ["exercise_sets_reps_load"],
        "source": "strength_template",
    }


def _external_prescription(day: dict) -> dict:
    return {
        "executable": True,
        "completeness": "external",
        "blocks": [
            {
                "name": "Fast/externt strukturerat pass",
                "work": {},
                "instruction": _text(day.get("development_focus")) or _text(day.get("session")),
                "intensity": "extern struktur",
            }
        ],
        "source": "external_commitment",
    }


def _prescription(day: dict, option: dict, document: dict) -> dict:
    if day.get("manual_lock") is True or day.get("classification") == "recreation":
        return _external_prescription(day)
    sport = day.get("sport")
    if sport == "swim":
        return _swim_prescription(day, option)
    if sport == "run":
        return _run_prescription(day, option)
    if sport == "bike":
        return _bike_prescription(day, option)
    if sport == "strength":
        return _strength_prescription(day, option, document)
    if sport in {"enduro", "swimrun"}:
        return _external_prescription(day)
    return {
        "executable": False,
        "completeness": "partial",
        "blocks": [],
        "missing": ["unsupported_sport_prescription"],
    }


def _score_candidate(day: dict, option: dict, prescription: dict, role: str) -> dict:
    option_id = _text(option.get("id"))
    preferred = _preferred_option_id(day)
    step = day.get("development_step") or {}
    planned_step_id = _text(step.get("option_id"))
    progression = day.get("development_progression") or {}
    floor_id = _text(progression.get("demonstrated_floor_option_id"))

    breakdown = {
        "mesocycle_alignment": 30 if role != "unclassified" else 0,
        "microcycle_alignment": 30 if option_id == preferred else 10,
        "progression_alignment": 15,
        "prescription_specificity": (
            15
            if prescription.get("completeness") == "full"
            else 10
            if prescription.get("completeness") == "external"
            else 0
        ),
        "near_term_resolution": 10 if option_id == preferred else 0,
    }

    if planned_step_id:
        if option_id == planned_step_id:
            breakdown["progression_alignment"] = 15
        elif option_id == floor_id:
            breakdown["progression_alignment"] = 8
        else:
            breakdown["progression_alignment"] = 4

    return {
        "total": sum(breakdown.values()),
        "breakdown": breakdown,
        "basis": "deterministic_constraint_alignment",
    }


def _selection_reason(day: dict, selected: dict) -> str:
    resolution = day.get("dose_resolution") or {}
    source = _text(resolution.get("source"))
    if source == "near_term_ai_revision":
        return _text(resolution.get("basis")) or "Närtidsbedömningen har valt en konservativt reducerad, förgodkänd dos."
    step = day.get("development_step") or {}
    if _text(step.get("option_id")) == _text(selected.get("dose_option_id")):
        return _text(step.get("reason")) or _text(day.get("reason"))
    option = next(
        (
            item
            for item in (day.get("dose_options") or [])
            if _text(item.get("id")) == _text(selected.get("dose_option_id"))
        ),
        None,
    )
    return _text((option or {}).get("intent")) or _text(day.get("reason"))


def build_workout_design(day: dict, document: dict, strategy: dict) -> dict:
    if day.get("sport") in {"rest", "open"}:
        raise WorkoutDesignError("rest/open har inget workout_design")

    role = _mesocycle_role(day, strategy)
    candidates = []
    for option in _candidate_options(day):
        prescription = _prescription(day, option, document)
        score = _score_candidate(day, option, prescription, role)
        candidates.append(
            {
                "id": _text(option.get("id")) or "current-session",
                "dose_option_id": (
                    _text(option.get("id"))
                    if any(
                        _text(item.get("id")) == _text(option.get("id"))
                        for item in (day.get("dose_options") or [])
                    )
                    else ""
                ),
                "session": _text(option.get("session")) or _text(day.get("session")),
                "intent": _text(option.get("intent")) or _text(day.get("reason")),
                "dose": {
                    "kind": option.get("kind"),
                    "value": option.get("value"),
                },
                "stimuli": copy.deepcopy(day.get("stimuli") or []),
                "prescription": prescription,
                "score": score,
            }
        )

    if not candidates:
        raise WorkoutDesignError(f"{day.get('date')}: inga workout-kandidater")

    # Selection is deterministic. The plan's resolved/baseline/development option
    # receives the strongest microcycle and near-term alignment, while
    # prescription specificity remains a separate quality dimension.
    selected = max(
        candidates,
        key=lambda item: (item["score"]["total"], item["id"] == _preferred_option_id(day)),
    )

    progression = day.get("development_step") or {}
    return {
        "schema_version": WORKOUT_DESIGN_SCHEMA_VERSION,
        "objective": {
            "mesocycle_role": role,
            "priority_role": day.get("priority_role"),
            "stimuli": copy.deepcopy(day.get("stimuli") or []),
            "mesocycle_id": day.get("mesocycle_id") or "",
            "microcycle_id": day.get("microcycle_id") or "",
            "microcycle_slot": day.get("microcycle_slot") or "",
        },
        "near_term_context": {
            "load_dimensions": copy.deepcopy(day.get("load_dimensions") or []),
            "selection_uses_only_preapproved_doses": bool(day.get("dose_options")),
        },
        "progression_from_previous": {
            "relation": progression.get("relation") or (
                "maintenance" if role == "maintenance" else "support"
            ),
            "reason": _text(progression.get("reason")) or _selection_reason(day, selected),
            "demonstrated_floor_option_id": (
                (day.get("development_progression") or {}).get("demonstrated_floor_option_id") or ""
            ),
        },
        "candidates": candidates,
        "selected_candidate_id": selected["id"],
        "selection": {
            "method": "deterministic_constraint_scoring",
            "preferred_dose_option_id": _preferred_option_id(day),
            "reason_for_today": _selection_reason(day, selected),
        },
    }


def selected_candidate(day: dict) -> dict:
    design = day.get("workout_design") or {}
    selected_id = _text(design.get("selected_candidate_id"))
    return next(
        (item for item in (design.get("candidates") or []) if _text(item.get("id")) == selected_id),
        {},
    )


def materialize_document(document: dict, strategy: dict) -> dict:
    result = copy.deepcopy(document)
    result["workout_design_schema_version"] = WORKOUT_DESIGN_SCHEMA_VERSION
    for day in result.get("days") or []:
        if day.get("sport") in {"rest", "open"}:
            day.pop("workout_design", None)
            continue
        day["workout_design"] = build_workout_design(day, result, strategy)
    return result


def validate_workout_design(day: dict, context: str) -> bool:
    design = day.get("workout_design")
    if not isinstance(design, dict):
        raise WorkoutDesignError(f"{context}: workout_design saknas")
    if design.get("schema_version") != WORKOUT_DESIGN_SCHEMA_VERSION:
        raise WorkoutDesignError(f"{context}: workout_design schema_version ogiltig")

    objective = design.get("objective")
    if not isinstance(objective, dict):
        raise WorkoutDesignError(f"{context}: objective saknas")
    if list(objective.get("stimuli") or []) != list(day.get("stimuli") or []):
        raise WorkoutDesignError(f"{context}: workout_design stimuli avviker från dagplanen")
    for field in ("mesocycle_id", "microcycle_id", "microcycle_slot"):
        expected = _text(day.get(field))
        actual = _text(objective.get(field))
        if expected and actual != expected:
            raise WorkoutDesignError(f"{context}: workout_design {field} avviker från dagplanen")

    candidates = design.get("candidates")
    if not isinstance(candidates, list) or not (1 <= len(candidates) <= MAX_CANDIDATES):
        raise WorkoutDesignError(f"{context}: workout_design kräver 1–{MAX_CANDIDATES} kandidater")
    ids = [_text(item.get("id")) for item in candidates if isinstance(item, dict)]
    if len(ids) != len(candidates) or any(not item for item in ids) or len(set(ids)) != len(ids):
        raise WorkoutDesignError(f"{context}: kandidat-id saknas eller är dubblerat")
    selected_id = _text(design.get("selected_candidate_id"))
    if selected_id not in ids:
        raise WorkoutDesignError(f"{context}: selected_candidate_id saknas bland kandidater")

    selected = next(item for item in candidates if _text(item.get("id")) == selected_id)
    prescription = selected.get("prescription")
    if not isinstance(prescription, dict):
        raise WorkoutDesignError(f"{context}: vald kandidat saknar prescription")
    blocks = prescription.get("blocks")
    if not isinstance(blocks, list):
        raise WorkoutDesignError(f"{context}: prescription.blocks måste vara lista")

    selected_score = ((selected.get("score") or {}).get("total"))
    candidate_scores = [((item.get("score") or {}).get("total")) for item in candidates]
    if not isinstance(selected_score, (int, float)) or any(
        not isinstance(score, (int, float)) for score in candidate_scores
    ):
        raise WorkoutDesignError(f"{context}: kandidatpoäng saknas")
    if selected_score != max(candidate_scores):
        raise WorkoutDesignError(f"{context}: vald kandidat är inte högst rankad")

    # Quality anchors and authored swim sessions may never degrade to a generic
    # title/focus string. They need an executable selected prescription.
    requires_full = day.get("priority_role") == "anchor" or day.get("sport") == "swim"
    if requires_full:
        if prescription.get("executable") is not True:
            raise WorkoutDesignError(f"{context}: prioriterat/simpass saknar exekverbart recept")
        if prescription.get("completeness") != "full":
            raise WorkoutDesignError(f"{context}: prioriterat/simpass kräver full prescription")
        if not blocks:
            raise WorkoutDesignError(f"{context}: prioriterat/simpass saknar prescription-block")

    return True
