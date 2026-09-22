#!/usr/bin/env python3
"""Canonical planning-relevant goal contract helpers.

The goal model is a portfolio: enduring development goals coexist with dated
performance goals. A performance goal can change emphasis/specificity without
implicitly replacing the enduring development identity.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy


class GoalContractError(ValueError):
    pass


def active_development_goals(goal: dict) -> list[dict]:
    return [
        deepcopy(item)
        for item in (goal.get("development_goals") or [])
        if item.get("status") == "active"
    ]


def active_performance_goals(goal: dict) -> list[dict]:
    return [
        deepcopy(item)
        for item in (goal.get("performance_goals") or [])
        if item.get("status") == "active"
    ]


def validate_goal_portfolio(goal: dict) -> bool:
    if goal.get("schema_version") != 3:
        raise GoalContractError("målbild: schema_version måste vara 3")

    north_star = str(goal.get("goal") or "").strip()
    if not north_star:
        raise GoalContractError("målbild: goal saknas")

    development = active_development_goals(goal)
    if not development:
        raise GoalContractError("målbild: minst ett aktivt development_goal krävs")

    ids = set()
    for index, item in enumerate(development):
        context = f"målbild.development_goals[{index}]"
        goal_id = str(item.get("id") or "").strip()
        if not goal_id or goal_id in ids:
            raise GoalContractError(f"{context}: unikt id krävs")
        ids.add(goal_id)
        if item.get("type") != "development":
            raise GoalContractError(f"{context}: type måste vara development")
        if item.get("role") != "enduring":
            raise GoalContractError(f"{context}: aktivt utvecklingsmål måste ha role=enduring")
        if item.get("horizon") != "ongoing":
            raise GoalContractError(f"{context}: varaktigt mål måste ha horizon=ongoing")
        if not str(item.get("objective") or "").strip():
            raise GoalContractError(f"{context}: objective saknas")
        disciplines = item.get("disciplines")
        if not isinstance(disciplines, list) or not disciplines:
            raise GoalContractError(f"{context}: disciplines saknas")
        if not all(isinstance(value, str) and value.strip() for value in disciplines):
            raise GoalContractError(f"{context}: disciplines innehåller ogiltigt värde")
        if not str(item.get("principle") or "").strip():
            raise GoalContractError(f"{context}: principle saknas")

    for index, item in enumerate(active_performance_goals(goal)):
        context = f"målbild.performance_goals[{index}]"
        goal_id = str(item.get("id") or "").strip()
        if not goal_id or goal_id in ids:
            raise GoalContractError(f"{context}: unikt id krävs")
        ids.add(goal_id)
        if not str(item.get("target") or "").strip():
            raise GoalContractError(f"{context}: target saknas")

    return True


def planning_goal_set(goal: dict) -> list[dict]:
    validate_goal_portfolio(goal)
    rows = []
    for item in active_development_goals(goal):
        rows.append(
            {
                "id": item["id"],
                "type": "development",
                "role": item["role"],
                "label": item.get("label") or item["id"],
                "horizon": item["horizon"],
                "objective": item["objective"],
                "disciplines": list(item.get("disciplines") or []),
                "principle": item["principle"],
            }
        )
    for item in active_performance_goals(goal):
        rows.append(
            {
                "id": item["id"],
                "type": "performance",
                "role": item.get("role") or "performance_goal",
                "priority_class": item.get("priority_class"),
                "event": item.get("event"),
                "sport": item.get("sport"),
                "target": item.get("target"),
                "event_date": item.get("event_date"),
                "principle": item.get("principle"),
            }
        )
    return rows


def planning_goal_payload(goal: dict) -> dict:
    return {
        "goal": str(goal.get("goal") or "").strip(),
        "development_goals": deepcopy(goal.get("development_goals") or []),
        "performance_goals": deepcopy(goal.get("performance_goals") or []),
    }


def planning_goal_hash(goal: dict) -> str:
    payload = planning_goal_payload(goal)
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
