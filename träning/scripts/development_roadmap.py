#!/usr/bin/env python3
"""Deterministic transparency projection from planning state to goal journey.

This module does not make coaching decisions. It explains decisions already
present in the canonical planning state and derives review dates from the
configured event-horizon policy. Dates are checkpoints for reconsidering
specificity, never predictions of when physiology will be achieved.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta


SCHEMA_VERSION = 1

ROLE_LABELS = {
    "primary": "Utvecklas nu",
    "secondary": "Stödjande utveckling",
    "maintenance": "Underhåll",
    "protected_capacity": "Skyddad kapacitet",
    "external_load": "Extern belastning",
    "supporting": "Stödjande",
}

STAGE_LABELS = {
    "foundation": "Grundkapacitet",
    "specificity_build": "Specificitetsbygge",
    "race_specific": "Tävlingsspecifikt",
    "taper_review": "Tävlingsnära översyn",
}


def _iso(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _goal_label(goal):
    if goal.get("label"):
        return str(goal["label"])
    event = str(goal.get("event") or "").strip()
    target = str(goal.get("target") or "").strip()
    if event and target:
        return f"{event} · {target}"
    return event or target or str(goal.get("id") or "Mål")


def _goal_rows(strategy):
    contract = strategy.get("goal_contract") or {}
    canonical = []
    for goal in contract.get("goal_set") or []:
        if not isinstance(goal, dict):
            continue
        target_date = goal.get("event_date")
        if target_date is None and goal.get("horizon") not in (None, "ongoing"):
            target_date = goal.get("horizon")
        canonical.append(
            {
                "id": str(goal.get("id") or ""),
                "source": "planning_goal",
                "label": _goal_label(goal),
                "role": str(goal.get("role") or ""),
                "type": str(goal.get("type") or ""),
                "target": goal.get("target"),
                "target_date": target_date,
                "date_kind": "fixed_event_date" if goal.get("event_date") else "ongoing",
            }
        )

    declared = []
    for index, goal in enumerate(contract.get("declared_profile_goals") or [], start=1):
        if not isinstance(goal, dict):
            continue
        text = str(goal.get("text") or "").strip()
        if not text:
            continue
        declared.append(
            {
                "id": f"profile-goal-{index}",
                "source": "athlete_profile",
                "label": text,
                "role": "declared",
                "type": "declared",
                "target": None,
                "target_date": goal.get("target_date"),
                "date_kind": "declared_target_date" if goal.get("target_date") else "open_horizon",
                "importance": goal.get("importance"),
            }
        )
    return canonical, declared


def _capability_role(key, contract):
    for role in ("primary", "secondary", "maintenance", "protected_capacity", "external_load"):
        if key in (contract.get(role) or []):
            return role
    return "supporting"


def _has_fact(fact):
    if not isinstance(fact, dict) or not fact:
        return False
    if fact.get("evidence"):
        return True
    if isinstance(fact.get("session_count"), int) and fact["session_count"] > 0:
        return True
    return any(isinstance(fact.get(name), dict) and fact.get(name) for name in ("longest_duration", "longest_distance"))


def _evidence_state(key, athlete_state):
    dose = (((athlete_state.get("dose_response") or {}).get("by_capability") or {}).get(key) or {})
    if dose.get("absorbed_value") is not None:
        return "absorbed", "Absorberad nivå finns dokumenterad i faktalagret."
    if dose.get("tolerated_value") is not None:
        return "tolerated", "Tolererad nivå finns dokumenterad; absorption är ännu inte fastställd."
    if dose.get("demonstrated_value") is not None:
        return "demonstrated", "Genomförd nivå finns dokumenterad; det är inte samma sak som absorberad kapacitet."

    fact = ((athlete_state.get("capability_facts") or {}).get(key) or {})
    if _has_fact(fact):
        return "observed", "Observerad träningshistorik finns, men ingen säker absorberad nivå är fastställd."
    return "missing", "Tillräcklig observerad baslinje saknas för en säker kapacitetsbedömning."


def _status_for_date(day, as_of):
    if day is None or as_of is None:
        return "planned"
    if day < as_of:
        return "passed"
    if day == as_of:
        return "today"
    return "planned"


def build_development_roadmap(strategy, policy, athlete_state):
    """Build a read-only explanation layer from already-decided planning state."""
    goal_contract = strategy.get("goal_contract") or {}
    meso = strategy.get("current_mesocycle") or {}
    contract = meso.get("contract") or {}
    canonical_goals, declared_goals = _goal_rows(strategy)

    contribution_by_goal = {
        str(row.get("goal_id") or ""): deepcopy(row)
        for row in (meso.get("goal_contributions") or [])
        if isinstance(row, dict)
    }
    for goal in canonical_goals:
        contribution = contribution_by_goal.get(goal["id"])
        if contribution:
            goal["current_block_contribution"] = contribution.get("contribution")
            goal["current_block_tradeoff"] = contribution.get("tradeoff")

    capabilities = []
    for item in strategy.get("capability_portfolio") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        evidence_state, evidence_summary = _evidence_state(key, athlete_state)
        role = _capability_role(key, contract)
        capabilities.append(
            {
                "key": key,
                "label": str(item.get("label") or key),
                "role": role,
                "role_label": ROLE_LABELS[role],
                "mode": item.get("mode"),
                "evidence_state": evidence_state,
                "evidence_summary": evidence_summary,
                "next_review_date": meso.get("evaluation_date") if role in {"primary", "secondary"} else None,
            }
        )

    active_block = {
        "id": meso.get("id"),
        "title": meso.get("title"),
        "status": "active",
        "start_date": meso.get("start_date"),
        "end_date": meso.get("end_date"),
        "evaluation_date": meso.get("evaluation_date"),
        "hypothesis": meso.get("hypothesis"),
        "goal_contribution": meso.get("goal_contribution"),
        "goal_contributions": deepcopy(meso.get("goal_contributions") or []),
        "success_signals": deepcopy(meso.get("success_signals") or []),
        "review_questions": deepcopy(meso.get("review_questions") or []),
        "primary_capabilities": deepcopy(contract.get("primary") or []),
        "secondary_capabilities": deepcopy(contract.get("secondary") or []),
        "maintenance_capabilities": deepcopy(contract.get("maintenance") or []),
        "protected_capabilities": deepcopy(contract.get("protected_capacity") or []),
        "external_load": deepcopy(contract.get("external_load") or []),
    }

    as_of = _iso((athlete_state.get("fact_window") or {}).get("end"))
    competition = goal_contract.get("competition_context") or {}
    event_date = _iso(competition.get("event_date"))
    horizon = policy.get("event_horizon_policy") or {}
    stages = horizon.get("stages") or {}

    timeline = []
    block_start = _iso(meso.get("start_date"))
    block_end = _iso(meso.get("end_date"))
    if block_start:
        timeline.append(
            {
                "id": "active-block",
                "kind": "active_block",
                "status": "active",
                "date": block_start.isoformat(),
                "end_date": block_end.isoformat() if block_end else None,
                "title": str(meso.get("title") or "Aktuellt utvecklingsblock"),
                "description": str(meso.get("goal_contribution") or ""),
                "certainty": "decided",
            }
        )

    evaluation_date = _iso(meso.get("evaluation_date"))
    if evaluation_date:
        timeline.append(
            {
                "id": "mesocycle-review",
                "kind": "checkpoint",
                "status": _status_for_date(evaluation_date, as_of),
                "date": evaluation_date.isoformat(),
                "end_date": None,
                "title": "Utvärdera aktuellt block",
                "description": "Här bedöms faktisk respons mot blockets framgångssignaler innan nästa utvecklingsbeslut.",
                "certainty": "scheduled_review",
            }
        )

    if event_date:
        for key, config_key in (
            ("specificity_build", "specificity_build_review_days"),
            ("race_specific", "race_specific_review_days"),
            ("taper_review", "taper_review_days"),
        ):
            days = horizon.get(config_key)
            if not isinstance(days, int) or days < 0:
                continue
            transition = event_date - timedelta(days=days)
            timeline.append(
                {
                    "id": f"{key}-review",
                    "kind": "decision_window",
                    "status": _status_for_date(transition, as_of),
                    "date": transition.isoformat(),
                    "end_date": None,
                    "title": STAGE_LABELS.get(key, key),
                    "description": str(stages.get(key) or ""),
                    "certainty": "policy_review_date",
                }
            )
        timeline.append(
            {
                "id": "goal-event",
                "kind": "goal_event",
                "status": _status_for_date(event_date, as_of),
                "date": event_date.isoformat(),
                "end_date": None,
                "title": _goal_label(
                    {
                        "event": competition.get("event"),
                        "target": competition.get("target"),
                        "id": competition.get("goal_id"),
                    }
                ),
                "description": "Fast måldag. Resultatet avgörs här; tidigare datum i tidslinjen är planerings- och utvärderingspunkter.",
                "certainty": "fixed_event_date",
            }
        )

    timeline.sort(key=lambda row: (str(row.get("date") or "9999-12-31"), row["id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "projection_type": "derived_transparency_view",
        "goal_basis_hash": goal_contract.get("goal_hash"),
        "as_of": as_of.isoformat() if as_of else None,
        "interpretation_boundary": (
            "Tidslinjen visar beslutade träningsblock, fasta måldatum och planerade omprövningspunkter. "
            "Den förutsäger inte vilket datum en fysiologisk kapacitet uppnås. Sådan utveckling bedöms "
            "vid checkpoints från faktisk träning och respons."
        ),
        "planning_principle": str(horizon.get("principle") or ""),
        "canonical_goals": canonical_goals,
        "declared_profile_goals": declared_goals,
        "active_block": active_block,
        "capabilities": capabilities,
        "timeline": timeline,
    }
