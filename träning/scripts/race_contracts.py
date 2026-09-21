#!/usr/bin/env python3
"""Verified competition-goal context for adaptive planning.

The race profile contains source facts. Derived timing/context is recalculated
from the planning date and never treated as an automatic training dose.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date


REQUIRED_PROFILE_NUMBERS = (
    "total_distance_m",
    "run_distance_m",
    "swim_distance_m",
    "elevation_gain_m",
)


class RaceContractError(ValueError):
    pass


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def active_primary_performance_goal(goal: dict) -> dict | None:
    items = [
        item
        for item in (goal.get("performance_goals") or [])
        if item.get("status") == "active"
        and item.get("role") == "primary_performance_goal"
    ]
    if not items:
        return None
    if len(items) > 1:
        raise RaceContractError(
            "målbild: flera aktiva primary_performance_goal stöds inte utan explicit prioritering"
        )
    return items[0]


def validate_race_goal(goal: dict) -> bool:
    item = active_primary_performance_goal(goal)
    if item is None:
        return True

    event_date = item.get("event_date")
    if not event_date:
        raise RaceContractError("målbild: aktivt prestationsmål saknar event_date")
    try:
        _as_date(event_date)
    except (TypeError, ValueError) as exc:
        raise RaceContractError("målbild: event_date måste vara ISO-datum") from exc

    profile = item.get("race_profile")
    if not isinstance(profile, dict):
        raise RaceContractError("målbild: aktivt prestationsmål saknar race_profile")

    for key in REQUIRED_PROFILE_NUMBERS:
        value = profile.get(key)
        if not isinstance(value, (int, float)) or value <= 0:
            raise RaceContractError(f"målbild: race_profile.{key} måste vara positivt tal")

    source = profile.get("source") or {}
    if not isinstance(source, dict) or not str(source.get("url") or "").strip():
        raise RaceContractError("målbild: race_profile.source.url saknas")
    if not str(source.get("verified_on") or "").strip():
        raise RaceContractError("målbild: race_profile.source.verified_on saknas")

    # Preserve the publisher's numbers. Åland's published total differs by 10 m
    # from published run+swim components; do not silently 'correct' source data.
    delta = float(profile["total_distance_m"]) - (
        float(profile["run_distance_m"]) + float(profile["swim_distance_m"])
    )
    if abs(delta) > 100:
        raise RaceContractError(
            "målbild: race_profile totaldistans avviker >100 m från publicerade delkomponenter"
        )

    characteristics = profile.get("characteristics")
    if not isinstance(characteristics, list) or not all(
        isinstance(x, str) and x.strip() for x in characteristics
    ):
        raise RaceContractError("målbild: race_profile.characteristics måste vara textlista")
    return True


def horizon_stage(days_to_event: int, event_horizon_policy: dict | None) -> str:
    if days_to_event < 0:
        return "past"
    policy = event_horizon_policy or {}
    taper = int(policy.get("taper_review_days") or 21)
    race_specific = int(policy.get("race_specific_review_days") or 84)
    specificity_build = int(policy.get("specificity_build_review_days") or 168)
    if days_to_event <= taper:
        return "taper_review"
    if days_to_event <= race_specific:
        return "race_specific"
    if days_to_event <= specificity_build:
        return "specificity_build"
    return "foundation"


def build_competition_context(
    goal: dict,
    as_of,
    event_horizon_policy: dict | None = None,
) -> dict:
    validate_race_goal(goal)
    item = active_primary_performance_goal(goal)
    if item is None:
        return {"available": False}

    as_of_date = _as_date(as_of)
    event_date = _as_date(item["event_date"])
    days = (event_date - as_of_date).days
    profile = deepcopy(item["race_profile"])
    total = float(profile["total_distance_m"])
    run = float(profile["run_distance_m"])
    swim = float(profile["swim_distance_m"])
    delta = total - run - swim

    return {
        "available": True,
        "goal_id": item.get("id"),
        "event": item.get("event"),
        "event_date": event_date.isoformat(),
        "as_of": as_of_date.isoformat(),
        "days_to_event": days,
        "weeks_to_event": round(days / 7.0, 1),
        "horizon_stage": horizon_stage(days, event_horizon_policy),
        "target": item.get("target"),
        "target_category": item.get("target_category"),
        "category_status": "specified" if item.get("target_category") else "unspecified",
        "sport": item.get("sport"),
        "race_profile": profile,
        "derived": {
            "run_share_of_published_total": round(run / total, 4),
            "swim_share_of_published_total": round(swim / total, 4),
            "published_component_delta_m": int(round(delta)),
        },
        "course_requirement_mapping": [
            {
                "source_fact": "run_distance_m",
                "published_value": int(run),
                "mapped_capabilities": ["run_easy_distance", "run_threshold"],
                "system_gap": None,
            },
            {
                "source_fact": "swim_distance_m",
                "published_value": int(swim),
                "mapped_capabilities": ["swim_aerobic", "swim_threshold", "swim_technique"],
                "system_gap": None,
            },
            {
                "source_fact": "characteristics: många växlingar",
                "published_value": "Många växlingar",
                "mapped_capabilities": [],
                "system_gap": "combined_swimrun_transition_durability",
            },
        ],
        "planning_implications": [
            "36,57 km publicerad löpdistans gör löptålighet över upprepade delsträckor till ett centralt tävlingskrav.",
            "9,96 km publicerad simdistans gör hög simuthållighet och bibehållen teknik under lång total simtid till ett centralt tävlingskrav.",
            "Officiell banbeskrivning anger många växlingar; swimrun-specifik kombinationstålighet och övergångsvana behöver byggas innan tävlingsspecifika block.",
            "391 höjdmeter ska vägas in, men systemet får inte hitta på en mer kuperad profil än den publicerade.",
            "Tävlingsdatumet styr när specificiteten ska omprövas; det får inte ensamt utlösa automatisk volym- eller intensitetsökning.",
        ],
    }
